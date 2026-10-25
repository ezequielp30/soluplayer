"""Registro de los renombres y movimientos de archivos hechos desde el programa, para el Historial.

Cada operación (renombrar un archivo, renombrar una carpeta, mover canciones) se guarda como una sesión
con sus cambios (de dónde a dónde). Deshacer hace el camino inverso: solo si el archivo sigue donde lo
dejó el programa y el lugar original está libre (nunca se pisa nada). Sin ventanas: la biblioteca la
actualiza app/file_operations.py.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import file_manager, journal

log = logging.getLogger(__name__)

KIND_RENAME_FILE = "renombrar"
KIND_RENAME_FOLDER = "renombrar-carpeta"
KIND_MOVE = "mover"
TITLES = {
    KIND_RENAME_FILE: "Renombrar archivo",
    KIND_RENAME_FOLDER: "Renombrar carpeta",
    KIND_MOVE: "Mover a otra carpeta",
}


@dataclass
class Change:
    source: str
    target: str
    track_ids: list[int] = field(default_factory=list)  # canciones que pasaron de source a target
    undone: bool = False


@dataclass
class FileSession:
    id: str
    kind: str
    created_at: str
    status: str
    changes: list[Change] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return sessions_dir() / f"archivos-{self.id}.json"

    def save(self) -> None:
        journal.write_atomic(self.path, asdict(self))

    @staticmethod
    def load(path: Path) -> "FileSession":
        data = journal.read(path)
        data["changes"] = [Change(**c) for c in data.get("changes", [])]
        return FileSession(**data)

    def pending(self) -> list[Change]:
        """Cambios que todavía se pueden deshacer (el resultado sigue ahí y el lugar original está libre)."""
        return [c for c in self.changes if not c.undone and os.path.exists(c.target) and not _taken(c)]


def sessions_dir() -> Path:
    return journal.journal_dir("archivos")


def record(kind: str, changes: list[Change]) -> FileSession | None:
    """Anota una operación ya hecha. Si no se puede anotar, la operación queda hecha igual (solo no
    aparecerá en el Historial)."""
    if not changes:
        return None
    session = FileSession(
        id=journal.new_id(sessions_dir(), "archivos"),
        kind=kind,
        created_at=datetime.now().isoformat(timespec="seconds"),
        status=journal.STATUS_DONE,
        changes=changes,
    )
    try:
        session.save()
    except OSError as exc:
        log.warning("No se pudo anotar en el Historial %s: %s", kind, exc)
        return None
    return session


def begin(kind: str, planned: list[Change]) -> FileSession | None:
    """Anota el plan ANTES de empezar («en curso»): si se corta la luz a mitad, al abrir se sabe qué
    archivos llegaron a moverse (ver FileOperations.reconcile_interrupted_moves)."""
    if not planned:
        return None
    session = FileSession(
        id=journal.new_id(sessions_dir(), "archivos"),
        kind=kind,
        created_at=datetime.now().isoformat(timespec="seconds"),
        status=journal.STATUS_RUNNING,
        changes=planned,
    )
    try:
        session.save()
    except OSError as exc:
        log.warning("No se pudo anotar el plan de %s: %s", kind, exc)
        return None
    return session


def finish(session: FileSession, done: list[Change]) -> None:
    """Termina una sesión empezada con begin(): quedan solo los cambios hechos. Sin ninguno, se borra."""
    try:
        if done:
            session.changes = done
            session.status = journal.STATUS_DONE
            session.save()
        else:
            session.path.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("No se pudo cerrar el registro de %s: %s", session.kind, exc)


def list_sessions() -> list[FileSession]:
    return journal.load_all(sessions_dir(), "archivos-*.json", FileSession.load)


def interrupted_sessions() -> list[FileSession]:
    return [s for s in list_sessions() if s.status == journal.STATUS_RUNNING]


def undo(session: FileSession, on_restored) -> tuple[list[Change], list[str]]:
    """Devuelve cada archivo (o carpeta) a donde estaba. `on_restored(change)` actualiza la biblioteca en
    cuanto cada uno vuelve; si falla, ese archivo se deja otra vez donde estaba. Devuelve (deshechos, problemas)."""
    restored: list[Change] = []
    problems: list[str] = []
    for change in reversed(session.changes):
        if change.undone:
            continue
        name = os.path.basename(change.target.rstrip("\\/"))
        if not os.path.exists(change.target):
            problems.append(f"{name}: ya no está donde lo dejó el programa.")
            continue
        if _taken(change):
            problems.append(f"{name}: ya hay otro elemento en su lugar original; no se tocó nada.")
            continue
        try:
            os.makedirs(os.path.dirname(change.source.rstrip("\\/")), exist_ok=True)  # la carpeta original pudo borrarse
            if os.path.isdir(change.target) or _same_drive(change.source, change.target):
                os.rename(change.target, change.source)
            else:
                result = file_manager.move_files([change.target], os.path.dirname(change.source))
                if not result.moved:
                    problems.append(f"{name}: {result.failed[0][1] if result.failed else 'no se pudo devolver'}")
                    continue
                if os.path.basename(change.source) != os.path.basename(change.target):
                    os.rename(os.path.join(os.path.dirname(change.source), os.path.basename(change.target)), change.source)
        except OSError as exc:
            problems.append(f"{name}: {file_manager.explain(exc, name)}")
            continue
        try:
            on_restored(change)
        except Exception as exc:
            log.error("No se pudo actualizar la biblioteca al deshacer %s: %s", change.target, exc)
            try:
                os.rename(change.source, change.target)  # todo como estaba
            except OSError:
                pass
            problems.append(f"{name}: no se pudo actualizar la biblioteca ({exc}); no se tocó nada.")
            continue
        change.undone = True
        restored.append(change)
        session.save()
    session.status = journal.STATUS_UNDONE if all(c.undone for c in session.changes) else journal.STATUS_DONE
    session.save()
    return restored, problems


def _taken(change: Change) -> bool:
    """El lugar original está ocupado por OTRO elemento. Un renombre que solo cambió mayúsculas no cuenta:
    en Windows origen y destino son el mismo archivo."""
    return os.path.exists(change.source) and os.path.normcase(change.source) != os.path.normcase(change.target)


def _same_drive(a: str, b: str) -> bool:
    return os.path.splitdrive(os.path.abspath(a))[0].lower() == os.path.splitdrive(os.path.abspath(b))[0].lower()
