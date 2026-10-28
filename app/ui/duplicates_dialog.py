"""Diálogo para buscar y resolver canciones repetidas.

Ventana compacta (como los resultados agrupados de dupeGuru): una línea de explicación con el detalle en
«?», pocas columnas (la ruta completa va en el tooltip) y el resultado de cada acción en una franja; al
terminar una acción se vuelve a buscar, así la lista queda limpia.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..duplicates import MODE_CONTENT, MODE_METADATA, DuplicateGroup, file_size
from ..duplicates_job import FindDuplicatesWorker
from ..metadata import Quality
from ..models import Track
from ..utils import format_time, plural
from . import theme
from .dialogs import ResultBanner, StatusLabel, ask, empty_state, tool_intro
from .worker_runner import StopQuestion, WorkerRunner

# (id de la copia que se conserva, copias a quitar)
Plan = list[tuple[int, list[Track]]]

_TRACK_ROLE = Qt.ItemDataRole.UserRole
COL_ACTION, COL_TITLE, COL_ARTIST, COL_DURATION, COL_QUALITY, COL_FOLDER = range(6)

_DETAILS = (
    "Busca la misma canción importada más de una vez. En cada grupo se propone conservar una copia (la "
    "disponible de mayor tamaño) y se marcan las demás.\n"
    "• Quitar de la biblioteca: los archivos se quedan en el disco.\n"
    "• Papelera: los archivos van a la Papelera de Windows (se pueden recuperar).\n"
    "• Reunir para revisar: pone todas las copias de cada canción juntas en una carpeta para escucharlas "
    "(se puede deshacer en el Historial).\n"
    "Las playlists pasan a usar la copia que conservas."
)


def _size_text(track: Track) -> str:
    size = file_size(track)
    return f"{size / 1_048_576:.1f} MB" if size else ""


class DuplicatesDialog(QDialog):
    COLUMNS = ("Acción", "Título", "Artista", "Duración", "Calidad", "Carpeta")

    def __init__(
        self,
        tracks_provider: Callable[[], list[Track]],
        apply_plan: Callable[[Plan, bool], str],
        parent: QWidget | None = None,
        gather: Callable[[list[DuplicateGroup]], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Canciones repetidas")
        self.resize(820, 500)
        self._tracks_provider = tracks_provider
        self._apply_plan = apply_plan
        self._gather = gather
        self._groups: list[DuplicateGroup] = []
        self._qualities: dict[int, Quality | None] = {}
        self._updating = False

        layout = QVBoxLayout(self)
        layout.addWidget(tool_intro("Encuentra la misma canción importada más de una vez y deja una sola copia.", _DETAILS))
        self.banner = ResultBanner()
        layout.addWidget(self.banner)

        row = QHBoxLayout()
        row.addWidget(QLabel("Criterio:"))
        self.mode = QComboBox()
        self.mode.addItem("Mismo título y artista", MODE_METADATA)
        self.mode.addItem("Archivos idénticos (más lento)", MODE_CONTENT)
        self.mode.setToolTip("Mismo título y artista: también exige una duración parecida")
        row.addWidget(self.mode)
        row.addStretch(1)
        self.btn_search = QPushButton("Buscar")
        self.btn_search.setObjectName("PrimaryButton")
        self.btn_search.clicked.connect(self._new_search)
        row.addWidget(self.btn_search)
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
        self.runner.busy_changed.connect(self._update_summary)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(self.COLUMNS)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        header = self.tree.header()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in ((COL_ACTION, 150), (COL_TITLE, 170), (COL_ARTIST, 140), (COL_DURATION, 70), (COL_QUALITY, 150)):
            header.resizeSection(col, width)
        header.setStretchLastSection(True)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.empty, self._set_empty = empty_state()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.tree)
        self.stack.addWidget(self.empty)
        layout.addWidget(self.stack, 1)

        self.summary = QLabel()
        self.summary.setObjectName("DialogNote")
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        self.btn_suggested = QPushButton("Restaurar sugerencia")
        self.btn_suggested.setToolTip("Vuelve a marcar todas las copias menos la sugerida para conservar")
        self.btn_suggested.clicked.connect(self._apply_suggestion)
        buttons.addWidget(self.btn_suggested)
        self.btn_gather = QPushButton("Reunir para revisar…")
        self.btn_gather.setToolTip(
            "Mueve todas las copias de cada canción repetida a una subcarpeta con su nombre, para escucharlas "
            "y compararlas. Se puede deshacer en Herramientas → Historial de cambios en archivos."
        )
        self.btn_gather.clicked.connect(self._on_gather)
        self.btn_gather.setVisible(gather is not None)
        buttons.addWidget(self.btn_gather)
        buttons.addStretch(1)
        self.btn_remove = QPushButton("Quitar de la biblioteca")
        self.btn_remove.setToolTip("Quita las copias marcadas de la biblioteca; los archivos se quedan en el disco")
        self.btn_remove.clicked.connect(lambda: self._apply(trash=False))
        self.btn_trash = QPushButton("A la Papelera…")
        self.btn_trash.setObjectName("DangerButton")  # se distingue de «Quitar de la biblioteca»: borra archivos
        self.btn_trash.setToolTip("Quita las copias marcadas y envía sus archivos a la Papelera de reciclaje")
        self.btn_trash.clicked.connect(lambda: self._apply(trash=True))
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        for button in (self.btn_remove, self.btn_trash, close):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.search()

    # ------------------------------------------------------------------ búsqueda

    def _new_search(self) -> None:
        self.banner.clear()  # el resultado de la acción anterior ya no corresponde
        self.search()

    def search(self) -> None:
        """Busca en un hilo aparte (comparar contenido y leer la calidad de cada copia lleva tiempo)."""
        if self.runner.busy:
            return
        mode = self.mode.currentData()
        text = "Comparando el contenido de los archivos…" if mode == MODE_CONTENT else "Buscando canciones repetidas…"
        self.runner.start(FindDuplicatesWorker(self._tracks_provider(), mode), 0, text, self._on_found,
                          stop_question=StopQuestion("la búsqueda de canciones repetidas", "Seguir buscando",
                                                     "Detener la búsqueda", "No se modificó ningún archivo."))

    def _on_found(self, groups, qualities, error: str) -> None:
        if groups is None:
            # Los resultados anteriores pueden estar desactualizados (p. ej. tras reunir, las rutas
            # cambiaron): se quitan para que no se pueda actuar sobre ellos.
            self._groups = []
            self._qualities = {}
            self._updating = True
            self.tree.clear()
            self._updating = False
            self.status.setText(f"No se pudo buscar: {error}" if error else "Búsqueda detenida: vuelve a pulsar «Buscar».")
            self._update_summary()
            return
        self.status.setText("")
        self._groups = groups
        self._qualities = qualities
        self._fill_tree()

    def _fill_tree(self) -> None:
        self._updating = True
        self.tree.clear()
        bold = QFont()
        bold.setBold(True)
        for index, group in enumerate(self._groups):
            first = group.keep
            parent = QTreeWidgetItem([f"{first.title} — {first.artist}  ·  {len(group.tracks)} copias"])
            parent.setFont(0, bold)
            parent.setFlags(Qt.ItemFlag.ItemIsEnabled)
            parent.setData(0, _TRACK_ROLE, index)
            self.tree.addTopLevelItem(parent)
            parent.setFirstColumnSpanned(True)
            for track in group.tracks:
                quality = self._qualities.get(track.id)
                size = _size_text(track)
                short = f"{quality.codec} {quality.kbps} kbps" if quality and quality.kbps else (quality.codec if quality else "")
                quality_text = " · ".join(x for x in (short, size) if x) or "—"
                folder = os.path.basename(os.path.dirname(track.path)) or track.path
                child = QTreeWidgetItem(
                    [
                        "",
                        track.title,
                        track.artist,
                        format_time(track.duration_ms) if track.duration_ms else "—",
                        quality_text,
                        folder if track.available else f"(no encontrado) {folder}",
                    ]
                )
                child.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
                child.setData(0, _TRACK_ROLE, track)
                tip = f"{track.path}\nÁlbum: {track.album}"
                for col in (COL_TITLE, COL_FOLDER):
                    child.setToolTip(col, tip)
                if quality:
                    child.setToolTip(COL_QUALITY, f"{quality.codec} · {quality.text()}" + (f" · {size}" if size else ""))
                child.setCheckState(0, Qt.CheckState.Unchecked if track.id == group.keep_id else Qt.CheckState.Checked)
                parent.addChild(child)
                self._style_child(child)
            parent.setExpanded(True)
        self._updating = False
        self._update_summary()

    def _apply_suggestion(self) -> None:
        self._updating = True
        for index, group in enumerate(self._groups):
            parent = self.tree.topLevelItem(index)
            for i in range(parent.childCount()):
                child = parent.child(i)
                track = child.data(0, _TRACK_ROLE)
                child.setCheckState(0, Qt.CheckState.Unchecked if track.id == group.keep_id else Qt.CheckState.Checked)
                self._style_child(child)
        self._updating = False
        self._update_summary()

    # ------------------------------------------------------------------ estado

    @staticmethod
    def _style_child(child: QTreeWidgetItem) -> None:
        remove = child.checkState(0) == Qt.CheckState.Checked
        child.setText(0, "Quitar" if remove else "Conservar")
        child.setForeground(0, theme.qcolor("danger" if remove else "success"))

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating or column != 0 or item.parent() is None:
            return
        self._updating = True
        self._style_child(item)
        self._updating = False
        self._update_summary()

    def _marked(self) -> int:
        return sum(len(remove) for _, remove in self._plan_raw())

    def _update_summary(self, *_args) -> None:
        busy = self.runner.busy
        marked = self._marked()
        if busy or not self._groups:
            self.summary.setText("")
            if not busy:
                self._set_empty("No hay canciones repetidas", "Puedes probar con el otro criterio de búsqueda.")
                self.stack.setCurrentWidget(self.empty)
        else:
            copies = sum(len(g.tracks) for g in self._groups)
            self.summary.setText(
                f"{plural(len(self._groups), 'canción repetida', 'canciones repetidas')} · {copies} copias · "
                f"marcadas para quitar: {marked}"
            )
            self.stack.setCurrentWidget(self.tree)
        has = marked > 0 and not busy
        self.btn_remove.setEnabled(has)
        self.btn_trash.setEnabled(has)
        self.btn_remove.setText(f"Quitar de la biblioteca ({marked})" if has else "Quitar de la biblioteca")
        self.btn_suggested.setEnabled(bool(self._groups) and not busy)
        self.btn_gather.setEnabled(bool(self._groups) and not busy)
        self.btn_search.setEnabled(not busy)
        self.mode.setEnabled(not busy)

    def _plan_raw(self) -> list[tuple[list[Track], list[Track]]]:
        """Por grupo: (copias conservadas, copias marcadas para quitar)."""
        plan = []
        for index in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(index)
            keep, remove = [], []
            for i in range(parent.childCount()):
                child = parent.child(i)
                (remove if child.checkState(0) == Qt.CheckState.Checked else keep).append(child.data(0, _TRACK_ROLE))
            plan.append((keep, remove))
        return plan

    # ------------------------------------------------------------------ aplicar

    def _on_gather(self) -> None:
        if not self._groups or self._gather is None:
            return
        message = self._gather(list(self._groups))
        if message:
            self.banner.show_result(message)
            self.search()  # las rutas cambiaron: la lista se rehace

    def _apply(self, trash: bool) -> None:
        plan: Plan = []
        for index, (keep, remove) in enumerate(self._plan_raw()):
            if not remove:
                continue
            if not keep:
                group = self._groups[index]
                QMessageBox.warning(
                    self,
                    "Deja al menos una copia",
                    f"En «{group.keep.title}» marcaste todas las copias para quitar.\n\n"
                    "Desmarca al menos una para conservarla.",
                )
                return
            suggested = self._groups[index].keep_id
            keep_id = suggested if any(t.id == suggested for t in keep) else keep[0].id
            plan.append((keep_id, remove))
        count = sum(len(remove) for _, remove in plan)
        if not count:
            return
        if trash:
            text = f"¿Enviar {plural(count, 'copia', 'copias')} a la Papelera de reciclaje?"
            info = "Se podrán recuperar desde la Papelera de Windows. Las playlists usarán la copia conservada."
            confirm = "Enviar a la papelera"
        else:
            text = f"¿Quitar {plural(count, 'copia', 'copias')} de la biblioteca?"
            info = "Los archivos NO se borran del disco. Las playlists usarán la copia conservada."
            confirm = "Quitar"
        choice = ask(
            self,
            "Canciones repetidas",
            text,
            [(confirm, QMessageBox.ButtonRole.DestructiveRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Warning,
            info,
        )
        if choice != 0:
            return
        try:
            message = self._apply_plan(plan, trash)
        except (sqlite3.Error, OSError) as exc:
            message = f"No se pudo completar: {exc}. Vuelve a buscar antes de intentarlo de nuevo."
        if message:
            self.banner.show_result(message, ok="no se pud" not in message.lower())
        self.search()  # operación terminada: la lista se rehace sin lo que ya se resolvió

    def reject(self) -> None:
        if self.runner.request_close():
            super().reject()

    def accept(self) -> None:
        if self.runner.request_close():
            super().accept()
