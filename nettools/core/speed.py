"""Đo Ping/Jitter/Loss/Download/Upload và đánh giá chất lượng (giữ logic từ NetCheck)."""
import csv
import os
import re
import time

import requests

from nettools.core.system import data_dir, popen

DOWN_BYTES = 25_000_000
DOWN_URL = f"https://speed.cloudflare.com/__down?bytes={DOWN_BYTES}"
UP_BYTES = 10_000_000
UP_URL = "https://speed.cloudflare.com/__up"
PING_COUNT = 15
PING_HOSTS = ["1.1.1.1", "8.8.8.8", "9.9.9.9", "google.com", "yahoo.co.jp"]
UNITS = {"Mbps": (1, 1), "MB/s": (1 / 8, 2), "Kbps": (1000, 0)}  # (hệ số từ Mbps, số lẻ)
HOST_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-:]*")


def valid_host(host):
    """Host đi thẳng vào ping.exe/tracert: chặn ký tự lạ và tham số bắt đầu bằng '-' hoặc '/'."""
    return bool(HOST_RE.fullmatch(host or ""))


def parse_ping(output, sent=PING_COUNT):
    """(ping_tb_ms, jitter_ms, loss_%) từ output ping.exe; chỉ đếm dòng có 'TTL=' (độc lập ngôn ngữ)."""
    times = []
    for line in output.splitlines():
        if "TTL=" in line.upper():
            m = re.search(r"[=<]\s*(\d+)\s*ms", line)
            if m:
                times.append(int(m.group(1)))
    m = re.search(r"\((\d+)%", output)
    loss = float(m.group(1)) if m else 100.0
    # "Destination host unreachable" được ping.exe tính là Received -> lấy số lớn hơn
    loss = max(loss, (sent - len(times)) / sent * 100) if sent else loss
    if not times:
        return None, None, 100.0
    avg = sum(times) / len(times)
    diffs = [abs(a - b) for a, b in zip(times, times[1:])]
    jitter = sum(diffs) / len(diffs) if diffs else 0.0
    return avg, jitter, min(loss, 100.0)


def ping_once(host, timeout_ms=1000):
    """Độ trễ ms của 1 gói ping, None nếu mất gói."""
    proc = popen(["ping", "-n", "1", "-w", str(timeout_ms), host])
    out = proc.communicate(timeout=timeout_ms / 1000 + 5)[0]
    ms, _, _ = parse_ping(out, sent=1)
    return ms


def verdict(ping, jitter, loss, down, up):
    inf = float("inf")
    ping = inf if ping is None else ping
    jitter = inf if jitter is None else jitter
    checks = [
        ("Chơi game Esports", ping < 50 and jitter < 10 and loss == 0,
         "cần Ping < 50ms, Jitter < 10ms, Loss 0%"),
        ("Xem video 4K", down >= 25 and loss < 2, "cần Download ≥ 25 Mbps, Loss < 2%"),
        ("Họp online (Zoom/Meet/Teams)",
         ping < 150 and jitter < 30 and loss < 2 and down >= 3 and up >= 3,
         "cần Ping < 150ms, Jitter < 30ms, Loss < 2%, Down/Up ≥ 3 Mbps"),
    ]
    return [(ok, name, "" if ok else need) for name, ok, need in checks]


# ngưỡng (tốt, tạm) — thấp là tốt với ping/jitter/loss, cao là tốt với tốc độ
THRESHOLDS = {"ping": (50, 120), "jitter": (10, 30), "loss": (0.5, 2),
              "down": (50, 10), "up": (20, 5)}


def quality(key, value):
    """'good' | 'ok' | 'bad' | '' cho 1 chỉ số."""
    if value is None:
        return "bad"
    good, ok = THRESHOLDS[key]
    if key in ("down", "up"):
        return "good" if value >= good else "ok" if value >= ok else "bad"
    return "good" if value <= good else "ok" if value <= ok else "bad"


def fmt_speed(mbps, unit):
    factor, digits = UNITS[unit]
    return f"{mbps * factor:.{digits}f} {unit}"


class Meter:
    """Tính Mbps theo thời gian thực; gọi meter(số_byte_đã_xong)."""

    def __init__(self, total, show):
        self.total, self.show = total, show
        self.start = self.last = None
        self.base = 0
        self.mbps = 0.0

    def __call__(self, done):
        now = time.perf_counter()
        if self.start is None:  # tính từ chunk đầu, bỏ qua thời gian bắt tay TLS
            self.start, self.last, self.base = now, now, done
            return
        self.mbps = (done - self.base) * 8 / max(now - self.start, 1e-6) / 1e6
        if now - self.last > 0.1 or done >= self.total:
            self.last = now
            self.show(self.mbps, done / self.total)


class UploadBody:
    """Body giả lập file để requests stream lên (có Content-Length) và báo tiến độ."""

    def __init__(self, size, report):
        self.size, self.report, self.sent = size, report, 0

    def __len__(self):
        return self.size

    def __iter__(self):
        while chunk := self.read(65536):
            yield chunk

    def read(self, n=-1):
        n = min(n if n and n > 0 else 65536, self.size - self.sent)
        self.sent += n
        if n:
            self.report(self.sent)
        return b"\0" * n


def measure_download(show):
    meter = Meter(DOWN_BYTES, show)
    with requests.get(DOWN_URL, stream=True, timeout=15) as r:
        r.raise_for_status()
        done = 0
        for chunk in r.iter_content(65536):
            done += len(chunk)
            meter(done)
    return meter.mbps


def measure_upload(show):
    meter = Meter(UP_BYTES, show)
    requests.post(UP_URL, data=UploadBody(UP_BYTES, meter), timeout=60,
                  headers={"Content-Type": "application/octet-stream"}).raise_for_status()
    return meter.mbps


# ---------------------------------------------------------------- lịch sử đo

HISTORY_FIELDS = ["time", "ping", "jitter", "loss", "down", "up", "host", "isp"]


def history_path():
    return os.path.join(data_dir(), "speed_history.csv")


def save_history(row, path=None):
    path = path or history_path()
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in HISTORY_FIELDS})


def load_history(limit=200, path=None):
    path = path or history_path()
    rows = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                for k in ("ping", "jitter", "loss", "down", "up"):
                    try:
                        r[k] = float(r[k]) if r[k] not in ("", None) else None
                    except ValueError:
                        r[k] = None
                rows.append(r)
    except OSError:
        pass
    return rows[-limit:]
