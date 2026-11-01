"""Respaldos de la biblioteca (SQLite) y comprobación de salud al arrancar.

- Copia con la API de respaldo de SQLite (segura aunque la base esté abierta en modo WAL).
- Cada copia se verifica con `PRAGMA integrity_check`; si falla, se descarta.
- Retención: las 10 copias más recientes + la más reciente de cada una de las 4 semanas anteriores.
- Nunca se sobrescribe una base dañada: al restaurar, se aparta con otro nombre.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from .config import backups_copy_dir, data_dir

log = logging.getLogger(__name__)

KEEP_RECENT = 10
KEEP_WEEKS = 4
KEEP_OPERATION_DAYS = 7  # los de antes de una operación (quitar faltantes, mover…) duran al menos esto
DAILY_INTERVAL = timedelta(hours=24)
_PREFIX = "biblioteca-"
_STAMP = "%Y%m%d-%H%M%S"


def backup_dir() -> Path:
    path = data_dir() / "respaldos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_backups() -> list[Path]:
    """Respaldos ordenados del más reciente al más antiguo."""
    return sorted(backup_dir().glob(f"{_PREFIX}*.db"), key=lambda p: p.name, reverse=True)


def _taken_at(path: Path) -> datetime | None:
    try:
        return datetime.strptime(path.stem[len(_PREFIX):len(_PREFIX) + 15], _STAMP)
    except ValueError:
        return None


def check_database(path: Path | str) -> str | None:
    """None si la base está sana; si no, el motivo. Abre en solo lectura."""
    try:
        if Path(path).stat().st_size == 0:
            # SQLite toma un archivo vacío como una base nueva y «sana»: tras un corte de luz o un disco
            # lleno el programa abriría sin canciones ni playlists, sin avisar ni ofrecer el respaldo.
            return "el archivo de la biblioteca está vacío (0 bytes)"
    except OSError as exc:
        return str(exc)
    try:
        # La ruta va escapada: un «#» o «%» en el nombre de la carpeta cortaría la URI y se revisaría
        # otro archivo (o ninguno).
        uri = "file:" + urllib.request.pathname2url(str(Path(path).resolve())) + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
            has_tracks = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tracks'").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return str(exc)
    if not row or row[0] != "ok":
        return row[0] if row else "sin respuesta"
    if not has_tracks:
        return "el archivo no contiene las tablas de la biblioteca"
    return None


def create_backup(conn: sqlite3.Connection, reason: str = "diario") -> Path | None:
    """Copia la base abierta a la carpeta de respaldos. Devuelve la ruta, o None si falló."""
    safe_reason = "".join(c if c.isalnum() or c == "-" else "-" for c in reason)[:30]
    target = backup_dir() / f"{_PREFIX}{datetime.now().strftime(_STAMP)}-{safe_reason}.db"
    counter = 1
    while target.exists():  # dos respaldos en el mismo segundo
        target = target.with_name(f"{target.stem}-{counter}.db")
        counter += 1
    try:
        copy = sqlite3.connect(target)
        try:
            conn.backup(copy)
            ok = copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            copy.close()
    except sqlite3.Error as exc:
        log.error("No se pudo crear el respaldo %s: %s", target, exc)
        target.unlink(missing_ok=True)
        return None
    if not ok:
        log.error("El respaldo %s no pasó la verificación y se descartó", target)
        target.unlink(missing_ok=True)
        return None
    log.info("Respaldo creado (%s): %s", reason, target.name)
    prune()
    return target


def prune(now: datetime | None = None) -> list[Path]:
    """Aplica la retención. Solo borra archivos de la carpeta de respaldos. Devuelve los borrados."""
    now = now or datetime.now()
    backups = list_backups()
    keep = set(backups[:KEEP_RECENT])
    weeks_kept: set[int] = set()
    reasons_kept = {p.stem[len(_PREFIX) + 16:] for p in backups[:KEEP_RECENT]}
    for path in backups[KEEP_RECENT:]:
        taken = _taken_at(path)
        if taken is None:
            keep.add(path)  # nombre inesperado: no se toca
            continue
        reason = path.stem[len(_PREFIX) + 16:]
        if reason != "diario" and reason not in reasons_kept and now - taken < timedelta(days=KEEP_OPERATION_DAYS):
            # El más reciente de cada tipo de operación dura una semana: una tarde de renombrar no se lleva
            # el de antes de quitar faltantes (y tampoco deja cientos de copias guardadas).
            reasons_kept.add(reason)
            keep.add(path)
            continue
        week = (now - taken).days // 7
        if week < KEEP_WEEKS + 1 and week not in weeks_kept:
            weeks_kept.add(week)
            keep.add(path)
    removed = []
    for path in backups:
        if path not in keep:
            try:
                path.unlink()
                removed.append(path)
            except OSError as exc:
                log.warning("No se pudo borrar el respaldo antiguo %s: %s", path, exc)
    return removed


def backup_if_due(conn: sqlite3.Connection) -> Path | None:
    """Respaldo diario: solo si el último tiene más de 24 h (o no hay ninguno)."""
    backups = list_backups()
    last = _taken_at(backups[0]) if backups else None
    if last is not None and datetime.now() - last < DAILY_INTERVAL:
        return None
    path = create_backup(conn, "diario")
    if path is not None:
        copy_latest_outside()
    return path


KEEP_OUTSIDE = 3  # respaldos copiados a Documentos


def outside_copies_dir() -> Path:
    """La subcarpeta de ESTA PC y este usuario: si Documentos está en OneDrive, dos PC con la misma cuenta
    no se pisan los respaldos ni una ofrece recuperar la biblioteca de la otra."""
    from .review_folder import safe_name

    who = f"{os.environ.get('COMPUTERNAME', 'PC')} - {os.environ.get('USERNAME', 'usuario')}"
    return backups_copy_dir() / safe_name(who)


def copy_latest_outside() -> Path | None:
    """Copia el respaldo más reciente a Documentos (fuera de la carpeta del programa: si esa se borra, la
    biblioteca se puede recuperar). Se guardan los KEEP_OUTSIDE más recientes. Devuelve la copia o None."""
    backups = list_backups()
    if not backups:
        return None
    target_dir = outside_copies_dir()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / backups[0].name
        if not target.exists():
            temp = target.with_name(target.name + ".tmp")
            shutil.copy2(backups[0], temp)
            os.replace(temp, target)  # de una vez: nunca una copia a medias con el nombre definitivo
        for old in sorted(target_dir.glob(f"{_PREFIX}*.db"), key=lambda p: p.name, reverse=True)[KEEP_OUTSIDE:]:
            old.unlink()
        for leftover in target_dir.glob("*.tmp"):  # copia cortada a medias (corte de luz)
            leftover.unlink()
    except OSError as exc:
        log.warning("No se pudo copiar el respaldo a %s: %s", target_dir, exc)
        return None
    return target


def newest_outside_copy() -> Path | None:
    """El respaldo válido más reciente de la copia en Documentos (para recuperar una biblioteca perdida)."""
    folder = outside_copies_dir()
    if not folder.is_dir():
        return None
    for path in sorted(folder.glob(f"{_PREFIX}*.db"), key=lambda p: p.name, reverse=True):
        if check_database(path) is None:
            return path
    return None


def latest_valid_backup() -> Path | None:
    for path in list_backups():
        if check_database(path) is None:
            return path
    return None


def restore(backup: Path, db_path: Path) -> Path:
    """Restaura `backup` en `db_path`. La base actual (y sus -wal/-shm) se aparta, no se borra.
    Devuelve la ruta donde quedó la base apartada."""
    stamp = datetime.now().strftime(_STAMP)
    aside = db_path.with_name(f"{db_path.stem}-danada-{stamp}{db_path.suffix}")
    # Orden pensado para que en ningún momento falte la biblioteca (un cierre a mitad o un disco lleno
    # dejan la anterior en su sitio):
    # 1) el respaldo se copia primero a un temporal junto a la base;
    temp = db_path.with_name(db_path.name + ".restaurando")
    shutil.copy2(backup, temp)
    with open(temp, "rb+") as handle:
        os.fsync(handle.fileno())
    # 2) la anterior se guarda aparte (con su -wal/-shm, que no deben aplicarse a la restaurada);
    for suffix in ("-wal", "-shm"):
        extra = Path(str(db_path) + suffix)
        if extra.exists():
            os.replace(extra, Path(str(aside) + suffix))
    if db_path.exists():
        shutil.copy2(db_path, aside)
    # 3) y el temporal reemplaza a la base en un solo paso.
    os.replace(temp, db_path)
    log.warning("Biblioteca restaurada desde %s; la anterior se apartó como %s", backup.name, aside.name)
    return aside
