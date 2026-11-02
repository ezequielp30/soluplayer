"""Pide la clave de AcoustID, con el enlace para registrarse gratis, y la comprueba antes de guardarla."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget

from .. import acoustid_lookup
from ..preferences import Preferences
from .worker_runner import WorkerRunner

_INTRO = (
    "Para reconocer tus canciones por su sonido, el programa consulta AcoustID, un servicio gratuito para uso no "
    "comercial. Necesita una clave de aplicación."
)
_HOW = (
    "Si no tienes una: pulsa «Registrarme gratis», entra con tu cuenta, registra una aplicación y copia aquí su clave. "
    "Se envían a AcoustID la huella y la duración de cada canción, nunca el audio."
)
_INVALID = (
    "AcoustID no acepta esa clave. Debe ser la clave de una aplicación, no la de tu cuenta: la obtienes en "
    "«Registrarme gratis». Si acabas de crearla, revisa que esté completa."
)


class _CheckWorker(QObject):
    finished = Signal(str)  # vacío si la clave sirve; si no, el problema

    def __init__(self, key: str) -> None:
        super().__init__()
        self._key = key

    @Slot()
    def run(self) -> None:
        try:
            acoustid_lookup.check_key(self._key)
            self.finished.emit("")
        except acoustid_lookup.InvalidKey:
            self.finished.emit(_INVALID)
        except acoustid_lookup.ServiceError as exc:
            self.finished.emit(str(exc))
        except Exception as exc:  # nunca dejar el hilo colgado
            self.finished.emit(str(exc) or "No se pudo comprobar la clave.")


class AcoustIdKeyDialog(QDialog):
    def __init__(self, prefs: Preferences, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._prefs = prefs
        self.setWindowTitle("Clave de AcoustID")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        for text in (_INTRO, _HOW):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(label)
        self.key = QLineEdit(prefs.acoustid_key)
        self.key.setPlaceholderText("Pega aquí la clave de tu aplicación")
        self.key.textChanged.connect(self._update_buttons)
        layout.addWidget(self.key)
        self.message = QLabel("")
        self.message.setObjectName("DialogNote")
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message)
        self.bar = QProgressBar()
        layout.addWidget(self.bar)
        buttons = QHBoxLayout()
        self.btn_register = QPushButton("Registrarme gratis")
        self.btn_register.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(acoustid_lookup.REGISTER_URL)))
        self.btn_save = QPushButton("Comprobar y guardar")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._check)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(self.btn_register)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_save)
        buttons.addWidget(self.btn_cancel)
        layout.addLayout(buttons)
        self.runner = WorkerRunner(self, self.bar, QLabel(self))
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.btn_save.setEnabled(bool(self.key.text().strip()) and not self.runner.busy)

    def _check(self) -> None:
        self.message.setText("Comprobando con AcoustID…")
        self.runner.start(_CheckWorker(self.key.text().strip()), 0, "", self._on_checked)
        self._update_buttons()

    def _on_checked(self, problem: str) -> None:
        self._update_buttons()
        if problem:
            self.message.setText(problem)
            return
        self._prefs.acoustid_key = self.key.text().strip()
        self.accept()

    def reject(self) -> None:
        if self.runner.request_close(ask=False):
            super().reject()
