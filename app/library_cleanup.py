"""Quitar de la biblioteca las canciones cuyo archivo ya no existe (sin ventanas).

Reglas para no perder nada por error:
- Solo se quitan si el disco (o la carpeta de red) donde estaban está disponible: si es un USB, un disco
  externo o una unidad de red desconectados, sus canciones se conservan hasta que vuelvan.
- Si en un disco falta más de la mitad de sus canciones (y son bastantes), es sospechoso (p. ej. Windows le
  cambió la letra al disco): no se quitan solas, se pregunta.
- Nunca se quitan canciones de una operación que todavía se puede deshacer (Historial): deshacerla las
  devuelve a su sitio.
- Solo se tocan la biblioteca y las playlists: los archivos de música no se modifican.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .models import Track

SUSPICIOUS_MIN = 20  # a partir de cuántas faltantes en un mismo disco se mira la proporción
SUSPICIOUS_RATIO = 0.5


def location_root(path: str) -> str:
    """Raíz del disco o de la carpeta de red: «D:\\» o «\\\\servidor\\recurso\\»."""
    drive, _rest = os.path.splitdrive(os.path.abspath(path))
    return drive + os.sep if drive else os.sep


MISSING_FOLDER_MIN = 10  # una carpeta entera que falta con tantas canciones: ¿se movió? Se pregunta.


@dataclass
class MissingPlan:
    remove: list[Track] = field(default_factory=list)  # se quitan solas
    suspicious: dict[str, list[Track]] = field(default_factory=dict)  # raíz → faltantes (preguntar)
    missing_folders: dict[str, list[Track]] = field(default_factory=dict)  # carpeta que no está → sus canciones
    disconnected: dict[str, int] = field(default_factory=dict)  # raíz → canciones conservadas
    protected: int = 0  # parte de una operación que se puede deshacer


def missing_folder(path: str) -> str | None:
    """La carpeta más alta que ya no existe en la ruta del archivo (None si su carpeta existe)."""
    folder = os.path.dirname(os.path.abspath(path))
    if os.path.isdir(folder):
        return None
    while True:
        parent = os.path.dirname(folder)
        if parent == folder or os.path.isdir(parent):
            return folder
        folder = parent


def plan_missing(tracks: list[Track], protected_ids: set[int]) -> MissingPlan:
    plan = MissingPlan()
    by_root: dict[str, list[Track]] = {}
    for track in tracks:
        by_root.setdefault(location_root(track.path), []).append(track)
    for root, on_root in by_root.items():
        missing = [t for t in on_root if not os.path.isfile(t.path)]
        if not missing:
            continue
        if not os.path.exists(root):
            plan.disconnected[root] = len(missing)
            continue
        candidates = [t for t in missing if t.id not in protected_ids]
        plan.protected += len(missing) - len(candidates)
        if len(candidates) >= SUSPICIOUS_MIN and len(candidates) > SUSPICIOUS_RATIO * len(on_root):
            plan.suspicious[root] = candidates
            continue
        # Una carpeta entera que falta con muchas canciones probablemente se movió o se renombró:
        # se pregunta (y se ofrece buscarla) en vez de quitarlas.
        by_folder: dict[str, list[Track]] = {}
        loose: list[Track] = []
        for track in candidates:
            folder = missing_folder(track.path)
            (by_folder.setdefault(folder, []) if folder else loose).append(track)
        for folder, in_folder in by_folder.items():
            if len(in_folder) >= MISSING_FOLDER_MIN:
                plan.missing_folders[folder] = in_folder
            else:
                loose.extend(in_folder)
        plan.remove.extend(loose)
    return plan


def relocate_folder(tracks: list[Track], old_folder: str, new_folder: str) -> list[tuple[int, str]]:
    """Rutas nuevas de las canciones de una carpeta movida, solo para los archivos que existen ahí."""
    changes = []
    for track in tracks:
        relative = os.path.relpath(track.path, old_folder)
        candidate = os.path.join(new_folder, relative)
        if os.path.isfile(candidate):
            changes.append((track.id, candidate))
    return changes
