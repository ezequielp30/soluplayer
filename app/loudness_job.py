"""Trabajos en segundo plano: medir la sonoridad de las canciones y ajustar el volumen de los MP3."""

from __future__ import annotations

import logging
import os

import numpy as np
from mutagen import MutagenError
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtMultimedia import QAudioFormat

from . import mp3gain
from .audio_decode import decode_file
from .loudness import RATE, LoudnessMeter
from .models import Track

log = logging.getLogger(__name__)

ADJUSTABLE = frozenset({".mp3"})  # formatos que se pueden ajustar sin recomprimir


def can_adjust(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in ADJUSTABLE


class AnalyzeWorker(QObject):
    """Decodifica cada canción a 48 kHz y mide LUFS y pico real. Vive en su propio hilo."""

    progress = Signal(int, int, str)
    measured = Signal(int, object, object, str, int)  # id, LUFS, dBTP, error ("" si ninguno), pasos anotados en el MP3
    finished = Signal(bool)  # cancelado

    def __init__(self, tracks: list[Track]) -> None:
        super().__init__()
        self._tracks = tracks
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        try:
            self._run()
        except Exception:  # nunca dejar el hilo colgado: «terminado» se avisa siempre
            log.exception("Error inesperado al analizar el volumen")
        finally:
            self.progress.emit(len(self._tracks), len(self._tracks), "")
            self.finished.emit(self._cancelled)

    def _run(self) -> None:
        fmt = QAudioFormat()
        fmt.setSampleRate(RATE)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
        for index, track in enumerate(self._tracks):
            if self._cancelled:
                break
            self.progress.emit(index, len(self._tracks), track.title)
            if not os.path.isfile(track.path):
                self.measured.emit(track.id, None, None, "El archivo no se encuentra.", 0)
                continue
            meter = LoudnessMeter()
            failure = decode_file(
                track.path, fmt, lambda buffer, m=meter: m.add(np.frombuffer(bytes(buffer.constData()), dtype=np.float32))
            )
            error: list[str] = [failure] if failure else []
            try:
                lufs, peak = meter.result()
            except Exception as exc:
                lufs, peak = None, None
                error.append(str(exc))
            annotated = 0
            if can_adjust(track.path):
                try:
                    annotated = mp3gain.read_applied_steps(track.path)
                except Exception as exc:  # se medirá igual; la anotación se leerá la próxima vez
                    log.warning("No se pudo leer la anotación de volumen de %s: %s", track.path, exc)
            self.measured.emit(track.id, lufs, peak, error[0] if error else "", annotated)


class AdjustWorker(QObject):
    """Aplica (o revierte) pasos de 1,5 dB dentro de los MP3, sin recomprimir."""

    progress = Signal(int, int, str)
    adjusted = Signal(int, int, int, str)  # id, pasos aplicados ahora, pasos totales en el archivo, error
    finished = Signal()

    def __init__(self, jobs: list[tuple[Track, int]]) -> None:
        super().__init__()
        self._jobs = jobs

    @Slot()
    def run(self) -> None:
        try:
            for index, (track, steps) in enumerate(self._jobs):
                self.progress.emit(index, len(self._jobs), track.title)
                self._adjust(track, steps)
        finally:  # nunca dejar el hilo colgado (la ventana no podría cerrarse)
            self.progress.emit(len(self._jobs), len(self._jobs), "")
            self.finished.emit()

    def _adjust(self, track: Track, steps: int) -> None:
        try:
            # Si la anotación no se puede leer (archivo bloqueado…), se falla: suponer «0» sumaría mal.
            before = mp3gain.read_applied_steps(track.path)
            if steps < 0:  # revertir: lo que diga el propio archivo manda
                steps = -before if before else steps
            if steps > 0:  # nunca pasar del límite interno del MP3 (255)
                steps = min(steps, mp3gain.inspect(track.path).max_up_steps)
                if steps <= 0:
                    raise mp3gain.Mp3GainError("La ganancia interna del archivo ya está al máximo.")
            if steps == 0:
                raise mp3gain.Mp3GainError("No hay ningún ajuste que aplicar o revertir.")
            total = max(0, before + steps)
            # Audio y anotación en una sola escritura atómica: o cambian los dos, o ninguno.
            mp3gain.apply_steps(track.path, steps, annotate_total=total)
            log.info("Volumen ajustado %+d pasos (%+.1f dB, total %+d): %s", steps, steps * mp3gain.STEP_DB, total, track.path)
            self.adjusted.emit(track.id, steps, total, "")
        except (mp3gain.Mp3GainError, OSError, MutagenError) as exc:
            log.warning("No se ajustó el volumen de %s: %s", track.path, exc)
            reason = "El archivo está en uso o no se puede leer." if isinstance(exc, (OSError, MutagenError)) else str(exc)
            self.adjusted.emit(track.id, 0, -1, reason)
        except Exception as exc:
            log.exception("Error inesperado al ajustar el volumen de %s", track.path)
            self.adjusted.emit(track.id, 0, -1, f"Error inesperado: {exc}")
