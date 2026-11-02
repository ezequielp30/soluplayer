"""Base de datos del organizador de MP3 (`organizador.db`). Es un archivo aparte de la biblioteca: no puede dañarla, y
restaurar un respaldo de la biblioteca no borra lo analizado. Cada hilo abre su propia conexión."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import data_dir
from .organizer import Identification
from .utils import path_key

SCHEMA_VERSION = 4
PENDING_MOVING, PENDING_WAITING, PENDING_RETURNING, PENDING_RETURNED = "moviendo", "pendiente", "devolviendo", "devuelta"
ITEM_PLANNED, ITEM_BACKED_UP, ITEM_TAGGED, ITEM_RENAMING = "anotada", "respaldada", "etiquetada", "renombrando"
ITEM_DONE, ITEM_FAILED, ITEM_RESTORED = "lista", "fallo", "restaurada"
_OPEN_STATES = (ITEM_PLANNED, ITEM_BACKED_UP, ITEM_TAGGED, ITEM_RENAMING)
STATUS_NEW, STATUS_ANALYZED, STATUS_DAMAGED = "nuevo", "analizado", "danado"

_OPERATIONS = (
    """CREATE TABLE IF NOT EXISTS operations (
        id INTEGER PRIMARY KEY,
        started_at REAL NOT NULL,
        finished_at REAL
    )""",
    """CREATE TABLE IF NOT EXISTS operation_items (
        id INTEGER PRIMARY KEY,
        operation_id INTEGER NOT NULL REFERENCES operations(id),
        file_id INTEGER NOT NULL,
        old_path TEXT NOT NULL,
        new_path TEXT NOT NULL DEFAULT '',
        old_tags TEXT NOT NULL,
        new_title TEXT NOT NULL,
        new_artist TEXT NOT NULL,
        backup_path TEXT NOT NULL DEFAULT '',
        backup_sha TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL,
        error TEXT NOT NULL DEFAULT '',
        library_synced INTEGER NOT NULL DEFAULT 0,
        updated_at REAL NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_items_file ON operation_items(file_id, state)",
    "CREATE INDEX IF NOT EXISTS idx_items_operation ON operation_items(operation_id)",
)
_PENDING = (
    """CREATE TABLE IF NOT EXISTS pending (
        id INTEGER PRIMARY KEY,
        file_id INTEGER NOT NULL,
        original_path TEXT NOT NULL,
        pending_path TEXT NOT NULL,
        original_tags TEXT NOT NULL,
        reason TEXT NOT NULL,
        candidates TEXT NOT NULL,
        state TEXT NOT NULL,
        retries INTEGER NOT NULL DEFAULT 0,
        library_synced INTEGER NOT NULL DEFAULT 0,
        moved_at REAL NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_pending_file ON pending(file_id, state)",
)
_IDENTIFICATIONS = (
    """CREATE TABLE IF NOT EXISTS identifications (
        file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
        decision TEXT NOT NULL,
        reason TEXT NOT NULL,
        score REAL NOT NULL,
        title TEXT NOT NULL,
        artist TEXT NOT NULL,
        version TEXT NOT NULL,
        recording_id TEXT NOT NULL,
        candidates TEXT NOT NULL,
        identified_at REAL NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_identifications_decision ON identifications(decision)",
)
_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY,
        path TEXT NOT NULL,
        path_key TEXT NOT NULL UNIQUE,
        size INTEGER NOT NULL,
        mtime_ns INTEGER NOT NULL,
        status TEXT NOT NULL,
        problem TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_files_status ON files(status)",
    """CREATE TABLE IF NOT EXISTS fingerprints (
        file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
        duration_s REAL NOT NULL,
        fingerprint TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS api_cache (
        source TEXT NOT NULL,
        request_key TEXT NOT NULL,
        response TEXT NOT NULL,
        fetched_at REAL NOT NULL,
        PRIMARY KEY (source, request_key)
    )""",
)


@dataclass(frozen=True)
class FileRow:
    id: int
    path: str
    status: str
    problem: str | None


@dataclass(frozen=True)
class PendingSong:
    id: int
    file_id: int
    original_path: str
    pending_path: str
    original_tags: str
    reason: str
    candidates: tuple[str, ...]
    state: str
    retries: int
    library_synced: bool


@dataclass(frozen=True)
class OperationItem:
    id: int
    operation_id: int
    file_id: int
    old_path: str
    new_path: str
    old_tags: str
    new_title: str
    new_artist: str
    backup_path: str
    backup_sha: str
    state: str
    error: str
    library_synced: bool


def cache_key(duration_s: float, fingerprint: str) -> str:
    return f"{int(round(duration_s))}:{hashlib.sha1(fingerprint.encode()).hexdigest()}"


def database_file() -> Path:
    return data_dir() / "organizador.db"


class OrganizerDb:
    def __init__(self, path: Path | str | None = None) -> None:
        self.conn = sqlite3.connect(str(path or database_file()), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        if self.conn.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
            with self.conn:
                for statement in (*_SCHEMA, *_IDENTIFICATIONS, *_OPERATIONS, *_PENDING):  # todas con IF NOT EXISTS
                    self.conn.execute(statement)
                self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self.conn.close()

    def register(self, entries: Iterable[tuple[str, int, int]]) -> None:
        """Anota archivos (ruta, tamaño, fecha) en UNA transacción. Si un archivo cambió desde la última vez, hay que
        analizarlo de nuevo: pierde su huella y vuelve a «nuevo». Si no cambió, se conserva lo que ya se sabe."""
        with self.conn:
            for path, size, mtime_ns in entries:
                key = path_key(path)
                row = self.conn.execute("SELECT id, size, mtime_ns FROM files WHERE path_key = ?", (key,)).fetchone()
                if row is None:
                    self.conn.execute(
                        "INSERT INTO files (path, path_key, size, mtime_ns, status) VALUES (?, ?, ?, ?, ?)",
                        (path, key, size, mtime_ns, STATUS_NEW),
                    )
                elif (row["size"], row["mtime_ns"]) != (size, mtime_ns):
                    self.conn.execute("DELETE FROM fingerprints WHERE file_id = ?", (row["id"],))
                    self.conn.execute("DELETE FROM identifications WHERE file_id = ?", (row["id"],))
                    self.conn.execute(
                        "UPDATE files SET path = ?, size = ?, mtime_ns = ?, status = ?, problem = NULL WHERE id = ?",
                        (path, size, mtime_ns, STATUS_NEW, row["id"]),
                    )
                else:
                    self.conn.execute("UPDATE files SET path = ? WHERE id = ?", (path, row["id"]))

    def pending_analysis(self) -> list[FileRow]:
        return [self._row(r) for r in self.conn.execute("SELECT * FROM files WHERE status = ? ORDER BY id", (STATUS_NEW,))]

    def save_results(self, fingerprints: Iterable[tuple[int, float, str]], damaged: Iterable[tuple[int, str]]) -> None:
        """Guarda un lote de una vez: un corte de luz pierde como mucho el lote en curso."""
        with self.conn:
            for file_id, duration, fingerprint in fingerprints:
                self.conn.execute(
                    "INSERT OR REPLACE INTO fingerprints (file_id, duration_s, fingerprint) VALUES (?, ?, ?)",
                    (file_id, duration, fingerprint),
                )
                self.conn.execute("UPDATE files SET status = ?, problem = NULL WHERE id = ?", (STATUS_ANALYZED, file_id))
            for file_id, problem in damaged:
                self.conn.execute("UPDATE files SET status = ?, problem = ? WHERE id = ?", (STATUS_DAMAGED, problem, file_id))

    def fingerprint(self, file_id: int) -> tuple[float, str] | None:
        row = self.conn.execute("SELECT duration_s, fingerprint FROM fingerprints WHERE file_id = ?", (file_id,)).fetchone()
        return (row["duration_s"], row["fingerprint"]) if row else None

    def pending_identification(self) -> list[FileRow]:
        rows = self.conn.execute(
            "SELECT f.* FROM files f LEFT JOIN identifications i ON i.file_id = f.id "
            "WHERE f.status = ? AND i.file_id IS NULL ORDER BY f.id",
            (STATUS_ANALYZED,),
        )
        return [self._row(r) for r in rows]

    def save_identifications(self, rows: Iterable[tuple[int, Identification]]) -> None:
        with self.conn:
            for file_id, item in rows:
                self.conn.execute(
                    "INSERT OR REPLACE INTO identifications (file_id, decision, reason, score, title, artist, version, "
                    "recording_id, candidates, identified_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (file_id, item.decision, item.reason, item.score, item.title, item.artist, item.version,
                     item.recording_id, json.dumps(item.candidates, ensure_ascii=False), time.time()),
                )

    def identification(self, file_id: int) -> Identification | None:
        row = self.conn.execute("SELECT * FROM identifications WHERE file_id = ?", (file_id,)).fetchone()
        if row is None:
            return None
        return Identification(
            row["decision"], row["reason"], row["score"], row["title"], row["artist"], row["version"],
            row["recording_id"], tuple(json.loads(row["candidates"])),
        )

    def identifications(self, file_ids: list[int] | None = None) -> list[tuple[int, Identification]]:
        rows = self.conn.execute("SELECT file_id FROM identifications ORDER BY file_id").fetchall()
        wanted = None if file_ids is None else set(file_ids)
        return [(r["file_id"], self.identification(r["file_id"])) for r in rows if wanted is None or r["file_id"] in wanted]

    def file_by_id(self, file_id: int) -> FileRow | None:
        row = self.conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return self._row(row) if row else None

    def unchanged(self, file_id: int, size: int, mtime_ns: int) -> bool:
        row = self.conn.execute("SELECT size, mtime_ns FROM files WHERE id = ?", (file_id,)).fetchone()
        return row is not None and (row["size"], row["mtime_ns"]) == (size, mtime_ns)

    def move_file(self, file_id: int, path: str, size: int, mtime_ns: int) -> None:
        """El archivo cambió por el propio organizador: su huella sigue valiendo (el audio es el mismo)."""
        with self.conn:
            self.conn.execute(
                "UPDATE files SET path = ?, path_key = ?, size = ?, mtime_ns = ? WHERE id = ?",
                (path, path_key(path), size, mtime_ns, file_id),
            )

    # ---------- pendientes de revisión

    def add_pending(self, file_id: int, original: str, target: str, tags: str, reason: str, candidates: str) -> PendingSong:
        with self.conn:
            pending_id = self.conn.execute(
                "INSERT INTO pending (file_id, original_path, pending_path, original_tags, reason, candidates, state, moved_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (file_id, original, target, tags, reason, candidates, PENDING_MOVING, time.time()),
            ).lastrowid
        return self.pending_song(pending_id)

    def pending_song(self, pending_id: int) -> PendingSong:
        return self._pending(self.conn.execute("SELECT * FROM pending WHERE id = ?", (pending_id,)).fetchone())

    def open_pending(self, file_id: int) -> PendingSong | None:
        row = self.conn.execute(
            "SELECT * FROM pending WHERE file_id = ? AND state != ? ORDER BY id DESC", (file_id, PENDING_RETURNED)
        ).fetchone()
        return self._pending(row) if row else None

    def pending_songs(self) -> list[PendingSong]:
        return [self._pending(r) for r in self.conn.execute("SELECT * FROM pending WHERE state = ? ORDER BY id", (PENDING_WAITING,))]

    def unfinished_pending(self) -> list[PendingSong]:
        rows = self.conn.execute("SELECT * FROM pending WHERE state IN (?, ?) ORDER BY id", (PENDING_MOVING, PENDING_RETURNING))
        return [self._pending(r) for r in rows]

    def set_pending_state(self, pending_id: int, state: str) -> PendingSong:
        with self.conn:
            self.conn.execute("UPDATE pending SET state = ?, library_synced = 0 WHERE id = ?", (state, pending_id))
        return self.pending_song(pending_id)

    def remove_pending(self, pending_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM pending WHERE id = ?", (pending_id,))

    def update_pending_review(self, file_id: int, reason: str, candidates: tuple[str, ...]) -> None:
        """Lo que dijo el último intento: se muestra junto a la canción."""
        with self.conn:
            self.conn.execute(
                "UPDATE pending SET reason = ?, candidates = ? WHERE file_id = ? AND state = ?",
                (reason, json.dumps(candidates, ensure_ascii=False), file_id, PENDING_WAITING),
            )

    def mark_pending_synced(self, pending_id: int) -> None:
        with self.conn:
            self.conn.execute("UPDATE pending SET library_synced = 1 WHERE id = ?", (pending_id,))

    def unsynced_pending(self) -> list[PendingSong]:
        """Movidas en el disco, pero la biblioteca no llegó a enterarse (corte de luz)."""
        rows = self.conn.execute("SELECT * FROM pending WHERE library_synced = 0 AND state IN (?, ?) ORDER BY id", (PENDING_WAITING, PENDING_RETURNED))
        return [self._pending(r) for r in rows]

    def prepare_retry(self, file_ids: list[int] | None = None) -> list[int]:
        """Olvida la última respuesta de estas pendientes (todas si no se dice) para volver a consultar: AcoustID crece
        con el tiempo. Devuelve cuáles quedaron listas para identificar."""
        rows = self.pending_songs()
        wanted = None if file_ids is None else set(file_ids)
        chosen = [p for p in rows if wanted is None or p.file_id in wanted]
        with self.conn:
            for song in chosen:
                saved = self.fingerprint(song.file_id)
                if saved is not None:
                    self.conn.execute("DELETE FROM api_cache WHERE source = ? AND request_key = ?", ("acoustid", cache_key(*saved)))
                self.conn.execute("DELETE FROM identifications WHERE file_id = ?", (song.file_id,))
                self.conn.execute("UPDATE pending SET retries = retries + 1 WHERE id = ?", (song.id,))
        return [p.file_id for p in chosen]

    @staticmethod
    def _pending(row: sqlite3.Row) -> PendingSong:
        return PendingSong(
            row["id"], row["file_id"], row["original_path"], row["pending_path"], row["original_tags"], row["reason"],
            tuple(json.loads(row["candidates"])), row["state"], row["retries"], bool(row["library_synced"]),
        )

    # ---------- operaciones: cada paso queda anotado antes de seguir

    def begin_operation(self) -> int:
        with self.conn:
            return self.conn.execute("INSERT INTO operations (started_at) VALUES (?)", (time.time(),)).lastrowid

    def finish_operation(self, operation_id: int) -> None:
        with self.conn:
            self.conn.execute("UPDATE operations SET finished_at = ? WHERE id = ?", (time.time(), operation_id))

    def add_item(self, operation_id: int, file_id: int, old_path: str, old_tags: str, title: str, artist: str) -> OperationItem:
        with self.conn:
            item_id = self.conn.execute(
                "INSERT INTO operation_items (operation_id, file_id, old_path, old_tags, new_title, new_artist, state, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (operation_id, file_id, old_path, old_tags, title, artist, ITEM_PLANNED, time.time()),
            ).lastrowid
        return self.item(item_id)

    def item(self, item_id: int) -> OperationItem:
        return self._item(self.conn.execute("SELECT * FROM operation_items WHERE id = ?", (item_id,)).fetchone())

    def open_item(self, file_id: int) -> OperationItem | None:
        """La que quedó a medias por un corte."""
        marks = ",".join("?" * len(_OPEN_STATES))
        row = self.conn.execute(
            f"SELECT * FROM operation_items WHERE file_id = ? AND state IN ({marks}) ORDER BY id DESC", (file_id, *_OPEN_STATES)
        ).fetchone()
        return self._item(row) if row else None

    def unfinished_items(self) -> list[OperationItem]:
        marks = ",".join("?" * len(_OPEN_STATES))
        return [self._item(r) for r in self.conn.execute(f"SELECT * FROM operation_items WHERE state IN ({marks}) ORDER BY id", _OPEN_STATES)]

    def items(self, operation_id: int | None = None) -> list[OperationItem]:
        query = "SELECT * FROM operation_items" + ("" if operation_id is None else " WHERE operation_id = ?") + " ORDER BY id"
        return [self._item(r) for r in self.conn.execute(query, () if operation_id is None else (operation_id,))]

    def latest_change(self, file_id: int) -> OperationItem | None:
        row = self.conn.execute(
            "SELECT * FROM operation_items WHERE file_id = ? AND state = ? ORDER BY id DESC", (file_id, ITEM_DONE)
        ).fetchone()
        return self._item(row) if row else None

    def _update_item(self, item_id: int, **fields) -> OperationItem:
        sets = ", ".join(f"{name} = ?" for name in fields)
        with self.conn:
            self.conn.execute(f"UPDATE operation_items SET {sets}, updated_at = ? WHERE id = ?", (*fields.values(), time.time(), item_id))
        return self.item(item_id)

    def mark_backed_up(self, item_id: int, backup_path: str, backup_sha: str) -> OperationItem:
        return self._update_item(item_id, backup_path=backup_path, backup_sha=backup_sha, state=ITEM_BACKED_UP)

    def set_item_state(self, item_id: int, state: str) -> OperationItem:
        return self._update_item(item_id, state=state, error="")

    def mark_renaming(self, item_id: int, new_path: str) -> OperationItem:
        return self._update_item(item_id, new_path=new_path, state=ITEM_RENAMING)

    def note_item_error(self, item_id: int, error: str) -> OperationItem:
        """Falló algo pasajero (archivo en uso): sigue a medias, y al retomarla se usa el mismo respaldo."""
        return self._update_item(item_id, error=error)

    def fail_item(self, item_id: int, error: str) -> OperationItem:
        return self._update_item(item_id, state=ITEM_FAILED, error=error)

    def mark_library_synced(self, item_id: int, synced: bool = True) -> None:
        self._update_item(item_id, library_synced=int(synced))

    def unsynced_items(self) -> list[OperationItem]:
        """Cambiadas en el disco, pero la biblioteca no llegó a enterarse (corte de luz)."""
        rows = self.conn.execute(
            "SELECT * FROM operation_items WHERE library_synced = 0 AND state IN (?, ?) ORDER BY id", (ITEM_DONE, ITEM_RESTORED)
        )
        return [self._item(r) for r in rows]

    @staticmethod
    def _item(row: sqlite3.Row) -> OperationItem:
        return OperationItem(
            row["id"], row["operation_id"], row["file_id"], row["old_path"], row["new_path"], row["old_tags"], row["new_title"],
            row["new_artist"], row["backup_path"], row["backup_sha"], row["state"], row["error"], bool(row["library_synced"]),
        )

    def forget_identifications(self) -> None:
        """Para decidir otra vez (cambiaron los niveles de confianza). Las respuestas de la caché se conservan."""
        with self.conn:
            self.conn.execute("DELETE FROM identifications")

    def counts(self) -> dict[str, int]:
        return {r["status"]: r["n"] for r in self.conn.execute("SELECT status, COUNT(*) AS n FROM files GROUP BY status")}

    def file(self, path: str) -> FileRow | None:
        row = self.conn.execute("SELECT * FROM files WHERE path_key = ?", (path_key(path),)).fetchone()
        return self._row(row) if row else None

    def cached(self, source: str, request_key: str, max_age_s: float) -> str | None:
        """Respuesta guardada de un servicio, si es lo bastante reciente: así no se repiten consultas."""
        row = self.conn.execute(
            "SELECT response, fetched_at FROM api_cache WHERE source = ? AND request_key = ?", (source, request_key)
        ).fetchone()
        return row["response"] if row and 0 <= time.time() - row["fetched_at"] <= max_age_s else None

    def store_cached(self, source: str, request_key: str, response: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO api_cache (source, request_key, response, fetched_at) VALUES (?, ?, ?, ?)",
                (source, request_key, response, time.time()),
            )

    @staticmethod
    def _row(row: sqlite3.Row) -> FileRow:
        return FileRow(row["id"], row["path"], row["status"], row["problem"])
