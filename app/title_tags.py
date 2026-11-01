"""Graba en los archivos el título sin los caracteres especiales del principio (solo la etiqueta del título).

- Solo se toca la etiqueta: ni el sonido, ni el nombre del archivo, ni su fecha de modificación.
- Se trabaja sobre una copia junto al archivo, se verifica y recién entonces reemplaza al original de una vez:
  un corte de luz o un disco lleno dejan el archivo como estaba.
- El título original se anota antes de cambiar nada, para poder deshacerlo desde el Historial.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import mutagen
from mutagen import MutagenError
from mutagen.apev2 import APEv2
from mutagen.asf import ASFTags
from mutagen.id3 import ID3, TIT2
from mutagen.mp4 import MP4Tags
from PySide6.QtCore import QObject, Signal, Slot

from . import journal
from .config import UNTAGGED_EXTENSIONS
from .metadata import MetadataError, read_metadata
from .utils import clean_title, long_path

log = logging.getLogger(__name__)

_LENGTH_MARGIN = 0.05  # segundos: la duración debe seguir igual tras escribir la etiqueta
_WRITE_ERRORS = (OSError, ValueError, MutagenError)


class CannotTag(Exception):
    """El formato no admite etiquetas que el programa pueda escribir: no es un fallo, se deja como está."""


@dataclass
class TitleChange:
    track_id: int
    path: str
    original: str | None  # None: el archivo no tenía etiqueta de título
    written: str
    undone: bool = False


@dataclass
class TitleSession:
    id: str
    created_at: str
    status: str
    changes: list[TitleChange] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return sessions_dir() / f"titulos-{self.id}.json"

    def save(self) -> None:
        journal.write_atomic(self.path, asdict(self))

    @staticmethod
    def load(path: Path) -> "TitleSession":
        data = journal.read(path)
        data["changes"] = [TitleChange(**c) for c in data.get("changes", [])]
        return TitleSession(**data)

    def pending(self) -> list[TitleChange]:
        """Cambios que se pueden deshacer: el archivo sigue ahí con el título que grabó el programa."""
        return [c for c in self.changes if not c.undone and _current_title(c.path) == c.written]


def sessions_dir() -> Path:
    return journal.journal_dir("titulos")


def list_sessions() -> list[TitleSession]:
    return journal.load_all(sessions_dir(), "titulos-*.json", TitleSession.load)


def _current_title(path: str) -> str | None:
    try:
        meta = read_metadata(path)
    except (MetadataError, OSError):
        return None
    return meta.title if meta.has_title_tag else None


def clean_title_for(path: str) -> tuple[str | None, str] | None:
    """(título en la etiqueta o None si no tiene, título limpio) si hay que grabarlo; None si no hace falta."""
    if os.path.splitext(path)[1].lower() in UNTAGGED_EXTENSIONS:
        return None
    try:
        meta = read_metadata(path)
    except (MetadataError, OSError):
        return None  # dañado o inaccesible: aquí no hay nada que limpiar
    cleaned = clean_title(meta.title)
    if cleaned == meta.title:
        return None
    return (meta.title if meta.has_title_tag else None), cleaned


def _set_title_tag(path: str, title: str | None) -> None:
    """Cambia solo la etiqueta del título del archivo. `title` None la quita."""
    try:
        audio = mutagen.File(path)
    except Exception as exc:
        raise CannotTag(str(exc)) from exc
    if audio is None:
        raise CannotTag("formato no reconocido")
    if audio.tags is None:
        if title is None:
            return
        try:
            audio.add_tags()
        except Exception as exc:
            raise CannotTag(str(exc)) from exc
    tags = audio.tags
    if isinstance(tags, ID3):
        tags.delall("TIT2")
        if title is not None:
            tags.add(TIT2(encoding=3, text=[title]))
        if tags.version[:2] == (2, 4):
            audio.save(v2_version=4)
        else:  # las versiones 2.2 y 2.3 quedan en 2.3, la que entienden todos
            tags.update_to_v23()
            audio.save(v2_version=3)
        return
    if isinstance(tags, MP4Tags):
        key = "\xa9nam"
    elif isinstance(tags, (ASFTags, APEv2)):
        key = "Title"
    else:
        key = "title"  # Vorbis Comment: FLAC, Ogg, Opus
    if title is None:
        if key in tags:
            del tags[key]
    else:
        tags[key] = [title]
    audio.save()


def write_title(path: str, title: str | None) -> None:
    """Graba el título de forma segura. Si no se pudo lanza un error y el original queda intacto."""
    source = long_path(path)
    if not os.access(source, os.W_OK):
        raise PermissionError("el archivo es de solo lectura")
    stem, ext = os.path.splitext(source)
    temp = f"{stem}.limpiando-titulo{ext}"
    before = os.stat(source)
    try:
        shutil.copy2(source, temp)
        _set_title_tag(temp, title)
        _verify(source, temp, title)
        os.utime(temp, ns=(before.st_atime_ns, before.st_mtime_ns))
        now = os.stat(source)
        if (now.st_mtime_ns, now.st_size) != (before.st_mtime_ns, before.st_size):
            raise OSError("el archivo cambió mientras se grababa el título")
        os.replace(temp, source)
    finally:
        if os.path.exists(temp):
            try:
                os.remove(temp)
            except OSError as exc:
                log.warning("No se pudo borrar el temporal %s: %s", temp, exc)


def _verify(source: str, temp: str, title: str | None) -> None:
    original, edited = mutagen.File(source), mutagen.File(temp)
    if edited is None or abs(edited.info.length - original.info.length) > _LENGTH_MARGIN:
        raise ValueError("la copia con el título nuevo no coincide con el original")
    if title is not None and read_metadata(temp).title != title:
        raise ValueError("la copia no quedó con el título nuevo")


def undo(session: TitleSession) -> tuple[int, list[str]]:
    """Devuelve a cada archivo el título que tenía. Si después se cambió por otro, no se toca."""
    restored, problems = 0, []
    for change in session.changes:
        if change.undone:
            continue
        name = os.path.basename(change.path)
        current = _current_title(change.path)
        if current == change.original:  # una sesión cortada a mitad: este no llegó a cambiar
            change.undone = True
            continue
        if current != change.written:
            problems.append(f"{name}: su título ya no es el que grabó el programa; no se tocó.")
            continue
        try:
            write_title(change.path, change.original)
        except (*_WRITE_ERRORS, CannotTag) as exc:
            problems.append(f"{name}: {exc}")
            continue
        change.undone = True
        restored += 1
        session.save()
    if all(c.undone for c in session.changes):
        session.status = journal.STATUS_UNDONE
    session.save()
    return restored, problems


class CleanTitleTagsWorker(QObject):
    """Revisa los archivos y graba los títulos limpios. Vive en su propio hilo."""

    finished = Signal(int, list)  # cuántos se grabaron, problemas

    def __init__(self, tracks: list[tuple[int, str]]) -> None:
        super().__init__()
        self._tracks = tracks
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        written, problems = 0, []
        try:
            written = self._run(problems)
        except Exception as exc:  # nunca dejar el hilo colgado: «terminado» se avisa siempre
            log.exception("Error inesperado al grabar los títulos")
            problems.append(str(exc))
        self.finished.emit(written, problems)

    def _run(self, problems: list[str]) -> int:
        session: TitleSession | None = None
        for track_id, path in self._tracks:
            if self._cancelled:
                break
            needed = clean_title_for(path)
            if needed is None:
                continue
            original, cleaned = needed
            if session is None:
                session = TitleSession(
                    journal.new_id(sessions_dir(), "titulos"),
                    datetime.now().isoformat(timespec="seconds"),
                    journal.STATUS_RUNNING,
                )
            change = TitleChange(track_id, path, original, cleaned)
            session.changes.append(change)
            session.save()  # el título original queda anotado antes de cambiar nada
            try:
                write_title(path, cleaned)
            except CannotTag as exc:
                log.info("Sin etiquetas que escribir en %s: %s", path, exc)
                session.changes.remove(change)
            except _WRITE_ERRORS as exc:
                log.warning("No se pudo grabar el título de %s: %s", path, exc)
                problems.append(f"{os.path.basename(path)}: {exc}")
                session.changes.remove(change)
        if session is None:
            return 0
        if session.changes:
            session.status = journal.STATUS_DONE
            session.save()
        else:
            session.path.unlink(missing_ok=True)
        return len(session.changes)
