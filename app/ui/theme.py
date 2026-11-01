"""Temas visuales: 10 paletas modernas (6 oscuras y 4 claras) de superficies neutras y un solo acento por tema.

Ónix (oscuro) y Nieve (claro) son los de «auto», que sigue el tema claro/oscuro de Windows.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

MODE_AUTO, MODE_LIGHT, MODE_DARK = "auto", "light", "dark"
MODES = (MODE_AUTO, MODE_LIGHT, MODE_DARK)
_DWMWA_CAPTION_COLOR = 35


@dataclass(frozen=True)
class Palette:
    name: str
    dark: bool
    bg: str  # panel principal
    sidebar: str  # barra lateral y barra de menús
    bar: str  # barra del reproductor
    elevated: str  # tarjeta de la canción actual, menús, campos
    border: str
    hover: str
    row_alt: str  # igual al fondo: las listas no llevan rayas
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


# Reglas comunes (las comprueba tests/theme_contrast_test.py): superficies neutras teñidas apenas con el color del
# tema y un solo acento; texto ≥ 7:1, pero sin blanco ni negro puros (más descansado); texto secundario y acento
# como texto ≥ 4.5:1; texto sobre el acento ≥ 4.5:1.

_ON_DARK = {"warning": "#f5b06b", "warning_soft": "#3a2f22", "success": "#5fd39a", "danger": "#ff8f8f"}
_ON_LIGHT = {"warning": "#a14a14", "warning_soft": "#fbeedc", "success": "#1c7a4a", "danger": "#c02a2a"}

ONYX = Palette(
    name="Ónix", dark=True,
    bg="#16181d", sidebar="#101216", bar="#16181d", elevated="#20232a", border="#2b2f38", hover="#242830", row_alt="#16181d",
    text="#e4e7ec", muted="#98a0ae", faint="#5d6472",
    accent="#5b9dff", accent_hover="#7cb1ff", accent_text="#7ab0ff", accent_soft="#1f2f49", on_accent="#07152b",
    cover_a="#2b2f38", cover_b="#1b1e24", **_ON_DARK,
)

MIDNIGHT = Palette(
    name="Medianoche", dark=True,
    bg="#14162b", sidebar="#0e1022", bar="#14162b", elevated="#1e2140", border="#2a2e52", hover="#22254a", row_alt="#14162b",
    text="#e2e4f2", muted="#9da1c4", faint="#5d618a",
    accent="#8f8bff", accent_hover="#a8a5ff", accent_text="#a5a2ff", accent_soft="#2b2a5c", on_accent="#0e0c33",
    cover_a="#2a2e52", cover_b="#191c36", **_ON_DARK,
)

EMERALD = Palette(
    name="Esmeralda", dark=True,
    bg="#121a18", sidebar="#0c1311", bar="#121a18", elevated="#1b2623", border="#27352f", hover="#202d29", row_alt="#121a18",
    text="#e1ebe7", muted="#93a8a1", faint="#587067",
    accent="#2fd6a3", accent_hover="#55e2b7", accent_text="#4fdcb1", accent_soft="#173a30", on_accent="#03241a",
    cover_a="#27352f", cover_b="#16201d", **_ON_DARK,
)

RUBY = Palette(
    name="Rubí", dark=True,
    bg="#1a1518", sidebar="#130f11", bar="#1a1518", elevated="#251d21", border="#35292f", hover="#2b2227", row_alt="#1a1518",
    text="#eee4e7", muted="#ad9ca3", faint="#6e5c64",
    accent="#ff5f7e", accent_hover="#ff7f97", accent_text="#ff8097", accent_soft="#43202b", on_accent="#2b0510",
    cover_a="#35292f", cover_b="#201a1d", **_ON_DARK,
)

AMBER = Palette(
    name="Ámbar", dark=True,
    bg="#18171a", sidebar="#121114", bar="#18171a", elevated="#232125", border="#322f34", hover="#29272b", row_alt="#18171a",
    text="#ece8e2", muted="#a8a29a", faint="#6a655e",
    accent="#f7b23b", accent_hover="#fac45f", accent_text="#f8bd57", accent_soft="#3b2f18", on_accent="#241803",
    cover_a="#322f34", cover_b="#1e1c20", **_ON_DARK,
)

HIGH_CONTRAST = Palette(
    name="Alto contraste", dark=True,
    bg="#000000", sidebar="#000000", bar="#000000", elevated="#161616", border="#8c8c8c", hover="#2b2b2b", row_alt="#000000",
    text="#ffffff", muted="#e0e0e0", faint="#9e9e9e",
    accent="#ffd60a", accent_hover="#ffe347", accent_text="#ffd60a", accent_soft="#4d4100", on_accent="#000000",
    warning="#ffb86b", warning_soft="#4a2a00", success="#7dffa8", danger="#ff8f8f", cover_a="#2b2b2b", cover_b="#161616",
)

SNOW = Palette(
    name="Nieve", dark=False,
    bg="#f7f8fa", sidebar="#eef0f4", bar="#f7f8fa", elevated="#ffffff", border="#dfe2e8", hover="#e9ebf0", row_alt="#f7f8fa",
    text="#262b33", muted="#596170", faint="#a0a7b3",
    accent="#2563eb", accent_hover="#1d4fd1", accent_text="#1f56d0", accent_soft="#dfe9fd", on_accent="#ffffff",
    cover_a="#e3e6ec", cover_b="#d2d6de", **_ON_LIGHT,
)

PEARL = Palette(
    name="Perla", dark=False,
    bg="#faf8f7", sidebar="#f2eeec", bar="#faf8f7", elevated="#fffefd", border="#e7e1de", hover="#efeae7", row_alt="#faf8f7",
    text="#2d2628", muted="#675a5e", faint="#aea3a6",
    accent="#d42c5c", accent_hover="#b72249", accent_text="#bd2450", accent_soft="#fae1e7", on_accent="#ffffff",
    cover_a="#ece6e3", cover_b="#dcd3cf", **_ON_LIGHT,
)

MINT = Palette(
    name="Menta", dark=False,
    bg="#f6faf8", sidebar="#ebf2ef", bar="#f6faf8", elevated="#fdfefe", border="#dae5e0", hover="#e6efeb", row_alt="#f6faf8",
    text="#1f2c28", muted="#52645d", faint="#9aaca5",
    accent="#0a7d63", accent_hover="#086a54", accent_text="#086e57", accent_soft="#d6efe6", on_accent="#ffffff",
    cover_a="#dfe9e5", cover_b="#cddad5", **_ON_LIGHT,
)

LAVENDER = Palette(
    name="Lavanda", dark=False,
    bg="#f8f7fc", sidebar="#efedf7", bar="#f8f7fc", elevated="#fefeff", border="#e1deee", hover="#eae8f4", row_alt="#f8f7fc",
    text="#26233a", muted="#5d5a75", faint="#a3a0b8",
    accent="#5b45d6", accent_hover="#4c38bd", accent_text="#4e3ac4", accent_soft="#e5e1fa", on_accent="#ffffff",
    cover_a="#e4e1f0", cover_b="#d3cfe4", **_ON_LIGHT,
)

# Clave guardada en las preferencias → tema. «auto», «light» y «dark» se conservan por compatibilidad.
THEMES: dict[str, Palette] = {
    "onix": ONYX, "medianoche": MIDNIGHT, "esmeralda": EMERALD, "rubi": RUBY, "ambar": AMBER, "alto_contraste": HIGH_CONTRAST,
    "nieve": SNOW, "perla": PEARL, "menta": MINT, "lavanda": LAVENDER,
}
# Temas retirados: quien los tenía elegidos pasa al más parecido.
_LEGACY = {
    "grafito": "ambar", "carmesi": "rubi", "acero": "esmeralda", "aluminio": "nieve", "cromo": "nieve", "cobalto": "lavanda",
    "arena": "perla", "neon": "medianoche", "vumetro": "esmeralda", "aurora": "esmeralda", "vino": "rubi", "oceano": "nieve",
}

_current: Palette = SNOW
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
        return ONYX
    if requested == MODE_LIGHT:
        return SNOW
    return ONYX if system_is_dark() else SNOW


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
    for window in app.topLevelWidgets():
        if window.isVisible():
            tint_title_bar(window)
    return _current


def tint_title_bar(window) -> None:
    """Windows 11: la barra de título con el color de la barra de menús. En otras versiones no hace nada."""
    if sys.platform != "win32" or QGuiApplication.platformName() != "windows":
        return
    import ctypes

    rgb = QColor(_current.sidebar)
    value = ctypes.c_int(rgb.red() | rgb.green() << 8 | rgb.blue() << 16)
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute(int(window.winId()), _DWMWA_CAPTION_COLOR, ctypes.byref(value), ctypes.sizeof(value))
    except OSError:
        pass  # sin el servicio de ventanas: se queda con la barra normal


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
