"""Persistencia en SQLite de la biblioteca y las playlists."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .config import RECENT_LIMIT
from .importer import ScannedTrack
from .metadata import AudioMetadata
from .models import Playlist, Track
from .utils import no_markup, normalize_text, path_key

SCHEMA_VERSION = 3

# Cambios de esquema por versión (se aplican en orden, dentro de la misma transacción).
_MIGRATIONS: dict[int, list[str]] = {
    2: [  # análisis de sonoridad y ajuste de volumen de los MP3
        "ALTER TABLE tracks ADD COLUMN loudness_lufs REAL",
        "ALTER TABLE tracks ADD COLUMN true_peak_db REAL",
        "ALTER TABLE tracks ADD COLUMN norm_gain_db REAL NOT NULL DEFAULT 0",
        "ALTER TABLE tracks ADD COLUMN analyzed_at TEXT",
    ],
    3: [  # orden manual de «Canciones» (NULL = sin posición elegida: va al final, en el orden de siempre)
        "ALTER TABLE tracks ADD COLUMN sort_pos INTEGER",
    ],
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS covers (
    hash TEXT PRIMARY KEY,
    data BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    path_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT NOT NULL,
    genre TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    cover_hash TEXT REFERENCES covers(hash),
    added_at TEXT NOT NULL,
    last_played_at TEXT,
    play_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    added_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_playlist_tracks_playlist ON playlist_tracks(playlist_id, position);
CREATE INDEX IF NOT EXISTS idx_playlist_tracks_track ON playlist_tracks(track_id);
"""

_TRACK_COLUMNS = (
    "t.id, t.path, t.title, t.artist, t.album, t.genre, t.duration_ms, "
    "t.added_at, t.last_played_at, t.cover_hash, t.loudness_lufs, t.true_peak_db, t.norm_gain_db"
)

MAX_PLAYLIST_NAME = 30  # para crear o renombrar; las que ya tenían un nombre más largo no se recortan


class PlaylistNameError(ValueError):
    """Nombre de playlist inválido o repetido. El mensaje es apto para el usuario."""


class DuplicatePathError(ValueError):
    """La ruta ya pertenece a otra canción de la biblioteca."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def available_paths(paths: Iterable[str]) -> set[str]:
    """Cuáles de estas rutas existen, leyendo cada carpeta UNA vez (no un acceso al disco por canción: con
    miles de canciones o música en red, arrancar tardaba mucho). Si un disco o servidor no responde, no se
    vuelve a intentar con el resto de sus carpetas (cada intento esperaría su tiempo límite)."""
    by_folder: dict[str, list[str]] = {}
    for path in paths:
        by_folder.setdefault(os.path.dirname(path), []).append(path)
    dead_roots: set[str] = set()
    found: set[str] = set()
    for folder, members in by_folder.items():
        root = os.path.splitdrive(folder)[0].casefold()
        if root in dead_roots:
            continue
        try:
            with os.scandir(folder) as entries:
                names = {e.name.casefold() for e in entries if e.is_file()}
        except OSError:
            if root and not os.path.exists(os.path.splitdrive(folder)[0] + "\\"):
                dead_roots.add(root)  # disco desconectado o servidor apagado: no insistir con el resto
            continue
        found.update(p for p in members if os.path.basename(p).casefold() in names)
    return found


def _row_to_track(row: sqlite3.Row, check: bool = True) -> Track:
    track = Track(
        id=row["id"],
        path=row["path"],
        title=no_markup(row["title"]),  # vienen de las etiquetas del archivo: nunca como HTML
        artist=no_markup(row["artist"]),
        album=no_markup(row["album"]),
        genre=no_markup(row["genre"]),
        duration_ms=row["duration_ms"],
        added_at=row["added_at"],
        last_played_at=row["last_played_at"],
        cover_hash=row["cover_hash"],
        loudness_lufs=row["loudness_lufs"] if "loudness_lufs" in row.keys() else None,
        true_peak_db=row["true_peak_db"] if "true_peak_db" in row.keys() else None,
        norm_gain_db=(row["norm_gain_db"] or 0.0) if "norm_gain_db" in row.keys() else 0.0,
        entry_id=row["entry_id"] if "entry_id" in row.keys() else None,
    )
    if check:
        track.check_available()
    return track


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    def _migrate(self) -> None:
        """Crea o actualiza el esquema en UNA transacción (con user_version dentro):
        si se corta a mitad, la base queda como estaba. Antes de actualizar una base
        con datos se hace un respaldo."""
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            return
        if version > 0:
            from .backup import create_backup  # evita import circular

            create_backup(self.conn, f"antes-de-actualizar-v{version}")
        statements = [s.strip() for s in _SCHEMA.split(";") if s.strip()] if version < 1 else []
        for step in range(max(version, 1) + 1, SCHEMA_VERSION + 1):
            statements += _MIGRATIONS.get(step, [])
        previous = self.conn.isolation_level
        self.conn.isolation_level = None  # control manual: BEGIN/COMMIT explícitos
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in statements:
                    self.conn.execute(statement)
                self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
        finally:
            self.conn.isolation_level = previous

    # ------------------------------------------------------------------ canciones

    def all_tracks(self) -> list[Track]:
        rows = self.conn.execute(
            f"SELECT {_TRACK_COLUMNS} FROM tracks t ORDER BY t.sort_pos IS NULL, t.sort_pos, "
            "t.artist COLLATE NOCASE, t.album COLLATE NOCASE, t.title COLLATE NOCASE"
        ).fetchall()
        tracks = [_row_to_track(r, check=False) for r in rows]
        present = available_paths(t.path for t in tracks)
        for track in tracks:
            track.available = track.path in present
        return tracks

    def set_library_order(self, track_ids: list[int]) -> None:
        """Guarda el orden manual de «Canciones» (arrastrar para ordenar) en UNA transacción.
        Las que no están en la lista quedan sin posición: al final, en el orden de siempre."""
        with self.conn:
            self.conn.execute("UPDATE tracks SET sort_pos = NULL WHERE sort_pos IS NOT NULL")
            self.conn.executemany("UPDATE tracks SET sort_pos = ? WHERE id = ?", [(i, tid) for i, tid in enumerate(track_ids)])

    def clear_library_order(self) -> None:
        """Vuelve «Canciones» al orden de siempre (artista, álbum, título)."""
        with self.conn:
            self.conn.execute("UPDATE tracks SET sort_pos = NULL WHERE sort_pos IS NOT NULL")

    def has_library_order(self) -> bool:
        return self.conn.execute("SELECT 1 FROM tracks WHERE sort_pos IS NOT NULL LIMIT 1").fetchone() is not None

    def recent_tracks(self, limit: int = RECENT_LIMIT) -> list[Track]:
        rows = self.conn.execute(
            f"SELECT {_TRACK_COLUMNS} FROM tracks t "
            "ORDER BY COALESCE(t.last_played_at, t.added_at) DESC, t.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_track(r) for r in rows]

    def known_path_keys(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT path_key FROM tracks")}

    def add_tracks(self, scanned: Iterable[ScannedTrack]) -> tuple[list[str], list[str]]:
        """Inserta las pistas. Devuelve (rutas agregadas, rutas que ya existían)."""
        added: list[str] = []
        duplicates: list[str] = []
        now = _now()
        with self.conn:
            for item in scanned:
                self._store_cover(item.cover_hash, item.cover_bytes)
                meta = item.metadata
                cursor = self.conn.execute(
                    "INSERT OR IGNORE INTO tracks (path, path_key, title, artist, album, genre, "
                    "duration_ms, cover_hash, added_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.path,
                        item.key,
                        meta.title,
                        meta.artist,
                        meta.album,
                        meta.genre,
                        meta.duration_ms,
                        item.cover_hash,
                        now,
                    ),
                )
                (added if cursor.rowcount else duplicates).append(item.path)
        return added, duplicates

    def _store_cover(self, digest: str | None, data: bytes | None) -> None:
        if digest and data:
            self.conn.execute(
                "INSERT OR IGNORE INTO covers (hash, data) VALUES (?, ?)", (digest, sqlite3.Binary(data))
            )

    def get_cover(self, digest: str) -> bytes | None:
        row = self.conn.execute("SELECT data FROM covers WHERE hash = ?", (digest,)).fetchone()
        return bytes(row[0]) if row else None

    def update_duration(self, track_id: int, duration_ms: int) -> None:
        with self.conn:
            self.conn.execute("UPDATE tracks SET duration_ms = ? WHERE id = ?", (duration_ms, track_id))

    def mark_played(self, track_id: int) -> str:
        now = _now()
        with self.conn:
            self.conn.execute(
                "UPDATE tracks SET last_played_at = ?, play_count = play_count + 1 WHERE id = ?",
                (now, track_id),
            )
        return now

    def track_id_for_path(self, path: str) -> int | None:
        row = self.conn.execute("SELECT id FROM tracks WHERE path_key = ?", (path_key(path),)).fetchone()
        return row[0] if row else None

    def relocate_track(
        self,
        track_id: int,
        new_path: str,
        metadata: AudioMetadata,
        cover_digest: str | None,
        cover_bytes: bytes | None,
    ) -> None:
        """Cambia la ruta de una canción conservando su id (y por tanto sus playlists).

        Conserva el título, artista, álbum y género de la biblioteca (pueden ser correcciones
        del usuario o de «Datos en internet»); del archivo nuevo solo toma la duración y,
        si la canción no tenía, la carátula.
        """
        other = self.track_id_for_path(new_path)
        if other is not None and other != track_id:
            raise DuplicatePathError("Ese archivo ya está en la biblioteca como otra canción.")
        with self.conn:
            self._store_cover(cover_digest, cover_bytes)
            self.conn.execute(
                "UPDATE tracks SET path = ?, path_key = ?, "
                "duration_ms = CASE WHEN ? > 0 THEN ? ELSE duration_ms END, "
                "cover_hash = COALESCE(cover_hash, ?) WHERE id = ?",
                (
                    new_path,
                    path_key(new_path),
                    metadata.duration_ms,
                    metadata.duration_ms,
                    cover_digest if cover_bytes else None,
                    track_id,
                ),
            )

    # ------------------------------------------------------------------ sonoridad

    def save_loudness(self, results: list[tuple[int, float | None, float | None]]) -> None:
        """Guarda la medición (LUFS, pico real) de varias canciones en una transacción."""
        now = _now()
        with self.conn:
            self.conn.executemany(
                "UPDATE tracks SET loudness_lufs = ?, true_peak_db = ?, analyzed_at = ? WHERE id = ?",
                [(lufs, peak, now, track_id) for track_id, lufs, peak in results],
            )

    def set_norm_gains(self, gains: list[tuple[int, float]]) -> None:
        """Ganancia de normalización (dB) que el reproductor aplica al sonar. 0 = sin ajuste."""
        with self.conn:
            self.conn.executemany("UPDATE tracks SET norm_gain_db = ? WHERE id = ?", [(g, i) for i, g in gains])

    def update_track_paths(self, changes: list[tuple[int, str]]) -> int:
        """Cambia solo la ruta de varias canciones en UNA transacción (conservan id, datos y playlists).
        Lo usa la carpeta de revisión de repetidas, que ya movió los archivos."""
        with self.conn:
            for track_id, new_path in changes:
                self.conn.execute(
                    "UPDATE tracks SET path = ?, path_key = ? WHERE id = ?", (new_path, path_key(new_path), track_id)
                )
        return len(changes)

    def with_raw_text(self, tracks: list[Track]) -> list[Track]:
        """Las mismas canciones con título, artista, álbum y género tal como están guardados (sin el ‹ ›
        de pantalla): para lo que se ESCRIBE (etiquetas de un MP3 convertido, la biblioteca)."""
        ids = [t.id for t in tracks]
        raw: dict[int, sqlite3.Row] = {}
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            marks = ",".join("?" * len(chunk))
            for row in self.conn.execute(f"SELECT id, title, artist, album, genre FROM tracks WHERE id IN ({marks})", chunk):
                raw[row["id"]] = row
        return [t.copy(title=raw[t.id]["title"], artist=raw[t.id]["artist"], album=raw[t.id]["album"], genre=raw[t.id]["genre"])
                if t.id in raw else t for t in tracks]

    def update_track_info(
        self,
        track_id: int,
        title: str,
        artist: str,
        album: str,
        cover_digest: str | None = None,
        cover_bytes: bytes | None = None,
    ) -> None:
        """Cambia título, artista, álbum y (opcionalmente) carátula en la biblioteca.
        No toca el archivo de audio."""
        self.update_tracks_info([(track_id, title, artist, album, cover_digest, cover_bytes)])

    def update_tracks_info(
        self, updates: list[tuple[int, str, str, str, str | None, bytes | None]]
    ) -> int:
        """Aplica varios cambios de datos en UNA transacción: o se guardan todos o ninguno."""
        with self.conn:
            for track_id, title, artist, album, digest, data in updates:
                self._store_cover(digest, data)
                self.conn.execute(
                    "UPDATE tracks SET title = ?, artist = ?, album = ?, cover_hash = COALESCE(?, cover_hash) "
                    "WHERE id = ?",
                    (title, artist, album, digest if data else None, track_id),
                )
        return len(updates)

    def remove_tracks(self, track_ids: Iterable[int]) -> int:
        """Quita canciones de la biblioteca (y de sus playlists). No toca los archivos."""
        with self.conn:
            return self._delete_tracks(track_ids)

    def _delete_tracks(self, track_ids: Iterable[int]) -> int:
        """Borrado sin confirmar la transacción: lo usa quien ya abrió una."""
        ids = list(set(track_ids))
        if not ids:
            return 0
        cursor = self.conn.executemany("DELETE FROM tracks WHERE id = ?", [(i,) for i in ids])
        removed = cursor.rowcount
        self.conn.execute(
            "DELETE FROM covers WHERE hash NOT IN (SELECT cover_hash FROM tracks WHERE cover_hash IS NOT NULL)"
        )
        return removed

    def merge_duplicates(self, keep_id: int, remove_ids: Iterable[int]) -> int:
        """Quita copias repetidas de la biblioteca y pasa sus playlists a la copia conservada.

        Si una playlist ya tenía la copia conservada (u otra copia ya redirigida), la entrada
        sobrante se elimina para no crear repeticiones que el usuario no eligió.
        Devuelve cuántas canciones se quitaron. No toca los archivos.
        """
        return self.merge_duplicate_groups([(keep_id, list(remove_ids))])

    def merge_duplicate_groups(self, groups: list[tuple[int, list[int]]]) -> int:
        """Fusiona varios grupos de repetidas en UNA transacción: si algo falla,
        ni las playlists ni la biblioteca cambian."""
        with self.conn:
            return sum(self._merge_group(keep_id, remove_ids) for keep_id, remove_ids in groups)

    def _merge_group(self, keep_id: int, remove_ids: Iterable[int]) -> int:
        """Un grupo de repetidas; se llama dentro de la transacción de merge_duplicate_groups."""
        ids = [i for i in set(remove_ids) if i != keep_id]
        if not ids:
            return 0
        marks = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT id, playlist_id, track_id FROM playlist_tracks "
            f"WHERE track_id = ? OR track_id IN ({marks}) ORDER BY position, id",
            [keep_id, *ids],
        ).fetchall()
        has_keep = {r["playlist_id"] for r in rows if r["track_id"] == keep_id}
        to_update, to_delete = [], []
        for row in rows:
            if row["track_id"] == keep_id:
                continue
            if row["playlist_id"] in has_keep:
                to_delete.append((row["id"],))
            else:
                has_keep.add(row["playlist_id"])
                to_update.append((keep_id, row["id"]))
        self.conn.executemany("UPDATE playlist_tracks SET track_id = ? WHERE id = ?", to_update)
        self.conn.executemany("DELETE FROM playlist_tracks WHERE id = ?", to_delete)
        return self._delete_tracks(ids)

    # ------------------------------------------------------------------ playlists

    def playlists(self) -> list[Playlist]:
        rows = self.conn.execute(
            "SELECT p.id, p.name, COUNT(pt.id) AS n FROM playlists p "
            "LEFT JOIN playlist_tracks pt ON pt.playlist_id = p.id "
            "GROUP BY p.id ORDER BY p.name COLLATE NOCASE"
        ).fetchall()
        return [Playlist(r["id"], no_markup(r["name"]), r["n"]) for r in rows]  # de antes, o restauradas

    def playlist(self, playlist_id: int) -> Playlist | None:
        return next((p for p in self.playlists() if p.id == playlist_id), None)

    def _clean_name(self, name: str, exclude_id: int | None = None) -> tuple[str, str]:
        clean = " ".join((name or "").split())
        if not clean:
            raise PlaylistNameError("Escribe un nombre para la playlist.")
        if len(clean) > MAX_PLAYLIST_NAME:
            raise PlaylistNameError(f"El nombre no puede superar los {MAX_PLAYLIST_NAME} caracteres.")
        key = normalize_text(clean)
        row = self.conn.execute("SELECT id, name FROM playlists WHERE name_key = ?", (key,)).fetchone()
        if row and row["id"] != exclude_id:
            raise PlaylistNameError(f"Ya existe una playlist llamada «{row['name']}».")
        return clean, key

    def create_playlist(self, name: str) -> Playlist:
        clean, key = self._clean_name(name)
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO playlists (name, name_key, created_at) VALUES (?, ?, ?)", (clean, key, _now())
            )
        return Playlist(cursor.lastrowid, clean, 0)

    def rename_playlist(self, playlist_id: int, name: str) -> str:
        clean, key = self._clean_name(name, exclude_id=playlist_id)
        with self.conn:
            self.conn.execute(
                "UPDATE playlists SET name = ?, name_key = ? WHERE id = ?", (clean, key, playlist_id)
            )
        return clean

    def delete_playlist(self, playlist_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))

    def playlist_tracks(self, playlist_id: int) -> list[Track]:
        rows = self.conn.execute(
            f"SELECT {_TRACK_COLUMNS}, pt.id AS entry_id FROM playlist_tracks pt "
            "JOIN tracks t ON t.id = pt.track_id WHERE pt.playlist_id = ? ORDER BY pt.position, pt.id",
            (playlist_id,),
        ).fetchall()
        return [_row_to_track(r) for r in rows]

    def playlist_contains(self, playlist_id: int, track_ids: Iterable[int]) -> set[int]:
        ids = set(track_ids)
        rows = self.conn.execute(
            "SELECT DISTINCT track_id FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,)
        ).fetchall()
        return {r[0] for r in rows} & ids

    def playlist_entries_of(self, track_ids: Iterable[int]) -> int:
        """Cuántas entradas de playlists son de estas canciones (para avisar antes de quitarlas)."""
        ids = list(set(track_ids))
        total = 0
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            marks = ",".join("?" * len(chunk))
            total += self.conn.execute(f"SELECT COUNT(*) FROM playlist_tracks WHERE track_id IN ({marks})", chunk).fetchone()[0]
        return total

    def reorder_playlist(self, playlist_id: int, entry_ids: list[int]) -> None:
        """Guarda el orden elegido a mano (ids de entrada: una canción puede estar repetida).
        Debe nombrar exactamente las entradas de la playlist; si no (cambió mientras tanto), no toca nada."""
        current = {r[0] for r in self.conn.execute("SELECT id FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))}
        if len(entry_ids) != len(current) or set(entry_ids) != current:
            raise ValueError("La playlist cambió mientras se reordenaba.")
        with self.conn:
            self.conn.executemany(
                "UPDATE playlist_tracks SET position = ? WHERE id = ?", [(i, eid) for i, eid in enumerate(entry_ids)]
            )

    def add_to_playlist(self, playlist_id: int, track_ids: list[int], allow_duplicates: bool = False) -> int:
        """Agrega canciones al final. Sin allow_duplicates omite las que ya están."""
        if allow_duplicates:
            to_add = list(track_ids)
        else:
            existing = self.playlist_contains(playlist_id, track_ids)
            to_add, seen = [], set(existing)
            for tid in track_ids:
                if tid not in seen:
                    seen.add(tid)
                    to_add.append(tid)
        if not to_add:
            return 0
        row = self.conn.execute(
            "SELECT COALESCE(MAX(position), -1) FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,)
        ).fetchone()
        start = row[0] + 1
        now = _now()
        with self.conn:
            self.conn.executemany(
                "INSERT INTO playlist_tracks (playlist_id, track_id, position, added_at) VALUES (?, ?, ?, ?)",
                [(playlist_id, tid, start + i, now) for i, tid in enumerate(to_add)],
            )
        return len(to_add)

    def remove_playlist_entries(self, entry_ids: Iterable[int]) -> int:
        """Quita entradas concretas de una playlist. Los archivos no se tocan."""
        ids = [(i,) for i in set(entry_ids) if i is not None]
        if not ids:
            return 0
        with self.conn:
            cursor = self.conn.executemany("DELETE FROM playlist_tracks WHERE id = ?", ids)
        return cursor.rowcount
