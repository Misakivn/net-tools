"""DNS: danh sách DNS, đổi DNS, truy vấn/benchmark trực tiếp qua UDP, DNS mã hóa (DoH)."""
import random
import socket
import statistics
import struct
import time

from nettools.core.system import IS_WINDOWS, powershell, ps_quote, run

DHCP = "Mặc định (DHCP - nhà mạng tự cấp)"
CUSTOM = "Tùy chỉnh (tự nhập)"

# tên -> (servers, mô tả). DoH dò theo IP ở DOH_TEMPLATES.
PRESETS = {
    DHCP: ((), "Dùng DNS do router/nhà mạng cấp"),
    "Cloudflare": (("1.1.1.1", "1.0.0.1"), "Nhanh nhất thế giới, tốt cho game"),
    "Google": (("8.8.8.8", "8.8.4.4"), "Ổn định, phủ rộng"),
    "NTT (Nhật)": (("129.250.35.250", "129.250.35.251"), "Nhà mạng lớn ở Nhật, nhanh trong nước"),
    "IIJ (Nhật)": (("210.130.1.1", "210.130.0.1"), "DNS của IIJ (có thể chỉ trả lời khách IIJ)"),
    "Quad9": (("9.9.9.9", "149.112.112.112"), "Chặn tên miền độc hại"),
    "AdGuard": (("94.140.14.14", "94.140.15.15"), "Chặn quảng cáo & theo dõi"),
    "Cloudflare Family": (("1.1.1.3", "1.0.0.3"), "Chặn malware + nội dung người lớn"),
    CUSTOM: ((), "Tự nhập 2 địa chỉ"),
}

DOH_TEMPLATES = {
    "1.1.1.1": "https://cloudflare-dns.com/dns-query",
    "1.0.0.1": "https://cloudflare-dns.com/dns-query",
    "1.1.1.3": "https://family.cloudflare-dns.com/dns-query",
    "1.0.0.3": "https://family.cloudflare-dns.com/dns-query",
    "8.8.8.8": "https://dns.google/dns-query",
    "8.8.4.4": "https://dns.google/dns-query",
    "9.9.9.9": "https://dns.quad9.net/dns-query",
    "149.112.112.112": "https://dns.quad9.net/dns-query",
    "94.140.14.14": "https://dns.adguard-dns.com/dns-query",
    "94.140.15.15": "https://dns.adguard-dns.com/dns-query",
}


def preset_of(servers):
    """Tên preset khớp với danh sách DNS hiện tại (hoặc '')."""
    for name, (srv, _) in PRESETS.items():
        if srv and list(srv[:len(servers)]) == list(servers[:2]) and servers:
            return name
    return ""


def doh_supported(servers):
    return bool(servers) and all(s in DOH_TEMPLATES for s in servers)


# ---------------------------------------------------------------- truy vấn DNS thô

def build_query(name, qid=None, qtype=1):
    qid = random.randint(0, 0xFFFF) if qid is None else qid
    q = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    for part in name.rstrip(".").split("."):
        q += bytes([len(part)]) + part.encode("idna")
    return q + b"\0" + struct.pack(">HH", qtype, 1)


def _skip_name(data, pos):
    while True:
        length = data[pos]
        if length == 0:
            return pos + 1
        if length & 0xC0 == 0xC0:  # con trỏ nén
            return pos + 2
        pos += length + 1


def parse_a_records(data, qid=None):
    """Danh sách IPv4 trong phần answer; ném ValueError nếu gói không hợp lệ."""
    if len(data) < 12:
        raise ValueError("gói DNS quá ngắn")
    rid, flags, qd, an, _, _ = struct.unpack(">HHHHHH", data[:12])
    if qid is not None and rid != qid:
        raise ValueError("sai ID")
    if flags & 0x000F not in (0, 3):  # 0 = OK, 3 = NXDOMAIN
        raise ValueError(f"DNS lỗi rcode={flags & 0xF}")
    pos = 12
    for _ in range(qd):
        pos = _skip_name(data, pos) + 4
    ips = []
    for _ in range(an):
        pos = _skip_name(data, pos)
        rtype, _, _, rdlen = struct.unpack(">HHIH", data[pos:pos + 10])
        pos += 10
        if rtype == 1 and rdlen == 4:
            ips.append(socket.inet_ntoa(data[pos:pos + 4]))
        pos += rdlen
    return ips


def resolve(server, name="example.com", timeout=2.0):
    """(ms, [ip]) truy vấn A trực tiếp tới 1 DNS server; (None, []) nếu không trả lời."""
    qid = random.randint(0, 0xFFFF)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        start = time.perf_counter()
        try:
            s.sendto(build_query(name, qid), (server, 53))
            while True:
                data, _ = s.recvfrom(1500)
                try:
                    ips = parse_a_records(data, qid)
                    break
                except ValueError as e:
                    if "sai ID" not in str(e):
                        return None, []
        except OSError:
            return None, []
    return (time.perf_counter() - start) * 1000, ips


def latency(server, tries=3):
    """Độ trễ trung vị (ms) với các tên miền khác nhau để tránh cache; None nếu không phản hồi."""
    names = ["example.com", "wikipedia.org", "github.com", "yahoo.co.jp", "cloudflare.com"]
    results = [ms for ms, _ in (resolve(server, names[i % len(names)]) for i in range(tries))
               if ms is not None]
    return statistics.median(results) if results else None


# ---------------------------------------------------------------- đổi DNS (Windows)

def set_dns(alias, servers):
    """servers rỗng = về DHCP. Trả (rc, output)."""
    a = ps_quote(alias)
    if not servers:
        script = f"Set-DnsClientServerAddress -InterfaceAlias {a} -ResetServerAddresses"
    else:
        addrs = ",".join(ps_quote(s) for s in servers)
        script = f"Set-DnsClientServerAddress -InterfaceAlias {a} -ServerAddresses ({addrs})"
    rc, out = powershell(script)
    if rc == 0:
        run(["ipconfig", "/flushdns"])
    return rc, out


def _doh_root(alias):
    return (f"$g=(Get-NetAdapter -Name {ps_quote(alias)}).InterfaceGuid;"
            "$root=\"HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Dnscache\\InterfaceSpecificParameters\\$g\\DohInterfaceSettings\\Doh\";")


def doh_enable(alias, servers):
    """Bật DNS mã hóa (chỉ mã hóa, không rơi về UDP) cho các server hỗ trợ."""
    lines = [_doh_root(alias),
             "if(Test-Path $root){Remove-Item $root -Recurse -Force};"]
    for s in servers:
        tpl = DOH_TEMPLATES[s]
        q, t = ps_quote(s), ps_quote(tpl)
        lines.append(
            f"if(Get-DnsClientDohServerAddress -ServerAddress {q} -ErrorAction SilentlyContinue)"
            f"{{Set-DnsClientDohServerAddress -ServerAddress {q} -DohTemplate {t} -AllowFallbackToUdp $false -AutoUpgrade $true}}"
            f"else{{Add-DnsClientDohServerAddress -ServerAddress {q} -DohTemplate {t} -AllowFallbackToUdp $false -AutoUpgrade $true}};"
            f"$p=Join-Path $root {q};New-Item -Path $p -Force|Out-Null;"
            "New-ItemProperty -Path $p -Name DohFlags -Value 1 -PropertyType QWord -Force|Out-Null;")
    lines.append("Clear-DnsClientCache")
    return powershell("".join(lines))


def doh_disable(alias):
    return powershell(_doh_root(alias) + "if(Test-Path $root){Remove-Item $root -Recurse -Force};"
                      "Clear-DnsClientCache")


def doh_status(alias):
    """Danh sách IP đang bật DoH trên card này."""
    if not IS_WINDOWS or not alias:
        return []
    rc, out = powershell(_doh_root(alias) +
                         "if(Test-Path $root){(Get-ChildItem $root).PSChildName -join ','}")
    return [x for x in out.split(",") if x.strip()] if rc == 0 else []
