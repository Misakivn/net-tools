"""Giám sát kết nối liên tục: ping router + internet, ghi lại mỗi lần rớt mạng."""
import collections
import csv
import os
import threading
import time

from nettools.core.system import data_dir

OUTAGE_FIELDS = ["start", "end", "seconds", "cause"]


class Monitor:
    """Luồng nền. pinger(host)->ms|None. on_sample(t, gw_ms, net_ms), on_event(dict)."""

    def __init__(self, pinger, on_sample=None, on_event=None, history=600):
        self.pinger = pinger
        self.on_sample = on_sample or (lambda *a: None)
        self.on_event = on_event or (lambda e: None)
        self.samples = collections.deque(maxlen=history)
        self.gateway = ""
        self.host = "1.1.1.1"
        self.interval = 3
        self._stop = threading.Event()
        self._thread = None
        self._fails = 0
        self._outage_start = None
        self._outage_gw_down = False
        self.outages = []

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            t0 = time.time()
            gw = self.pinger(self.gateway) if self.gateway else None
            net = self.pinger(self.host)
            self.step(t0, gw, net)
            self._stop.wait(max(0.5, self.interval - (time.time() - t0)))

    def step(self, t, gw, net):
        """Xử lý 1 mẫu (tách riêng để kiểm thử)."""
        self.samples.append((t, gw, net))
        self.on_sample(t, gw, net)
        if net is None:
            self._fails += 1
            if self._fails == 2:  # 2 lần liên tiếp mới tính là rớt (tránh mất 1 gói lẻ)
                self._outage_start = t - self.interval
                self._outage_gw_down = False
                self.on_event({"type": "down", "start": self._outage_start})
            if self._outage_start and self.gateway and gw is None:
                self._outage_gw_down = True
        else:
            if self._outage_start:
                cause = ("Mất kết nối tới router (dây mạng / Wi-Fi / router)" if self._outage_gw_down
                         else "Router vẫn chạy nhưng mất internet (phía tòa nhà / nhà mạng)")
                ev = {"type": "up", "start": self._outage_start, "end": t,
                      "seconds": round(t - self._outage_start), "cause": cause}
                self.outages.append(ev)
                self._save(ev)
                self.on_event(ev)
            self._fails = 0
            self._outage_start = None

    def stats(self, window=None):
        """Thống kê trên các mẫu gần nhất: dict avg, loss, uptime."""
        data = list(self.samples)[-window:] if window else list(self.samples)
        if not data:
            return {"avg": None, "loss": None, "uptime": None, "gw_avg": None}
        net = [n for _, _, n in data if n is not None]
        gw = [g for _, g, _ in data if g is not None]
        return {"avg": sum(net) / len(net) if net else None,
                "gw_avg": sum(gw) / len(gw) if gw else None,
                "loss": 100 * (len(data) - len(net)) / len(data),
                "uptime": 100 * len(net) / len(data)}

    @staticmethod
    def log_path():
        return os.path.join(data_dir(), "outages.csv")

    def _save(self, ev):
        path = self.log_path()
        try:
            new = not os.path.exists(path)
            with open(path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(OUTAGE_FIELDS)
                w.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ev["start"])),
                            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ev["end"])),
                            ev["seconds"], ev["cause"]])
        except OSError:
            pass

    @classmethod
    def load_outages(cls, limit=100):
        try:
            with open(cls.log_path(), newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))[-limit:]
        except OSError:
            return []
