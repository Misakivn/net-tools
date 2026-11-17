"""Cài đặt: giao diện, khởi động cùng Windows, khay hệ thống, giám sát."""
import webbrowser

import customtkinter as ctk

from nettools import APP_NAME, REPO_URL, __version__
from nettools.core import autostart
from nettools.core.system import IS_WINDOWS, data_dir, is_admin, open_path
from nettools.ui import theme as T
from nettools.ui.app import Page
from nettools.ui.widgets import Card, button, header

THEMES = {"Tối": "dark", "Sáng": "light", "Theo Windows": "system"}


class SettingsPage(Page):
    def __init__(self, app):
        super().__init__(app)
        s = app.settings
        header(self, "Cài đặt")

        c = Card(self, "Giao diện")
        c.pack(fill="x", padx=24, pady=6)
        theme = ctk.CTkSegmentedButton(c.body, values=list(THEMES),
                                       command=lambda v: self.app.set_theme(THEMES[v]))
        theme.set(next((k for k, v in THEMES.items() if v == s["theme"]), "Tối"))
        theme.pack(anchor="w")

        c = Card(self, "Khởi động & khay hệ thống")
        c.pack(fill="x", padx=24, pady=6)
        self.auto_var = ctk.BooleanVar(value=False)
        self.auto_sw = ctk.CTkSwitch(c.body, text="Khởi động cùng Windows (chạy ẩn ở khay, không hỏi UAC)",
                                     variable=self.auto_var, command=self._toggle_autostart, font=T.font(13))
        self.auto_sw.pack(anchor="w", pady=4)
        self._switch(c.body, "Bấm nút X thì thu nhỏ xuống khay thay vì thoát", "close_to_tray")
        self._switch(c.body, "Hiện thông báo khi rớt mạng / có mạng lại / VPN kết nối", "notify")
        self.auto_note = ctk.CTkLabel(c.body, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.auto_note.pack(fill="x")

        c = Card(self, "Giám sát kết nối")
        c.pack(fill="x", padx=24, pady=6)
        self._switch(c.body, "Tự bật giám sát khi mở app (cần cho thông báo rớt mạng)", "monitor_autostart")

        c = Card(self, "Dữ liệu")
        c.pack(fill="x", padx=24, pady=6)
        ctk.CTkLabel(c.body, text=f"Cài đặt, lịch sử đo, nhật ký và hồ sơ VPN lưu tại:\n{data_dir()}",
                     font=T.font(12), text_color=T.MUTED, anchor="w", justify="left").pack(fill="x")
        button(c.body, "Mở thư mục", lambda: open_path(data_dir()), "neutral", width=140).pack(anchor="w", pady=(8, 0))

        c = Card(self, "Giới thiệu")
        c.pack(fill="x", padx=24, pady=(6, 20))
        ctk.CTkLabel(c.body, text=f"{APP_NAME} {__version__} — gộp từ NetCheck và Đổi DNS.\n"
                                  f"Quyền Administrator: {'có' if is_admin() else 'không'}",
                     font=T.font(12), anchor="w", justify="left").pack(fill="x")
        button(c.body, "Mã nguồn trên GitHub", lambda: webbrowser.open(REPO_URL), "neutral",
               width=180).pack(anchor="w", pady=(8, 0))

        if IS_WINDOWS:
            self.app.bg(lambda: self.ui(self.auto_var.set, autostart.is_enabled()))
        else:
            self.auto_sw.configure(state="disabled")

    def _switch(self, parent, text, key):
        var = ctk.BooleanVar(value=bool(self.app.settings[key]))
        sw = ctk.CTkSwitch(parent, text=text, variable=var, font=T.font(13),
                           command=lambda: self.app.settings.__setitem__(key, var.get()))
        sw.pack(anchor="w", pady=4)
        return sw

    def _toggle_autostart(self):
        want = self.auto_var.get()

        def work():
            rc, out = autostart.enable() if want else autostart.disable()
            ok = rc == 0
            self.ui(self.auto_var.set, autostart.is_enabled())
            self.ui(self.auto_note.configure,
                    text=("✔ Đã bật khởi động cùng Windows." if want else "Đã tắt khởi động cùng Windows.") if ok
                    else f"✖ Lỗi: {out[:200]}")
            self.app.ui(self.app.log, f"Khởi động cùng Windows: {'bật' if want else 'tắt'} — {'OK' if ok else out[:120]}")
        self.app.bg(work)
