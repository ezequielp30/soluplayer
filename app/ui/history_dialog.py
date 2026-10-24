"""Diálogo «Historial de cambios en archivos»: todo lo que el programa hizo con tus archivos, en un solo
lugar, con la forma de deshacerlo (reunir repetidas, convertir a MP3 y ajustar el volumen)."""

from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..file_operations import KIND_CONVERSION, KIND_REVIEW, KIND_VOLUME, FileOperations, HistoryEntry
from ..models import Track
from ..utils import plural
from . import theme
from .dialogs import ask, empty_state, note_label, tidy_table

COL_WHEN, COL_WHAT, COL_DETAIL, COL_STATE = range(4)


class HistoryDialog(QDialog):
    def __init__(
        self,
        ops: FileOperations,
        tracks_provider: Callable[[], list[Track]],
        open_volume: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Historial de cambios en archivos")
        self.resize(980, 520)
        self._ops = ops
        self._tracks_provider = tracks_provider
        self._open_volume = open_volume
        self._entries: list[HistoryEntry] = []

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Todo lo que el programa hizo con tus archivos de música: <b>reunir repetidas</b>, <b>convertir a MP3</b> "
            "y <b>ajustar el volumen</b>. Elige una operación para deshacerla."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(note_label(
            "Deshacer devuelve cada archivo a su carpeta original (los MP3 creados por una conversión van a la "
            "Papelera). El volumen se revierte en su propia ventana, porque reescribir los MP3 lleva un rato."
        ))

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Fecha", "Operación", "Detalle", "Estado"])
        tidy_table(self.table)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)  # en las rutas importa el final
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.resizeSection(COL_WHEN, 130)
        header.resizeSection(COL_WHAT, 230)
        header.setSectionResizeMode(COL_DETAIL, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(COL_STATE, 110)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.cellDoubleClicked.connect(lambda *_: self._undo())
        self.empty, set_empty = empty_state()
        set_empty("Todavía no hay cambios", "Cuando reúnas repetidas, conviertas a MP3 o ajustes el volumen, aparecerá aquí.")
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        layout.addWidget(self.stack, 1)

        bottom = QHBoxLayout()
        self.btn_folder = QPushButton("Abrir la carpeta")
        self.btn_folder.clicked.connect(self._open_folder)
        bottom.addWidget(self.btn_folder)
        bottom.addStretch(1)
        self.btn_undo = QPushButton("Deshacer…")
        self.btn_undo.setObjectName("PrimaryButton")
        self.btn_undo.clicked.connect(self._undo)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        bottom.addWidget(self.btn_undo)
        bottom.addWidget(close)
        layout.addLayout(bottom)

        self.refresh()

    def refresh(self) -> None:
        self._entries = self._ops.history(self._tracks_provider())
        self.table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            when = entry.when.strftime("%d/%m/%Y %H:%M") if entry.when else "—"
            cells = [when, entry.title, entry.detail, entry.status]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == COL_DETAIL:
                    item.setToolTip(text)
                if col == COL_STATE:
                    role = {"Deshecha": "muted", "Interrumpida": "danger"}.get(entry.status)
                    if role:
                        item.setForeground(theme.qcolor(role))
                self.table.setItem(row, col, item)
        self.stack.setCurrentWidget(self.table if self._entries else self.empty)
        first = next((i for i, e in enumerate(self._entries) if e.can_undo), 0 if self._entries else -1)
        if first >= 0:
            self.table.selectRow(first)
        self._update_buttons()

    def _selected(self) -> HistoryEntry | None:
        rows = self.table.selectionModel().selectedRows()
        return self._entries[rows[0].row()] if rows else None

    def _update_buttons(self) -> None:
        entry = self._selected()
        self.btn_undo.setText("Revertir volumen…" if entry and entry.kind == KIND_VOLUME else "Deshacer…")
        self.btn_undo.setEnabled(bool(entry and entry.can_undo))
        self.btn_folder.setEnabled(bool(entry and entry.location and os.path.isdir(entry.location)))

    def _open_folder(self) -> None:
        entry = self._selected()
        if entry and entry.location:
            QDesktopServices.openUrl(QUrl.fromLocalFile(entry.location))

    def _undo(self) -> None:
        entry = self._selected()
        if entry is None or not entry.can_undo:
            return
        if entry.kind == KIND_VOLUME:
            self._open_volume()
            self.refresh()
            return
        if entry.kind == KIND_REVIEW:
            text = f"¿Devolver {plural(entry.count, 'archivo')} a su carpeta original?"
            info = "Las copias reunidas para revisar vuelven a donde estaban; la biblioteca y las playlists se actualizan solas."
        elif entry.kind == KIND_CONVERSION:
            text = f"¿Deshacer la conversión de {plural(entry.count, 'canción', 'canciones')}?"
            info = ("Los originales vuelven a su sitio y la biblioteca vuelve a usarlos. Los MP3 creados van a la "
                    "Papelera (solo si su original está de vuelta en su lugar).")
        else:
            return
        if ask(self, "Deshacer", text,
               [("Deshacer", QMessageBox.ButtonRole.AcceptRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
               QMessageBox.Icon.Question, info) != 0:
            return
        outcome = self._ops.undo(entry)
        QMessageBox.information(self, "Deshacer", outcome.message)
        self.refresh()
