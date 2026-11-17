"""Màu sắc & font dùng chung. Mỗi màu là (sáng, tối) theo chuẩn customtkinter."""
import sys

import customtkinter as ctk

FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
MONO_FAMILY = "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono"

ACCENT = ("#2563eb", "#3b82f6")
ACCENT_HOVER = ("#1d4ed8", "#2563eb")
SIDEBAR = ("#eef1f6", "#141821")
CONTENT = ("#f7f8fb", "#0e1117")
CARD = ("#ffffff", "#1a1f2b")
BORDER = ("#e2e6ee", "#262c3a")
TEXT = ("#111827", "#e5e7eb")
MUTED = ("#6b7280", "#8b93a7")
NAV_HOVER = ("#dfe4ee", "#1f2533")
NAV_ACTIVE = ("#dbe6ff", "#1e2a44")

GOOD = ("#16a34a", "#22c55e")
OK = ("#ca8a04", "#eab308")
BAD = ("#dc2626", "#ef4444")
WARN_BG = ("#fff7ed", "#2a1f12")
DANGER = ("#dc2626", "#b91c1c")
DANGER_HOVER = ("#b91c1c", "#991b1b")
NEUTRAL_BTN = ("#e5e7eb", "#2a3142")
NEUTRAL_HOVER = ("#d1d5db", "#343c50")

QUALITY = {"good": GOOD, "ok": OK, "bad": BAD, "": TEXT, None: TEXT}


def is_dark():
    return ctk.get_appearance_mode().lower() == "dark"


def pick(color):
    """Lấy 1 mã màu theo giao diện hiện tại (cho tk.Canvas / ttk)."""
    return color[1] if is_dark() else color[0]


def font(size=13, weight="normal"):
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def mono(size=12):
    return ctk.CTkFont(family=MONO_FAMILY, size=size)
