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
    if requested == MODE_DARK:
        return GRAPHITE
    if requested == MODE_LIGHT:
        return ALUMINIUM
    return GRAPHITE if system_is_dark() else ALUMINIUM


def apply(app, requested: str) -> Palette:
    """Aplica el tema a toda la aplicación (paleta Qt, hoja de estilos, barra de título)."""
    global _current, _mode
    from .styles import build_stylesheet  # evita import circular

    _mode = requested if requested in MODES else MODE_AUTO
    hints = app.styleHints()
    # La barra de título de Windows sigue a colorScheme; en «auto» se deja al sistema.
    try:
        hints.setColorScheme(
            {MODE_DARK: Qt.ColorScheme.Dark, MODE_LIGHT: Qt.ColorScheme.Light}.get(_mode, Qt.ColorScheme.Unknown)
        )
    except AttributeError:  # Qt anterior a 6.8
        pass
    _current = resolve(_mode)
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
