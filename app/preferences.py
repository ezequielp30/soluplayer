"""Preferencias del usuario guardadas con QSettings."""

from __future__ import annotations

from PySide6.QtCore import QSettings


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
        from .ui.theme import valid

        value = str(self._s.value(self.THEME, "auto"))
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
