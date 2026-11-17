"""Chặn tên miền qua file hosts."""
import os
import shutil
import subprocess

import customtkinter as ctk

from nettools.core import hosts
from nettools.core.system import IS_WINDOWS, run
from nettools.ui import theme as T
from nettools.ui.app import Page
from nettools.ui.widgets import Card, button, header, notice


class BlockPage(Page):
    def __init__(self, app):
        super().__init__(app)
        header(self, "Chặn tên miền", "Chặn web/quảng cáo/theo dõi trên máy này bằng file hosts của Windows. "
                                      "Net Tools chỉ sửa phần của mình trong file và luôn giữ bản sao lưu.")
        notice(self, "Mẹo: muốn chặn quảng cáo diện rộng, dùng DNS AdGuard ở trang DNS — hiệu quả hơn tự liệt kê "
                     "tên miền. Trang này hợp để chặn vài trang cụ thể (web gây xao nhãng, tracker...).").pack(
            fill="x", padx=24, pady=6)

        c = Card(self, "Danh sách đang chặn", "Mỗi dòng một tên miền, ví dụ: ads.example.com")
        c.pack(fill="both", expand=True, padx=24, pady=6)
        self.box = ctk.CTkTextbox(c.body, height=280, font=T.mono(13), corner_radius=8, border_width=1,
                                  border_color=T.BORDER)
        self.box.pack(fill="both", expand=True)
        sug = ctk.CTkFrame(c.body, fg_color="transparent")
        sug.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(sug, text="Thêm nhanh:", font=T.font(12), text_color=T.MUTED).pack(side="left")
        for name, domains in hosts.SUGGESTIONS.items():
            button(sug, f"＋ {name}", lambda d=domains: self._add(d), "neutral", height=28,
                   font=T.font(12)).pack(side="left", padx=4)
        row = ctk.CTkFrame(c.body, fg_color="transparent")
        row.pack(fill="x", pady=(10, 0))
        self.lock(button(row, "✔  Lưu & áp dụng", self.save, width=150)).pack(side="left")
        button(row, "⟳  Tải lại", self.load, "neutral", width=100).pack(side="left", padx=8)
        button(row, "↩  Khôi phục bản sao lưu", self.restore, "neutral", width=190).pack(side="left")
        button(row, "Mở file hosts", self.open_hosts, "neutral", width=140).pack(side="right")
        self.status = ctk.CTkLabel(c.body, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.status.pack(fill="x", pady=(8, 0))
        self.load()

    def _add(self, domains):
        cur, _ = hosts.normalize(self.box.get("1.0", "end"))
        self._set(cur + [d for d in domains if d not in cur])

    def _set(self, domains):
        self.box.delete("1.0", "end")
        self.box.insert("1.0", "\n".join(domains))

    def load(self):
        domains = hosts.read_blocked()
        self._set(domains)
        self.status.configure(text=f"Đang chặn {len(domains)} tên miền.")

    def save(self):
        domains, bad = hosts.normalize(self.box.get("1.0", "end"))
        if bad:
            self.status.configure(text=f"Bỏ qua dòng không hợp lệ: {', '.join(bad[:5])}", text_color=T.OK)
        try:
            hosts.write_blocked(domains)
        except OSError as e:
            self.status.configure(text=f"✖ Không ghi được file hosts: {e} (cần quyền Admin; "
                                       "một số phần mềm diệt virus khóa file này).", text_color=T.BAD)
            return
        run(["ipconfig", "/flushdns"])
        self._set(domains)
        self.status.configure(text=f"✔ Đã áp dụng — đang chặn {len(domains)} tên miền. "
                                   "Trình duyệt có thể cần mở lại để nhận.", text_color=T.GOOD)
        self.app.log(f"Đã cập nhật danh sách chặn: {len(domains)} tên miền.")

    def restore(self):
        backup = hosts.HOSTS + ".nettools.bak"
        if not os.path.exists(backup):
            self.status.configure(text="Chưa có bản sao lưu (chỉ tạo khi bạn lưu lần đầu).", text_color=T.MUTED)
            return
        if self.app.confirm("Khôi phục hosts", "Khôi phục file hosts về bản trước khi Net Tools chỉnh sửa lần đầu?"):
            try:
                shutil.copy2(backup, hosts.HOSTS)
                run(["ipconfig", "/flushdns"])
                self.load()
                self.status.configure(text="✔ Đã khôi phục file hosts gốc.", text_color=T.GOOD)
            except OSError as e:
                self.status.configure(text=f"✖ {e}", text_color=T.BAD)

    def open_hosts(self):
        if IS_WINDOWS:
            subprocess.Popen(["notepad.exe", hosts.HOSTS])
