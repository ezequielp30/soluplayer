"""Búsqueda, validación y lectura de archivos de audio para importar.

Nunca mueve, renombra ni elimina archivos: solo los lee.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot

from .artwork import cover_hash, make_thumbnail
from .config import SUPPORTED_EXTENSIONS, UNTAGGED_EXTENSIONS
from .metadata import AudioMetadata, MetadataError, basic_metadata, read_metadata
from .utils import path_key


@dataclass
class ImportFailure:
    path: str
    reason: str
    corrupt: bool = False  # archivo de audio dañado o vacío (se puede ofrecer enviarlo a la papelera)


@dataclass
class ScannedTrack:
    path: str
    key: str
    metadata: AudioMetadata
    cover_bytes: bytes | None
    cover_hash: str | None


@dataclass
class ScanResult:
    tracks: list[ScannedTrack] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    failures: list[ImportFailure] = field(default_factory=list)
    ignored_count: int = 0  # archivos que no son de audio dentro de carpetas
    cancelled: bool = False


def supported_formats_text() -> str:
    return ", ".join(sorted(ext.lstrip(".").upper() for ext in SUPPORTED_EXTENSIONS))


def validate_audio_path(path: str) -> str | None:
    """Comprobaciones previas a leer el archivo. Devuelve el motivo del rechazo o None."""
    if not path:
        return "La ruta está vacía."
    if not os.path.exists(path):
        return "El archivo no existe (puede haberse movido o eliminado)."
    if not os.path.isfile(path):
        return "La ruta no es un archivo."
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        shown = ext or "sin extensión"
        return f"Formato no compatible ({shown}). Formatos admitidos: {supported_formats_text()}."
    if not os.access(path, os.R_OK):
        return "No hay permiso para leer el archivo."
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            handle.read(16)
    except PermissionError:
        return "No hay permiso para leer el archivo (puede estar bloqueado por otro programa)."
    except OSError as exc:
        return f"No se pudo abrir el archivo ({exc.strerror or exc})."
    if size == 0:
        return EMPTY_FILE_REASON
    return None


EMPTY_FILE_REASON = "El archivo está vacío (0 bytes)."


def scan_file(path: str) -> tuple[ScannedTrack | None, ImportFailure | None]:
    """Valida y lee un archivo. Devuelve (pista, None) o (None, fallo con su motivo)."""
    try:
        return _scan_file(path)
    except Exception as exc:  # un archivo raro nunca debe cortar la importación del resto
        return None, ImportFailure(path, f"No se pudo leer el archivo (error inesperado: {exc}).", corrupt=False)


# Cabeceras de WAV/AIFF válidos que mutagen no siempre entiende (RF64/BW64 de más de 4 GB, WAV «de
# streaming» con tamaños a 0): FFmpeg los reproduce, así que no son archivos dañados.
_RIFF_LIKE = (b"RIFF", b"RF64", b"BW64", b"FORM")


def _has_audio_container_header(path: str) -> bool:
    try:
        with open(path, "rb") as handle:
            head = handle.read(12)
    except OSError:
        return False
    return head[:4] in _RIFF_LIKE and head[8:12] in (b"WAVE", b"AIFF", b"AIFC")


def _scan_file(path: str) -> tuple[ScannedTrack | None, ImportFailure | None]:
    reason = validate_audio_path(path)
    if reason:
        return None, ImportFailure(path, reason, corrupt=reason == EMPTY_FILE_REASON)
    try:
        metadata = read_metadata(path)
    except MetadataError as exc:
        untagged = os.path.splitext(path)[1].lower() in UNTAGGED_EXTENSIONS
        if not exc.corrupt or not (untagged or _has_audio_container_header(path)):
            return None, ImportFailure(path, str(exc), corrupt=exc.corrupt)
        # Formato que FFmpeg reproduce pero cuyas etiquetas no se pueden leer: se importa igual.
        metadata = basic_metadata(path)
    thumb = make_thumbnail(metadata.cover) if metadata.cover else None
    # La carátula original (a veces varios MB) ya no se usa: soltarla evita que importar miles de
    # canciones llene la memoria (solo se conserva la miniatura).
    metadata.cover = None
    return (
        ScannedTrack(
            path=os.path.abspath(path),
            key=path_key(path),
            metadata=metadata,
            cover_bytes=thumb,
            cover_hash=cover_hash(thumb) if thumb else None,
        ),
        None,
    )


# Carpetas que crea el propio programa: reimportar la música no debe volver a meter los originales
# convertidos ni las copias reunidas como canciones nuevas (aparecerían como repetidas).
SKIPPED_FOLDERS = {"_originales convertidos", "_repetidas para revisar", "respaldos_mp3", "pendientes_revision"}


def in_skipped_folder(path: str) -> bool:
    """¿El archivo está dentro de una de esas carpetas? (también si se importa esa carpeta directamente o
    se arrastran sus archivos: si no, los originales se agruparían como «repetidas» de sus MP3 y
    «Repetidas → A la Papelera» propondría enviarlos)."""
    parts = os.path.normpath(os.path.abspath(path)).split(os.sep)[:-1]
    return any(part.casefold() in SKIPPED_FOLDERS for part in parts)


def collect_folder(
    folder: str, recursive: bool, cancelled: Callable[[], bool] | None = None
) -> tuple[list[str], list[ImportFailure], int]:
    """Lista los archivos de audio compatibles de una carpeta.

    Devuelve (archivos, errores de acceso, cantidad de archivos ignorados). `cancelled` permite
    detener el recorrido (en una unidad de red puede tardar mucho).
    """
    files: list[str] = []
    failures: list[ImportFailure] = []
    ignored = 0

    def on_error(exc: OSError) -> None:
        failures.append(
            ImportFailure(exc.filename or folder, f"No se pudo abrir la carpeta ({exc.strerror or exc}).")
        )

    for root, dirs, names in os.walk(folder, onerror=on_error):
        if cancelled is not None and cancelled():
            break
        dirs[:] = [d for d in dirs if d.casefold() not in SKIPPED_FOLDERS]
        dirs.sort(key=str.casefold)
        for name in sorted(names, key=str.casefold):
            if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
                files.append(os.path.join(root, name))
            else:
                ignored += 1
        if not recursive:
            break
    return files, failures, ignored


class ImportWorker(QObject):
    """Lee metadatos en un hilo aparte. Las escrituras en SQLite las hace el hilo principal."""

    progress = Signal(int, int, str)
    finished = Signal(object)  # ScanResult

    def __init__(
        self,
        known_keys: set[str],
        files: list[str] | None = None,
        folder: str | None = None,
        recursive: bool = False,
    ) -> None:
        super().__init__()
        self._known = set(known_keys)
        self._files = files or []
        self._folder = folder
        self._recursive = recursive
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        result = ScanResult()
        try:
            files = list(self._files)
            if self._folder:
                self.progress.emit(0, 0, "Buscando archivos de audio…")
                found, failures, ignored = collect_folder(self._folder, self._recursive, lambda: self._cancelled)
                files.extend(found)
                result.failures.extend(failures)
                result.ignored_count = ignored

            total = len(files)
            seen: set[str] = set()
            thumbs: dict[str, bytes] = {}  # una sola copia de cada miniatura (las de un mismo álbum se repiten)
            for index, path in enumerate(files):
                if self._cancelled:
                    result.cancelled = True
                    break
                self.progress.emit(index, total, os.path.basename(path))
                key = path_key(path)
                if key in self._known or key in seen:
                    result.duplicates.append(path)
                    continue
                seen.add(key)
                if in_skipped_folder(path):
                    result.failures.append(ImportFailure(
                        path, "Está en una carpeta del programa (originales convertidos o copias para revisar): no se importa.",
                    ))
                    continue
                track, failure = scan_file(path)
                if track:
                    if track.cover_hash:
                        track.cover_bytes = thumbs.setdefault(track.cover_hash, track.cover_bytes)
                    result.tracks.append(track)
                else:
                    result.failures.append(failure or ImportFailure(path, "Error desconocido."))
            else:
                self.progress.emit(total, total, "")
        except Exception as exc:  # no dejar el hilo colgado ante un error inesperado
            result.failures.append(ImportFailure(self._folder or "", f"Error inesperado: {exc}"))
        self.finished.emit(result)
