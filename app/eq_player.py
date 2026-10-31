"""Motor de reproducción con ecualizador.

El reproductor de Qt (QMediaPlayer) no deja procesar el audio antes de que suene, así que con él no se
puede ecualizar. Este motor hace el camino completo: decodifica el archivo con el mismo FFmpeg de Qt
(QAudioDecoder), le aplica el ecualizador (app/equalizer.py) y lo envía a la salida de audio (QAudioSink).

Tiene los mismos métodos y señales que QMediaPlayer que usa PlaybackController, para poder cambiar de
motor sin tocar el resto del programa. Solo se usa con el ecualizador activado; desactivado, se reproduce
con QMediaPlayer como siempre.

El audio decodificado (16 bits, ~11 MB por minuto) se guarda en memoria hasta RAM_BYTES (≈ 14 minutos); si
la canción es más larga (p. ej. un CD completo en un solo archivo) pasa a un archivo temporal en disco, que se
borra al cambiar de canción. Así no hay límite de duración y la memoria no crece con ella. Si el disco se
llena, la canción suena hasta donde se llegó a guardar.
"""

from __future__ import annotations

import glob
import logging
import os
import tempfile
import threading
import time

import numpy as np
import shiboken6
from PySide6.QtCore import QCoreApplication, QIODevice, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtMultimedia import (
    QAudio,
    QAudioDecoder,
    QAudioFormat,
    QAudioOutput,
    QAudioSink,
    QMediaDevices,
    QMediaPlayer,
)

from .equalizer import EqProcessor, EqSettings, soft_limit, to_pcm16

log = logging.getLogger(__name__)

RAM_BYTES = 160 * 1024 * 1024  # ≈ 7 min a 48 kHz estéreo en float; en bytes, no en minutos: no depende del dispositivo
RAM_STEP_BYTES = 16 * 1024 * 1024  # la memoria crece de a tramos, no duplicándose
_TEMP_PREFIX = "reproductor-eq-"
_BUFFER_MS = 750  # audio que tiene la salida por delante: aguanta 3/4 s con la ventana ocupada sin cortarse
# (pausa, saltos y cambio de canción siguen siendo inmediatos: se suspende o se rehace la salida)
_STALL_SECONDS = 20.0
_FADE_MS = 8  # fundido al empezar, saltar, pausar y reanudar: sin clic por cortar la onda a mitad
_SAMPLE = np.float32  # el audio decodificado se guarda en float: sin truncar a 16 bits ni recortar picos > 0 dBFS

State = QMediaPlayer.PlaybackState
Status = QMediaPlayer.MediaStatus


def _as_float(raw: bytes, sample_format) -> np.ndarray:
    """Muestras del decodificador como float32 en [-1, 1] (pueden pasar de 1 en archivos con picos > 0 dBFS).
    Se pide Float; si la plataforma entrega otro formato, se convierte sin perder lo que trae."""
    Fmt = QAudioFormat.SampleFormat
    if sample_format == Fmt.Float:
        return np.frombuffer(raw, dtype="<f4")
    if sample_format == Fmt.Int32:
        return np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    if sample_format == Fmt.UInt8:
        return (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0

class _PcmStore:
    """Audio decodificado de la canción actual: en memoria hasta RAM_BYTES; más largo, en un archivo
    temporal (la memoria deja de crecer). Lecturas y escrituras van con cerrojo: la salida de audio puede
    pedir datos desde su propio hilo."""

    def __init__(self, rate: int, channels: int) -> None:
        self._channels = channels
        self._bpf = np.dtype(_SAMPLE).itemsize * channels
        self._limit = RAM_BYTES // self._bpf  # en frames
        self._step = RAM_STEP_BYTES // self._bpf
        self._ram = np.zeros((0, channels), dtype=_SAMPLE)
        self._file = None
        self._path = ""
        self._lock = threading.Lock()
        self.frames = 0

    @property
    def on_disk(self) -> bool:
        return self._file is not None

    def append(self, data: np.ndarray) -> None:
        """Agrega frames (forma: frames × canales). Si el disco se llena o falta memoria lanza OSError o
        MemoryError y no cambia nada de lo ya guardado (se puede seguir oyendo hasta ahí)."""
        with self._lock:
            need = self.frames + len(data)
            if self._file is None and need > self._limit:
                self._spill()
            if self._file is not None:
                self._file.seek(self.frames * self._bpf)  # justo después de lo válido (no al final del archivo)
                self._file.write(data.tobytes())
                self._file.flush()  # que un disco lleno falle aquí y no más tarde, al leer
            else:
                if need > len(self._ram):
                    grown = np.zeros((min(self._limit, max(need, len(self._ram) + self._step)), self._channels), dtype=_SAMPLE)
                    grown[: self.frames] = self._ram[: self.frames]
                    self._ram = grown
                self._ram[self.frames:need] = data
            self.frames = need

    def read(self, start: int, count: int) -> np.ndarray:
        with self._lock:
            count = max(0, min(count, self.frames - start))
            if self._file is None:
                return self._ram[start:start + count].copy()
            try:
                self._file.seek(start * self._bpf)
                raw = self._file.read(count * self._bpf)
            except OSError as exc:
                log.warning("Ecualizador: no se pudo leer el temporal: %s", exc)
                self.frames = start  # lo que sigue no se puede oír: la canción termina aquí
                return np.zeros((0, self._channels), dtype=_SAMPLE)
            usable = len(raw) - len(raw) % self._bpf
            if usable < count * self._bpf:
                self.frames = start + usable // self._bpf  # el archivo quedó más corto de lo esperado
            return np.frombuffer(raw[:usable], dtype=_SAMPLE).reshape(-1, self._channels)

    def _spill(self) -> None:
        """Pasa lo que hay en memoria a un temporal, por tramos (sin duplicar la memoria). Si falla, se
        borra el temporal y todo sigue en memoria como estaba."""
        fd, path = tempfile.mkstemp(prefix=_TEMP_PREFIX, suffix=".pcm")
        file = os.fdopen(fd, "w+b")
        try:
            view = memoryview(self._ram[: self.frames].reshape(-1)).cast("B")
            for offset in range(0, len(view), RAM_STEP_BYTES):
                file.write(view[offset:offset + RAM_STEP_BYTES])
            file.flush()
        except BaseException:
            file.close()
            try:
                os.remove(path)
            except OSError:
                pass
            raise
        self._file, self._path = file, path
        self._ram = np.zeros((0, self._channels), dtype=_SAMPLE)
        log.info("Ecualizador: canción larga, el audio pasa a %s", self._path)

    def close(self) -> None:
        with self._lock:
            file, self._file = self._file, None
            if file is not None:
                file.close()
                try:
                    os.remove(self._path)
                except OSError:
                    pass
            self._ram = np.zeros((0, self._channels), dtype=_SAMPLE)
            self.frames = 0

    @staticmethod
    def remove_leftovers() -> None:
        """Borra temporales de una sesión que terminó de golpe (corte de luz, cierre forzado)."""
        for path in glob.glob(os.path.join(tempfile.gettempdir(), _TEMP_PREFIX + "*.pcm")):
            try:
                os.remove(path)
            except OSError:
                pass  # en uso o sin permiso: se intenta la próxima vez


class _Pull(QIODevice):
    """La salida de audio pide bytes y este dispositivo se los da desde el motor."""

    def __init__(self, engine: "EqPlayer") -> None:
        super().__init__()
        self._engine = engine

    def readData(self, maxlen: int) -> bytes:  # noqa: N802 (nombre de Qt)
        return self._engine._produce(maxlen)

    def writeData(self, _data) -> int:  # noqa: N802
        return -1

    def isSequential(self) -> bool:  # noqa: N802
        return True

    def bytesAvailable(self) -> int:  # noqa: N802
        return 1 << 20


class _Preload(QObject):
    """La canción siguiente, decodificada de antemano (en su propio almacén) para pasar a ella sin silencio."""

    def __init__(self, url: QUrl, rate: int, channels: int, parent: QObject) -> None:
        super().__init__(parent)
        self.url = QUrl(url)
        self._channels = channels
        self._rate = rate
        self.store = _PcmStore(rate, channels)
        self.done = False
        self.failed = False
        self.duration_ms = 0
        self._in_signal = False
        decoder = QAudioDecoder(self)
        fmt = QAudioFormat()
        fmt.setSampleRate(rate)
        fmt.setChannelCount(channels)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
        decoder.setAudioFormat(fmt)
        decoder.bufferReady.connect(lambda: self._guarded(self._on_buffer))
        decoder.finished.connect(lambda: self._guarded(self._on_finished))
        decoder.error.connect(lambda _code: self._guarded(self._on_error))
        decoder.durationChanged.connect(lambda ms: setattr(self, "duration_ms", int(ms)) if ms and ms > 0 else None)
        decoder.setSource(self.url)
        self._decoder: QAudioDecoder | None = decoder
        decoder.start()

    def _guarded(self, handler) -> None:
        self._in_signal = True
        try:
            handler()
        finally:
            self._in_signal = False

    def _on_buffer(self) -> None:
        if self._decoder is None:
            return
        buffer = self._decoder.read()
        data = _as_float(bytes(buffer.constData()), buffer.format().sampleFormat())
        frames = len(data) // self._channels
        if not frames:
            return
        try:
            self.store.append(data[: frames * self._channels].reshape(frames, self._channels))
        except (OSError, MemoryError) as exc:
            log.warning("Sin silencios: no se pudo preparar %s: %s", self.url.toLocalFile(), exc)
            self._finish(failed=self.store.frames == 0)

    def _on_finished(self) -> None:
        if self.store.frames == 0:
            self._finish(failed=True)  # sin audio: la siguiente se carga como siempre (y avisa su error)
            return
        self.duration_ms = int(self.store.frames * 1000 / self._rate)
        self._finish(failed=False)

    def _on_error(self) -> None:
        self._finish(failed=self.store.frames == 0)

    def _finish(self, failed: bool) -> None:
        self.done = True
        self.failed = failed
        self._release_decoder()

    def _release_decoder(self) -> None:
        decoder, self._decoder = self._decoder, None
        if decoder is None:
            return
        decoder.blockSignals(True)
        if self._in_signal:
            QTimer.singleShot(0, lambda d=decoder: EqPlayer._dispose_decoder(d))
        else:
            EqPlayer._dispose_decoder(decoder)  # suelta el archivo en el acto

    def discard(self) -> None:
        self._release_decoder()
        self.store.close()
        self.deleteLater()


class EqPlayer(QObject):
    positionChanged = Signal("qlonglong")
    durationChanged = Signal("qlonglong")
    playbackStateChanged = Signal(QMediaPlayer.PlaybackState)
    mediaStatusChanged = Signal(QMediaPlayer.MediaStatus)
    errorOccurred = Signal(QMediaPlayer.Error, str)
    need_next = Signal()  # la canción actual ya está decodificada: se puede preparar la siguiente (preload)
    advanced = Signal(QUrl)  # empezó a sonar la canción preparada, sin silencio y sin cerrar la salida

    def __init__(self, audio: QAudioOutput, settings: EqSettings | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._audio = audio
        self._settings = settings or EqSettings()
        self._source = QUrl()
        self._state = State.StoppedState
        self._status = Status.NoMedia
        self._decoder: QAudioDecoder | None = None
        self._in_decoder_signal = False  # dentro de una señal del decodificador: no se lo puede borrar ahí
        self._next: _Preload | None = None  # la canción siguiente, preparada para pasar sin silencio
        self._feeding: _Preload | None = None  # la preparada que ya suena pero todavía se decodifica
        self._old_frames = 0  # frames de la canción anterior que siguen en la cola de salida
        self._announce = False  # avisar (advanced) cuando la canción nueva empiece a oírse
        self._waiting_start = False  # «reproducir» pedido: la salida se abre cuando haya audio decodificado
        self.paused_by_device = False  # en pausa porque la salida se cayó (no porque lo pidió el usuario)
        self._sink: QAudioSink | None = None
        self._device: _Pull | None = None
        self._format = self._choose_format()
        self._rate = self._format.sampleRate()
        self._channels = 2
        self._eq = EqProcessor(self._rate, self._channels, self._settings)
        _PcmStore.remove_leftovers()
        self._store = _PcmStore(self._rate, self._channels)
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._store.close)  # no dejar el temporal de una canción larga
        self._reset_data()
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)
        self._last_data = time.monotonic()
        self._gain = 1.0  # volumen del fundido de pausa/reanudar (multiplica al del usuario)
        self._boost = 1.0  # ganancia extra dentro del audio (igualar volumen que sube por encima del 100 %)
        self._rng = np.random.default_rng()  # dither al pasar a 16 bits
        self._ramp_target, self._ramp_step, self._ramp_done = 1.0, 0.0, None
        self._ramp = QTimer(self)
        self._ramp.setTimerType(Qt.TimerType.PreciseTimer)
        self._ramp.setInterval(_FADE_MS // 4 or 1)
        self._ramp.timeout.connect(self._ramp_tick)
        audio.volumeChanged.connect(self._apply_volume)
        audio.mutedChanged.connect(self._apply_volume)
        audio.deviceChanged.connect(self._device_changed)

    # ------------------------------------------------------------------ formato y datos

    def _choose_format(self) -> QAudioFormat:
        device = self._audio.device() if not self._audio.device().isNull() else QMediaDevices.defaultAudioOutput()
        fmt = QAudioFormat()
        fmt.setSampleRate(device.preferredFormat().sampleRate() or 48000)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
        if not device.isFormatSupported(fmt):
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        return fmt

    def _reset_data(self) -> None:
        self._store.close()  # audio decodificado de la canción anterior (y su temporal, si había)
        self._decode_done = False
        self._duration_ms = 0
        self._cursor = 0  # próximo frame decodificado que entra al ecualizador
        self._fifo = np.zeros((0, self._channels), dtype=np.float32)  # ya ecualizado, listo para sonar
        self._skip = 0  # frames de «arranque» del filtro que se descartan
        self._origin = 0  # frame de la fuente donde empezó la entrega actual
        self._delivered = 0  # frames reales entregados desde el origen
        self._flushed = False
        self._eos = False
        self._eos_at = 0.0
        self._eq.reset()
        self._skip = self._latency()
        self._fade_left = self._fade_frames()
        self._old_frames = 0
        self._announce = False

    def _fade_frames(self) -> int:
        return max(1, int(self._rate * _FADE_MS / 1000))

    def _latency(self) -> int:
        return self._eq.latency

    # ------------------------------------------------------------------ API como QMediaPlayer

    def source(self) -> QUrl:
        return self._source

    def preload(self, url: QUrl | None) -> None:
        """Prepara la canción que sigue (None = ninguna). Al terminar la actual se pasa a ella sin silencio."""
        if self._next is not None and url is not None and self._next.url == url and not self._next.failed:
            return
        self._drop_next()
        if url is not None and not url.isEmpty():
            self._next = _Preload(url, self._rate, self._channels, self)

    def _drop_next(self) -> None:
        if self._next is not None:
            self._next.discard()
            self._next = None

    def _drop_feeding(self) -> None:
        if self._feeding is not None:
            self._feeding._release_decoder()
            self._feeding.deleteLater()  # su almacén ya es el de la canción actual: se cierra con ella
            self._feeding = None

    def setSource(self, url: QUrl) -> None:  # noqa: N802
        self.paused_by_device = False
        self._drop_next()
        self._drop_feeding()
        self._teardown_decoder()
        self._stop_sink()
        self._set_state(State.StoppedState)
        self._source = QUrl(url)
        self._reset_data()
        if url.isEmpty():
            self._set_status(Status.NoMedia)
            self.durationChanged.emit(0)
            return
        self._set_status(Status.LoadingMedia)
        self._start_decoder(url)

    def play(self) -> None:
        if self._source.isEmpty():
            return
        if self._status == Status.EndOfMedia:
            self.setPosition(0)
        if self._state == State.PausedState and self._sink is not None:
            self._ramp.stop()
            self._gain = 0.0
            self._apply_volume()
            self._sink.resume()
            self._ramp_to(1.0)
        else:
            self._ramp.stop()
            self._gain = 1.0
            self._start_sink_when_ready()
        self._set_state(State.PlayingState)
        self._timer.start()

    def _ready_to_start(self) -> bool:
        """Ya está decodificado lo que llena la salida entera (más el retardo del filtro): así no se rellena
        con trozos de silencio mientras el decodificador termina, que se oían como cortes al empezar."""
        need = int(self._rate * _BUFFER_MS / 1000) + self._eq.latency + self._eq.block
        return self._decode_done or self._store.frames - self._cursor >= need

    def _start_sink_when_ready(self) -> None:
        self._waiting_start = not self._ready_to_start()
        if not self._waiting_start:
            self._start_sink()

    def _start_if_waiting(self) -> None:
        if self._waiting_start and self._state == State.PlayingState and self._ready_to_start():
            self._waiting_start = False
            self._start_sink()

    def pause(self) -> None:
        self.paused_by_device = False
        if self._waiting_start:  # todavía no sonaba: no hay salida que suspender
            self._waiting_start = False
            self._set_state(State.PausedState)
            return
        if self._state == State.PlayingState and self._sink is not None:
            self._set_state(State.PausedState)
            sink = self._sink
            self._ramp_to(0.0, lambda: sink.suspend() if sink is self._sink and self._state == State.PausedState else None)

    def set_boost(self, gain: float) -> None:
        """Ganancia (lineal, ≥ 1) que se aplica dentro del audio cuando el volumen pedido pasa del 100 %."""
        self._boost = max(1.0, float(gain))

    def _ramp_to(self, target: float, done=None) -> None:
        """Lleva el volumen de la salida hasta `target` en unos milisegundos (fundido de pausa/reanudar)."""
        self._ramp_target, self._ramp_done = target, done
        self._ramp_step = (target - self._gain) / 4
        self._ramp.start()

    def _ramp_tick(self) -> None:
        self._gain += self._ramp_step
        if (self._ramp_step >= 0 and self._gain >= self._ramp_target) or (self._ramp_step < 0 and self._gain <= self._ramp_target):
            self._gain = self._ramp_target
            self._ramp.stop()
        self._apply_volume()
        if not self._ramp.isActive() and self._ramp_done is not None:
            done, self._ramp_done = self._ramp_done, None
            done()

    def stop(self) -> None:
        self._waiting_start = False
        self.paused_by_device = False
        self._ramp.stop()  # detener es inmediato: suelta el archivo en el acto (Papelera, mover, renombrar)
        self._ramp_done = None
        self._gain = 1.0
        self._stop_sink()
        self._seek_frames(0)
        self._set_state(State.StoppedState)
        self.positionChanged.emit(0)

    def position(self) -> int:
        return int(self._source_frame() * 1000 / self._rate)

    def duration(self) -> int:
        return int(self._duration_ms)

    def setPosition(self, ms: int) -> None:  # noqa: N802
        frame = max(0, int(ms * self._rate / 1000))
        playing = self._state == State.PlayingState
        if self._sink is not None:
            self._stop_sink()
        self._seek_frames(frame)
        if self._status == Status.EndOfMedia:
            self._set_status(Status.BufferedMedia)
        if playing:
            self._start_sink_when_ready()
        self.positionChanged.emit(self.position())

    def playbackState(self) -> QMediaPlayer.PlaybackState:  # noqa: N802
        return self._state

    def mediaStatus(self) -> QMediaPlayer.MediaStatus:  # noqa: N802
        return self._status

    def setAudioOutput(self, _output) -> None:  # noqa: N802 (se usa siempre la del controlador)
        pass

    # ------------------------------------------------------------------ ecualizador

    def set_settings(self, settings: EqSettings) -> None:
        """Cambia el ecualizador en vivo: se nota en el próximo bloque (~0,2 s), sin cortes."""
        self._settings = settings
        self._eq.set_settings(settings)

    # ------------------------------------------------------------------ decodificación

    def _start_decoder(self, url: QUrl) -> None:
        decoder = QAudioDecoder(self)
        fmt = QAudioFormat()
        fmt.setSampleRate(self._rate)
        fmt.setChannelCount(self._channels)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
        decoder.setAudioFormat(fmt)
        decoder.bufferReady.connect(self._on_buffer)
        decoder.finished.connect(self._on_decoded)
        decoder.error.connect(self._on_decode_error)
        decoder.durationChanged.connect(self._on_duration)
        decoder.setSource(url)
        self._decoder = decoder
        self._last_data = time.monotonic()
        decoder.start()
        self._timer.start()

    def _teardown_decoder(self) -> None:
        """Suelta el decodificador (y con él el archivo). En el acto, para que se pueda renombrar, mover o
        enviar a la Papelera la canción que suena; solo se difiere si se llama desde una señal del propio
        decodificador (borrarlo ahí dentro cerraría el programa de golpe)."""
        decoder, self._decoder = self._decoder, None
        if decoder is None:
            return
        decoder.blockSignals(True)
        if self._in_decoder_signal:
            QTimer.singleShot(0, lambda d=decoder: self._dispose_decoder(d))
        else:
            self._dispose_decoder(decoder)

    @staticmethod
    def _dispose_decoder(decoder: QAudioDecoder) -> None:
        if shiboken6.isValid(decoder):
            decoder.stop()
            decoder.setSource(QUrl())
            shiboken6.delete(decoder)  # ya (no deleteLater): Windows no deja mover un archivo abierto

    def _on_buffer(self) -> None:
        self._in_decoder_signal = True
        try:
            self._handle_buffer()
        finally:
            self._in_decoder_signal = False

    def _handle_buffer(self) -> None:
        if self._decoder is None:
            return
        buffer = self._decoder.read()
        data = _as_float(bytes(buffer.constData()), buffer.format().sampleFormat())
        frames = len(data) // self._channels
        if not frames:
            return
        self._last_data = time.monotonic()
        try:
            self._store.append(data[: frames * self._channels].reshape(frames, self._channels))
        except (OSError, MemoryError) as exc:  # disco lleno o sin memoria: suena hasta donde se llegó a guardar
            log.warning("Ecualizador: no se pudo guardar el audio de %s: %s", self._source.toLocalFile(), exc)
            self._teardown_decoder()
            self._decode_done = True
            return
        if self._status == Status.LoadingMedia:
            self._set_status(Status.LoadedMedia)
            self._set_status(Status.BufferedMedia)
        self._start_if_waiting()

    def _on_duration(self, ms) -> None:
        if ms and ms > 0:
            self._duration_ms = int(ms)
            self.durationChanged.emit(self._duration_ms)

    def _on_decoded(self) -> None:
        self._in_decoder_signal = True
        try:
            self._handle_decoded()
        finally:
            self._in_decoder_signal = False

    def _handle_decoded(self) -> None:
        self._decode_done = True
        exact = int(self._store.frames * 1000 / self._rate)
        if exact and abs(exact - self._duration_ms) > 50:
            self._duration_ms = exact
            self.durationChanged.emit(exact)
        if self._status == Status.LoadingMedia:  # archivo sin audio
            self._set_status(Status.InvalidMedia)
            self.errorOccurred.emit(QMediaPlayer.Error.FormatError, "el archivo no tiene audio")
        self._teardown_decoder()  # todo decodificado: el archivo original queda libre
        self._start_if_waiting()
        if self._status != Status.InvalidMedia:
            QTimer.singleShot(0, self.need_next.emit)  # ya se puede preparar la siguiente

    def _on_decode_error(self, _code) -> None:
        self._in_decoder_signal = True
        try:
            self._handle_decode_error()
        finally:
            self._in_decoder_signal = False

    def _handle_decode_error(self) -> None:
        text = self._decoder.errorString() if self._decoder is not None else ""
        log.warning("Ecualizador: no se pudo decodificar %s: %s", self._source.toLocalFile(), text)
        self._teardown_decoder()
        self._decode_done = True
        if self._store.frames == 0:
            self._set_status(Status.InvalidMedia)
            self.errorOccurred.emit(QMediaPlayer.Error.FormatError, text or "error de decodificación")

    # ------------------------------------------------------------------ salida

    def _start_sink(self) -> None:
        self._stop_sink()
        device = self._audio.device() if not self._audio.device().isNull() else QMediaDevices.defaultAudioOutput()
        self._sink = QAudioSink(device, self._format, self)
        self._sink.setBufferSize(int(self._rate * _BUFFER_MS / 1000) * self._format.bytesPerFrame())
        sink = self._sink
        sink.stateChanged.connect(lambda state: self._on_sink_state(sink, state))
        self._apply_volume()
        self._device = _Pull(self)
        self._device.open(QIODevice.OpenModeFlag.ReadOnly)
        self._sink.start(self._device)

    def _stop_sink(self) -> None:
        sink, self._sink = self._sink, None
        if sink is not None:
            sink.stop()
            sink.deleteLater()
        if self._device is not None:
            self._device.close()
            self._device.deleteLater()
            self._device = None

    def _apply_volume(self, *_args) -> None:
        if self._sink is not None:
            self._sink.setVolume(0.0 if self._audio.isMuted() else self._audio.volume() * self._gain)

    def _on_sink_state(self, sink: QAudioSink, state) -> None:
        """La salida se detuvo sola con un error (auriculares USB o Bluetooth desconectados, vuelta de la
        suspensión): se pasa a «Pausa» en el mismo punto, para que no figure sonando sin sonar. No es un
        error de la canción; Reproducir abre otra vez la salida que haya."""
        if sink is not self._sink or state != QAudio.State.StoppedState or sink.error() == QAudio.Error.NoError:
            return  # una salida que ya se cambió o se detuvo a propósito
        if self._state != State.PlayingState:
            return
        log.warning("La salida de audio se detuvo (%s): queda en pausa hasta que vuelva una salida", sink.error().name)
        position = self.position()
        self._stop_sink()
        self._seek_frames(int(position * self._rate / 1000))
        self._set_state(State.PausedState)
        self.paused_by_device = True  # al volver una salida, sigue sola (si el usuario no hizo otra cosa)

    def _device_changed(self) -> None:
        """La salida de Windows cambió (auriculares, Bluetooth…): se sigue sonando por la nueva, en el formato
        que ella prefiere. Si la música se había pausado porque la salida anterior se cayó, sigue sola."""
        resume = self.paused_by_device and self._state == State.PausedState
        self.paused_by_device = False
        new = self._choose_format()
        if new.sampleRate() != self._rate or new.sampleFormat() != self._format.sampleFormat():
            self._renegotiate(new, resume)
            return
        if self._sink is None:
            if resume:
                self.play()
            return
        position = self.position()
        playing = self._state == State.PlayingState
        self._stop_sink()
        self._seek_frames(int(position * self._rate / 1000))
        if playing:
            self._start_sink()

    def resume_after_device(self) -> None:
        """Apareció una salida de audio (p. ej. volvió el Bluetooth): si la pausa la causó la caída, sigue."""
        if self.paused_by_device:
            self._device_changed()

    def _renegotiate(self, fmt: QAudioFormat, resume: bool) -> None:
        """La salida nueva trabaja a otra frecuencia o formato: se vuelve a decodificar a esa frecuencia desde
        el mismo punto (sin que Windows tenga que convertir, ni la salida rechace el formato)."""
        url, position = QUrl(self._source), self.position()
        playing = self._state == State.PlayingState or resume
        log.info("Salida nueva: %d Hz, %s (antes %d Hz)", fmt.sampleRate(), fmt.sampleFormat().name, self._rate)
        self._stop_sink()
        self._format = fmt
        if fmt.sampleRate() != self._rate:
            self._rate = fmt.sampleRate()
            self._eq = EqProcessor(self._rate, self._channels, self._eq.settings)
        if url.isEmpty():
            return
        self.setSource(url)
        if position:
            self.setPosition(position)
        if playing:
            self.play()

    def _seek_frames(self, frame: int) -> None:
        self._cursor = frame
        self._origin = self._cursor
        self._delivered = 0
        self._fifo = np.zeros((0, self._channels), dtype=np.float32)
        self._flushed = False
        self._eos = False
        self._eq.reset()
        self._skip = self._latency()
        self._fade_left = self._fade_frames()
        self._old_frames = 0
        self._announce = False

    def _source_frame(self) -> int:
        buffered = 0
        if self._sink is not None:
            buffered = max(0, self._sink.bufferSize() - self._sink.bytesFree()) // self._format.bytesPerFrame()
        return max(self._origin, self._origin + self._delivered - buffered)

    def _produce(self, maxlen: int) -> bytes:
        """Lo que pide la salida de audio: audio ecualizado, o silencio mientras se decodifica."""
        bpf = self._format.bytesPerFrame()
        want = max(1, maxlen // bpf)
        while len(self._fifo) < want and not self._flushed:
            if self._feeding is not None and self._feeding.done:
                self._decode_done = True  # la canción preparada terminó de decodificarse mientras sonaba
                self._duration_ms = self._feeding.duration_ms or self._duration_ms
                self._drop_feeding()
            available = self._store.frames - self._cursor
            if available > 0:
                chunk = self._store.read(self._cursor, 8192)
                if not len(chunk):
                    break  # el temporal no pudo dar datos (se recortó lo ilegible): sin bucle infinito
                self._cursor += len(chunk)
                out = self._eq.process(chunk)
            elif self._decode_done and self._next is not None and not self._next.failed:
                self._switch_to_next()  # sin vaciar el filtro: el sonido sigue de corrido
                continue
            elif self._decode_done:
                out = self._eq.flush()
                self._flushed = True
            else:
                break  # todavía decodificando
            if self._skip and len(out):
                drop = min(self._skip, len(out))
                out = out[drop:]
                self._skip -= drop
            if len(out):
                self._fifo = np.concatenate([self._fifo, out]) if len(self._fifo) else out
        if not len(self._fifo):
            if self._flushed:
                if not self._eos:
                    self._eos = True
                    self._eos_at = time.monotonic()
                return b""
            return bytes(min(maxlen, int(self._rate * 0.02) * bpf))  # 20 ms de silencio mientras carga
        take = min(want, len(self._fifo))
        frames, self._fifo = self._fifo[:take].copy(), self._fifo[take:]
        old = min(take, self._old_frames)  # lo que aún era de la canción anterior no cuenta para la nueva
        self._old_frames -= old
        self._delivered += take - old
        if self._boost != 1.0:
            frames = soft_limit(frames * self._boost)  # nunca pasa de 0 dBFS
        if self._fade_left:  # después de empezar o saltar: entra con un fundido, no a mitad de onda
            total = self._fade_frames()
            n = min(self._fade_left, take)
            done = total - self._fade_left
            frames[:n] *= ((np.arange(done, done + n, dtype=np.float32) + 1) / total)[:, None]
            self._fade_left -= n
        if self._format.sampleFormat() == QAudioFormat.SampleFormat.Int16:  # salida que no acepta float
            return to_pcm16(frames, self._rng)
        return frames.astype("<f4").tobytes()

    def _switch_to_next(self) -> None:
        """La canción actual se acabó y la siguiente está preparada: se sigue con ella en la misma salida."""
        nxt, self._next = self._next, None
        self._teardown_decoder()
        self._store.close()
        self._store = nxt.store
        self._source = QUrl(nxt.url)
        self._decode_done = nxt.done
        self._feeding = None if nxt.done else nxt
        if nxt.done:
            nxt._release_decoder()
            nxt.deleteLater()
        self._duration_ms = nxt.duration_ms
        self._cursor = 0
        self._origin = 0
        self._old_frames = len(self._fifo)  # lo que queda en la cola es todavía de la anterior
        self._delivered = 0
        self._announce = True

    def _tick(self) -> None:
        if self._announce and self._sink is not None:
            buffered = max(0, self._sink.bufferSize() - self._sink.bytesFree()) // self._format.bytesPerFrame()
            if self._old_frames == 0 and self._delivered > buffered:  # ya se oye la canción nueva
                self._announce = False
                self.durationChanged.emit(self._duration_ms)
                self.advanced.emit(QUrl(self._source))
                if self._decode_done:
                    self.need_next.emit()
        if self._decoder is not None and not self._decode_done and time.monotonic() - self._last_data > _STALL_SECONDS:
            log.warning("Ecualizador: el archivo no responde: %s", self._source.toLocalFile())
            self._teardown_decoder()
            self._decode_done = True
            if self._store.frames == 0:
                self._set_status(Status.InvalidMedia)
                self.errorOccurred.emit(QMediaPlayer.Error.ResourceError, "el archivo no responde")
        if self._state == State.PlayingState:
            self.positionChanged.emit(self.position())
            # Fin: ya se entregó todo y pasó lo que quedaba en la salida (Windows no siempre avisa con
            # un cambio de estado cuando se acaban los datos).
            drained = self._eos and (time.monotonic() - self._eos_at) * 1000 > _BUFFER_MS + 120
            if drained and self._sink is not None:
                self._stop_sink()
                self._set_state(State.StoppedState)
                self._set_status(Status.EndOfMedia)
        elif self._decode_done and self._decoder is None:
            self._timer.stop()

    def _set_state(self, state) -> None:
        if state != self._state:
            self._state = state
            self.playbackStateChanged.emit(state)

    def _set_status(self, status) -> None:
        if status != self._status:
            self._status = status
            self.mediaStatusChanged.emit(status)
