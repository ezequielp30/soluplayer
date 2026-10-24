"""Iconos vectoriales (SVG) con un mismo trazo, coloreados según el tema.

Retícula de 24×24, trazo 1.8 con extremos redondeados. Los controles de transporte
(reproducir, pausa, anterior, siguiente, detener) van rellenos para leerse de un vistazo.
Varias formas siguen la geometría de Lucide (licencia ISC, https://lucide.dev).

`color` acepta un rol del tema ('text', 'muted', 'accent_text', 'on_accent', 'warning',
'faint'…) o un color literal.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme

# Roles del tema (se resuelven en el momento de dibujar, así siguen al tema activo).
TEXT = "text"
MUTED = "muted"
ACCENT = "accent_text"

_STROKE = 'fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
_FILL = 'fill="{c}"'

_SPEAKER = (
    '<path d="M11 4.7a.7.7 0 0 0-1.2-.5L6.4 7.6A1.4 1.4 0 0 1 5.4 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.4'
    'a1.4 1.4 0 0 1 1 .4l3.4 3.4a.7.7 0 0 0 1.2-.5z"/>'
)

# nombre -> (estilo, contenido SVG)
_SHAPES: dict[str, tuple[str, str]] = {
    "play": (_FILL, '<path d="M8 5.6v12.8a1.1 1.1 0 0 0 1.7.9l10-6.4a1.1 1.1 0 0 0 0-1.8l-10-6.4A1.1 1.1 0 0 0 8 5.6z"/>'),
    "pause": (_FILL, '<rect x="6" y="5" width="4.2" height="14" rx="1.3"/><rect x="13.8" y="5" width="4.2" height="14" rx="1.3"/>'),
    "prev": (
        _FILL,
        '<path d="M18.5 6.6v10.8a1 1 0 0 1-1.6.8l-7.6-5.4a1 1 0 0 1 0-1.6l7.6-5.4a1 1 0 0 1 1.6.8z"/>'
        '<rect x="5.2" y="5.5" width="2.5" height="13" rx="1.25"/>',
    ),
    "next": (
        _FILL,
        '<path d="M5.5 6.6v10.8a1 1 0 0 0 1.6.8l7.6-5.4a1 1 0 0 0 0-1.6L7.1 5.8a1 1 0 0 0-1.6.8z"/>'
        '<rect x="16.3" y="5.5" width="2.5" height="13" rx="1.25"/>',
    ),
    "stop": (_FILL, '<rect x="6.5" y="6.5" width="11" height="11" rx="2.4"/>'),
    "shuffle": (
        _STROKE,
        '<path d="M2 18h1.4c1.3 0 2.5-.6 3.3-1.7l6.1-8.6c.7-1.1 2-1.7 3.3-1.7H22"/><path d="m18 2 4 4-4 4"/>'
        '<path d="M2 6h1.9c1.5 0 2.9.9 3.6 2.2"/><path d="M22 18h-5.9c-1.3 0-2.6-.7-3.3-1.8l-.5-.8"/>'
        '<path d="m18 14 4 4-4 4"/>',
    ),
    "repeat": (
        _STROKE,
        '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/>'
        '<path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    ),
    "repeat_one": (
        _STROKE,
        '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/>'
        '<path d="M21 13v1a4 4 0 0 1-4 4H3"/><path d="M11 10h1v4"/>',
    ),
    "volume": (_STROKE, _SPEAKER + '<path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.4 18.4a9 9 0 0 0 0-12.8"/>'),
    "mute": (_STROKE, _SPEAKER + '<path d="m22 9-6 6"/><path d="m16 9 6 6"/>'),
    "search": (_STROKE, '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.9-3.9"/>'),
    "add": (_STROKE, '<path d="M5 12h14"/><path d="M12 5v14"/>'),
    "add_circle": (_STROKE, '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/><path d="M12 8v8"/>'),
    "recent": (_STROKE, '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>'),
    "artist": (_STROKE, '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/>'),
    "album": (_STROKE, '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.6"/><path d="M12 5.5a6.5 6.5 0 0 0-6.5 6.5"/>'),
    "song": (_STROKE, '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>'),
    "music": (_STROKE, '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>'),
    "playlist": (
        _STROKE,
        '<path d="M21 15V6"/><circle cx="18.5" cy="15.5" r="2.5"/><path d="M12 12H3"/><path d="M16 6H3"/><path d="M12 18H3"/>',
    ),
    "warning": (
        _STROKE,
        '<path d="M10.3 3.9 2.4 17.6A2 2 0 0 0 4.1 20.6h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
        '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    ),
    "folder": (
        _STROKE,
        '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9l-.8-1.2A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13'
        'a2 2 0 0 0 2 2z"/>',
    ),
    "folder_plus": (
        _STROKE,
        '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9l-.8-1.2A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13'
        'a2 2 0 0 0 2 2z"/><path d="M12 10v6"/><path d="M9 13h6"/>',
    ),
    "trash": (
        _STROKE,
        '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    ),
    "copy": (
        _STROKE,
        '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2"/>',
    ),
    "globe": (
        _STROKE,
        '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18"/><path d="M12 3a14 14 0 0 0 0 18"/>',
    ),
    "settings": (
        _STROKE,
        '<path d="M4 7h10"/><path d="M18 7h2"/><circle cx="16" cy="7" r="2"/><path d="M4 17h2"/><path d="M10 17h10"/>'
        '<circle cx="8" cy="17" r="2"/>',
    ),
}

_cache: dict[tuple[str, str, int, str], QIcon] = {}


def _svg(name: str, color: str) -> bytes:
    style, body = _SHAPES[name]
    paint = style.format(c=color)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g {paint}>{body}</g></svg>'
    ).encode()


def glyph_pixmap(name: str, color: str = TEXT, size: int = 20, ratio: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(_svg(name, theme.color(color))))
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, pixmap.width(), pixmap.height()))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icon(name: str, color: str = TEXT, size: int = 20) -> QIcon:
    key = (name, color, size, theme.current().name)
    if key not in _cache:
        result = QIcon()
        result.addPixmap(glyph_pixmap(name, color, size), QIcon.Mode.Normal)
        result.addPixmap(glyph_pixmap(name, "faint", size), QIcon.Mode.Disabled)
        _cache[key] = result
    return _cache[key]


_padded: dict[tuple[str, str, int, int, str], QPixmap] = {}


def padded_pixmap(name: str, color: str, size: int, box: int) -> QPixmap:
    """Icono de `size` centrado en un lienzo de `box`: las vistas escalan los iconos al
    tamaño de icono de la vista, y así el «+» de cada fila no se agranda como la carátula."""
    key = (name, color, size, box, theme.current().name)
    if key not in _padded:
        ratio = 2.0
        canvas = QPixmap(int(box * ratio), int(box * ratio))
        canvas.fill(Qt.GlobalColor.transparent)
        glyph = glyph_pixmap(name, color, size, ratio)
        painter = QPainter(canvas)
        offset = (box - size) * ratio / 2
        glyph.setDevicePixelRatio(1.0)
        painter.drawPixmap(int(offset), int(offset), glyph)
        painter.end()
        canvas.setDevicePixelRatio(ratio)
        _padded[key] = canvas
    return _padded[key]

