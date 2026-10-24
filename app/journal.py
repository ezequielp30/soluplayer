"""Registro (diario) común de las operaciones que mueven o crean archivos del usuario.

Lo usan «Reunir repetidas» (`review_folder`) y «Convertir a MP3» (`converter`). Reglas comunes:
- Se escribe la INTENCIÓN (qué archivo va a dónde) antes de hacer el cambio, y el resultado después.
- Cada escritura es atómica: temporal + fsync + reemplazo. Un cierre inesperado nunca deja un registro
  a medias: queda el anterior o el nuevo.
- Un registro «en curso» al arrancar significa que la operación se interrumpió: se ofrece deshacerla.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, TypeVar

from .config import data_dir

log = logging.getLogger(__name__)

STATUS_RUNNING = "en curso"
STATUS_DONE = "completada"
STATUS_UNDONE = "deshecha"

T = TypeVar("T")


def journal_dir(name: str) -> Path:
    path = data_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_id(folder: Path, prefix: str) -> str:
    """Identificador con fecha y hora que no pisa un registro existente (dos operaciones en el mismo
    segundo reciben «…-2», «…-3»)."""
    base = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate, n = base, 2
    while (folder / f"{prefix}-{candidate}.json").exists():
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def write_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_all(folder: Path, pattern: str, loader: Callable[[Path], T]) -> list[T]:
    """Todos los registros de una carpeta, del más reciente al más antiguo (los ilegibles se ignoran)."""
    items: list[T] = []
    for path in sorted(folder.glob(pattern), reverse=True):
        try:
            items.append(loader(path))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            log.warning("Registro ilegible %s: %s", path, exc)
    return items


def was_moved(source: str, target: str) -> bool:
    """Reconciliación: el archivo está en el destino y ya no en el origen, aunque el registro no
    llegara a anotarlo (cierre inesperado justo después de moverlo)."""
    return bool(target) and os.path.exists(target) and not os.path.exists(source)
