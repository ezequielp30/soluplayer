"""Diálogo «Analizar y ajustar volumen»: mide todas las canciones y sube, de forma permanente y sin
pérdida, solo las que están muy bajas (MP3).

Ventana compacta (como el escaneo de ReplayGain de foobar2000): pocas columnas, un estado corto por
canción con el detalle al pasar el mouse, y el resultado de cada operación en una franja (sin avisos
emergentes). Al terminar, la lista se actualiza: las canciones ya ajustadas dejan de aparecer como pendientes.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Callable

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
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
from ..loudness import (
    CEILING_DBTP, MAX_GAIN, SET_ASIDE_FOLDER, TARGET_LUFS, decide, measurement_to_store, plausible, spread,
    why_not_equalizable,
)
from ..loudness_job import REVERT, AdjustWorker, AnalyzeWorker, can_adjust
from ..models import Track
from ..mp3gain import STEP_DB
from ..utils import plural
from . import theme
from .dialogs import ResultBanner, StatusLabel, ask, empty_state, set_primary, tidy_table, tool_intro
from .worker_runner import StopQuestion
from .worker_runner import WorkerRunner

COL_USE, COL_SONG, COL_LUFS, COL_GAIN, COL_DIAG = range(5)
_TRACK = Qt.ItemDataRole.UserRole
FILTER_NEED, FILTER_DONE, FILTER_ALL = "need", "done", "all"

_DETAILS = (
    "Mide la sonoridad de cada canción con el estándar EBU R128 (LUFS) y su pico real (dBTP).\n"
    f"Iguala cada canción a {TARGET_LUFS:.0f} LUFS (escucha general): sube las bajas y baja las fuertes, de forma lineal (toda "
    f"la canción por igual, sin compresión). Al subir, el pico nunca pasa de {CEILING_DBTP:.0f} dBTP: no se distorsiona.\n"
    "En los MP3 el ajuste es permanente y sin pérdida (no se recomprime, pasos de 1,5 dB), se oye en cualquier "
    "reproductor y se puede revertir. WMA, M4A y otros formatos se indican pero no se tocan.\n"
    "Para igualar TODAS las canciones analizadas (también FLAC, M4A, WAV…) sin modificar ningún archivo: "
    "Reproducción → Igualar volumen al reproducir (subidas limitadas para no pasar de "
    f"{CEILING_DBTP:.0f} dBTP, sin compresión).\n"
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
        self.btn_apply = QPushButton("Igualar volumen")
        self.btn_apply.clicked.connect(self._apply)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.reject)
        self.btn_aside = QPushButton("Apartar…")
        self.btn_aside.setToolTip(f"Mueve las que no se pueden igualar a «{SET_ASIDE_FOLDER}», en la carpeta principal de tu música\n"
                                    "(antes de mover puedes elegir otra carpeta destino)")
        self.btn_aside.clicked.connect(self._set_aside)
        bottom.addWidget(self.btn_aside)
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
        self.runner.start(worker, len(tracks), "Analizando…", self._on_analysis_finished, label="Analizando",
                          stop_question=StopQuestion("el análisis de volumen", "Seguir analizando", "Detener el análisis",
                                                     "Lo medido hasta ahora se conserva; las demás se pueden analizar después."))

    @Slot(int, object, object, str, int)
    def _on_measured(self, track_id: int, lufs, peak, error: str, annotated_steps: int) -> None:
        track = next((t for t in self._tracks() if t.id == track_id), None)
        if lufs is None and track is not None:
            lufs = measurement_to_store(None, track.path)  # dañada o sin audio: marcada; no está: pendiente
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
        reference = TARGET_LUFS  # fijo: no depende de qué canciones haya ni de las ya ajustadas
        self._reference = reference
        rows = []
        for track in tracks:
            decision = decide(track.loudness_lufs, track.true_peak_db, reference, track.norm_gain_db) if track.loudness_lufs is not None else None
            steps = round(decision.gain_db / STEP_DB) if decision and can_adjust(track.path) and track.available else 0
            rows.append((track, decision, steps))
        return rows

    @staticmethod
    def _state(track: Track, decision, steps: int) -> tuple[str, str]:
        """Estado corto para la lista y explicación completa para el tooltip."""
        ext = os.path.splitext(track.path)[1].lstrip(".").upper()
        done = f" Ya ajustada {track.norm_gain_db:+.1f} dB." if track.norm_gain_db != 0 else ""
        if decision is None:
            return "Sin analizar", "Todavía no se midió." + done
        if steps == 0 and decision.gain_db != 0:
            if not track.available:
                return "No disponible", f"Necesita {decision.gain_db:+.1f} dB, pero el archivo no está en el disco."
            if not can_adjust(track.path):
                return (f"No se puede ajustar ({ext})",
                        f"Necesita {decision.gain_db:+.1f} dB, pero el formato {ext} no se puede ajustar sin recomprimir.")
        if steps < 0:
            return "Muy fuerte", decision.reason + done
        if steps:
            detail = f"Está {decision.wanted_db:.1f} dB por debajo de la referencia: se sube +{steps * STEP_DB:.1f} dB"
            if decision.limited_by_peak:
                detail += "; no más, para que los picos no distorsionen."
            elif decision.wanted_db > MAX_GAIN - max(0.0, track.norm_gain_db):
                detail += f"; no más: el tope por canción es +{MAX_GAIN:.0f} dB en total."
            else:
                detail += f" (pasos de {STEP_DB} dB, sin pérdida)."
            return "Muy baja", detail + done
        if track.norm_gain_db != 0:
            return f"Ajustada {track.norm_gain_db:+.1f} dB", decision.reason + done
        short = {"alto": "No se puede bajar", "sin datos": "No se pudo medir"}.get(decision.status)
        if short is None:
            short = "No se puede subir" if decision.status == "bajo" else "Adecuado"
        return short, decision.reason

    def _refresh_table(self) -> None:
        mode = self.filter.currentData()
        rows = self._rows()
        analyzed = sum(1 for t, d, _ in rows if d is not None)
        pending = sum(1 for t, d, _ in rows if d is None and t.available)
        # «Necesitan ajuste»: las que se pueden acercar a la referencia (bajas o fuertes), y las que lo
        # necesitan pero no se pueden ajustar (otro formato, picos), para que se vea por qué.
        need = [r for r in rows if r[1] is not None and r[1].status in ("bajo", "alto")
                and (r[2] != 0 or (r[1].wanted_db and r[0].norm_gain_db == 0 and abs(r[1].wanted_db) >= 3))]
        done = [r for r in rows if r[0].norm_gain_db != 0]
        shown = {FILTER_NEED: need, FILTER_DONE: done, FILTER_ALL: rows}[mode]
        self.table.blockSignals(True)
        self.table.setRowCount(len(shown))
        for row, (track, decision, steps) in enumerate(shown):
            use = QTableWidgetItem()
            if steps:
                use.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                use.setCheckState(Qt.CheckState.Checked)
            else:
                use.setFlags(Qt.ItemFlag.ItemIsEnabled)
            use.setData(_TRACK, (track, steps))
            if track.loudness_lufs is None:
                lufs = "—"
            elif not plausible(track.loudness_lufs, track.true_peak_db):
                lufs = "no se pudo medir"
            else:
                lufs = f"{track.loudness_lufs:.1f} LUFS"
            state, detail = self._state(track, decision, steps)
            peak = f"\nPico real: {track.true_peak_db:.1f} dBTP" if track.true_peak_db is not None else ""
            gain = f"{steps * STEP_DB:+.1f} dB" if steps else ""
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
            f"Analizadas: {analyzed} de {total} · objetivo {self._reference:.0f} LUFS · "
            f"por igualar: {sum(1 for r in need if r[2])} · ajustadas: {len(done)}"
        )
        report = spread([t.loudness_lufs for t, _d, _s in rows if can_adjust(t.path)], self._reference)
        if report.total:
            self.summary.setToolTip(
                f"Parejas (a ±{STEP_DB / 2:.2f} LU del objetivo): {report.inside} de {report.total} MP3 analizados.\n"
                f"Más bajas: {report.below} (algunas no pueden subir más sin distorsionar).\n"
                f"Más fuertes: {report.above}."
            )
        self._update_buttons()

    def _checked_jobs(self) -> list[tuple[Track, int]]:
        jobs = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_USE)
            track, steps = item.data(_TRACK)
            if steps and item.checkState() == Qt.CheckState.Checked:
                jobs.append((track, steps))
        return jobs

    def _unequalizable(self) -> list[tuple[Track, str]]:
        return [(t, reason) for t in self._tracks() if (reason := why_not_equalizable(t, can_adjust(t.path)))]

    def _set_aside(self) -> None:
        items = self._unequalizable()
        if not items:
            self.banner.show_result("No hay canciones que apartar: todas se pueden igualar (o falta analizarlas).")
            return
        destination = self._ops.set_aside_folder(self._tracks())
        if not destination:
            self.banner.show_result("No hay una carpeta principal clara para tu música: no se apartó nada.", ok=False)
            return
        kinds = Counter(reason.split(":")[0].split(" (")[0] for _t, reason in items)
        detail = "\n".join(f"  · {name}: {count}" for name, count in kinds.items())
        while True:  # carpeta destino: la propuesta, o la que se elija
            choice = ask(
                self, "Apartar canciones",
                f"¿Mover {plural(len(items), 'canción', 'canciones')} que no se pueden igualar a:\n{destination}?",
                [("Apartar", QMessageBox.ButtonRole.DestructiveRole),
                 ("Elegir otra carpeta…", QMessageBox.ButtonRole.ActionRole),
                 ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
                QMessageBox.Icon.Question,
                f"{detail}\n\nSiguen en tu biblioteca y en tus playlists, con un LEEME.txt que explica cada una. "
                "Se puede deshacer desde el Historial.",
            )
            if choice == 1:
                parent = QFileDialog.getExistingDirectory(self, "¿Dónde crear la carpeta de las apartadas?",
                                                          os.path.dirname(destination))
                if parent:
                    destination = os.path.join(os.path.normpath(parent), SET_ASIDE_FOLDER)
                continue
            if choice != 0:
                return
            break
        try:
            outcome = self._ops.set_aside(items, self._tracks(), destination)
        except Exception as exc:  # carpeta sin permiso, disco lleno…
            self.banner.show_result(f"No se pudieron apartar: {exc}", ok=False)
            return
        self._ops.changed()
        self._refresh_table()
        self.banner.setToolTip("")
        if not outcome.moved and not outcome.failed:
            self.banner.show_result("No se movió nada (operación cancelada).", ok=False)
            return
        text = f"Se apartaron {plural(len(outcome.moved), 'canción', 'canciones')} en {outcome.folder}."
        if outcome.failed:
            text += f" No se movieron {len(outcome.failed)} (pasa el mouse por aquí)."
            self.banner.setToolTip("\n".join(f"{os.path.basename(p)}: {r}" for p, r in outcome.failed[:15]))
        self.banner.show_result(text, ok=not outcome.failed)

    def _update_buttons(self, *_args) -> None:
        busy = self.runner.busy
        aside = len(self._unequalizable())
        self.btn_aside.setText(f"Apartar ({aside})…" if aside else "Apartar…")
        self.btn_aside.setEnabled(bool(aside) and not busy)
        jobs = self._checked_jobs()
        self.btn_apply.setText(f"Igualar volumen ({len(jobs)})" if jobs else "Igualar volumen")
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
            "Igualar volumen",
            f"¿Igualar el volumen de {plural(len(jobs), 'canción', 'canciones')} dentro de los archivos?",
            [("Igualar volumen", QMessageBox.ButtonRole.AcceptRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Question,
            "Queda guardado en los MP3: suenan parejas en cualquier reproductor (celular, auto, otros programas). "
            "Sin recomprimir ni distorsionar. Se puede revertir desde esta ventana (Mostrar: Ya ajustadas).",
        )
        if choice == 0:
            self._run_adjust(jobs)

    def _revert_selected(self) -> None:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        jobs = []
        for row in rows:
            track, _steps = self.table.item(row, COL_USE).data(_TRACK)
            if track.norm_gain_db != 0 and can_adjust(track.path):
                jobs.append((track, REVERT))
        if not jobs:
            self.banner.show_result("Selecciona en la lista canciones ya ajustadas para revertirlas.", ok=False)
            return
        if ask(
            self, "Revertir ajuste",
            f"¿Devolver {plural(len(jobs), 'canción', 'canciones')} a su volumen original?",
            [("Revertir", QMessageBox.ButtonRole.AcceptRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
        ) == 0:
            self._run_adjust(jobs)

    def _run_adjust(self, jobs: list[tuple[Track, int | None]]) -> None:
        if not self._ops.begin_volume_adjust({t.id for t, _ in jobs}):
            return
        self.banner.clear()
        self._adjusted: list[tuple[Track, int, int]] = []
        self._adjust_errors: list[str] = []
        self._adjust_by_id = {t.id: t for t, _ in jobs}
        worker = AdjustWorker(jobs)
        worker.adjusted.connect(self._on_adjusted)  # método con @Slot: se ejecuta en el hilo principal
        self.runner.start(worker, len(jobs), "Ajustando volumen…", self._on_adjust_finished, label="Ajustando", modifies_files=True,
                          stop_question=StopQuestion("el ajuste de volumen", "Seguir ajustando", "Detener el ajuste",
                                                     "Las canciones ya ajustadas quedan así (se pueden revertir)."))

    @Slot(int, int, int, str)
    def _on_adjusted(self, track_id: int, steps: int, total_steps: int, error: str) -> None:
        """Un archivo terminado: se anota en el acto en la biblioteca (hilo principal)."""
        track = self._adjust_by_id[track_id]
        if steps:
            self._adjusted.append((track, steps, total_steps))
            self._ops.record_volume(track, steps, total_steps)
        if error:
            self._adjust_errors.append(f"{track.title}: {error}")

    def _on_adjust_finished(self) -> None:
        self._ops.changed()
        self.status.setText("")
        self._refresh_table()  # operación terminada: las ajustadas dejan de figurar como pendientes
        reverted = sum(1 for _t, _s, total in self._adjusted if total == 0)
        up = sum(1 for _t, s, total in self._adjusted if s > 0 and total != 0)
        down = sum(1 for _t, s, total in self._adjusted if s < 0 and total != 0)
        text = []
        if up:
            text.append(f"Se subió el volumen de {plural(up, 'canción', 'canciones')}.")
        if down:
            text.append(f"Se bajó el volumen de {plural(down, 'canción', 'canciones')}.")
        if reverted:
            text.append(f"{plural(reverted, 'canción volvió', 'canciones volvieron')} a su volumen original.")
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
