"""Tạo assets/icon.ico và assets/icon.png từ hình vẽ trong nettools/ui/icon.py."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from nettools.ui.icon import make_icon  # noqa: E402

out = os.path.join(ROOT, "assets")
os.makedirs(out, exist_ok=True)
img = make_icon(256)
img.save(os.path.join(out, "icon.png"))
img.save(os.path.join(out, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Đã tạo assets/icon.ico và assets/icon.png")
