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

from .config import data_dir

log = logging.getLogger(__name__)

KEEP_RECENT = 10
KEEP_WEEKS = 4
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
    for path in backups[KEEP_RECENT:]:
        taken = _taken_at(path)
        if taken is None:
            keep.add(path)  # nombre inesperado: no se toca
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
    return create_backup(conn, "diario")


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
