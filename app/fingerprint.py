"""Huella digital del audio con `fpcalc` (Chromaprint). Solo lee los archivos."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import resource_path
from .utils import long_path

_TIMEOUT_S = 120
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class ToolMissing(Exception):
    """No está `fpcalc`: es un problema del programa, no del archivo. No hay que marcar nada como dañado."""


class DamagedFile(Exception):
    """`fpcalc` no pudo leer el audio. El texto se le muestra a la persona."""


@dataclass(frozen=True)
class Fingerprint:
    duration_s: float
    value: str


def tool_path() -> Path:
    """Junto al programa instalado o, al trabajar desde el código, donde lo deja `tools/obtener_fpcalc.py`."""
    for candidate in (resource_path("fpcalc", "fpcalc.exe"), resource_path("build", "herramientas", "fpcalc.exe")):
        if candidate.is_file():
            return candidate
    raise ToolMissing("Falta el componente fpcalc: vuelve a instalar el programa.")


def compute(path: str) -> Fingerprint:
    try:
        done = subprocess.run(
            [str(tool_path()), "-json", long_path(path)],
            capture_output=True, timeout=_TIMEOUT_S, creationflags=_NO_WINDOW, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise DamagedFile("El archivo tarda demasiado en leerse: podría estar dañado.") from exc
    except FileNotFoundError as exc:  # el archivo de música sí lo revisa fpcalc: lo que falta aquí es fpcalc
        raise ToolMissing("No se pudo ejecutar fpcalc: vuelve a instalar el programa.") from exc
    except OSError as exc:
        raise DamagedFile(f"No se pudo leer el archivo ({exc.strerror or exc}).") from exc
    if b"Empty fingerprint" in done.stderr:
        raise DamagedFile("Dura muy poco (menos de 3 segundos) para reconocerla por su sonido.")
    if done.returncode != 0:
        raise DamagedFile("No se pudo leer el audio: el archivo parece dañado.")
    try:
        data = json.loads(done.stdout)
        duration, value = float(data["duration"]), str(data["fingerprint"])
    except (ValueError, KeyError, TypeError) as exc:
        raise DamagedFile("No se pudo leer el audio: el archivo parece dañado.") from exc
    if duration <= 0 or not value:
        raise DamagedFile("El archivo no tiene audio que se pueda analizar.")
    return Fingerprint(duration, value)


def available() -> bool:
    try:
        return os.access(tool_path(), os.X_OK)
    except ToolMissing:
        return False
