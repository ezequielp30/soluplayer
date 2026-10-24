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
    bg="#17181b", sidebar="#0f1012", bar="#1d1e22", elevated="#232529", border="#2e3035", hover="#282a2f",
    row_alt="#1a1b1e", text="#ededf0", muted="#a3a6ae", faint="#62656e",
    accent="#f5b14c", accent_hover="#f9c473", accent_text="#f5b14c", accent_soft="#3d3223", on_accent="#1f1402",
    warning="#ff9f6e", warning_soft="#3c2e28", success="#5fd49a", danger="#ff7070", cover_a="#2b2d33", cover_b="#1c1d21",
    sec_library="#7db8ff", sec_playlists="#f59bc2", sec_folders="#6fd6a4",
)

ALUMINIUM = Palette(
    name="Aluminio", dark=False,
    bg="#fafafb", sidebar="#f0f1f3", bar="#f5f6f7", elevated="#ffffff", border="#e1e3e7", hover="#e5e7eb",
    row_alt="#f4f5f7", text="#17181b", muted="#5b5f69", faint="#a6aab2",
    accent="#d97706", accent_hover="#ec8a12", accent_text="#a15800", accent_soft="#f4e4d1", on_accent="#1f1300",
    warning="#b4401c", warning_soft="#f3e7e5", success="#1c7a4b", danger="#c42b3a", cover_a="#e6e7eb", cover_b="#d2d4da",
    sec_library="#1c56b8", sec_playlists="#a01f6f", sec_folders="#106a4a",
)

MIDNIGHT = Palette(
    name="Medianoche", dark=True,
    bg="#13151e", sidebar="#0d0f16", bar="#181b26", elevated="#1e2130", border="#2a2e40", hover="#232738",
    row_alt="#161822", text="#eaecf6", muted="#a2a7bf", faint="#5d6279",
    accent="#8b93ff", accent_hover="#a5abff", accent_text="#9ca3ff", accent_soft="#2b2e4b", on_accent="#0e1133",
    warning="#ffad73", warning_soft="#392d2c", success="#52d6a4", danger="#ff7d8c", cover_a="#2a2f46", cover_b="#1a1d2b",
    sec_library="#5fd2e8", sec_playlists="#f7a0c6", sec_folders="#f2c062",
)

AURORA = Palette(
    name="Aurora", dark=True,
    bg="#121816", sidebar="#0c1110", bar="#171f1c", elevated="#1d2623", border="#29342f", hover="#222d29",
    row_alt="#151b19", text="#e8f0ec", muted="#9fb2ab", faint="#5a6b65",
    accent="#3ecf8e", accent_hover="#62dca4", accent_text="#4fd89b", accent_soft="#1a392c", on_accent="#032112",
    warning="#ffb070", warning_soft="#383024", success="#8ee6b4", danger="#ff8080", cover_a="#24332e", cover_b="#18201d",
    sec_library="#94b6ff", sec_playlists="#f7a3bb", sec_folders="#f0c46c",
)

WINE = Palette(
    name="Burdeos", dark=True,
    bg="#191416", sidebar="#120e10", bar="#1f191c", elevated="#261f22", border="#362b30", hover="#2d2428",
    row_alt="#1c1619", text="#f3ebee", muted="#b9a7ae", faint="#6d5c63",
    accent="#ff7d8e", accent_hover="#ff99a6", accent_text="#ff8d9c", accent_soft="#42272c", on_accent="#2b0911",
    warning="#ffb27a", warning_soft="#3e2d26", success="#6fdcae", danger="#ff8a7a", cover_a="#3a2a31", cover_b="#221a1e",
    sec_library="#7fd3d9", sec_playlists="#d6a8ff", sec_folders="#f2c66c",
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
    bg="#f8fafc", sidebar="#edf2f7", bar="#f2f6fa", elevated="#ffffff", border="#dae2eb", hover="#dfe7f0",
    row_alt="#f2f5f9", text="#0f1a2a", muted="#4a5a70", faint="#9dacbe",
    accent="#0067b8", accent_hover="#00579c", accent_text="#0062ad", accent_soft="#d3e4f2", on_accent="#ffffff",
    warning="#b4401c", warning_soft="#f1e7e6", success="#16794a", danger="#c42b3a", cover_a="#dce7f2", cover_b="#c5d5e6",
    sec_library="#5338b8", sec_playlists="#a8205a", sec_folders="#814d00",
)

SAND = Palette(
    name="Arena", dark=False,
    bg="#fbf8f3", sidebar="#f2ebe1", bar="#f7f2ea", elevated="#fffdfa", border="#e6dccf", hover="#ebe1d3",
    row_alt="#f6f1e9", text="#2a2018", muted="#6a5a49", faint="#b4a592",
    accent="#b5441e", accent_hover="#983817", accent_text="#a43d1a", accent_soft="#f0ddd3", on_accent="#ffffff",
    warning="#a8521a", warning_soft="#f3e7dd", success="#3d7a32", danger="#b8292f", cover_a="#efe4d4", cover_b="#dfd0ba",
    sec_library="#2a56a0", sec_playlists="#8f2a6e", sec_folders="#41661a",
)

LAVENDER = Palette(
    name="Lavanda", dark=False,
    bg="#fbfaff", sidebar="#f1eefa", bar="#f6f4fd", elevated="#ffffff", border="#e2ddf2", hover="#e7e2f6",
    row_alt="#f6f4fd", text="#1d1830", muted="#5c5475", faint="#aaa3c2",
    accent="#6847dc", accent_hover="#5735c7", accent_text="#5f3ed2", accent_soft="#e5dffa", on_accent="#ffffff",
    warning="#b4401c", warning_soft="#f4e7e8", success="#1c7a4b", danger="#c42b3a", cover_a="#e8e2fa", cover_b="#d6cdf2",
    sec_library="#09675f", sec_playlists="#ad2059", sec_folders="#7d4d00",
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
