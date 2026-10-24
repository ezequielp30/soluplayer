"""Creación de la aplicación Qt y arranque de la ventana principal."""

from __future__ import annotations

import logging
import os
import sqlite3
import sys

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__, backup, error_log
from .config import APP_NAME, ORG_NAME, database_path, resource_path
from .database import Database
from .preferences import Preferences
from .single_instance import InstanceServer, acquire_or_forward
from .ui import theme, worker_runner
from .ui.main_window import MainWindow

log = logging.getLogger(__name__)


def _check_and_maybe_restore() -> bool:
    """Revisa la biblioteca antes de abrirla. Devuelve False si el usuario prefiere salir."""
    db_file = database_path()
    if not db_file.exists():
        return True
    problem = backup.check_database(db_file)
    if problem is None:
        return True
    log.error("La biblioteca no pasó la revisión al arrancar: %s", problem)
    latest = backup.latest_valid_backup()
    box = QMessageBox(QMessageBox.Icon.Warning, APP_NAME, "La biblioteca parece dañada.")
    if latest is not None:
        box.setInformativeText(
            f"Se puede restaurar el último respaldo válido ({latest.name}). La biblioteca actual no se borra: "
            "se guarda aparte con el nombre «biblioteca-danada-…».\n\nDetalle técnico: " + problem
        )
        restore = box.addButton("Restaurar respaldo", QMessageBox.ButtonRole.AcceptRole)
    else:
        box.setInformativeText("No hay respaldos disponibles.\n\nDetalle técnico: " + problem)
        restore = None
    box.addButton("Abrir de todos modos", QMessageBox.ButtonRole.DestructiveRole)
    quit_button = box.addButton("Salir", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() is quit_button:
        return False
    if restore is not None and box.clickedButton() is restore:
        try:
            aside = backup.restore(latest, db_file)
        except OSError as exc:
            QMessageBox.critical(None, APP_NAME, f"No se pudo restaurar el respaldo:\n{exc}\n\n¿Está el programa abierto dos veces?")
            return False
        QMessageBox.information(None, APP_NAME, f"Biblioteca restaurada desde {latest.name}.\nLa anterior quedó guardada como {aside.name}.")
    return True


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(ORG_NAME)
    app.setStyle("Fusion")
    icon_file = resource_path("assets", "icono.ico")
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    # Archivos recibidos desde Windows («Abrir con», doble clic, arrastrar al ícono).
    paths = [os.path.abspath(a) for a in sys.argv[1:] if os.path.isfile(a)]
    try:
        lock = acquire_or_forward(paths)
    except TimeoutError:
        QMessageBox.warning(
            None, APP_NAME,
            "El Reproductor de Música ya está abierto pero no responde.\n\n"
            "Espera unos segundos y vuelve a intentarlo, o ciérralo desde el Administrador de tareas.",
        )
        return 1
    if lock is None:
        return 0  # ya había una copia abierta: ella los reproduce
    # Escuchar desde ya: las copias que se abran mientras esta arranca esperan en la cola.
    server = InstanceServer(app)
    app._instance_lock = lock  # vive hasta el final del programa (al salir se libera el cerrojo)

    error_log.setup()
    log.info("Inicio de %s %s", APP_NAME, __version__)

    prefs = Preferences(QSettings(ORG_NAME, "ReproductorMusica"))
    theme.apply(app, prefs.theme)

    if not _check_and_maybe_restore():
        return 0

    db_file = database_path()
    try:
        db = Database(db_file)
    except sqlite3.Error as exc:
        log.exception("No se pudo abrir la biblioteca")
        QMessageBox.critical(
            None,
            APP_NAME,
            f"No se pudo abrir la base de datos de la biblioteca:\n{db_file}\n\n{exc}\n\n"
            f"Hay respaldos en:\n{backup.backup_dir()}",
        )
        return 1
    backup.backup_if_due(db.conn)

    window = MainWindow(db)

    def notify(summary: str) -> None:
        # Diferido: el aviso no debe abrirse dentro del código que acaba de fallar.
        QTimer.singleShot(0, lambda: QMessageBox.warning(
            window,
            "Ocurrió un error inesperado",
            f"{summary}\n\nEl programa sigue funcionando. Los detalles se guardaron en:\n{error_log.log_path()}",
        ))

    error_log.install_excepthook(notify)
    window.show()
    QTimer.singleShot(0, window.startup_checks)
    QTimer.singleShot(1500, window.sync_volume_annotations)
    if paths:
        server.enqueue(paths)  # se juntan con los de otras copias abiertas a la vez
    server.set_handler(window.open_files)
    code = app.exec()
    if not worker_runner.wait_pending():
        # Una tarea sigue atascada (red, archivo bloqueado). La biblioteca y los ajustes ya se guardaron
        # al cerrar la ventana; salir así evita que Qt aborte al destruir un hilo en marcha.
        log.warning("Una tarea en segundo plano no terminó: se sale sin esperarla")
        log.info("Cierre normal (código %s)", code)
        logging.shutdown()
        os._exit(code)
    log.info("Cierre normal (código %s)", code)
    return code
