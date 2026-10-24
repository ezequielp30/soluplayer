"""Reproducción con Qt Multimedia y gestión de la cola."""

from __future__ import annotations

import logging
import random
from enum import IntEnum

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

from .models import Track

log = logging.getLogger(__name__)

_RESTART_THRESHOLD_MS = 3000

_ERROR_MESSAGES = {
    QMediaPlayer.Error.ResourceError: "No se pudo abrir el archivo. Puede estar dañado, "
    "en uso por otro programa o en una unidad desconectada.",
    QMediaPlayer.Error.FormatError: "El formato del archivo no es compatible o el archivo está dañado.",
    QMediaPlayer.Error.AccessDeniedError: "No hay permiso para leer el archivo.",
    QMediaPlayer.Error.NetworkError: "No se pudo acceder al archivo a través de la red.",
}


class RepeatMode(IntEnum):
    OFF = 0
    ALL = 1
    ONE = 2


class PlaybackController(QObject):
    current_track_changed = Signal(object)  # Track | None
    playing_changed = Signal(bool)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    error_occurred = Signal(object, str)  # Track | None, mensaje
    track_skipped = Signal(object)  # Track omitida porque el archivo no existe
    track_started = Signal(object)  # Track que empezó a sonar (una vez por carga)
    shuffle_changed = Signal(bool)
    repeat_changed = Signal(int)
    output_changed = Signal(str)  # nombre del dispositivo de salida nuevo

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._audio = QAudioOutput(QMediaDevices.defaultAudioOutput(), self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)
        # Si en Windows cambia la salida predeterminada (auriculares, Bluetooth, HDMI…),
        # Qt seguiría enviando el audio al dispositivo anterior: hay que seguirla a mano.
        self._devices = QMediaDevices(self)
        self._devices.audioOutputsChanged.connect(self._follow_default_output)
        log.info("Salida de audio: %s", self._audio.device().description())

        self._queue: list[Track] = []
        self._order: list[int] = []
        self._pos = -1
        self._shuffle = False
        self._repeat = RepeatMode.OFF
        self._started_pending = False

        self._player.positionChanged.connect(lambda p: self.position_changed.emit(int(p)))
        self._player.durationChanged.connect(lambda d: self.duration_changed.emit(int(d)))
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)

    # ------------------------------------------------------------------ estado

    @property
    def current_track(self) -> Track | None:
        if 0 <= self._pos < len(self._order):
            return self._queue[self._order[self._pos]]
        return None

    @property
    def has_queue(self) -> bool:
        return bool(self._queue)

    @property
    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @property
    def repeat(self) -> RepeatMode:
        return self._repeat

    def position(self) -> int:
        return int(self._player.position())

    def duration(self) -> int:
        return int(self._player.duration())

    # ------------------------------------------------------------------ cola

    def play_queue(self, tracks: list[Track], start_index: int = 0) -> None:
        if not tracks:
            return
        self._queue = list(tracks)
        start_index = max(0, min(start_index, len(self._queue) - 1))
        self._build_order(start_index)
        self._load_current(autoplay=True)

    def _build_order(self, current_index: int) -> None:
        indices = list(range(len(self._queue)))
        if self._shuffle:
            rest = [i for i in indices if i != current_index]
            random.shuffle(rest)
            self._order = [current_index] + rest
            self._pos = 0
        else:
            self._order = indices
            self._pos = current_index

    def append_tracks(self, tracks: list[Track]) -> None:
        """Agrega canciones al final de la cola sin interrumpir la que suena (si no hay cola, la crea)."""
        if not self._queue or self.current_track is None:
            self.play_queue(tracks, 0)
            return
        start = len(self._queue)
        self._queue.extend(tracks)
        added = list(range(start, len(self._queue)))
        if self._shuffle:
            random.shuffle(added)
        self._order.extend(added)

    def update_track(self, track: Track) -> None:
        """Refleja cambios de metadatos/ruta en la cola (p. ej. tras relocalizar)."""
        self.update_tracks({track.id: track})

    def update_tracks(self, by_id: dict[int, Track]) -> None:
        """Igual que update_track para muchas canciones, recorriendo la cola una sola vez."""
        current = self.current_track
        for i, queued in enumerate(self._queue):
            new = by_id.get(queued.id)
            if new is not None:
                self._queue[i] = new.copy(entry_id=queued.entry_id)
        if (
            current is not None and current.id in by_id and by_id[current.id].path != current.path
            and not self._player.source().isEmpty()
        ):
            # La canción actual cambió de archivo (se movió, se convirtió a MP3…) y el reproductor tenía
            # cargado el anterior: se carga el nuevo. Si ya se había soltado, se deja suelto (cargarlo
            # bloquearía el archivo en Windows); «Reproducir» lo vuelve a cargar.
            self._reload_current()

    def _reload_current(self) -> None:
        track = self.current_track
        if track is None:
            return
        was_playing = self.is_playing
        position = self.position()
        self._player.setSource(QUrl.fromLocalFile(track.path) if track.check_available() else QUrl())
        if not self._player.source().isEmpty():
            self._player.setPosition(position)
            if was_playing:
                self._player.play()

    def remove_tracks(self, track_ids: set[int]) -> None:
        """Quita de la cola canciones eliminadas de la biblioteca. Si se quita la que suena, se pasa a la
        siguiente que quede (en vez de vaciar toda la cola)."""
        if not any(t.id in track_ids for t in self._queue):
            return
        current = self.current_track
        removing_current = current is not None and current.id in track_ids
        was_playing = self.is_playing
        if removing_current:
            self._player.stop()
            self._player.setSource(QUrl())  # suelta el archivo (puede ir a la Papelera)
        keep = [i for i, t in enumerate(self._queue) if t.id not in track_ids]
        remap = {old: new for new, old in enumerate(keep)}
        old_order, old_pos = self._order, self._pos
        self._queue = [self._queue[i] for i in keep]
        self._order = [remap[i] for i in old_order if i in remap]
        if not self._queue:
            self._order, self._pos = [], -1
            self.current_track_changed.emit(None)
            return
        if not removing_current:
            self._pos = self._order.index(remap[old_order[old_pos]]) if current is not None else -1
            return
        # La siguiente en el orden que todavía exista.
        following = [remap[i] for i in old_order[old_pos + 1:] if i in remap]
        if not following:
            self._player.stop()
            self._pos = 0
            self._load_current(autoplay=False)
            return
        self._pos = self._order.index(following[0])
        self._load_current(autoplay=was_playing)

    # ------------------------------------------------------------------ controles

    def toggle_play(self) -> None:
        if self.is_playing:
            self._player.pause()
        else:
            self.play()

    def play(self) -> None:
        if self.current_track is None:
            return
        if self._player.source().isEmpty():
            # El archivo se soltó (para moverlo, convertirlo o ajustarlo): se vuelve a cargar, sin
            # contarla otra vez como reproducida.
            pending = self._started_pending
            self._load_current(autoplay=True)
            self._started_pending = pending
            return
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def seek(self, position_ms: int) -> None:
        if self.current_track is not None:
            self._player.setPosition(max(0, int(position_ms)))

    def set_volume(self, percent: int) -> None:
        self._audio.setVolume(max(0, min(100, percent)) / 100)

    def set_muted(self, muted: bool) -> None:
        self._audio.setMuted(muted)

    def set_shuffle(self, enabled: bool) -> None:
        if enabled == self._shuffle:
            return
        self._shuffle = enabled
        if self._queue:
            if self.current_track is not None:
                self._build_order(self._order[self._pos])
            else:
                self._build_order(0)
                self._pos = -1  # sin canción actual: reordenar no debe «elegir» una sin cargarla
        self.shuffle_changed.emit(enabled)

    def set_repeat(self, mode: RepeatMode | int) -> None:
        self._repeat = RepeatMode(mode)
        self.repeat_changed.emit(int(self._repeat))

    def cycle_repeat(self) -> RepeatMode:
        self.set_repeat((int(self._repeat) + 1) % 3)
        return self._repeat

    def next(self) -> None:
        self._advance(1, user=True)

    def previous(self) -> None:
        if not self._queue:
            return
        if self.position() > _RESTART_THRESHOLD_MS or (self._pos <= 0 and self._repeat == RepeatMode.OFF):
            self._player.setPosition(0)
            self._player.play()
            return
        self._advance(-1, user=True)

    def _advance(self, step: int, user: bool) -> None:
        if not self._order:
            return
        new_pos = self._pos + step
        if not 0 <= new_pos < len(self._order):
            wrap = self._repeat == RepeatMode.ALL or (user and self._repeat == RepeatMode.ONE)
            if not wrap:
                # Fin de la cola: se detiene y queda lista desde el principio.
                self._player.stop()
                self._pos = 0
                self._load_current(autoplay=False, direction=1)
                return
            new_pos %= len(self._order)
        self._pos = new_pos
        self._load_current(autoplay=True, direction=1 if step >= 0 else -1)

    def _load_current(self, autoplay: bool, direction: int = 1) -> None:
        """Carga la pista actual, saltando las que ya no existen en disco."""
        for _ in range(len(self._order)):
            track = self.current_track
            if track is None:
                break
            if track.check_available():
                self._player.setSource(QUrl.fromLocalFile(track.path))
                log.info("Reproduciendo: %s", track.path)
                self._started_pending = True  # se cuenta como reproducida cuando realmente empiece a sonar
                self.current_track_changed.emit(track)
                if autoplay:
                    self._player.play()
                return
            self.track_skipped.emit(track)
            new_pos = self._pos + direction
            if not 0 <= new_pos < len(self._order) and autoplay and self._repeat != RepeatMode.ALL:
                # Sin «repetir todo», saltar la última que falta es llegar al final, no volver a empezar.
                self._player.stop()
                self._pos = 0
                self._load_current(autoplay=False)
                return
            self._pos = new_pos % len(self._order)
        self._player.stop()
        self._player.setSource(QUrl())
        self._pos = -1
        self.current_track_changed.emit(None)
        self.error_occurred.emit(None, "Ninguna canción de la cola está disponible en el disco.")

    def release_source(self) -> None:
        """Detiene y suelta el archivo actual (para que Windows deje moverlo o modificarlo)."""
        self._player.stop()
        self._player.setSource(QUrl())

    def output_device(self):
        return self._audio.device()

    def output_name(self) -> str:
        return self._audio.device().description() or "(sin dispositivo)"

    def _follow_default_output(self) -> None:
        default = QMediaDevices.defaultAudioOutput()
        if default.isNull():
            log.warning("Windows no informa ninguna salida de audio")
            return
        if default.id() != self._audio.device().id():
            self._audio.setDevice(default)
            log.info("La salida de audio cambió a: %s", default.description())
            self.output_changed.emit(default.description())

    # ------------------------------------------------------------------ eventos de Qt

    def _on_state_changed(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        if playing and self._started_pending and self.current_track is not None:
            self._started_pending = False
            self.track_started.emit(self.current_track)
        self.playing_changed.emit(playing)

    def _on_media_status(self, status) -> None:
        if status in (QMediaPlayer.MediaStatus.InvalidMedia, QMediaPlayer.MediaStatus.StalledMedia):
            track = self.current_track
            log.warning("Estado de reproducción %s en %s", status.name, track.path if track else "-")
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self._repeat == RepeatMode.ONE:
            self._player.setPosition(0)
            self._player.play()
        else:
            self._advance(1, user=False)

    def _on_error(self, error, error_string: str = "") -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        message = _ERROR_MESSAGES.get(error) or f"No se pudo reproducir el archivo. {error_string}".strip()
        track = self.current_track
        log.error("Error de reproducción (%s: %s) en %s", error.name, error_string, track.path if track else "-")
        self.error_occurred.emit(self.current_track, message)
