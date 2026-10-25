"""Una sola copia abierta: si el programa ya está abierto, la segunda le pasa los archivos y se cierra.

Así, «Abrir con» o un doble clic en una canción la reproducen en la ventana existente en vez de
abrir otra copia que competiría por la misma biblioteca.

Cómo se garantiza:
- Un cerrojo de archivo (QLockFile) en la carpeta de datos, tomado al primer instante. Solo la copia que
  lo tiene abre la biblioteca. Si una copia anterior se cerró de golpe, Qt detecta que su proceso ya no
  existe y libera el cerrojo.
- Si el cerrojo está ocupado, se le envían los archivos a la copia abierta; si todavía está arrancando
  (p. ej. Windows lanzó una copia por cada archivo seleccionado), se reintenta unos segundos.
- La copia principal escucha desde el arranque y guarda lo que llegue hasta que la ventana esté lista;
  junta los archivos que llegan casi a la vez y espera si hay una ventana modal (una operación en curso).
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Callable

from PySide6.QtCore import QLockFile, QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .config import data_dir

log = logging.getLogger(__name__)

_TIMEOUT_MS = 1500
_END = "\x04"  # fin del mensaje: así no depende de cuándo se desconecta la otra copia
_MAX_MESSAGE = 4 * 1024 * 1024  # miles de rutas caben de sobra; más que esto no es otra copia del programa
_SHOW = "\x00mostrar"
_BATCH_MS = 350  # archivos que llegan casi a la vez (un proceso por archivo) se juntan en una sola cola
_MODAL_RETRY_MS = 500


def _server_name() -> str:
    # Una por usuario y por carpeta de datos (las pruebas con otra carpeta no chocan con la real).
    key = f"{os.environ.get('USERNAME', '')}|{data_dir()}".encode("utf-8")
    return "ReproductorMusica-" + hashlib.sha1(key).hexdigest()[:16]


def send_to_running(paths: list[str]) -> bool:
    """Si ya hay una copia escuchando, le envía los archivos (o solo «mostrar») y devuelve True."""
    socket = QLocalSocket()
    socket.connectToServer(_server_name())
    if not socket.waitForConnected(_TIMEOUT_MS):
        return False
    socket.write((("\n".join(paths) or _SHOW) + _END).encode("utf-8"))
    socket.flush()
    ok = socket.waitForBytesWritten(_TIMEOUT_MS) or socket.bytesToWrite() == 0
    socket.disconnectFromServer()
    return ok


def acquire_or_forward(paths: list[str], wait_seconds: float = 12.0) -> QLockFile | None:
    """Devuelve el cerrojo (esta copia es la principal) o None si los archivos se entregaron a la copia
    abierta. Lanza TimeoutError si hay otra copia pero no responde."""
    lock = QLockFile(str(data_dir() / "programa.lock"))
    lock.setStaleLockTime(0)  # no caduca por tiempo; solo si su proceso ya no existe
    deadline = time.monotonic() + wait_seconds
    while True:
        if lock.tryLock(0):
            return lock
        if send_to_running(paths):
            return None
        if time.monotonic() > deadline:
            raise TimeoutError("El programa ya está abierto pero no responde.")
        time.sleep(0.2)  # la otra copia todavía está arrancando


class InstanceServer(QObject):
    """Escucha a las copias nuevas y entrega sus archivos a `on_paths` (cuando se asigna)."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._on_paths: Callable[[list[str]], None] | None = None
        self._pending: list[str] = []
        self._show_requested = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._deliver)
        self._server = QLocalServer(self)
        QLocalServer.removeServer(_server_name())  # restos de un cierre inesperado (tenemos el cerrojo)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self._server.listen(_server_name()):
            log.warning("No se pudo escuchar a otras copias: %s", self._server.errorString())
        self._server.newConnection.connect(self._accept)

    def close(self) -> None:
        """Deja de recibir archivos (al cerrar el programa): una copia nueva espera a que este termine
        y los abre ella, en vez de entregárselos a una ventana que ya se cerró."""
        self._server.close()
        self._timer.stop()

    def set_handler(self, on_paths: Callable[[list[str]], None]) -> None:
        self._on_paths = on_paths
        if self._pending or self._show_requested:
            self._timer.start(0)

    def enqueue(self, paths: list[str]) -> None:
        """Archivos para abrir (los recibidos o los de la propia línea de órdenes). Se juntan un momento."""
        if paths:
            self._pending.extend(p for p in paths if p not in self._pending)
        else:
            self._show_requested = True
        self._timer.start(_BATCH_MS)

    def _accept(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            state = {"buffer": bytearray(), "done": False}

            def read(s=socket, st=state) -> None:
                if st["done"]:
                    return
                st["buffer"].extend(bytes(s.readAll()))
                if len(st["buffer"]) > _MAX_MESSAGE:
                    st["done"] = True
                    log.warning("Mensaje de otra copia demasiado grande: se descarta")
                    s.abort()
                    s.deleteLater()
                    return
                if st["buffer"].endswith(_END.encode()) or s.state() == QLocalSocket.LocalSocketState.UnconnectedState:
                    st["done"] = True
                    self._finish(s, bytes(st["buffer"]))

            socket.readyRead.connect(read)
            socket.disconnected.connect(read)
            read()  # puede que todo haya llegado (y la otra copia se haya ido) antes de atenderla

    def _finish(self, socket: QLocalSocket, raw: bytes) -> None:
        socket.deleteLater()
        data = raw.decode("utf-8", errors="replace").rstrip(_END)
        if not data:
            return
        self.enqueue([] if data == _SHOW else [p for p in data.split("\n") if p])

    def _deliver(self) -> None:
        if self._on_paths is None:
            return  # la ventana todavía no está lista: se entrega en set_handler
        if QApplication.activeModalWidget() is not None:
            # Hay un diálogo o una operación sobre archivos en curso: reproducir ahora podría bloquear
            # un archivo que se está moviendo o reescribiendo. Se espera a que termine.
            self._timer.start(_MODAL_RETRY_MS)
            return
        paths, self._pending, self._show_requested = self._pending, [], False
        self._on_paths(paths)
