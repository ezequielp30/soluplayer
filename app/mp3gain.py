"""Ajuste de volumen SIN pérdida dentro de archivos MP3 (técnica «MP3Gain»).

Cada trama MP3 (MPEG-1/2/2.5 Layer III) guarda un valor «global_gain» de 8 bits por gránulo y canal;
sumarle 1 sube la señal 1,5 dB (2^(1/4) en amplitud). No se recomprime nada: el audio decodificado es
el mismo multiplicado por la ganancia, sin pérdida de calidad, y la operación es exactamente reversible
restando los mismos pasos.

Seguridad:
- Se calcula el máximo global_gain del archivo para no pasarse de 255 (no se recorta nada).
- Si la trama tiene CRC, se vuelve a calcular.
- Se escribe en un archivo temporal en la misma carpeta y se reemplaza de forma atómica.
- Si la estructura no es la esperada (no es MP3 Layer III, tramas inválidas), no se toca el archivo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from mutagen import MutagenError
from mutagen.apev2 import APENoHeaderError, APEv2
from mutagen.apev2 import delete as apev2_delete

from .utils import temp_beside

STEP_DB = 1.5

_BITRATES = {  # kbps por índice: (MPEG-1 Layer III, MPEG-2/2.5 Layer III)
    1: (32, 8), 2: (40, 16), 3: (48, 24), 4: (56, 32), 5: (64, 40), 6: (80, 48), 7: (96, 56),
    8: (112, 64), 9: (128, 80), 10: (160, 96), 11: (192, 112), 12: (224, 128), 13: (256, 144), 14: (320, 160),
}
_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}  # versión → Hz


class Mp3GainError(Exception):
    """No se puede ajustar este archivo con seguridad. El mensaje es apto para el usuario."""


@dataclass
class _Frame:
    offset: int
    length: int
    mpeg1: bool
    channels: int
    crc: bool

    @property
    def side_start(self) -> int:
        return self.offset + 4 + (2 if self.crc else 0)

    @property
    def side_len(self) -> int:
        if self.mpeg1:
            return 17 if self.channels == 1 else 32
        return 9 if self.channels == 1 else 17

    def gain_bit_offsets(self) -> list[int]:
        """Posición (en bits, desde el inicio de la información lateral) de cada global_gain."""
        if self.mpeg1:
            start = 9 + (5 if self.channels == 1 else 3) + 4 * self.channels
            return [start + (gr * self.channels + ch) * 59 + 21 for gr in range(2) for ch in range(self.channels)]
        start = 8 + (1 if self.channels == 1 else 2)
        return [start + ch * 63 + 21 for ch in range(self.channels)]


def _skip_id3v2(data: bytes) -> int:
    if data[:3] == b"ID3" and len(data) >= 10:
        size = (data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F)
        footer = 10 if data[5] & 0x10 else 0
        return 10 + size + footer
    return 0


def _audio_end(data: bytes) -> int:
    """Fin de la zona de audio: antes de las etiquetas ID3v1 («TAG») y APEv2 del final, en cualquier
    orden (algunos programas, incluido mutagen, escriben la APE después de la ID3v1)."""
    end = len(data)
    while True:
        if end >= 128 and data[end - 128:end - 125] == b"TAG":
            end -= 128
            continue
        if end >= 32 and data[end - 32:end - 24] == b"APETAGEX":
            size = int.from_bytes(data[end - 20:end - 16], "little")
            has_header = bool(data[end - 9] & 0x80)
            new_end = end - size - (32 if has_header else 0)
            if 0 <= new_end < end:
                end = new_end
                continue
        return max(0, end)


def _parse_header(data: bytes, pos: int) -> _Frame | None:
    if pos + 4 > len(data) or data[pos] != 0xFF or (data[pos + 1] & 0xE0) != 0xE0:
        return None
    version = (data[pos + 1] >> 3) & 0x3
    layer = (data[pos + 1] >> 1) & 0x3
    if version == 1 or layer != 1:  # versión reservada, o no es Layer III
        return None
    crc = not (data[pos + 1] & 0x1)
    bitrate_index = data[pos + 2] >> 4
    rate_index = (data[pos + 2] >> 2) & 0x3
    padding = (data[pos + 2] >> 1) & 0x1
    if bitrate_index in (0, 15) or rate_index == 3:  # «free format» o valores inválidos
        return None
    mpeg1 = version == 3
    bitrate = _BITRATES[bitrate_index][0 if mpeg1 else 1] * 1000
    rate = _RATES[version][rate_index]
    length = (144 if mpeg1 else 72) * bitrate // rate + padding
    channels = 1 if (data[pos + 3] >> 6) == 3 else 2
    return _Frame(pos, length, mpeg1, channels, crc)


def _frames(data: bytes) -> list[_Frame]:
    pos, end = _skip_id3v2(data), _audio_end(data)
    frames: list[_Frame] = []
    while pos + 4 <= end:
        frame = _parse_header(data, pos)
        # Una trama válida debe estar seguida de otra (o del final): evita falsos sincronismos.
        if frame and pos + frame.length <= end and (pos + frame.length >= end - 3 or _parse_header(data, pos + frame.length)):
            frames.append(frame)
            pos += frame.length
        else:
            pos += 1
    return frames


def _get_bits(buf: bytearray, bit: int, count: int) -> int:
    value = 0
    for i in range(count):
        byte = buf[(bit + i) // 8]
        value = (value << 1) | ((byte >> (7 - (bit + i) % 8)) & 1)
    return value


def _set_bits(buf: bytearray, bit: int, count: int, value: int) -> None:
    for i in range(count):
        index, shift = (bit + i) // 8, 7 - (bit + i) % 8
        if (value >> (count - 1 - i)) & 1:
            buf[index] |= 1 << shift
        else:
            buf[index] &= ~(1 << shift) & 0xFF


def _crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x8005) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


@dataclass(frozen=True)
class Mp3Info:
    frames: int
    min_gain: int
    max_gain: int

    @property
    def max_up_steps(self) -> int:
        return 255 - self.max_gain

    @property
    def max_down_steps(self) -> int:
        return self.min_gain


def inspect(path: str) -> Mp3Info:
    data = open(path, "rb").read()
    frames = _frames(data)
    if len(frames) < 10:
        raise Mp3GainError("No se reconoce como MP3 (Layer III) válido.")
    buf = bytearray(data)
    gains = [_get_bits(buf, f.side_start * 8 + o, 8) for f in frames for o in f.gain_bit_offsets()]
    audible = [g for g in gains if g > 0] or [0]
    return Mp3Info(len(frames), min(audible), max(gains))


def apply_steps(path: str, steps: int, annotate_total: int | None = None) -> Mp3Info:
    """Suma `steps` (positivo o negativo) a todos los global_gain del archivo, sin pérdida.
    Con `annotate_total`, la anotación para deshacer (pasos subidos en total) se escribe en el mismo
    temporal, y audio y anotación reemplazan al archivo en UNA sola operación atómica: un cierre a mitad
    nunca deja el audio cambiado sin anotar. Devuelve la información del archivo ANTES del cambio."""
    if steps == 0:
        return inspect(path)
    data = open(path, "rb").read()
    frames = _frames(data)
    if len(frames) < 10:
        raise Mp3GainError("No se reconoce como MP3 (Layer III) válido.")
    buf = bytearray(data)
    gains = [_get_bits(buf, f.side_start * 8 + o, 8) for f in frames for o in f.gain_bit_offsets()]
    info = Mp3Info(len(frames), min([g for g in gains if g > 0] or [0]), max(gains))
    if steps > 0 and info.max_gain + steps > 255:
        raise Mp3GainError("La ganancia interna del archivo no admite tanta subida.")
    if steps < 0 and info.min_gain + steps < 0:
        raise Mp3GainError("La ganancia interna del archivo no admite tanta bajada.")
    for frame in frames:
        base = frame.side_start * 8
        for offset in frame.gain_bit_offsets():
            value = _get_bits(buf, base + offset, 8)
            if value:  # 0 = gránulo en silencio (p. ej. la trama de información LAME): se deja igual
                _set_bits(buf, base + offset, 8, value + steps)
        if frame.crc:
            covered = bytes(buf[frame.offset + 2:frame.offset + 4]) + bytes(buf[frame.side_start:frame.side_start + frame.side_len])
            crc = _crc16(covered)
            buf[frame.offset + 4:frame.offset + 6] = crc.to_bytes(2, "big")
    if not os.access(path, os.W_OK):
        raise Mp3GainError("El archivo es de solo lectura.")
    temp = temp_beside(path, ".ajuste-volumen.tmp")
    try:
        with open(temp, "wb") as handle:
            handle.write(buf)
            handle.flush()
            os.fsync(handle.fileno())
        if annotate_total is not None:
            write_applied_steps(temp, annotate_total)
            with open(temp, "rb+") as handle:
                os.fsync(handle.fileno())
        # La fecha de modificación cambia a propósito: las copias de seguridad y sincronizaciones que
        # comparan fecha y tamaño (el tamaño no cambia) así detectan que el archivo es distinto.
        os.replace(temp, path)
    except (OSError, MutagenError) as exc:
        try:
            os.remove(temp)
        except OSError:
            pass
        if isinstance(exc, PermissionError):
            raise Mp3GainError("El archivo está abierto en otro programa (o no hay permiso para modificarlo).") from exc
        if isinstance(exc, MutagenError):
            raise Mp3GainError(f"No se pudo guardar la anotación del ajuste ({exc}).") from exc
        raise Mp3GainError(f"No se pudo guardar el archivo ({exc.strerror or exc}).") from exc
    return info


# ---------------------------------------------------------------------- anotación para deshacer

UNDO_KEY = "MP3GAIN_UNDO"  # mismo campo que usa MP3Gain: otros programas también pueden deshacerlo


def read_applied_steps(path: str) -> int:
    """Pasos que ya se subieron a este MP3, según la anotación guardada DENTRO del archivo (0 si no hay).

    Formato de MP3Gain en la etiqueta APEv2: «-002,-002,N» = pasos para DESHACER (izquierdo, derecho, ajuste).
    """
    try:
        tag = APEv2(path)
    except APENoHeaderError:
        return 0  # sin etiqueta APE: nunca se ajustó
    # Un archivo bloqueado o ilegible NO es «sin ajuste»: el error sube, para no sumar mal los pasos.
    value = str(tag.get(UNDO_KEY, "")).strip()
    try:
        return -int(value.split(",")[0])
    except (ValueError, IndexError):
        return 0


def write_applied_steps(path: str, total_steps: int) -> None:
    """Guarda en el propio archivo cuánto se subió en total (0 = sin ajuste: se quita la anotación).
    Así el ajuste se puede revertir aunque la biblioteca se restaure o la canción se reimporte."""
    try:
        tag = APEv2(path)
    except APENoHeaderError:
        tag = None
    if total_steps == 0:
        if tag is not None and UNDO_KEY in tag:
            del tag[UNDO_KEY]
            if len(tag):
                tag.save(path)
            else:
                apev2_delete(path)  # la etiqueta era solo nuestra: el archivo queda como estaba
        return
    if tag is None:
        tag = APEv2()
    undo = -total_steps
    tag[UNDO_KEY] = f"{undo:+04d},{undo:+04d},N"
    tag.save(path)


def steps_for_gain(gain_db: float) -> int:
    """Pasos enteros de 1,5 dB sin pasarse de la ganancia permitida (redondeo hacia abajo)."""
    return max(0, int(gain_db // STEP_DB))
