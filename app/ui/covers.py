"""Carga y caché de carátulas, con imagen de reemplazo."""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap

from ..artwork import image_format
from ..database import Database
from . import theme
from .icons import glyph_pixmap

_MAX_CACHE = 600


class CoverProvider:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._cache: OrderedDict[tuple[str | None, int], QPixmap] = OrderedDict()
        theme.on_change(self._cache.clear)  # la carátula de reemplazo depende del tema

    def pixmap(self, cover_hash: str | None, size: int) -> QPixmap:
        key = (cover_hash, size)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached

        result: QPixmap | None = None
        if cover_hash:
            data = self._db.get_cover(cover_hash)
            source = QPixmap()
            fmt = image_format(data) if data else None
            if fmt and source.loadFromData(data, fmt):
                result = _rounded(source, size)
        if result is None:
            result = _placeholder(size)

        self._cache[key] = result
        if len(self._cache) > _MAX_CACHE:
            self._cache.popitem(last=False)
        return result


def _rounded(source: QPixmap, size: int, ratio: float = 2.0) -> QPixmap:
    px = int(size * ratio)
    scaled = source.scaled(
        px, px, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
    )
    out = QPixmap(px, px)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, px, px), px * 0.08, px * 0.08)
    painter.setClipPath(path)
    painter.drawPixmap((px - scaled.width()) // 2, (px - scaled.height()) // 2, scaled)
    painter.end()
    out.setDevicePixelRatio(ratio)
    return out


def _placeholder(size: int, ratio: float = 2.0) -> QPixmap:
    px = int(size * ratio)
    out = QPixmap(px, px)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, px, px)
    gradient.setColorAt(0, QColor(theme.color("cover_a")))
    gradient.setColorAt(1, QColor(theme.color("cover_b")))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, px, px), px * 0.08, px * 0.08)
    painter.fillPath(path, gradient)
    # Se dibuja en píxeles reales: ratio 1 sobre un lienzo que aún no tiene DPR.
    note = glyph_pixmap("music", "faint", max(10, int(px * 0.42)), 1.0)
    note_size = note.width()
    painter.drawPixmap((px - note_size) // 2, (px - note_size) // 2, note)
    painter.end()
    out.setDevicePixelRatio(ratio)
    return out
