"""Conversión de archivos de audio (WMA, M4A, FLAC, WAV…) a MP3 con LAME, y deshacer la conversión.

Calidad: convertir de un formato con pérdida (WMA, M4A) a MP3 no puede mejorar el sonido original;
lo que se garantiza es no añadir pérdida audible, usando el DOBLE de kbps que el original (mínimo
128, máximo 320). Los formatos sin pérdida (FLAC, WAV…) van a 320 kbps.

Seguridad:
- El MP3 se escribe primero como temporal y se comprueba (que sea un MP3 válido y dure lo mismo)
  antes de darlo por bueno. Si algo falla, el original no se toca.
- El original no se borra: se mueve (mismo disco) a «_Originales convertidos», conservando su
  estructura de carpetas. Todo queda anotado en un registro para poder deshacerlo.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import lameenc
import mutagen
import numpy as np
from mutagen.id3 import APIC, ID3, TALB, TCON, TDRC, TIT2, TPE1, TRCK, ID3NoHeaderError
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtMultimedia import QAudioFormat

from .audio_decode import decode_file
from . import journal, mp3gain
from .metadata import MetadataError, read_metadata
from .models import Track
from .utils import path_key
from .metadata import Quality, audio_quality

log = logging.getLogger(__name__)

ORIGINALS_FOLDER_NAME = "_Originales convertidos"
LOSSLESS = frozenset({".flac", ".wav", ".aif", ".aiff", ".aifc", ".ape", ".wv", ".tta", ".dsf", ".dff"})
_MP3_RATES = (128, 160, 192, 224, 256, 320)
_LAME_SAMPLE_RATES = (32000, 44100, 48000)

STATUS_RUNNING, STATUS_DONE, STATUS_UNDONE = journal.STATUS_RUNNING, journal.STATUS_DONE, journal.STATUS_UNDONE


class ConversionError(Exception):
    """No se pudo convertir. El mensaje es apto para el usuario."""


def target_bitrate(path: str, quality: Quality | None = None) -> int:
    """kbps del MP3: 320 para formatos sin pérdida; si no, el doble del original entre 128 y 320.

    Con originales mono o de frecuencia baja (≤ 24 kHz: grabaciones de voz, WAV de 8 kHz…) se limita:
    LAME no necesita 320 kbps para reproducirlos sin pérdida audible y solo se gastaría espacio.
    Tope: estéreo 320, mono 160; con frecuencia baja, estéreo 192 y mono 128."""
    quality = quality or audio_quality(path)
    mono = quality.channels == 1
    low_rate = bool(quality.sample_rate) and quality.sample_rate <= 24000
    cap = (128 if mono else 192) if low_rate else (160 if mono else 320)
    if os.path.splitext(path)[1].lower() in LOSSLESS:
        wanted = 320
    elif quality.kbps:
        wanted = max(128, quality.kbps * 2)
    else:
        wanted = 256
    wanted = min(wanted, cap)
    return next(rate for rate in _MP3_RATES if rate >= wanted)


def target_format(path: str) -> tuple[int, int]:
    """(frecuencia, canales) del MP3: se conserva la del original si LAME la admite."""
    quality = audio_quality(path)
    rate = quality.sample_rate if quality.sample_rate in _LAME_SAMPLE_RATES else 44100
    channels = 1 if quality.channels == 1 else 2
    return rate, channels


def mp3_path_for(path: str, taken: set[str] | None = None) -> str:
    """Ruta libre para el MP3. `taken` = claves de ruta ya ocupadas (por la biblioteca, aunque el archivo
    no esté en el disco, o por otro elemento del mismo plan); se le agrega la elegida.
    Así «Canción.wav» y «Canción.flac» de la misma carpeta nunca reciben el mismo MP3."""
    taken = taken if taken is not None else set()
    base = os.path.splitext(path)[0]
    candidate = base + ".mp3"
    n = 2
    while os.path.exists(candidate) or path_key(candidate) in taken:
        candidate = f"{base} (convertido{'' if n == 2 else f' {n}'}).mp3"
        n += 1
    taken.add(path_key(candidate))
    return candidate


def original_seconds(track: Track) -> float:
    """Duración del original según la biblioteca o su cabecera (0 si se desconoce)."""
    if track.duration_ms > 0:
        return track.duration_ms / 1000
    try:
        info = mutagen.File(track.path)
        return float(info.info.length) if info is not None and info.info else 0.0
    except Exception:
        return 0.0


class Mp3Writer:
    """Recibe PCM de 16 bits intercalado y lo codifica con LAME (calidad alta) a un temporal."""

    def __init__(self, temp_path: str, bitrate: int, sample_rate: int, channels: int) -> None:
        self.temp_path = temp_path
        self._encoder = lameenc.Encoder()
        self._encoder.set_bit_rate(bitrate)
        self._encoder.set_in_sample_rate(sample_rate)
        self._encoder.set_channels(channels)
        self._encoder.set_quality(2)  # 0 = la mejor y más lenta; 2 = casi idéntica y bastante más rápida
        self._file = open(temp_path, "wb")
        self.frames = 0
        self._channels = channels

    def write(self, pcm16: bytes) -> None:
        self.frames += len(pcm16) // (2 * self._channels)
        self._file.write(self._encoder.encode(pcm16))

    def close(self) -> None:
        try:
            self._file.write(self._encoder.flush())
            self._file.flush()
            os.fsync(self._file.fileno())
        finally:
            self._file.close()  # aunque falle (disco lleno): un archivo abierto no se puede borrar en Windows

    def abort(self) -> None:
        try:
            self._file.close()
        except OSError:
            pass
        try:
            os.remove(self.temp_path)
        except OSError:
            pass


def copy_tags(source: str, mp3: str, track: Track, cover: bytes | None) -> None:
    """Etiquetas ID3 del MP3: datos de la biblioteca (incluye tus correcciones) + carátula y número de pista."""
    try:
        tags = ID3(mp3)
    except ID3NoHeaderError:
        tags = ID3()
    tags.add(TIT2(encoding=3, text=track.title))
    tags.add(TPE1(encoding=3, text=track.artist))
    tags.add(TALB(encoding=3, text=track.album))
    tags.add(TCON(encoding=3, text=track.genre))
    try:
        easy = mutagen.File(source, easy=True)
        extra = getattr(easy, "tags", None) or {}
        for key, frame in (("tracknumber", TRCK), ("date", TDRC)):
            value = extra.get(key) if hasattr(extra, "get") else None
            if value:
                tags.add(frame(encoding=3, text=str(value[0] if isinstance(value, list) else value)))
    except Exception:
        pass
    if cover:
        mime = "image/png" if cover[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover))
    tags.save(mp3, v2_version=3)  # ID3v2.3: la versión que entienden todos los reproductores y Windows


def verify_mp3(mp3: str, expected_seconds: float) -> None:
    try:
        info = mutagen.File(mp3)
    except Exception as exc:
        raise ConversionError(f"El MP3 generado no es válido ({exc}).") from exc
    if info is None or not getattr(info, "info", None) or info.info.length <= 0:
        raise ConversionError("El MP3 generado no es válido.")
    if expected_seconds > 1 and abs(info.info.length - expected_seconds) > max(1.0, expected_seconds * 0.01):
        raise ConversionError(
            f"El MP3 dura {info.info.length:.1f} s y el original {expected_seconds:.1f} s: no se usa por seguridad."
        )


def original_cover(path: str) -> bytes | None:
    try:
        return read_metadata(path).cover
    except MetadataError:
        return None


# ---------------------------------------------------------------------- registro y deshacer


@dataclass
class Conversion:
    track_id: int
    original: str
    mp3: str
    moved_to: str = ""  # dónde quedó el original («» si no se movió)
    done: bool = False


@dataclass
class ConversionSession:
    id: str
    originals_root: str
    status: str
    created_at: str
    items: list[Conversion] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return sessions_dir() / f"conversion-{self.id}.json"

    def save(self) -> None:
        journal.write_atomic(self.path, asdict(self))

    @staticmethod
    def load(path: Path) -> "ConversionSession":
        data = journal.read(path)
        data["items"] = [Conversion(**item) for item in data.get("items", [])]
        return ConversionSession(**data)


def sessions_dir() -> Path:
    return journal.journal_dir("conversiones")


def list_sessions() -> list[ConversionSession]:
    return journal.load_all(sessions_dir(), "conversion-*.json", ConversionSession.load)


def interrupted_sessions() -> list[ConversionSession]:
    return [s for s in list_sessions() if s.status == STATUS_RUNNING]


def pending_items(session: ConversionSession) -> list[Conversion]:
    """Elementos con algo que deshacer: convertidos, o a medias tras un cierre inesperado
    (MP3 ya creado u original ya movido aunque el registro no lo marcara como hecho)."""
    return [
        item for item in session.items
        if item.done or os.path.exists(item.mp3) or journal.was_moved(item.original, item.moved_to)
    ]


def originals_root_for(tracks: list[Track]) -> str:
    folders = [os.path.dirname(t.path) for t in tracks]
    try:
        common = os.path.commonpath(folders)
    except ValueError:
        common = folders[0]
    return os.path.join(common, ORIGINALS_FOLDER_NAME)


def new_session(tracks: list[Track], library_keys: set[str] | None = None) -> ConversionSession:
    """`library_keys`: rutas que ya usa la biblioteca (Database.known_path_keys()), para no elegir
    como destino una ruta de otra canción aunque su archivo ya no esté en el disco."""
    root = originals_root_for(tracks)
    taken = set(library_keys or ())
    return ConversionSession(
        id=journal.new_id(sessions_dir(), "conversion"),
        originals_root=root,
        status=STATUS_RUNNING,
        created_at=datetime.now().isoformat(timespec="seconds"),
        items=[Conversion(t.id, t.path, mp3_path_for(t.path, taken)) for t in tracks],
    )


def original_target(item: Conversion, originals_root: str) -> str:
    """Dónde se guardará el original («» si está en otro disco: entonces se deja en su sitio)."""
    common = os.path.dirname(originals_root)
    try:
        relative = os.path.relpath(item.original, common)
    except ValueError:
        relative = os.path.basename(item.original)
    if relative.startswith(".."):
        relative = os.path.basename(item.original)
    target = os.path.join(originals_root, relative)
    if os.path.exists(target):
        stem, ext = os.path.splitext(target)
        n = 2
        while os.path.exists(f"{stem} ({n}){ext}"):
            n += 1
        target = f"{stem} ({n}){ext}"
    if os.path.splitdrive(target)[0].lower() != os.path.splitdrive(item.original)[0].lower():
        return ""
    return target


def move_original(item: Conversion, session: ConversionSession) -> None:
    """Guarda el original aparte. Primero se anota el DESTINO en el registro y después se mueve:
    si el programa se cierra entre medio, el registro ya sabe dónde buscarlo."""
    target = original_target(item, session.originals_root)
    item.moved_to = target
    session.save()
    if not target:
        return
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.rename(item.original, target)
    except OSError:
        item.moved_to = ""  # no se movió: el original sigue en su sitio
        session.save()
        raise


def undo(session: ConversionSession, on_restored=None) -> tuple[list[Conversion], list[str]]:
    """Deshace: el original vuelve a su sitio y el MP3 creado va a la Papelera. Devuelve (deshechas, problemas).
    Nunca se manda un MP3 a la Papelera si su original no está de vuelta en su lugar.

    `on_restored(item)` pasa la biblioteca al original en cuanto vuelve, ANTES de quitar el MP3 y de
    anotarlo en el registro: si fallara, se deja todo como estaba (la biblioteca sigue con el MP3)."""
    from .file_ops import move_to_trash

    restored, problems = [], []
    for item in reversed(pending_items(session)):
        name = os.path.basename(item.original)
        try:
            original_here = os.path.exists(item.original)
            saved_copy = bool(item.moved_to) and os.path.exists(item.moved_to)
            if saved_copy and original_here:
                problems.append(f"{name}: ya hay otro archivo en su lugar original; no se tocó nada.")
                continue
            if saved_copy:
                os.makedirs(os.path.dirname(item.original), exist_ok=True)
                os.rename(item.moved_to, item.original)
                original_here = True
            if not original_here:
                problems.append(
                    f"{name}: el original no está ni en su sitio ni en «{ORIGINALS_FOLDER_NAME}»; el MP3 se conserva."
                )
                continue
            if on_restored is not None:
                try:
                    on_restored(item)
                except Exception as exc:
                    if saved_copy:
                        os.rename(item.original, item.moved_to)  # todo como estaba
                    log.error("No se pudo actualizar la biblioteca al deshacer %s: %s", item.original, exc)
                    problems.append(f"{name}: no se pudo actualizar la biblioteca ({exc}); no se tocó nada.")
                    continue
            if os.path.exists(item.mp3):
                _moved, failed = move_to_trash([item.mp3])
                if failed:
                    problems.append(f"{os.path.basename(item.mp3)}: {failed[0][1]}")
            item.done = False
            restored.append(item)
            session.save()
        except OSError as exc:
            problems.append(f"{name}: {exc}")
    # Limpieza: solo carpetas vacías dentro de «_Originales convertidos».
    for root, _dirs, _files in sorted(os.walk(session.originals_root, topdown=False), key=lambda x: -len(x[0])):
        try:
            if not os.listdir(root):
                os.rmdir(root)
        except OSError:
            pass
    session.status = STATUS_UNDONE if not problems else STATUS_DONE
    session.save()
    return restored, problems


# ---------------------------------------------------------------------- trabajador


class ConvertWorker(QObject):
    """Crea los MP3 (en su propio hilo). No toca la biblioteca ni mueve originales: eso lo hace
    el hilo principal al recibir `converted`, para que todo quede anotado en el mismo sitio."""

    progress = Signal(int, int, str)
    converted = Signal(int, str)  # índice del elemento, error («» si salió bien)
    finished = Signal(bool)  # cancelado

    def __init__(self, items: list[tuple[Conversion, Track]]) -> None:
        super().__init__()
        self._items = items
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        for index, (item, track) in enumerate(self._items):
            if self._cancelled:
                break
            self.progress.emit(index, len(self._items), track.title)
            try:
                self._convert(item, track)
                self.converted.emit(index, "")
            except ConversionError as exc:
                self.converted.emit(index, str(exc))
            except Exception as exc:  # nunca dejar el hilo colgado
                log.exception("Error inesperado al convertir %s", item.original)
                self.converted.emit(index, f"Error inesperado: {exc}")
        self.progress.emit(len(self._items), len(self._items), "")
        self.finished.emit(self._cancelled)

    def _convert(self, item: Conversion, track: Track) -> None:
        if not os.path.isfile(item.original):
            raise ConversionError("El archivo original no se encuentra.")
        rate, channels = target_format(item.original)
        bitrate = target_bitrate(item.original)
        fmt = QAudioFormat()
        fmt.setSampleRate(rate)
        fmt.setChannelCount(channels)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)

        # Paso 1: pico del original. Algunos archivos (p. ej. WMA) tienen picos por encima de 0 dBFS;
        # pasarlos a 16 bits los recortaría (distorsión). Si es así, se baja lo justo antes de codificar.
        peak = [0.0]

        def find_peak(buffer) -> None:
            samples = np.frombuffer(bytes(buffer.constData()), dtype=np.float32)
            if len(samples):
                peak[0] = max(peak[0], float(np.abs(samples).max()))

        failure = decode_file(item.original, fmt, find_peak)
        if failure:
            raise ConversionError(f"No se pudo leer el audio original ({failure}).")
        scale = 1.0 if peak[0] <= 0.999 else 0.999 / peak[0]

        # Paso 2: codificar con LAME.
        temp = item.mp3 + ".convirtiendo.tmp"
        writer = Mp3Writer(temp, bitrate, rate, channels)

        def on_buffer(buffer) -> None:
            samples = np.frombuffer(bytes(buffer.constData()), dtype=np.float32)
            writer.write((np.clip(samples * scale, -1.0, 1.0) * 32767).astype("<i2").tobytes())

        failure = decode_file(item.original, fmt, on_buffer)  # suelta el original al terminar
        error = [failure] if failure else []
        if error or writer.frames == 0:
            writer.abort()
            raise ConversionError(f"No se pudo leer el audio original ({error[0] if error else 'sin audio'}).")
        try:
            writer.close()
            seconds = writer.frames / rate
            # Un original dañado puede terminar de leerse antes de tiempo sin dar error: se compara con
            # la duración del original, no solo con lo que se llegó a leer.
            expected = original_seconds(track)
            if expected > 1 and abs(seconds - expected) > max(2.0, expected * 0.02):
                raise ConversionError(
                    f"Solo se pudieron leer {seconds:.0f} s de {expected:.0f} s: el original podría estar dañado."
                )
            copy_tags(item.original, temp, track, original_cover(item.original))
            verify_mp3(temp, seconds)
            restore_steps = 0
            if scale < 1.0:
                # Devolver el nivel original DENTRO del MP3, sin pérdida (ganancia global, pasos de 1,5 dB).
                lowered_db = -20 * math.log10(scale)
                restore_steps = min(int(lowered_db // mp3gain.STEP_DB), mp3gain.inspect(temp).max_up_steps)
                if restore_steps > 0:
                    mp3gain.apply_steps(temp, restore_steps)
            # rename (no replace): en Windows falla si ya existe un archivo con ese nombre, así que
            # nunca se pisa un archivo que haya aparecido mientras tanto.
            if os.path.exists(item.mp3):
                raise ConversionError(f"Ya existe «{os.path.basename(item.mp3)}»: no se sobrescribe.")
            os.rename(temp, item.mp3)
        except Exception as exc:  # cualquier fallo: no dejar el temporal junto a la música
            writer.abort()
            if isinstance(exc, ConversionError):
                raise
            if isinstance(exc, OSError):
                raise ConversionError(f"No se pudo guardar el MP3 ({exc}).") from exc
            raise ConversionError(f"No se pudo terminar el MP3 ({exc}).") from exc
        log.info(
            "Convertido a MP3 %d kbps: %s → %s (pico original %.2f dBFS, nivel restituido %+.1f dB)",
            bitrate, item.original, item.mp3, 20 * math.log10(max(peak[0], 1e-9)), restore_steps * mp3gain.STEP_DB,
        )
