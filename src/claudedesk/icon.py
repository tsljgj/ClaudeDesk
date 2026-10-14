"""程序图标（Pillow 画）：渐变圆角方块里一个白色的 "C"，开口处一个圆点——像一条刚到的消息。

托盘图标按状态变化：右下角红底白字的未读数（白边隔开底色）；有待决定但都看过时右上角一个红点；
需要你马上处理时（未读的待决定 / 紧急消息）底色在橙色和墨黑之间闪。
任务栏按钮另有一个角标（render_badge，Windows 的 overlay icon）：同样的未读数。
"""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFont

ACCENT_A = (255, 138, 61)   # 渐变起点（左上）
ACCENT_B = (238, 59, 22)    # 渐变终点（右下）
INK = (22, 22, 28)
WHITE = (255, 255, 255)
BADGE = (232, 17, 35)       # 角标红（Windows 的通知红）
SS = 4  # 超采样倍数：先画大再缩小，边缘更平滑（小字也是：16px 下直接画的字被 hinting 扭得变形）
DOT = "•"  # 角标"没有未读但有待决定"


def _gradient(size: int, a, b) -> Image.Image:
    g = Image.new("RGBA", (size, size))
    px = g.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1) or 1)
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
    return g


def _font(px: int, bold: bool = False):
    names = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else \
        ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def badge_text(count: int) -> str:
    """角标上的字：1..99 原样，100 起写 99+；0 → ""（不显示）。"""
    return "" if count <= 0 else str(count) if count < 100 else "99+"


def overlay_state(unread: int, open_: int) -> tuple[str, str]:
    """任务栏角标 (字, 读屏说明)：有未读 → 未读数；没有未读但有待决定 → 圆点；都没有 → ("", "") 清掉。"""
    t = badge_text(unread)
    if t:
        return t, f"{t} 条未读"
    return (DOT, "有待你决定的消息") if open_ > 0 else ("", "")


def _pill(d: ImageDraw.ImageDraw, box, text: str, ring: float) -> None:
    """红底白字的圆 / 胶囊，外面一圈白边（压在橙色图标、深色浅色任务栏上都分得开）。box 含白边；text 为空 = 实心红点。
    三个字（99+）用圆角小一点的方块：圆头太占地方，16px 下字会小到认不出。"""
    x0, y0, x1, y1 = box
    h, w = y1 - y0, x1 - x0
    rad, pad, k = (h * 0.38, 0.10, 0.66) if len(text) >= 3 else (h / 2, 0.30, 0.62 if len(text) == 1 else 0.58)
    d.rounded_rectangle(box, radius=rad, fill=WHITE)
    d.rounded_rectangle((x0 + ring, y0 + ring, x1 - ring, y1 - ring), radius=rad - ring, fill=BADGE)
    if not text:
        return
    ih, iw = h - 2 * ring, w - 2 * ring
    # 按字的实际墨迹定大小和位置（"mm" 锚点按行高居中，数字会偏上）：高 ≤ 内框的 k，宽 ≤ 去掉两头留白后的宽度
    l, t, r, b = _font(100, True).getbbox(text)
    px = max(6, int(min(ih * k * 100 / (b - t), (iw - ih * pad) * 100 / (r - l))))
    f = _font(px, True)
    l, t, r, b = f.getbbox(text)
    d.text(((x0 + x1) / 2 - (l + r) / 2, (y0 + y1) / 2 - (t + b) / 2), text, font=f, fill=WHITE)


def render_badge(size: int, text: str) -> Image.Image:
    """任务栏按钮角标（SetOverlayIcon 用）。size = 任务栏那块屏幕的小图标尺寸（16/20/24/32…），按这个像素数画才清楚。
    一位数是占满的圆；两位数是胶囊，99+ 是圆角块，都占满宽度；DOT 是靠右的小红点。
    竖直方向都居中：Windows 10 把角标放在图标右下角，Windows 11 放在右上角，居中两边看着都对。"""
    S = size * SS
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ring = max(SS, S / 16)
    if text == DOT:
        dd = S * 0.62
        _pill(ImageDraw.Draw(im), (S - dd, (S - dd) / 2, S, (S + dd) / 2), "", ring)
    elif text:
        h = S if len(text) == 1 else S * (0.82 if len(text) == 2 else 0.80)
        _pill(ImageDraw.Draw(im), (0, (S - h) / 2, S, (S + h) / 2), text, ring)
    return im.resize((size, size), Image.LANCZOS)


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

    ring = max(SS, S / 16)
    txt = badge_text(count)
    if txt:  # 未读数：右下角红底白字，一位数是圆，多位数是胶囊（99+ 占满整个宽度）
        bh = S * (0.66 if len(txt) == 1 else 0.60 if len(txt) == 2 else 0.62)
        bw = bh if len(txt) == 1 else min(S, bh * (1.0 + 0.45 * (len(txt) - 1)))
        _pill(d, (S - bw, S - bh, S, S), txt, ring)
    elif pending:
        dd = S * 0.40
        _pill(d, (S - dd, 0, S, dd), "", ring)
    return im.resize((size, size), Image.LANCZOS)


def save_ico(path: str, sizes=(16, 20, 24, 32, 40, 48, 64, 128, 256)) -> None:
    imgs = [render(s) for s in sizes]
    imgs[-1].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[:-1])


def to_png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def png_bytes(size: int = 64, **kw) -> bytes:
    return to_png(render(size, **kw))


if __name__ == "__main__":  # 构建脚本：python -m claudedesk.icon out.ico
    import sys

    save_ico(sys.argv[1])
    print("wrote", sys.argv[1])
