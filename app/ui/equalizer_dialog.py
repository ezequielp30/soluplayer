"""Ventana del ecualizador: 10 bandas, nivel general, presets por género, presets propios y activar/desactivar.

No bloquea el programa: se puede dejar abierta mientras suena la música, y cada cambio se oye en el acto.
La configuración se guarda en las preferencias y se recupera al abrir el programa.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..equalizer import BAND_LABELS, MAX_DB, PRESETS, EqSettings
from ..eq_player import MAX_MINUTES
from ..preferences import Preferences
from .dialogs import ask, note_label

CUSTOM = "Personalizado"
_STEPS = 10  # el control se mueve de 0,1 en 0,1 dB


class EqualizerDialog(QDialog):
    def __init__(self, prefs: Preferences, apply: Callable[[bool, EqSettings], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ecualizador")
        self.setWindowFlag(Qt.WindowType.Tool)
        self._prefs = prefs
        self._apply = apply
        self._state = prefs.equalizer()
        self._loading = False
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(60)
        self._debounce.timeout.connect(self._commit)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.enabled = QCheckBox("Activar ecualizador")
        self.enabled.setObjectName("EqSwitch")
        self.enabled.toggled.connect(self._changed)
        top.addWidget(self.enabled)
        top.addStretch(1)
        top.addWidget(QLabel("Preset:"))
        self.preset = QComboBox()
        self.preset.setMinimumWidth(170)
        self.preset.activated.connect(self._preset_chosen)
        top.addWidget(self.preset)
        layout.addLayout(top)

        self.board = QFrame()
        self.board.setObjectName("EqBoard")
        grid = QGridLayout(self.board)
        grid.setHorizontalSpacing(6)
        self.sliders: list[QSlider] = []
        self.value_labels: list[QLabel] = []
        columns = [("Nivel", True)] + [(label, False) for label in BAND_LABELS]
        for col, (label, is_preamp) in enumerate(columns):
            value = QLabel("0")
            value.setObjectName("EqValue")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            slider = QSlider(Qt.Orientation.Vertical)
            slider.setObjectName("EqSlider")
            slider.setRange(int(-MAX_DB * _STEPS), int(MAX_DB * _STEPS))
            slider.setPageStep(_STEPS * 3)
            slider.setSingleStep(5)
            slider.setMinimumHeight(170)
            slider.setToolTip("Nivel general (antes de las bandas)" if is_preamp else f"Banda de {label} Hz")
            slider.valueChanged.connect(lambda _v, c=col: self._slider_moved(c))
            name = QLabel(label + ("" if is_preamp else ""))
            name.setObjectName("EqBandLabel")
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(value, 0, col * 2)
            grid.addWidget(slider, 1, col * 2, alignment=Qt.AlignmentFlag.AlignHCenter)
            grid.addWidget(name, 2, col * 2)
            if is_preamp:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.VLine)
                line.setObjectName("EqDivider")
                grid.addWidget(line, 0, 1, 3, 1)
            self.sliders.append(slider)
            self.value_labels.append(value)
        scale = QVBoxLayout()
        for text in (f"+{MAX_DB:.0f} dB", "0 dB", f"−{MAX_DB:.0f} dB"):
            mark = QLabel(text)
            mark.setObjectName("EqBandLabel")
            scale.addWidget(mark)
            if text != f"−{MAX_DB:.0f} dB":
                scale.addStretch(1)
        grid.addLayout(scale, 1, len(columns) * 2)
        layout.addWidget(self.board)

        self.prevent = QCheckBox("Evitar saturación (baja el nivel general lo que suba la banda más alta)")
        self.prevent.toggled.connect(self._changed)
        layout.addWidget(self.prevent)
        layout.addWidget(note_label(
            "El ecualizador cambia el sonido real (no solo el dibujo). Con el ecualizador activado el programa usa "
            f"su propio motor de audio; los archivos de más de {MAX_MINUTES} minutos suenan sin ecualizar."
        ))

        bottom = QHBoxLayout()
        self.btn_reset = QPushButton("Restablecer")
        self.btn_reset.setToolTip("Vuelve todas las bandas a 0 dB (preset Normal)")
        self.btn_reset.clicked.connect(self._reset)
        self.btn_save = QPushButton("Guardar como preset…")
        self.btn_save.clicked.connect(self._save_preset)
        self.btn_delete = QPushButton("Eliminar preset")
        self.btn_delete.clicked.connect(self._delete_preset)
        close = QPushButton("Cerrar")
        close.setObjectName("PrimaryButton")
        close.clicked.connect(self.close)
        for button in (self.btn_reset, self.btn_save, self.btn_delete):
            bottom.addWidget(button)
        bottom.addStretch(1)
        bottom.addWidget(close)
        layout.addLayout(bottom)

        self._load_state()

    # ------------------------------------------------------------------ estado

    def settings(self) -> EqSettings:
        values = [s.value() / _STEPS for s in self.sliders]
        return EqSettings(tuple(values[1:]), values[0], self.prevent.isChecked())

    def _fill_presets(self, current: str) -> None:
        self.preset.blockSignals(True)
        self.preset.clear()
        self.preset.addItems(list(PRESETS))
        custom = sorted(self._state["custom"])
        if custom:
            self.preset.insertSeparator(self.preset.count())
            self.preset.addItems(custom)
        self.preset.addItem(CUSTOM)
        index = self.preset.findText(current)
        self.preset.setCurrentIndex(index if index >= 0 else self.preset.findText(CUSTOM))
        self.preset.blockSignals(False)
        self.btn_delete.setEnabled(current in self._state["custom"])

    def _load_state(self) -> None:
        self._loading = True
        s = self._state
        self.enabled.setChecked(bool(s["enabled"]))
        self.prevent.setChecked(bool(s["prevent_clipping"]))
        self._set_sliders([s["preamp"]] + list(s["gains"]))
        self._fill_presets(s["preset"])
        self._loading = False
        self._update_enabled()

    def _set_sliders(self, values: list[float]) -> None:
        for slider, value in zip(self.sliders, values):
            slider.blockSignals(True)
            slider.setValue(int(round(float(value) * _STEPS)))
            slider.blockSignals(False)
        for col in range(len(self.sliders)):
            self._show_value(col)

    def _show_value(self, col: int) -> None:
        value = self.sliders[col].value() / _STEPS
        self.value_labels[col].setText(f"{value:+.1f}" if abs(value) >= 0.05 else "0")

    def _update_enabled(self) -> None:
        on = self.enabled.isChecked()
        for widget in (self.board, self.preset, self.prevent, self.btn_reset, self.btn_save):
            widget.setEnabled(on)
        self.btn_delete.setEnabled(on and self.preset.currentText() in self._state["custom"])

    # ------------------------------------------------------------------ cambios

    def _slider_moved(self, col: int) -> None:
        self._show_value(col)
        if self._loading:
            return
        if self.preset.currentText() != CUSTOM and self._preset_values(self.preset.currentText()) != self._current_values():
            self.preset.setCurrentIndex(self.preset.findText(CUSTOM))
            self.btn_delete.setEnabled(False)
        self._changed()

    def _current_values(self) -> tuple[float, ...]:
        return tuple(s.value() / _STEPS for s in self.sliders[1:])

    def _preset_values(self, name: str) -> tuple[float, ...] | None:
        if name in PRESETS:
            return tuple(float(v) for v in PRESETS[name])
        if name in self._state["custom"]:
            return tuple(float(v) for v in self._state["custom"][name].get("gains", []))
        return None

    def _preset_chosen(self, _index: int) -> None:
        name = self.preset.currentText()
        values = self._preset_values(name)
        if values is None:
            return
        preamp = self._state["custom"].get(name, {}).get("preamp", 0.0) if name in self._state["custom"] else 0.0
        self._set_sliders([preamp] + list(values))
        self.btn_delete.setEnabled(name in self._state["custom"])
        self._changed()

    def _changed(self, *_args) -> None:
        if self._loading:
            return
        self._update_enabled()
        self._debounce.start()

    def _commit(self) -> None:
        """Aplica al audio y guarda en las preferencias."""
        settings = self.settings()
        self._state.update(
            enabled=self.enabled.isChecked(), preset=self.preset.currentText(), gains=list(settings.gains),
            preamp=settings.preamp, prevent_clipping=settings.prevent_clipping,
        )
        self._prefs.set_equalizer(self._state)
        self._apply(self.enabled.isChecked(), settings)

    def _reset(self) -> None:
        self._set_sliders([0.0] * len(self.sliders))
        self.preset.setCurrentIndex(self.preset.findText("Normal"))
        self.btn_delete.setEnabled(False)
        self._changed()

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Guardar preset", "Nombre del preset:", text="Mi ecualización")
        name = " ".join(name.split()) if ok else ""
        if not name:
            return
        if name in PRESETS or name == CUSTOM:
            QMessageBox.information(self, "Guardar preset", f"«{name}» es un preset del programa: elige otro nombre.")
            return
        if name in self._state["custom"] and ask(
            self, "Guardar preset", f"Ya existe «{name}». ¿Reemplazarlo?",
            [("Reemplazar", QMessageBox.ButtonRole.AcceptRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
        ) != 0:
            return
        settings = self.settings()
        self._state["custom"][name] = {"gains": list(settings.gains), "preamp": settings.preamp}
        self._fill_presets(name)
        self._commit()

    def _delete_preset(self) -> None:
        name = self.preset.currentText()
        if name not in self._state["custom"]:
            return
        if ask(
            self, "Eliminar preset", f"¿Eliminar el preset «{name}»?",
            [("Eliminar", QMessageBox.ButtonRole.DestructiveRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Warning,
        ) != 0:
            return
        del self._state["custom"][name]
        self._fill_presets(CUSTOM)
        self._commit()
