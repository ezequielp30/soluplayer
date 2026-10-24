"""Diálogo «Buscar datos en internet»: título, artista, álbum y carátula desde bases de datos de música."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models import Track
from ..online_job import CoverWorker, LookupWorker, Update
from ..online_lookup import SOURCES, Candidate, LookupResult, Query, needs_data
from ..utils import format_time, normalize_text
from . import theme
from .dialogs import note_label, tidy_table
from .worker_runner import WorkerRunner

SAFE_SCORE = 0.85  # a partir de aquí la coincidencia se marca sola
COL_USE, COL_CURRENT, COL_PROPOSAL, COL_SCORE = range(4)

def _same(track: Track, candidate: Candidate) -> bool:
    return (normalize_text(track.title), normalize_text(track.artist), normalize_text(track.album)) == (
        normalize_text(candidate.title),
        normalize_text(candidate.artist),
        normalize_text(candidate.album),
    )


def _label(candidate: Candidate) -> str:
    duration = f" · {format_time(candidate.duration_ms)}" if candidate.duration_ms else ""
    album = f" · {candidate.album}" if candidate.album else ""
    return f"{candidate.title} — {candidate.artist}{album}{duration}   [{candidate.source_name}]"


class OnlineLookupDialog(QDialog):
    def __init__(
        self,
        tracks: list[Track],
        sources: list[str],
        with_covers: bool,
        apply_updates: Callable[[list[Update]], str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Buscar datos en internet")
        self.resize(1080, 640)
        self._all_tracks = list(tracks)
        self._apply_updates = apply_updates
        self._results: dict[int, LookupResult] = {}
        self._rows: list[Track] = []
        self._errors: set[str] = set()
        single = len(tracks) == 1

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Busca el título, artista, álbum y carátula correctos en bases de datos de música. "
            "Elige la propuesta correcta en cada canción y pulsa «Aplicar marcadas»."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(note_label(
            "Solo se envían el título y el artista de cada canción. "
            "Los cambios se guardan en la biblioteca: tus archivos no se modifican."
        ))

        sources_row = QHBoxLayout()
        sources_row.addWidget(QLabel("<b>Bases de datos:</b>"))
        self.source_boxes: dict[str, QCheckBox] = {}
        for key, source in SOURCES.items():
            box = QCheckBox(source.name)
            box.setChecked(key in sources)
            box.setToolTip(source.description)
            box.toggled.connect(self._update_buttons)
            self.source_boxes[key] = box
            sources_row.addWidget(box)
        sources_row.addStretch(1)
        self.covers = QCheckBox("Actualizar también la carátula")
        self.covers.setChecked(with_covers)
        sources_row.addWidget(self.covers)
        layout.addLayout(sources_row)

        scope_row = QHBoxLayout()
        incomplete = sum(1 for t in tracks if needs_data(t))
        self.only_incomplete = QCheckBox(f"Solo canciones con datos incompletos ({incomplete} de {len(tracks)})")
        self.only_incomplete.setToolTip("Sin artista o álbum, o con un título que parece un nombre de archivo")
        self.only_incomplete.setVisible(not single)
        self.only_incomplete.toggled.connect(self._update_buttons)
        scope_row.addWidget(self.only_incomplete)

        # En modo de una sola canción se puede afinar la búsqueda a mano.
        self.query_title = QLineEdit()
        self.query_artist = QLineEdit()
        if single:
            query = Query.from_track(tracks[0])
            self.query_title.setText(query.title)
            self.query_artist.setText(query.artist or "")
            self.query_title.setPlaceholderText("Título")
            self.query_artist.setPlaceholderText("Artista (opcional)")
            scope_row.addWidget(QLabel("Buscar:"))
            scope_row.addWidget(self.query_title, 2)
            scope_row.addWidget(self.query_artist, 1)
            self.query_title.returnPressed.connect(self.start_search)
            self.query_artist.returnPressed.connect(self.start_search)
        else:
            scope_row.addStretch(1)
        self.btn_search = QPushButton("Buscar" if single else f"Buscar en todas ({len(tracks)})")
        self.btn_search.setObjectName("PrimaryButton")
        self.btn_search.clicked.connect(self.start_search)
        scope_row.addWidget(self.btn_search)
        layout.addLayout(scope_row)

        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(8)
        self.status = QLabel()
        self.status.setObjectName("EmptyMessage")
        self.btn_cancel = QPushButton("Detener búsqueda")
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.status, 2)
        progress_row.addWidget(self.btn_cancel)
        layout.addLayout(progress_row)
        self.runner = WorkerRunner(self, self.progress, self.status, self.btn_cancel)
        self.runner.busy_changed.connect(self._update_buttons)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "Canción en tu biblioteca", "Propuesta (elige la correcta)", "Coincidencia"])
        tidy_table(self.table)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(40)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_USE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_CURRENT, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_PROPOSAL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_SCORE, QHeaderView.ResizeMode.ResizeToContents)
        header.resizeSection(COL_CURRENT, 330)
        self.table.itemChanged.connect(lambda *_: self._update_buttons())
        layout.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.btn_safe = QPushButton(f"Marcar solo coincidencias seguras (≥ {int(SAFE_SCORE * 100)} %)")
        self.btn_safe.clicked.connect(self._mark_safe)
        self.btn_none = QPushButton("Desmarcar todas")
        self.btn_none.clicked.connect(lambda: self._set_all_checked(False))
        bottom.addWidget(self.btn_safe)
        bottom.addWidget(self.btn_none)
        bottom.addStretch(1)
        self.btn_apply = QPushButton("Aplicar marcadas")
        self.btn_apply.setObjectName("PrimaryButton")
        self.btn_apply.clicked.connect(self._apply)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.reject)
        bottom.addWidget(self.btn_apply)
        bottom.addWidget(close)
        layout.addLayout(bottom)

        self._update_buttons()
        if single:
            self.start_search()

    # ------------------------------------------------------------------ búsqueda

    def _sources(self) -> list[str]:
        return [key for key, box in self.source_boxes.items() if box.isChecked()]

    def _targets(self) -> list[Track]:
        if self.only_incomplete.isVisible() and self.only_incomplete.isChecked():
            return [t for t in self._all_tracks if needs_data(t)]
        return list(self._all_tracks)

    def start_search(self) -> None:
        if self.runner.busy:
            return
        sources = self._sources()
        if not sources:
            QMessageBox.information(self, "Elige una base de datos", "Marca al menos una base de datos para buscar.")
            return
        self._rows = self._targets()
        if not self._rows:
            self.status.setText("No hay canciones que buscar con estas opciones.")
            return
        if len(self._all_tracks) == 1:  # modo de una sola canción (con los campos de búsqueda)
            title = " ".join(self.query_title.text().split()) or self._rows[0].title
            artist = " ".join(self.query_artist.text().split()) or None
            queries = [Query(title, artist, self._rows[0].duration_ms)]
        else:
            queries = [Query.from_track(t) for t in self._rows]
        self._results.clear()
        self._errors.clear()
        self._fill_rows()

        estimate = len(queries) * max(SOURCES[s].min_interval_s for s in sources)
        worker = LookupWorker(queries, sources)
        worker.found.connect(self._on_found)  # método con @Slot: se ejecuta en el hilo principal
        self.runner.start(
            worker, len(queries),
            f"Buscando… (≈ {max(1, round(estimate / 60))} min)" if estimate > 90 else "Buscando…",
            self._on_search_finished, label="Buscando",
        )

    @Slot(int, object)
    def _on_found(self, index: int, result: LookupResult) -> None:
        self._results[index] = result
        self._errors.update(result.errors)
        self._fill_proposal(index, result)
        self._update_buttons()

    def _on_search_finished(self, cancelled: bool) -> None:
        found = sum(1 for r in self._results.values() if r.candidates)
        text = f"{'Búsqueda detenida. ' if cancelled else ''}Se encontraron datos para {found} de {len(self._rows)}."
        if self._errors:
            text += "  Avisos: " + " ".join(sorted(self._errors))
        self.status.setText(text)
        self._update_buttons()

    # ------------------------------------------------------------------ tabla

    def _fill_rows(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._rows))
        for row, track in enumerate(self._rows):
            use = QTableWidgetItem()
            use.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            use.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row, COL_USE, use)
            current = QTableWidgetItem(f"{track.title} — {track.artist}")
            current.setToolTip(f"{track.title}\n{track.artist} — {track.album}\n{track.path}")
            self.table.setItem(row, COL_CURRENT, current)
            pending = QTableWidgetItem("Buscando…")
            pending.setForeground(theme.qcolor("muted"))
            self.table.setItem(row, COL_PROPOSAL, pending)
            self.table.setCellWidget(row, COL_PROPOSAL, None)
            self.table.setItem(row, COL_SCORE, QTableWidgetItem(""))
        self.table.blockSignals(False)

    def _fill_proposal(self, row: int, result: LookupResult) -> None:
        track = self._rows[row]
        self.table.blockSignals(True)
        if not result.candidates:
            item = self.table.item(row, COL_PROPOSAL)
            item.setText("Sin resultados" + (" (error de conexión)" if result.errors else ""))
            item.setToolTip("\n".join(result.errors) or "Prueba con otra base de datos o corrige el título y el artista.")
            self.table.item(row, COL_USE).setFlags(Qt.ItemFlag.NoItemFlags)
            self.table.blockSignals(False)
            return
        combo = QComboBox()
        combo.addItem("(No cambiar)", None)
        for candidate in result.candidates:
            combo.addItem(_label(candidate), candidate)
        combo.setCurrentIndex(1)
        combo.setToolTip("Elige la versión correcta; «(No cambiar)» deja la canción como está")
        combo.currentIndexChanged.connect(lambda _i, r=row: self._on_choice_changed(r))
        self.table.setItem(row, COL_PROPOSAL, QTableWidgetItem(""))
        self.table.setCellWidget(row, COL_PROPOSAL, combo)
        best = result.best
        if _same(track, best):
            self.table.item(row, COL_SCORE).setText("Ya es correcta")
            self.table.item(row, COL_USE).setCheckState(Qt.CheckState.Unchecked)
        else:
            self.table.item(row, COL_USE).setCheckState(
                Qt.CheckState.Checked if best.score >= SAFE_SCORE else Qt.CheckState.Unchecked
            )
        self.table.blockSignals(False)
        self._on_choice_changed(row, keep_check=True)

    def _on_choice_changed(self, row: int, keep_check: bool = False) -> None:
        combo = self.table.cellWidget(row, COL_PROPOSAL)
        if not isinstance(combo, QComboBox):
            return
        candidate: Candidate | None = combo.currentData()
        score_item = self.table.item(row, COL_SCORE)
        use = self.table.item(row, COL_USE)
        self.table.blockSignals(True)
        if candidate is None:
            score_item.setText("—")
            use.setCheckState(Qt.CheckState.Unchecked)
        else:
            if not (keep_check and score_item.text() == "Ya es correcta"):
                score_item.setText(f"{round(candidate.score * 100)} %")
            role = "success" if candidate.score >= SAFE_SCORE else ("accent_text" if candidate.score >= 0.6 else "danger")
            score_item.setForeground(theme.qcolor(role))
            if not keep_check:
                use.setCheckState(Qt.CheckState.Checked)  # elegir una propuesta la marca
        self.table.blockSignals(False)
        self._update_buttons()

    def _chosen(self) -> list[tuple[Track, Candidate]]:
        chosen = []
        for row, track in enumerate(self._rows):
            use = self.table.item(row, COL_USE)
            combo = self.table.cellWidget(row, COL_PROPOSAL)
            if use and use.checkState() == Qt.CheckState.Checked and isinstance(combo, QComboBox):
                candidate = combo.currentData()
                if candidate is not None:
                    chosen.append((track, candidate))
        return chosen

    def _mark_safe(self) -> None:
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            if not self.table.item(row, COL_USE).flags() & Qt.ItemFlag.ItemIsUserCheckable:
                continue  # ya aplicada o sin resultados
            combo = self.table.cellWidget(row, COL_PROPOSAL)
            candidate = combo.currentData() if isinstance(combo, QComboBox) else None
            safe = candidate is not None and candidate.score >= SAFE_SCORE and not _same(self._rows[row], candidate)
            self.table.item(row, COL_USE).setCheckState(Qt.CheckState.Checked if safe else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._update_buttons()

    def _set_all_checked(self, checked: bool) -> None:
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_USE)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._update_buttons()

    def _update_buttons(self, *_args) -> None:
        busy = self.runner.busy
        count = len(self._chosen()) if self._rows else 0
        self.btn_apply.setText(f"Aplicar marcadas ({count})")
        self.btn_apply.setEnabled(count > 0 and not busy)
        self.btn_search.setEnabled(not busy and bool(self._sources()))
        if len(self._all_tracks) > 1:
            self.btn_search.setText(f"Buscar en todas ({len(self._targets())})")
        self.btn_safe.setEnabled(not busy and bool(self._results))
        self.btn_none.setEnabled(not busy and bool(self._results))
        for box in self.source_boxes.values():
            box.setEnabled(not busy)
        self.only_incomplete.setEnabled(not busy)

    # ------------------------------------------------------------------ aplicar

    def _apply(self) -> None:
        chosen = self._chosen()
        if not chosen:
            return
        worker = CoverWorker(chosen, self.covers.isChecked())
        # Al cerrar o pulsar «Detener» se dejan de bajar carátulas, pero lo elegido se guarda igual.
        self.runner.start(
            worker, len(chosen), "Descargando carátulas…" if self.covers.isChecked() else "Guardando…",
            self._on_covers_ready,
        )

    def _on_covers_ready(self, updates: list[Update]) -> None:
        message = self._apply_updates(updates)
        applied = {track.id: candidate for track, candidate, _cover in updates}
        # Las canciones de esta ventana pasan a tener los datos nuevos (si no, una búsqueda nueva o
        # «Marcar seguras» las compararían con los datos viejos y las volverían a proponer).
        def refreshed(track: Track) -> Track:
            candidate = applied.get(track.id)
            if candidate is None:
                return track
            new = track.copy()
            new.title = candidate.title.strip() or track.title
            new.artist = candidate.artist.strip() or track.artist
            new.album = candidate.album.strip() or track.album
            return new

        self._rows = [refreshed(t) for t in self._rows]
        self._all_tracks = [refreshed(t) for t in self._all_tracks]
        # Las filas aplicadas quedan como «Actualizada» y sin marcar.
        self.table.blockSignals(True)
        for row, track in enumerate(self._rows):
            if track.id in applied:
                use = self.table.item(row, COL_USE)
                use.setCheckState(Qt.CheckState.Unchecked)
                use.setFlags(Qt.ItemFlag.NoItemFlags)
                self.table.item(row, COL_SCORE).setText("Actualizada")
                self.table.item(row, COL_SCORE).setForeground(theme.qcolor("success"))
                combo = self.table.cellWidget(row, COL_PROPOSAL)
                if combo is not None:
                    combo.setEnabled(False)
        self.table.blockSignals(False)
        self.status.setText(message)
        self._update_buttons()

    def reject(self) -> None:
        if self.runner.request_close(wait_ms=15000):
            super().reject()
