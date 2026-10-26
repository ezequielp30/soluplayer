"""Operaciones del usuario sobre archivos y carpetas de música: renombrar, crear carpeta, mover y borrar
(a la Papelera). Sin ventanas: cada función hace UNA cosa en el disco y, si no puede, lanza FileManagerError
con un mensaje comprensible. La biblioteca la actualiza app/file_operations.py.
"""

from __future__ import annotations

import errno
import logging
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass, field

from PySide6.QtCore import QFile

from .config import SUPPORTED_EXTENSIONS
from .file_ops import trash_block_reason
from .utils import long_path, temp_beside

log = logging.getLogger(__name__)

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
    *(f"COM{i}" for i in "123456789¹²³"), *(f"LPT{i}" for i in "123456789¹²³"),
}
MAX_PATH = 259  # sin «rutas largas» activadas, Windows no admite rutas de 260 caracteres o más
_MOVING_SUFFIX = ".moviendo.tmp"


class FileManagerError(Exception):
    """No se pudo hacer la operación. El mensaje es apto para el usuario."""


def explain(exc: OSError, name: str) -> str:
    """Mensaje comprensible para un error del sistema de archivos."""
    if isinstance(exc, FileNotFoundError):
        return f"«{name}» ya no existe (¿se movió o se borró por fuera del programa?)."
    if isinstance(exc, FileExistsError) or exc.errno == errno.EEXIST:
        return f"Ya existe un elemento con el nombre «{name}» en esa carpeta."
    if isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in (5, 32, 33):
        return f"«{name}» está abierto en otro programa o no hay permiso para cambiarlo."
    if getattr(exc, "winerror", None) == 206 or exc.errno == errno.ENAMETOOLONG:
        return f"La ruta de «{name}» es demasiado larga para Windows."
    if exc.errno == errno.ENOSPC:
        return "No hay espacio suficiente en el disco."
    return f"No se pudo completar con «{name}» ({exc.strerror or exc})."


def check_name(name: str, is_folder: bool = False) -> str:
    """Valida un nombre de archivo o carpeta para Windows. Devuelve el nombre limpio o lanza el motivo."""
    clean = name.strip()
    if not clean:
        raise FileManagerError("Escribe un nombre.")
    if clean in (".", ".."):
        raise FileManagerError("Ese nombre no es válido.")
    bad = sorted(set(_INVALID.findall(clean)))
    if bad:
        shown = " ".join(c if c.isprintable() else "?" for c in bad)
        raise FileManagerError(f"El nombre no puede contener estos caracteres: {shown}")
    if clean.endswith("."):
        raise FileManagerError("El nombre no puede terminar en punto.")
    # Caracteres invisibles o que invierten el texto (U+200B, U+202E…): sirven para disfrazar un nombre.
    if any(unicodedata.category(c) == "Cf" for c in clean):
        raise FileManagerError("El nombre tiene caracteres invisibles o de control de texto. Escríbelo de nuevo.")
    stem = clean if is_folder else os.path.splitext(clean)[0]
    if stem.split(".")[0].strip().upper() in _RESERVED:
        raise FileManagerError(f"«{clean}» es un nombre reservado de Windows.")
    if len(clean.encode("utf-16-le")) // 2 > 200:  # Windows cuenta en UTF-16: un emoji ocupa 2
        raise FileManagerError("El nombre es demasiado largo (máximo 200 caracteres).")
    return clean


def _check_path_length(target: str) -> None:
    if len(os.path.abspath(target).encode("utf-16-le")) // 2 > MAX_PATH:
        raise FileManagerError(
            "La ruta completa quedaría demasiado larga para Windows (más de 260 caracteres). "
            "Usa un nombre más corto o una carpeta menos profunda."
        )


def rename_file(path: str, new_name: str) -> str:
    """Renombra un archivo en su misma carpeta. Si el nombre nuevo no trae extensión, conserva la suya.
    Devuelve la ruta nueva."""
    if not os.path.isfile(path):
        raise FileManagerError(f"«{os.path.basename(path)}» ya no existe.")
    ext = os.path.splitext(path)[1]
    clean = check_name(new_name)
    if os.path.splitext(clean)[1].lower() != ext.lower():
        clean += ext  # «Mi canción» → «Mi canción.mp3»: nunca cambiar el formato por accidente
    target = os.path.join(os.path.dirname(path), clean)
    return _rename(path, target)


_KNOWN_FOLDERS = (  # FOLDERID_* de Windows: Escritorio, Documentos, Descargas, Música, Imágenes, Videos, OneDrive
    "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}", "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "{374DE290-123F-4565-9164-39C4925E467B}", "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "{33E28130-4E1E-4676-835A-98395C3BC3BB}", "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
    "{A52BBA46-E9E1-435F-B3D9-28DAA648C0F6}",
)


def _known_folder(guid: str) -> str | None:
    import ctypes
    import uuid

    raw = (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID(guid).bytes_le)
    out = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(raw), 0, None, ctypes.byref(out)) != 0:
        return None
    try:
        return out.value
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)


def _protected_folders() -> list[str]:
    """Carpetas que el programa nunca envía a la Papelera ni renombra: el perfil del usuario, la carpeta de
    usuarios, la de Windows y las carpetas conocidas (Escritorio, Documentos, Descargas, Música…)."""
    home = os.path.expanduser("~")
    public = os.environ.get("PUBLIC", "")
    folders = [home, os.path.dirname(home), os.environ.get("SystemRoot", r"C:\Windows"),
               os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", ""), public]
    if public:
        folders += [os.path.join(public, name) for name in ("Desktop", "Documents", "Downloads", "Music", "Pictures", "Videos")]
    if os.name == "nt":
        folders += [f for f in (_known_folder(g) for g in _KNOWN_FOLDERS) if f]
    return [f for f in folders if f]


def protected_reason(folder: str) -> str:
    """Por qué una carpeta no se puede enviar a la Papelera ni renombrar desde el programa («» si se puede).
    Una carpeta de música puede estar dentro de Documentos o de Música, pero no ser una de ellas."""
    key = os.path.normcase(long_path(folder)).rstrip("\\/")  # también «C:\USERS\EZEQUI~1»
    if os.path.splitdrive(key)[1] in ("", "\\", "/"):
        return "Es la raíz de un disco: el programa no la toca."
    for protected in _protected_folders():
        if key == os.path.normcase(long_path(protected)).rstrip("\\/"):
            name = os.path.basename(long_path(folder).rstrip("\\/"))
            return f"«{name}» es una carpeta protegida de Windows o de tu usuario: el programa no la toca."
    return ""


def rename_folder(folder: str, new_name: str) -> str:
    if not os.path.isdir(folder):
        raise FileManagerError(f"La carpeta «{os.path.basename(folder)}» ya no existe.")
    reason = protected_reason(folder)
    if reason:
        raise FileManagerError(reason)
    clean = check_name(new_name, is_folder=True)
    target = os.path.join(os.path.dirname(os.path.normpath(folder)), clean)
    return _rename(folder, target)


def _rename(source: str, target: str) -> str:
    name = os.path.basename(target)
    same = os.path.normcase(os.path.abspath(source)) == os.path.normcase(os.path.abspath(target))
    if same and os.path.basename(source) == name:
        return source  # sin cambios
    if os.path.exists(target) and not same:
        raise FileManagerError(f"Ya existe «{name}» en esa carpeta. Elige otro nombre.")
    _check_path_length(target)
    try:
        os.rename(source, target)  # solo cambia mayúsculas/minúsculas también funciona en Windows
    except OSError as exc:
        raise FileManagerError(explain(exc, os.path.basename(source))) from exc
    log.info("Renombrado: %s → %s", source, target)
    return target


def create_folder(parent: str, name: str) -> str:
    clean = check_name(name, is_folder=True)
    target = os.path.join(parent, clean)
    if os.path.exists(target):
        raise FileManagerError(f"Ya existe «{clean}» en esa carpeta.")
    _check_path_length(os.path.join(target, "x" * 40 + ".mp3"))  # que quepan canciones dentro
    try:
        os.makedirs(target)
    except OSError as exc:
        raise FileManagerError(explain(exc, clean)) from exc
    log.info("Carpeta creada: %s", target)
    return target


@dataclass
class MoveResult:
    moved: list[tuple[str, str]] = field(default_factory=list)  # (origen, destino)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (ruta, motivo)


def _move_across_drives(path: str, target: str) -> None:
    """Mueve a otro disco sin perder nunca la canción: se copia a un temporal (sin pisar nada), se fuerza al
    disco y se verifica; el temporal toma su nombre definitivo y recién entonces se borra el original. Si el
    original no se puede borrar (solo lectura, abierto en otro programa), se quita la copia.
    Así un «.moviendo.tmp» que quede tras un corte de luz es siempre una copia a medias (el original sigue
    en su sitio) y se puede borrar sin riesgo al abrir el programa."""
    if not os.access(path, os.W_OK):
        raise PermissionError(errno.EACCES, "el archivo es de solo lectura", path)
    temp = moving_temp(target)
    try:
        with open(path, "rb") as src, open(temp, "xb") as dst:  # «x»: falla si ya existe, no sobrescribe
            shutil.copyfileobj(src, dst, 1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        shutil.copystat(path, temp)
        if os.path.getsize(temp) != os.path.getsize(path):
            raise OSError(errno.EIO, "la copia no quedó completa")
    except BaseException:
        _remove_quietly(temp)
        raise
    try:
        os.rename(temp, target)  # mismo disco y misma carpeta: instantáneo; falla si apareció ese nombre
    except OSError:
        _remove_quietly(temp)
        raise
    try:
        os.remove(path)
    except OSError:
        _remove_quietly(target)  # el original sigue en su sitio: no queda ninguna copia de más
        raise


def moving_temp(target: str) -> str:
    """El temporal de una copia a otro disco hacia `target`."""
    return temp_beside(target, _MOVING_SUFFIX)


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def move_files(paths: list[str], destination: str) -> MoveResult:
    """Mueve archivos a otra carpeta. En el mismo disco es un renombrado instantáneo; a otro disco se
    copia de forma segura (ver _move_across_drives). Nunca sobrescribe."""
    result = MoveResult()
    if not os.path.isdir(destination):
        for p in paths:
            result.failed.append((p, "La carpeta de destino no existe."))
        return result
    for path in paths:
        name = os.path.basename(path)
        target = os.path.join(destination, name)
        if os.path.normcase(os.path.abspath(os.path.dirname(path))) == os.path.normcase(os.path.abspath(destination)):
            result.failed.append((path, "Ya está en esa carpeta."))
            continue
        if not os.path.isfile(path):
            result.failed.append((path, "El archivo ya no existe."))
            continue
        if os.path.exists(target):
            result.failed.append((path, f"En la carpeta de destino ya hay un archivo llamado «{name}»."))
            continue
        try:
            _check_path_length(target)
        except FileManagerError as exc:
            result.failed.append((path, str(exc)))
            continue
        try:
            if os.path.splitdrive(os.path.abspath(path))[0].lower() == os.path.splitdrive(os.path.abspath(target))[0].lower():
                os.rename(path, target)
            else:
                _move_across_drives(path, target)
        except OSError as exc:
            result.failed.append((path, explain(exc, name)))
            continue
        result.moved.append((path, target))
        log.info("Movido: %s → %s", path, target)
    return result


@dataclass
class FolderContents:
    files: int  # todos los archivos (incluye los que no son música)
    audio: int
    folders: int


def folder_contents(folder: str) -> FolderContents:
    files = audio = folders = 0
    for _root, dirs, names in os.walk(folder):
        folders += len(dirs)
        files += len(names)
        audio += sum(1 for n in names if os.path.splitext(n)[1].lower() in SUPPORTED_EXTENSIONS)
    return FolderContents(files, audio, folders)


def trash_folder(folder: str) -> None:
    """Envía una carpeta entera a la Papelera de reciclaje (se puede recuperar desde allí)."""
    name = os.path.basename(os.path.normpath(folder))
    if not os.path.isdir(folder):
        raise FileManagerError(f"La carpeta «{name}» ya no existe.")
    blocked = protected_reason(folder) or trash_block_reason(folder)
    if blocked:
        raise FileManagerError(blocked)
    if not QFile.moveToTrash(folder):
        raise FileManagerError(
            f"No se pudo enviar «{name}» a la Papelera: algún archivo está abierto en otro programa "
            "o no hay permiso. No se borró nada."
        )
    log.info("Carpeta enviada a la Papelera: %s", folder)
