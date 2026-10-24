"""Operaciones sobre archivos del usuario. Solo se usan con confirmación explícita.

Nunca se borra de forma permanente: los archivos van a la Papelera de reciclaje. Por eso
solo se permite en discos fijos locales; en unidades de red, USB o CD, Windows puede no
tener Papelera y borraría para siempre sin preguntar.
"""

from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import QFile

log = logging.getLogger(__name__)

_DRIVE_FIXED = 3
_DRIVE_NAMES = {
    0: "una unidad desconocida",
    1: "una ruta no válida",
    2: "una unidad extraíble (USB, tarjeta)",
    4: "una unidad de red",
    5: "un CD/DVD",
    6: "un disco en memoria (RAM)",
}


def _drive_type(path: str) -> int:
    import ctypes

    root = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
    return ctypes.windll.kernel32.GetDriveTypeW(root)


_NOT_SENT = "Por seguridad no se envió; puedes quitarlo solo de la biblioteca o borrarlo tú desde el Explorador."


def _recycle_bin_reason(path: str) -> str | None:
    """Configuración de la Papelera de Windows para el disco del archivo. Si está puesta en «No mover
    archivos a la Papelera» o el archivo es más grande que su tamaño máximo, Windows lo borraría para
    siempre (sin preguntar, porque el programa no muestra el aviso de Windows)."""
    import ctypes
    import winreg

    def read(key: str, name: str) -> int | None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
                return int(winreg.QueryValueEx(handle, name)[0])
        except (OSError, ValueError, TypeError):
            return None

    if read(r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoRecycleFiles") == 1:
        return "En este equipo la Papelera está desactivada por una directiva: Windows lo borraría para siempre. " + _NOT_SENT
    root = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
    buffer = ctypes.create_unicode_buffer(64)
    if not ctypes.windll.kernel32.GetVolumeNameForVolumeMountPointW(root, buffer, len(buffer)):
        return None  # no se puede saber: se confía en la comprobación del tipo de disco
    guid = buffer.value.rstrip("\\").split("Volume", 1)[-1]  # «{xxxxxxxx-…}»
    key = rf"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume\{guid}"
    if read(key, "NukeOnDelete") == 1:
        return (
            f"En el disco {root[:2]} la Papelera está configurada para borrar los archivos al instante: "
            "Windows lo borraría para siempre. " + _NOT_SENT
        )
    max_mb = read(key, "MaxCapacity")
    if max_mb:
        try:
            if os.path.getsize(path) > max_mb * 1024 * 1024:
                return f"El archivo es más grande que la Papelera del disco {root[:2]}: Windows lo borraría para siempre. " + _NOT_SENT
        except OSError:
            pass
    return None


def trash_block_reason(path: str) -> str | None:
    """None si el archivo se puede mandar a la Papelera con seguridad; si no, el motivo."""
    if sys.platform != "win32":
        return None
    full = os.path.abspath(path)
    if full.startswith("\\\\"):
        kind = "una carpeta de red"
    else:
        drive_type = _drive_type(full)
        if drive_type == _DRIVE_FIXED:
            return _recycle_bin_reason(full)
        kind = _DRIVE_NAMES.get(drive_type, "una unidad sin Papelera")
    return f"Está en {kind}: ahí Windows podría borrarlo para siempre en vez de enviarlo a la Papelera. " + _NOT_SENT


def move_to_trash(paths: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Envía archivos a la Papelera. Devuelve (enviados, [(ruta, motivo del fallo)])."""
    moved: list[str] = []
    failed: list[tuple[str, str]] = []
    for path in paths:
        if not os.path.exists(path):
            failed.append((path, "El archivo ya no existe."))
            continue
        blocked = trash_block_reason(path)
        if blocked:
            failed.append((path, blocked))
        elif QFile.moveToTrash(path):
            moved.append(path)
            log.info("Enviado a la Papelera: %s", path)
            continue
        elif not os.access(path, os.W_OK):
            failed.append((path, "No hay permiso para modificar el archivo."))
        else:
            failed.append((path, "No se pudo mover a la Papelera (puede estar abierto en otro programa)."))
        log.warning("No se envió a la Papelera %s: %s", path, failed[-1][1])
    return moved, failed
