"""Vẽ icon app bằng Pillow (dùng cho khay hệ thống và để tạo assets/icon.ico)."""
from PIL import Image, ImageDraw


def make_icon(size=256, status=None):
    """Quả địa cầu trắng trên nền xanh bo góc. status: None | 'bad' (chấm đỏ) | 'vpn' (chấm xanh lá)."""
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(s * 0.22)
    # nền gradient xanh
    for y in range(s):
        t = y / s
        col = (int(37 + 22 * t), int(99 - 30 * t), int(235 - 20 * t), 255)
        d.line([(0, y), (s, y)], fill=col)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=r, fill=255)
    img.putalpha(mask)
    d = ImageDraw.Draw(img)
    w = max(2, s // 28)
    c, R = s / 2, s * 0.30
    box = [c - R, c - R, c + R, c + R]
    d.ellipse(box, outline="white", width=w)
    d.ellipse([c - R * 0.45, c - R, c + R * 0.45, c + R], outline="white", width=w)
    d.line([c, c - R, c, c + R], fill="white", width=w)
    d.line([c - R, c, c + R, c], fill="white", width=w)
    for k in (-0.5, 0.5):
        y = c + R * k
        half = (R ** 2 - (R * k) ** 2) ** 0.5
        d.line([c - half, y, c + half, y], fill="white", width=w)
    if status:
        color = {"bad": (239, 68, 68, 255), "vpn": (34, 197, 94, 255)}.get(status, (234, 179, 8, 255))
        rr = s * 0.17
        d.ellipse([s - rr * 2 - s * 0.03, s - rr * 2 - s * 0.03, s - s * 0.03, s - s * 0.03],
                  fill=color, outline="white", width=max(1, w // 2))
    return img
