"""La ventanita de «Localizar archivo»: busca en otro hilo, y la música y la ventana siguen respondiendo."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from ..file_locator import FindFileWorker, search_tiers
from ..models import Track
from .worker_runner import WorkerRunner


class LocateDialog(QDialog):
    """Al terminar, `found` tiene las rutas encontradas y `stopped` dice si se detuvo antes de acabar."""

    def __init__(self, track: Track, library: list[Track], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Localizar archivo")
        self.setMinimumWidth(520)
        self.found: list[str] = []
        self.stopped = False
        self._track, self._library = track, library

        title = QLabel(f"Buscando «{track.title}»…")
        title.setWordWrap(True)
        title.setTextFormat(Qt.TextFormat.PlainText)
        self.where = QLabel("")
        self.where.setTextFormat(Qt.TextFormat.PlainText)
        self.bar = QProgressBar()
        self.btn_stop = QPushButton("Detener")
        self.btn_stop.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.btn_stop)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.bar)
        layout.addWidget(self.where)
        layout.addLayout(buttons)
        self.runner = WorkerRunner(self, self.bar, QLabel(self))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self.runner.busy and not self.found and not self.stopped:
            worker = FindFileWorker(self._track, self._library, search_tiers(self._track, self._library))
            worker.folder.connect(self._show_folder)
            self.runner.start(worker, 0, "", self._on_finished)

    def _show_folder(self, folder: str) -> None:
        metrics = self.where.fontMetrics()
        self.where.setText(metrics.elidedText(folder, Qt.TextElideMode.ElideMiddle, max(100, self.where.width())))

    def _on_finished(self, found: list, stopped: bool) -> None:
        self.found, self.stopped = found, stopped
        self.accept()

    def reject(self) -> None:
        """Detener o Esc: lo encontrado hasta ahora sirve. Se cierra cuando el hilo avise."""
        if self.runner.busy:
            self.runner.stop()
            self.btn_stop.setEnabled(False)
            self.where.setText("Deteniendo…")
            return
        super().reject()
