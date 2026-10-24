"""Procesado de carátulas (QImage es seguro fuera del hilo de la interfaz)."""

from __future__ import annotations

import hashlib

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage

THUMBNAIL_SIZE = 300


def make_thumbnail(data: bytes, size: int = THUMBNAIL_SIZE) -> bytes | None:
    """Reduce la carátula para no inflar la base de datos. None si no es una imagen válida."""
    image = QImage()
    if not image.loadFromData(data):
        return None
    if image.width() > size or image.height() > size:
        image = image.scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
    for fmt, quality in (("JPG", 88), ("PNG", -1)):
        buffer_bytes = QByteArray()
        buffer = QBuffer(buffer_bytes)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        ok = image.convertToFormat(QImage.Format.Format_RGB32).save(buffer, fmt, quality)
        buffer.close()
        if ok:
            return bytes(buffer_bytes.data())
    return None


def cover_hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()
