"""Chẩn đoán: traceroute, CGNAT, kiểm tra website, kiểm tra cổng, dò MTU."""
import re
import socket
import time
from urllib.parse import urlparse

import requests

from nettools.core import dns
from nettools.core.netinfo import classify_ip
from nettools.core.system import popen, run

IP_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}|[0-9a-fA-F:]+:[0-9a-fA-F:]+)")


def parse_tracert_line(line):
    """(hop, [ms|None]*3, ip|None) hoặc None nếu không phải dòng hop."""
    m = re.match(r"^\s*(\d+)\s+(.*)$", line)
    if not m:
        return None
    tokens = m.group(2).split()
    times, i = [], 0
    while i < len(tokens) and len(times) < 3:
        tok = tokens[i]
        if tok == "*":
            times.append(None)
        elif re.fullmatch(r"<?\d+", tok) and i + 1 < len(tokens) and tokens[i + 1] == "ms":
            times.append(int(tok.lstrip("<")))
            i += 1
        elif re.fullmatch(r"<?\d+ms", tok):
            times.append(int(tok.lstrip("<")[:-2]))
        else:
            break
        i += 1
    if len(times) < 3:
        return None
    last = tokens[-1].strip("[]") if tokens else ""
    ip = last if IP_RE.fullmatch(last) else None
    return int(m.group(1)), times, ip


def traceroute(host, on_hop, max_hops=20):
    """Chạy tracert, gọi on_hop(hop, times, ip, kind) cho từng hop. Trả list hop."""
    proc = popen(["tracert", "-d", "-w", "800", "-h", str(max_hops), host])
    hops = []
    for line in proc.stdout:
        parsed = parse_tracert_line(line)
        if parsed:
            hop, times, ip = parsed
            kind = classify_ip(ip) if ip else ""
            hops.append((hop, times, ip, kind))
            on_hop(hop, times, ip, kind)
    proc.wait()
    return hops


def nat_summary(hops):
    """Nhận định NAT từ danh sách hop (hop, times, ip, kind)."""
    kinds = [k for _, _, ip, k in hops if ip]
    if "cgnat" in kinds:
        return ("cgnat", "Mạng đang bị CGNAT (có IP 100.64.x.x trên đường đi): "
                "không mở cổng từ ngoài vào được, muốn host server cần VPS hoặc tunnel.")
    privates = 0
    for k in kinds:
        if k != "private":
            break
        privates += 1
    if privates >= 2:
        return ("double", f"Có {privates} lớp mạng nội bộ (double NAT) — thường gặp ở mạng tòa nhà. "
                "Mở cổng sẽ khó vì bạn không quản lý router phía trên.")
    if privates == 1:
        return ("single", "Chỉ 1 lớp NAT (router nhà bạn) — có thể mở cổng trên router nếu có quyền.")
    return ("unknown", "Không đủ dữ liệu để kết luận về NAT.")


def normalize_url(url):
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    p = urlparse(url)
    if not p.hostname:
        raise ValueError("URL không hợp lệ.")
    return url, p.hostname


def website_check(url):
    """Kiểm tra 1 website: phân giải DNS (máy + Cloudflare) và tải trang. Trả list dòng kết quả."""
    url, host = normalize_url(url)
    lines = [f"Kiểm tra: {url}"]
    try:
        t = time.perf_counter()
        sys_ips = sorted({a[4][0] for a in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)})
        lines.append(f"✔ DNS máy bạn: {', '.join(sys_ips[:4])}  ({(time.perf_counter() - t) * 1000:.0f} ms)")
    except OSError as e:
        sys_ips = []
        lines.append(f"✖ DNS máy bạn không phân giải được: {e}")
    ms, cf_ips = dns.resolve("1.1.1.1", host)
    if ms is None:
        lines.append("✖ Không hỏi được Cloudflare DNS (1.1.1.1).")
    elif not cf_ips:
        lines.append("✖ Cloudflare DNS: tên miền không tồn tại.")
    else:
        lines.append(f"✔ Cloudflare DNS: {', '.join(cf_ips[:4])}  ({ms:.0f} ms)")
    try:
        t = time.perf_counter()
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 NetTools"},
                         allow_redirects=True, stream=True)
        elapsed = (time.perf_counter() - t) * 1000
        r.close()
        ok = r.status_code < 400
        lines.append(f"{'✔' if ok else '✖'} HTTP {r.status_code} {r.reason}  ({elapsed:.0f} ms)"
                     + (f"  → {r.url}" if r.url.rstrip('/') != url.rstrip('/') else ""))
        if ok:
            lines.append("➜ Website hoạt động bình thường từ máy bạn.")
        elif r.status_code in (401, 403):
            lines.append("➜ Website chạy nhưng từ chối truy cập (bị chặn/vùng/đăng nhập).")
        else:
            lines.append("➜ Website trả lỗi — có thể đang gặp sự cố phía máy chủ.")
    except requests.exceptions.SSLError:
        lines.append("✖ Lỗi chứng chỉ HTTPS — có thể bị chặn bởi mạng/ứng dụng diệt virus.")
    except requests.RequestException as e:
        if not sys_ips and cf_ips:
            lines.append("➜ DNS của bạn không phân giải được nhưng Cloudflare thì được: "
                         "hãy đổi DNS ở trang DNS.")
        else:
            lines.append(f"✖ Không kết nối được: {type(e).__name__}. Website có thể đang sập "
                         "hoặc bị chặn trên mạng này.")
    return lines


def tcp_check(host, port, timeout=4):
    """(ok, ms|None, thông báo) khi kết nối TCP tới host:port."""
    try:
        t = time.perf_counter()
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, (time.perf_counter() - t) * 1000, "Mở (kết nối được)"
    except socket.timeout:
        return False, None, "Hết thời gian chờ (bị lọc/chặn hoặc máy chủ không trả lời)"
    except ConnectionRefusedError:
        return False, None, "Đóng (máy chủ từ chối)"
    except OSError as e:
        return False, None, f"Lỗi: {e}"


COMMON_PORTS = {"HTTP": 80, "HTTPS": 443, "SSH": 22, "RDP": 3389, "Minecraft": 25565,
                "Discord voice": 50000, "SMTP": 25, "DNS": 53}


def ping_df(host, size):
    """True nếu gói có kích thước size đi được mà không cần phân mảnh."""
    _, out = run(["ping", "-f", "-l", str(size), "-n", "1", "-w", "1500", host], timeout=10)
    return "TTL=" in out.upper()


def find_mtu(host, progress=None, low=1200, high=1472):
    """MTU lớn nhất (payload + 28 byte header) bằng tìm kiếm nhị phân; None nếu không ping được."""
    if not ping_df(host, low):
        return None
    best = low
    while low <= high:
        mid = (low + high) // 2
        if progress:
            progress(mid)
        if ping_df(host, mid):
            best, low = mid, mid + 1
        else:
            high = mid - 1
    return best + 28
