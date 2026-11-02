"""Canciones que no se pudieron identificar: van a la carpeta PENDIENTES_REVISION sin cambiar nombre ni etiquetas, con todo
anotado para devolverlas. Mover dentro del mismo disco es un cambio de nombre instantáneo: no se copian datos."""

from __future__ import annotations

import json
import os

from .normalizer import tags_snapshot
from .organizer import PENDING_FOLDER, Identification
from .organizer_db import PENDING_MOVING, PENDING_RETURNING, PENDING_RETURNED, PENDING_WAITING, OrganizerDb, PendingSong
from .utils import long_path, path_key

MAX_PATH = 240  # el mismo margen que la carpeta de revisión de repetidas


class PendingError(Exception):
    """El texto se le muestra a la persona. La canción queda donde estaba."""


def root_of(path: str, roots: list[str]) -> str:
    """La carpeta elegida que contiene al archivo (la más específica); si ninguna, la carpeta del propio archivo."""
    key = path_key(path)
    inside = [r for r in roots if key.startswith(path_key(r).rstrip("\\/") + os.sep)]
    return max(inside, key=len) if inside else os.path.dirname(path)


def pending_path_for(path: str, root: str) -> str:
    """Conserva las subcarpetas: así dos canciones con el mismo nombre no chocan y el nombre nunca cambia."""
    relative = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    return os.path.join(root, PENDING_FOLDER, relative)


def move_to_pending(db: OrganizerDb, file_id: int, root: str, item: Identification) -> PendingSong:
    row = db.file_by_id(file_id)
    if row is None or not os.path.isfile(long_path(row.path)):
        raise PendingError("El archivo ya no está en su sitio.")
    if db.open_pending(file_id) is not None:
        raise PendingError("La canción ya está en pendientes.")
    if db.open_item(file_id) is not None:
        raise PendingError("Quedó a medias de normalizar: retómala o restáurala en Historial.")
    target = pending_path_for(row.path, root)
    if len(target) > MAX_PATH:
        raise PendingError("La ruta quedaría demasiado larga para Windows: la canción se queda donde está.")
    if os.path.splitdrive(os.path.abspath(row.path))[0].casefold() != os.path.splitdrive(os.path.abspath(target))[0].casefold():
        raise PendingError("La carpeta de pendientes tiene que estar en el mismo disco.")
    if os.path.exists(long_path(target)):
        raise PendingError(f"Ya hay otro archivo en pendientes con el nombre «{os.path.basename(target)}»: no se pisó.")
    # Todo queda anotado antes de mover: un corte de luz a mitad se puede resolver al abrir.
    pending = db.add_pending(file_id, row.path, target, tags_snapshot(row.path), item.reason, json.dumps(item.candidates, ensure_ascii=False))
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.rename(long_path(row.path), long_path(target))
    except OSError as exc:
        db.remove_pending(pending.id)
        raise PendingError(f"No se pudo mover: {exc.strerror or exc}") from exc
    _point_file_at(db, file_id, target)
    return db.set_pending_state(pending.id, PENDING_WAITING)


def return_to_origin(db: OrganizerDb, pending: PendingSong) -> PendingSong:
    """La devuelve a su carpeta. Nunca pisa: si ya hay otro archivo en ese lugar, sigue en pendientes y se avisa."""
    origin, current = long_path(pending.original_path), long_path(pending.pending_path)
    if not os.path.isfile(current):
        raise PendingError("La canción ya no está en pendientes.")
    if os.path.exists(origin):
        raise PendingError(f"Ya hay otro archivo en «{pending.original_path}»: la canción sigue en pendientes.")
    pending = db.set_pending_state(pending.id, PENDING_RETURNING, moved=False)
    try:
        os.makedirs(os.path.dirname(origin), exist_ok=True)
        os.rename(current, origin)
    except OSError as exc:
        db.set_pending_state(pending.id, PENDING_WAITING, moved=False)
        raise PendingError(f"No se pudo devolver: {exc.strerror or exc}") from exc
    _point_file_at(db, pending.file_id, pending.original_path)
    _remove_empty_folders(os.path.dirname(pending.pending_path))
    return db.set_pending_state(pending.id, PENDING_RETURNED)


def _point_file_at(db: OrganizerDb, file_id: int, path: str) -> None:
    info = os.stat(long_path(path))
    db.move_file(file_id, path, info.st_size, info.st_mtime_ns)


def _remove_empty_folders(folder: str) -> None:
    """Solo dentro de PENDIENTES_REVISION, incluida ella, y solo si están vacías."""
    while PENDING_FOLDER.casefold() in [part.casefold() for part in os.path.normpath(folder).split(os.sep)]:
        try:
            os.rmdir(long_path(folder))
        except OSError:
            return
        if os.path.basename(os.path.normpath(folder)).casefold() == PENDING_FOLDER.casefold():
            return
        folder = os.path.dirname(folder)


def reconcile(db: OrganizerDb) -> int:
    """Al abrir: los movimientos que un corte dejó a mitad quedan según lo que hay de verdad en el disco."""
    fixed = 0
    for pending in db.unfinished_pending():
        at_origin = os.path.isfile(long_path(pending.original_path))
        at_pending = os.path.isfile(long_path(pending.pending_path))
        if pending.state == PENDING_MOVING:
            if at_pending and not at_origin:
                _point_file_at(db, pending.file_id, pending.pending_path)
                db.set_pending_state(pending.id, PENDING_WAITING)
            else:
                db.remove_pending(pending.id)  # no llegó a moverse
        elif at_origin and not at_pending:  # devolviéndola: ya llegó
            _point_file_at(db, pending.file_id, pending.original_path)
            _remove_empty_folders(os.path.dirname(pending.pending_path))
            db.set_pending_state(pending.id, PENDING_RETURNED)
        else:  # no llegó a volver: sigue donde la biblioteca ya sabe
            db.set_pending_state(pending.id, PENDING_WAITING, moved=False)
        fixed += 1
    return fixed
