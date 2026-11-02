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

from .metadata import MetadataError, read_metadata
from .models import Track
from .title_format import strip_noise
from .utils import normalize_text, path_key

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


DURATION_MARGIN_MS = 2000  # la misma canción con otro nombre dura lo mismo


def _bare_name(path: str) -> tuple[str, str]:
    stem, ext = os.path.splitext(os.path.basename(path))
    return normalize_text(strip_noise(stem)), ext.lower()


def find_renamed(tracks: list[Track]) -> list[tuple[Track, str]]:
    """Canciones cuyo archivo se renombró por fuera solo quitándole signos o numeración del inicio
    («¿A quién….mp3» → «A quién….mp3», «4ª En el….mp3» → «En el….mp3»). Tiene que haber un único archivo posible,
    fuera de la biblioteca y de la misma duración: ante la duda, no se reconecta. Solo mira; no cambia nada."""
    by_folder: dict[str, list[Track]] = {}
    for track in tracks:
        if not os.path.isfile(track.path):
            by_folder.setdefault(os.path.dirname(track.path), []).append(track)
    known = {path_key(t.path) for t in tracks}
    found = []
    for folder, missing in by_folder.items():
        try:
            with os.scandir(folder) as entries:
                loose = [e.path for e in entries if e.is_file() and path_key(e.path) not in known]
        except OSError:
            continue  # carpeta que ya no existe o disco desconectado
        names: dict[tuple[str, str], list[str]] = {}
        for path in loose:
            names.setdefault(_bare_name(path), []).append(path)
        wanted: dict[tuple[str, str], list[Track]] = {}
        for track in missing:
            wanted.setdefault(_bare_name(track.path), []).append(track)
        for name, claiming in wanted.items():
            candidates = names.get(name, [])
            if len(candidates) == 1 and len(claiming) == 1 and _same_length(claiming[0], candidates[0]):
                found.append((claiming[0], candidates[0]))
    return found


def _same_length(track: Track, path: str) -> bool:
    try:
        return abs(read_metadata(path).duration_ms - track.duration_ms) <= DURATION_MARGIN_MS
    except (MetadataError, OSError):
        return False


def relocate_folder(tracks: list[Track], old_folder: str, new_folder: str) -> list[tuple[int, str]]:
    """Rutas nuevas de las canciones de una carpeta movida, solo para los archivos que existen ahí."""
    changes = []
    for track in tracks:
        relative = os.path.relpath(track.path, old_folder)
        candidate = os.path.join(new_folder, relative)
        if os.path.isfile(candidate):
            changes.append((track.id, candidate))
    return changes


# Temporales que el programa crea junto a la música y renombra al terminar. Si quedan (corte de luz o
# cierre forzado a mitad de una conversión, un ajuste de volumen o un movimiento a otro disco) son
# siempre copias a medias: el archivo original sigue entero en su sitio, así que se pueden borrar.
LEFTOVER_SUFFIXES = (".convirtiendo.tmp", ".ajuste-volumen.tmp", ".moviendo.tmp", ".limpiando-titulo.mp3", ".restaurando.tmp")


def remove_leftover_temps(tracks: list[Track]) -> list[str]:
    """Borra esos temporales de las carpetas de la biblioteca. Devuelve los borrados. Solo toca archivos
    con exactamente esas terminaciones; nunca otros archivos."""
    removed: list[str] = []
    for folder in {os.path.dirname(t.path) for t in tracks}:
        try:
            with os.scandir(folder) as entries:
                leftovers = [e.path for e in entries if e.is_file() and e.name.lower().endswith(LEFTOVER_SUFFIXES)]
        except OSError:
            continue  # carpeta que ya no existe o disco desconectado
        for path in leftovers:
            try:
                os.remove(path)
                removed.append(path)
            except OSError:
                pass  # en uso (otra copia del programa trabajando con él): se intenta la próxima vez
    return removed
