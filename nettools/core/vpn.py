"""VPN: hồ sơ WireGuard (.conf) / OpenVPN (.ovpn), máy chủ miễn phí VPN Gate, Cloudflare WARP.

Net Tools không tự cài driver VPN; nó điều khiển các phần mềm chính chủ đã cài trên máy:
- WireGuard: wireguard.exe /installtunnelservice <file>  (chạy như service, bền nhất)
- OpenVPN : openvpn.exe --config <file> --management ...  (dừng êm qua cổng quản lý)
- WARP    : warp-cli connect/disconnect
"""
import base64
import csv
import io
import os
import re
import shutil
import socket
import threading
import time

import requests

from nettools.core.system import data_dir, popen, run

PROGRAM_FILES = os.environ.get("ProgramFiles", r"C:\Program Files")
TOOLS = {
    "wireguard": {"name": "WireGuard", "url": "https://www.wireguard.com/install/",
                  "paths": [os.path.join(PROGRAM_FILES, "WireGuard", "wireguard.exe")],
                  "which": "wireguard"},
    "openvpn": {"name": "OpenVPN", "url": "https://openvpn.net/community-downloads/",
                "paths": [os.path.join(PROGRAM_FILES, "OpenVPN", "bin", "openvpn.exe")],
                "which": "openvpn"},
    "warp": {"name": "Cloudflare WARP", "url": "https://one.one.one.one/",
             "paths": [os.path.join(PROGRAM_FILES, "Cloudflare", "Cloudflare WARP", "warp-cli.exe")],
             "which": "warp-cli"},
}
VPNGATE_API = "https://www.vpngate.net/api/iphone/"


def find_tool(key):
    t = TOOLS[key]
    for p in t["paths"]:
        if os.path.exists(p):
            return p
    return shutil.which(t["which"])


def profiles_dir():
    return data_dir("vpn")


# ---------------------------------------------------------------- hồ sơ

def safe_name(name):
    """Tên tunnel WireGuard chỉ cho [A-Za-z0-9_=+.-], tối đa 32 ký tự."""
    base = re.sub(r"[^A-Za-z0-9_=+.\-]", "_", name).strip("._") or "vpn"
    return base[:32]


def profile_kind(path):
    ext = os.path.splitext(path)[1].lower()
    return {".conf": "wireguard", ".ovpn": "openvpn"}.get(ext, "")


def import_profile(src):
    """Chép file cấu hình vào thư mục app. Trả đường dẫn mới; ném ValueError nếu sai loại."""
    kind = profile_kind(src)
    if not kind:
        raise ValueError("Chỉ hỗ trợ file .conf (WireGuard) hoặc .ovpn (OpenVPN).")
    with open(src, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if kind == "wireguard" and "[Interface]" not in text:
        raise ValueError("File .conf này không phải cấu hình WireGuard (thiếu [Interface]).")
    if kind == "openvpn" and not re.search(r"^\s*remote\s+\S+", text, re.M):
        raise ValueError("File .ovpn thiếu dòng 'remote'.")
    stem = safe_name(os.path.splitext(os.path.basename(src))[0])
    dst = os.path.join(profiles_dir(), stem + os.path.splitext(src)[1].lower())
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return dst


def list_profiles():
    out = []
    for fn in sorted(os.listdir(profiles_dir())):
        path = os.path.join(profiles_dir(), fn)
        kind = profile_kind(fn)
        if kind:
            out.append({"name": os.path.splitext(fn)[0], "kind": kind, "path": path,
                        "remote": profile_remote(path)})
    return out


def profile_remote(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return ""
    m = (re.search(r"^\s*Endpoint\s*=\s*(\S+)", text, re.M | re.I)
         or re.search(r"^\s*remote\s+(\S+(?:\s+\d+)?)", text, re.M))
    return m.group(1) if m else ""


def needs_auth(path):
    """True nếu .ovpn cần nhập username/password (auth-user-pass không kèm file)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                if parts[:1] == ["auth-user-pass"]:
                    return len(parts) == 1
    except OSError:
        pass
    return False


def delete_profile(path):
    if os.path.dirname(os.path.abspath(path)) == os.path.abspath(profiles_dir()):
        os.remove(path)


# ---------------------------------------------------------------- WireGuard

def wg_connect(path):
    exe = find_tool("wireguard")
    if not exe:
        return 127, "Chưa cài WireGuard."
    return run([exe, "/installtunnelservice", path], timeout=30)


def wg_disconnect(name):
    exe = find_tool("wireguard")
    if not exe:
        return 127, "Chưa cài WireGuard."
    return run([exe, "/uninstalltunnelservice", name], timeout=30)


def wg_is_up(name):
    rc, out = run(["sc", "query", f"WireGuardTunnel${name}"], timeout=10)
    return rc == 0 and "RUNNING" in out.upper()


# ---------------------------------------------------------------- OpenVPN

OVPN_COMPAT = ("data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305:AES-128-CBC\n"
               "data-ciphers-fallback AES-128-CBC\n")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class OpenVPNSession:
    """1 phiên openvpn.exe. on_line(str) nhận log, on_state('connecting'|'connected'|'stopped')."""

    def __init__(self, path, on_line, on_state, auth=None):
        self.path, self.on_line, self.on_state = path, on_line, on_state
        self.auth = auth
        self.proc = None
        self.port = None
        self.state = "stopped"
        self._authfile = None

    def start(self):
        exe = find_tool("openvpn")
        if not exe:
            raise RuntimeError("Chưa cài OpenVPN.")
        self.port = free_port()
        cmd = [exe, "--config", self.path, "--management", "127.0.0.1", str(self.port),
               "--auth-nocache", "--connect-retry-max", "3", "--verb", "3"]
        if self.auth:
            self._authfile = os.path.join(data_dir(), f".auth{self.port}.tmp")
            with open(self._authfile, "w", encoding="utf-8") as f:
                f.write(f"{self.auth[0]}\n{self.auth[1]}\n")
            cmd += ["--auth-user-pass", self._authfile]
        self.proc = popen(cmd)
        self._set("connecting")
        threading.Thread(target=self._read, daemon=True).start()

    def _set(self, state):
        self.state = state
        self.on_state(state)

    def _read(self):
        for line in self.proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            self.on_line(line)
            if "Initialization Sequence Completed" in line:
                self._cleanup_auth()
                self._set("connected")
            elif "AUTH_FAILED" in line:
                self.on_line("Sai tài khoản hoặc mật khẩu VPN.")
        self.proc.wait()
        self._cleanup_auth()
        self._set("stopped")

    def _cleanup_auth(self):
        if self._authfile and os.path.exists(self._authfile):
            try:
                os.remove(self._authfile)
            except OSError:
                pass
        self._authfile = None

    def stop(self):
        if not self.proc or self.proc.poll() is not None:
            return
        try:  # yêu cầu openvpn tự thoát để gỡ route sạch sẽ
            with socket.create_connection(("127.0.0.1", self.port), timeout=3) as s:
                s.sendall(b"signal SIGTERM\r\n")
                time.sleep(0.3)
        except OSError:
            pass
        try:
            self.proc.wait(timeout=8)
        except Exception:  # noqa: BLE001
            self.proc.kill()


# ---------------------------------------------------------------- VPN Gate

def parse_vpngate(text):
    """Danh sách server từ CSV của VPN Gate (đã sắp theo điểm giảm dần)."""
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("*")]
    if lines and lines[0].startswith("#"):
        lines[0] = lines[0][1:]
    servers = []
    for r in csv.DictReader(io.StringIO("\n".join(lines))):
        b64 = (r.get("OpenVPN_ConfigData_Base64") or "").strip()
        if not b64 or not r.get("IP"):
            continue
        try:
            config = base64.b64decode(b64).decode("utf-8", "replace")
        except (ValueError, TypeError):
            continue
        num = lambda k: int(r.get(k) or 0) if str(r.get(k) or "0").isdigit() else 0  # noqa: E731
        proto = re.search(r"^\s*proto\s+(\w+)", config, re.M)
        servers.append({
            "host": r.get("HostName", ""), "ip": r["IP"], "score": num("Score"),
            "ping": num("Ping"), "speed": num("Speed") / 1e6, "country": r.get("CountryLong", ""),
            "cc": r.get("CountryShort", ""), "sessions": num("NumVpnSessions"),
            "uptime_days": num("Uptime") / 86_400_000, "proto": proto.group(1) if proto else "",
            "config": config,
        })
    servers.sort(key=lambda s: s["score"], reverse=True)
    return servers


def fetch_vpngate(timeout=25):
    r = requests.get(VPNGATE_API, timeout=timeout)
    r.raise_for_status()
    return parse_vpngate(r.text)


def clean_ovpn(config):
    """Bỏ dòng chú thích và thêm cấu hình tương thích OpenVPN 2.6 (server cũ dùng AES-128-CBC)."""
    lines = [ln for ln in config.splitlines() if ln.strip() and not ln.lstrip().startswith(("#", ";"))]
    text = "\n".join(lines) + "\n"
    if "data-ciphers" not in text:
        text = OVPN_COMPAT + text
    return text


def save_vpngate_profile(server):
    name = safe_name(f"vpngate_{server['cc']}_{server['host']}")
    path = os.path.join(profiles_dir(), name + ".ovpn")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(clean_ovpn(server["config"]))
    return path


# ---------------------------------------------------------------- Cloudflare WARP

def warp(*args):
    exe = find_tool("warp")
    if not exe:
        return 127, "Chưa cài Cloudflare WARP."
    return run([exe, "--accept-tos", *args], timeout=40)


def warp_status():
    """'connected' | 'connecting' | 'disconnected' | 'unregistered' | 'missing' | 'unknown'."""
    rc, out = warp("status")
    low = out.lower()
    if rc == 127:
        return "missing"
    if "registration missing" in low or "missing registration" in low:
        return "unregistered"
    if "disconnected" in low:
        return "disconnected"
    if "connecting" in low:
        return "connecting"
    if "connected" in low:
        return "connected"
    return "unknown"


def warp_connect():
    if warp_status() == "unregistered":
        rc, out = warp("registration", "new")
        if rc != 0:
            return rc, out
    return warp("connect")


def warp_disconnect():
    return warp("disconnect")


# ---------------------------------------------------------------- kiểm tra rò rỉ

def dns_resolver_ip():
    """IP của DNS resolver đang thật sự đi ra internet (Akamai trả về IP resolver đã hỏi)."""
    try:
        return socket.gethostbyname("whoami.akamai.net")
    except OSError:
        return ""
