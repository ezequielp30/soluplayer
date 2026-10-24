"""Ejecuta un trabajador en su propio hilo: barra de progreso, texto de estado, botón «Detener» y cierre seguro.

Antes cada herramienta (convertir, volumen, datos en internet, repetidas) repetía esta lógica a su manera.
El trabajador es un QObject con un método `run()` y una señal `finished` (con o sin argumentos); si además
tiene la señal `progress(índice, total[, título])` y el método `cancel()`, se usan.

Reglas:
- Lo que hace el trabajador ocurre en su hilo; todo lo que toca la interfaz o la biblioteca, en el principal.
- Mientras un trabajador modifica archivos, la ventana no se puede cerrar (quedarían a medias).
- Si un trabajador que solo lee no se detiene a tiempo (p. ej. un archivo dañado que bloquea el
  decodificador), la ventana se cierra igual y el hilo termina por su cuenta, sin que Qt lo destruya en marcha.
"""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QCoreApplication, QObject, Qt, QThread, Signal
from PySide6.QtWidgets import QLabel, QMessageBox, QProgressBar, QPushButton, QWidget

log = logging.getLogger(__name__)

# Hilos que siguen terminando después de cerrar su ventana: la referencia evita que se destruyan en marcha.
_orphans: set[QThread] = set()


def keep_alive(thread: QThread) -> None:
    """Conserva un hilo que todavía no terminó (se descarta solo al terminar)."""
    _orphans.add(thread)
    thread.finished.connect(lambda: _orphans.discard(thread))


def wait_pending(timeout_ms: int = 5000) -> bool:
    """Al salir del programa: espera a los hilos pendientes. False si alguno sigue en marcha (entonces
    no se puede dejar que Python destruya su QThread: Qt abortaría el proceso)."""
    deadline_ok = True
    for thread in list(_orphans):
        try:
            if thread.isRunning() and not thread.wait(timeout_ms):
                deadline_ok = False
        except RuntimeError:  # el objeto de Qt ya no existe: terminó
            pass
    return deadline_ok


class WorkerRunner(QObject):
    busy_changed = Signal(bool)

    def __init__(
        self,
        parent: QWidget,
        progress: QProgressBar,
        status: QLabel,
        stop_button: QPushButton | None = None,
    ) -> None:
        super().__init__(parent)
        self._window = parent
        self.progress = progress
        self.status = status
        self.stop_button = stop_button
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._on_finished: Callable | None = None
        self._label = ""
        self._modifies_files = False
        progress.hide()
        if stop_button is not None:
            stop_button.hide()
            stop_button.clicked.connect(self.stop)

    @property
    def busy(self) -> bool:
        return self._thread is not None

    @property
    def worker(self) -> QObject | None:
        return self._worker

    def start(
        self,
        worker: QObject,
        total: int,
        text: str,
        on_finished: Callable | None = None,
        *,
        label: str = "",
        modifies_files: bool = False,
    ) -> None:
        """`label` («Convirtiendo», «Analizando»…) arma el estado «Convirtiendo 3 de 40: título».
        `on_finished` recibe los argumentos de la señal `finished` del trabajador, ya en el hilo principal."""
        if self.busy:
            raise RuntimeError("Ya hay una tarea en marcha")
        thread = QThread()  # sin padre: su vida la controla este objeto (ver request_close)
        self._thread, self._worker = thread, worker
        self._on_finished = on_finished
        self._label = label
        self._modifies_files = modifies_files
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # El hilo acaba solo, aunque la ventana ya no exista. Conexión directa (quit es seguro entre hilos):
        # en cola, esperaría al hilo principal, que puede estar bloqueado justo en wait().
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        if hasattr(worker, "progress"):
            worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_worker_finished)
        self.progress.setRange(0, max(0, total))
        self.progress.setValue(0)
        self.progress.show()
        if self.stop_button is not None:
            self.stop_button.setVisible(hasattr(worker, "cancel"))
            self.stop_button.setEnabled(True)
        self.status.setText(text)
        thread.start()
        self.busy_changed.emit(True)

    # Métodos (no funciones sueltas) conectados a señales del trabajador: Qt los ejecuta en el hilo
    # de este objeto, el principal.
    def _on_progress(self, index: int, total: int, title: str = "") -> None:
        if total and self.progress.maximum() != total:
            self.progress.setMaximum(total)
        self.progress.setValue(index)
        if title and self._label:
            self.status.setText(f"{self._label} {index + 1} de {total}: {title}")

    def _on_worker_finished(self, *args) -> None:
        if self._thread is None:
            return
        self._thread.wait()  # ya recibió quit(): termina enseguida
        callback = self._release()
        if callback is not None:
            callback(*args)

    def _release(self) -> Callable | None:
        callback = self._on_finished
        self._thread = self._worker = None
        self._on_finished = None
        self.progress.hide()
        if self.stop_button is not None:
            self.stop_button.hide()
        self.busy_changed.emit(False)
        return callback

    def stop(self) -> None:
        worker = self._worker
        if worker is not None and hasattr(worker, "cancel"):
            worker.cancel()
            if self.stop_button is not None:
                self.stop_button.setEnabled(False)
            self.status.setText("Deteniendo…")

    def request_close(self, wait_ms: int = 8000) -> bool:
        """Llamar al cerrar la ventana. Devuelve False si no se debe cerrar todavía."""
        if self._thread is None:
            return True
        if self._modifies_files:
            QMessageBox.information(
                self._window, "Espera",
                "Se están modificando archivos: espera a que termine"
                + (" o pulsa «Detener»." if self.stop_button is not None and self.stop_button.isVisible() else "."),
            )
            return False
        self.stop()
        thread = self._thread
        if thread.wait(wait_ms):
            # Entrega lo que el trabajador dejó en cola (resultados y «terminado») antes de cerrar.
            QCoreApplication.sendPostedEvents(self._window, 0)
            QCoreApplication.sendPostedEvents(self, 0)
            if self._thread is not None:
                self._release()
            return True
        log.warning("Una tarea no se detuvo a tiempo; la ventana se cierra y la tarea termina por su cuenta")
        keep_alive(thread)
        try:
            self._worker.finished.disconnect(self._on_worker_finished)
        except (RuntimeError, TypeError):
            pass
        self._release()
        return True
