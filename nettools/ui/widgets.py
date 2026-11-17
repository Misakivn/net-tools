"""Thành phần giao diện dùng lại: thẻ, ô số liệu, biểu đồ, bảng, hộp log."""
import time
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from nettools.ui import theme as T


class Card(ctk.CTkFrame):
    def __init__(self, parent, title=None, subtitle=None, **kw):
        kw.setdefault("fg_color", T.CARD)
        super().__init__(parent, corner_radius=12, border_width=1, border_color=T.BORDER, **kw)
        if title:
            head = ctk.CTkFrame(self, fg_color="transparent")
            head.pack(fill="x", padx=16, pady=(12, 0))
            ctk.CTkLabel(head, text=title, font=T.font(14, "bold"), anchor="w").pack(side="left")
            self.head = head
            if subtitle:
                ctk.CTkLabel(self, text=subtitle, font=T.font(12), text_color=T.MUTED, anchor="w",
                             justify="left", wraplength=640).pack(fill="x", padx=16)
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=16, pady=(8, 14))


class Tile(ctk.CTkFrame):
    """Ô số liệu: nhãn nhỏ + giá trị lớn có màu theo chất lượng."""

    def __init__(self, parent, title, value="—", size=24):
        super().__init__(parent, fg_color=T.CARD, corner_radius=12, border_width=1, border_color=T.BORDER)
        ctk.CTkLabel(self, text=title.upper(), font=T.font(11, "bold"), text_color=T.MUTED).pack(pady=(12, 0))
        self.value = ctk.CTkLabel(self, text=value, font=T.font(size, "bold"))
        self.value.pack(pady=(0, 2))
        self.note = ctk.CTkLabel(self, text="", font=T.font(11), text_color=T.MUTED)
        self.note.pack(pady=(0, 10))

    def set(self, text, quality=None, note=None):
        self.value.configure(text=text, text_color=T.QUALITY.get(quality, T.TEXT))
        if note is not None:
            self.note.configure(text=note)


class InfoRow(ctk.CTkFrame):
    """Dòng 'Nhãn ........ Giá trị' trong thẻ thông tin."""

    def __init__(self, parent, label, value="—"):
        super().__init__(parent, fg_color="transparent")
        ctk.CTkLabel(self, text=label, font=T.font(12), text_color=T.MUTED, anchor="w").pack(side="left")
        self.value = ctk.CTkLabel(self, text=value, font=T.font(12, "bold"), anchor="e")
        self.value.pack(side="right")

    def set(self, text, color=None):
        self.value.configure(text=text or "—", text_color=color or T.TEXT)


def header(parent, title, subtitle=""):
    f = ctk.CTkFrame(parent, fg_color="transparent")
    f.pack(fill="x", padx=24, pady=(20, 8))
    ctk.CTkLabel(f, text=title, font=T.font(22, "bold"), anchor="w").pack(fill="x")
    if subtitle:
        ctk.CTkLabel(f, text=subtitle, font=T.font(13), text_color=T.MUTED, anchor="w",
                     justify="left", wraplength=760).pack(fill="x")
    return f


def button(parent, text, command, kind="primary", **kw):
    colors = {
        "primary": dict(fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER),
        "neutral": dict(fg_color=T.NEUTRAL_BTN, hover_color=T.NEUTRAL_HOVER, text_color=T.TEXT),
        "danger": dict(fg_color=T.DANGER, hover_color=T.DANGER_HOVER),
    }[kind]
    kw.setdefault("height", 34)
    kw.setdefault("corner_radius", 8)
    kw.setdefault("font", T.font(13, "bold" if kind == "primary" else "normal"))
    return ctk.CTkButton(parent, text=text, command=command, **colors, **kw)


def notice(parent, text, color=T.OK):
    f = ctk.CTkFrame(parent, fg_color=T.WARN_BG, corner_radius=8)
    ctk.CTkLabel(f, text=text, font=T.font(12), text_color=color, justify="left",
                 anchor="w", wraplength=700).pack(fill="x", padx=12, pady=8)
    return f


class LogBox(ctk.CTkTextbox):
    def __init__(self, parent, **kw):
        kw.setdefault("height", 160)
        super().__init__(parent, font=T.mono(12), wrap="word", corner_radius=8,
                         border_width=1, border_color=T.BORDER, **kw)
        self.configure(state="disabled")

    def write(self, text, stamp=True):
        self.configure(state="normal")
        prefix = f"[{time.strftime('%H:%M:%S')}] " if stamp else ""
        self.insert("end", prefix + text + "\n")
        self.see("end")
        self.configure(state="disabled")

    def clear(self):
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")

    def text(self):
        return self.get("1.0", "end").strip()


class LineChart(ctk.CTkFrame):
    """Biểu đồ đường đơn giản trên tk.Canvas, tự co giãn, đổi màu theo giao diện.

    series: list (tên, màu(sáng,tối)). set_data(list các list giá trị, None = mất gói).
    """

    def __init__(self, parent, series, height=180, unit="ms", min_top=10):
        super().__init__(parent, fg_color="transparent")
        self.series, self.unit, self.min_top = series, unit, min_top
        self.data = [[] for _ in series]
        self.labels = []
        self.canvas = tk.Canvas(self, height=height, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw())

    def set_data(self, data, labels=None):
        self.data = data
        self.labels = labels or []
        self.redraw()

    def redraw(self):
        c = self.canvas
        c.delete("all")
        c.configure(bg=T.pick(T.CARD))
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50:
            return
        left, right, top, bottom = 46, 10, 22, 22
        vals = [v for s in self.data for v in s if v is not None]
        vmax = max(vals) if vals else 0
        top_val = max(self.min_top, vmax * 1.15)
        grid, muted = T.pick(T.BORDER), T.pick(T.MUTED)
        for i in range(5):
            y = top + (h - top - bottom) * i / 4
            c.create_line(left, y, w - right, y, fill=grid)
            c.create_text(left - 6, y, text=f"{top_val * (4 - i) / 4:.0f}", fill=muted,
                          anchor="e", font=(T.FONT_FAMILY, 9))
        c.create_text(left - 6, 8, text=self.unit, fill=muted, anchor="e", font=(T.FONT_FAMILY, 9))
        n = max((len(s) for s in self.data), default=0)
        if n:
            step = (w - left - right) / max(n - 1, 1)
            ys = lambda v: top + (h - top - bottom) * (1 - v / top_val)  # noqa: E731
            for (name, color), series in zip(self.series, self.data):
                col = T.pick(color)
                pts = []
                for i, v in enumerate(series):
                    x = left + i * step
                    if v is None:
                        if len(pts) >= 4:
                            c.create_line(*pts, fill=col, width=2, smooth=False)
                        elif len(pts) == 2:
                            c.create_oval(pts[0] - 2, pts[1] - 2, pts[0] + 2, pts[1] + 2, fill=col, outline="")
                        pts = []
                        c.create_line(x, h - bottom, x, h - bottom - 6, fill=T.pick(T.BAD), width=2)
                    else:
                        pts += [x, ys(v)]
                if len(pts) >= 4:
                    c.create_line(*pts, fill=col, width=2)
                elif len(pts) == 2:
                    c.create_oval(pts[0] - 3, pts[1] - 3, pts[0] + 3, pts[1] + 3, fill=col, outline="")
            if self.labels:
                c.create_text(left, h - 8, text=self.labels[0], fill=muted, anchor="w", font=(T.FONT_FAMILY, 9))
                c.create_text(w - right, h - 8, text=self.labels[-1], fill=muted, anchor="e", font=(T.FONT_FAMILY, 9))
        else:
            c.create_text(w / 2, h / 2, text="Chưa có dữ liệu", fill=muted, font=(T.FONT_FAMILY, 11))
        x = left
        for name, color in self.series:
            c.create_rectangle(x, 6, x + 10, 14, fill=T.pick(color), outline="")
            c.create_text(x + 14, 10, text=name, fill=T.pick(T.TEXT), anchor="w", font=(T.FONT_FAMILY, 9))
            x += 24 + len(name) * 7


def style_tables(root):
    """Áp màu cho ttk.Treeview theo giao diện sáng/tối."""
    s = ttk.Style(root)
    s.theme_use("clam")
    bg, fg, head = T.pick(T.CARD), T.pick(T.TEXT), T.pick(T.SIDEBAR)
    s.configure("NT.Treeview", background=bg, fieldbackground=bg, foreground=fg, rowheight=26,
                borderwidth=0, relief="flat", bordercolor=bg, lightcolor=bg, darkcolor=bg,
                font=(T.FONT_FAMILY, 10))
    s.layout("NT.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    s.configure("NT.Treeview.Heading", background=head, foreground=T.pick(T.MUTED), relief="flat",
                bordercolor=head, lightcolor=head, darkcolor=head, font=(T.FONT_FAMILY, 10, "bold"))
    s.map("NT.Treeview", background=[("selected", T.pick(T.ACCENT))], foreground=[("selected", "#ffffff")])
    s.map("NT.Treeview.Heading", background=[("active", T.pick(T.NAV_HOVER))])


class Table(ctk.CTkFrame):
    """Bảng có thanh cuộn. columns: list (key, tiêu đề, độ rộng, căn lề)."""

    def __init__(self, parent, columns, height=8):
        super().__init__(parent, fg_color=T.CARD, corner_radius=8, border_width=1, border_color=T.BORDER)
        self.keys = [c[0] for c in columns]
        self.tree = ttk.Treeview(self, columns=self.keys, show="headings", height=height,
                                 style="NT.Treeview", selectmode="browse")
        for key, title, width, anchor in columns:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor=anchor, stretch=anchor == "w")
        sb = ctk.CTkScrollbar(self, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        sb.pack(side="right", fill="y", pady=4)
        self.tree.tag_configure("good", foreground=T.pick(T.GOOD))
        self.tree.tag_configure("bad", foreground=T.pick(T.BAD))
        self.tree.tag_configure("ok", foreground=T.pick(T.OK))
        self.rows = []

    def set_rows(self, rows, tags=None):
        """rows: list dict hoặc tuple; tags: list tag tương ứng (tô màu)."""
        self.tree.delete(*self.tree.get_children())
        self.rows = list(rows)
        for i, r in enumerate(self.rows):
            values = [r.get(k, "") for k in self.keys] if isinstance(r, dict) else list(r)
            tag = (tags[i],) if tags and tags[i] else ()
            self.tree.insert("", "end", iid=str(i), values=values, tags=tag)

    def add_row(self, row, tag=""):
        self.rows.append(row)
        values = [row.get(k, "") for k in self.keys] if isinstance(row, dict) else list(row)
        self.tree.insert("", "end", iid=str(len(self.rows) - 1), values=values, tags=(tag,) if tag else ())
        self.tree.see(str(len(self.rows) - 1))

    def selected(self):
        sel = self.tree.selection()
        return self.rows[int(sel[0])] if sel else None

    def on_double(self, fn):
        self.tree.bind("<Double-1>", lambda e: fn())
