import base64
import struct

import pytest

from nettools.core import diag, dns, hosts, monitor, netinfo, speed, vpn


# ---------------------------------------------------------------- speed
PING_SAMPLE = (
    "Pinging 1.1.1.1 with 32 bytes of data:\n"
    "Reply from 1.1.1.1: bytes=32 time=10ms TTL=57\n"
    "Reply from 1.1.1.1: bytes=32 time=14ms TTL=57\n"
    "Request timed out.\n"
    "Reply from 1.1.1.1: bytes=32 time<1ms TTL=57\n"
    "    Packets: Sent = 4, Received = 3, Lost = 1 (25% loss),\n")


def test_parse_ping():
    ping, jitter, loss = speed.parse_ping(PING_SAMPLE, sent=4)
    assert round(ping, 2) == 8.33 and jitter == 8.5 and loss == 25.0
    assert speed.parse_ping("Request timed out.\n(100% loss)", sent=1) == (None, None, 100.0)
    unreachable = "Reply from 192.168.1.1: Destination host unreachable.\n(0% loss)"
    assert speed.parse_ping(unreachable, sent=1)[2] == 100.0


def test_parse_ping_japanese():
    jp = "1.1.1.1 からの応答: バイト数 =32 時間 =9ms TTL=57\n(0% の損失)"
    assert speed.parse_ping(jp, sent=1) == (9.0, 0.0, 0.0)


def test_verdict_quality_units():
    assert all(ok for ok, _, _ in speed.verdict(20, 2, 0, 100, 20))
    assert not any(ok for ok, _, _ in speed.verdict(None, None, 100, 0, 0))
    assert [ok for ok, _, _ in speed.verdict(80, 5, 0, 50, 10)] == [False, True, True]
    assert speed.quality("ping", 20) == "good" and speed.quality("ping", 300) == "bad"
    assert speed.quality("down", 60) == "good" and speed.quality("down", 5) == "bad"
    assert [speed.fmt_speed(100, u) for u in speed.UNITS] == ["100.0 Mbps", "12.50 MB/s", "100000 Kbps"]


def test_upload_body():
    seen = []
    body = speed.UploadBody(100_000, seen.append)
    assert len(body) == 100_000 and sum(len(c) for c in body) == 100_000 and seen[-1] == 100_000
    assert body.read(8192) == b""


def test_valid_host():
    assert speed.valid_host("1.1.1.1") and speed.valid_host("google.com")
    assert not speed.valid_host("-t 1.1.1.1") and not speed.valid_host("/?") and not speed.valid_host("a b")


def test_history_roundtrip(tmp_path):
    p = tmp_path / "h.csv"
    speed.save_history({"time": "t", "ping": 10, "down": 50.5, "up": ""}, path=str(p))
    rows = speed.load_history(path=str(p))
    assert rows[0]["ping"] == 10.0 and rows[0]["down"] == 50.5 and rows[0]["up"] is None


# ---------------------------------------------------------------- dns
def _answer(qid, ips):
    q = dns.build_query("example.com", qid)
    head = struct.pack(">HHHHHH", qid, 0x8180, 1, len(ips), 0, 0)
    body = q[12:]
    for ip in ips:
        body += b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 60, 4) + bytes(map(int, ip.split(".")))
    return head + body


def test_dns_parse():
    assert dns.parse_a_records(_answer(7, ["93.184.215.14", "1.2.3.4"]), 7) == ["93.184.215.14", "1.2.3.4"]
    with pytest.raises(ValueError):
        dns.parse_a_records(_answer(7, []), 8)
    assert dns.preset_of(["1.1.1.1", "1.0.0.1"]) == "Cloudflare"
    assert dns.preset_of(["129.250.35.250", "129.250.35.251"]) == "NTT (Nhật)"
    assert dns.preset_of([]) == "" and dns.preset_of(["10.0.0.1"]) == ""
    assert dns.doh_supported(["1.1.1.1", "1.0.0.1"]) and not dns.doh_supported(["129.250.35.250"])


# ---------------------------------------------------------------- netinfo / diag
def test_pick_and_classify():
    assert netinfo.pick_default(["Wi-Fi", "Ethernet 2", "Ethernet"]) == "Ethernet"
    assert netinfo.pick_default(["vEthernet (WSL)", "Wi-Fi"]) == "Wi-Fi"
    assert netinfo.pick_default(["Wi-Fi", "Ethernet"], saved="Wi-Fi") == "Wi-Fi"
    assert netinfo.classify_ip("100.70.1.1") == "cgnat"
    assert netinfo.classify_ip("192.168.0.1") == "private"
    assert netinfo.classify_ip("8.8.8.8") == "public"


def test_tracert_parse_and_nat():
    assert diag.parse_tracert_line("  1    <1 ms    <1 ms    <1 ms  192.168.1.1") == (1, [1, 1, 1], "192.168.1.1")
    assert diag.parse_tracert_line("  3     *        *        *     Request timed out.") == (3, [None] * 3, None)
    assert diag.parse_tracert_line("  2     5 ms     *        6 ms  10.0.0.1") == (2, [5, None, 6], "10.0.0.1")
    assert diag.parse_tracert_line("Tracing route to 1.1.1.1") is None
    hops = [(1, [], "192.168.1.1", "private"), (2, [], "10.0.0.1", "private"), (3, [], "8.8.8.8", "public")]
    assert diag.nat_summary(hops)[0] == "double"
    assert diag.nat_summary([(1, [], "192.168.1.1", "private"), (2, [], "100.64.0.1", "cgnat")])[0] == "cgnat"
    assert diag.normalize_url("example.com/a") == ("https://example.com/a", "example.com")


# ---------------------------------------------------------------- vpn
def test_vpngate_parse():
    cfg = "# comment\nclient\nproto tcp\nremote 1.2.3.4 443\ncipher AES-128-CBC\n"
    b64 = base64.b64encode(cfg.encode()).decode()
    csv_text = ("*vpn_servers\r\n#HostName,IP,Score,Ping,Speed,CountryLong,CountryShort,NumVpnSessions,"
                "Uptime,TotalUsers,TotalTraffic,LogType,Operator,Message,OpenVPN_ConfigData_Base64\r\n"
                f"public-vpn-1,1.2.3.4,100,12,50000000,Japan,JP,5,86400000,10,10,2weeks,op,,{b64}\r\n"
                f"public-vpn-2,5.6.7.8,900,30,10000000,Korea Republic of,KR,1,0,1,1,2weeks,op,,{b64}\r\n*\r\n")
    servers = vpn.parse_vpngate(csv_text)
    assert [s["host"] for s in servers] == ["public-vpn-2", "public-vpn-1"]
    jp = servers[1]
    assert jp["speed"] == 50 and jp["proto"] == "tcp" and jp["uptime_days"] == 1
    cleaned = vpn.clean_ovpn(jp["config"])
    assert "# comment" not in cleaned and cleaned.startswith("data-ciphers") and "remote 1.2.3.4 443" in cleaned


def test_vpn_profiles(tmp_path, monkeypatch):
    monkeypatch.setattr(vpn, "profiles_dir", lambda: str(tmp_path / "vpn"))
    (tmp_path / "vpn").mkdir()
    wg = tmp_path / "My Tokyo VPN!.conf"
    wg.write_text("[Interface]\nPrivateKey = x\n[Peer]\nEndpoint = jp.example.com:51820\n")
    dst = vpn.import_profile(str(wg))
    assert dst.endswith("My_Tokyo_VPN.conf")
    ov = tmp_path / "a.ovpn"
    ov.write_text("client\nremote vpn.example.com 1194\nauth-user-pass\n")
    vpn.import_profile(str(ov))
    profs = {p["name"]: p for p in vpn.list_profiles()}
    assert profs["My_Tokyo_VPN"]["remote"] == "jp.example.com:51820"
    assert vpn.needs_auth(profs["a"]["path"])
    bad = tmp_path / "x.conf"
    bad.write_text("hello")
    with pytest.raises(ValueError):
        vpn.import_profile(str(bad))


# ---------------------------------------------------------------- hosts
def test_hosts_block_roundtrip(tmp_path):
    p = tmp_path / "hosts"
    p.write_text("127.0.0.1 localhost\n")
    good, bad = hosts.normalize("https://ads.example.com/x, tracker.net\nnot_a_domain\n")
    assert good == ["ads.example.com", "tracker.net"] and bad == ["not_a_domain"]
    hosts.write_blocked(good, path=str(p))
    assert hosts.read_blocked(path=str(p)) == good
    assert "127.0.0.1 localhost" in p.read_text()
    hosts.write_blocked([], path=str(p))
    assert hosts.read_blocked(path=str(p)) == [] and hosts.BEGIN not in p.read_text()
    assert (tmp_path / "hosts.nettools.bak").exists()


# ---------------------------------------------------------------- monitor
def test_monitor_outage(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor.Monitor, "log_path", staticmethod(lambda: str(tmp_path / "o.csv")))
    events = []
    m = monitor.Monitor(lambda h: None, on_event=events.append)
    m.gateway, m.interval = "192.168.1.1", 3
    m.step(0, 1, 10)
    m.step(3, 1, None)          # mất 1 gói: chưa tính là rớt
    m.step(6, 1, 10)
    m.step(9, 1, None)
    m.step(12, None, None)      # rớt + router cũng mất
    m.step(15, 1, 12)
    assert [e["type"] for e in events] == ["down", "up"]
    assert events[1]["seconds"] == 6 and "router" in events[1]["cause"].lower()
    st = m.stats()
    assert st["loss"] == 50 and st["uptime"] == 50
    assert len(monitor.Monitor.load_outages()) == 1
