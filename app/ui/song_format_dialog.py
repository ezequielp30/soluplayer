"""Herramienta «Título y quién la canta»: muestra la propuesta de cada canción, se corrige lo que haga falta y
recién entonces se aplica al título, al nombre del archivo y a sus etiquetas (ver app/song_format.py)."""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import song_format
from ..file_operations import FileOperations
from ..models import Track
from ..title_format import known_singers, propose
from ..utils import plural
from .dialogs import StatusLabel, ask, tool_intro
from .worker_runner import StopQuestion, WorkerRunner

log = logging.getLogger(__name__)

COL_NOW, COL_SONG, COL_SINGER, COL_STATE = range(4)
SURE, REVIEW = "Lista", "Por revisar"
FILTER_ALL, FILTER_REVIEW = 0, 1

_DETAILS = (
    "Cada canción queda como «Canción - Quién la canta» en el título, en el nombre del archivo y dentro del "
    "archivo, sin lo que agrega YouTube («(Video Oficial)», «LETRA»…). Los demás datos se borran: álbum, género, "
    "año, comentarios y carátula.\n"
    "Las playlists y tus órdenes se conservan, el sonido no se toca y todo se puede deshacer en Herramientas → "
    "Historial de cambios en archivos."
)


class SongFormatDialog(QDialog):
    def __init__(self, ops: FileOperations, tracks_provider: Callable[[], list[Track]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ops = ops
        self._tracks_provider = tracks_provider
        self._rows: list[Track] = []
        self._session: song_format.FormatSession | None = None
        self._applied = 0
        self._problems: list[str] = []
        self.setWindowTitle("Título y quién la canta")
        self.resize(1040, 640)

        layout = QVBoxLayout(self)
        layout.addWidget(tool_intro("Revisa la propuesta de cada canción y corrige lo que haga falta.", _DETAILS))

        tools = QHBoxLayout()
        tools.addWidget(QLabel("Ver:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Todas", "Por revisar"])
        self.filter_combo.currentIndexChanged.connect(self._apply_filter)
        tools.addWidget(self.filter_combo)
        self.btn_swap = QPushButton("Invertir canción y quien canta")
        self.btn_swap.setToolTip("En las filas seleccionadas")
        self.btn_swap.clicked.connect(self._swap_selected)
        tools.addWidget(self.btn_swap)
        self.btn_check_all = QPushButton("Marcar las visibles")
        self.btn_check_all.clicked.connect(lambda: self._check_visible(True))
        tools.addWidget(self.btn_check_all)
        self.btn_uncheck_all = QPushButton("Desmarcar las visibles")
        self.btn_uncheck_all.clicked.connect(lambda: self._check_visible(False))
        tools.addWidget(self.btn_uncheck_all)
        tools.addStretch(1)
        layout.addLayout(tools)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Ahora", "Canción", "Quién la canta", "Estado"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.resizeSection(COL_NOW, 390)
        header.resizeSection(COL_SONG, 290)
        header.resizeSection(COL_SINGER, 200)
        header.setStretchLastSection(True)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, 1)

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

        bottom = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setObjectName("DialogNote")
        bottom.addWidget(self.summary, 1)
        self.keep_cover = QCheckBox("Conservar la carátula")
        self.keep_cover.setToolTip("Sin marcar, la carátula se borra junto con los demás datos")
        bottom.addWidget(self.keep_cover)
        self.btn_apply = QPushButton("Aplicar")
        self.btn_apply.setObjectName("PrimaryButton")
        self.btn_apply.clicked.connect(self._apply)
        bottom.addWidget(self.btn_apply)
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.reject)
        bottom.addWidget(self.btn_close)
        layout.addLayout(bottom)
        self._load()

    # ------------------------------------------------------------------ la lista

    def _load(self) -> None:
        tracks = self._ops.db.with_raw_text(self._tracks_provider())
        singers = known_singers((t.title, t.artist) for t in self._ops.db.with_raw_text(self._ops.db.all_tracks()))
        rows = []
        for track in tracks:
            proposal = propose(track.title, track.artist, singers)
            if not song_format.is_formatted(track, proposal.song, proposal.singer):
                rows.append((track, proposal))
        rows.sort(key=lambda row: row[1].sure)  # primero lo que hay que mirar
        self._rows = [track for track, _ in rows]
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for row, (track, proposal) in enumerate(rows):
            now = QTableWidgetItem(track.title)
            now.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
            now.setCheckState(Qt.CheckState.Checked if proposal.sure else Qt.CheckState.Unchecked)
            now.setToolTip(os.path.basename(track.path))
            self.table.setItem(row, COL_NOW, now)
            self.table.setItem(row, COL_SONG, QTableWidgetItem(proposal.song))
            self.table.setItem(row, COL_SINGER, QTableWidgetItem(proposal.singer))
            state = QTableWidgetItem(SURE if proposal.sure else REVIEW)
            state.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, COL_STATE, state)
        self.table.blockSignals(False)
        self._apply_filter()

    def _apply_filter(self) -> None:
        only_review = self.filter_combo.currentIndex() == FILTER_REVIEW
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, only_review and self.table.item(row, COL_STATE).text() != REVIEW)
        self._update_buttons()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() in (COL_SONG, COL_SINGER):  # lo corrigió una persona: queda elegida
            self.table.blockSignals(True)
            self.table.item(item.row(), COL_NOW).setCheckState(Qt.CheckState.Checked)
            self.table.item(item.row(), COL_STATE).setText(SURE)
            self.table.blockSignals(False)
            self._apply_filter()
            return
        self._update_buttons()

    def _swap_selected(self) -> None:
        rows = sorted(index.row() for index in self.table.selectionModel().selectedRows())
        for row in rows:
            song, singer = self.table.item(row, COL_SONG).text(), self.table.item(row, COL_SINGER).text()
            self.table.item(row, COL_SONG).setText(singer)
            self.table.item(row, COL_SINGER).setText(song)

    def _check_visible(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                self.table.item(row, COL_NOW).setCheckState(state)
        self.table.blockSignals(False)
        self._update_buttons()

    def _chosen(self) -> list[tuple[Track, str, str]]:
        """Las marcadas que tienen canción y quien canta."""
        chosen = []
        for row, track in enumerate(self._rows):
            song = self.table.item(row, COL_SONG).text().strip()
            singer = self.table.item(row, COL_SINGER).text().strip()
            if self.table.item(row, COL_NOW).checkState() == Qt.CheckState.Checked and song and singer:
                chosen.append((track, song, singer))
        return chosen

    def _update_buttons(self, *_args) -> None:
        busy = self.runner.busy
        count = len(self._chosen())
        review = sum(1 for row in range(self.table.rowCount()) if self.table.item(row, COL_STATE).text() == REVIEW)
        self.summary.setText(f"{plural(count, 'canción marcada', 'canciones marcadas')} · {review} por revisar")
        self.btn_apply.setEnabled(count > 0 and not busy)
        self.btn_apply.setText(f"Aplicar a {count}" if count else "Aplicar")
        for widget in (self.btn_swap, self.btn_check_all, self.btn_uncheck_all, self.filter_combo, self.keep_cover, self.table):
            widget.setEnabled(not busy)

    # ------------------------------------------------------------------ aplicar

    def _apply(self) -> None:
        chosen = self._chosen()
        if not chosen or self.runner.busy:
            return
        keep = self.keep_cover.isChecked()
        erased = "álbum, género, año y comentarios" if keep else "álbum, género, año, comentarios y carátula"
        if ask(
            self, "Aplicar", f"¿Cambiar {plural(len(chosen), 'canción', 'canciones')}?",
            [("Aplicar", QMessageBox.ButtonRole.AcceptRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Question,
            f"Cambian el título, quien la canta y el nombre del archivo. Se borran: {erased}. Las vistas de Álbumes y "
            "Géneros quedan sin esas canciones. El sonido no se toca, las playlists se conservan y se puede deshacer "
            "desde el Historial. Si suena una de estas canciones, se detiene.",
        ) != 0:
            return
        if not self._ops.prepare_files("antes-de-titulo-y-cantante", {track.id for track, _, _ in chosen}):
            return
        changes = [song_format.plan(track, song, singer, keep) for track, song, singer in chosen]
        self._session = song_format.new_session()
        self._applied, self._problems = 0, []
        worker = song_format.SongFormatWorker(self._session, changes)
        worker.applied.connect(self._on_applied)
        worker.failed.connect(self._problems.append)
        self.runner.start(
            worker, len(changes), "Cambiando las canciones…", self._on_finished, label="Cambiando", modifies_files=True,
            stop_question=StopQuestion(
                "los cambios", "Seguir", "Detener", "Lo ya cambiado queda hecho y se puede deshacer desde el Historial."
            ),
        )

    def _on_applied(self, change: song_format.FormatChange) -> None:
        try:
            song_format.set_in_library(self._ops.db, change)
            change.done = True
            self._applied += 1
        except sqlite3.Error as exc:
            log.error("No se pudo actualizar la biblioteca con %s: %s", change.new_path, exc)
            self._problems.append(f"{os.path.basename(change.new_path)}: no se pudo actualizar la biblioteca ({exc}).")
            try:
                song_format.revert(self._session, change)
            except Exception:
                log.exception("No se pudo devolver %s", change.new_path)

    def _on_finished(self, _cancelled: bool) -> None:
        session = self._session
        session.changes = [c for c in session.changes if c.done]
        if session.changes:
            session.status = song_format.journal.STATUS_DONE
            session.save()
        else:
            session.path.unlink(missing_ok=True)
        self._ops.changed()
        self._load()
        message = f"{plural(self._applied, 'canción cambiada', 'canciones cambiadas')}. Se puede deshacer desde el Historial."
        if self._problems:
            shown = "\n".join(f"• {p}" for p in self._problems[:20])
            message += f"\n\nNo se pudieron cambiar {len(self._problems)}:\n{shown}"
        QMessageBox.information(self, "Título y quién la canta", message)

    def reject(self) -> None:
        if self.runner.request_close():
            super().reject()
