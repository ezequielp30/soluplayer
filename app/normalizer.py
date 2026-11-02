"""Normaliza un MP3 identificado: respaldo verificado, etiquetas TITLE y ARTIST, nombre «TITULO - ARTISTA.mp3». Sin ventanas.

El orden protege la canción. Cada paso queda anotado antes de seguir, así que tras un corte de luz se retoma donde iba:
1. Copia completa, comparada byte a byte. Sin esa confirmación, el archivo no se toca.
2. Etiquetas en una copia de trabajo. Solo reemplaza al archivo si el audio salió idéntico.
3. Cambio de nombre, sin pisar nunca otro archivo.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime

import mutagen
from mutagen.id3 import ID3, TIT2, TPE1, ID3NoHeaderError

from . import converter, song_backup
from .organizer import BACKUP_FOLDER, DECISION_AUTO, DECISION_DONE, Identification
from .organizer_db import ITEM_BACKED_UP, ITEM_DONE, ITEM_PLANNED, ITEM_RENAMING, ITEM_RESTORED, ITEM_TAGGED, OperationItem, OrganizerDb
from .review_folder import safe_name
from .song_format import _target_path
from .title_format import confirmed_title, file_stem, has_file_name, has_foreign_letters
from .title_tags import _WRITE_ERRORS, CannotTag, edit_safely
from .utils import long_path

log = logging.getLogger(__name__)

MAX_PATH = 240  # el mismo margen que la carpeta de revisión de repetidas y la de pendientes


class NormalizeError(Exception):
    """El texto se le muestra a la persona. El archivo queda como estaba o en un estado que se puede retomar."""


@dataclass(frozen=True)
class SongJob:
    file_id: int
    title: str
    artist: str


def jobs_from_identifications(db: OrganizerDb, file_ids: list[int] | None = None) -> list[SongJob]:
    """Las identificadas como seguras; o, si se piden unas concretas, esas (la persona ya las eligió)."""
    return [SongJob(file_id, item.title, item.artist) for file_id, item in db.identifications(file_ids)
            if item.title and item.artist and (file_ids is not None or item.decision == DECISION_AUTO)]


def backup_root(path: str, chosen: str | None) -> str:
    """Siempre en una carpeta «RESPALDOS_MP3», dentro de la elegida o en la raíz del disco de la canción: por ese nombre
    el programa sabe en todas partes que no son canciones, aunque se analice la unidad entera."""
    return os.path.join(chosen or os.path.splitdrive(os.path.abspath(path))[0] + os.sep, BACKUP_FOLDER)


def _target_for(path: str, title: str, artist: str) -> str:
    """Siempre con extensión .mp3 en minúsculas. Si la ruta no entra en Windows, se avisa antes de tocar nada."""
    target = _target_path(os.path.splitext(path)[0] + ".mp3", file_stem(title, artist))
    if len(target) > MAX_PATH:
        raise NormalizeError("La ruta quedaría demasiado larga para Windows: la canción se queda como está.")
    return target


def tags_snapshot(path: str) -> str:
    """Los metadatos originales en texto, para el registro. La restauración usa la copia completa."""
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        return "{}"
    except (OSError, mutagen.MutagenError):
        return "{}"
    snapshot = {}
    for key, frame in tags.items():
        snapshot[key] = f"<{len(frame.data)} bytes>" if key.startswith("APIC") else str(frame)
    return json.dumps(snapshot, ensure_ascii=False)


def write_song_tags(path: str, title: str, artist: str) -> None:
    """Solo TITLE y ARTIST, más la marca interna con la que se deshace una conversión a MP3. La etiqueta APEv2 de
    «Ajustar volumen» va aparte, al final del archivo: no se toca. Se quita ID3v1, que recorta los títulos largos."""
    try:
        audio = mutagen.File(path)
    except Exception as exc:
        raise CannotTag(str(exc)) from exc
    if audio is None:
        raise CannotTag("formato no reconocido")
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    if not isinstance(tags, ID3):
        raise CannotTag("no tiene etiquetas ID3")
    created = f"TXXX:{converter._CREATED_MARK}"
    for key in list(tags.keys()):
        if key != created:
            del tags[key]
    tags.add(TIT2(encoding=3, text=[title]))
    tags.add(TPE1(encoding=3, text=[artist]))
    tags.update_to_v23()
    audio.save(v2_version=3, v1=0)


def already_normalized(path: str, title: str, artist: str) -> bool:
    try:
        tags = ID3(path)
    except (OSError, mutagen.MutagenError):
        return False
    kept = {key for key in tags.keys() if key != f"TXXX:{converter._CREATED_MARK}"}
    return (
        kept == {"TIT2", "TPE1"} and str(tags["TIT2"]) == title and str(tags["TPE1"]) == artist
        and re.sub(r" \(\d+\)$", "", os.path.splitext(os.path.basename(path))[0]) == safe_name(file_stem(title, artist), 150)
    )


def normalize(db: OrganizerDb, operation_id: int, job: SongJob, backup_folder: str | None) -> OperationItem | None:
    """Procesa una canción, o retoma la que quedó a medias. None si no había nada que hacer."""
    row = db.file_by_id(job.file_id)
    if row is None:
        raise NormalizeError("La canción ya no está en el análisis.")
    # El título y el artista ya vienen decididos: de la base de datos o de la persona. Aquí no se vuelven a recortar.
    title, artist = confirmed_title(job.title), job.artist.strip()
    if not title or not artist:
        raise NormalizeError("Falta el título o el artista.")
    if not has_file_name(title, artist) or has_foreign_letters(f"{title} {artist}"):  # el nombre perdería esas letras
        raise NormalizeError("El título o el artista no usa solo letras latinas: escríbelos como quieras que se llame el archivo.")
    item = db.open_item(job.file_id)
    if item is not None and (item.new_title, item.new_artist) != (title, artist):
        if item.state not in (ITEM_PLANNED, ITEM_BACKED_UP):
            raise NormalizeError(f"Quedó a medias como «{item.new_title}»: retómala o restáurala en Historial.")
        item = db.update_item_song(item.id, title, artist)
    if item is None:
        if not os.path.isfile(long_path(row.path)):
            raise NormalizeError("El archivo ya no está en su sitio.")
        info = os.stat(long_path(row.path))
        if not db.unchanged(job.file_id, info.st_size, info.st_mtime_ns):
            raise NormalizeError("El archivo cambió desde que se analizó: analízalo de nuevo.")
        if already_normalized(row.path, title, artist):
            return None
        _target_for(row.path, title, artist)
        item = db.add_item(operation_id, job.file_id, row.path, tags_snapshot(row.path), title, artist)
    return _advance(db, item, backup_folder)


def _advance(db: OrganizerDb, item: OperationItem, backup_folder: str | None) -> OperationItem:
    if item.state == ITEM_PLANNED:
        item = _back_up(db, item, backup_folder)
    if item.state == ITEM_BACKED_UP:
        if not song_backup.is_intact(item.backup_path, item.backup_sha):
            db.fail_item(item.id, "El respaldo ya no está intacto: no se modificó la canción.")
            raise NormalizeError("El respaldo ya no está intacto: no se modificó la canción.")
        if _matches_backup(item):
            item = _write_tags(db, item)
        elif _is_same_song(long_path(item.old_path), item.backup_path) and _has_new_tags(item):
            item = db.set_item_state(item.id, ITEM_TAGGED)  # se cortó justo después de escribir las etiquetas
        else:
            db.fail_item(item.id, "El archivo cambió después del respaldo: no se modificó.")
            raise NormalizeError("El archivo cambió después del respaldo: no se modificó.")
    if item.state == ITEM_TAGGED:
        item = _rename(db, item)
    if item.state == ITEM_RENAMING:
        item = _finish_rename(db, item)
    return item


def _back_up(db: OrganizerDb, item: OperationItem, backup_folder: str | None) -> OperationItem:
    name = safe_name(os.path.basename(item.old_path), 150)
    folder = os.path.join(backup_root(item.old_path, backup_folder), datetime.now().strftime("%Y-%m"))
    target = _free_name(folder, f"{item.id:07d} - {name}")
    if not song_backup.enough_space(os.path.dirname(target), os.path.getsize(long_path(item.old_path))):
        db.fail_item(item.id, "No hay espacio para el respaldo: no se modificó la canción.")
        raise NormalizeError("No hay espacio para el respaldo: no se modificó la canción.")
    try:
        digest = song_backup.make_backup(long_path(item.old_path), target)
    except song_backup.BackupError as exc:
        db.fail_item(item.id, str(exc))
        raise NormalizeError(str(exc)) from exc
    _note_in_index(target, item.old_path)
    return db.mark_backed_up(item.id, target, digest)


def _note_in_index(backup: str, original: str) -> None:
    """Un índice junto a las copias: si se perdiera la base de datos, se sabe de dónde salió cada una."""
    try:
        with open(os.path.join(os.path.dirname(backup), "indice.tsv"), "a", encoding="utf-8") as index:
            index.write(f"{os.path.basename(backup)}\t{original}\n")
    except OSError as exc:
        log.warning("No se pudo anotar el respaldo en el índice: %s", exc)


def _matches_backup(item: OperationItem) -> bool:
    try:
        return song_backup.file_digest(long_path(item.old_path)) == item.backup_sha
    except OSError:
        return False


def _has_new_tags(item: OperationItem) -> bool:
    try:
        tags = ID3(long_path(item.old_path))
        return str(tags.get("TIT2")) == item.new_title and str(tags.get("TPE1")) == item.new_artist
    except (OSError, mutagen.MutagenError):
        return False


def _free_name(folder: str, name: str) -> str:
    """Un nombre libre: un respaldo anterior nunca se pisa, aunque la numeración se repita (si se borró la base)."""
    stem, ext = os.path.splitext(name)
    candidate, n = os.path.join(folder, name), 2
    while os.path.exists(candidate):
        candidate, n = os.path.join(folder, f"{stem} ({n}){ext}"), n + 1
    return candidate


def _write_tags(db: OrganizerDb, item: OperationItem) -> OperationItem:
    try:
        edit_safely(item.old_path, lambda temp: write_song_tags(temp, item.new_title, item.new_artist), item.new_title)
    except (*_WRITE_ERRORS, CannotTag) as exc:
        db.note_item_error(item.id, f"No se pudieron escribir las etiquetas: {exc}")
        raise NormalizeError(f"No se pudieron escribir las etiquetas: {exc}") from exc
    return db.set_item_state(item.id, ITEM_TAGGED)


def _rename(db: OrganizerDb, item: OperationItem) -> OperationItem:
    try:
        target = _target_for(item.old_path, item.new_title, item.new_artist)
    except NormalizeError as exc:
        db.note_item_error(item.id, str(exc))
        raise
    return db.mark_renaming(item.id, target)


def _finish_rename(db: OrganizerDb, item: OperationItem) -> OperationItem:
    """Si se cortó justo aquí, el archivo ya puede estar con su nombre nuevo."""
    old, new = long_path(item.old_path), long_path(item.new_path)
    same = os.path.normcase(old) == os.path.normcase(new)
    if not (os.path.exists(new) and not os.path.exists(old)) and not (same and item.old_path == item.new_path):
        try:
            os.rename(old, new)  # en Windows falla si el destino existe: nunca pisa otro archivo
        except OSError as exc:
            db.note_item_error(item.id, f"No se pudo cambiar el nombre: {exc.strerror or exc}")
            raise NormalizeError(f"No se pudo cambiar el nombre: {exc.strerror or exc}") from exc
    info = os.stat(new)
    db.move_file(item.file_id, item.new_path, info.st_size, info.st_mtime_ns)
    # Ya no es dudosa: la persona la corrigió o se identificó. No debe ir a pendientes.
    db.save_identifications([(item.file_id, Identification(DECISION_DONE, "Ya está normalizada.", 0.0, item.new_title, item.new_artist))])
    return db.set_item_state(item.id, ITEM_DONE)


def restore(db: OrganizerDb, item: OperationItem) -> OperationItem:
    """Devuelve la canción a como estaba antes de `item`, byte a byte y con su nombre, aunque después se normalizara
    otra vez. Nunca pisa un archivo ajeno. El respaldo se conserva hasta que la persona lo borre."""
    if item.state == ITEM_RESTORED:
        return item
    if not song_backup.is_intact(item.backup_path, item.backup_sha):
        raise NormalizeError("El respaldo no está o no está intacto: no se tocó nada.")
    old = long_path(item.old_path)
    # La versión normalizada, si sigue ahí y con otro nombre: la que hay que quitar una vez restaurada la original.
    row = db.file_by_id(item.file_id)
    current_path = row.path if row is not None else item.new_path
    renamed = long_path(current_path) if current_path else ""
    if not renamed or os.path.normcase(renamed) == os.path.normcase(old) or not os.path.exists(renamed):
        renamed = ""
    if os.path.exists(old) and not _is_same_song(old, item.backup_path):
        raise NormalizeError(f"Ya hay otro archivo en «{os.path.basename(item.old_path)}»: no se pisó.")
    if renamed and not _is_same_song(renamed, item.backup_path):
        raise NormalizeError(f"«{os.path.basename(renamed)}» ya no es esta canción: no se tocó.")
    temp = f"{old}.restaurando.tmp"
    try:
        os.makedirs(os.path.dirname(old), exist_ok=True)
        digest = song_backup.make_backup(item.backup_path, temp)
        if digest != item.backup_sha:
            raise NormalizeError("La copia restaurada no salió idéntica: no se tocó nada.")
        os.replace(temp, old)
    except (OSError, song_backup.BackupError) as exc:
        raise NormalizeError(f"No se pudo restaurar: {getattr(exc, 'strerror', None) or exc}") from exc
    finally:
        if os.path.exists(temp):
            try:
                os.remove(temp)
            except OSError:
                pass
    info = os.stat(old)
    db.move_file(item.file_id, item.old_path, info.st_size, info.st_mtime_ns)
    db.forget_identification(item.file_id)  # al analizar se decide otra vez, sin repetir la consulta
    # Anotado antes de quitar la versión normalizada: si se corta aquí, sobra una copia, pero la biblioteca lo sabe.
    restored = db.mark_restored_from(item, current_path or "")
    if renamed:
        try:
            os.remove(renamed)
        except OSError as exc:
            log.warning("Restaurada, pero no se pudo quitar %s: %s", renamed, exc)
    return restored


def _is_same_song(path: str, backup: str) -> bool:
    """El mismo audio, sean cuales sean sus etiquetas."""
    try:
        return song_backup.audio_digest(path) == song_backup.audio_digest(backup)
    except OSError:
        return False
