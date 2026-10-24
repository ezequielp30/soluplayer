"""Barra superior: controles, progreso, canción actual y búsqueda."""

from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSlider,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..models import Track
from ..player import RepeatMode
from ..utils import format_time
from . import theme
from .covers import CoverProvider
from .icons import ACCENT, MUTED, TEXT, icon

COVER_SIZE = 52


class JumpSlider(QSlider):
    """Slider que salta al punto donde se hace clic (no avanza por páginas)."""

    released_at = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._dragging = False

    @property
    def dragging(self) -> bool:
        return self._dragging

    def _value_at(self, x: float) -> int:
        handle = self.style().pixelMetric(QStyle.PixelMetric.PM_SliderLength, None, self)
        span = max(1, self.width() - handle)
        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), int(x - handle / 2), span
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._dragging = True
            self.setValue(self._value_at(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self.setValue(self._value_at(event.position().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setValue(self._value_at(event.position().x()))
            self.released_at.emit(self.value())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _cancel_drag(self) -> None:
        # Si aparece un diálogo mientras se arrastra, el «soltar» nunca llega: sin esto la barra
        # quedaría congelada (ya no seguiría la canción).
        self._dragging = False

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.EnabledChange and not self.isEnabled():
            self._cancel_drag()
        super().changeEvent(event)

    def focusOutEvent(self, event) -> None:
        self._cancel_drag()
        super().focusOutEvent(event)

    def hideEvent(self, event) -> None:
        self._cancel_drag()
        super().hideEvent(event)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.UngrabMouse:  # otra ventana se quedó con el mouse
            self._cancel_drag()
        return super().event(event)


def _tool_button(name: str, tooltip: str, size: int = 20, checkable: bool = False) -> QToolButton:
    button = QToolButton()
    button.setIcon(icon(name, TEXT, size))
    button.setIconSize(QSize(size, size))
    button.setToolTip(tooltip)
    button.setCheckable(checkable)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return button


class PlayerBar(QFrame):
    play_pause_clicked = Signal()
    stop_clicked = Signal()
    prev_clicked = Signal()
    next_clicked = Signal()
    seek_requested = Signal(int)
    volume_changed = Signal(int)
    mute_toggled = Signal(bool)
    shuffle_toggled = Signal(bool)
    repeat_clicked = Signal()
    equalizer_clicked = Signal()
    search_changed = Signal(str)

    def __init__(self, covers: CoverProvider, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PlayerBar")
        self._covers = covers
        self._duration = 0
        self._show_remaining = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        # Controles de transporte: el botón reproducir es el único relleno de color.
        self.btn_prev = _tool_button("prev", "Anterior", 20)
        self.btn_play = _tool_button("play", "Reproducir (Espacio)", 20)
        self.btn_play.setObjectName("PlayButton")
        self.btn_play.setFixedSize(44, 44)
        self.btn_next = _tool_button("next", "Siguiente", 20)
        self.btn_stop = _tool_button("stop", "Detener", 16)
        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_stop)
        layout.addSpacing(10)

        # Canción actual + progreso
        now = QFrame()
        now.setObjectName("NowPlaying")
        now.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        now.setMinimumWidth(280)
        now_layout = QHBoxLayout(now)
        now_layout.setContentsMargins(8, 8, 14, 8)
        now_layout.setSpacing(12)

        self.cover = QLabel()
        self.cover.setFixedSize(COVER_SIZE, COVER_SIZE)
        now_layout.addWidget(self.cover)

        info = QVBoxLayout()
        info.setSpacing(1)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.meter = LevelMeter()
        self.title = QLabel("Nada en reproducción")
        self.title.setObjectName("NowTitle")
        self.subtitle = QLabel("Elige una canción y haz doble clic para escucharla")
        self.subtitle.setObjectName("NowSubtitle")
        for label in (self.title, self.subtitle):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title_row.addWidget(self.meter, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.title, 1)
        info.addLayout(title_row)
        info.addWidget(self.subtitle)

        progress = QHBoxLayout()
        progress.setSpacing(8)
        self.elapsed = QLabel("0:00")
        self.elapsed.setObjectName("TimeLabel")
        self.elapsed.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.progress = JumpSlider()
        self.progress.setRange(0, 0)
        self.progress.setEnabled(False)
        self.remaining = QLabel("0:00")
        self.remaining.setObjectName("TimeLabel")
        self.remaining.setToolTip("Clic para alternar entre tiempo restante y duración total")
        self.remaining.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remaining.mousePressEvent = self._toggle_time_mode  # type: ignore[assignment]
        progress.addWidget(self.elapsed)
        progress.addWidget(self.progress, 1)
        progress.addWidget(self.remaining)
        info.addLayout(progress)
        now_layout.addLayout(info, 1)
        layout.addWidget(now, 1)

        # Modos y volumen
        self.btn_shuffle = _tool_button("shuffle", "Orden aleatorio", 18, checkable=True)
        self.btn_repeat = _tool_button("repeat", "Repetición: desactivada", 18)
        self.btn_eq = _tool_button("equalizer", "Ecualizador (Ctrl+E)", 18)
        self.btn_mute = _tool_button("volume", "Silenciar", 18, checkable=True)
        self.volume = JumpSlider()
        self.volume.setRange(0, 100)
        self.volume.setFixedWidth(96)
        self.volume.setToolTip("Volumen")
        layout.addSpacing(10)
        layout.addWidget(self.btn_shuffle)
        layout.addWidget(self.btn_repeat)
        layout.addWidget(self.btn_eq)
        layout.addSpacing(8)
        layout.addWidget(self.btn_mute)
        layout.addWidget(self.volume)
        layout.addSpacing(12)

        # Búsqueda (con retardo para no consultar en cada pulsación)
        self.search = QLineEdit()
        self.search.setObjectName("SearchField")
        self.search.setPlaceholderText("Buscar título, artista o álbum")
        self.search.setClearButtonEnabled(True)
        self._search_action = self.search.addAction(icon("search", MUTED, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setMaximumWidth(300)
        layout.addWidget(self.search)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(lambda: self.search_changed.emit(self.search.text()))
        self.search.textChanged.connect(lambda _: self._search_timer.start())

        # Señales
        self.btn_play.clicked.connect(self.play_pause_clicked)
        self.btn_stop.clicked.connect(self.stop_clicked)
        self.btn_prev.clicked.connect(self.prev_clicked)
        self.btn_next.clicked.connect(self.next_clicked)
        self.btn_shuffle.toggled.connect(self._on_shuffle)
        self.btn_repeat.clicked.connect(self.repeat_clicked)
        self.btn_eq.clicked.connect(self.equalizer_clicked)
        self.btn_mute.toggled.connect(self._on_mute)
        self.volume.valueChanged.connect(self.volume_changed)
        self.progress.valueChanged.connect(self._on_progress_value)
        self.progress.released_at.connect(self.seek_requested)

        self._track: Track | None = None
        self._playing = False
        self._repeat_mode = RepeatMode.OFF
        self._eq_on = False
        self.set_track(None)
        self.refresh_icons()

    # ------------------------------------------------------------------ API pública

    def refresh_icons(self) -> None:
        """Vuelve a dibujar iconos y carátula con los colores del tema activo."""
        self.btn_prev.setIcon(icon("prev", TEXT, 20))
        self.btn_next.setIcon(icon("next", TEXT, 20))
        self.btn_stop.setIcon(icon("stop", MUTED, 16))
        self._search_action.setIcon(icon("search", MUTED, 16))
        self.set_playing(self._playing)
        self._update_shuffle_icon(self.btn_shuffle.isChecked())
        self.set_repeat(self._repeat_mode)
        self._on_mute_icon(self.btn_mute.isChecked())
        self.set_equalizer_on(self._eq_on)
        self.cover.setPixmap(self._covers.pixmap(self._track.cover_hash if self._track else None, COVER_SIZE))
        self.meter.update()

    def set_equalizer_on(self, on: bool) -> None:
        """El icono del ecualizador va en color de acento mientras está activado."""
        self._eq_on = on
        self.btn_eq.setIcon(icon("equalizer", "accent_text" if on else TEXT, 18))
        self.btn_eq.setToolTip("Ecualizador: activado (Ctrl+E)" if on else "Ecualizador: desactivado (Ctrl+E)")

    def set_track(self, track: Track | None) -> None:
        self._track = track
        self.cover.setPixmap(self._covers.pixmap(track.cover_hash if track else None, COVER_SIZE))
        self.meter.setVisible(track is not None)
        if track is None:
            self.title.setText("Nada en reproducción")
            self.subtitle.setText("Elige una canción y haz doble clic para escucharla")
            self.set_duration(0)
            self.set_position(0)
        else:
            self.title.setText(track.title)
            self.subtitle.setText(f"{track.artist} — {track.album}")
            self.title.setToolTip(track.title)
            self.subtitle.setToolTip(f"{track.artist} — {track.album}\n{track.path}")
            self.set_duration(track.duration_ms)

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        self.meter.set_active(playing)
        self.btn_play.setIcon(icon("pause" if playing else "play", "on_accent", 20))
        self.btn_play.setToolTip("Pausar (Espacio)" if playing else "Reproducir (Espacio)")

    def set_duration(self, ms: int) -> None:
        self._duration = max(0, ms)
        self.progress.setRange(0, self._duration)
        self.progress.setEnabled(self._duration > 0)
        self._update_time_labels(self.progress.value())

    def set_position(self, ms: int) -> None:
        if not self.progress.dragging:
            self.progress.blockSignals(True)
            self.progress.setValue(ms)
            self.progress.blockSignals(False)
            self._update_time_labels(ms)

    def set_volume(self, percent: int) -> None:
        self.volume.setValue(percent)

    def set_muted(self, muted: bool) -> None:
        self.btn_mute.setChecked(muted)

    def set_shuffle(self, enabled: bool) -> None:
        self.btn_shuffle.blockSignals(True)
        self.btn_shuffle.setChecked(enabled)
        self.btn_shuffle.blockSignals(False)
        self._update_shuffle_icon(enabled)

    def set_repeat(self, mode: int) -> None:
        mode = RepeatMode(mode)
        self._repeat_mode = mode
        name = "repeat_one" if mode == RepeatMode.ONE else "repeat"
        color = TEXT if mode == RepeatMode.OFF else ACCENT
        self.btn_repeat.setIcon(icon(name, color, 18))
        text = {
            RepeatMode.OFF: "desactivada",
            RepeatMode.ALL: "toda la lista",
            RepeatMode.ONE: "una canción",
        }[mode]
        self.btn_repeat.setToolTip(f"Repetición: {text} (clic para cambiar)")

    def clear_search(self) -> None:
        self._search_timer.stop()
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)

    # ------------------------------------------------------------------ interno

    def _on_progress_value(self, value: int) -> None:
        if self.progress.dragging:
            self._update_time_labels(value)

    def _update_time_labels(self, position: int) -> None:
        self.elapsed.setText(format_time(position))
        if self._show_remaining:
            left = max(0, self._duration - position)
            self.remaining.setText("−" + format_time(-(-left // 1000) * 1000))  # segundos hacia arriba
        else:
            self.remaining.setText(format_time(self._duration))

    def _toggle_time_mode(self, _event) -> None:
        self._show_remaining = not self._show_remaining
        self._update_time_labels(self.progress.value())

    def _on_shuffle(self, enabled: bool) -> None:
        self._update_shuffle_icon(enabled)
        self.shuffle_toggled.emit(enabled)

    def _update_shuffle_icon(self, enabled: bool) -> None:
        self.btn_shuffle.setIcon(icon("shuffle", ACCENT if enabled else TEXT, 18))
        self.btn_shuffle.setToolTip("Orden aleatorio: " + ("activado" if enabled else "desactivado"))

    def _on_mute(self, muted: bool) -> None:
        self._on_mute_icon(muted)
        self.mute_toggled.emit(muted)

    def _on_mute_icon(self, muted: bool) -> None:
        self.btn_mute.setIcon(icon("mute" if muted else "volume", ACCENT if muted else TEXT, 18))
        self.btn_mute.setToolTip("Quitar silencio" if muted else "Silenciar")


class LevelMeter(QWidget):
    """Tres barras de nivel en ámbar junto al título: se mueven mientras suena la música
    y quedan quietas y bajas en pausa. Es la única animación de la interfaz."""

    BARS = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._phase = 0.0
        self._active = False
        self._timer = QTimer(self)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self._tick)
        self.setToolTip("Reproduciendo")

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            self._timer.start()
        else:
            self._timer.stop()
        self.setToolTip("Reproduciendo" if active else "En pausa")
        self.update()

    def _tick(self) -> None:
        self._phase += 0.42
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.qcolor("accent_text" if self._active else "faint"))
        width, gap = 3.0, 2.5
        for i in range(self.BARS):
            if self._active:
                # Ondas desfasadas: simulan un vúmetro sin leer la señal real.
                level = 0.35 + 0.65 * abs(math.sin(self._phase * (1.0 + i * 0.37) + i * 1.3))
            else:
                level = (0.35, 0.55, 0.3)[i]
            height = max(3.0, self.height() * level)
            x = i * (width + gap)
            painter.drawRoundedRect(QRectF(x, self.height() - height, width, height), 1.5, 1.5)
        painter.end()
