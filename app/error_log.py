"""Registro de errores en archivo, para que nada falle en silencio (con pythonw no hay consola)."""

from __future__ import annotations

import faulthandler
import logging
import sys
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

from .config import data_dir

_fault_file = None
_last_notice = 0.0


def log_path() -> Path:
    return data_dir() / "registro.log"


def setup() -> Path:
    """Registro rotativo (1 MB × 3) y volcado de cierres inesperados de bajo nivel."""
    global _fault_file
    path = log_path()
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        _fault_file = open(data_dir() / "cierres-inesperados.log", "a", encoding="utf-8")
        faulthandler.enable(_fault_file)
    except OSError:
        pass
    return path


def install_excepthook(notify: Callable[[str], None] | None = None) -> None:
    """Guarda en el registro cualquier error no controlado y avisa al usuario (como mucho uno cada 5 s)."""
    previous = sys.excepthook

    def hook(exc_type, exc, tb) -> None:
        global _last_notice
        details = "".join(traceback.format_exception(exc_type, exc, tb))
        logging.getLogger("errores").error("Error no controlado:\n%s", details)
        if notify is not None and time.monotonic() - _last_notice > 5:
            _last_notice = time.monotonic()
            try:
                notify(f"{exc_type.__name__}: {exc}")
            except Exception:
                pass
        if sys.stderr is not None:  # con consola, también se muestra ahí
            previous(exc_type, exc, tb)

    sys.excepthook = hook
