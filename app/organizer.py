"""Organizador de MP3, sin ventanas: qué archivos examinar. Nada de este módulo modifica la música."""

from __future__ import annotations

import os
from typing import Callable, Iterable, Iterator

from .file_locator import _SKIPPED_FOLDERS as SYSTEM_FOLDERS
from .importer import SKIPPED_FOLDERS as PROGRAM_FOLDERS

PENDING_FOLDER = "PENDIENTES_REVISION"
BACKUP_FOLDER = "RESPALDOS_MP3"
_SKIPPED = frozenset(SYSTEM_FOLDERS) | frozenset(PROGRAM_FOLDERS) | {PENDING_FOLDER.casefold(), BACKUP_FOLDER.casefold()}


def collect_mp3(
    roots: Iterable[str], cancelled: Callable[[], bool] = lambda: False, on_problem: Callable[[str, OSError], None] | None = None,
) -> Iterator[tuple[str, int, int]]:
    """Da (ruta, tamaño, fecha) de cada MP3 bajo estas carpetas o unidades, sin repetir carpetas si las raíces se
    solapan. Sirve para colecciones enormes: no carga la lista completa en memoria y no sigue enlaces. Una carpeta o
    un archivo sin permiso se avisa y se sigue con el resto."""
    seen: set[str] = set()
    pending = list(reversed(list(roots)))
    while pending and not cancelled():
        folder = pending.pop()
        key = os.path.normcase(os.path.abspath(folder))
        if key in seen:
            continue
        seen.add(key)
        try:
            with os.scandir(folder) as scan:
                entries = sorted(scan, key=lambda e: e.name.casefold())
        except OSError as exc:
            if on_problem is not None:
                on_problem(folder, exc)
            continue
        below = []
        for entry in entries:
            if cancelled():
                return
            try:
                if entry.is_dir(follow_symlinks=False):
                    if not entry.is_junction() and entry.name.casefold() not in _SKIPPED:
                        below.append(entry.path)
                elif entry.is_file(follow_symlinks=False) and os.path.splitext(entry.name)[1].lower() == ".mp3":
                    info = entry.stat()
                    yield entry.path, info.st_size, info.st_mtime_ns
            except OSError as exc:
                if on_problem is not None:
                    on_problem(entry.path, exc)
        pending.extend(reversed(below))
