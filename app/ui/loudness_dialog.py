"""Diálogo «Analizar y ajustar volumen»: mide todas las canciones y sube, de forma permanente y sin
pérdida, solo las que están muy bajas (MP3)."""

from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..file_operations import FileOperations
from ..loudness import CEILING_DBTP, MAX_GAIN, decide, reference_level
from ..loudness_job import AdjustWorker, AnalyzeWorker, can_adjust
from ..models import Track
from ..mp3gain import STEP_DB, steps_for_gain
from ..utils import plural
from . import theme
from .dialogs import ask, empty_state, note_label, set_primary, tidy_table
from .worker_runner import WorkerRunner

COL_USE, COL_SONG, COL_FORMAT, COL_LUFS, COL_PEAK, COL_DONE, COL_DIAG, COL_GAIN = range(8)
_TRACK = Qt.ItemDataRole.UserRole
FILTER_NEED, FILTER_DONE, FILTER_ALL = "need", "done", "all"


class LoudnessDialog(QDialog):
    def __init__(
        self,
        ops: FileOperations,
        tracks_provider: Callable[[], list[Track]],
        parent: QWidget | None = None,
        initial_filter: str = FILTER_NEED,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Analizar y ajustar volumen")
        self.resize(1180, 680)
        self._ops = ops
        self._tracks_provider = tracks_provider
        self._pending_save: list[tuple[int, float | None, float | None]] = []

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Mide la sonoridad de cada canción con el estándar profesional EBU R128 (LUFS) y su pico real (dBTP). "
            "Solo se proponen las canciones <b>claramente más bajas</b> que el resto de tu biblioteca, y la subida "
            f"se limita para que el pico nunca pase de {CEILING_DBTP:.0f} dBTP: <b>no se distorsiona</b>."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(note_label(
            "En los MP3 el ajuste es permanente y sin pérdida de calidad (no se recomprime, pasos de 1,5 dB); se "
            "nota en cualquier reproductor y se puede revertir. WMA, M4A y otros formatos no se pueden ajustar sin "
            "recomprimir: se indican pero no se tocan."
        ))

        row = QHBoxLayout()
        self.btn_analyze_new = QPushButton()
        self.btn_analyze_new.clicked.connect(lambda: self._start_analysis(only_new=True))
        self.btn_analyze_all = QPushButton()
        self.btn_analyze_all.clicked.connect(lambda: self._start_analysis(only_new=False))
        self.filter = QComboBox()
        self.filter.addItem("Mostrar: solo las que necesitan ajuste", FILTER_NEED)
        self.filter.addItem("Mostrar: ya ajustadas", FILTER_DONE)
        self.filter.addItem("Mostrar: todas", FILTER_ALL)
        self.filter.setCurrentIndex(max(0, self.filter.findData(initial_filter)))
        self.filter.currentIndexChanged.connect(self._refresh_table)
        row.addWidget(self.btn_analyze_new)
        row.addWidget(self.btn_analyze_all)
        row.addStretch(1)
        row.addWidget(self.filter)
        layout.addLayout(row)

        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(8)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.btn_stop = QPushButton("Detener")
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.status, 3)
        progress_row.addWidget(self.btn_stop)
        layout.addLayout(progress_row)
        self.runner = WorkerRunner(self, self.progress, self.status, self.btn_stop)
        self.runner.busy_changed.connect(self._update_buttons)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["", "Canción", "Formato", "Sonoridad", "Pico real", "Ajuste hecho", "Diagnóstico", "Subida"]
        )
        tidy_table(self.table)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in ((COL_USE, 30), (COL_SONG, 330), (COL_FORMAT, 70), (COL_LUFS, 95), (COL_PEAK, 90), (COL_DONE, 100), (COL_GAIN, 80)):
            header.resizeSection(col, width)
        header.setSectionResizeMode(COL_DIAG, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._update_buttons)
        self.empty, self._set_empty = empty_state()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        layout.addWidget(self.stack, 1)

        bottom = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        bottom.addWidget(self.summary, 1)
        self.btn_revert = QPushButton("Revertir ajuste de las seleccionadas…")
        self.btn_revert.setToolTip("Devuelve las canciones seleccionadas (ya ajustadas) a su volumen original")
        self.btn_revert.clicked.connect(self._revert_selected)
        self.btn_apply = QPushButton("Aplicar")
        self.btn_apply.clicked.connect(self._apply)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.reject)
        bottom.addWidget(self.btn_revert)
        bottom.addWidget(self.btn_apply)
        bottom.addWidget(close)
        layout.addLayout(bottom)

        self._refresh_table()

    # ------------------------------------------------------------------ análisis

    def _tracks(self) -> list[Track]:
        return self._tracks_provider()

    def _start_analysis(self, only_new: bool) -> None:
        if self.runner.busy:
            return
        tracks = [t for t in self._tracks() if t.available and (not only_new or t.loudness_lufs is None)]
        if not tracks:
            self.status.setText("No hay canciones pendientes de analizar.")
            return
        worker = AnalyzeWorker(tracks)
        self._measured_count, self._analysis_total = 0, len(tracks)
        worker.measured.connect(self._on_measured)  # método con @Slot: se ejecuta en el hilo principal
        self.runner.start(worker, len(tracks), "Analizando…", self._on_analysis_finished, label="Analizando")

    @Slot(int, object, object, str, int)
    def _on_measured(self, track_id: int, lufs, peak, error: str, annotated_steps: int) -> None:
        self._pending_save.append((track_id, lufs, peak))
        self._measured_count = getattr(self, "_measured_count", 0) + 1
        if annotated_steps:
            self._flush()
            self._ops.recover_volume_from_file(track_id, annotated_steps)
        if len(self._pending_save) >= 25:  # se guarda por tandas: si se detiene, no se pierde lo medido
            self._flush()

    def _flush(self) -> None:
        self._ops.save_measurements(self._pending_save)
        self._pending_save = []

    def _on_analysis_finished(self, cancelled: bool) -> None:
        self._flush()
        self._ops.changed()
        self._refresh_table()
        done = getattr(self, "_measured_count", 0)
        total = getattr(self, "_analysis_total", done)
        self.status.setText(
            f"Análisis detenido: se midieron {done} de {total}." if cancelled
            else f"Análisis terminado: {plural(done, 'canción medida', 'canciones medidas')}."
        )

    # ------------------------------------------------------------------ tabla

    def _rows(self) -> list[tuple[Track, object, int]]:
        tracks = self._tracks()
        reference = reference_level([t.loudness_lufs for t in tracks])
        self._reference = reference
        rows = []
        for track in tracks:
            decision = decide(track.loudness_lufs, track.true_peak_db, reference, track.norm_gain_db) if track.loudness_lufs is not None else None
            steps = steps_for_gain(decision.gain_db) if decision and can_adjust(track.path) and track.available else 0
            rows.append((track, decision, steps))
        return rows

    def _refresh_table(self) -> None:
        mode = self.filter.currentData()
        rows = self._rows()
        analyzed = sum(1 for t, d, _ in rows if d is not None)
        pending = sum(1 for t, d, _ in rows if d is None and t.available)
        need = [r for r in rows if r[1] is not None and r[1].status == "bajo"]
        fixable = [r for r in need if r[2] > 0]
        done = [r for r in rows if r[0].norm_gain_db > 0]
        shown = {FILTER_NEED: need, FILTER_DONE: done, FILTER_ALL: rows}[mode]
        self.table.blockSignals(True)
        self.table.setRowCount(len(shown))
        for row, (track, decision, steps) in enumerate(shown):
            use = QTableWidgetItem()
            if steps > 0:
                use.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                use.setCheckState(Qt.CheckState.Checked)
            else:
                use.setFlags(Qt.ItemFlag.ItemIsEnabled)
            use.setData(_TRACK, (track, steps))
            ext = os.path.splitext(track.path)[1].lstrip(".").upper()
            lufs = f"{track.loudness_lufs:.1f} LUFS" if track.loudness_lufs is not None else "—"
            peak = f"{track.true_peak_db:.1f} dBTP" if track.true_peak_db is not None else "—"
            done_text = f"+{track.norm_gain_db:.1f} dB" if track.norm_gain_db > 0 else ""
            if decision is None:
                diag = "Sin analizar"
            elif decision.status == "bajo" and steps == 0 and decision.gain_db > 0:
                diag = (
                    f"Necesita +{decision.gain_db:.1f} dB, pero el formato {ext} no se puede ajustar sin recomprimir."
                    if not can_adjust(track.path) else f"Necesita +{decision.gain_db:.1f} dB: menos de un paso de {STEP_DB} dB."
                )
            elif steps:
                applied = steps * STEP_DB
                diag = f"Muy baja ({decision.wanted_db:.1f} dB bajo la referencia): se sube +{applied:.1f} dB"
                if decision.limited_by_peak:
                    diag += "; no más, para que los picos no distorsionen."
                elif decision.wanted_db > MAX_GAIN - track.norm_gain_db:
                    diag += f"; no más: el tope por canción es +{MAX_GAIN:.0f} dB en total."
                else:
                    diag += f" (pasos de {STEP_DB} dB, sin pérdida)."
            else:
                diag = decision.reason
            gain = f"+{steps * STEP_DB:.1f} dB" if steps else ""
            cells = [use, track.title + " — " + track.artist, ext, lufs, peak, done_text, diag, gain]
            for col, value in enumerate(cells):
                item = value if isinstance(value, QTableWidgetItem) else QTableWidgetItem(value)
                if col == COL_SONG:
                    item.setToolTip(track.path)
                if col == COL_DIAG:
                    item.setToolTip(diag)
                if col in (COL_LUFS, COL_PEAK, COL_GAIN, COL_DONE):
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
                if col == COL_GAIN and steps:
                    item.setForeground(theme.qcolor("accent_text"))
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)

        # Estado vacío: antes de analizar, o cuando el filtro no tiene nada que mostrar.
        if shown:
            self.stack.setCurrentWidget(self.table)
        else:
            if analyzed == 0 and mode != FILTER_DONE:
                self._set_empty(
                    "Aún no se analizó ninguna canción",
                    "Pulsa «Analizar las no analizadas» para medir el volumen de tu biblioteca. "
                    "Analizar solo lee los archivos: no cambia nada.",
                )
            elif mode == FILTER_DONE:
                self._set_empty("Todavía no se ajustó ninguna canción", "Las canciones que subas aparecerán aquí para poder revertirlas.")
            else:
                self._set_empty("Ninguna canción necesita ajuste", "Todas las analizadas tienen un volumen parecido al resto de tu biblioteca.")
            self.stack.setCurrentWidget(self.empty)

        total = len(rows)
        self.btn_analyze_new.setText(f"Analizar las no analizadas ({pending})")
        self.btn_analyze_all.setText(f"Volver a analizar todas ({total})")
        # Un solo botón ámbar: analizar mientras falte, después subir el volumen.
        set_primary(self.btn_analyze_new, pending > 0)
        set_primary(self.btn_apply, pending == 0)
        self.summary.setText(
            f"Analizadas: <b>{analyzed}</b> de {total} · referencia de tu biblioteca: <b>{self._reference:.1f} LUFS</b><br>"
            f"Muy bajas: <b>{len(need)}</b> · se pueden subir sin distorsionar: <b>{len(fixable)}</b> · "
            f"ya ajustadas: <b>{len(done)}</b>"
        )
        self._update_buttons()

    def _checked_jobs(self) -> list[tuple[Track, int]]:
        jobs = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_USE)
            track, steps = item.data(_TRACK)
            if steps > 0 and item.checkState() == Qt.CheckState.Checked:
                jobs.append((track, steps))
        return jobs

    def _update_buttons(self, *_args) -> None:
        busy = self.runner.busy
        jobs = self._checked_jobs()
        self.btn_apply.setText(f"Subir volumen de las marcadas ({len(jobs)})")
        self.btn_apply.setEnabled(bool(jobs) and not busy)
        for button in (self.btn_analyze_new, self.btn_analyze_all, self.btn_revert, self.filter):
            button.setEnabled(not busy)

    # ------------------------------------------------------------------ aplicar / revertir

    def _apply(self) -> None:
        jobs = self._checked_jobs()
        if not jobs:
            return
        choice = ask(
            self,
            "Subir volumen",
            f"¿Subir el volumen de {plural(len(jobs), 'canción', 'canciones')} de forma permanente?",
            [("Subir volumen", QMessageBox.ButtonRole.AcceptRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Question,
            "Se modifican los archivos MP3 sin recomprimirlos (sin pérdida de calidad) y sin superar "
            f"{CEILING_DBTP:.0f} dBTP, así que no se distorsionan. El cambio se oye en cualquier reproductor. "
            "Se puede revertir desde esta misma ventana.",
        )
        if choice == 0:
            self._run_adjust(jobs)

    def _revert_selected(self) -> None:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        jobs = []
        for row in rows:
            track, _steps = self.table.item(row, COL_USE).data(_TRACK)
            if track.norm_gain_db > 0 and can_adjust(track.path):
                jobs.append((track, -round(track.norm_gain_db / STEP_DB)))
        if not jobs:
            QMessageBox.information(self, "Revertir", "Selecciona en la lista canciones ya ajustadas (filtro «ya ajustadas»).")
            return
        if ask(
            self, "Revertir ajuste",
            f"¿Devolver {plural(len(jobs), 'canción', 'canciones')} a su volumen original?",
            [("Revertir", QMessageBox.ButtonRole.AcceptRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
        ) == 0:
            self._run_adjust(jobs)

    def _run_adjust(self, jobs: list[tuple[Track, int]]) -> None:
        if not self._ops.begin_volume_adjust({t.id for t, _ in jobs}):
            return
        self._adjusted: list[tuple[Track, int]] = []
        self._adjust_errors: list[str] = []
        self._adjust_by_id = {t.id: t for t, _ in jobs}
        worker = AdjustWorker(jobs)
        worker.adjusted.connect(self._on_adjusted)  # método con @Slot: se ejecuta en el hilo principal
        self.runner.start(worker, len(jobs), "Ajustando volumen…", self._on_adjust_finished, label="Ajustando", modifies_files=True)

    @Slot(int, int, int, str)
    def _on_adjusted(self, track_id: int, steps: int, total_steps: int, error: str) -> None:
        """Un archivo terminado: se anota en el acto en la biblioteca (hilo principal)."""
        track = self._adjust_by_id[track_id]
        if steps:
            self._adjusted.append((track, steps))
            self._ops.record_volume(track, steps, total_steps)
        if error:
            self._adjust_errors.append(f"• {track.title}: {error}")

    def _on_adjust_finished(self) -> None:
        self._ops.changed()
        self._refresh_table()
        up = sum(1 for _t, s in self._adjusted if s > 0)
        down = sum(1 for _t, s in self._adjusted if s < 0)
        text = []
        if up:
            text.append(f"Se subió el volumen de {plural(up, 'canción', 'canciones')}.")
        if down:
            text.append(f"Se {'revirtió' if down == 1 else 'revirtieron'} {plural(down, 'canción', 'canciones')}.")
        if self._adjust_errors:
            text.append(f"No se pudieron ajustar {len(self._adjust_errors)}:\n" + "\n".join(self._adjust_errors[:15]))
        self.status.setText(" ".join(t.split("\n")[0] for t in text))
        QMessageBox.information(self, "Volumen", "\n\n".join(text) or "No se cambió nada.")

    def reject(self) -> None:
        if self.runner.request_close(wait_ms=20000):
            self._flush()
            super().reject()
