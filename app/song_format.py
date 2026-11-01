"""Deja cada canción como «Canción - Quién la canta»: en el título, en el nombre del archivo y en sus etiquetas.

Los demás datos del archivo (álbum, género, año, comentarios y, si se pide, la carátula) se borran; las marcas
del programa no. En ID3 (MP3, WAV, AIFF) la etiqueta completa se guarda antes en el registro, así que se puede
deshacer todo. En los otros formatos solo cambian título y artista. El sonido no se toca (ver title_tags).
"""

from __future__ import annotations

import io
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import mutagen
from mutagen.asf import ASFTags
from mutagen.apev2 import APEv2
from mutagen.id3 import ID3, TIT2, TPE1
from mutagen.mp4 import MP4Tags
from PySide6.QtCore import QObject, Signal, Slot

from . import converter, file_manager, journal
from .metadata import UNKNOWN_ALBUM, UNKNOWN_GENRE, MetadataError, read_metadata
from .models import Track
from .review_folder import safe_name
from .title_tags import _WRITE_ERRORS, CannotTag, edit_safely
from .utils import clean_title, long_path

log = logging.getLogger(__name__)

NAME_LIMIT = 150  # caracteres del nombre de archivo: lejos del límite de Windows para la ruta completa
_DUPLICATE_MARK = re.compile(r" \(\d+\)$")  # «Canción - Cantante (2).mp3»: ya había otro archivo con ese nombre


@dataclass
class FormatChange:
    track_id: int
    old_path: str
    new_path: str
    old_title: str
    old_artist: str
    old_album: str
    old_genre: str
    old_cover: str | None
    new_title: str
    new_artist: str
    keep_cover: bool
    tag_version: int = 0  # 3 o 4: la etiqueta ID3 guardada aparte. 0: no había ID3
    tag_title: str | None = None  # los que no son ID3: lo que había en las etiquetas
    tag_artist: str | None = None
    done: bool = False
    undone: bool = False


@dataclass
class FormatSession:
    id: str
    created_at: str
    status: str
    changes: list[FormatChange] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return sessions_dir() / f"formato-{self.id}.json"

    def save(self) -> None:
        journal.write_atomic(self.path, asdict(self))

    @staticmethod
    def load(path: Path) -> "FormatSession":
        data = journal.read(path)
        data["changes"] = [FormatChange(**c) for c in data.get("changes", [])]
        return FormatSession(**data)

    def pending(self) -> list[FormatChange]:
        return [c for c in self.changes if c.done and not c.undone and os.path.exists(long_path(c.new_path))]

    def backup_file(self, change: FormatChange) -> Path:
        return sessions_dir() / f"formato-{self.id}-{change.track_id}.id3"


def sessions_dir() -> Path:
    return journal.journal_dir("formato")


def list_sessions() -> list[FormatSession]:
    return journal.load_all(sessions_dir(), "formato-*.json", FormatSession.load)


def new_session() -> FormatSession:
    return FormatSession(
        journal.new_id(sessions_dir(), "formato"), datetime.now().isoformat(timespec="seconds"), journal.STATUS_RUNNING
    )


def format_title(song: str, singer: str) -> str:
    return clean_title(f"{song.strip()} - {singer.strip()}")


def plan(track: Track, song: str, singer: str, keep_cover: bool) -> FormatChange:
    """`track` con el texto tal como está guardado (Database.with_raw_text)."""
    return FormatChange(
        track.id, track.path, track.path, track.title, track.artist, track.album, track.genre, track.cover_hash,
        format_title(song, singer), singer.strip(), keep_cover,
    )


def new_library_cover(change: FormatChange) -> str | None:
    return change.old_cover if change.keep_cover else None


def is_formatted(track: Track, song: str, singer: str) -> bool:
    """Ya no hay nada que cambiarle (para no listarla otra vez)."""
    title = format_title(song, singer)
    return (
        track.title == title and track.artist == singer.strip() and track.album == UNKNOWN_ALBUM
        and track.genre == UNKNOWN_GENRE and _DUPLICATE_MARK.sub("", _stem(track.path)) == _stem(_file_name(title, track.path))
    )


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _file_name(title: str, path: str) -> str:
    return safe_name(title.replace(" / ", ", ").replace("/", "-"), NAME_LIMIT) + os.path.splitext(path)[1]


def _target_path(path: str, title: str) -> str:
    """Nunca pisa otro archivo: si ya existe uno con ese nombre, «(2)», «(3)»…"""
    wanted = os.path.join(os.path.dirname(path), _file_name(title, path))
    stem, ext = os.path.splitext(wanted)
    candidate, n = wanted, 2
    while os.path.exists(long_path(candidate)) and os.path.normcase(candidate) != os.path.normcase(path):
        candidate, n = f"{stem} ({n}){ext}", n + 1
    return candidate


def _tag_keys(tags) -> tuple[str, str]:
    if isinstance(tags, MP4Tags):
        return "\xa9nam", "\xa9ART"
    if isinstance(tags, (ASFTags, APEv2)):
        return "Title", "Artist"
    return "title", "artist"  # Vorbis Comment: FLAC, Ogg, Opus


def _open(path: str):
    try:
        audio = mutagen.File(path)
    except Exception as exc:
        raise CannotTag(str(exc)) from exc
    if audio is None:
        raise CannotTag("formato no reconocido")
    if audio.tags is None:
        try:
            audio.add_tags()
        except Exception as exc:
            raise CannotTag(str(exc)) from exc
    return audio


def _save_id3(audio, version: int) -> None:
    if version == 4:
        audio.save(v2_version=4)
    else:
        audio.tags.update_to_v23()
        audio.save(v2_version=3)


def _remember_tags(session: FormatSession, change: FormatChange) -> None:
    """Guarda lo que hay en el archivo antes de cambiarlo."""
    try:
        audio = mutagen.File(long_path(change.old_path))
    except Exception:
        return
    tags = getattr(audio, "tags", None)
    if isinstance(tags, ID3):
        copy = ID3()
        for key, frame in tags.items():
            copy[key] = frame
        if len(copy):
            buffer = io.BytesIO()
            copy.save(buffer, v1=0, v2_version=4)
            session.backup_file(change).write_bytes(buffer.getvalue())
        change.tag_version = 4 if tags.version[:2] == (2, 4) else 3
    elif tags:
        title_key, artist_key = _tag_keys(tags)
        change.tag_title = str(tags[title_key][0]) if title_key in tags else None
        change.tag_artist = str(tags[artist_key][0]) if artist_key in tags else None


def _write_tags(path: str, change: FormatChange) -> None:
    audio = _open(path)
    tags = audio.tags
    if isinstance(tags, ID3):
        created = f"TXXX:{converter._CREATED_MARK}"
        for key in list(tags.keys()):
            if key != created and not (change.keep_cover and key.startswith("APIC")):
                del tags[key]
        tags.add(TIT2(encoding=3, text=[change.new_title]))
        tags.add(TPE1(encoding=3, text=[change.new_artist]))
        _save_id3(audio, 4 if tags.version[:2] == (2, 4) else 3)
        return
    title_key, artist_key = _tag_keys(tags)
    tags[title_key] = [change.new_title]
    tags[artist_key] = [change.new_artist]
    audio.save()


def _restore_tags(path: str, session: FormatSession, change: FormatChange) -> None:
    audio = _open(path)
    tags = audio.tags
    if isinstance(tags, ID3):
        for key in list(tags.keys()):
            del tags[key]
        backup = session.backup_file(change)
        if backup.exists():
            saved = ID3(io.BytesIO(backup.read_bytes()))
            for key, frame in saved.items():
                tags[key] = frame
        _save_id3(audio, change.tag_version or 4)
        return
    title_key, artist_key = _tag_keys(tags)
    for key, value in ((title_key, change.tag_title), (artist_key, change.tag_artist)):
        if value is not None:
            tags[key] = [value]
        elif key in tags:
            del tags[key]
    audio.save()


def apply(session: FormatSession, change: FormatChange) -> None:
    """Renombra y graba las etiquetas. Si algo falla, el archivo queda como estaba y se lanza el error.
    La biblioteca no se toca aquí: la actualiza el hilo principal."""
    _remember_tags(session, change)
    change.new_path = _target_path(change.old_path, change.new_title)
    session.changes.append(change)
    session.save()  # lo que había y a dónde va quedan anotados antes de cambiar nada
    renamed = change.new_path != change.old_path
    try:
        if renamed:
            os.rename(long_path(change.old_path), long_path(change.new_path))
        try:
            edit_safely(change.new_path, lambda temp: _write_tags(temp, change), change.new_title)
        except CannotTag as exc:
            log.info("Sin etiquetas que escribir en %s: %s", change.new_path, exc)
    except BaseException:
        if renamed and os.path.exists(long_path(change.new_path)) and not os.path.exists(long_path(change.old_path)):
            os.rename(long_path(change.new_path), long_path(change.old_path))
        session.changes.remove(change)
        session.backup_file(change).unlink(missing_ok=True)
        raise


def revert(session: FormatSession, change: FormatChange) -> None:
    """Devuelve el archivo a como estaba (nombre y etiquetas). No toca la biblioteca."""
    new, old = long_path(change.new_path), long_path(change.old_path)
    if not os.path.exists(new):
        raise FileNotFoundError("ya no está donde lo dejó el programa")
    renamed = change.new_path != change.old_path
    if renamed and os.path.exists(old) and os.path.normcase(old) != os.path.normcase(new):
        raise FileExistsError("ya hay otro archivo con su nombre original")
    if renamed:
        os.rename(new, old)
    try:
        edit_safely(change.old_path, lambda temp: _restore_tags(temp, session, change), None)
    except CannotTag as exc:
        log.info("Sin etiquetas que devolver en %s: %s", change.old_path, exc)
    except BaseException:
        if renamed:
            os.rename(old, new)
        raise


def undo(session: FormatSession, db) -> tuple[int, list[str]]:
    restored, problems = 0, []
    for change in session.changes:
        if change.undone or not change.done:
            continue
        name = os.path.basename(change.new_path)
        try:
            meta = read_metadata(change.new_path)
        except (MetadataError, OSError):
            problems.append(f"{name}: ya no está donde lo dejó el programa.")
            continue
        if meta.has_title_tag and meta.title != change.new_title:
            problems.append(f"{name}: su título cambió después; no se tocó.")
            continue
        try:
            revert(session, change)
        except (*_WRITE_ERRORS, CannotTag) as exc:
            problems.append(f"{name}: {exc}")
            continue
        db.set_song_data(
            change.track_id, change.old_path, change.old_title, change.old_artist, change.old_album, change.old_genre,
            change.old_cover,
        )
        change.undone = True
        restored += 1
        session.save()
    if all(c.undone for c in session.changes):
        session.status = journal.STATUS_UNDONE
    session.save()
    return restored, problems


def follow_rename(track_id: int, new_path: str) -> None:
    """El archivo se renombró por fuera después de aplicar: deshacer tiene que buscarlo con su nombre nuevo."""
    for session in list_sessions():
        changes = [c for c in session.changes if c.track_id == track_id and c.done and not c.undone]
        if changes:
            changes[-1].new_path = new_path
            session.save()


def set_in_library(db, change: FormatChange) -> None:
    db.set_song_data(
        change.track_id, change.new_path, change.new_title, change.new_artist, UNKNOWN_ALBUM, UNKNOWN_GENRE,
        new_library_cover(change),
    )


def reconcile(session: FormatSession, db) -> int:
    """Una sesión cortada a mitad: lo que ya se renombró pasa a la biblioteca y la sesión queda terminada."""
    fixed = 0
    for change in session.changes:
        moved = change.new_path != change.old_path and journal.was_moved(change.old_path, change.new_path)
        if change.done or not moved:
            continue
        set_in_library(db, change)
        change.done = True
        fixed += 1
    session.changes = [c for c in session.changes if c.done]
    if session.changes:
        session.status = journal.STATUS_DONE
        session.save()
    else:
        session.path.unlink(missing_ok=True)
    return fixed


class SongFormatWorker(QObject):
    """Cambia los archivos en su propio hilo; la biblioteca la actualiza el hilo principal con `applied`."""

    progress = Signal(int, int, str)
    applied = Signal(object)  # FormatChange
    failed = Signal(str)
    finished = Signal(bool)  # cancelado

    def __init__(self, session: FormatSession, changes: list[FormatChange]) -> None:
        super().__init__()
        self._session = session
        self._changes = changes
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        total = len(self._changes)
        for index, change in enumerate(self._changes):
            if self._cancelled:
                break
            self.progress.emit(index, total, change.new_title)
            try:
                apply(self._session, change)
                self.applied.emit(change)
            except OSError as exc:
                log.warning("No se pudo cambiar %s: %s", change.old_path, exc)
                name = os.path.basename(change.old_path)
                self.failed.emit(f"{name}: {file_manager.explain(exc, name)}")
            except (*_WRITE_ERRORS, CannotTag) as exc:
                log.warning("No se pudo cambiar %s: %s", change.old_path, exc)
                self.failed.emit(f"{os.path.basename(change.old_path)}: {exc}")
            except Exception as exc:  # nunca dejar el hilo colgado
                log.exception("Error inesperado con %s", change.old_path)
                self.failed.emit(f"{os.path.basename(change.old_path)}: {exc}")
        self.progress.emit(total, total, "")
        self.finished.emit(self._cancelled)
