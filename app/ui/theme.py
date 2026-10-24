"""Temas visuales «Hi-Fi»: Grafito (oscuro) y Aluminio (claro), con acento ámbar.

El ámbar viene de la luz de los vúmetros de los equipos de música; el grafito y el
aluminio, de sus frontales. El modo «auto» sigue el tema claro/oscuro de Windows.
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
    accent: str  # relleno ámbar (botón reproducir, progreso)
    accent_hover: str
    accent_text: str  # ámbar usado como texto o icono sobre el fondo (≥ 4.5:1)
    accent_soft: str  # selección
    on_accent: str  # texto/icono sobre el relleno ámbar
    warning: str
    warning_soft: str
    success: str
    danger: str
    cover_a: str  # degradado de la carátula de reemplazo
    cover_b: str


GRAPHITE = Palette(
    name="Grafito",
    dark=True,
    bg="#17181c",
    sidebar="#111215",
    bar="#1c1d22",
    elevated="#23252b",
    border="#2e3038",
    hover="#2a2c33",
    row_alt="#1a1b20",
    text="#eceef1",
    muted="#a3a7b1",
    faint="#646873",
    accent="#f5a524",
    accent_hover="#ffb947",
    accent_text="#f7b548",
    accent_soft="#3a2f1a",
    on_accent="#1c1404",
    warning="#ff8a73",
    warning_soft="#3a221d",
    success="#5ccf95",
    danger="#ff6b6b",
    cover_a="#2b2d35",
    cover_b="#1f2026",
)

ALUMINIUM = Palette(
    name="Aluminio",
    dark=False,
    bg="#fbfbfc",
    sidebar="#f0f1f4",
    bar="#f6f7f9",
    elevated="#ffffff",
    border="#e1e3e8",
    hover="#e8e9ee",
    row_alt="#f5f6f8",
    text="#16171b",
    muted="#5c606b",
    faint="#a6aab3",
    accent="#eda21b",
    accent_hover="#f7b234",
    accent_text="#9a5a00",
    accent_soft="#fcecc9",
    on_accent="#2a1a00",
    warning="#b5381f",
    warning_soft="#fde9e4",
    success="#1d7a4c",
    danger="#c0322b",
    cover_a="#e7e8ec",
    cover_b="#d3d5db",
)

# ---------------------------------------------------------------------- temas adicionales
# Mismas reglas que Grafito y Aluminio: texto ≥ 7:1, texto secundario y acento usado como texto ≥ 4.5:1
# sobre el fondo, y texto sobre el relleno de acento ≥ 4.5:1 (lo comprueba tests/theme_contrast_test.py).

MIDNIGHT = Palette(
    name="Medianoche", dark=True,
    bg="#0f1524", sidebar="#0a0f1b", bar="#131a2c", elevated="#1a2236", border="#263049", hover="#1f2840",
    row_alt="#121a2b", text="#e8edf7", muted="#9aa6c0", faint="#56617a",
    accent="#38bdf8", accent_hover="#67d0fb", accent_text="#5cc8f9", accent_soft="#13324a", on_accent="#04121c",
    warning="#ff9a7a", warning_soft="#3a2420", success="#4ade9a", danger="#ff7a85", cover_a="#1f2a42", cover_b="#151d30",
)

AURORA = Palette(
    name="Aurora", dark=True,
    bg="#0e1a1a", sidebar="#0a1313", bar="#122020", elevated="#172828", border="#223a39", hover="#1c3130",
    row_alt="#112020", text="#e6f2f0", muted="#93b3ae", faint="#4f6c68",
    accent="#2dd4bf", accent_hover="#5ee3d2", accent_text="#4fdcc9", accent_soft="#12403a", on_accent="#03201c",
    warning="#ffa07a", warning_soft="#3a2620", success="#86efac", danger="#ff8080", cover_a="#1d3533", cover_b="#142625",
)

WINE = Palette(
    name="Vino", dark=True,
    bg="#1c1216", sidebar="#150d10", bar="#22161b", elevated="#2a1b21", border="#3d2730", hover="#33212a",
    row_alt="#20151a", text="#f4e9ec", muted="#c0a3ac", faint="#6e5560",
    accent="#f472b6", accent_hover="#f799c9", accent_text="#f78fc4", accent_soft="#4a1e33", on_accent="#2a0716",
    warning="#ffab7a", warning_soft="#3c2620", success="#6ee7b7", danger="#ff8a8a", cover_a="#3a2430", cover_b="#2a1a22",
)

NEON = Palette(
    name="Neón", dark=True,
    bg="#100b1c", sidebar="#0b0714", bar="#150f24", elevated="#1c142f", border="#2d2148", hover="#241a3b",
    row_alt="#130d22", text="#efe9ff", muted="#a99cc9", faint="#5d5079",
    accent="#c084fc", accent_hover="#d4a7fd", accent_text="#cb98fd", accent_soft="#3a2160", on_accent="#1a0733",
    warning="#ff9d7a", warning_soft="#3a2220", success="#5eead4", danger="#ff7aa2", cover_a="#2c2047", cover_b="#1d1431",
)

VU_GREEN = Palette(
    name="Vúmetro verde", dark=True,
    bg="#121411", sidebar="#0c0e0b", bar="#171a15", elevated="#1d211b", border="#2c3328", hover="#252a21",
    row_alt="#151813", text="#e9f0e4", muted="#a2b098", faint="#5c6655",
    accent="#a3e635", accent_hover="#bef264", accent_text="#b2ec55", accent_soft="#2e3d14", on_accent="#141f02",
    warning="#ffb067", warning_soft="#3a2a18", success="#86efac", danger="#ff7b6b", cover_a="#2a3124", cover_b="#1c2118",
)

HIGH_CONTRAST = Palette(
    name="Alto contraste", dark=True,
    bg="#000000", sidebar="#000000", bar="#0a0a0a", elevated="#141414", border="#5c5c5c", hover="#262626",
    row_alt="#0b0b0b", text="#ffffff", muted="#d6d6d6", faint="#8a8a8a",
    accent="#ffd60a", accent_hover="#ffe14d", accent_text="#ffd60a", accent_soft="#3d3300", on_accent="#000000",
    warning="#ffb36b", warning_soft="#3d2400", success="#7dffa8", danger="#ff8c8c", cover_a="#262626", cover_b="#141414",
)

OCEAN = Palette(
    name="Océano", dark=False,
    bg="#f7fafd", sidebar="#ebf1f8", bar="#f1f6fb", elevated="#ffffff", border="#d8e2ee", hover="#e1eaf4",
    row_alt="#f0f5fa", text="#0f1b2d", muted="#4c5d74", faint="#9fb0c4",
    accent="#0369a1", accent_hover="#075985", accent_text="#03669a", accent_soft="#d6effc", on_accent="#ffffff",
    warning="#b5381f", warning_soft="#fde9e4", success="#15803d", danger="#c0322b", cover_a="#dde8f3", cover_b="#c8d7e8",
)

SAND = Palette(
    name="Arena", dark=False,
    bg="#fcf9f4", sidebar="#f3ece1", bar="#f8f3eb", elevated="#ffffff", border="#e6dccd", hover="#ede4d6",
    row_alt="#f7f1e8", text="#2a1f14", muted="#6b5a47", faint="#b3a48f",
    accent="#c2410c", accent_hover="#9a3412", accent_text="#9c4520", accent_soft="#f9e0d3", on_accent="#ffffff",
    warning="#b5381f", warning_soft="#fde9e4", success="#3f7d3a", danger="#b8322a", cover_a="#efe5d6", cover_b="#e0d2bd",
)

LAVENDER = Palette(
    name="Lavanda", dark=False,
    bg="#fbfaff", sidebar="#f1eefb", bar="#f6f4fd", elevated="#ffffff", border="#e2ddf3", hover="#e9e4f8",
    row_alt="#f5f2fd", text="#1c1630", muted="#5b5275", faint="#aaa2c4",
    accent="#7c3aed", accent_hover="#6d28d9", accent_text="#6d3ee6", accent_soft="#ece4fe", on_accent="#ffffff",
    warning="#b5381f", warning_soft="#fde9e4", success="#1d7a4c", danger="#c0322b", cover_a="#e9e3fa", cover_b="#d8cff4",
)

# Clave guardada en las preferencias → tema. «auto», «light» y «dark» se conservan por compatibilidad.
THEMES: dict[str, Palette] = {
    "grafito": GRAPHITE, "aluminio": ALUMINIUM, "medianoche": MIDNIGHT, "aurora": AURORA, "vino": WINE,
    "neon": NEON, "vumetro": VU_GREEN, "alto_contraste": HIGH_CONTRAST, "oceano": OCEAN, "arena": SAND,
    "lavanda": LAVENDER,
}

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
    if requested in THEMES:
        return THEMES[requested]
    if requested == MODE_DARK:
        return GRAPHITE
    if requested == MODE_LIGHT:
        return ALUMINIUM
    return GRAPHITE if system_is_dark() else ALUMINIUM


def valid(requested: str) -> bool:
    return requested in MODES or requested in THEMES


def apply(app, requested: str) -> Palette:
    """Aplica el tema a toda la aplicación (paleta Qt, hoja de estilos, barra de título), sin reiniciar."""
    global _current, _mode
    from .styles import build_stylesheet  # evita import circular

    _mode = requested if valid(requested) else MODE_AUTO
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
