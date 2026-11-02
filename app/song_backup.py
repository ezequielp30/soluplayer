"""Respaldo verificado de los MP3 y comparación exacta de su audio. Sin dependencias de la interfaz."""

from __future__ import annotations

import hashlib
import os
import shutil
import struct

_CHUNK = 1024 * 1024
_ID3_HEADER = 10
_ID3V1 = 128
_APE_FOOTER = 32
SPACE_MARGIN = 200 * 1024 * 1024  # que el disco no quede lleno del todo


class BackupError(Exception):
    """El respaldo no se pudo crear o verificar: el archivo no se debe modificar. El texto se le muestra a la persona."""


def file_digest(path: str) -> str:
    return _digest_range(path, 0, os.path.getsize(path))


def audio_digest(path: str) -> str:
    """Huella de los bytes del audio de un MP3, sin sus etiquetas (ID3v2 al principio; ID3v1 y APEv2 al final). Si
    coincide antes y después de editar, el audio, la calidad y la codificación no cambiaron."""
    start, end = audio_range(path)
    return _digest_range(path, start, end)


def audio_range(path: str) -> tuple[int, int]:
    size = os.path.getsize(path)
    start, end = 0, size
    with open(path, "rb") as file:
        header = file.read(_ID3_HEADER)
        if len(header) == _ID3_HEADER and header[:3] == b"ID3" and not any(b & 0x80 for b in header[6:10]):
            length = (header[6] << 21) | (header[7] << 14) | (header[8] << 7) | header[9]
            start = _ID3_HEADER + length + (_ID3_HEADER if header[5] & 0x10 else 0)
        for _ in range(2):  # en cualquier orden: ID3v1 y APEv2 pueden convivir
            if end - start >= _ID3V1:
                file.seek(end - _ID3V1)
                if file.read(3) == b"TAG":
                    end -= _ID3V1
                    continue
            if end - start >= _APE_FOOTER:
                file.seek(end - _APE_FOOTER)
                footer = file.read(_APE_FOOTER)
                if footer[:8] == b"APETAGEX":
                    length, _items, flags = struct.unpack("<III", footer[12:24])
                    end -= length + (_APE_FOOTER if flags & 0x80000000 else 0)
    return min(start, size), max(min(start, size), end)


def _digest_range(path: str, start: int, end: int) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        file.seek(start)
        left = end - start
        while left > 0:
            chunk = file.read(min(_CHUNK, left))
            if not chunk:
                break
            digest.update(chunk)
            left -= len(chunk)
    return digest.hexdigest()


def flush_to_disk(path: str) -> None:
    """Fuerza el archivo al disco. Comparar una copia recién hecha lee la caché de Windows: sin esto, un corte de luz
    podría dejar dañados a la vez la copia y lo que iba a reemplazar."""
    with open(path, "r+b") as file:
        os.fsync(file.fileno())


def enough_space(folder: str, needed: int) -> bool:
    probe = folder
    while not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return False
        probe = parent
    return shutil.disk_usage(probe).free >= needed + SPACE_MARGIN


def make_backup(source: str, target: str) -> str:
    """Copia `source` a `target` y comprueba que la copia es idéntica. Devuelve su SHA-256. Nunca pisa otro archivo. Si
    algo falla no queda una copia a medias y se lanza BackupError."""
    if os.path.exists(target):
        raise BackupError(f"Ya existe el respaldo {target}.")
    temp = f"{target}.copiando.tmp"
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        expected = file_digest(source)
        shutil.copy2(source, temp)
        if file_digest(temp) != expected:
            raise BackupError(f"La copia de «{os.path.basename(source)}» no salió idéntica.")
        flush_to_disk(temp)
        os.rename(temp, target)
        return expected
    except OSError as exc:
        raise BackupError(f"No se pudo respaldar «{os.path.basename(source)}»: {exc.strerror or exc}.") from exc
    finally:
        if os.path.exists(temp):
            try:
                os.remove(temp)
            except OSError:
                pass


def is_intact(backup: str, expected: str) -> bool:
    try:
        return file_digest(backup) == expected
    except OSError:
        return False
