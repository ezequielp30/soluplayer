"""Creación de la aplicación Qt y arranque de la ventana principal."""

from __future__ import annotations

import logging
import os
import sqlite3
import sys

from PySide6.QtCore import QLibraryInfo, QObject, QSettings, Qt, QTimer, QTranslator, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__, backup, error_log
from .config import APP_NAME, ORG_NAME, data_dir, database_path, resource_path
from .database import Database
from .preferences import Preferences
from .single_instance import InstanceServer, acquire_or_forward
from .ui import theme, worker_runner
from .ui.main_window import MainWindow

log = logging.getLogger(__name__)

UPDATE_CHECK_DELAY_MS = 10000  # que primero abra la ventana y empiece la música


def _install_spanish(app: QApplication) -> None:
    """Textos propios de Qt en español (menú del clic derecho en los campos de texto: «Copiar», «Pegar»,
    «Deshacer»…; botones estándar de los cuadros de diálogo). Sin traducción quedaban en inglés."""
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    app._translators = []
    for name in ("qtbase_es", "qtmultimedia_es"):
        translator = QTranslator(app)
        if translator.load(name, folder):
            app.installTranslator(translator)
            app._translators.append(translator)
        else:
            log.info("Sin traducción de Qt: %s", name)


class _ErrorNotifier(QObject):
    """Vive en el hilo principal; emitir su señal desde cualquier hilo muestra el aviso en el principal."""

    show = Signal(str)


def _check_and_maybe_restore() -> bool:
    """Revisa la biblioteca antes de abrirla. Devuelve False si el usuario prefiere salir."""
    db_file = database_path()
    if not db_file.exists():
        return _offer_outside_copy(db_file)
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


def _backup_date(path) -> str:
    taken = backup._taken_at(path)
    return taken.strftime("%d/%m/%Y a las %H:%M") if taken else "(fecha desconocida)"


def _offer_outside_copy(db_file) -> bool:
    """No hay biblioteca (primera vez, o se borró la carpeta del programa). Si en Documentos hay una copia
    de un respaldo, se ofrece recuperarla. Siempre devuelve True (se abre igual)."""
    copy = backup.newest_outside_copy()
    if copy is None:
        return True
    answer = QMessageBox.question(
        None, APP_NAME,
        "No se encontró tu biblioteca, pero hay un respaldo de esta PC guardado en Documentos, del "
        f"{_backup_date(copy)}:\n{copy}\n\n¿Recuperar tu biblioteca (canciones, playlists y correcciones) desde ese respaldo?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes,
    )
    if answer == QMessageBox.StandardButton.Yes:
        try:
            backup.restore(copy, db_file)
            log.warning("Biblioteca recuperada desde la copia de Documentos: %s", copy)
        except OSError as exc:
            QMessageBox.warning(None, APP_NAME, f"No se pudo recuperar el respaldo:\n{exc}")
    return True


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    # MUSICPLAYER_ORG: otro lugar del registro para los ajustes (lo usan las pruebas para no leer ni
    # cambiar los del usuario).
    org = os.environ.get("MUSICPLAYER_ORG") or ORG_NAME
    app.setOrganizationName(org)
    app.setStyle("Fusion")
    _install_spanish(app)
    icon_file = resource_path("assets", "icono.ico")
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    # Archivos recibidos desde Windows («Abrir con», doble clic, arrastrar al ícono).
    paths = [os.path.abspath(a) for a in sys.argv[1:] if os.path.isfile(a)]
    try:
        # Carpeta actual segura: al abrir una canción desde el Explorador, Windows deja como carpeta
        # actual la de esa canción (p. ej. una descarga), y desde ahí se podrían cargar programas.
        os.chdir(data_dir())
    except OSError:
        pass
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
    error_log.install_excepthook()  # desde ya: un fallo al arrancar también queda en el registro
    log.info("Inicio de %s %s", APP_NAME, __version__)

    prefs = Preferences(QSettings(org, "ReproductorMusica"))
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

    try:
        window = MainWindow(db)
    except Exception as exc:
        log.exception("No se pudo crear la ventana principal")
        QMessageBox.critical(
            None, APP_NAME,
            f"El programa no pudo iniciarse:\n{type(exc).__name__}: {exc}\n\nLos detalles se guardaron en:\n{error_log.log_path()}",
        )
        return 1

    # El aviso de error se entrega SIEMPRE en el hilo de la ventana (señal en cola), aunque el fallo
    # ocurra en una tarea en segundo plano: crear una ventana desde otro hilo cerraría el programa.
    notifier = _ErrorNotifier()
    notifier.show.connect(
        lambda summary: QMessageBox.warning(
            window,
            "Ocurrió un error inesperado",
            f"{summary}\n\nEl programa sigue funcionando. Los detalles se guardaron en:\n{error_log.log_path()}",
        ),
        Qt.ConnectionType.QueuedConnection,  # diferido: no se abre dentro del código que acaba de fallar
    )
    app._error_notifier = notifier
    error_log.install_excepthook(notifier.show.emit)
    window.show()
    QTimer.singleShot(0, window.startup_checks)
    QTimer.singleShot(1500, window.sync_volume_annotations)
    QTimer.singleShot(UPDATE_CHECK_DELAY_MS, window.check_updates_on_start)
    if paths:
        server.enqueue(paths)  # se juntan con los de otras copias abiertas a la vez
    server.set_handler(window.open_files)
    code = app.exec()
    server.close()  # la ventana ya se cerró: los archivos que lleguen ahora los abre la copia nueva
    if not worker_runner.wait_pending():
        # Una tarea sigue atascada (red, archivo bloqueado). La biblioteca y los ajustes ya se guardaron
        # al cerrar la ventana; salir así evita que Qt aborte al destruir un hilo en marcha.
        log.warning("Una tarea en segundo plano no terminó: se sale sin esperarla")
        log.info("Cierre normal (código %s)", code)
        logging.shutdown()
        os._exit(code)
    log.info("Cierre normal (código %s)", code)
    return code
