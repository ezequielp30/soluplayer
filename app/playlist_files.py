"""Copias de las playlists en archivos M3U8 (uno por playlist) y su restauración.

Sin ventanas. M3U8 es el formato estándar: también lo abren VLC, Winamp, foobar2000 o el celular. Cada
archivo guarda el nombre real de la playlist (#PLAYLIST), y de cada canción su ruta completa y, en
#EXTINF, su duración, artista y título: así se encuentra aunque la música haya cambiado de carpeta.

Al restaurar nunca se borra nada: una playlist igual a la que ya existe se deja como está, y una con el
mismo nombre pero distinta entra como «Nombre (restaurada)». Al guardar, solo se escriben archivos
.m3u8 con el nombre de cada playlist; los demás archivos de la carpeta no se tocan.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .database import MAX_PLAYLIST_NAME, Database, PlaylistNameError
from .importer import scan_file
from .metadata import UNKNOWN_ARTIST
from .models import Track
from .review_folder import safe_name
from .utils import normalize_text, path_key

log = logging.getLogger(__name__)

EXTENSION = ".m3u8"
PREVIOUS_FOLDER = "Anteriores"  # versión anterior de una copia que perdió canciones (p. ej. al quitar faltantes)
_DURATION_SLACK_S = 3  # al buscar por título y artista, la duración puede diferir un poco (otra codificación)


@dataclass
class Entry:
    path: str
    title: str = ""  # «Artista - Título» tal como figura en #EXTINF
    duration_s: int = -1


@dataclass
class PlaylistFile:
    name: str
    entries: list[Entry] = field(default_factory=list)
    source: str = ""


@dataclass
class RestorePlan:
    name: str
    entries: list[Entry]
    found: int = 0  # canciones que se pueden poner (en la biblioteca, en el disco o por título)
    missing: int = 0


@dataclass
class RestoreOutcome:
    created: list[str] = field(default_factory=list)  # nombres con los que quedaron
    unchanged: list[str] = field(default_factory=list)  # ya estaban iguales (o ya se habían restaurado)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (nombre, motivo)
    added_tracks: int = 0  # canciones que se agregaron a la biblioteca (estaban en el disco)
    missing: int = 0


# ---------------------------------------------------------------------- guardar


def _label(track: Track) -> str:
    if track.artist and track.artist != UNKNOWN_ARTIST:
        return f"{track.artist} - {track.title}"
    return track.title


def render(name: str, tracks: list[Track]) -> str:
    lines = ["#EXTM3U", f"#PLAYLIST:{name}"]
    for t in tracks:
        seconds = round(t.duration_ms / 1000) if t.duration_ms and t.duration_ms > 0 else -1
        lines.append(f"#EXTINF:{seconds},{_label(t)}")
        lines.append(t.path)
    return "\n".join(lines) + "\n"


def export_all(db: Database, folder: str | Path) -> list[Path]:
    """Guarda cada playlist en `folder` (la crea si hace falta). Solo escribe las que cambiaron; si una no
    se puede escribir (abierta en otro programa, disco lleno) se sigue con las demás. Si una copia pierde
    canciones, su versión anterior queda en «Anteriores». Devuelve los archivos escritos."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    taken: set[str] = set()
    for playlist in db.playlists():
        stem = safe_name(playlist.name)
        name, n = stem, 2
        while name.casefold() in taken:  # dos nombres que en Windows quedarían iguales
            name, n = f"{stem} ({n})", n + 1
        taken.add(name.casefold())
        path = folder / f"{name}{EXTENSION}"
        content = render(playlist.name, db.playlist_tracks(playlist.id))
        try:
            old = path.read_text(encoding="utf-8-sig") if path.exists() else None
        except (OSError, UnicodeDecodeError):
            old = None
        if old == content:
            continue
        temp = path.with_name(path.name + ".tmp")
        try:
            if old is not None and _entries(old) - _entries(content):  # contando repeticiones
                # Pierde canciones: la versión anterior se guarda aparte (una sola, la última).
                previous = folder / PREVIOUS_FOLDER
                previous.mkdir(exist_ok=True)
                (previous / path.name).write_text(old, encoding="utf-8", newline="\r\n")
            temp.write_text(content, encoding="utf-8", newline="\r\n")  # CRLF: lo abre bien cualquier programa de Windows
            os.replace(temp, path)  # de una vez: un corte de luz no deja una copia a medias
        except OSError as exc:
            log.warning("No se pudo guardar la copia de la playlist «%s»: %s", playlist.name, exc)
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            continue
        written.append(path)
    return written


def _entries(text: str) -> Counter:
    return Counter(line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#"))


# ---------------------------------------------------------------------- leer


def read_file(path: str | Path) -> PlaylistFile:
    path = Path(path)
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")  # .m3u antiguo de otro reproductor
    result = PlaylistFile(name=path.stem, source=str(path))
    pending: Entry | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#PLAYLIST:"):
            result.name = line[len("#PLAYLIST:"):].strip() or result.name
        elif line.startswith("#EXTINF:"):
            seconds, _, label = line[len("#EXTINF:"):].partition(",")
            try:
                duration = int(float(seconds))
            except ValueError:
                duration = -1
            pending = Entry("", label.strip(), duration)
        elif not line.startswith("#"):
            location = line if os.path.isabs(line) else os.path.normpath(os.path.join(path.parent, line))
            entry = pending or Entry("")
            entry.path = location
            result.entries.append(entry)
            pending = None
    return result


def read_folder(folder: str | Path) -> list[PlaylistFile]:
    """Las playlists (.m3u8 y .m3u) de una carpeta. Las que no se pueden leer se omiten."""
    found: list[PlaylistFile] = []
    for path in sorted(Path(folder).iterdir()):
        if path.suffix.lower() in (".m3u8", ".m3u") and path.is_file():
            try:
                found.append(read_file(path))
            except OSError as exc:
                log.warning("No se pudo leer la playlist %s: %s", path, exc)
    return found


# ---------------------------------------------------------------------- restaurar


class _Finder:
    """Busca la canción de cada entrada: por ruta en la biblioteca, en el disco, o por título y duración."""

    def __init__(self, library: list[Track]) -> None:
        self.by_key = {path_key(t.path): t for t in library}
        self.labels: dict[str, list[Track]] = {}
        for t in library:
            self.labels.setdefault(normalize_text(_label(t)), []).append(t)

    def in_library(self, entry: Entry) -> Track | None:
        track = self.by_path(entry)
        if track is not None:
            return track
        if self.on_disk(entry):
            return None  # el archivo está en su ruta exacta: se agrega ese, no otro con el mismo título
        return self.by_label(entry)

    def by_path(self, entry: Entry) -> Track | None:
        return self.by_key.get(path_key(entry.path)) if entry.path else None

    def by_label(self, entry: Entry) -> Track | None:
        if not entry.title:
            return None
        for t in self.labels.get(normalize_text(entry.title), []):
            if entry.duration_s < 0 or t.duration_ms <= 0 or abs(t.duration_ms / 1000 - entry.duration_s) <= _DURATION_SLACK_S:
                return t
        return None

    def on_disk(self, entry: Entry) -> bool:
        return bool(entry.path) and os.path.isfile(entry.path)


def plan_restore(files: list[PlaylistFile], library: list[Track]) -> list[RestorePlan]:
    """Qué se podría restaurar de cada playlist (sin cambiar nada todavía)."""
    finder = _Finder(library)
    plans: list[RestorePlan] = []
    for f in files:
        plan = RestorePlan(f.name, f.entries)
        for entry in f.entries:
            if finder.in_library(entry) is not None or finder.on_disk(entry):
                plan.found += 1
            else:
                plan.missing += 1
        plans.append(plan)
    return plans


def apply_restore(db: Database, plans: list[RestorePlan]) -> RestoreOutcome:
    """Crea las playlists elegidas. Las canciones que están en el disco pero no en la biblioteca se agregan."""
    outcome = RestoreOutcome()
    finder = _Finder(db.all_tracks())
    to_import = sorted({e.path for p in plans for e in p.entries if finder.in_library(e) is None and finder.on_disk(e)})
    if to_import:
        scanned = [s for s in (scan_file(path)[0] for path in to_import) if s is not None]
        added, _duplicates = db.add_tracks(scanned)
        outcome.added_tracks = len(added)
        finder = _Finder(db.all_tracks())
    existing = {normalize_text(p.name): p for p in db.playlists()}
    for plan in plans:
        ids = []
        for entry in plan.entries:
            track = finder.in_library(entry)
            if track is None:
                outcome.missing += 1
            else:
                ids.append(track.id)
        full = " ".join(plan.name.split()) or "Playlist restaurada"
        base = full[:MAX_PLAYLIST_NAME]  # el límite de nombres; las de antes podían ser más largas
        # La misma (también con su nombre largo de antes), o una copia ya restaurada («Nombre (restaurada…)»)
        # con las mismas canciones: nada que hacer.
        short = normalize_text(base[:MAX_PLAYLIST_NAME - len(" (restaurada 999)")].rstrip())  # como queda acortada
        same_keys = {normalize_text(full), normalize_text(base)}
        twins = [p for key, p in existing.items() if key in same_keys or (key.startswith(short) and "(restaurada" in key)]
        if any([t.id for t in db.playlist_tracks(p.id)] == ids for p in twins):
            outcome.unchanged.append(plan.name)
            continue
        name = base
        if same_keys & existing.keys():
            n = 1
            while True:
                suffix = " (restaurada)" if n == 1 else f" (restaurada {n})"
                name = base[:MAX_PLAYLIST_NAME - len(suffix)].rstrip() + suffix
                if normalize_text(name) not in existing:
                    break
                n += 1
        try:
            playlist = db.create_playlist(name)
            if ids:
                db.add_to_playlist(playlist.id, ids, allow_duplicates=True)  # tal cual: con sus repeticiones y su orden
        except (PlaylistNameError, sqlite3.Error) as exc:
            outcome.failed.append((plan.name, str(exc)))
            continue
        existing[normalize_text(name)] = playlist
        outcome.created.append(name)
    return outcome
