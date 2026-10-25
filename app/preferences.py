"""Preferencias del usuario guardadas con QSettings."""

from __future__ import annotations

import json

import math

from PySide6.QtCore import QSettings


def _number(value, default: float, low: float = -24.0, high: float = 24.0) -> float:
    """Número leído de las preferencias; si está dañado vuelve al de fábrica."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(high, max(low, number)) if math.isfinite(number) else default


def _gains(values) -> list[float]:
    values = values if isinstance(values, list) else []
    return [_number(g, 0.0) for g in values[:10]] + [0.0] * (10 - len(values[:10]))


class Preferences:
    ASK_TITLES = "preferences/ask_titles_on_import"
    DETECT_ARTIST = "preferences/detect_artist_in_filename"

    def __init__(self, settings: QSettings) -> None:
        self._s = settings

    @property
    def ask_titles_on_import(self) -> bool:
        """Al importar, preguntar si se completan los títulos de canciones sin título."""
        return self._s.value(self.ASK_TITLES, False, type=bool)

    @ask_titles_on_import.setter
    def ask_titles_on_import(self, value: bool) -> None:
        self._s.setValue(self.ASK_TITLES, bool(value))

    ONLINE_SOURCES = "preferences/online_sources"
    ONLINE_COVERS = "preferences/online_covers"

    @property
    def online_sources(self) -> list[str]:
        """Bases de datos en internet marcadas por defecto."""
        from .online_lookup import DEFAULT_SOURCES, SOURCES

        value = self._s.value(self.ONLINE_SOURCES, ",".join(DEFAULT_SOURCES))
        keys = [k for k in str(value).split(",") if k in SOURCES]
        return keys or list(DEFAULT_SOURCES)

    @online_sources.setter
    def online_sources(self, keys: list[str]) -> None:
        self._s.setValue(self.ONLINE_SOURCES, ",".join(keys))

    @property
    def online_covers(self) -> bool:
        return self._s.value(self.ONLINE_COVERS, True, type=bool)

    @online_covers.setter
    def online_covers(self, value: bool) -> None:
        self._s.setValue(self.ONLINE_COVERS, bool(value))

    THEME = "preferences/theme"

    @property
    def theme(self) -> str:
        """'auto' (sigue a Windows), 'light', 'dark' o la clave de un tema (p. ej. 'medianoche')."""
        from .ui.theme import canonical, valid

        # Un tema retirado se lee como el que lo reemplaza: Preferencias lo muestra marcado y, al
        # guardar, no se cambia a «Automático».
        value = canonical(str(self._s.value(self.THEME, "auto")))
        return value if valid(value) else "auto"

    @theme.setter
    def theme(self, value: str) -> None:
        self._s.setValue(self.THEME, value)

    @property
    def detect_artist_in_filename(self) -> bool:
        """Proponer el artista si el nombre tiene la forma «Artista - Título»."""
        return self._s.value(self.DETECT_ARTIST, True, type=bool)

    @detect_artist_in_filename.setter
    def detect_artist_in_filename(self, value: bool) -> None:
        self._s.setValue(self.DETECT_ARTIST, bool(value))

    REMOVE_MISSING = "preferences/remove_missing_on_start"

    @property
    def remove_missing_on_start(self) -> bool:
        """Al abrir, quitar de la biblioteca las canciones cuyo archivo ya no existe (con protecciones)."""
        return self._s.value(self.REMOVE_MISSING, True, type=bool)

    @remove_missing_on_start.setter
    def remove_missing_on_start(self, value: bool) -> None:
        self._s.setValue(self.REMOVE_MISSING, bool(value))

    MEDIA_KEYS = "preferences/global_media_keys"

    @property
    def global_media_keys(self) -> bool:
        """Las teclas multimedia del teclado manejan el reproductor aunque la ventana esté minimizada."""
        return self._s.value(self.MEDIA_KEYS, True, type=bool)

    @global_media_keys.setter
    def global_media_keys(self, value: bool) -> None:
        self._s.setValue(self.MEDIA_KEYS, bool(value))

    # ------------------------------------------------------------------ ecualizador

    EQ = "equalizer/state"

    def equalizer(self) -> dict:
        """{'enabled', 'preset', 'gains', 'preamp', 'prevent_clipping', 'custom': {nombre: {gains, preamp}}}"""
        default = {"enabled": False, "preset": "Normal", "gains": [0.0] * 10, "preamp": 0.0,
                   "prevent_clipping": True, "custom": {}}
        try:
            data = json.loads(str(self._s.value(self.EQ, "")) or "{}")
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        state = {**default, **{k: v for k, v in data.items() if k in default}}
        # Un valor dañado en el registro de Windows vuelve al de fábrica (antes impedía abrir el programa).
        state["gains"] = _gains(state["gains"])
        state["preamp"] = _number(state["preamp"], 0.0)
        state["enabled"] = bool(state["enabled"])
        state["prevent_clipping"] = bool(state["prevent_clipping"])
        state["preset"] = str(state["preset"])
        custom = state["custom"] if isinstance(state["custom"], dict) else {}
        state["custom"] = {
            str(name): {"gains": _gains(p.get("gains")), "preamp": _number(p.get("preamp"), 0.0)}
            for name, p in custom.items() if isinstance(p, dict)
        }
        return state

    def set_equalizer(self, state: dict) -> None:
        self._s.setValue(self.EQ, json.dumps(state, ensure_ascii=False))
