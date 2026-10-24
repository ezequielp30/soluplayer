"""Diálogo «Analizar y ajustar volumen»: mide todas las canciones y sube, de forma permanente y sin
pérdida, solo las que están muy bajas (MP3).

Ventana compacta (como el escaneo de ReplayGain de foobar2000): pocas columnas, un estado corto por
canción con el detalle al pasar el mouse, y el resultado de cada operación en una franja (sin avisos
emergentes). Al terminar, la lista se actualiza: las canciones ya ajustadas dejan de aparecer como pendientes.
"""

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
from .dialogs import ResultBanner, StatusLabel, ask, empty_state, set_primary, tidy_table, tool_intro
from .worker_runner import WorkerRunner

COL_USE, COL_SONG, COL_LUFS, COL_GAIN, COL_DIAG = range(5)
_TRACK = Qt.ItemDataRole.UserRole
FILTER_NEED, FILTER_DONE, FILTER_ALL = "need", "done", "all"

_DETAILS = (
    "Mide la sonoridad de cada canción con el estándar EBU R128 (LUFS) y su pico real (dBTP).\n"
    "Solo se proponen las canciones claramente más bajas que el resto de tu biblioteca, y la subida se limita "
    f"para que el pico nunca pase de {CEILING_DBTP:.0f} dBTP: no se distorsiona.\n"
    "En los MP3 el ajuste es permanente y sin pérdida (no se recomprime, pasos de 1,5 dB), se oye en cualquier "
    "reproductor y se puede revertir. WMA, M4A y otros formatos se indican pero no se tocan.\n"
    "Analizar solo lee los archivos."
)


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
        self.resize(780, 500)
        self._ops = ops
        self._tracks_provider = tracks_provider
        self._pending_save: list[tuple[int, float | None, float | None]] = []

        layout = QVBoxLayout(self)
        layout.addWidget(tool_intro("Sube, sin pérdida, solo las canciones claramente más bajas que el resto.", _DETAILS))
        self.banner = ResultBanner()
        layout.addWidget(self.banner)

        row = QHBoxLayout()
        self.btn_analyze_new = QPushButton()
        self.btn_analyze_new.clicked.connect(lambda: self._start_analysis(only_new=True))
        self.btn_analyze_all = QPushButton("Reanalizar todas")
        self.btn_analyze_all.setToolTip("Vuelve a medir todas las canciones (solo lee los archivos)")
        self.btn_analyze_all.clicked.connect(lambda: self._start_analysis(only_new=False))
        self.filter = QComboBox()
        self.filter.addItem("Necesitan ajuste", FILTER_NEED)
        self.filter.addItem("Ya ajustadas", FILTER_DONE)
        self.filter.addItem("Todas", FILTER_ALL)
        self.filter.setCurrentIndex(max(0, self.filter.findData(initial_filter)))
        self.filter.currentIndexChanged.connect(self._refresh_table)
        row.addWidget(self.btn_analyze_new)
        row.addWidget(self.btn_analyze_all)
        row.addStretch(1)
        row.addWidget(QLabel("Mostrar:"))
        row.addWidget(self.filter)
        layout.addLayout(row)

        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(8)
        self.status = StatusLabel()
        self.btn_stop = QPushButton("Detener")
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.status, 3)
        progress_row.addWidget(self.btn_stop)
        layout.addLayout(progress_row)
        self.runner = WorkerRunner(self, self.progress, self.status, self.btn_stop)
        self.runner.busy_changed.connect(self._update_buttons)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Canción", "Sonoridad", "Subida", "Estado"])
        tidy_table(self.table)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in ((COL_USE, 30), (COL_LUFS, 95), (COL_GAIN, 70), (COL_DIAG, 170)):
            header.resizeSection(col, width)
        header.setSectionResizeMode(COL_SONG, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._update_buttons)
        self.empty, self._set_empty = empty_state()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        layout.addWidget(self.stack, 1)

        bottom = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setObjectName("DialogNote")
        bottom.addWidget(self.summary, 1)
        self.btn_revert = QPushButton("Revertir…")
        self.btn_revert.setToolTip("Devuelve las canciones seleccionadas (ya ajustadas) a su volumen original")
        self.btn_revert.clicked.connect(self._revert_selected)
        self.btn_apply = QPushButton("Subir volumen")
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
            self.banner.show_result("No hay canciones pendientes de analizar.")
            return
        self.banner.clear()
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
        self.status.setText("")
        self._refresh_table()
        done = getattr(self, "_measured_count", 0)
        total = getattr(self, "_analysis_total", done)
        self.banner.show_result(
            f"Análisis detenido: se midieron {done} de {total}." if cancelled
            else f"Análisis terminado: {plural(done, 'canción medida', 'canciones medidas')}.",
            ok=not cancelled,
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

    @staticmethod
    def _state(track: Track, decision, steps: int) -> tuple[str, str]:
        """Estado corto para la lista y explicación completa para el tooltip."""
        ext = os.path.splitext(track.path)[1].lstrip(".").upper()
        done = f" Ya se subió +{track.norm_gain_db:.1f} dB." if track.norm_gain_db > 0 else ""
        if decision is None:
            return "Sin analizar", "Todavía no se midió." + done
        if decision.status == "bajo" and steps == 0 and decision.gain_db > 0:
            if not can_adjust(track.path):
                return (f"No se puede ajustar ({ext})",
                        f"Necesita +{decision.gain_db:.1f} dB, pero el formato {ext} no se puede ajustar sin recomprimir.")
            return "Casi bien", f"Necesita +{decision.gain_db:.1f} dB: menos de un paso de {STEP_DB} dB."
        if steps:
            detail = f"Está {decision.wanted_db:.1f} dB por debajo de la referencia: se sube +{steps * STEP_DB:.1f} dB"
            if decision.limited_by_peak:
                detail += "; no más, para que los picos no distorsionen."
            elif decision.wanted_db > MAX_GAIN - track.norm_gain_db:
                detail += f"; no más: el tope por canción es +{MAX_GAIN:.0f} dB en total."
            else:
                detail += f" (pasos de {STEP_DB} dB, sin pérdida)."
            return "Muy baja", detail + done
        if track.norm_gain_db > 0:
            return f"Ajustada +{track.norm_gain_db:.1f} dB", decision.reason + done
        short = {"alto": "Fuerte", "sin datos": "No se pudo medir"}.get(decision.status)
        if short is None:
            short = "No se puede subir" if decision.status == "bajo" else "Adecuado"
        return short, decision.reason

    def _refresh_table(self) -> None:
        mode = self.filter.currentData()
        rows = self._rows()
        analyzed = sum(1 for t, d, _ in rows if d is not None)
        pending = sum(1 for t, d, _ in rows if d is None and t.available)
        # «Necesitan ajuste»: las bajas, salvo las ya subidas que no admiten más (ya se resolvieron).
        need = [r for r in rows if r[1] is not None and r[1].status == "bajo" and not (r[0].norm_gain_db > 0 and r[2] == 0)]
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
            lufs = f"{track.loudness_lufs:.1f} LUFS" if track.loudness_lufs is not None else "—"
            state, detail = self._state(track, decision, steps)
            peak = f"\nPico real: {track.true_peak_db:.1f} dBTP" if track.true_peak_db is not None else ""
            gain = f"+{steps * STEP_DB:.1f} dB" if steps else ""
            for col, value in enumerate([use, track.title + " — " + track.artist, lufs, gain, state]):
                item = value if isinstance(value, QTableWidgetItem) else QTableWidgetItem(value)
                if col == COL_SONG:
                    item.setToolTip(track.path)
                if col in (COL_LUFS, COL_DIAG):
                    item.setToolTip(detail + peak)
                if col in (COL_LUFS, COL_GAIN):
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
                if col == COL_GAIN and steps:
                    item.setForeground(theme.qcolor("accent_text"))
                if col == COL_DIAG and not steps:
                    item.setForeground(theme.qcolor("muted"))
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)

        # Estado vacío: antes de analizar, o cuando el filtro no tiene nada que mostrar.
        if shown:
            self.stack.setCurrentWidget(self.table)
        else:
            if analyzed == 0 and mode != FILTER_DONE:
                self._set_empty("Aún no se analizó ninguna canción", "Pulsa «Analizar» para medir el volumen de tu biblioteca.")
            elif mode == FILTER_DONE:
                self._set_empty("Ninguna canción ajustada", "Las que subas aparecerán aquí para poder revertirlas.")
            else:
                self._set_empty("Ninguna canción necesita ajuste", "Todas tienen un volumen parecido al resto de tu biblioteca.")
            self.stack.setCurrentWidget(self.empty)

        total = len(rows)
        self.btn_analyze_new.setText(f"Analizar ({pending})" if pending else "Analizar")
        self.btn_analyze_new.setToolTip(f"Mide las {pending} canciones que aún no se analizaron")
        # Un solo botón ámbar: analizar mientras falte, después subir el volumen.
        set_primary(self.btn_analyze_new, pending > 0)
        set_primary(self.btn_apply, pending == 0)
        self.summary.setText(
            f"Analizadas: {analyzed} de {total} · referencia {self._reference:.1f} LUFS · "
            f"muy bajas: {len(need)} · ajustadas: {len(done)}"
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
        self.btn_apply.setText(f"Subir volumen ({len(jobs)})" if jobs else "Subir volumen")
        self.btn_apply.setEnabled(bool(jobs) and not busy)
        for button in (self.btn_analyze_new, self.btn_analyze_all, self.filter):
            button.setEnabled(not busy)
        self.btn_revert.setEnabled(not busy and self.filter.currentData() != FILTER_NEED)
        self.btn_revert.setVisible(self.filter.currentData() != FILTER_NEED)

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
            "Sin recomprimir ni distorsionar. Se puede revertir desde esta ventana (Mostrar: Ya ajustadas).",
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
            self.banner.show_result("Selecciona en la lista canciones ya ajustadas para revertirlas.", ok=False)
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
        self.banner.clear()
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
            self._adjust_errors.append(f"{track.title}: {error}")

    def _on_adjust_finished(self) -> None:
        self._ops.changed()
        self.status.setText("")
        self._refresh_table()  # operación terminada: las ajustadas dejan de figurar como pendientes
        up = sum(1 for _t, s in self._adjusted if s > 0)
        down = sum(1 for _t, s in self._adjusted if s < 0)
        text = []
        if up:
            text.append(f"Se subió el volumen de {plural(up, 'canción', 'canciones')}.")
        if down:
            text.append(f"Se {'revirtió' if down == 1 else 'revirtieron'} {plural(down, 'canción', 'canciones')}.")
        if self._adjust_errors:
            text.append(f"No se pudieron ajustar {len(self._adjust_errors)} (pasa el mouse por aquí).")
            self.banner.setToolTip("\n".join(self._adjust_errors[:15]))
        else:
            self.banner.setToolTip("")
        self.banner.show_result(" ".join(text) or "No se cambió nada.", ok=not self._adjust_errors)

    def reject(self) -> None:
        if self.runner.request_close(wait_ms=20000):
            self._flush()
            super().reject()
