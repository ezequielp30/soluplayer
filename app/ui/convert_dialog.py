"""Diálogo «Convertir a MP3»: busca en la biblioteca los archivos que no son MP3 y los convierte.

Ventana compacta: una línea de explicación (el detalle va en «?»), una lista con lo justo y, al terminar,
las canciones convertidas salen de la lista y el resultado se muestra en una franja (sin avisos emergentes).
"""

from __future__ import annotations

import os
import sqlite3
from typing import Callable

import mutagen
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
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

from .. import converter
from ..file_operations import FileOperations
from ..metadata import audio_quality
from ..models import Track
from ..utils import plural
from . import theme
from .dialogs import ResultBanner, StatusLabel, ask, empty_state, tidy_table, tool_intro
from .worker_runner import StopQuestion, WorkerRunner

COL_USE, COL_SONG, COL_NOW, COL_MP3, COL_STATE = range(5)
_TRACK = Qt.ItemDataRole.UserRole

_DETAILS = (
    "Convierte con LAME, el codificador de referencia. Desde formatos sin pérdida (FLAC, WAV…) usa 320 kbps, "
    "transparente. Desde otro formato ya comprimido (WMA, AAC, OGG…) es una SEGUNDA compresión: usa el doble "
    "de kbps para que la pérdida extra sea mínima, pero puede sumar algo; conviértelos solo si tu equipo "
    "(auto, celular) no los reproduce.\n"
    "Título, artista, álbum, género y carátula pasan al MP3, y las playlists lo usan solas.\n"
    "Convertir no mejora la calidad que ya tiene un archivo.\n"
    f"Los originales no se borran: se guardan en «{converter.ORIGINALS_FOLDER_NAME}» y la conversión se puede "
    "deshacer en Herramientas → Historial de cambios en archivos."
)


def is_lossy(path: str) -> bool:
    """El original ya viene comprimido con pérdida (WMA, AAC, OGG…): convertirlo es comprimir dos veces."""
    ext = os.path.splitext(path)[1].lower()
    if ext in converter.LOSSLESS:
        return False
    if ext in (".m4a", ".m4b", ".mp4"):  # puede ser AAC (con pérdida) o ALAC (Apple Lossless, sin pérdida)
        try:
            return not str(getattr(mutagen.File(path).info, "codec", "")).lower().startswith("alac")
        except Exception:
            return True
    return True


class ConvertDialog(QDialog):
    def __init__(
        self,
        ops: FileOperations,
        tracks_provider: Callable[[], list[Track]],
        parent: QWidget | None = None,
        open_history: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Convertir a MP3")
        self.resize(780, 480)
        self._ops = ops
        self._tracks_provider = tracks_provider
        self._open_history = open_history

        layout = QVBoxLayout(self)
        layout.addWidget(tool_intro("Convierte a MP3 las canciones de otros formatos. Los originales se guardan.", _DETAILS))
        self.banner = ResultBanner()
        layout.addWidget(self.banner)

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
        self.table.setHorizontalHeaderLabels(["", "Canción", "Ahora", "Será", "Estado"])
        tidy_table(self.table)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in ((COL_USE, 30), (COL_NOW, 110), (COL_MP3, 105), (COL_STATE, 120)):
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
        self.btn_history = QPushButton("Deshacer…")
        self.btn_history.setToolTip("Historial de cambios: devuelve los originales a su sitio")
        self.btn_history.clicked.connect(self._history)
        self.btn_history.setVisible(open_history is not None)
        self.btn_convert = QPushButton("Convertir")
        self.btn_convert.setObjectName("PrimaryButton")
        self.btn_convert.clicked.connect(self._convert)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.reject)
        bottom.addWidget(self.btn_history)
        bottom.addWidget(self.btn_convert)
        bottom.addWidget(close)
        layout.addLayout(bottom)

        self.scan()

    # ------------------------------------------------------------------ búsqueda

    def scan(self) -> None:
        """Busca en la biblioteca los archivos que no son MP3."""
        tracks = sorted(
            (t for t in self._tracks_provider() if os.path.splitext(t.path)[1].lower() != ".mp3"),
            key=lambda t: t.path.lower(),
        )
        self.table.blockSignals(True)
        self.table.setRowCount(len(tracks))
        size = 0
        for row, track in enumerate(tracks):
            ext = os.path.splitext(track.path)[1].lstrip(".").upper()
            use = QTableWidgetItem()
            use.setData(_TRACK, track)
            try:
                # Se vuelve a mirar el disco: el archivo pudo desaparecer después de cargar la biblioteca.
                file_size = os.path.getsize(track.path) if track.available else None
            except OSError:
                file_size = None
            details = track.path
            if file_size is not None:
                use.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                use.setCheckState(Qt.CheckState.Checked)
                now, result, state = ext, "…", ""  # la calidad se completa por tandas (ver _fill_quality)
                size += file_size
            else:
                use.setFlags(Qt.ItemFlag.ItemIsEnabled)
                now, result, state = ext, "—", "No se encuentra"
            for col, value in enumerate([use, f"{track.title} — {track.artist}", now, result, state]):
                item = value if isinstance(value, QTableWidgetItem) else QTableWidgetItem(value)
                if col == COL_SONG:
                    item.setToolTip(details)
                if col == COL_STATE and value:
                    item.setForeground(theme.qcolor("muted"))
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)
        self.summary.setText(f"{plural(len(tracks), 'archivo', 'archivos')} · {size / 1_048_576:.0f} MB" if tracks else "")
        self._quality_next = 0
        self._fill_quality(first=True)
        self._show_list_or_empty()
        self._update_buttons()

    def _fill_quality(self, first: bool = False) -> None:
        """Lee la calidad de cada archivo (abrirlo lleva unos milisegundos) por tandas, para que la ventana
        se abra enseguida y no se congele con miles de canciones. La primera tanda se lee en el acto."""
        batch = 200 if first else 40
        end = min(self.table.rowCount(), self._quality_next + batch)
        self.table.blockSignals(True)
        for row in range(self._quality_next, end):
            use = self.table.item(row, COL_USE)
            if use is None or not use.flags() & Qt.ItemFlag.ItemIsUserCheckable or self.table.item(row, COL_MP3).text() != "…":
                continue  # el archivo no se encuentra, ya se leyó o la fila ya se convirtió
            track = use.data(_TRACK)
            ext = os.path.splitext(track.path)[1].lstrip(".").upper()
            quality = audio_quality(track.path)
            lossy = is_lossy(track.path)
            now = f"{ext} {quality.kbps} kbps" if quality and quality.kbps else ext
            self.table.item(row, COL_NOW).setText(now + (" · ya comprimido" if lossy else ""))
            if lossy:
                self.table.item(row, COL_NOW).setToolTip(
                    "Ya está comprimido: pasarlo a MP3 es una segunda compresión (no mejora y puede perder algo de "
                    "calidad). Conviértelo solo si tu equipo no reproduce este formato."
                )
            self.table.item(row, COL_MP3).setText(f"MP3 {converter.target_bitrate(track.path, quality)} kbps")
            if quality:
                self.table.item(row, COL_SONG).setToolTip(f"{track.path}\n{ext} · {quality.text()}")
        self.table.blockSignals(False)
        self._quality_next = end
        if end < self.table.rowCount() and not self.runner.busy:
            QTimer.singleShot(0, self._fill_quality)

    def _show_list_or_empty(self) -> None:
        if self.table.rowCount():
            self.stack.setCurrentWidget(self.table)
        else:
            self._set_empty("Todo está en MP3", "No hay canciones de otros formatos para convertir.")
            self.stack.setCurrentWidget(self.empty)

    def _checked(self) -> list[tuple[int, Track]]:
        rows = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_USE)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable and item.checkState() == Qt.CheckState.Checked:
                rows.append((row, item.data(_TRACK)))
        return rows

    def _update_buttons(self, *_args) -> None:
        busy = self.runner.busy
        count = len(self._checked())
        self.btn_convert.setText(f"Convertir ({count})" if count else "Convertir")
        self.btn_convert.setEnabled(count > 0 and not busy)
        self.btn_history.setEnabled(not busy)

    # ------------------------------------------------------------------ convertir

    def _convert(self) -> None:
        checked = self._checked()
        if not checked:
            return
        tracks = [t for _, t in checked]
        session = converter.new_session(tracks, self._ops.db.known_path_keys())
        lossy = sum(1 for t in tracks if is_lossy(t.path))
        lossy_note = (
            f"{plural(lossy, 'canción ya está comprimida', 'canciones ya están comprimidas')} (WMA, AAC, OGG…): "
            "pasarlas a MP3 es una segunda compresión, que no mejora y puede perder algo de calidad.\n\n"
            if lossy else ""
        )
        while True:  # carpeta destino de los originales: la propuesta, o la que se elija
            choice = ask(
                self,
                "Convertir a MP3",
                f"¿Convertir {plural(len(tracks), 'canción', 'canciones')} a MP3?",
                [("Convertir", QMessageBox.ButtonRole.AcceptRole),
                 ("Elegir otra carpeta…", QMessageBox.ButtonRole.ActionRole),
                 ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
                QMessageBox.Icon.Question,
                f"{lossy_note}Los MP3 nuevos quedan junto a cada original. Los originales se guardarán en:\n"
                f"{session.originals_root}\n\nSe puede deshacer desde el Historial.",
            )
            if choice == 1:
                parent = QFileDialog.getExistingDirectory(self, "¿Dónde guardar los originales?",
                                                          os.path.dirname(session.originals_root))
                if parent:
                    session.originals_root = os.path.join(os.path.normpath(parent), converter.ORIGINALS_FOLDER_NAME)
                continue
            if choice != 0:
                return
            break
        if not self._ops.begin_conversion(session):
            return
        self.banner.clear()
        self._session = session
        self._rows = [row for row, _ in checked]
        self._ok = self._failed = 0
        self._done_rows: list[int] = []
        # Las etiquetas del MP3 nuevo llevan el texto original (no el «‹ ›» de pantalla).
        worker = converter.ConvertWorker(list(zip(session.items, self._ops.db.with_raw_text(tracks), strict=True)))
        worker.converted.connect(self._on_converted)  # método @Slot: se ejecuta en el hilo principal
        self.runner.start(worker, len(tracks), "Convirtiendo…", self._on_finished, label="Convirtiendo", modifies_files=True,
                          stop_question=StopQuestion("la conversión a MP3", "Seguir convirtiendo", "Detener la conversión",
                                                     "Las ya convertidas quedan convertidas (se pueden deshacer desde el Historial)."))

    @Slot(int, str)
    def _on_converted(self, index: int, error: str) -> None:
        item = self._session.items[index]
        row = self._rows[index]
        state = self.table.item(row, COL_STATE)
        problem = error
        if not problem:
            try:
                problem = self._ops.record_converted(item, self._session)
            except (sqlite3.Error, OSError) as exc:  # biblioteca bloqueada o disco lleno al anotarla
                problem = f"no se pudo anotar en la biblioteca ({exc})"
        if problem:
            self._failed += 1
            state.setText("No se convirtió")
            state.setToolTip(problem)
            state.setForeground(theme.qcolor("danger"))
            return
        self._ok += 1
        self._done_rows.append(row)
        state.setText("Convertida")
        state.setForeground(theme.qcolor("success"))
        self.table.item(row, COL_USE).setFlags(Qt.ItemFlag.ItemIsEnabled)

    def _on_finished(self, cancelled: bool) -> None:
        self._ops.finish_conversion(self._session)
        text = f"Se {'convirtió' if self._ok == 1 else 'convirtieron'} {plural(self._ok, 'canción', 'canciones')} a MP3."
        if self._failed:
            text += f" {plural(self._failed, 'no se pudo convertir', 'no se pudieron convertir')} (pasa el mouse por «Estado»)."
        if cancelled:
            text = "Conversión detenida. " + text
        # Operación terminada: las convertidas salen de la lista; quedan solo las pendientes o con error.
        self.table.blockSignals(True)
        for row in sorted(self._done_rows, reverse=True):
            self.table.removeRow(row)
        self.table.blockSignals(False)
        self.status.setText("")
        self.summary.setText(plural(self.table.rowCount(), "archivo pendiente", "archivos pendientes") if self.table.rowCount() else "")
        self._show_list_or_empty()
        self._quality_next = 0
        self._fill_quality()  # completar las que quedaron sin leer si la conversión empezó antes
        self.banner.show_result(text, ok=not self._failed)
        self._update_buttons()

    # ------------------------------------------------------------------ deshacer

    def _history(self) -> None:
        if self._open_history is not None:
            self._open_history()
            self.banner.clear()
            self.scan()

    def reject(self) -> None:
        if self.runner.request_close():
            super().reject()
