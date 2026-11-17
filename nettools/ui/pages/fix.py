"""Sửa lỗi mạng 1 click."""
import customtkinter as ctk

from nettools.core import fix
from nettools.ui.app import Page
from nettools.ui.widgets import Card, LogBox, button, header

ORDER = ["flushdns", "renew", "restart", "arp", "proxy", "winsock", "ipreset"]


class FixPage(Page):
    def __init__(self, app):
        super().__init__(app)
        header(self, "Sửa lỗi mạng", "Thử từ trên xuống dưới: các thao tác phía dưới mạnh hơn nhưng cần khởi động lại máy.")
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=24, pady=6)
        grid.grid_columnconfigure((0, 1), weight=1, uniform="f")
        for i, key in enumerate(ORDER):
            title, desc, confirm, _ = fix.ACTIONS[key]
            heavy = key in ("winsock", "ipreset")
            c = Card(grid, f"{i + 1}. {title}", desc)
            c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, 6) if i % 2 == 0 else (6, 0), pady=6)
            self.lock(button(c.body, "Chạy", lambda k=key: self.run(k), "danger" if heavy else
                             ("neutral" if confirm else "primary"), width=110)).pack(anchor="w")
        lc = Card(self, "Kết quả")
        lc.pack(fill="x", padx=24, pady=(6, 20))
        self.out = LogBox(lc.body, height=200)
        self.out.pack(fill="x")

    def run(self, key):
        title, _, confirm, warning = fix.ACTIONS[key]
        if confirm and not self.app.confirm(title, f"{warning}\n\nTiếp tục?"):
            return
        self.job(self._run, key, self.app.adapter)

    def _run(self, key, alias):
        title = fix.ACTIONS[key][0]
        self.ui(self.out.write, f"▶ {title}" + (f" (card '{alias}')" if key in ("renew", "restart") else "") + "...")
        ok = True
        for cmd, rc, out in fix.run_action(key, alias):
            ok = ok and rc == 0
            self.ui(self.out.write, f"  > {cmd}  (mã {rc})")
            if out:
                self.ui(self.out.write, "    " + out.strip().replace("\n", "\n    ")[:1500], False)
        self.ui(self.out.write, f"{'✔' if ok else '✖'} {title}: {'xong' if ok else 'có lỗi (xem bên trên)'}.")
        self.app.ui(self.app.log, f"Sửa mạng: {title} — {'OK' if ok else 'lỗi'}", "info" if ok else "error")
        if key in ("winsock", "ipreset") and ok:
            self.ui(self.out.write, "⚠ Hãy KHỞI ĐỘNG LẠI máy để hoàn tất.")
        self.app.ui(self.app.refresh_ipconf)
