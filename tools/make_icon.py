"""Genera assets/icono.ico (16–256 px) y assets/icono.png: tres barras de vúmetro ámbar sobre grafito.

Uso: python tools/make_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath

SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)
    margin = s * 0.04
    body = QRectF(margin, margin, s - 2 * margin, s - 2 * margin)
    radius = s * 0.22
    path = QPainterPath()
    path.addRoundedRect(body, radius, radius)
    background = QLinearGradient(0, 0, 0, s)
    background.setColorAt(0, QColor("#2b2d35"))
    background.setColorAt(1, QColor("#111215"))
    p.fillPath(path, background)

    # Tres barras de nivel (el «vúmetro» de la interfaz), de distinta altura.
    bar_w = s * 0.15
    gap = s * 0.085
    total = 3 * bar_w + 2 * gap
    x0 = (s - total) / 2
    base = s * 0.78
    amber = QLinearGradient(0, s * 0.2, 0, base)
    amber.setColorAt(0, QColor("#ffc45c"))
    amber.setColorAt(1, QColor("#f59e1b"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(amber)
    for i, level in enumerate((0.42, 0.62, 0.30)):
        h = s * level
        p.drawRoundedRect(QRectF(x0 + i * (bar_w + gap), base - h, bar_w, h), bar_w * 0.35, bar_w * 0.35)
    p.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    buf.close()
    return bytes(data.data())


def write_ico(path: Path, sizes=SIZES) -> None:
    """ICO con una imagen PNG por tamaño (formato admitido desde Windows Vista)."""
    images = [png_bytes(draw(size)) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in zip(sizes, images, strict=True):
        dim = 0 if size >= 256 else size  # 0 significa 256
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    path.write_bytes(header + entries + blobs)


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # QPainter necesita una aplicación Qt
    ASSETS.mkdir(exist_ok=True)
    app.processEvents()
    write_ico(ASSETS / "icono.ico")
    draw(256).save(str(ASSETS / "icono.png"))
    print(f"Ícono creado en {ASSETS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
