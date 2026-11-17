"""VPN: hồ sơ WireGuard/OpenVPN, VPN Gate miễn phí, Cloudflare WARP, kiểm tra rò rỉ."""
import os
import threading
import time
import webbrowser
from tkinter import filedialog

import customtkinter as ctk

from nettools.core import netinfo, vpn
from nettools.core.system import IS_WINDOWS, open_path, powershell
from nettools.ui import theme as T
from nettools.ui.app import Page
from nettools.ui.widgets import Card, InfoRow, LogBox, Table, button, header, notice

ALL = "Tất cả quốc gia"
KIND_LABEL = {"wireguard": "WireGuard", "openvpn": "OpenVPN", "warp": "Cloudflare WARP"}


class AuthDialog(ctk.CTkToplevel):
    """Hỏi tên đăng nhập/mật khẩu cho hồ sơ OpenVPN cần xác thực (không lưu lại)."""

    def __init__(self, parent, name):
        super().__init__(parent)
        self.title("Đăng nhập VPN")
        self.geometry("360x230")
        self.resizable(False, False)
        self.result = None
        ctk.CTkLabel(self, text=f"Hồ sơ '{name}' cần tài khoản VPN", font=T.font(13, "bold")).pack(pady=(16, 8))
        self.user = ctk.CTkEntry(self, placeholder_text="Tên đăng nhập", width=280)
        self.user.pack(pady=4)
        self.pw = ctk.CTkEntry(self, placeholder_text="Mật khẩu", show="•", width=280)
        self.pw.pack(pady=4)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=12)
        button(row, "Kết nối", self._ok, width=120).pack(side="left", padx=4)
        button(row, "Hủy", self.destroy, "neutral", width=90).pack(side="left", padx=4)
        self.bind("<Return>", lambda e: self._ok())
        self.after(100, lambda: (self.grab_set(), self.user.focus()))

    def _ok(self):
        if self.user.get().strip():
            self.result = (self.user.get().strip(), self.pw.get())
        self.destroy()


class VpnPage(Page):
    def __init__(self, app):
        super().__init__(app)
        header(self, "VPN", "Kết nối VPN từ file cấu hình của bạn, máy chủ miễn phí VPN Gate hoặc Cloudflare WARP. "
                            "Chỉ 1 VPN chạy tại một thời điểm.")
        self.active = None     # {"kind", "name", "session"?}
        self.servers = []

        st = Card(self, "Trạng thái")
        st.pack(fill="x", padx=24, pady=6)
        row = ctk.CTkFrame(st.body, fg_color="transparent")
        row.pack(fill="x")
        self.state = ctk.CTkLabel(row, text="● Chưa kết nối VPN", font=T.font(18, "bold"), anchor="w")
        self.state.pack(side="left", fill="x", expand=True)
        self.disc_btn = button(row, "■  Ngắt VPN", self.disconnect, "danger", width=120)
        self.disc_btn.pack(side="right")
        self.leak_btn = self.lock(button(row, "⌕  Kiểm tra IP & rò rỉ DNS", self.leak_check, "neutral", width=200))
        self.leak_btn.pack(side="right", padx=8)
        grid = ctk.CTkFrame(st.body, fg_color="transparent")
        grid.pack(fill="x", pady=(8, 0))
        grid.grid_columnconfigure((0, 1), weight=1, uniform="v")
        self.rows = {}
        for i, (k, lbl) in enumerate([("ip", "IP công khai"), ("country", "Quốc gia"), ("isp", "Nhà mạng"),
                                      ("resolver", "DNS thực sự đi ra"), ("verdict", "Đánh giá")]):
            r = InfoRow(grid, lbl)
            r.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 12) if i % 2 == 0 else (12, 0), pady=2)
            self.rows[k] = r

        self.tabs = ctk.CTkTabview(self, height=420, fg_color=T.CARD, segmented_button_selected_color=T.ACCENT,
                                   border_width=1, border_color=T.BORDER, corner_radius=12)
        self.tabs.pack(fill="x", padx=24, pady=6)
        self._build_profiles(self.tabs.add("Hồ sơ của tôi"))
        self._build_vpngate(self.tabs.add("VPN Gate (miễn phí)"))
        self._build_warp(self.tabs.add("Cloudflare WARP"))

        lc = Card(self, "Nhật ký kết nối VPN")
        lc.pack(fill="x", padx=24, pady=(6, 20))
        self.out = LogBox(lc.body, height=140)
        self.out.pack(fill="x")
        self._refresh_state()
        self.after(800, self.detect)

    # ---------------------------------------------------------------- dựng tab
    def _tool_row(self, parent, key):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        installed = bool(vpn.find_tool(key))
        ctk.CTkLabel(row, text=f"{vpn.TOOLS[key]['name']}: " + ("✔ đã cài" if installed else "✖ chưa cài"),
                     font=T.font(12), text_color=T.GOOD if installed else T.OK).pack(side="left")
        if not installed:
            ctk.CTkButton(row, text="Tải về (trang chính chủ)", width=150, height=26, font=T.font(12),
                          fg_color="transparent", text_color=T.ACCENT, hover_color=T.NAV_HOVER,
                          command=lambda: webbrowser.open(vpn.TOOLS[key]["url"])).pack(side="left", padx=6)
        return row

    def _build_profiles(self, tab):
        tools = ctk.CTkFrame(tab, fg_color="transparent")
        tools.pack(fill="x", padx=6, pady=(4, 6))
        self._tool_row(tools, "wireguard").pack(side="left")
        self._tool_row(tools, "openvpn").pack(side="left", padx=20)
        brow = ctk.CTkFrame(tab, fg_color="transparent")
        brow.pack(fill="x", padx=6, pady=(0, 6))
        self.lock(button(brow, "＋  Nhập file (.conf / .ovpn)", self.import_files, width=200)).pack(side="left")
        self.conn_btn = self.lock(button(brow, "▶  Kết nối", self.connect_selected, width=110))
        self.conn_btn.pack(side="left", padx=8)
        self.lock(button(brow, "✕  Xóa", self.delete_selected, "neutral", width=80)).pack(side="left")
        button(brow, "Thư mục hồ sơ", lambda: open_path(vpn.profiles_dir()), "neutral",
               width=140).pack(side="right")
        self.ptable = Table(tab, [("name", "Tên hồ sơ", 260, "w"), ("kind", "Loại", 100, "center"),
                                  ("remote", "Máy chủ", 240, "w"), ("status", "Trạng thái", 120, "center")], height=8)
        self.ptable.pack(fill="both", expand=True, padx=6)
        self.ptable.on_double(self.connect_selected)
        ctk.CTkLabel(tab, text="Mẹo: Proton VPN miễn phí cho tải file WireGuard (.conf) tại account.protonvpn.com → "
                               "Downloads. Nhà cung cấp VPN trả phí thường đều có file .conf hoặc .ovpn.",
                     font=T.font(11), text_color=T.MUTED, anchor="w", justify="left", wraplength=780).pack(
            fill="x", padx=6, pady=(6, 0))
        self.load_profiles()

    def _build_vpngate(self, tab):
        notice(tab, "⚠ VPN Gate là dự án học thuật của Đại học Tsukuba (Nhật). Máy chủ do tình nguyện viên chạy nên "
                    "chủ máy chủ có thể thấy lưu lượng không mã hóa và VPN Gate lưu nhật ký kết nối. "
                    "Phù hợp để đổi vùng/thử nghiệm — KHÔNG dùng để đăng nhập ngân hàng hay tài khoản quan trọng.").pack(
            fill="x", padx=6, pady=(4, 6))
        brow = ctk.CTkFrame(tab, fg_color="transparent")
        brow.pack(fill="x", padx=6, pady=(0, 6))
        self.load_btn = self.lock(button(brow, "⟳  Tải danh sách máy chủ", self.load_vpngate, width=190))
        self.load_btn.pack(side="left")
        self.country = ctk.CTkOptionMenu(brow, values=[ALL], command=lambda _: self._fill_vpngate(), width=200)
        self.country.pack(side="left", padx=8)
        self.lock(button(brow, "▶  Kết nối máy chủ đã chọn", self.connect_vpngate, width=200)).pack(side="left")
        self._tool_row(brow, "openvpn").pack(side="right")
        self.gtable = Table(tab, [("country", "Quốc gia", 150, "w"), ("host", "Máy chủ", 140, "w"),
                                  ("ping", "Ping", 70, "center"), ("speed", "Tốc độ", 100, "center"),
                                  ("sessions", "Người dùng", 100, "center"), ("uptime", "Hoạt động", 95, "center"),
                                  ("proto", "Giao thức", 95, "center")], height=9)
        self.gtable.pack(fill="both", expand=True, padx=6)
        self.gtable.on_double(self.connect_vpngate)

    def _build_warp(self, tab):
        ctk.CTkLabel(tab, text="Cloudflare WARP miễn phí: mã hóa toàn bộ kết nối qua mạng Cloudflare, nhanh và ổn định. "
                               "Không chọn được quốc gia (IP vẫn ở gần bạn) — hợp để bảo mật Wi-Fi công cộng "
                               "và tránh nhà mạng theo dõi.", font=T.font(12), text_color=T.MUTED, anchor="w",
                     justify="left", wraplength=780).pack(fill="x", padx=6, pady=(6, 10))
        self._tool_row(tab, "warp").pack(anchor="w", padx=6)
        self.warp_state = ctk.CTkLabel(tab, text="Trạng thái: —", font=T.font(14, "bold"), anchor="w")
        self.warp_state.pack(fill="x", padx=6, pady=10)
        brow = ctk.CTkFrame(tab, fg_color="transparent")
        brow.pack(fill="x", padx=6)
        self.lock(button(brow, "▶  Bật WARP", self.connect_warp, width=130)).pack(side="left")
        self.lock(button(brow, "■  Tắt WARP", self.disconnect_warp, "neutral", width=130)).pack(side="left", padx=8)
        self.lock(button(brow, "⟳  Cập nhật trạng thái", self.refresh_warp, "neutral", width=170)).pack(side="left")

    # ---------------------------------------------------------------- trạng thái chung
    def log(self, text):
        self.out.write(text)

    def _set_active(self, active):
        self.active = active
        self._refresh_state()
        self.load_profiles()

    def _refresh_state(self):
        a = self.active
        if not a:
            text, color = "● Chưa kết nối VPN", T.MUTED
            self.app.vpn_text = "Chưa kết nối"
        elif a.get("state") == "connecting":
            text, color = f"● Đang kết nối {a['name']} ({KIND_LABEL[a['kind']]})...", T.OK
            self.app.vpn_text = f"Đang kết nối {a['name']}"
        else:
            text, color = f"● Đã kết nối: {a['name']} ({KIND_LABEL[a['kind']]})", T.GOOD
            self.app.vpn_text = f"Đã kết nối · {a['name']}"
        self.state.configure(text=text, text_color=color)
        self.disc_btn.configure(state="normal" if a else "disabled",
                                fg_color=T.DANGER if a else T.NEUTRAL_BTN)
        if self.app.tray:
            self.app.tray.set_status("vpn" if a and a.get("state") != "connecting" else None)

    def detect(self):
        """Phát hiện VPN đang chạy sẵn khi mở app (WireGuard service / WARP)."""
        if not IS_WINDOWS:
            return

        def work():
            rc, out = powershell("Get-Service -Name 'WireGuardTunnel$*' -ErrorAction SilentlyContinue | "
                                 "Where-Object {$_.Status -eq 'Running'} | ForEach-Object {$_.Name}")
            names = [n.split("$", 1)[1] for n in out.splitlines() if "$" in n] if rc == 0 else []
            warp_on = vpn.find_tool("warp") and vpn.warp_status() == "connected"
            if names:
                self.ui(self._set_active, {"kind": "wireguard", "name": names[0], "state": "connected"})
            elif warp_on:
                self.ui(self._set_active, {"kind": "warp", "name": "WARP", "state": "connected"})
        self.app.bg(work)

    # ---------------------------------------------------------------- hồ sơ
    def load_profiles(self):
        rows = []
        for p in vpn.list_profiles():
            st = ""
            if self.active and self.active.get("name") == p["name"]:
                st = "Đang kết nối..." if self.active.get("state") == "connecting" else "● Đã kết nối"
            rows.append({**p, "kind": KIND_LABEL[p["kind"]], "status": st, "_kind": p["kind"]})
        self.ptable.set_rows(rows, ["good" if r["status"].startswith("●") else "" for r in rows])

    def import_files(self):
        files = filedialog.askopenfilenames(parent=self, title="Chọn file cấu hình VPN",
                                            filetypes=[("Cấu hình VPN", "*.conf *.ovpn"), ("Tất cả", "*.*")])
        for f in files:
            try:
                dst = vpn.import_profile(f)
                self.log(f"✔ Đã nhập hồ sơ {os.path.basename(dst)}")
            except (ValueError, OSError) as e:
                self.log(f"✖ {os.path.basename(f)}: {e}")
        self.load_profiles()

    def delete_selected(self):
        p = self.ptable.selected()
        if not p:
            self.log("Hãy chọn 1 hồ sơ trong bảng.")
            return
        if self.active and self.active.get("name") == p["name"]:
            self.log("Hãy ngắt kết nối trước khi xóa hồ sơ này.")
            return
        if self.app.confirm("Xóa hồ sơ", f"Xóa hồ sơ '{p['name']}'?"):
            vpn.delete_profile(p["path"])
            self.load_profiles()

    def connect_selected(self):
        p = self.ptable.selected()
        if not p:
            self.log("Hãy chọn 1 hồ sơ trong bảng (hoặc nhấp đúp vào hồ sơ).")
            return
        self.connect_profile(p["_kind"], p["name"], p["path"])

    def connect_profile(self, kind, name, path):
        if not vpn.find_tool(kind):
            self.log(f"✖ Chưa cài {vpn.TOOLS[kind]['name']}. Bấm 'Tải về' để cài từ trang chính chủ, rồi mở lại Net Tools.")
            return
        auth = None
        if kind == "openvpn" and vpn.needs_auth(path):
            dlg = AuthDialog(self, name)
            self.wait_window(dlg)
            if not dlg.result:
                return
            auth = dlg.result
        self.job(self._connect, kind, name, path, auth)

    def _connect(self, kind, name, path, auth):
        self._disconnect_sync()
        self.ui(self._set_active, {"kind": kind, "name": name, "state": "connecting"})
        self.ui(self.log, f"Đang kết nối {name} ({KIND_LABEL[kind]})...")
        if kind == "wireguard":
            rc, out = vpn.wg_connect(path)
            time.sleep(2)
            if rc == 0 and vpn.wg_is_up(name):
                self._connected(name)
            else:
                self.ui(self.log, f"✖ WireGuard lỗi: {out or 'tunnel không chạy'}")
                self.ui(self._set_active, None)
            return
        done = threading.Event()

        def on_state(state):
            if state == "connected":
                done.set()
                threading.Thread(target=self._connected, args=(name,), daemon=True).start()
            elif state == "stopped":
                done.set()
                self.ui(self._ovpn_stopped, name)

        session = vpn.OpenVPNSession(path, lambda line: self.ui(self.log, line[-160:]), on_state, auth)
        self.active_session = session
        session.start()
        self.ui(lambda: self.active and self.active.update(session=session))
        if not done.wait(45):
            self.ui(self.log, "✖ Quá 45 giây chưa kết nối được — máy chủ có thể đã tắt. Thử máy chủ khác.")
            session.stop()

    def _connected(self, name):
        self.ui(lambda: self._set_active({**(self.active or {}), "name": name, "state": "connected"}))
        self.ui(self.log, f"✔ Đã kết nối VPN {name}. Đang kiểm tra IP mới...")
        self.app.ui(self.app.log, f"VPN đã kết nối: {name}")
        self.app.notify("VPN đã kết nối", name)
        time.sleep(2)
        self._leak()

    def _ovpn_stopped(self, name):
        if self.active and self.active.get("kind") == "openvpn" and self.active.get("name") == name:
            self._set_active(None)
            self.log(f"Phiên OpenVPN {name} đã dừng.")

    def disconnect(self):
        if not self.active:
            return
        self.app.bg(lambda: (self._disconnect_sync(), self.ui(self.leak_check)))

    def _disconnect_sync(self):
        a = self.active
        if not a:
            return
        self.ui(self.log, f"Đang ngắt {a['name']}...")
        if a["kind"] == "wireguard":
            vpn.wg_disconnect(a["name"])
        elif a["kind"] == "openvpn":
            session = a.get("session") or getattr(self, "active_session", None)
            if session:
                session.stop()
        elif a["kind"] == "warp":
            vpn.warp_disconnect()
        self.ui(self._set_active, None)
        self.ui(self.log, "Đã ngắt VPN.")
        self.app.ui(self.app.log, f"VPN đã ngắt: {a['name']}")

    def shutdown(self):
        """Khi thoát app: dừng OpenVPN (tiến trình con). WireGuard/WARP chạy độc lập nên giữ nguyên."""
        if self.active and self.active["kind"] == "openvpn" and self.active.get("session"):
            self.active["session"].stop()

    # ---------------------------------------------------------------- VPN Gate
    def load_vpngate(self):
        self.job(self._load_vpngate)

    def _load_vpngate(self):
        self.ui(self.log, "Đang tải danh sách máy chủ VPN Gate...")
        try:
            servers = vpn.fetch_vpngate()
        except Exception as e:  # noqa: BLE001
            self.ui(self.log, f"✖ Không tải được danh sách VPN Gate: {e}")
            return
        self.servers = servers
        self.ui(self._after_vpngate)

    def _after_vpngate(self):
        countries = sorted({s["country"] for s in self.servers if s["country"]})
        self.country.configure(values=[ALL] + countries)
        self._fill_vpngate()
        self.log(f"✔ Có {len(self.servers)} máy chủ ở {len(countries)} quốc gia.")

    def _fill_vpngate(self):
        c = self.country.get()
        shown = [s for s in self.servers if c == ALL or s["country"] == c][:200]
        self._shown = shown
        self.gtable.set_rows([{"country": s["country"], "host": s["host"], "ping": f"{s['ping']} ms" if s["ping"] else "—",
                               "speed": f"{s['speed']:.0f} Mbps", "sessions": s["sessions"],
                               "uptime": f"{s['uptime_days']:.0f} ngày", "proto": s["proto"].upper(), "_s": s}
                              for s in shown])

    def connect_vpngate(self):
        row = self.gtable.selected()
        if not row:
            self.log("Hãy tải danh sách và chọn 1 máy chủ (nhấp đúp để kết nối nhanh).")
            return
        if not vpn.find_tool("openvpn"):
            self.log("✖ VPN Gate cần OpenVPN. Bấm 'Tải về' để cài OpenVPN Community, rồi mở lại Net Tools.")
            return
        path = vpn.save_vpngate_profile(row["_s"])
        name = os.path.splitext(os.path.basename(path))[0]
        self.load_profiles()
        self.connect_profile("openvpn", name, path)

    # ---------------------------------------------------------------- WARP
    def refresh_warp(self):
        def work():
            st = vpn.warp_status()
            self.ui(self.warp_state.configure, text="Trạng thái: " + {
                "connected": "● Đang bật", "connecting": "Đang kết nối...", "disconnected": "Đã tắt",
                "unregistered": "Chưa đăng ký (bấm Bật WARP để tự đăng ký)", "missing": "Chưa cài WARP",
            }.get(st, "Không rõ"))
        self.app.bg(work)

    def connect_warp(self):
        if not vpn.find_tool("warp"):
            self.log("✖ Chưa cài Cloudflare WARP. Bấm 'Tải về' để cài.")
            return
        self.job(self._connect_warp)

    def _connect_warp(self):
        self._disconnect_sync()
        self.ui(self._set_active, {"kind": "warp", "name": "WARP", "state": "connecting"})
        rc, out = vpn.warp_connect()
        self.ui(self.log, out or ("Đã gửi lệnh bật WARP." if rc == 0 else "Lỗi bật WARP"))
        for _ in range(15):
            time.sleep(1)
            if vpn.warp_status() == "connected":
                self._connected("WARP")
                self.ui(self.refresh_warp)
                return
        self.ui(self.log, "✖ WARP chưa kết nối được sau 15 giây.")
        self.ui(self._set_active, None)
        self.ui(self.refresh_warp)

    def disconnect_warp(self):
        def work():
            vpn.warp_disconnect()
            if self.active and self.active["kind"] == "warp":
                self.ui(self._set_active, None)
            self.ui(self.refresh_warp)
        self.app.bg(work)

    def on_show(self):
        if vpn.find_tool("warp"):
            self.refresh_warp()

    # ---------------------------------------------------------------- kiểm tra rò rỉ
    def leak_check(self):
        self.job(self._leak)

    def _leak(self):
        for k in self.rows:
            self.ui(self.rows[k].set, "…")
        info = netinfo.public_info()
        resolver = vpn.dns_resolver_ip()
        rinfo = netinfo.lookup_ip(resolver) if resolver else {}
        self.ui(self._show_leak, info, resolver, rinfo)

    def _show_leak(self, info, resolver, rinfo):
        if "error" in info:
            self.rows["ip"].set("Không có internet", T.BAD)
            return
        self.rows["ip"].set(info["ip"])
        self.rows["country"].set(f"{info['country']} ({info['cc']})")
        self.rows["isp"].set(info["isp"])
        self.rows["resolver"].set(f"{resolver} · {rinfo.get('isp', '?')} ({rinfo.get('cc', '?')})" if resolver else "Không xác định")
        if not self.active:
            self.rows["verdict"].set("Không dùng VPN — đây là IP thật của bạn")
        elif rinfo.get("cc") and info.get("cc") and rinfo["cc"] != info["cc"]:
            self.rows["verdict"].set("⚠ Có thể rò rỉ DNS (DNS ở quốc gia khác VPN)", T.OK)
        else:
            self.rows["verdict"].set("✔ VPN hoạt động, không thấy rò rỉ DNS", T.GOOD)
        self.log(f"IP hiện tại: {info['ip']} — {info['country']} — {info['isp']}")
