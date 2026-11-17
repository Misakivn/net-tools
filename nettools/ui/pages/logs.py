"""Nhật ký hoạt động của app."""
import customtkinter as ctk

from nettools.core.system import data_dir, open_path
from nettools.ui.app import Page
from nettools.ui.widgets import Card, LogBox, button, header


class LogsPage(Page):
    def __init__(self, app):
        super().__init__(app)
        header(self, "Nhật ký", "Mọi thao tác và lỗi của Net Tools. Gửi nội dung này khi cần hỗ trợ sửa lỗi.")
        c = Card(self)
        c.pack(fill="both", expand=True, padx=24, pady=(6, 20))
        row = ctk.CTkFrame(c.body, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        button(row, "Sao chép", self.copy, "neutral", width=120).pack(side="left")
        button(row, "✕  Xóa màn hình", self.box_clear, "neutral", width=130).pack(side="left", padx=8)
        button(row, "Mở thư mục dữ liệu", lambda: open_path(data_dir()), "neutral", width=170).pack(side="right")
        self.box = LogBox(c.body, height=520)
        self.box.pack(fill="both", expand=True)
        for line in self.app.log_lines:
            self.box.write(line, stamp=False)

    def append(self, line):
        self.box.write(line, stamp=False)

    def box_clear(self):
        self.box.clear()

    def copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.box.text())
        self.app.log("Đã sao chép nhật ký.")
