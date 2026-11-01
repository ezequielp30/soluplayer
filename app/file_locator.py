"""Busca el archivo de una canción que ya no está donde se guardó. Solo mira: no cambia nada.

Se busca primero cerca (su carpeta, las carpetas de la biblioteca, las carpetas personales) y después en todos los
discos. Un archivo sirve si su nombre o el título de su etiqueta dicen lo mismo que la canción, y además dura lo
mismo. Nunca se ofrece un archivo que ya es de otra canción de la biblioteca.
"""

from __future__ import annotations

import logging
import os
import re
import string
import sys
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QObject, Signal, Slot

from .config import SUPPORTED_EXTENSIONS
from .metadata import MetadataError, read_metadata
from .models import Track
from .title_format import strip_noise
from .utils import normalize_text, path_key

log = logging.getLogger(__name__)

DURATION_MARGIN_MS = 2000
_DRIVE_REMOVABLE, _DRIVE_FIXED = 2, 3  # las unidades de red y los CD pueden tardar minutos en responder
_SKIPPED_FOLDERS = frozenset({
    "$recycle.bin", "system volume information", "$winreagent", "windows", "program files", "program files (x86)",
    "programdata", "appdata", "node_modules", "__pycache__", ".git", ".venv",
})


def _key(text: str) -> str:
    """Para comparar nombres: sin lo que agrega YouTube, signos, numeración, tildes ni mayúsculas."""
    return " ".join(re.sub(r"[\W_]+", " ", normalize_text(strip_noise(text))).split())


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def wanted_names(track: Track) -> set[str]:
    return {name for name in (_key(_stem(track.path)), _key(track.title)) if name}


def matches(path: str, names: set[str], duration_ms: int) -> bool:
    """¿Es este archivo la canción? Su nombre o el título de su etiqueta, y su duración."""
    try:
        meta = read_metadata(path)
    except (MetadataError, OSError):
        return False
    if _key(_stem(path)) not in names and not (meta.has_title_tag and _key(meta.title) in names):
        return False
    return not duration_ms or abs(meta.duration_ms - duration_ms) <= DURATION_MARGIN_MS


def _local_drives() -> list[str]:
    if sys.platform != "win32":
        return ["/"]
    import ctypes

    drives = [f"{letter}:\\" for letter in string.ascii_uppercase]
    return [d for d in drives if ctypes.windll.kernel32.GetDriveTypeW(d) in (_DRIVE_REMOVABLE, _DRIVE_FIXED)]


def search_tiers(track: Track, library: Iterable[Track]) -> list[list[str]]:
    """Dónde buscar, de lo más probable a lo menos. En cuanto un nivel da resultado, no se sigue."""
    home = Path.home()
    personal = [str(home / name) for name in ("Music", "Downloads", "Desktop", "Documents", "OneDrive")]
    return [
        [os.path.dirname(track.path), *sorted({os.path.dirname(t.path) for t in library})],
        personal,
        _local_drives(),
    ]


class FindFileWorker(QObject):
    """Recorre las carpetas en su propio hilo."""

    folder = Signal(str)  # dónde está buscando
    finished = Signal(list, bool)  # rutas encontradas, si se detuvo

    def __init__(self, track: Track, library: list[Track], tiers: list[list[str]]) -> None:
        super().__init__()
        self._names = wanted_names(track)
        self._duration = track.duration_ms
        self._taken = {path_key(t.path) for t in library}
        self._tiers = tiers
        self._seen: set[str] = set()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        found: list[str] = []
        try:
            for tier in self._tiers:
                for root in tier:
                    self._walk(root, found)
                if found or self._cancelled:
                    break
        except Exception:  # nunca dejar el hilo colgado: «terminado» se avisa siempre
            log.exception("Error inesperado al buscar el archivo")
        self.finished.emit(found, self._cancelled)

    def _walk(self, root: str, found: list[str]) -> None:
        pending = [root]
        while pending and not self._cancelled:
            folder = pending.pop()
            key = path_key(folder)
            if key in self._seen:
                continue
            self._seen.add(key)
            self.folder.emit(folder)
            try:
                with os.scandir(folder) as scan:
                    entries = list(scan)
            except OSError:
                continue  # sin permiso, o una carpeta que ya no existe
            for entry in entries:
                if self._cancelled:
                    return
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if not entry.is_junction() and entry.name.casefold() not in _SKIPPED_FOLDERS:
                            pending.append(entry.path)
                    elif (
                        os.path.splitext(entry.name)[1].lower() in SUPPORTED_EXTENSIONS
                        and path_key(entry.path) not in self._taken
                        and matches(entry.path, self._names, self._duration)
                    ):
                        found.append(entry.path)
                except OSError:
                    continue
