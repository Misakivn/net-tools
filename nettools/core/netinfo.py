"""Thông tin card mạng, IP nội bộ/công khai."""
import ipaddress

import requests

from nettools.core.system import IS_WINDOWS, ps_json, ps_quote

PREFERRED = ("ethernet", "イーサネット", "wi-fi", "wifi", "wlan")


def list_adapters():
    """Card mạng đang Up: list dict {name, desc, speed, mac, guid}."""
    if not IS_WINDOWS:
        return []
    rows = ps_json("Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | "
                   "Select-Object Name,InterfaceDescription,LinkSpeed,MacAddress,InterfaceGuid")
    return [{"name": r.get("Name", ""), "desc": r.get("InterfaceDescription", ""),
             "speed": r.get("LinkSpeed", ""), "mac": r.get("MacAddress", ""),
             "guid": r.get("InterfaceGuid", "")} for r in rows if r.get("Name")]


def pick_default(names, saved=""):
    """Chọn card mặc định: card đã lưu > Ethernet > Wi-Fi > card đầu tiên."""
    if saved in names:
        return saved
    for key in PREFERRED:
        for n in names:
            if n.lower() == key:
                return n
    for key in PREFERRED:
        for n in names:
            if n.lower().startswith(key):
                return n
    for key in PREFERRED:
        for n in names:
            if key in n.lower():
                return n
    return names[0] if names else ""


def ip_config(alias):
    """IP, gateway, DNS của 1 card; DNS 'dhcp' True nếu DNS do nhà mạng cấp."""
    empty = {"ipv4": "", "ipv6": "", "gateway": "", "dns": [], "dns_dhcp": True}
    if not IS_WINDOWS or not alias:
        return empty
    a = ps_quote(alias)
    rows = ps_json(
        f"$c=Get-NetIPConfiguration -InterfaceAlias {a} -ErrorAction Stop;"
        f"$g=(Get-NetAdapter -Name {a}).InterfaceGuid;"
        "$ns=(Get-ItemProperty \"HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces\\$g\" "
        "-ErrorAction SilentlyContinue).NameServer;"
        "[pscustomobject]@{"
        "ipv4=(@($c.IPv4Address.IPAddress) -join ',');"
        "ipv6=(@($c.IPv6Address.IPAddress) -join ',');"
        "gateway=(@($c.IPv4DefaultGateway.NextHop) -join ',');"
        f"dns=(@((Get-DnsClientServerAddress -InterfaceAlias {a} -AddressFamily IPv4).ServerAddresses) -join ',');"
        "static=[bool]$ns}")
    if not rows:
        return empty
    r = rows[0]
    split = lambda s: [x for x in (s or "").split(",") if x]  # noqa: E731
    return {"ipv4": (split(r.get("ipv4")) or [""])[0], "ipv6": (split(r.get("ipv6")) or [""])[0],
            "gateway": (split(r.get("gateway")) or [""])[0], "dns": split(r.get("dns")),
            "dns_dhcp": not r.get("static")}


def public_info(timeout=8):
    """IP công khai + nhà mạng + vị trí. Trả dict, có key 'error' nếu thất bại."""
    try:
        d = requests.get("https://ipwho.is/", timeout=timeout).json()
        if d.get("success", True):
            return {"ip": d.get("ip", ""), "isp": (d.get("connection") or {}).get("isp", ""),
                    "city": d.get("city", ""), "country": d.get("country", ""),
                    "cc": d.get("country_code", "")}
    except (requests.RequestException, ValueError):
        pass
    try:
        ip = requests.get("https://api.ipify.org", timeout=timeout).text.strip()
        ipaddress.ip_address(ip)
        return {"ip": ip, "isp": "", "city": "", "country": "", "cc": ""}
    except (requests.RequestException, ValueError) as e:
        return {"error": str(e)}


def lookup_ip(ip, timeout=8):
    try:
        d = requests.get(f"https://ipwho.is/{ip}", timeout=timeout).json()
        return {"isp": (d.get("connection") or {}).get("isp", ""), "country": d.get("country", ""),
                "cc": d.get("country_code", "")}
    except (requests.RequestException, ValueError):
        return {}


def public_ipv6(timeout=4):
    try:
        ip = requests.get("https://api6.ipify.org", timeout=timeout).text.strip()
        return ip if ipaddress.ip_address(ip).version == 6 else ""
    except (requests.RequestException, ValueError):
        return ""


def classify_ip(ip):
    """'private' | 'cgnat' | 'public' | 'loopback' | '' cho chuỗi IP."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    if addr.version == 4 and addr in ipaddress.ip_network("100.64.0.0/10"):
        return "cgnat"
    if addr.is_loopback:
        return "loopback"
    if addr.is_private or addr.is_link_local:
        return "private"
    return "public"
