"""Cửa sổ chính: thanh điều hướng bên trái, trang nội dung bên phải, thanh trạng thái."""
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from nettools import APP_NAME, __version__
from nettools.core import netinfo, speed
from nettools.core.monitor import Monitor
from nettools.core.settings import Settings
from nettools.core.system import IS_WINDOWS, data_dir, is_admin, resource_path, wait_show_requests
from nettools.ui import theme as T
from nettools.ui.widgets import style_tables

# nhóm -> [(khóa trang, nhãn, biểu tượng)]
NAV = [
    ("TỔNG QUAN", [("dashboard", "Bảng điều khiển", "◉")]),
    ("HIỆU NĂNG", [("speed", "Đo tốc độ", "⚡"), ("monitor", "Giám sát kết nối", "≋")]),
    ("KẾT NỐI", [("dns", "DNS", "⌖"), ("vpn", "VPN", "⛨")]),
    ("CÔNG CỤ", [("diag", "Chẩn đoán", "⌕"), ("fix", "Sửa lỗi mạng", "⚒"),
                 ("block", "Chặn tên miền", "⛔")]),
    ("HỆ THỐNG", [("logs", "Nhật ký", "☰"), ("settings", "Cài đặt", "⚙")]),
]


def page_factory(key):
    from nettools.ui.pages import (block, dashboard, diag, dns, fix, logs, monitor, settings,
                                   speed as speed_page, vpn)
    return {"dashboard": dashboard.DashboardPage, "speed": speed_page.SpeedPage,
            "monitor": monitor.MonitorPage, "dns": dns.DnsPage, "vpn": vpn.VpnPage,
            "diag": diag.DiagPage, "fix": fix.FixPage, "block": block.BlockPage,
            "logs": logs.LogsPage, "settings": settings.SettingsPage}[key]


class Page(ctk.CTkScrollableFrame):
    """Trang nội dung. Mỗi trang có nhóm nút riêng bị khóa khi đang chạy tác vụ."""

    def __init__(self, app):
        super().__init__(app.content, fg_color=T.CONTENT, corner_radius=0)
        self.app = app
        self._buttons = []
        self.busy = False

    # tiện ích
    def ui(self, fn, *a, **kw):
        self.app.ui(fn, *a, **kw)

    def lock(self, *buttons):
        self._buttons.extend(buttons)
        return buttons[0] if len(buttons) == 1 else buttons

    def job(self, fn, *args, done=None):
        """Chạy fn ở luồng nền; khóa các nút của trang tới khi xong."""
        if self.busy:
            return
        self.busy = True
        for b in self._buttons:
            b.configure(state="disabled")

        def wrap():
            try:
                fn(*args)
            except Exception as e:  # noqa: BLE001 - mọi lỗi đều hiện cho người dùng
                self.app.ui(self.app.log, f"Lỗi: {e}", "error")
            finally:
                self.ui(self._finish, done)

        threading.Thread(target=wrap, daemon=True).start()

    def _finish(self, done):
        self.busy = False
        for b in self._buttons:
            try:
                b.configure(state="normal")
            except tk.TclError:
                pass
        if done:
            done()

    # sự kiện (trang con ghi đè khi cần)
    def on_show(self):
        pass

    def on_adapter(self, name):
        pass

    def on_theme(self):
        pass


class App(ctk.CTk):
    def __init__(self, start_hidden=False):
        self.settings = Settings()
        ctk.set_appearance_mode(self.settings["theme"])
        ctk.set_default_color_theme("blue")
        super().__init__(fg_color=T.CONTENT)
        self.title(f"{APP_NAME} {__version__}")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self._set_icon()

        self.q = queue.Queue()
        self.pages, self.nav_buttons = {}, {}
        self.current = None
        self.adapters, self.adapter = [], ""
        self.ipconf = {}
        self.vpn_text = "Chưa kết nối"
        self.log_lines = []
        self._log_path = os.path.join(data_dir(), "nettools.log")
        self._tray_hint_shown = False

        style_tables(self)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.content = ctk.CTkFrame(self, fg_color=T.CONTENT, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self._build_statusbar()

        self.monitor = Monitor(speed.ping_once, on_sample=self._on_sample, on_event=self._on_outage)
        self.monitor.host = self.settings["monitor_host"]
        self.monitor.interval = self.settings["monitor_interval"]
        self.sample_listeners = []

        self.tray = None
        try:
            from nettools.ui.tray import Tray
            self.tray = Tray(self)
        except Exception as e:  # noqa: BLE001 - app vẫn chạy được khi thiếu khay
            self.log(f"Không tạo được icon khay hệ thống: {e}", "warn")

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        wait_show_requests(lambda: self.ui(self.show_window))
        self.after(50, self._poll)
        self.show("dashboard")
        self.refresh_adapters()
        if self.settings["monitor_autostart"]:
            self.monitor.start()
        self.after(1500, lambda: self.page("vpn"))  # phát hiện VPN đang chạy sẵn
        if not is_admin() and IS_WINDOWS:
            self.log("App đang chạy KHÔNG có quyền Administrator: đổi DNS/VPN/sửa mạng sẽ thất bại.", "warn")
        if start_hidden and self.tray:
            self.withdraw()
        self.log(f"{APP_NAME} {__version__} đã khởi động.")

    # ---------------------------------------------------------------- dựng khung
    def _set_icon(self):
        ico = resource_path("assets", "icon.ico")
        try:
            if IS_WINDOWS and os.path.exists(ico):
                self.iconbitmap(ico)
            else:
                png = resource_path("assets", "icon.png")
                if os.path.exists(png):
                    self._icon_img = tk.PhotoImage(file=png)
                    self.iconphoto(True, self._icon_img)
        except tk.TclError:
            pass

    def _build_sidebar(self):
        bar = ctk.CTkFrame(self, width=230, fg_color=T.SIDEBAR, corner_radius=0)
        bar.grid(row=0, column=0, rowspan=2, sticky="ns")
        bar.grid_propagate(False)
        bar.pack_propagate(False)
        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(18, 10))
        from nettools.ui.icon import make_icon
        self._brand_img = ctk.CTkImage(make_icon(96), size=(36, 36))
        ctk.CTkLabel(brand, text="", image=self._brand_img).pack(side="left")
        txt = ctk.CTkFrame(brand, fg_color="transparent")
        txt.pack(side="left", padx=8)
        ctk.CTkLabel(txt, text=APP_NAME, font=T.font(18, "bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(txt, text=f"phiên bản {__version__}", font=T.font(11), text_color=T.MUTED,
                     anchor="w").pack(fill="x")

        bottom = ctk.CTkFrame(bar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=14, pady=14)
        ctk.CTkLabel(bottom, text="CARD MẠNG ĐANG DÙNG", font=T.font(10, "bold"), text_color=T.MUTED,
                     anchor="w").pack(fill="x", padx=4)
        row = ctk.CTkFrame(bottom, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        self.adapter_menu = ctk.CTkOptionMenu(row, values=["Đang tải..."], width=160, height=30,
                                              dynamic_resizing=False, command=self.set_adapter,
                                              font=T.font(12))
        self.adapter_menu.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="↻", width=32, height=30, fg_color=T.NEUTRAL_BTN, hover_color=T.NEUTRAL_HOVER,
                      text_color=T.TEXT, command=self.refresh_adapters).pack(side="left", padx=(6, 0))
        admin = "✔ Quyền Administrator" if is_admin() else "⚠ Chưa có quyền Admin"
        ctk.CTkLabel(bottom, text=admin, font=T.font(11),
                     text_color=T.GOOD if is_admin() else T.OK, anchor="w").pack(fill="x", padx=4, pady=(8, 0))

        for group, items in NAV:
            ctk.CTkLabel(bar, text=group, font=T.font(10, "bold"), text_color=T.MUTED,
                         anchor="w").pack(fill="x", padx=22, pady=(10, 2))
            for key, label, icon in items:
                b = ctk.CTkButton(bar, text=f"{icon}   {label}", anchor="w", height=34, corner_radius=8,
                                  fg_color="transparent", hover_color=T.NAV_HOVER, text_color=T.TEXT,
                                  font=T.font(13), command=lambda k=key: self.show(k))
                b.pack(fill="x", padx=10, pady=1)
                self.nav_buttons[key] = b

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=28, fg_color=T.SIDEBAR, corner_radius=0)
        bar.grid(row=1, column=1, sticky="ew")
        self.status = ctk.CTkLabel(bar, text="Sẵn sàng.", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.status.pack(side="left", fill="x", expand=True, padx=14)
        self.status_right = ctk.CTkLabel(bar, text="", font=T.font(12), text_color=T.MUTED)
        self.status_right.pack(side="right", padx=14)

    # ---------------------------------------------------------------- luồng
    def ui(self, fn, *args, **kwargs):
        """Gọi từ luồng nền: đẩy việc cập nhật giao diện về luồng chính."""
        self.q.put((fn, args, kwargs))

    def _poll(self):
        try:
            for _ in range(200):
                fn, args, kwargs = self.q.get_nowait()
                try:
                    fn(*args, **kwargs)
                except Exception as e:  # noqa: BLE001
                    self._write_log(f"Lỗi giao diện: {e}", "error")
        except queue.Empty:
            pass
        self.after(40, self._poll)

    def report_callback_exception(self, exc, val, tb):
        """Lỗi trong giao diện: ghi vào Nhật ký thay vì im lặng."""
        import traceback
        self._write_log("Lỗi giao diện:\n" + "".join(traceback.format_exception(exc, val, tb)), "error")
        self.status.configure(text=f"Lỗi: {val}", text_color=T.BAD)

    def bg(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    # ---------------------------------------------------------------- điều hướng
    def show(self, key):
        if key not in self.pages:
            self.pages[key] = page_factory(key)(self)
        if self.current:
            self.pages[self.current].pack_forget()
            self.nav_buttons[self.current].configure(fg_color="transparent", font=T.font(13))
        self.current = key
        self.pages[key].pack(fill="both", expand=True)
        self.nav_buttons[key].configure(fg_color=T.NAV_ACTIVE, font=T.font(13, "bold"))
        self.pages[key].on_show()
        return self.pages[key]

    def page(self, key):
        """Trang theo khóa (tạo nếu chưa có, không chuyển tới)."""
        if key not in self.pages:
            self.pages[key] = page_factory(key)(self)
        return self.pages[key]

    # ---------------------------------------------------------------- card mạng
    def refresh_adapters(self):
        def work():
            items = netinfo.list_adapters()
            self.ui(self._set_adapters, items)
        self.bg(work)

    def _set_adapters(self, items):
        self.adapters = items
        names = [a["name"] for a in items]
        self.adapter_menu.configure(values=names or ["(không có card nào)"])
        chosen = netinfo.pick_default(names, self.settings["adapter"] or self.adapter)
        self.adapter_menu.set(chosen or "(không có card nào)")
        self.set_adapter(chosen, save=False)

    def set_adapter(self, name, save=True):
        if name.startswith("("):
            name = ""
        self.adapter = name
        if save and name:
            self.settings["adapter"] = name
        self.refresh_ipconf()
        for p in self.pages.values():
            p.on_adapter(name)

    def adapter_info(self):
        return next((a for a in self.adapters if a["name"] == self.adapter), {})

    def refresh_ipconf(self, then=None):
        name = self.adapter

        def work():
            conf = netinfo.ip_config(name)
            self.ui(self._set_ipconf, conf, then)
        self.bg(work)

    def _set_ipconf(self, conf, then):
        self.ipconf = conf
        self.monitor.gateway = conf.get("gateway", "")
        if then:
            then(conf)

    # ---------------------------------------------------------------- giám sát
    def _on_sample(self, t, gw, net):
        self.ui(self._dispatch_sample, t, gw, net)

    def _dispatch_sample(self, t, gw, net):
        txt = "Internet: mất kết nối" if net is None else f"Internet {net:.0f} ms"
        if gw is not None:
            txt += f"  ·  Router {gw:.0f} ms"
        self.status_right.configure(text=txt, text_color=T.BAD if net is None else T.MUTED)
        for fn in list(self.sample_listeners):
            fn(t, gw, net)

    def _on_outage(self, ev):
        if ev["type"] == "down":
            self.ui(self.log, "Mất kết nối internet!", "error")
            self.notify("Mất kết nối internet", "Net Tools đang theo dõi và sẽ báo khi có mạng lại.")
        else:
            msg = f"Có mạng lại sau {ev['seconds']} giây. Nguyên nhân: {ev['cause']}."
            self.ui(self.log, msg, "warn")
            self.notify("Đã có mạng lại", msg)
            if "monitor" in self.pages:
                self.ui(self.pages["monitor"].on_outage)
        if self.tray:
            self.tray.set_status("bad" if ev["type"] == "down" else None)

    def notify(self, title, msg):
        if self.tray and self.settings["notify"]:
            self.tray.notify(title, msg)

    # ---------------------------------------------------------------- log
    def log(self, text, level="info"):
        if threading.current_thread() is not threading.main_thread():
            self.ui(self.log, text, level)
            return
        self._write_log(text, level)
        self.status.configure(text=text.splitlines()[-1] if text else "",
                              text_color={"error": T.BAD, "warn": T.OK}.get(level, T.MUTED))
        if "logs" in self.pages:
            self.pages["logs"].append(self.log_lines[-1])

    def _write_log(self, text, level):
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {level.upper():5} {text}"
        self.log_lines.append(line)
        del self.log_lines[:-2000]
        try:
            if os.path.exists(self._log_path) and os.path.getsize(self._log_path) > 1_000_000:
                os.replace(self._log_path, self._log_path + ".old")
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    # ---------------------------------------------------------------- giao diện
    def set_theme(self, mode):
        self.settings["theme"] = mode
        ctk.set_appearance_mode(mode)
        self.after(100, self._apply_theme)

    def _apply_theme(self):
        style_tables(self)
        for p in self.pages.values():
            p.on_theme()

    def confirm(self, title, text):
        return messagebox.askyesno(title, text, parent=self)

    # ---------------------------------------------------------------- cửa sổ / khay
    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def on_close(self):
        if self.tray and self.settings["close_to_tray"]:
            self.withdraw()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.notify(APP_NAME, "Net Tools vẫn chạy ở khay hệ thống. Bấm chuột phải vào icon để mở hoặc thoát.")
        else:
            self.quit_app()

    def quit_app(self):
        self.monitor.stop()
        if "vpn" in self.pages:
            self.pages["vpn"].shutdown()
        if self.tray:
            self.tray.stop()
        self.destroy()
