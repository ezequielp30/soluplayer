"""Herramientas → Título y quién la canta: el organizador de MP3. Analizar nunca modifica nada; cambiar exige pulsar un botón."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import acoustid_lookup, file_locator, fingerprint
from ..file_operations import FileOperations
from ..normalizer import SongJob
from ..organizer import DECISION_AUTO, DECISION_DONE, DECISION_OFFLINE, DECISION_REVIEW, Confidence
from ..organizer_db import STATUS_DAMAGED, OrganizerDb
from ..organizer_job import (
    AnalyzeWorker,
    IdentifyWorker,
    MoveToPendingWorker,
    NormalizeWorker,
    RestoreWorker,
    ResolvePendingWorker,
)
from ..preferences import Preferences
from ..utils import plural
from .acoustid_dialog import AcoustIdKeyDialog
from .dialogs import ask, tool_intro
from .worker_runner import StopQuestion, WorkerRunner

log = logging.getLogger(__name__)

_DETAILS = (
    "Reconoce cada canción por su sonido con AcoustID y la deja como «TITULO - ARTISTA.mp3», con solo el título y el "
    "artista dentro del archivo.\n"
    "Analizar no cambia nada. Antes de cambiar una canción se hace una copia completa y se comprueba que es idéntica. El "
    "audio no se toca, y todo se puede restaurar en la pestaña Historial.\n"
    "Las dudosas van a PENDIENTES_REVISION sin cambios, para reintentarlas o corregirlas."
)
_STATE_TEXT = {DECISION_AUTO: "Segura", DECISION_REVIEW: "Dudosa", DECISION_OFFLINE: "Sin huella", DECISION_DONE: "Normalizada", "": "Sin identificar"}
_FILTERS = ("Todas", "Seguras", "Dudosas", "Sin huella", "Dañadas", "Normalizadas")
COL_NOW, COL_TITLE, COL_ARTIST, COL_VERSION, COL_SCORE, COL_STATE, COL_REASON = range(7)
_COLUMNS = ("Ahora", "Título", "Artista", "Versión", "Confianza", "Estado", "Motivo")


@dataclass
class ResultRow:
    file_id: int
    path: str
    title: str
    artist: str
    version: str
    score: float | None
    decision: str
    reason: str
    damaged: bool
    checked: bool = False


class ResultsModel(QAbstractTableModel):
    """Modelo y no QTableWidget: con miles de canciones solo se dibuja lo que se ve."""

    def __init__(self, on_change: Callable[[], None], parent=None) -> None:
        super().__init__(parent)
        self._all: list[ResultRow] = []
        self._rows: list[ResultRow] = []
        self._filter = 0
        self._on_change = on_change

    def load(self, rows: list[ResultRow]) -> None:
        self._all = rows
        self.set_filter(self._filter)

    def set_filter(self, index: int) -> None:
        self.beginResetModel()
        self._filter = index
        wanted = {1: DECISION_AUTO, 2: DECISION_REVIEW, 3: DECISION_OFFLINE, 5: DECISION_DONE}.get(index)
        if index == 4:
            self._rows = [r for r in self._all if r.damaged]
        elif wanted:
            self._rows = [r for r in self._all if r.decision == wanted and not r.damaged]
        else:
            self._rows = list(self._all)
        self.endResetModel()
        self._on_change()

    def rows(self) -> list[ResultRow]:
        return self._all

    def visible(self) -> list[ResultRow]:
        return self._rows

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802 (nombre de Qt)
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section]
        return None

    def flags(self, index):
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        row = self._rows[index.row()]
        if index.column() == COL_NOW and not row.damaged:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        if index.column() in (COL_TITLE, COL_ARTIST) and not row.damaged:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        row = self._rows[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.CheckStateRole and column == COL_NOW and not row.damaged:
            return Qt.CheckState.Checked if row.checked else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.ToolTipRole:
            return row.reason if column == COL_REASON else row.path
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return None
        if column == COL_NOW:
            return os.path.basename(row.path)
        if column == COL_TITLE:
            return row.title
        if column == COL_ARTIST:
            return row.artist
        if column == COL_VERSION:
            return row.version
        if column == COL_SCORE:
            return f"{row.score:.0%}" if row.score else ""
        if column == COL_STATE:
            return "Dañada" if row.damaged else _STATE_TEXT.get(row.decision, "")
        return row.reason

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):  # noqa: N802
        row = self._rows[index.row()]
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == COL_NOW:
            row.checked = Qt.CheckState(value) == Qt.CheckState.Checked
        elif role == Qt.ItemDataRole.EditRole and index.column() == COL_TITLE:
            row.title = str(value).strip()
        elif role == Qt.ItemDataRole.EditRole and index.column() == COL_ARTIST:
            row.artist = str(value).strip()
        else:
            return False
        self.dataChanged.emit(index, index)
        self._on_change()
        return True

    def check_visible(self, checked: bool) -> None:
        for row in self._rows:
            if not row.damaged:
                row.checked = checked
        if self._rows:
            self.dataChanged.emit(self.index(0, COL_NOW), self.index(len(self._rows) - 1, COL_NOW))
        self._on_change()


class OrganizerSettingsDialog(QDialog):
    """Clave, niveles de confianza y carpeta de los respaldos."""

    def __init__(self, prefs: Preferences, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._prefs = prefs
        self.setWindowTitle("Ajustes del organizador")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        confidence = prefs.confidence
        self.auto_score = self._percent(confidence.auto_score)
        self.strong_score = self._percent(confidence.strong_score)
        self.max_diff = QDoubleSpinBox()
        self.max_diff.setRange(0, 60)
        self.max_diff.setSuffix(" s")
        self.max_diff.setValue(confidence.max_duration_diff_s)
        form.addRow("Parecido mínimo de la huella:", self.auto_score)
        form.addRow("Mínimo si contradice el nombre actual:", self.strong_score)
        form.addRow("Diferencia máxima de duración:", self.max_diff)
        self.backup = QLineEdit(prefs.organizer_backup_folder)
        self.backup.setPlaceholderText("RESPALDOS_MP3 en la raíz del disco de cada canción")
        choose = QPushButton("Elegir…")
        choose.clicked.connect(self._choose_backup)
        row = QHBoxLayout()
        row.addWidget(self.backup, 1)
        row.addWidget(choose)
        form.addRow("Carpeta de los respaldos:", row)
        layout.addLayout(form)
        note = QLabel("Lo ideal es que los respaldos estén en otro disco: en el mismo no protegen de una avería del disco.")
        note.setObjectName("DialogNote")
        note.setWordWrap(True)
        layout.addWidget(note)
        key = QPushButton("Clave de AcoustID…")
        key.clicked.connect(lambda: AcoustIdKeyDialog(self._prefs, self).exec())
        layout.addWidget(key, 0, Qt.AlignmentFlag.AlignLeft)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _percent(value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(50, 100)
        box.setDecimals(0)
        box.setSuffix(" %")
        box.setValue(value * 100)
        return box

    def _choose_backup(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de los respaldos", self.backup.text())
        if folder:
            self.backup.setText(os.path.normpath(folder))

    def _save(self) -> None:
        self._prefs.confidence = Confidence(self.auto_score.value() / 100, self.strong_score.value() / 100, self.max_diff.value())
        self._prefs.organizer_backup_folder = self.backup.text().strip()
        self.accept()


class OrganizerDialog(QDialog):
    def __init__(
        self, ops: FileOperations, prefs: Preferences, roots: list[str], parent: QWidget | None = None,
        open_previous_tool: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._ops = ops
        self._prefs = prefs
        self._db = OrganizerDb()
        self._started = 0.0
        self._send_doubts_after = False
        self._counts = (0, 0)
        self._phase_text = ""
        self.setWindowTitle("Título y quién la canta")
        self.resize(1140, 720)

        layout = QVBoxLayout(self)
        layout.addWidget(tool_intro("Reconoce tus canciones por su sonido y las deja como «TITULO - ARTISTA.mp3».", _DETAILS))
        layout.addLayout(self._build_roots(roots))

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_results(), "Resultados")
        self.tabs.addTab(self._build_pending(), "Pendientes")
        self.tabs.addTab(self._build_history(), "Historial")
        self.errors = QPlainTextEdit()
        self.errors.setReadOnly(True)
        self.tabs.addTab(self.errors, "Errores")
        layout.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(8)
        self.status = QLabel("")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.btn_stop = QPushButton("Detener")
        row.addWidget(self.progress, 1)
        row.addWidget(self.status, 2)
        row.addWidget(self.btn_stop)
        layout.addLayout(row)
        self.runner = WorkerRunner(self, self.progress, QLabel(self), self.btn_stop)
        self.runner.busy_changed.connect(self._update_buttons)
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._show_progress)

        bottom = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setObjectName("DialogNote")
        bottom.addWidget(self.summary, 1)
        self.btn_previous = QPushButton("Herramienta anterior…")
        self.btn_previous.setToolTip("La vista sin huella digital de versiones anteriores")
        self.btn_previous.setVisible(open_previous_tool is not None)
        if open_previous_tool is not None:
            self.btn_previous.clicked.connect(open_previous_tool)
        self.btn_settings = QPushButton("Ajustes…")
        self.btn_settings.clicked.connect(self._open_settings)
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.reject)
        bottom.addWidget(self.btn_previous)
        bottom.addWidget(self.btn_settings)
        bottom.addWidget(self.btn_close)
        layout.addLayout(bottom)
        self._refresh()

    # ------------------------------------------------------------------ construcción

    def _build_roots(self, roots: list[str]) -> QHBoxLayout:
        row = QHBoxLayout()
        self.roots = QListWidget()
        self.roots.setMaximumHeight(68)
        self.roots.addItems(roots)
        self.roots.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        row.addWidget(self.roots, 1)
        column = QVBoxLayout()
        self.btn_add_folder = QPushButton("Agregar carpeta…")
        self.btn_add_folder.clicked.connect(self._add_folder)
        self.btn_add_drive = QPushButton("Agregar unidad…")
        self.btn_add_drive.clicked.connect(self._add_drive)
        self.btn_remove_root = QPushButton("Quitar")
        self.btn_remove_root.clicked.connect(self._remove_roots)
        for button in (self.btn_add_folder, self.btn_add_drive, self.btn_remove_root):
            column.addWidget(button)
        row.addLayout(column)
        self.btn_analyze = QPushButton("Analizar")
        self.btn_analyze.setObjectName("PrimaryButton")
        self.btn_analyze.setToolTip("Calcula las huellas e identifica las canciones. No cambia ningún archivo.")
        self.btn_analyze.clicked.connect(self._analyze)
        row.addWidget(self.btn_analyze)
        return row

    def _build_results(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        tools = QHBoxLayout()
        tools.addWidget(QLabel("Ver:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(_FILTERS)
        self.filter_combo.currentIndexChanged.connect(lambda index: self.model.set_filter(index))
        tools.addWidget(self.filter_combo)
        self.btn_check = QPushButton("Marcar las visibles")
        self.btn_check.clicked.connect(lambda: self.model.check_visible(True))
        self.btn_uncheck = QPushButton("Desmarcar")
        self.btn_uncheck.clicked.connect(lambda: self.model.check_visible(False))
        tools.addWidget(self.btn_check)
        tools.addWidget(self.btn_uncheck)
        tools.addStretch(1)
        self.btn_normalize_selected = QPushButton("Normalizar selección")
        self.btn_normalize_selected.clicked.connect(self._normalize_selected)
        self.btn_normalize_all = QPushButton("Normalizar todas las seguras")
        self.btn_normalize_all.clicked.connect(self._normalize_all)
        tools.addWidget(self.btn_normalize_selected)
        tools.addWidget(self.btn_normalize_all)
        layout.addLayout(tools)
        self.model = ResultsModel(self._update_buttons, self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in ((COL_NOW, 270), (COL_TITLE, 200), (COL_ARTIST, 150), (COL_VERSION, 70), (COL_SCORE, 75), (COL_STATE, 90)):
            header.resizeSection(column, width)
        header.setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        return page

    def _build_pending(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.pending = QTableView()
        self.pending_model = _SimpleModel(("Canción", "Ubicación original", "Motivo", "Posibles coincidencias", "Intentos"), self)
        self.pending.setModel(self.pending_model)
        self.pending.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.pending.verticalHeader().hide()
        self.pending.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.pending, 1)
        tools = QHBoxLayout()
        self.btn_retry_selected = QPushButton("Reintentar selección")
        self.btn_retry_selected.clicked.connect(lambda: self._retry(self._selected_pending()))
        self.btn_retry_all = QPushButton("Reintentar todas")
        self.btn_retry_all.clicked.connect(lambda: self._retry(None))
        self.btn_fix = QPushButton("Corregir a mano…")
        self.btn_fix.setToolTip("Escribe el título y el artista: se normaliza y vuelve a su carpeta")
        self.btn_fix.clicked.connect(self._fix_pending)
        self.btn_resolve = QPushButton("Procesar las identificadas")
        self.btn_resolve.setToolTip("Las que ya se reconocieron se normalizan y vuelven a su carpeta")
        self.btn_resolve.clicked.connect(self._resolve_pending)
        for button in (self.btn_retry_selected, self.btn_retry_all, self.btn_fix):
            tools.addWidget(button)
        tools.addStretch(1)
        tools.addWidget(self.btn_resolve)
        layout.addLayout(tools)
        return page

    def _build_history(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.history = QTableView()
        self.history_model = _SimpleModel(("Antes", "Ahora", "Título", "Artista", "Estado", "Respaldo"), self)
        self.history.setModel(self.history_model)
        self.history.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history.verticalHeader().hide()
        self.history.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.history, 1)
        tools = QHBoxLayout()
        tools.addStretch(1)
        self.btn_restore_selected = QPushButton("Restaurar selección")
        self.btn_restore_selected.clicked.connect(self._restore_selected)
        self.btn_restore_all = QPushButton("Restaurar todo")
        self.btn_restore_all.clicked.connect(self._restore_all)
        tools.addWidget(self.btn_restore_selected)
        tools.addWidget(self.btn_restore_all)
        layout.addLayout(tools)
        return page

    # ------------------------------------------------------------------ lo que se muestra

    def _root_list(self) -> list[str]:
        return [self.roots.item(i).text() for i in range(self.roots.count())]

    def _refresh(self) -> None:
        checked = {r.file_id for r in self.model.rows() if r.checked}
        rows = []
        for row in self._db.result_rows(self._root_list()):
            rows.append(ResultRow(row["id"], row["path"], row["title"] or "", row["artist"] or "", row["version"] or "", row["score"],
                                  row["decision"] or "", row["reason"] or row["problem"] or "", row["status"] == STATUS_DAMAGED,
                                  row["id"] in checked))
        self.model.load(rows)
        self._pending_rows = self._db.pending_songs()
        self.pending_model.load([
            (os.path.basename(p.pending_path), p.original_path, p.reason, " · ".join(p.candidates), str(p.retries)) for p in self._pending_rows
        ])
        self._history_rows = list(reversed(self._db.restorable_items()))
        self.history_model.load([
            (os.path.basename(i.old_path), os.path.basename(i.new_path) or "—", i.new_title, i.new_artist, i.state, i.backup_path) for i in self._history_rows
        ])
        self.tabs.setTabText(1, f"Pendientes ({len(self._pending_rows)})")
        self._update_buttons()

    def _update_buttons(self, *_args) -> None:
        if not hasattr(self, "runner"):
            return
        busy = self.runner.busy
        rows = self.model.rows()
        safe = sum(1 for r in rows if r.decision == DECISION_AUTO and not r.damaged)
        doubts = sum(1 for r in rows if r.decision == DECISION_REVIEW and not r.damaged)
        checked = sum(1 for r in rows if r.checked)
        self.summary.setText(f"{plural(len(rows), 'canción', 'canciones')} · {safe} seguras · {doubts} dudosas · {checked} marcadas")
        self.btn_normalize_selected.setEnabled(checked > 0 and not busy)
        self.btn_normalize_selected.setText(f"Normalizar selección ({checked})" if checked else "Normalizar selección")
        self.btn_normalize_all.setEnabled(safe > 0 and not busy)
        self.btn_normalize_all.setText(f"Normalizar las {safe} seguras" if safe else "Normalizar todas las seguras")
        for button in (self.btn_analyze, self.btn_add_folder, self.btn_add_drive, self.btn_remove_root, self.btn_settings, self.btn_previous,
                       self.btn_retry_selected, self.btn_retry_all, self.btn_fix, self.btn_resolve, self.btn_restore_selected, self.btn_restore_all,
                       self.btn_check, self.btn_uncheck, self.filter_combo):
            button.setEnabled(not busy)

    def _show_progress(self) -> None:
        elapsed = int(time.monotonic() - self._started)
        clock = f"{elapsed // 3600:02d}:{elapsed % 3600 // 60:02d}:{elapsed % 60:02d}"
        done, total = self._counts
        if total:
            self.status.setText(f"{done * 100 // total} %  ·  {done} de {total}  ·  faltan {total - done}  ·  {clock}")
        else:
            self.status.setText(f"{self._phase_text}  ·  {clock}")

    def _on_progress(self, done: int, total: int, text: str) -> None:
        self._counts = (done, total)
        if not total and text:
            self._phase_text = text
        self._show_progress()

    def _start(self, worker, text: str, on_finished, *, modifies_files: bool = False, stop_question: StopQuestion | None = None) -> None:
        self._started, self._counts, self._phase_text = time.monotonic(), (0, 0), text
        worker.progress.connect(self._on_progress)
        self.runner.start(worker, 0, text, on_finished, modifies_files=modifies_files, stop_question=stop_question)
        self._clock.start()
        self._show_progress()

    def _finish(self, message: str) -> None:
        self._clock.stop()
        self.status.setText(message)
        self._refresh()

    def _add_problems(self, problems) -> None:
        for path, reason in problems:
            self.errors.appendPlainText(f"{path}: {reason}" if path else str(reason))
        if problems:
            self.tabs.setTabText(3, f"Errores ({self.errors.blockCount() - (0 if self.errors.toPlainText() else 1)})")

    # ------------------------------------------------------------------ carpetas

    def _add_root(self, path: str) -> None:
        path = os.path.normpath(path)
        if path not in self._root_list():
            self.roots.addItem(path)
            self._refresh()

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta con música")
        if folder:
            self._add_root(folder)

    def _add_drive(self) -> None:
        drive, ok = QInputDialog.getItem(self, "Agregar unidad", "Unidad completa (se examinan todas sus carpetas):", file_locator._local_drives(), 0, False)
        if ok and drive:
            self._add_root(drive)

    def _remove_roots(self) -> None:
        for item in self.roots.selectedItems():
            self.roots.takeItem(self.roots.row(item))
        self._refresh()

    # ------------------------------------------------------------------ analizar e identificar

    def _analyze(self) -> None:
        roots = self._root_list()
        if not roots:
            QMessageBox.information(self, "Analizar", "Agrega al menos una carpeta o unidad.")
            return
        if not fingerprint.available():
            QMessageBox.warning(self, "Analizar", "Falta el componente fpcalc: vuelve a instalar el programa.")
            return
        if not self._prefs.acoustid_key:
            AcoustIdKeyDialog(self._prefs, self).exec()
        self._start(AnalyzeWorker(roots, None, fingerprint.compute), "Examinando las carpetas…", self._on_analyzed)

    def _on_analyzed(self, result) -> None:
        self._add_problems([("", p) for p in result.problems])
        if result.cancelled:
            self._finish(f"Análisis detenido: {result.computed} huellas nuevas. Lo hecho se conserva.")
            return
        self._identify()

    def _identify(self) -> None:
        worker = IdentifyWorker(self._prefs.acoustid_key, self._prefs.confidence, None, acoustid_lookup.lookup_raw)
        self._start(worker, "Identificando las canciones…", self._on_identified)

    def _on_identified(self, result) -> None:
        text = f"Listo: {result.automatic} seguras y {result.review} dudosas."
        if result.offline:
            text = f"Sin clave de AcoustID: {result.offline} canciones con una propuesta por su título, para que las revises."
        if result.cancelled:
            text = "Identificación detenida. Lo hecho se conserva."
        if result.problem:
            self.errors.appendPlainText(result.problem)
            text = f"Se detuvo: {result.problem} Lo hecho se conserva: analiza de nuevo para seguir."
        self._finish(text)
        if result.invalid_key:
            self._finish("AcoustID no aceptó la clave.")
            AcoustIdKeyDialog(self._prefs, self).exec()

    # ------------------------------------------------------------------ normalizar

    def _normalize_selected(self) -> None:
        jobs = [SongJob(r.file_id, r.title, r.artist) for r in self.model.rows() if r.checked and r.title and r.artist and not r.damaged]
        missing = sum(1 for r in self.model.rows() if r.checked and not (r.title and r.artist))
        if missing:
            QMessageBox.information(self, "Normalizar", f"{plural(missing, 'canción marcada no tiene', 'canciones marcadas no tienen')} título o artista: no se tocarán.")
        self._normalize(jobs, send_doubts=False)

    def _normalize_all(self) -> None:
        jobs = [SongJob(r.file_id, r.title, r.artist) for r in self.model.rows() if r.decision == DECISION_AUTO and not r.damaged and r.title and r.artist]
        self._normalize(jobs, send_doubts=True)

    def _normalize(self, jobs: list[SongJob], send_doubts: bool) -> None:
        if not jobs or self.runner.busy:
            return
        doubts = sum(1 for r in self.model.rows() if r.decision == DECISION_REVIEW and not r.damaged) if send_doubts else 0
        extra = f"\n\nLas {doubts} dudosas irán a PENDIENTES_REVISION, sin cambiar sus nombres ni sus etiquetas." if doubts else ""
        folder = self._prefs.organizer_backup_folder or "RESPALDOS_MP3, en la raíz de cada disco"
        if ask(
            self, "Normalizar", f"¿Normalizar {plural(len(jobs), 'canción', 'canciones')}?",
            [("Normalizar", QMessageBox.ButtonRole.AcceptRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Question,
            "Cambia el nombre del archivo y deja dentro solo el título y el artista: se borran álbum, género, año, comentarios "
            f"y carátula. Antes se hace una copia completa en {folder}. El audio no se toca, y se puede restaurar en Historial."
            " Si suena una de estas canciones, se detiene." + extra,
        ) != 0:
            return
        if not self._ops.prepare_organizer([self._db.file_by_id(j.file_id).path for j in jobs]):
            return
        self._send_doubts_after = bool(doubts)
        worker = NormalizeWorker(jobs, self._prefs.organizer_backup_folder or None)
        worker.applied.connect(self._on_applied)
        self._start(worker, "Normalizando…", self._on_normalized, modifies_files=True, stop_question=StopQuestion(
            "la normalización", "Seguir", "Detener", "Se termina la canción en curso: ninguna queda a medias."))

    def _on_applied(self, item) -> None:
        self._ops.sync_organizer_item(self._db, item)

    def _on_normalized(self, result) -> None:
        self._add_problems(result.failed)
        text = f"{plural(result.done, 'canción normalizada', 'canciones normalizadas')}"
        if result.failed:
            text += f", {len(result.failed)} con problemas (ver Errores)"
        self._finish(text + ".")
        self._ops.changed()
        if self._send_doubts_after and not result.cancelled:
            self._send_doubts_after = False
            self._send_to_pending()

    def _send_to_pending(self) -> None:
        roots = self._root_list()
        ids = [r.file_id for r in self.model.rows() if r.decision == DECISION_REVIEW and not r.damaged]
        worker = MoveToPendingWorker(roots, ids)
        worker.moved.connect(self._on_moved)
        self._start(worker, "Llevando las dudosas a pendientes…", self._on_pending_done, modifies_files=True)

    def _on_moved(self, pending) -> None:
        self._ops.sync_organizer_pending(self._db, pending)

    def _on_pending_done(self, result) -> None:
        self._add_problems(result.failed)
        self._finish(f"{plural(result.moved, 'canción movida', 'canciones movidas')} a pendientes.")
        self._ops.changed()

    # ------------------------------------------------------------------ pendientes

    def _selected_pending(self) -> list[int]:
        rows = {index.row() for index in self.pending.selectionModel().selectedRows()}
        return [self._pending_rows[r].file_id for r in rows]

    def _retry(self, file_ids: list[int] | None) -> None:
        if file_ids == []:
            QMessageBox.information(self, "Reintentar", "Selecciona alguna canción de la lista.")
            return
        if not self._prefs.acoustid_key:
            AcoustIdKeyDialog(self._prefs, self).exec()
            if not self._prefs.acoustid_key:
                return
        if self._db.prepare_retry(file_ids):
            self._identify()

    def _fix_pending(self) -> None:
        ids = self._selected_pending()
        if len(ids) != 1:
            QMessageBox.information(self, "Corregir a mano", "Selecciona una canción de la lista.")
            return
        title, ok = QInputDialog.getText(self, "Corregir a mano", "Título de la canción:")
        if not ok or not title.strip():
            return
        artist, ok = QInputDialog.getText(self, "Corregir a mano", "Artista principal:")
        if ok and artist.strip():
            self._start_resolve([SongJob(ids[0], title, artist)])

    def _resolve_pending(self) -> None:
        self._start_resolve(None)

    def _start_resolve(self, jobs: list[SongJob] | None) -> None:
        if not self._ops.prepare_organizer([p.pending_path for p in self._pending_rows]):
            return
        worker = ResolvePendingWorker(jobs, self._prefs.organizer_backup_folder or None)
        worker.returned.connect(self._on_moved)
        worker.applied.connect(self._on_applied)
        self._start(worker, "Devolviendo las canciones…", self._on_resolved, modifies_files=True)

    def _on_resolved(self, result) -> None:
        self._add_problems(result.failed)
        self._finish(f"{plural(result.normalized, 'canción normalizada', 'canciones normalizadas')} y de vuelta en su carpeta.")
        self._ops.changed()

    # ------------------------------------------------------------------ restaurar

    def _restore_selected(self) -> None:
        rows = {index.row() for index in self.history.selectionModel().selectedRows()}
        items = [self._history_rows[r] for r in rows]
        if not items:
            QMessageBox.information(self, "Restaurar", "Selecciona alguna canción de la lista.")
            return
        self._restore(items)

    def _restore_all(self) -> None:
        self._restore(list(self._history_rows))

    def _restore(self, items: list) -> None:
        if not items or ask(
            self, "Restaurar", f"¿Restaurar {plural(len(items), 'canción', 'canciones')}?",
            [("Restaurar", QMessageBox.ButtonRole.AcceptRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Question, "Cada una vuelve exactamente a como estaba, con su nombre y sus datos. Los respaldos se conservan.",
        ) != 0:
            return
        if not self._ops.prepare_organizer([i.new_path or i.old_path for i in items]):
            return
        worker = RestoreWorker(items)
        worker.restored.connect(self._on_restored)
        self._start(worker, "Restaurando…", self._on_restore_done, modifies_files=True)

    def _on_restored(self, item) -> None:
        self._ops.sync_organizer_restored(self._db, item)

    def _on_restore_done(self, problems: list) -> None:
        self._add_problems(problems)
        self._finish("Restauración terminada." if not problems else f"{len(problems)} no se pudieron restaurar (ver Errores).")
        self._ops.changed()

    # ------------------------------------------------------------------ ajustes y cierre

    def _open_settings(self) -> None:
        before = self._prefs.confidence
        OrganizerSettingsDialog(self._prefs, self).exec()
        if self._prefs.confidence != before:
            self._db.forget_identifications()
            self.status.setText("Cambiaron los niveles: pulsa Analizar para decidir otra vez (no repite consultas).")
            self._refresh()

    def reject(self) -> None:
        if self.runner.request_close():
            self._clock.stop()
            self._db.close()
            super().reject()


class _SimpleModel(QAbstractTableModel):
    def __init__(self, columns: tuple[str, ...], parent=None) -> None:
        super().__init__(parent)
        self._columns = columns
        self._rows: list[tuple[str, ...]] = []

    def load(self, rows: list[tuple[str, ...]]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        return self._columns[section] if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole else None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return self._rows[index.row()][index.column()]
        return None


def default_roots(paths: list[str]) -> list[str]:
    """Las carpetas de la biblioteca, sin las que ya están dentro de otra."""
    folders = sorted({os.path.dirname(p) for p in paths}, key=lambda folder: (len(folder), folder))
    roots: list[str] = []
    for folder in folders:
        if not any(folder == r or folder.startswith(r.rstrip("\\/") + os.sep) for r in roots):
            roots.append(folder)
    return roots

