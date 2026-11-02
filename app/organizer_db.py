"""Base de datos del organizador de MP3 (`organizador.db`). Es un archivo aparte de la biblioteca: no puede dañarla, y
restaurar un respaldo de la biblioteca no borra lo analizado. Cada hilo abre su propia conexión."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import data_dir
from .utils import path_key

SCHEMA_VERSION = 1
STATUS_NEW, STATUS_ANALYZED, STATUS_DAMAGED = "nuevo", "analizado", "danado"

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
                for statement in _SCHEMA:
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
