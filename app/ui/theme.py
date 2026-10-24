"""Temas visuales: 9 paletas (5 oscuras y 4 claras) con fondos casi neutros y un acento propio cada una.

Grafito (oscuro) y Aluminio (claro) son los de «auto», que sigue el tema claro/oscuro de Windows.
Cada paleta trae además tres colores para identificar las secciones de la barra lateral.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

MODE_AUTO, MODE_LIGHT, MODE_DARK = "auto", "light", "dark"
MODES = (MODE_AUTO, MODE_LIGHT, MODE_DARK)


@dataclass(frozen=True)
class Palette:
    name: str
    dark: bool
    bg: str  # panel principal
    sidebar: str
    bar: str  # barra del reproductor
    elevated: str  # tarjetas, menús, campos
    border: str
    hover: str
    row_alt: str
    text: str
    muted: str  # texto secundario (≥ 4.5:1 sobre bg)
    faint: str  # deshabilitado / decorativo
    accent: str  # relleno del acento (botón reproducir, progreso)
    accent_hover: str
    accent_text: str  # acento usado como texto o icono sobre el fondo (≥ 4.5:1)
    accent_soft: str  # selección
    on_accent: str  # texto/icono sobre el relleno del acento
    warning: str
    warning_soft: str
    success: str
    danger: str
    cover_a: str  # degradado de la carátula de reemplazo
    cover_b: str
    sec_library: str  # encabezado «Biblioteca» de la barra lateral (≥ 4.5:1 sobre sidebar)
    sec_playlists: str  # encabezado «Playlists»
    sec_folders: str  # encabezado «Carpetas»


# Reglas comunes (las comprueba tests/theme_contrast_test.py): fondos casi neutros con un acento propio;
# texto ≥ 7:1; texto secundario, acento como texto y títulos de sección ≥ 4.5:1; texto sobre el acento
# ≥ 4.5:1. Los tres colores de sección se separan en el círculo cromático y se alejan del acento.

GRAPHITE = Palette(
    name="Grafito", dark=True,
    bg="#1d1e21", sidebar="#151618", bar="#232428", elevated="#282a2e", border="#33353a", hover="#2d2f34",
    row_alt="#202124", text="#cccccf", muted="#989ba3", faint="#62656e",
    accent="#e1a956", accent_hover="#e9bc78", accent_text="#e1a956", accent_soft="#3e362a", on_accent="#1f1402",
    warning="#f0a47d", warning_soft="#3b312e", success="#6bc89a", danger="#f17e7e", cover_a="#303238", cover_b="#222327",
    sec_library="#82ace0", sec_playlists="#dc98b5", sec_folders="#74ba98",
)

ALUMINIUM = Palette(
    name="Aluminio", dark=False,
    bg="#f4f4f5", sidebar="#eaebed", bar="#eff0f1", elevated="#f9f9f9", border="#dbdde1", hover="#dfe1e5",
    row_alt="#eeeff1", text="#36373a", muted="#5b5f69", faint="#a6aab2",
    accent="#c67619", accent_hover="#d88826", accent_text="#93570e", accent_soft="#eee2d6", on_accent="#1f1300",
    warning="#a94627", warning_soft="#ede4e2", success="#23734b", danger="#b93643", cover_a="#e0e1e5", cover_b="#cdcfd5",
    sec_library="#3a5e9a", sec_playlists="#873869", sec_folders="#215945",
)

MIDNIGHT = Palette(
    name="Medianoche", dark=True,
    bg="#191b24", sidebar="#13151c", bar="#1e212b", elevated="#242735", border="#2f3345", hover="#282c3d",
    row_alt="#1c1e28", text="#c9cbd4", muted="#979cb3", faint="#5d6279",
    accent="#8d94f1", accent_hover="#a4a9f4", accent_text="#9ca2f3", accent_soft="#2d3047", on_accent="#0e1133",
    warning="#f1af81", warning_soft="#373031", success="#5fc9a1", danger="#f28a96", cover_a="#2f344b", cover_b="#202330",
    sec_library="#6ab7c6", sec_playlists="#df9cb9", sec_folders="#cfad6d",
)

AURORA = Palette(
    name="Aurora", dark=True,
    bg="#181e1c", sidebar="#121716", bar="#1d2522", elevated="#232b28", border="#2e3934", hover="#28322e",
    row_alt="#1b211f", text="#c7cecb", muted="#94a6a0", faint="#5a6b65",
    accent="#48bd89", accent_hover="#68cc9e", accent_text="#57c795", accent_soft="#20392f", on_accent="#032112",
    warning="#f1b27e", warning_soft="#36332a", success="#97ddb5", danger="#f28d8d", cover_a="#293833", cover_b="#1e2623",
    sec_library="#93ade4", sec_playlists="#df9eb1", sec_folders="#cfb174",
)

WINE = Palette(
    name="Burdeos", dark=True,
    bg="#1f1a1c", sidebar="#181416", bar="#251f22", elevated="#2b2528", border="#3b3035", hover="#32292d",
    row_alt="#221c1f", text="#d1cacc", muted="#ad9ca2", faint="#6d5c63",
    accent="#ef8190", accent_hover="#f299a5", accent_text="#f18f9c", accent_soft="#422c30", on_accent="#2b0911",
    warning="#f2b487", warning_soft="#3d302b", success="#7ad1ac", danger="#f29487", cover_a="#3f2f36", cover_b="#282024",
    sec_library="#81bbbf", sec_playlists="#c7a2e8", sec_folders="#d1b374",
)

HIGH_CONTRAST = Palette(
    name="Alto contraste", dark=True,
    bg="#000000", sidebar="#000000", bar="#0d0d0d", elevated="#161616", border="#8c8c8c", hover="#2b2b2b",
    row_alt="#0f0f0f", text="#ffffff", muted="#e0e0e0", faint="#9e9e9e",
    accent="#ffd60a", accent_hover="#ffe347", accent_text="#ffd60a", accent_soft="#4d4100", on_accent="#000000",
    warning="#ffb86b", warning_soft="#4a2a00", success="#7dffa8", danger="#ff8f8f", cover_a="#2b2b2b", cover_b="#161616",
    sec_library="#7fd8ff", sec_playlists="#ffa3d6", sec_folders="#8dffb4",
)

OCEAN = Palette(
    name="Océano", dark=False,
    bg="#f2f4f6", sidebar="#e7ecf1", bar="#ecf0f4", elevated="#f9f9f9", border="#d5dce5", hover="#d9e1ea",
    row_alt="#eceff3", text="#2f3947", muted="#4a5a70", faint="#9dacbe",
    accent="#1165a7", accent_hover="#0e558e", accent_text="#10609d", accent_soft="#d2e0eb", on_accent="#ffffff",
    warning="#a94627", warning_soft="#ebe4e3", success="#1d724a", danger="#b93643", cover_a="#d6e1ec", cover_b="#c0d0e0",
    sec_library="#6150a0", sec_playlists="#8e3a5e", sec_folders="#684819",
)

SAND = Palette(
    name="Arena", dark=False,
    bg="#f5f2ed", sidebar="#ece5db", bar="#f1ece4", elevated="#f9f7f4", border="#e0d6ca", hover="#e5dbce",
    row_alt="#f0ebe3", text="#463d36", muted="#6a5a49", faint="#b4a592",
    accent="#a74b2c", accent_hover="#8c3e23", accent_text="#984326", accent_soft="#eadbd2", on_accent="#ffffff",
    warning="#9d5425", warning_soft="#ede4db", success="#407336", danger="#ad3439", cover_a="#e9decf", cover_b="#d9cbb5",
    sec_library="#405c8a", sec_playlists="#7c3d67", sec_folders="#415828",
)

LAVENDER = Palette(
    name="Lavanda", dark=False,
    bg="#f5f4f9", sidebar="#ebe8f4", bar="#f0eef7", elevated="#f9f9f9", border="#dcd7ec", hover="#e1dcf0",
    row_alt="#f0eef7", text="#3b374c", muted="#5c5475", faint="#aaa3c2",
    accent="#6f54cf", accent_hover="#5e42ba", accent_text="#664bc5", accent_soft="#e2def3", on_accent="#ffffff",
    warning="#a94627", warning_soft="#eee4e6", success="#23734b", danger="#b93643", cover_a="#e2dcf4", cover_b="#d1c8ec",
    sec_library="#1b5550", sec_playlists="#923b5e", sec_folders="#654718",
)

# Clave guardada en las preferencias → tema. «auto», «light» y «dark» se conservan por compatibilidad.
THEMES: dict[str, Palette] = {
    "grafito": GRAPHITE, "aluminio": ALUMINIUM, "medianoche": MIDNIGHT, "aurora": AURORA, "vino": WINE,
    "alto_contraste": HIGH_CONTRAST, "oceano": OCEAN, "arena": SAND, "lavanda": LAVENDER,
}
# Temas retirados en 1.8.0: quien los tenía elegidos pasa al más parecido.
_LEGACY = {"neon": "medianoche", "vumetro": "aurora"}

_current: Palette = ALUMINIUM
_mode: str = MODE_AUTO
_listeners: list[Callable[[], None]] = []


def current() -> Palette:
    return _current


def mode() -> str:
    return _mode


def color(role: str) -> str:
    """Color de un rol del tema ('text', 'muted', 'accent'…) o el valor tal cual si es un color."""
    return getattr(_current, role, role)


def qcolor(role: str) -> QColor:
    return QColor(color(role))


def on_change(callback: Callable[[], None]) -> None:
    _listeners.append(callback)


def off_change(callback: Callable[[], None]) -> None:
    if callback in _listeners:
        _listeners.remove(callback)


def system_is_dark() -> bool:
    hints = QGuiApplication.styleHints()
    return hints.colorScheme() == Qt.ColorScheme.Dark


def resolve(requested: str) -> Palette:
    requested = _LEGACY.get(requested, requested)
    if requested in THEMES:
        return THEMES[requested]
    if requested == MODE_DARK:
        return GRAPHITE
    if requested == MODE_LIGHT:
        return ALUMINIUM
    return GRAPHITE if system_is_dark() else ALUMINIUM


def valid(requested: str) -> bool:
    requested = _LEGACY.get(requested, requested)
    return requested in MODES or requested in THEMES


def apply(app, requested: str) -> Palette:
    """Aplica el tema a toda la aplicación (paleta Qt, hoja de estilos, barra de título), sin reiniciar."""
    global _current, _mode
    from .styles import build_stylesheet  # evita import circular

    _mode = _LEGACY.get(requested, requested) if valid(requested) else MODE_AUTO
    _current = resolve(_mode)
    hints = app.styleHints()
    # La barra de título de Windows sigue a colorScheme; en «auto» se deja al sistema.
    try:
        scheme = Qt.ColorScheme.Unknown if _mode == MODE_AUTO else (
            Qt.ColorScheme.Dark if _current.dark else Qt.ColorScheme.Light
        )
        hints.setColorScheme(scheme)
    except AttributeError:  # Qt anterior a 6.8
        pass
    app.setPalette(_qt_palette(_current))
    app.setStyleSheet(build_stylesheet(_current))
    for callback in list(_listeners):
        callback()
    return _current


def _qt_palette(p: Palette) -> QPalette:
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: p.bg,
        QPalette.ColorRole.WindowText: p.text,
        QPalette.ColorRole.Base: p.elevated,
        QPalette.ColorRole.AlternateBase: p.row_alt,
        QPalette.ColorRole.ToolTipBase: p.elevated,
        QPalette.ColorRole.ToolTipText: p.text,
        QPalette.ColorRole.PlaceholderText: p.muted,
        QPalette.ColorRole.Text: p.text,
        QPalette.ColorRole.Button: p.elevated,
        QPalette.ColorRole.ButtonText: p.text,
        QPalette.ColorRole.BrightText: p.on_accent,
        QPalette.ColorRole.Highlight: p.accent,
        QPalette.ColorRole.HighlightedText: p.on_accent,
        QPalette.ColorRole.Link: p.accent_text,
        QPalette.ColorRole.LinkVisited: p.accent_text,
        QPalette.ColorRole.Light: p.hover,
        QPalette.ColorRole.Midlight: p.border,
        QPalette.ColorRole.Mid: p.border,
        QPalette.ColorRole.Dark: p.sidebar,
        QPalette.ColorRole.Shadow: "#000000",
    }
    for role, value in roles.items():
        pal.setColor(role, QColor(value))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(p.faint))
    return pal
