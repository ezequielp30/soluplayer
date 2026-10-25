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
from PySide6.QtCore import QCoreApplication, QIODevice, QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import (
    QAudio,
    QAudioDecoder,
    QAudioFormat,
    QAudioOutput,
    QAudioSink,
    QMediaDevices,
    QMediaPlayer,
)

from .equalizer import EqProcessor, EqSettings

log = logging.getLogger(__name__)

RAM_BYTES = 160 * 1024 * 1024  # ≈ 14 min a 48 kHz estéreo; en bytes, no en minutos: no depende del dispositivo
RAM_STEP_BYTES = 16 * 1024 * 1024  # la memoria crece de a tramos, no duplicándose
_TEMP_PREFIX = "reproductor-eq-"
_BUFFER_MS = 250  # audio que tiene la salida por delante: poco, para que pausa y saltos respondan rápido
_STALL_SECONDS = 20.0

State = QMediaPlayer.PlaybackState
Status = QMediaPlayer.MediaStatus


class _PcmStore:
    """Audio decodificado de la canción actual: en memoria hasta RAM_BYTES; más largo, en un archivo
    temporal (la memoria deja de crecer). Lecturas y escrituras van con cerrojo: la salida de audio puede
    pedir datos desde su propio hilo."""

    def __init__(self, rate: int, channels: int) -> None:
        self._channels = channels
        self._bpf = 2 * channels
        self._limit = RAM_BYTES // self._bpf  # en frames
        self._step = RAM_STEP_BYTES // self._bpf
        self._ram = np.zeros((0, channels), dtype=np.int16)
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
                    grown = np.zeros((min(self._limit, max(need, len(self._ram) + self._step)), self._channels), dtype=np.int16)
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
                return np.zeros((0, self._channels), dtype=np.int16)
            usable = len(raw) - len(raw) % self._bpf
            if usable < count * self._bpf:
                self.frames = start + usable // self._bpf  # el archivo quedó más corto de lo esperado
            return np.frombuffer(raw[:usable], dtype=np.int16).reshape(-1, self._channels)

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
        self._ram = np.zeros((0, self._channels), dtype=np.int16)
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
            self._ram = np.zeros((0, self._channels), dtype=np.int16)
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


class EqPlayer(QObject):
    positionChanged = Signal("qlonglong")
    durationChanged = Signal("qlonglong")
    playbackStateChanged = Signal(QMediaPlayer.PlaybackState)
    mediaStatusChanged = Signal(QMediaPlayer.MediaStatus)
    errorOccurred = Signal(QMediaPlayer.Error, str)

    def __init__(self, audio: QAudioOutput, settings: EqSettings | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._audio = audio
        self._settings = settings or EqSettings()
        self._source = QUrl()
        self._state = State.StoppedState
        self._status = Status.NoMedia
        self._decoder: QAudioDecoder | None = None
        self._in_decoder_signal = False  # dentro de una señal del decodificador: no se lo puede borrar ahí
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

    def _latency(self) -> int:
        from .equalizer import LATENCY_FRAMES

        return LATENCY_FRAMES

    # ------------------------------------------------------------------ API como QMediaPlayer

    def source(self) -> QUrl:
        return self._source

    def setSource(self, url: QUrl) -> None:  # noqa: N802
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
            self._sink.resume()
        else:
            self._start_sink()
        self._set_state(State.PlayingState)
        self._timer.start()

    def pause(self) -> None:
        if self._state == State.PlayingState and self._sink is not None:
            self._sink.suspend()
            self._set_state(State.PausedState)

    def stop(self) -> None:
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
            self._start_sink()
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
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
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
        data = np.frombuffer(bytes(buffer.constData()), dtype=np.int16)
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
            self._sink.setVolume(0.0 if self._audio.isMuted() else self._audio.volume())

    def _on_sink_state(self, sink: QAudioSink, state) -> None:
        """La salida se detuvo sola con un error (auriculares USB o Bluetooth desconectados, vuelta de la
        suspensión): se pasa a «Pausa» en el mismo punto, para que no figure sonando sin sonar. No es un
        error de la canción; Reproducir abre otra vez la salida que haya."""
        if sink is not self._sink or state != QAudio.State.StoppedState or sink.error() == QAudio.Error.NoError:
            return  # una salida que ya se cambió o se detuvo a propósito
        if self._state != State.PlayingState:
            return
        log.warning("La salida de audio se detuvo (%s): el ecualizador queda en pausa", sink.error().name)
        position = self.position()
        self._stop_sink()
        self._seek_frames(int(position * self._rate / 1000))
        self._set_state(State.PausedState)

    def _device_changed(self) -> None:
        """La salida de Windows cambió (auriculares, Bluetooth…): se sigue sonando por la nueva."""
        if self._sink is None:
            return
        position = self.position()
        playing = self._state == State.PlayingState
        self._stop_sink()
        self._seek_frames(int(position * self._rate / 1000))
        if playing:
            self._start_sink()

    def _seek_frames(self, frame: int) -> None:
        self._cursor = frame
        self._origin = self._cursor
        self._delivered = 0
        self._fifo = np.zeros((0, self._channels), dtype=np.float32)
        self._flushed = False
        self._eos = False
        self._eq.reset()
        self._skip = self._latency()

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
            available = self._store.frames - self._cursor
            if available > 0:
                chunk = self._store.read(self._cursor, 8192).astype(np.float32) / 32768.0
                if not len(chunk):
                    break  # el temporal no pudo dar datos (se recortó lo ilegible): sin bucle infinito
                self._cursor += len(chunk)
                out = self._eq.process(chunk)
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
        frames, self._fifo = self._fifo[:take], self._fifo[take:]
        self._delivered += take
        if self._format.sampleFormat() == QAudioFormat.SampleFormat.Int16:
            return (np.clip(frames, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        return frames.astype("<f4").tobytes()

    def _tick(self) -> None:
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
