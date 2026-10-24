"""Decodificación de un archivo completo con el motor del programa (FFmpeg vía Qt), con vigilancia.

Un archivo dañado puede dejar al decodificador sin decir nunca «terminé» ni «error»: sin vigilancia,
el análisis de volumen o la conversión se quedarían esperando para siempre. Aquí, si pasan
`stall_seconds` sin recibir audio, se abandona ese archivo con un error claro.
"""

from __future__ import annotations

import time
from typing import Callable

import shiboken6
from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtMultimedia import QAudioBuffer, QAudioDecoder, QAudioFormat

STALL_SECONDS = 20.0


def decode_file(
    path: str,
    fmt: QAudioFormat,
    on_buffer: Callable[[QAudioBuffer], None],
    stall_seconds: float = STALL_SECONDS,
) -> str | None:
    """Decodifica `path` y entrega cada trozo a `on_buffer`. Devuelve None si terminó bien, o el error.
    Debe llamarse desde un hilo con bucle de eventos (usa uno local)."""
    decoder = QAudioDecoder()
    decoder.setAudioFormat(fmt)
    loop = QEventLoop()
    error: list[str] = []
    last_data = [time.monotonic()]

    def on_ready() -> None:
        last_data[0] = time.monotonic()
        on_buffer(decoder.read())

    def on_error(_code) -> None:
        error.append(decoder.errorString() or "error de decodificación")
        loop.quit()

    def watchdog() -> None:
        if time.monotonic() - last_data[0] > stall_seconds:
            error.append(f"el archivo no responde (¿dañado?): sin audio durante {stall_seconds:.0f} s")
            loop.quit()

    timer = QTimer()
    timer.setInterval(500)
    timer.timeout.connect(watchdog)
    decoder.bufferReady.connect(on_ready)
    decoder.finished.connect(loop.quit)
    decoder.error.connect(on_error)
    decoder.setSource(QUrl.fromLocalFile(path))
    decoder.start()
    timer.start()
    loop.exec()
    timer.stop()
    decoder.stop()
    decoder.setSource(QUrl())
    # Se libera ya (no con deleteLater): el hilo del trabajador puede terminar antes de procesar
    # borrados diferidos, y el archivo debe quedar suelto para poder moverlo o modificarlo.
    shiboken6.delete(decoder)
    shiboken6.delete(timer)
    return error[0] if error else None
