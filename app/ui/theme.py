"""Temas visuales: 9 paletas (5 oscuras y 4 claras) inspiradas en reproductores clásicos de Windows (Winamp,
jetAudio, AIMP, XMPlay, UltraPlayer), con fondos suaves, un acento propio y una «pantalla» tipo LCD.

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
    lcd_bg: str  # «pantalla» de la canción actual, como el visor de los reproductores clásicos
    lcd_text: str  # título en la pantalla (≥ 7:1 sobre lcd_bg)
    lcd_muted: str  # artista y tiempos en la pantalla (≥ 4.5:1)


# Reglas comunes (las comprueba tests/theme_contrast_test.py): fondos casi neutros con un acento propio;
# texto ≥ 7:1; texto secundario, acento como texto y títulos de sección ≥ 4.5:1; texto sobre el acento
# ≥ 4.5:1. Los tres colores de sección se separan en el círculo cromático y se alejan del acento.

GRAPHITE = Palette(
    name="Grafito", dark=True,
    bg="#1e2023", sidebar="#18191c", bar="#232529", elevated="#292b30", border="#35383e", hover="#2e3136",
    row_alt="#212327", text="#d8dee6", muted="#9aa3ad", faint="#5f656e",
    accent="#e8a24a", accent_hover="#f0b46a", accent_text="#e8a858", accent_soft="#40362a", on_accent="#1e1405",
    warning="#f0a07a", warning_soft="#3b322f", success="#7cc99a", danger="#ec7f7f", cover_a="#30333a", cover_b="#212327",
    sec_library="#8fb8dc", sec_playlists="#d9a0bf", sec_folders="#8fcfaa",
    lcd_bg="#111416", lcd_text="#9fe0a8", lcd_muted="#78a882",
)

CRIMSON = Palette(
    name="Carmesí", dark=True,
    bg="#1c1a1b", sidebar="#151314", bar="#211e20", elevated="#282426", border="#383033", hover="#2e292b",
    row_alt="#1f1c1e", text="#e6dcdc", muted="#ab9d9f", faint="#66595c",
    accent="#d9534f", accent_hover="#e46d69", accent_text="#ec7a74", accent_soft="#3c2424", on_accent="#1a0605",
    warning="#f0a070", warning_soft="#3a2d27", success="#7cc99a", danger="#f08c8c", cover_a="#3a2c2e", cover_b="#231d1f",
    sec_library="#8fb3d9", sec_playlists="#c5a8e8", sec_folders="#e3c27a",
    lcd_bg="#0e0b0b", lcd_text="#f2766b", lcd_muted="#b3685f",
)

STEEL = Palette(
    name="Acero", dark=True,
    bg="#182022", sidebar="#12191a", bar="#1d2628", elevated="#232d30", border="#303c3f", hover="#283336",
    row_alt="#1b2325", text="#d9e4e4", muted="#98aaab", faint="#5a6a6c",
    accent="#4cc3b5", accent_hover="#6fd3c7", accent_text="#5ccdbf", accent_soft="#213c3b", on_accent="#052421",
    warning="#f0a878", warning_soft="#36332e", success="#8fd6a0", danger="#ee8a8a", cover_a="#2a3739", cover_b="#1c2527",
    sec_library="#93b5e8", sec_playlists="#e3a3c0", sec_folders="#e6c77a",
    lcd_bg="#0b1819", lcd_text="#7fe6d6", lcd_muted="#5fa89d",
)

MIDNIGHT = Palette(
    name="Medianoche", dark=True,
    bg="#191b24", sidebar="#13151c", bar="#1e212b", elevated="#242735", border="#2f3345", hover="#282c3d",
    row_alt="#1c1e28", text="#c9cbd4", muted="#979cb3", faint="#5d6279",
    accent="#8d94f1", accent_hover="#a4a9f4", accent_text="#9ca2f3", accent_soft="#2d3047", on_accent="#0e1133",
    warning="#f1af81", warning_soft="#373031", success="#5fc9a1", danger="#f28a96", cover_a="#2f344b", cover_b="#202330",
    sec_library="#6ab7c6", sec_playlists="#df9cb9", sec_folders="#cfad6d",
    lcd_bg="#0b0d14", lcd_text="#b4b9ff", lcd_muted="#8a90c8",
)

HIGH_CONTRAST = Palette(
    name="Alto contraste", dark=True,
    bg="#000000", sidebar="#000000", bar="#0d0d0d", elevated="#161616", border="#8c8c8c", hover="#2b2b2b",
    row_alt="#0f0f0f", text="#ffffff", muted="#e0e0e0", faint="#9e9e9e",
    accent="#ffd60a", accent_hover="#ffe347", accent_text="#ffd60a", accent_soft="#4d4100", on_accent="#000000",
    warning="#ffb86b", warning_soft="#4a2a00", success="#7dffa8", danger="#ff8f8f", cover_a="#2b2b2b", cover_b="#161616",
    sec_library="#7fd8ff", sec_playlists="#ffa3d6", sec_folders="#8dffb4",
    lcd_bg="#000000", lcd_text="#ffd60a", lcd_muted="#e0e0e0",
)

ALUMINIUM = Palette(
    name="Aluminio", dark=False,
    bg="#eceef0", sidebar="#e1e4e8", bar="#e6e9ec", elevated="#f4f5f7", border="#cdd2d8", hover="#d8dce1",
    row_alt="#e5e8eb", text="#23262b", muted="#555b65", faint="#9aa0a9",
    accent="#cc6f18", accent_hover="#e8862a", accent_text="#984d00", accent_soft="#e9dcd0", on_accent="#1f1000",
    warning="#a8461f", warning_soft="#e5dddb", success="#287248", danger="#b23838", cover_a="#d9dde2", cover_b="#c5cad1",
    sec_library="#2e5c99", sec_playlists="#95386f", sec_folders="#2c674e",
    lcd_bg="#2a2d31", lcd_text="#ffad5c", lcd_muted="#c99a6a",
)

CHROME = Palette(
    name="Cromo", dark=False,
    bg="#eef1f4", sidebar="#e2e7ec", bar="#dde4ea", elevated="#f6f8fa", border="#c8d1da", hover="#d6dee6",
    row_alt="#e7ecf0", text="#1f2a36", muted="#4f5d6c", faint="#98a5b2",
    accent="#1f72ad", accent_hover="#1a6399", accent_text="#1e679e", accent_soft="#cfdee9", on_accent="#ffffff",
    warning="#a8461f", warning_soft="#e7e0df", success="#217246", danger="#b23838", cover_a="#d6e0ea", cover_b="#c1cfdd",
    sec_library="#4a46a8", sec_playlists="#9e3867", sec_folders="#27694d",
    lcd_bg="#9fd8ee", lcd_text="#0f2c4a", lcd_muted="#2a5578",
)

COBALT = Palette(
    name="Cobalto", dark=False,
    bg="#eceaf2", sidebar="#e0dde9", bar="#e4e1ed", elevated="#f4f3f8", border="#c9c5d8", hover="#d6d2e3",
    row_alt="#e6e3ee", text="#22203a", muted="#555170", faint="#9d99b3",
    accent="#3550c8", accent_hover="#2a42ad", accent_text="#2f47b8", accent_soft="#d1d3ec", on_accent="#ffffff",
    warning="#a3441e", warning_soft="#e5dadd", success="#276f46", danger="#ad3636", cover_a="#dcd9ea", cover_b="#c8c3dc",
    sec_library="#1a6076", sec_playlists="#943461", sec_folders="#725410",
    lcd_bg="#203c9c", lcd_text="#f2f5ff", lcd_muted="#bcc8f2",
)

SAND = Palette(
    name="Arena", dark=False,
    bg="#f5f2ed", sidebar="#ece5db", bar="#f1ece4", elevated="#f9f7f4", border="#e0d6ca", hover="#e5dbce",
    row_alt="#f0ebe3", text="#463d36", muted="#6a5a49", faint="#b4a592",
    accent="#a74b2c", accent_hover="#8c3e23", accent_text="#984326", accent_soft="#eadbd2", on_accent="#ffffff",
    warning="#9d5425", warning_soft="#ede4db", success="#407336", danger="#ad3439", cover_a="#e9decf", cover_b="#d9cbb5",
    sec_library="#405c8a", sec_playlists="#7c3d67", sec_folders="#415828",
    lcd_bg="#3a3128", lcd_text="#f5c27a", lcd_muted="#c9a070",
)

# Clave guardada en las preferencias → tema. «auto», «light» y «dark» se conservan por compatibilidad.
THEMES: dict[str, Palette] = {
    "grafito": GRAPHITE, "carmesi": CRIMSON, "acero": STEEL, "medianoche": MIDNIGHT, "alto_contraste": HIGH_CONTRAST,
    "aluminio": ALUMINIUM, "cromo": CHROME, "cobalto": COBALT, "arena": SAND,
}
# Temas retirados: quien los tenía elegidos pasa al más parecido.
_LEGACY = {
    "neon": "medianoche", "vumetro": "acero", "aurora": "acero", "vino": "carmesi", "oceano": "cromo",
    "lavanda": "cobalto",
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


def canonical(key: str) -> str:
    """Clave vigente de un tema (las de temas retirados pasan al que los reemplaza)."""
    return _LEGACY.get(key, key)


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
