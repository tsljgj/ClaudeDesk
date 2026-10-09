"""程序图标：运行时按未读数画托盘 / 窗口图标；构建时生成 .ico。"""
from __future__ import annotations

import struct

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

BASE = QColor("#C96442")      # 平常：陶土橙
ALERT = QColor("#F5A524")     # 闪烁的另一帧：琥珀
BADGE = QColor("#E5484D")     # 未读数：红
PENDING = QColor("#FFD166")   # 有待决定但都看过：小黄点
SIZES = (16, 20, 24, 32, 40, 48, 64)


def draw(size: int, count: int = 0, alert: bool = False, pending: bool = False) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    r = size * 0.22
    p.setPen(Qt.NoPen)
    p.setBrush(ALERT if alert else BASE)
    p.drawRoundedRect(QRectF(0, 0, size, size), r, r)

    f = QFont("Segoe UI")
    f.setPixelSize(max(8, int(size * 0.74)))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    shift = size * 0.12 if count > 0 else 0.0
    p.drawText(QRectF(-shift, -shift - size * 0.02, size, size), Qt.AlignCenter, "C")

    if count > 0:
        txt = str(count) if count < 100 else "99+"
        bh = size * 0.60
        bw = bh if len(txt) == 1 else min(size, bh * (1.0 + 0.42 * (len(txt) - 1)))
        rect = QRectF(size - bw, size - bh, bw, bh)
        p.setBrush(BADGE)
        p.setPen(QPen(QColor("#FFFFFF"), max(1.0, size / 24)))
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), bh / 2, bh / 2)
        bf = QFont("Segoe UI")
        bf.setPixelSize(max(7, int(bh * (0.80 if len(txt) == 1 else 0.70))))
        bf.setBold(True)
        p.setFont(bf)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(rect, Qt.AlignCenter, txt)
    elif pending:
        d = size * 0.38
        p.setBrush(PENDING)
        p.setPen(QPen(QColor("#FFFFFF"), max(1.0, size / 24)))
        p.drawEllipse(QRectF(size - d - 0.5, 0.5, d, d))
    p.end()
    return pm


def make_icon(count: int = 0, alert: bool = False, pending: bool = False) -> QIcon:
    icon = QIcon()
    for s in SIZES:
        icon.addPixmap(draw(s, count, alert, pending))
    return icon


def write_ico(path: str, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    """把几种尺寸的 PNG 打进一个 .ico（PyInstaller --icon 用）。"""
    blobs = []
    for s in sizes:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        draw(s).save(buf, "PNG")
        buf.close()
        blobs.append((s, bytes(ba.data())))
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries, data = b"", b""
    for s, png in blobs:
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    with open(path, "wb") as f:
        f.write(header + entries + data)


if __name__ == "__main__":  # 构建脚本调用：python icons.py out.ico
    import sys

    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication(sys.argv)
    write_ico(sys.argv[1])
    print("wrote", sys.argv[1])
