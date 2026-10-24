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


_DEFAULT_BIN_FRACTION = 0.05  # tamaño de la Papelera que Windows usa si el usuario nunca lo cambió


def _volume_root(path: str) -> str:
    """Raíz del volumen REAL donde está el archivo: resuelve accesos directos de carpeta (junctions) y
    discos montados en una carpeta (p. ej. un USB montado en «C:\\Musica\\USB» no es el disco C:)."""
    import ctypes

    buffer = ctypes.create_unicode_buffer(1024)
    if ctypes.windll.kernel32.GetVolumePathNameW(path, buffer, len(buffer)):
        return buffer.value if buffer.value.endswith("\\") else buffer.value + "\\"
    return os.path.splitdrive(path)[0] + "\\"


def _drive_type(root: str) -> int:
    import ctypes

    return ctypes.windll.kernel32.GetDriveTypeW(root)


def _is_subst_drive(path: str) -> bool:
    """Unidades creadas con «subst» (una letra que apunta a una carpeta): no tienen Papelera propia."""
    import ctypes

    drive = os.path.splitdrive(path)[0]
    if len(drive) != 2:
        return False
    buffer = ctypes.create_unicode_buffer(1024)
    if not ctypes.windll.kernel32.QueryDosDeviceW(drive, buffer, len(buffer)):
        return False
    return buffer.value.startswith("\\??\\")


_NOT_SENT = "Por seguridad no se envió; puedes quitarlo solo de la biblioteca o borrarlo tú desde el Explorador."


def _size_exceeds(path: str, limit: int) -> bool:
    """¿El archivo, o todo el contenido de la carpeta, ocupa más que `limit` bytes? (para en cuanto lo supera)."""
    if not os.path.isdir(path):
        try:
            return os.path.getsize(path) > limit
        except OSError:
            return False
    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not os.path.isjunction(os.path.join(root, d))]  # sin ciclos
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
            if total > limit:
                return True
    return False


def _recycle_bin_reason(path: str, root: str) -> str | None:
    """Configuración de la Papelera de Windows para el disco del archivo. Si está puesta en «No mover
    archivos a la Papelera» o el archivo (o la carpeta entera) es más grande que su tamaño máximo,
    Windows lo borraría para siempre (sin preguntar, porque el programa no muestra el aviso de Windows)."""
    import ctypes
    import shutil
    import winreg

    def read(hive, key: str, name: str) -> int | None:
        try:
            with winreg.OpenKey(hive, key) as handle:
                return int(winreg.QueryValueEx(handle, name)[0])
        except (OSError, ValueError, TypeError):
            return None

    policy = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    if 1 in (read(winreg.HKEY_CURRENT_USER, policy, "NoRecycleFiles"), read(winreg.HKEY_LOCAL_MACHINE, policy, "NoRecycleFiles")):
        return "En este equipo la Papelera está desactivada por una directiva: Windows lo borraría para siempre. " + _NOT_SENT
    label = root[:2] if len(root) <= 3 else root.rstrip("\\")
    buffer = ctypes.create_unicode_buffer(64)
    max_mb = None
    if ctypes.windll.kernel32.GetVolumeNameForVolumeMountPointW(root, buffer, len(buffer)):
        guid = buffer.value.rstrip("\\").split("Volume", 1)[-1]  # «{xxxxxxxx-…}»
        key = rf"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume\{guid}"
        if read(winreg.HKEY_CURRENT_USER, key, "NukeOnDelete") == 1:
            return (
                f"En el disco {label} la Papelera está configurada para borrar los archivos al instante: "
                "Windows lo borraría para siempre. " + _NOT_SENT
            )
        max_mb = read(winreg.HKEY_CURRENT_USER, key, "MaxCapacity")
    if max_mb:
        limit = max_mb * 1024 * 1024
    else:
        # Sin tamaño configurado se usa el que pone Windows por defecto (una parte del disco).
        try:
            limit = int(shutil.disk_usage(root).total * _DEFAULT_BIN_FRACTION)
        except OSError:
            return f"No se pudo saber el tamaño de la Papelera del disco {label}. " + _NOT_SENT
    if _size_exceeds(path, limit):
        what = "La carpeta ocupa" if os.path.isdir(path) else "El archivo es"
        return f"{what} más que la Papelera del disco {label}: Windows lo borraría para siempre. " + _NOT_SENT
    return None


def trash_block_reason(path: str) -> str | None:
    """None si el archivo o la carpeta se puede mandar a la Papelera con seguridad; si no, el motivo."""
    if sys.platform != "win32":
        return None
    full = os.path.abspath(path)
    if _is_subst_drive(full):
        kind = "una unidad virtual (creada con «subst»)"
    else:
        real = full
        if os.path.exists(full):
            try:
                real = os.path.realpath(full)  # resuelve junctions y enlaces hasta el disco de verdad
            except OSError:
                pass
        if full.startswith("\\\\") or real.startswith("\\\\"):
            kind = "una carpeta de red"
        else:
            root = _volume_root(real)
            drive_type = _drive_type(root)
            if drive_type == _DRIVE_FIXED:
                return _recycle_bin_reason(full, root)
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
