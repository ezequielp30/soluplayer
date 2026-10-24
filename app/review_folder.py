"""Reunir canciones repetidas en una carpeta de revisión, y devolverlas a su lugar.

Es la única función del programa que MUEVE archivos del usuario, y solo cuando él lo pide:
- Solo dentro del mismo disco y en discos fijos locales: mover es un renombrado instantáneo,
  sin copiar datos, así que no hay riesgo de perder un archivo a mitad de camino.
- Cada movimiento se anota en un registro (JSON) ANTES y DESPUÉS de hacerlo. Si el programa se
  cierra a mitad, el registro queda «en curso» y al abrirlo se ofrece devolver todo.
- La biblioteca actualiza las rutas conservando el id de cada canción (playlists intactas).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import journal
from .duplicates import DuplicateGroup
from .file_ops import trash_block_reason
from .metadata import UNKNOWN_ARTIST, audio_quality
from .models import Track
from .utils import format_time

log = logging.getLogger(__name__)

REVIEW_FOLDER_NAME = "_Repetidas para revisar"
README_NAME = "LEEME.txt"
MAX_PATH = 240  # margen bajo el límite clásico de 260 caracteres de Windows
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}

STATUS_RUNNING, STATUS_DONE, STATUS_UNDONE = journal.STATUS_RUNNING, journal.STATUS_DONE, journal.STATUS_UNDONE


# ---------------------------------------------------------------------- nombres


def safe_name(text: str, limit: int = 80) -> str:
    """Nombre válido en Windows: sin caracteres prohibidos, sin punto/espacio final, no reservado."""
    clean = " ".join(_INVALID.sub("_", text).split()).strip(" .")
    clean = clean[:limit].rstrip(" .") or "sin nombre"
    return f"_{clean}" if clean.split(".")[0].upper() in _RESERVED else clean


def _unique(path: Path, taken: set[str]) -> Path:
    candidate, n = path, 2
    while candidate.exists() or str(candidate).lower() in taken:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    taken.add(str(candidate).lower())
    return candidate


def _fit(folder: Path, stem: str, ext: str) -> Path:
    """Recorta el nombre para que la ruta completa no pase de MAX_PATH."""
    room = MAX_PATH - len(str(folder)) - len(ext) - 8
    return folder / f"{stem[:max(12, room)].rstrip(' .')}{ext}"


# ---------------------------------------------------------------------- plan


@dataclass
class Move:
    track_id: int
    source: str
    target: str
    done: bool = False


@dataclass
class Skipped:
    path: str
    reason: str


@dataclass
class Session:
    id: str
    destination: str
    status: str
    created_at: str
    moves: list[Move] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)  # subcarpetas creadas (para limpiarlas al deshacer)

    @property
    def manifest_path(self) -> Path:
        return sessions_dir() / f"reunion-{self.id}.json"

    def save(self) -> None:
        journal.write_atomic(self.manifest_path, asdict(self))

    @staticmethod
    def load(path: Path) -> "Session":
        data = journal.read(path)
        data["moves"] = [Move(**m) for m in data.get("moves", [])]
        return Session(**data)

    def moved(self) -> list[Move]:
        """Movimientos hechos, incluidos los que el registro no llegó a anotar (cierre inesperado)."""
        return [m for m in self.moves if m.done or journal.was_moved(m.source, m.target)]


def sessions_dir() -> Path:
    return journal.journal_dir("reuniones")


def list_sessions() -> list[Session]:
    return journal.load_all(sessions_dir(), "reunion-*.json", Session.load)


def interrupted_sessions() -> list[Session]:
    return [s for s in list_sessions() if s.status == STATUS_RUNNING]


def default_destination(tracks: list[Track]) -> str:
    """Carpeta raíz común de la música (p. ej. D:\\Musica Cristiana) + «_Repetidas para revisar»."""
    folders = [os.path.dirname(t.path) for t in tracks if t.path]
    try:
        common = os.path.commonpath(folders) if folders else str(Path.home() / "Music")
    except ValueError:  # carpetas en discos distintos: se usa la de la primera canción
        common = folders[0]
    return os.path.join(common, REVIEW_FOLDER_NAME)


def _same_drive(a: str, b: str) -> bool:
    return os.path.splitdrive(os.path.abspath(a))[0].lower() == os.path.splitdrive(os.path.abspath(b))[0].lower()


def plan_moves(groups: list[DuplicateGroup], destination: str) -> tuple[Session, list[Skipped]]:
    """Calcula los movimientos sin tocar nada. Devuelve la sesión planificada y lo que se omite."""
    destination = os.path.abspath(destination)
    skipped: list[Skipped] = []
    blocked = trash_block_reason(destination)  # la misma regla: solo discos fijos locales
    session = Session(
        id=journal.new_id(sessions_dir(), "reunion"),
        destination=destination,
        status=STATUS_RUNNING,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    taken: set[str] = set()
    used_folders: set[str] = set()
    root = Path(destination)
    for group in groups:
        keep = group.keep
        label = keep.title if keep.artist == UNKNOWN_ARTIST else f"{keep.title} - {keep.artist}"
        folder = root / safe_name(label, 70)
        n = 2
        while str(folder).lower() in used_folders:
            folder = root / f"{safe_name(label, 66)} ({n})"
            n += 1
        used_folders.add(str(folder).lower())
        planned_any = False
        for index, track in enumerate(group.tracks, start=1):
            if blocked:
                skipped.append(Skipped(track.path, "La carpeta de destino no está en un disco local fijo."))
                continue
            if not os.path.isfile(track.path):
                skipped.append(Skipped(track.path, "El archivo no se encuentra."))
                continue
            if not _same_drive(track.path, destination):
                skipped.append(Skipped(track.path, "Está en otro disco: solo se mueve dentro del mismo disco."))
                continue
            if trash_block_reason(track.path):
                skipped.append(Skipped(track.path, "Está en una unidad de red o extraíble."))
                continue
            if os.path.commonpath([os.path.abspath(track.path), destination]) == destination:
                skipped.append(Skipped(track.path, "Ya está dentro de la carpeta de revisión."))
                continue
            stem, ext = os.path.splitext(os.path.basename(track.path))
            origin = os.path.basename(os.path.dirname(track.path))
            target = _unique(_fit(folder, safe_name(f"{index} - {stem} (de «{origin}»)", 150), ext.lower()), taken)
            session.moves.append(Move(track.id, os.path.abspath(track.path), str(target)))
            planned_any = True
        if planned_any:
            session.folders.append(str(folder))
    return session, skipped


# ---------------------------------------------------------------------- ejecutar


def write_readme(folder: Path, group: DuplicateGroup, moves: dict[int, Move]) -> None:
    lines = [
        f"Canción repetida: {group.keep.title} — {group.keep.artist}",
        f"Reunida el {datetime.now():%d/%m/%Y %H:%M} por Reproductor de Música.",
        "",
        "Para devolver todos los archivos a su carpeta original:",
        "  Reproductor de Música → Herramientas → Historial de cambios en archivos → Deshacer.",
        "",
    ]
    for index, track in enumerate(group.tracks, start=1):
        move = moves.get(track.id)
        current = move.target if move else track.path
        quality = audio_quality(current)
        size = os.path.getsize(current) / 1_048_576 if os.path.isfile(current) else 0
        mark = "  ← sugerida para conservar" if track.id == group.keep_id else ""
        lines += [
            f"[{index}] {os.path.basename(current)}{mark}",
            f"    Origen:   {move.source if move else track.path + ' (no se movió)'}",
            f"    Duración: {format_time(track.duration_ms) if track.duration_ms else '—'}   "
            f"Tamaño: {size:.1f} MB   Calidad: {quality.codec} {quality.text()}",
            "",
        ]
    (folder / README_NAME).write_text("\n".join(lines), encoding="utf-8-sig")  # con BOM: el Bloc de notas lo lee bien


def execute(session: Session, groups: list[DuplicateGroup], progress=None) -> tuple[Session, list[Skipped]]:
    """Mueve los archivos. El registro se guarda antes de empezar y tras cada archivo."""
    failed: list[Skipped] = []
    session.save()
    for number, move in enumerate(session.moves):
        if progress is not None and not progress(number, len(session.moves)):
            break
        try:
            os.makedirs(os.path.dirname(move.target), exist_ok=True)
            if os.path.exists(move.target):
                raise FileExistsError("ya existe un archivo con ese nombre en el destino")
            os.rename(move.source, move.target)  # mismo disco: renombrado instantáneo
            move.done = True
            session.save()
            log.info("Movido para revisión: %s → %s", move.source, move.target)
        except OSError as exc:
            reason = "Está abierto en otro programa." if isinstance(exc, PermissionError) else str(exc)
            failed.append(Skipped(move.source, reason))
            log.warning("No se movió %s: %s", move.source, exc)
    by_id = {m.track_id: m for m in session.moves if m.done}
    for group in groups:
        folder_moves = {t.id: by_id[t.id] for t in group.tracks if t.id in by_id}
        if folder_moves:
            folder = Path(next(iter(folder_moves.values())).target).parent
            try:
                write_readme(folder, group, folder_moves)
            except OSError as exc:
                log.warning("No se pudo escribir %s en %s: %s", README_NAME, folder, exc)
    session.moves = [m for m in session.moves if m.done]
    session.status = STATUS_DONE
    session.save()
    return session, failed


def undo(session: Session, on_restored=None) -> tuple[list[Move], list[Skipped]]:
    """Devuelve a su lugar los archivos de una reunión. Devuelve (devueltos, no devueltos).

    `on_restored(move)` actualiza la biblioteca de cada archivo en cuanto vuelve, ANTES de anotarlo en
    el registro: si fallara, el archivo se deja donde estaba (la biblioteca sigue apuntando ahí)."""
    restored: list[Move] = []
    problems: list[Skipped] = []
    for move in reversed(session.moved()):
        if not os.path.exists(move.target):
            problems.append(Skipped(move.target, "Ya no está en la carpeta de revisión (¿se envió a la Papelera o se movió?)."))
            continue
        if os.path.exists(move.source):
            problems.append(Skipped(move.target, f"En su lugar original ya hay otro archivo: {move.source}"))
            continue
        try:
            os.makedirs(os.path.dirname(move.source), exist_ok=True)
            os.rename(move.target, move.source)
            if on_restored is not None:
                try:
                    on_restored(move)
                except Exception as exc:
                    os.rename(move.source, move.target)
                    log.error("No se pudo actualizar la biblioteca al devolver %s: %s", move.source, exc)
                    problems.append(Skipped(move.target, f"No se pudo actualizar la biblioteca ({exc}); se dejó en la carpeta de revisión."))
                    continue
            move.done = False
            restored.append(move)
            session.save()
            log.info("Devuelto a su lugar: %s → %s", move.target, move.source)
        except OSError as exc:
            problems.append(Skipped(move.target, "Está abierto en otro programa." if isinstance(exc, PermissionError) else str(exc)))
    # Limpieza: solo LEEME.txt y carpetas que quedaron vacías (nunca se borra música).
    for folder in session.folders:
        readme = Path(folder) / README_NAME
        try:
            if readme.exists() and all(p.name == README_NAME for p in Path(folder).iterdir()):
                readme.unlink()
            Path(folder).rmdir()
        except OSError:
            pass
    try:
        Path(session.destination).rmdir()  # solo si quedó vacía
    except OSError:
        pass
    session.status = STATUS_UNDONE if not problems else STATUS_DONE
    session.save()
    return restored, problems
