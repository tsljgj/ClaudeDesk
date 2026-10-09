"""程序图标（Pillow 画）：渐变圆角方块里一个白色的 "C"，开口处一个圆点——像一条刚到的消息。

托盘图标按状态变化：右下角黑底白字的未读数；有待决定但都看过时右上角一个白点；
需要你马上处理时（未读的待决定 / 紧急消息）在橙色和墨黑之间闪。
"""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFont

ACCENT_A = (255, 138, 61)   # 渐变起点（左上）
ACCENT_B = (238, 59, 22)    # 渐变终点（右下）
INK = (22, 22, 28)
WHITE = (255, 255, 255)
SS = 4  # 超采样倍数：先画大再缩小，边缘更平滑


def _gradient(size: int, a, b) -> Image.Image:
    g = Image.new("RGBA", (size, size))
    px = g.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1) or 1)
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
    return g


def _font(px: int):
    for name in ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def render(size: int = 64, count: int = 0, alert: bool = False, pending: bool = False) -> Image.Image:
    S = size * SS
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # 底：圆角方块（小尺寸时圆角小一点，更像系统图标）
    radius = int(S * (0.24 if size >= 32 else 0.2))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=radius, fill=255)
    if alert:
        base = Image.new("RGBA", (S, S), INK + (255,))
    else:
        base = _gradient(64, ACCENT_A, ACCENT_B).resize((S, S), Image.BILINEAR)
    im.paste(base, (0, 0), mask)

    d = ImageDraw.Draw(im)
    # "C"：开口朝右的粗圆弧
    shift = S * 0.10 if count > 0 else 0.0
    cx, cy = S * 0.45 - shift, S * 0.5 - shift
    r = S * 0.25
    w = max(2 * SS, int(S * 0.13))
    d.arc((cx - r, cy - r, cx + r, cy + r), start=55, end=305, fill=WHITE, width=w)
    for ang in (55, 305):  # 圆头
        a = math.radians(ang)
        ex, ey = cx + (r - w / 2) * math.cos(a), cy + (r - w / 2) * math.sin(a)
        d.ellipse((ex - w / 2, ey - w / 2, ex + w / 2, ey + w / 2), fill=WHITE)
    dot = S * 0.075
    dx = cx + r * 1.02
    d.ellipse((dx - dot, cy - dot, dx + dot, cy + dot), fill=(255, 220, 200) if alert else WHITE)

    if count > 0:
        txt = str(count) if count < 100 else "99+"
        bh = S * 0.56
        bw = bh if len(txt) == 1 else min(S, bh * (1.0 + 0.40 * (len(txt) - 1)))
        x0, y0 = S - bw, S - bh
        ring = max(SS, int(S / 22))
        d.rounded_rectangle((x0, y0, S - 1, S - 1), radius=bh / 2, fill=WHITE)
        d.rounded_rectangle((x0 + ring, y0 + ring, S - 1 - ring, S - 1 - ring), radius=bh / 2 - ring,
                            fill=(ACCENT_B + (255,)) if alert else INK + (255,))
        f = _font(int(bh * (0.70 if len(txt) == 1 else 0.58)))
        d.text((x0 + bw / 2, y0 + bh / 2 + S * 0.005), txt, font=f, fill=WHITE, anchor="mm")
    elif pending:
        dd = S * 0.36
        ring = max(SS, int(S / 22))
        d.ellipse((S - dd, 0, S - 1, dd - 1), fill=INK)
        d.ellipse((S - dd + ring, ring, S - 1 - ring, dd - 1 - ring), fill=WHITE)
    return im.resize((size, size), Image.LANCZOS)


def save_ico(path: str, sizes=(16, 20, 24, 32, 40, 48, 64, 128, 256)) -> None:
    imgs = [render(s) for s in sizes]
    imgs[-1].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[:-1])


def png_bytes(size: int = 64, **kw) -> bytes:
    buf = io.BytesIO()
    render(size, **kw).save(buf, "PNG")
    return buf.getvalue()


if __name__ == "__main__":  # 构建脚本：python -m claudedesk.icon out.ico
    import sys

    save_ico(sys.argv[1])
    print("wrote", sys.argv[1])
