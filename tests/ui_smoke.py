"""Chạy giao diện với dữ liệu giả (không cần Windows) và chụp màn hình từng trang.

python tests/ui_smoke.py <thư_mục_ảnh>   (cần màn hình X, vd: xvfb-run)
"""
import faulthandler
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nettools.core import dns, netinfo, speed, vpn  # noqa: E402

faulthandler.dump_traceback_later(90, exit=True)
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/shots"
os.makedirs(OUT, exist_ok=True)

# ---- dữ liệu giả
netinfo.list_adapters = lambda: [
    {"name": "Ethernet", "desc": "Realtek PCIe 2.5GbE Family Controller", "speed": "1 Gbps",
     "mac": "A8-A1-59-12-34-56", "guid": "{X}"},
    {"name": "Wi-Fi", "desc": "Intel Wi-Fi 6E AX211", "speed": "866.7 Mbps", "mac": "", "guid": "{Y}"}]
netinfo.ip_config = lambda a: {"ipv4": "192.168.10.23", "ipv6": "", "gateway": "192.168.10.1",
                               "dns": ["1.1.1.1", "1.0.0.1"], "dns_dhcp": False}
netinfo.public_info = lambda timeout=8: {"ip": "203.0.113.45", "isp": "NTT Communications", "city": "Tokyo",
                                         "country": "Japan", "cc": "JP"}
netinfo.public_ipv6 = lambda timeout=4: ""
dns.doh_status = lambda a: ["1.1.1.1", "1.0.0.1"]
speed.ping_once = lambda host, timeout_ms=1000: None if random.random() < 0.04 else random.uniform(8, 30)
vpn.find_tool = lambda k: "x" if k != "warp" else None
for i in range(12):
    speed.save_history({"time": f"2026-11-{10 + i // 3:02d} {8 + i:02d}:00", "ping": 10 + i, "jitter": 2, "loss": 0,
                        "down": random.uniform(60, 300), "up": random.uniform(20, 90), "isp": "NTT"})

from nettools.ui.app import App  # noqa: E402

app = App()
app.monitor.interval = 0.2
pages = ["dashboard", "speed", "monitor", "dns", "vpn", "diag", "fix", "block", "logs", "settings"]


def shot(name):
    app.update()
    time.sleep(0.4)
    app.update()
    subprocess.run(["import", "-window", "root", os.path.join(OUT, f"{name}.png")], check=False)


def tour():
    for _ in range(30):
        app.update()
        time.sleep(0.1)
    for p in pages:
        app.show(p)
        for _ in range(8):
            app.update()
            time.sleep(0.1)
        if p == "vpn":
            pg = app.pages["vpn"]
            pg.servers = [{"host": f"public-vpn-{i}", "ip": f"1.2.3.{i}", "score": 1000 - i, "ping": 5 + i,
                           "speed": 120 - i * 3, "country": c, "cc": c[:2].upper(), "sessions": i,
                           "uptime_days": 3 + i, "proto": "tcp", "config": "remote 1.2.3.4 443"}
                          for i, c in enumerate(["Japan", "Japan", "Korea Republic of", "United States", "Viet Nam"] * 3)]
            pg._after_vpngate()
            pg.tabs.set("VPN Gate (miễn phí)")
        shot(p)
    app.set_theme("light")
    for _ in range(10):
        app.update()
        time.sleep(0.1)
    app.show("dashboard")
    shot("dashboard_light")
    app.show("dns")
    shot("dns_light")
    app.quit_app()


app.after(500, tour)
app.mainloop()
print("errors:", [l for l in app.log_lines if "ERROR" in l])
