"""Ventana principal: conecta la interfaz, la reproducción, la base de datos y la importación."""

from __future__ import annotations

import logging
import os
import random
import sqlite3
import subprocess
import sys
import time
from functools import partial

from PySide6.QtCore import QPoint, QSettings, Qt, QThread, QTimer, QUrl, Slot
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..config import APP_NAME, AUDIO_FILE_FILTER, AUTHOR_NAME, CONTACT_EMAIL, DISCLAIMER, ORG_NAME
from ..database import Database, DuplicatePathError
from .. import backup, error_log, file_manager, library_cleanup, review_folder, win_audio
from ..config import data_dir, resource_path
from ..artwork import cover_hash
from ..equalizer import EqSettings
from ..file_operations import FileOperations
from ..folders import breadcrumb as folder_breadcrumb
from ..folders import build_folder_tree, display_name, tracks_in_folder
from ..importer import ImportWorker, ScannedTrack, ScanResult, in_skipped_folder, scan_file
from ..models import Track
from ..player import PlaybackController, RepeatMode
from ..preferences import Preferences
from ..titles import suggest_from_filename
from ..utils import normalize_text, path_key, plural
from .content_panel import (
    MODE_LIBRARY,
    MODE_PLAYLIST,
    MODE_SEARCH,
    ContentPanel,
    EmptyAction,
    Group,
    describe_tracks,
)
from .covers import CoverProvider
from .dialogs import (
    FolderImportDialog,
    ImportReportDialog,
    PlaylistNameDialog,
    PreferencesDialog,
    TitleReviewDialog,
    ask,
    confirm_without_backup,
)
from . import menu_loader, theme, worker_runner
from .duplicates_dialog import DuplicatesDialog
from .equalizer_dialog import EqualizerDialog
from .convert_dialog import ConvertDialog
from .history_dialog import HistoryDialog
from .loudness_dialog import FILTER_DONE, FILTER_NEED, LoudnessDialog
from .online_dialog import OnlineLookupDialog
from .icons import TEXT, icon
from .player_bar import PlayerBar
from .sidebar import Sidebar

log = logging.getLogger(__name__)

_VIEW_TITLES = {
    "recent": "Recientes",
    "artists": "Artistas",
    "albums": "Álbumes",
    "songs": "Canciones",
}


# Ruta completa: con solo «explorer», Windows lo busca primero en la carpeta actual (p. ej. la de una
# descarga), donde un «explorer.exe» falso se ejecutaría en su lugar.
_EXPLORER = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "explorer.exe")


def _setting_int(settings, key: str, default: int, low: int, high: int) -> int:
    """Entero de las preferencias; si está dañado vuelve al de fábrica."""
    try:
        value = int(settings.value(key, default))
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high else default


class MainWindow(QMainWindow):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        # La organización viene de QApplication para que las pruebas usen ajustes aparte.
        self.settings = QSettings(QApplication.organizationName() or ORG_NAME, "ReproductorMusica")
        self.prefs = Preferences(self.settings)
        self.covers = CoverProvider(db)
        self.player = PlaybackController(self)
        self.library: list[Track] = []
        self.ops = FileOperations(
            db,
            release_files=self._release_files,
            forget_tracks=self.player.remove_tracks,
            on_changed=self._on_files_changed,
            confirm_without_backup=lambda: confirm_without_backup(self),
        )
        self._import_thread: QThread | None = None
        self._import_worker: ImportWorker | None = None
        self._progress: QProgressDialog | None = None

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(900, 590)  # con la barra lateral completa: 5 playlists y al menos 1 carpeta
        self.resize(1280, 800)

        # Estructura: barra superior + (barra lateral | panel principal)
        self.player_bar = PlayerBar(self.covers)
        self.sidebar = Sidebar()
        self.content = ContentPanel(self.covers)
        # La barra lateral ocupa toda la altura (más espacio para Playlists y Carpetas); la barra del
        # reproductor va solo encima del panel principal.
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.player_bar)
        right_layout.addWidget(self.content, 1)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)
        self.splitter.setSizes([230, 1050])
        self.setCentralWidget(self.splitter)

        self._build_menus()
        self._connect()
        self._restore_settings()
        self._restore_equalizer()
        theme.on_change(self._on_theme_changed)
        QApplication.styleHints().colorSchemeChanged.connect(self._on_system_scheme_changed)
        if os.environ.get("MUSICPLAYER_SILENCIO") == "1":
            # Solo para pruebas automáticas: silencia la salida sin tocar los ajustes guardados.
            self.player.set_muted(True)

        self._reload_library()
        self.sidebar.set_playlists(self.db.playlists())
        self.sidebar.select_library("songs")
        self._report_missing_on_start()

    # ================================================================== construcción

    def _build_menus(self) -> None:
        """Los menús (textos, orden, atajos, separadores, submenús) vienen de assets/menus.ui, que se
        edita con Qt Designer. Aquí solo se dice qué hace cada opción, por su nombre de objeto."""
        handlers = {
            "act_import_files": self._import_files,
            "act_import_folder": self._import_folder,
            "act_search": self._focus_search,
            "act_backup_now": self._backup_now,
            "act_backup_folder": self._open_backup_folder,
            "act_preferences": self._open_preferences,
            "act_quit": self.close,
            "act_play": self._toggle_play,
            "act_stop": self.player.stop,
            "act_prev": self.player.previous,
            "act_next": self.player.next,
            "act_shuffle": None,  # casilla: se conecta abajo con «toggled»
            "act_repeat": self.player.cycle_repeat,
            "act_equalizer": self._open_equalizer,
            "act_volume_up": lambda: self._nudge_volume(5),
            "act_volume_down": lambda: self._nudge_volume(-5),
            "act_test_sound": self._test_sound,
            "act_new_playlist": self._create_playlist,
            "act_rename_playlist": self._rename_selected_playlist,
            "act_delete_playlist": self._delete_selected_playlist,
            "act_online": lambda: self._open_online(self.library),
            "act_duplicates": self._open_duplicates,
            "act_loudness": self._open_loudness,
            "act_convert": self._open_convert,
            "act_history": self._open_history,
            "act_error_log": self._open_error_log,
            "act_about": self._about,
        }
        spec, self._menu_warning = menu_loader.load()
        if spec is None:
            spec = menu_loader.basic_spec(handlers)
        actions, menus = menu_loader.build(self, self.menuBar(), spec, handlers)
        if spec.warnings:
            self._menu_warning = "\n".join(filter(None, [self._menu_warning, *spec.warnings]))

        def action(name: str) -> QAction:
            # Si se quitó del archivo de menús, se crea igual (sin mostrarla) para que el resto funcione.
            return actions.get(name) or QAction(self)

        self.act_import_files = action("act_import_files")
        self.act_import_folder = action("act_import_folder")
        self.act_play = action("act_play")
        self.act_shuffle = action("act_shuffle")
        self.act_shuffle.setCheckable(True)
        self.act_shuffle.toggled.connect(self.player.set_shuffle)
        self.act_rename = action("act_rename_playlist")
        self.act_delete = action("act_delete_playlist")
        # Teclas multimedia del teclado, además del atajo que se elija en el editor.
        media = {
            "act_play": (Qt.Key.Key_MediaTogglePlayPause, Qt.Key.Key_MediaPlay),
            "act_stop": (Qt.Key.Key_MediaStop,),
            "act_prev": (Qt.Key.Key_MediaPrevious,),
            "act_next": (Qt.Key.Key_MediaNext,),
        }
        for name, keys in media.items():
            if name in actions:
                act = actions[name]
                act.setShortcuts([s for s in act.shortcuts() if not s.isEmpty()] + [QKeySequence(k) for k in keys])
        for menu in menus.values():
            if self.act_rename in menu.actions() or self.act_delete in menu.actions():
                menu.aboutToShow.connect(self._update_playlist_actions)
        if self._menu_warning:
            QTimer.singleShot(800, lambda: QMessageBox.warning(self, "Menús", self._menu_warning))

    def _connect(self) -> None:
        bar = self.player_bar
        bar.play_pause_clicked.connect(self._toggle_play)
        bar.stop_clicked.connect(self.player.stop)
        bar.prev_clicked.connect(self.player.previous)
        bar.next_clicked.connect(self.player.next)
        bar.seek_requested.connect(self.player.seek)
        bar.volume_changed.connect(self.player.set_volume)
        bar.mute_toggled.connect(self.player.set_muted)
        bar.shuffle_toggled.connect(self.player.set_shuffle)
        bar.repeat_clicked.connect(self.player.cycle_repeat)
        bar.equalizer_clicked.connect(self._open_equalizer)
        bar.search_changed.connect(self._on_search_changed)

        p = self.player
        p.current_track_changed.connect(self._on_track_changed)
        p.track_started.connect(self._on_track_started)
        p.playing_changed.connect(bar.set_playing)
        p.playing_changed.connect(self._check_system_volume)
        p.output_changed.connect(
            lambda name: self.statusBar().showMessage(f"La salida de audio cambió a «{name}».", 8000)
        )
        p.position_changed.connect(bar.set_position)
        p.duration_changed.connect(self._on_duration_changed)
        p.error_occurred.connect(self._on_player_error)
        p.track_skipped.connect(self._on_track_skipped)
        p.shuffle_changed.connect(self._on_shuffle_changed)
        p.repeat_changed.connect(self._on_repeat_changed)

        sb = self.sidebar
        sb.view_selected.connect(self._on_view_selected)
        sb.create_playlist_requested.connect(self._create_playlist)
        sb.rename_playlist_requested.connect(self._rename_playlist)
        sb.delete_playlist_requested.connect(self._delete_playlist)
        sb.play_playlist_requested.connect(self._play_playlist)
        sb.import_folder_requested.connect(self._import_folder)
        sb.play_folder_requested.connect(self._play_folder)
        sb.folder_add_to_playlist_requested.connect(self._add_folder_to_playlist)
        sb.folder_show_in_explorer_requested.connect(self._open_folder_in_explorer)
        sb.folder_rescan_requested.connect(self._rescan_folder)
        sb.folder_rename_requested.connect(self._rename_folder)
        sb.folder_create_requested.connect(self._create_subfolder)
        sb.folder_trash_requested.connect(self._trash_folder)

        c = self.content
        c.play_requested.connect(self._on_play_requested)
        c.shuffle_play_requested.connect(self._on_shuffle_play)
        c.add_to_playlist_requested.connect(self._show_add_menu)
        c.remove_from_playlist_requested.connect(self._remove_from_playlist)
        c.remove_from_library_requested.connect(self._remove_from_library)
        c.locate_requested.connect(self._locate_track)
        c.show_in_folder_requested.connect(self._show_in_folder)
        c.import_files_requested.connect(self._import_files)
        c.import_folder_requested.connect(self._import_folder)
        c.missing_review_requested.connect(self._review_first_missing)
        c.folder_requested.connect(self.sidebar.select_folder)
        c.online_lookup_requested.connect(self._open_online)
        c.rename_file_requested.connect(self._rename_track_file)
        c.move_files_requested.connect(self._move_track_files)
        c.trash_files_requested.connect(self._trash_track_files)

    # ================================================================== ajustes

    def _fit_to_screen(self) -> None:
        """La ventana entra entera en el área visible de su monitor (sin quedar bajo la barra de tareas),
        también en pantallas chicas (1366×768 o 1280×720 con escala 125 %) o si cambió el monitor."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        frame_extra = max(0, self.frameGeometry().height() - self.geometry().height()) or 32
        width, height = area.width(), area.height() - frame_extra
        self.setMinimumSize(min(self.minimumWidth(), width), min(self.minimumHeight(), height))
        if self.width() > width or self.height() > height:
            self.resize(min(self.width(), width), min(self.height(), height))
        frame = self.frameGeometry()
        if not area.contains(frame):
            x = min(max(frame.x(), area.x()), area.right() - frame.width() + 1)
            y = min(max(frame.y(), area.y()), area.bottom() - frame.height() + 1)
            self.move(max(x, area.x()), max(y, area.y()))

    def _restore_settings(self) -> None:
        s = self.settings
        geometry = s.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self._fit_to_screen()
        splitter = s.value("window/splitter")
        if splitter is not None:
            self.splitter.restoreState(splitter)
        volume = _setting_int(s, "player/volume", 70, 0, 100)  # un valor dañado no impide abrir
        muted = s.value("player/muted", False, type=bool)
        shuffle = s.value("player/shuffle", False, type=bool)
        repeat = _setting_int(s, "player/repeat", 0, 0, 2)
        self.player_bar.set_volume(volume)
        self.player.set_volume(volume)
        self.player_bar.set_muted(muted)
        self.player.set_muted(muted)
        self.player.set_shuffle(shuffle)
        self._on_shuffle_changed(shuffle)
        self._restoring = True  # restaurar los ajustes no debe mostrar avisos en la barra de estado
        self.player.set_repeat(repeat if repeat in (0, 1, 2) else 0)
        self._restoring = False

    def _save_settings(self) -> None:
        s = self.settings
        s.setValue("window/geometry", self.saveGeometry())
        s.setValue("window/splitter", self.splitter.saveState())
        s.setValue("player/volume", self.player_bar.volume.value())
        s.setValue("player/muted", self.player_bar.btn_mute.isChecked())
        s.setValue("player/shuffle", self.player.shuffle)
        s.setValue("player/repeat", int(self.player.repeat))

    def closeEvent(self, event) -> None:
        if self._import_worker is not None:
            self._import_worker.cancel()
        if self._import_thread is not None:
            self._import_thread.quit()
            if not self._import_thread.wait(5000):
                # Sigue leyendo (p. ej. una unidad de red lenta): que no se destruya en marcha; al salir
                # del programa se espera a los hilos pendientes (application.run).
                worker_runner.keep_alive(self._import_thread)
        self._save_settings()
        self.settings.sync()
        theme.off_change(self._on_theme_changed)
        try:
            QApplication.styleHints().colorSchemeChanged.disconnect(self._on_system_scheme_changed)
        except (RuntimeError, TypeError):
            pass
        self.player.stop()
        self.db.close()
        super().closeEvent(event)

    # ================================================================== vistas

    def _reload_library(self) -> None:
        self.library = self.db.all_tracks()
        was_folder = self.sidebar.current_view()[0] == "folder"
        self.folder_roots = build_folder_tree(self.library)
        self.sidebar.set_folders(self.folder_roots)
        if was_folder and self.sidebar.current_folder() is None:
            # La carpeta que se estaba viendo ya no tiene canciones.
            self.sidebar.select_library("songs")

    def _library_empty_state(self):
        return (
            "music",
            "Tu biblioteca está vacía",
            "Importa una carpeta con tu música (puede incluir subcarpetas) o elige archivos sueltos. "
            "Los archivos se quedan donde están: el programa solo guarda su ubicación.",
            [
                EmptyAction("Importar carpeta…", self._import_folder, primary=True),
                EmptyAction("Importar archivos…", self._import_files),
            ],
        )

    def _on_view_selected(self, kind: str, playlist_id) -> None:
        if self.player_bar.search.text():
            self.player_bar.clear_search()
        self._render_view(kind, playlist_id)

    def _refresh_view(self) -> None:
        text = self.player_bar.search.text().strip()
        if text:
            self._render_search(text)
        else:
            self._render_view(*self.sidebar.current_view())

    def _render_view(self, kind: str, playlist_id: int | None = None) -> None:
        if kind == "playlist" and playlist_id is not None:
            self._render_playlist(playlist_id)
        elif kind == "folder" and playlist_id is not None:
            self._render_folder(playlist_id)
        elif kind == "recent":
            self.content.show_tracks(
                "Recientes",
                self.db.recent_tracks(),
                MODE_LIBRARY,
                self._library_empty_state(),
            )
            if self.library:
                self.content.add_subtitle_note("reproducidas o agregadas recientemente")
        elif kind in ("artists", "albums"):
            attr, noun, group_icon = {
                "artists": ("artist", ("artista", "artistas"), "artist"),
                "albums": ("album", ("álbum", "álbumes"), "cover"),
            }[kind]
            self.content.show_groups(
                _VIEW_TITLES[kind], self._groups_by(attr), noun, self._library_empty_state(), group_icon
            )
        else:
            self.content.show_tracks("Canciones", self.library, MODE_LIBRARY, self._library_empty_state())
        self._sync_current_track()

    def _render_playlist(self, playlist_id: int) -> None:
        playlist = self.db.playlist(playlist_id)
        if playlist is None:
            self.sidebar.set_playlists(self.db.playlists())
            self.sidebar.select_library("songs")
            return
        tracks = self.db.playlist_tracks(playlist_id)
        cover = next((t.cover_hash for t in tracks if t.cover_hash and t.available), None)
        empty = (
            "playlist",
            "Esta playlist está vacía",
            "Ve a «Canciones» o usa la búsqueda, y pulsa el botón + de una canción "
            "(o clic derecho → «Agregar a playlist…») para añadirla aquí.",
            [EmptyAction("Ir a Canciones", lambda: self.sidebar.select_library("songs"), primary=True)],
        )
        self.content.show_tracks(
            playlist.name, tracks, MODE_PLAYLIST, empty, cover_hash=cover, show_cover=True
        )
        self._sync_current_track()

    # ================================================================== carpetas

    def _render_folder(self, path: str) -> None:
        tracks = tracks_in_folder(self.library, path)
        empty = (
            "folder",
            "Esta carpeta no tiene canciones en la biblioteca",
            "Puede que se hayan quitado o movido. Busca música nueva en ella o elige otra carpeta.",
            [
                EmptyAction("Buscar música nueva aquí", lambda: self._rescan_folder(path), primary=True),
                EmptyAction("Ir a Canciones", lambda: self.sidebar.select_library("songs")),
            ],
        )
        subtitle = describe_tracks(tracks) + "  ·  incluye subcarpetas" if tracks else None
        self.content.show_tracks(
            display_name(path),
            tracks,
            MODE_LIBRARY,
            empty,
            subtitle=subtitle,
            breadcrumb=folder_breadcrumb(path, self.folder_roots),
        )
        self.content.set_title_tooltip(path)
        self._sync_current_track()

    def _play_folder(self, path: str, shuffle: bool) -> None:
        tracks = tracks_in_folder(self.library, path)
        if not tracks:
            return
        if shuffle:
            self._on_shuffle_play(tracks)
        else:
            self._on_play_requested(tracks, 0)

    def _add_folder_to_playlist(self, path: str, pos: QPoint) -> None:
        self._show_add_menu(tracks_in_folder(self.library, path), pos)

    def _open_folder_in_explorer(self, path: str) -> None:
        if not os.path.isdir(path):
            QMessageBox.warning(
                self, "Carpeta no encontrada",
                f"No se encuentra la carpeta:\n{path}\n\nPuede que se haya movido o que la unidad esté desconectada.",
            )
            return
        if sys.platform == "win32":
            subprocess.Popen([_EXPLORER, os.path.normpath(path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _rescan_folder(self, path: str) -> None:
        if self._busy_importing():
            return
        if not os.path.isdir(path):
            QMessageBox.warning(
                self, "Carpeta no encontrada",
                f"No se encuentra la carpeta:\n{path}\n\nPuede que se haya movido o que la unidad esté desconectada.",
            )
            return
        self._start_import(folder=path, recursive=True)

    def _groups_by(self, attr: str) -> list[Group]:
        buckets: dict[str, list[Track]] = {}
        for track in self.library:
            buckets.setdefault(getattr(track, attr), []).append(track)
        groups = []
        for label in sorted(buckets, key=normalize_text):
            tracks = buckets[label]
            cover = next((t.cover_hash for t in tracks if t.cover_hash), None)
            groups.append(Group(label, tracks, cover))
        return groups

    def _on_search_changed(self, text: str) -> None:
        text = text.strip()
        if text:
            self._render_search(text)
        else:
            self._render_view(*self.sidebar.current_view())

    def _render_search(self, text: str) -> None:
        terms = normalize_text(text).split()
        results = [
            t
            for t in self.library
            if all(term in normalize_text(f"{t.title} {t.artist} {t.album}") for term in terms)
        ]
        actions = [EmptyAction("Limpiar búsqueda", self._clear_search, primary=True)]
        if not self.library:
            actions.append(EmptyAction("Importar carpeta…", self._import_folder))
        empty = (
            "search",
            f"Sin resultados para «{text}»",
            "Prueba con otra palabra del título, el artista o el álbum. "
            "La búsqueda no distingue mayúsculas ni tildes."
            if self.library
            else "Tu biblioteca todavía no tiene canciones. Importa música para poder buscarla.",
            actions,
        )
        self.content.show_tracks(
            "Resultados de búsqueda",
            results,
            MODE_SEARCH,
            empty,
            subtitle=f"{plural(len(results), 'canción', 'canciones')} para «{text}»  ·  "
            "pulsa + en una canción para agregarla a una playlist",
        )
        self._sync_current_track()

    def _clear_search(self) -> None:
        self.player_bar.clear_search()
        self._render_view(*self.sidebar.current_view())

    def _focus_search(self) -> None:
        self.player_bar.search.setFocus()
        self.player_bar.search.selectAll()

    def _sync_current_track(self) -> None:
        current = self.player.current_track
        self.content.set_current_track(current.id if current else None)

    def _report_missing_on_start(self) -> None:
        missing = sum(1 for t in self.library if not t.available)
        if missing:
            self.statusBar().showMessage(
                f"Atención: {plural(missing, 'canción', 'canciones')} de la biblioteca no "
                f"{'se encuentra' if missing == 1 else 'se encuentran'} en el disco. "
                "Aparecen en gris; usa clic derecho → «Localizar archivo…».",
                15000,
            )
        elif not self.library:
            self.statusBar().showMessage("Empieza importando música: Archivo → Importar carpeta… (Ctrl+Mayús+O)")

    # ================================================================== importación

    def _import_files(self) -> None:
        if self._busy_importing():
            return
        start = self.settings.value("import/last_dir", os.path.expanduser("~"))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Importar archivos de audio", start, f"{AUDIO_FILE_FILTER};;Todos los archivos (*.*)"
        )
        if files:
            self.settings.setValue("import/last_dir", os.path.dirname(files[0]))
            self._start_import(files=files)

    def _import_folder(self) -> None:
        if self._busy_importing():
            return
        start = self.settings.value("import/last_dir", os.path.expanduser("~"))
        folder = QFileDialog.getExistingDirectory(self, "Elegir carpeta de música", start)
        if not folder:
            return
        if not os.path.isdir(folder) or not os.access(folder, os.R_OK):
            QMessageBox.warning(self, "Carpeta no accesible", f"No se puede leer la carpeta:\n{folder}")
            return
        dialog = FolderImportDialog(folder, self)
        if not dialog.exec():
            return
        self.settings.setValue("import/last_dir", folder)
        self._start_import(folder=folder, recursive=dialog.recursive.isChecked())

    def _busy_importing(self) -> bool:
        if self._import_thread is not None:
            QMessageBox.information(self, "Importación en curso", "Espera a que termine la importación actual.")
            return True
        return False

    def _start_import(self, files: list[str] | None = None, folder: str | None = None, recursive: bool = False) -> None:
        self._progress = QProgressDialog("Preparando la importación…", "Cancelar", 0, 0, self)
        self._progress.setWindowTitle("Importando música")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(300)
        self._progress.setAutoClose(False)
        self._progress.setAutoReset(False)
        self._progress.setMinimumWidth(460)

        self._import_thread = QThread(self)
        self._import_worker = ImportWorker(self.db.known_path_keys(), files=files, folder=folder, recursive=recursive)
        self._import_worker.moveToThread(self._import_thread)
        self._import_thread.started.connect(self._import_worker.run)
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.finished.connect(self._on_import_finished)
        self._progress.canceled.connect(self._cancel_import)
        self._import_thread.start()

    def _cancel_import(self) -> None:
        if self._import_worker is not None:
            self._import_worker.cancel()
        if self._progress is not None:
            self._progress.setLabelText("Cancelando…")

    @Slot(int, int, str)
    def _on_import_progress(self, index: int, total: int, name: str) -> None:
        progress = self._progress
        if progress is None or progress.wasCanceled():
            return
        if total:
            progress.setMaximum(total)
            # setValue procesa eventos pendientes en un diálogo modal: la importación puede terminar
            # justo aquí y cerrar esta ventana de progreso, así que se comprueba de nuevo.
            progress.setValue(index)
            if self._progress is not progress:
                return
            if name:
                progress.setLabelText(f"Leyendo {index + 1} de {total}:\n{name}")
        else:
            progress.setLabelText(name)

    @Slot(object)
    def _on_import_finished(self, result: ScanResult) -> None:
        if self._import_thread is not None:
            self._import_thread.quit()
            self._import_thread.wait()
            self._import_thread.deleteLater()
        if self._import_worker is not None:
            self._import_worker.deleteLater()
        self._import_thread = None
        self._import_worker = None
        if self._progress is not None:
            self._progress.close()
            self._progress.deleteLater()
            self._progress = None

        if self.prefs.ask_titles_on_import:
            self._review_missing_titles(result.tracks)
        added, late_duplicates = self.db.add_tracks(result.tracks)
        duplicates = result.duplicates + late_duplicates
        self._reload_library()
        self._refresh_view()

        self.statusBar().showMessage(
            f"Importación terminada: {plural(len(added), 'canción', 'canciones')} "
            f"{'nueva' if len(added) == 1 else 'nuevas'}.",
            8000,
        )
        self._run_dialog(ImportReportDialog(
            len(added), duplicates, result.failures, result.ignored_count, result.cancelled, self
        ))

    def _review_missing_titles(self, tracks: list[ScannedTrack]) -> None:
        """Pregunta si se completan los títulos de las canciones que no traen etiqueta de título."""
        untitled = [t for t in tracks if not t.metadata.has_title_tag]
        if not untitled:
            return
        detect_artist = self.prefs.detect_artist_in_filename
        rows = []
        for item in untitled:
            title, artist = suggest_from_filename(item.path, detect_artist)
            # Solo se propone artista si la canción tampoco lo trae en sus etiquetas.
            rows.append((item.path, title, artist if not item.metadata.has_artist_tag else None))
        dialog = TitleReviewDialog(rows, self)
        if not dialog.exec():
            return  # se conservan los nombres de archivo como título
        for index, (title, artist) in dialog.results().items():
            meta = untitled[index].metadata
            meta.title = title
            if artist and not meta.has_artist_tag:
                meta.artist = artist

    # ================================================================== datos en internet

    def _open_online(self, tracks: list[Track]) -> None:
        if not tracks:
            QMessageBox.information(self, "Datos en internet", "La biblioteca está vacía. Importa música primero.")
            return
        self._run_dialog(OnlineLookupDialog(
            tracks, self.prefs.online_sources, self.prefs.online_covers, self._apply_online_updates, self
        ))

    def _apply_online_updates(self, updates: list[tuple[Track, object, bytes | None]]) -> str:
        """Guarda en la biblioteca los datos elegidos. Los archivos de audio no se modifican."""
        if len(updates) >= 10:
            self._safety_backup("antes-de-datos-internet")  # solo cambia la biblioteca, no los archivos
        covers = sum(1 for _t, _c, cover in updates if cover)
        # Todas en una transacción: si algo falla, no queda la mitad aplicada.
        self.db.update_tracks_info(
            [
                (
                    track.id,
                    candidate.title.strip() or track.title,
                    candidate.artist.strip() or track.artist,
                    candidate.album.strip() or track.album,
                    cover_hash(cover) if cover else None,
                    cover,
                )
                for track, candidate, cover in updates
            ]
        )
        self._reload_library()
        by_id = {t.id: t for t in self.library}
        for track, _candidate, _cover in updates:
            if track.id in by_id:
                self.player.update_track(by_id[track.id])
        current = self.player.current_track
        if current is not None and current.id in by_id:
            self.player_bar.set_track(by_id[current.id])
        self._refresh_view()
        message = f"Se actualizaron {plural(len(updates), 'canción', 'canciones')}"
        message += f" ({plural(covers, 'carátula nueva', 'carátulas nuevas')})." if covers else "."
        self.statusBar().showMessage(message, 8000)
        return message

    # ================================================================== operaciones sobre archivos
    # El orden (respaldo → soltar → operar → biblioteca → refrescar) lo garantiza `self.ops`
    # (app/file_operations.py); aquí solo se confirma con el usuario y se muestra el resultado.

    def _on_files_changed(self) -> None:
        """Después de cualquier operación sobre archivos: recargar la biblioteca y refrescar todo."""
        self._reload_library()
        self.player.update_tracks({t.id: t for t in self.library})  # una sola pasada por la cola
        self.sidebar.set_playlists(self.db.playlists())
        self._refresh_view()

    def _release_files(self, track_ids: set[int]) -> None:
        """Si la canción que suena va a moverse o modificarse, se suelta para que Windows lo permita."""
        current = self.player.current_track
        if current is not None and current.id in track_ids:
            self.player.release_source()

    @staticmethod
    def _run_dialog(dialog) -> int:
        """Abre un diálogo modal y lo libera al cerrarlo (si no, queda en memoria hasta cerrar el programa)."""
        try:
            return dialog.exec()
        finally:
            dialog.deleteLater()

    def _library_is_empty(self, title: str) -> bool:
        if self.library:
            return False
        QMessageBox.information(self, title, "La biblioteca está vacía. Importa música primero.")
        return True

    def _open_duplicates(self) -> None:
        if not self._library_is_empty("Canciones repetidas"):
            self._run_dialog(DuplicatesDialog(lambda: self.library, self._apply_duplicates_plan, self, gather=self._gather_for_review))

    def _open_loudness(self, initial_filter: str = FILTER_NEED) -> None:
        if not self._library_is_empty("Volumen"):
            self._run_dialog(LoudnessDialog(self.ops, lambda: self.library, self, initial_filter))

    def _open_convert(self) -> None:
        if not self._library_is_empty("Convertir a MP3"):
            self._run_dialog(ConvertDialog(self.ops, lambda: self.library, self, open_history=self._open_history))

    def _open_history(self) -> None:
        self._run_dialog(HistoryDialog(
            self.ops, lambda: self.library, lambda: self._open_loudness(FILTER_DONE), self
        ))

    def _apply_duplicates_plan(self, plan: list[tuple[int, list[Track]]], trash: bool) -> str:
        """Quita copias repetidas (y opcionalmente envía sus archivos a la papelera)."""
        outcome = self.ops.remove_duplicates(plan, trash, self.library)
        if outcome is None:
            return ""
        self.statusBar().showMessage(outcome.message, 10000)
        return outcome.message

    def _gather_for_review(self, groups) -> str:
        """Mueve las copias de cada canción repetida a una subcarpeta con su nombre."""
        destination = review_folder.default_destination(self.library)
        while True:
            choice = ask(
                self,
                "Reunir repetidas para revisar",
                f"Se moverán las copias de {plural(len(groups), 'canción repetida', 'canciones repetidas')} "
                "a una carpeta con una subcarpeta por canción.",
                [
                    ("Continuar", QMessageBox.ButtonRole.AcceptRole),
                    ("Elegir otra carpeta…", QMessageBox.ButtonRole.ActionRole),
                    ("Cancelar", QMessageBox.ButtonRole.RejectRole),
                ],
                informative=f"Carpeta de revisión:\n{destination}\n\n"
                "IMPORTANTE: se mueven TODAS las copias de cada canción. Después de escucharlas, quita solo las "
                "que sobran (o usa Deshacer): si borras la carpeta entera, esas canciones se pierden por completo.\n\n"
                "Solo se mueven archivos del mismo disco. Los archivos no se modifican, la biblioteca y las playlists "
                "se actualizan solas, y puedes deshacerlo en Herramientas → Historial de cambios en archivos.",
            )
            if choice == 1:
                parent = QFileDialog.getExistingDirectory(self, "¿Dónde crear la carpeta de revisión?", os.path.dirname(destination))
                if parent:
                    destination = os.path.join(parent, review_folder.REVIEW_FOLDER_NAME)
                continue
            if choice != 0:
                return ""
            break

        session, skipped = review_folder.plan_moves(groups, destination)
        if not session.moves:
            QMessageBox.information(
                self, "Reunir repetidas", "No hay archivos que se puedan mover.\n\n"
                + "\n".join(f"• {os.path.basename(s.path)}: {s.reason}" for s in skipped[:15])
            )
            return ""
        folders = len({os.path.dirname(m.target) for m in session.moves})
        if ask(
            self,
            "Confirmar",
            f"¿Mover {plural(len(session.moves), 'archivo')} a {plural(folders, 'carpeta')} de revisión?",
            [("Mover", QMessageBox.ButtonRole.AcceptRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Question,
            f"Destino: {destination}" + (f"\n\nSe omitirán {len(skipped)} (verás el motivo al terminar)." if skipped else ""),
        ) != 0:
            return ""

        progress = QProgressDialog("Moviendo archivos…", "Detener", 0, len(session.moves), self)
        progress.setWindowTitle("Reunir repetidas")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(400)

        def report(done: int, total: int) -> bool:
            progress.setValue(done)
            QApplication.processEvents()
            return not progress.wasCanceled()

        outcome = self.ops.gather(session, groups, skipped, report)
        progress.close()
        progress.deleteLater()
        if outcome is None:
            return ""
        if outcome.error:
            QMessageBox.critical(self, "Reunir repetidas", f"No se pudo actualizar la biblioteca y se devolvió todo:\n{outcome.error}")
            return ""

        session, problems = outcome.session, outcome.problems
        message = (
            f"Se movieron {plural(len(session.moves), 'archivo')} a "
            f"{plural(len({os.path.dirname(m.target) for m in session.moves}), 'carpeta')} en «{destination}»."
        )
        details = "\n".join(f"• {os.path.basename(s.path)}: {s.reason}" for s in problems[:20])
        box = QMessageBox(QMessageBox.Icon.Information, "Reunir repetidas", message, parent=self)
        box.setInformativeText(
            "Cada subcarpeta tiene un LEEME.txt con el origen, el tamaño y la calidad de cada copia. "
            "También la encuentras en la barra lateral, en «Carpetas».\n\n"
            "Para deshacer: Herramientas → Historial de cambios en archivos."
            + (f"\n\nNo se movieron {len(problems)}:\n{details}" if problems else "")
        )
        open_folder = box.addButton("Abrir la carpeta", QMessageBox.ButtonRole.ActionRole)
        show_here = box.addButton("Verla en el programa", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Cerrar", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(destination))
        elif box.clickedButton() is show_here:
            self.sidebar.select_folder(destination)
        return message

    def sync_volume_annotations(self) -> None:
        """Al arrancar: las canciones ya ajustadas reciben la anotación dentro del propio MP3, para poder
        revertirlas aunque la biblioteca se restaure o se reimporten. No cambia el audio."""
        current = self.player.current_track
        self.ops.sync_volume_annotations(self.library, current.id if current is not None else None)

    # ------------------------------------------------------------------ gestión de archivos y carpetas

    def _ask_name(self, title: str, label: str, current: str) -> str | None:
        """Pide un nombre. El texto aparece seleccionado sin la extensión, para escribir encima."""
        dialog = QInputDialog(self)
        dialog.setWindowTitle(title)
        dialog.setLabelText(label)
        dialog.setTextValue(current)
        dialog.setOkButtonText("Aceptar")
        dialog.setCancelButtonText("Cancelar")
        dialog.resize(460, dialog.sizeHint().height())

        def select_stem() -> None:
            edit = dialog.findChild(QLineEdit)
            if edit is not None:
                stem = os.path.splitext(current)[0] if "." in current else current
                edit.setSelection(0, len(stem))

        QTimer.singleShot(0, select_stem)
        ok = self._run_dialog(dialog)
        value = dialog.textValue() if ok else None
        return value

    def _file_error(self, title: str, exc: Exception) -> None:
        QMessageBox.warning(self, title, str(exc))

    def _resume_after(self, action):
        """Renombrar o mover la canción que suena obliga a soltarla (Windows no deja tocar un archivo
        abierto). Después, si sonaba, vuelve a sonar desde el mismo punto con el archivo nuevo."""
        current = self.player.current_track
        was_playing = self.player.is_playing
        position = self.player.position()
        try:
            return action()
        finally:
            now = self.player.current_track
            if was_playing and current is not None and now is not None and now.id == current.id and not self.player.is_playing:
                self.player.play()
                QTimer.singleShot(150, lambda: self.player.seek(position))

    def _rename_track_file(self, track: Track) -> None:
        name = self._ask_name("Renombrar archivo", "Nombre nuevo del archivo:", os.path.basename(track.path))
        if name is None:
            return
        try:
            new_path = self._resume_after(lambda: self.ops.rename_track_file(track, name))
        except file_manager.FileManagerError as exc:
            self._file_error("Renombrar archivo", exc)
            return
        self.statusBar().showMessage(f"Archivo renombrado: «{os.path.basename(new_path)}».", 6000)

    def _move_track_files(self, tracks: list[Track]) -> None:
        start = os.path.dirname(os.path.dirname(tracks[0].path))
        destination = QFileDialog.getExistingDirectory(
            self, f"Mover {plural(len(tracks), 'archivo')} a… (puedes crear una carpeta nueva aquí)", start
        )
        if not destination:
            return
        result = self._resume_after(lambda: self.ops.move_tracks(tracks, destination))
        text = f"Se movieron {plural(len(result.moved), 'archivo')} a «{destination}»."
        if result.failed:
            details = "\n".join(f"• {os.path.basename(p)}: {r}" for p, r in result.failed[:15])
            QMessageBox.warning(self, "Mover archivos", f"{text}\n\nNo se movieron {len(result.failed)}:\n{details}")
        self.statusBar().showMessage(text, 8000)

    def _trash_track_files(self, tracks: list[Track]) -> None:
        folders = sorted({os.path.dirname(t.path) for t in tracks})
        names = "\n".join(f"• {os.path.basename(t.path)}" for t in tracks[:12])
        if len(tracks) > 12:
            names += f"\n… y {len(tracks) - 12} más"
        where = folders[0] if len(folders) == 1 else f"{len(folders)} carpetas"
        if ask(
            self,
            "Enviar a la Papelera",
            f"¿Enviar {plural(len(tracks), 'archivo')} a la Papelera de reciclaje?",
            [("Enviar a la Papelera", QMessageBox.ButtonRole.DestructiveRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Warning,
            f"{names}\n\nUbicación: {where}\n\nSe quitan también de la biblioteca y de las playlists. "
            "Se pueden recuperar desde la Papelera de Windows.",
        ) != 0:
            return
        sent, failed = self.ops.trash_tracks(tracks)
        text = f"Se {'envió' if sent == 1 else 'enviaron'} {plural(sent, 'archivo')} a la Papelera."
        if failed:
            details = "\n".join(f"• {os.path.basename(p)}: {r}" for p, r in failed[:15])
            QMessageBox.warning(self, "Enviar a la Papelera", f"{text}\n\nNo se enviaron {len(failed)} (siguen en la biblioteca):\n{details}")
        self.statusBar().showMessage(text, 8000)

    def _rename_folder(self, folder: str) -> None:
        name = self._ask_name("Renombrar carpeta", "Nombre nuevo de la carpeta:", os.path.basename(os.path.normpath(folder)))
        if name is None:
            return
        try:
            new_folder = self._resume_after(lambda: self.ops.rename_folder(folder, name, self.library))
        except file_manager.FileManagerError as exc:
            self._file_error("Renombrar carpeta", exc)
            return
        self.sidebar.select_folder(new_folder)
        self.statusBar().showMessage(f"Carpeta renombrada: «{os.path.basename(new_folder)}».", 6000)

    def _create_subfolder(self, parent: str) -> None:
        name = self._ask_name("Nueva subcarpeta", f"Nombre de la carpeta nueva dentro de «{os.path.basename(parent)}»:", "Nueva carpeta")
        if name is None:
            return
        try:
            created = file_manager.create_folder(parent, name)
        except file_manager.FileManagerError as exc:
            self._file_error("Nueva subcarpeta", exc)
            return
        QMessageBox.information(
            self, "Nueva subcarpeta",
            f"Se creó «{created}».\n\nAparecerá en «Carpetas» cuando tenga canciones: usa clic derecho sobre "
            "las canciones → «Mover a otra carpeta…».",
        )

    def _trash_folder(self, folder: str) -> None:
        name = os.path.basename(os.path.normpath(folder))
        contents = file_manager.folder_contents(folder) if os.path.isdir(folder) else None
        in_library = len(self.ops.tracks_in(folder, self.library))
        if contents is None:
            QMessageBox.warning(self, "Enviar carpeta a la Papelera", f"La carpeta «{name}» ya no existe.")
            return
        detail = f"Contiene {plural(contents.files, 'archivo')}"
        if contents.audio != contents.files:
            detail += f" ({contents.audio} de música)"
        if contents.folders:
            detail += f" y {plural(contents.folders, 'subcarpeta')}"
        if ask(
            self,
            "Enviar carpeta a la Papelera",
            f"¿Enviar la carpeta «{name}» completa a la Papelera de reciclaje?",
            [("Enviar a la Papelera", QMessageBox.ButtonRole.DestructiveRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Warning,
            f"Ubicación: {os.path.dirname(os.path.normpath(folder))}\n{detail}. "
            f"Se borrarán {plural(contents.files, 'archivo')}.\n\n"
            f"{plural(in_library, 'canción', 'canciones')} de la biblioteca se quitan también de las playlists. "
            "Se puede recuperar desde la Papelera de Windows.",
        ) != 0:
            return
        try:
            removed = self.ops.trash_folder(folder, self.library)
        except file_manager.FileManagerError as exc:
            self._file_error("Enviar carpeta a la Papelera", exc)
            return
        self.statusBar().showMessage(
            f"Carpeta «{name}» enviada a la Papelera ({plural(removed, 'canción quitada', 'canciones quitadas')} de la biblioteca).", 8000
        )

    def startup_checks(self) -> None:
        """Al abrir, en este orden: ofrecer deshacer lo interrumpido y después limpiar lo que falta
        (si fuera al revés, se quitarían canciones que deshacer devolvería a su sitio)."""
        self.check_interrupted_review()
        for path in library_cleanup.remove_leftover_temps(self.library):
            log.info("Temporal sobrante borrado (corte o cierre a mitad de una operación): %s", path)
        self.remove_missing_tracks()

    def remove_missing_tracks(self) -> None:
        """Quita de la lista las canciones (y con ellas las carpetas) que ya no existen en el disco."""
        if not self.prefs.remove_missing_on_start or not self.library:
            return
        plan = library_cleanup.plan_missing(self.library, self.ops.undoable_track_ids())
        to_remove: list[Track] = []
        if plan.remove:
            # Siempre se pregunta (antes las pocas se quitaban solas): quitar también las saca de las
            # playlists, y una carpeta renombrada por fuera del programa no debe costar las playlists.
            shown = "\n".join(f"• {t.title} — {t.artist}" for t in plan.remove[:10])
            if len(plan.remove) > 10:
                shown += f"\n… y {len(plan.remove) - 10} más"
            if ask(
                self,
                "Canciones que no se encuentran",
                f"{plural(len(plan.remove), 'canción de tu biblioteca ya no se encuentra', 'canciones de tu biblioteca ya no se encuentran')} en el disco.",
                [("Conservarlas", QMessageBox.ButtonRole.RejectRole),
                 ("Quitarlas de la lista", QMessageBox.ButtonRole.DestructiveRole)],
                QMessageBox.Icon.Question,
                f"{shown}\n\nQuitarlas no borra ningún archivo: solo las saca de la biblioteca y de las playlists (se "
                "hace un respaldo antes). Si las moviste, consérvalas y usa clic derecho → «Localizar archivo…». "
                "Esta revisión se puede desactivar en Preferencias.",
            ) == 1:
                to_remove = list(plan.remove)
        for root, tracks in plan.suspicious.items():
            on_root = sum(1 for t in self.library if library_cleanup.location_root(t.path) == root)
            if ask(
                self,
                "Canciones que no se encuentran",
                f"En {root} no se encuentran {len(tracks)} de {on_root} canciones de tu biblioteca.",
                [("Conservarlas", QMessageBox.ButtonRole.RejectRole),
                 ("Quitarlas de la lista", QMessageBox.ButtonRole.DestructiveRole)],
                QMessageBox.Icon.Warning,
                "Son muchas a la vez: puede que el disco haya cambiado de letra o que la carpeta se haya movido. "
                "Si es así, consérvalas y usa clic derecho → «Localizar archivo…». Quitarlas no borra ningún "
                "archivo: solo las saca de la biblioteca y de las playlists (se hace un respaldo antes).",
            ) == 1:
                to_remove.extend(tracks)
        relocated = 0
        for folder, tracks in plan.missing_folders.items():
            moved, leftover = self._ask_missing_folder(folder, tracks)
            relocated += moved
            to_remove.extend(leftover)
        if relocated:
            self._on_files_changed()
        removed = self.ops.remove_missing(to_remove)
        if relocated:
            self.statusBar().showMessage(f"Se reubicaron {plural(relocated, 'canción', 'canciones')}.", 10000)
        if removed:
            self.statusBar().showMessage(
                f"Se quitaron de la lista {plural(removed, 'canción', 'canciones')} cuyo archivo ya no existe "
                "(la lista está en el registro; se hizo un respaldo antes).", 15000
            )
        elif plan.disconnected:
            kept = sum(plan.disconnected.values())
            self.statusBar().showMessage(
                f"{plural(kept, 'canción', 'canciones')} de {', '.join(plan.disconnected)} no se "
                f"{'encuentra' if kept == 1 else 'encuentran'}: el disco no está conectado, se conservan.", 15000
            )

    def _ask_missing_folder(self, folder: str, tracks: list[Track]) -> tuple[int, list[Track]]:
        """Falta una carpeta entera: ¿se movió? Devuelve (reubicadas, las que hay que quitar)."""
        while True:
            choice = ask(
                self,
                "Carpeta que no se encuentra",
                f"La carpeta «{folder}» ya no existe y tenía {plural(len(tracks), 'canción', 'canciones')} de tu biblioteca.",
                [("Buscar dónde está…", QMessageBox.ButtonRole.AcceptRole),
                 ("Quitarlas de la lista", QMessageBox.ButtonRole.DestructiveRole),
                 ("Conservarlas", QMessageBox.ButtonRole.RejectRole)],
                QMessageBox.Icon.Question,
                "Si la moviste o le cambiaste el nombre, elige dónde está ahora y las canciones se reubican solas "
                "(con sus playlists). Quitarlas no borra ningún archivo: solo las saca de la lista.",
            )
            if choice == 1:
                return 0, tracks
            if choice != 0:
                return 0, []
            new_folder = QFileDialog.getExistingDirectory(
                self, f"¿Dónde está ahora «{os.path.basename(folder)}»?", os.path.dirname(folder)
            )
            if not new_folder:
                continue
            changes = library_cleanup.relocate_folder(tracks, folder, new_folder)
            if not changes:
                QMessageBox.information(
                    self, "Carpeta que no se encuentra",
                    "En esa carpeta no están las canciones que faltan. Elige la carpeta que reemplaza a "
                    f"«{os.path.basename(folder)}» (la que contiene sus subcarpetas y archivos).",
                )
                continue
            # Una canción que ya está en la biblioteca con la ruta nueva (la carpeta se importó otra vez)
            # no se reubica: chocaría con esa entrada. Queda entre las que faltan.
            changes = [(tid, p) for tid, p in changes if self.db.track_id_for_path(p) in (None, tid)]
            backup.create_backup(self.db.conn, "antes-de-reubicar")
            try:
                self.db.update_track_paths(changes)
            except sqlite3.Error as exc:
                log.error("No se pudo reubicar %s: %s", folder, exc)
                QMessageBox.warning(self, "Carpeta que no se encuentra", f"No se pudo reubicar la carpeta: {exc}")
                return 0, []
            found = {track_id for track_id, _p in changes}
            log.info("Carpeta reubicada: %s → %s (%d canciones)", folder, new_folder, len(changes))
            still = [t for t in tracks if t.id not in found]
            if still:
                QMessageBox.information(
                    self, "Carpeta reubicada",
                    f"Se reubicaron {plural(len(changes), 'canción', 'canciones')}. "
                    f"{plural(len(still), 'no estaba', 'no estaban')} en la carpeta nueva y se "
                    f"{'conserva' if len(still) == 1 else 'conservan'} en gris para localizarlas a mano.",
                )
            return len(changes), []

    def check_interrupted_review(self) -> None:
        """Al abrir: si una operación sobre archivos quedó a medias (cierre inesperado), ofrecer deshacerla."""
        for entry in self.ops.interrupted():
            if self._ask_recover(entry.title, entry.count):
                outcome = self.ops.undo(entry)
                QMessageBox.information(self, "Operación interrumpida", outcome.message)

    def _ask_recover(self, what: str, count: int) -> bool:
        return ask(
            self,
            "Operación interrumpida",
            f"La última {what} se interrumpió con {plural(count, 'archivo')} ya tocado(s).",
            [("Deshacerla ahora", QMessageBox.ButtonRole.AcceptRole), ("Más tarde", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Warning,
            "Recomendado: deshacerla ahora para dejar cada archivo en su sitio. Si eliges «Más tarde», puedes "
            "hacerlo desde Herramientas → Historial de cambios en archivos.",
        ) == 0

    def _open_preferences(self) -> None:
        if self._run_dialog(PreferencesDialog(self.prefs, self)):
            if self.prefs.theme != theme.mode():
                theme.apply(QApplication.instance(), self.prefs.theme)
            state = "activada" if self.prefs.ask_titles_on_import else "desactivada"
            self.statusBar().showMessage(
                f"Preferencias guardadas. Tema: {theme.current().name}. Revisión de títulos al importar: {state}.", 6000
            )

    # ================================================================== tema

    def _on_theme_changed(self) -> None:
        self.player_bar.refresh_icons()
        self.sidebar.refresh_icons()
        self.content.refresh_icons()

    def _on_system_scheme_changed(self, _scheme) -> None:
        # Solo en modo automático y si de verdad cambia la paleta (evita aplicar dos veces).
        if theme.mode() == theme.MODE_AUTO and theme.resolve(theme.MODE_AUTO) is not theme.current():
            theme.apply(QApplication.instance(), theme.MODE_AUTO)

    # ================================================================== playlists

    def _create_playlist(self) -> int | None:
        dialog = PlaylistNameDialog(
            "Nueva playlist", "Nombre de la playlist:", "", self.db.create_playlist, self
        )
        if not dialog.exec() or dialog.result_value is None:
            return None
        playlist = dialog.result_value
        self.sidebar.set_playlists(self.db.playlists())
        self.statusBar().showMessage(f"Playlist «{playlist.name}» creada.", 5000)
        return playlist.id

    def _rename_playlist(self, playlist_id: int) -> None:
        playlist = self.db.playlist(playlist_id)
        if playlist is None:
            return
        dialog = PlaylistNameDialog(
            "Renombrar playlist",
            "Nuevo nombre:",
            playlist.name,
            lambda name: self.db.rename_playlist(playlist_id, name),
            self,
        )
        if dialog.exec():
            self.sidebar.set_playlists(self.db.playlists())
            if self.sidebar.current_view() == ("playlist", playlist_id):
                self.content.set_title(dialog.result_value)

    def _delete_playlist(self, playlist_id: int) -> None:
        playlist = self.db.playlist(playlist_id)
        if playlist is None:
            return
        choice = ask(
            self,
            "Eliminar playlist",
            f"¿Eliminar la playlist «{playlist.name}»?",
            [("Eliminar", QMessageBox.ButtonRole.DestructiveRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Warning,
            "Solo se borra la lista. Las canciones siguen en la biblioteca y los archivos no se tocan.",
        )
        if choice != 0:
            return
        was_selected = self.sidebar.current_view() == ("playlist", playlist_id)
        if playlist.track_count:
            self._safety_backup("antes-de-eliminar-playlist")
        self.db.delete_playlist(playlist_id)
        self.sidebar.set_playlists(self.db.playlists())
        if was_selected:
            self.sidebar.select_library("songs")
        self.statusBar().showMessage(f"Playlist «{playlist.name}» eliminada.", 5000)

    def _rename_selected_playlist(self) -> None:
        pid = self.sidebar.current_playlist_id()
        if pid is not None:
            self._rename_playlist(pid)

    def _delete_selected_playlist(self) -> None:
        pid = self.sidebar.current_playlist_id()
        if pid is not None:
            self._delete_playlist(pid)

    def _update_playlist_actions(self) -> None:
        has = self.sidebar.current_view()[0] == "playlist"
        self.act_rename.setEnabled(has)
        self.act_delete.setEnabled(has)

    def _play_playlist(self, playlist_id: int) -> None:
        tracks = self.db.playlist_tracks(playlist_id)
        if not tracks:
            self.statusBar().showMessage("La playlist está vacía.", 4000)
            return
        start = random.randrange(len(tracks)) if self.player.shuffle else 0
        self._on_play_requested(tracks, start)

    def _show_add_menu(self, tracks: list[Track], pos: QPoint) -> None:
        if not tracks:
            return
        ids = [t.id for t in tracks]
        menu = QMenu(self)
        title = menu.addAction("Agregar a playlist")
        title.setEnabled(False)
        menu.addSeparator()
        playlists = self.db.playlists()
        current_view = self.sidebar.current_view()
        for playlist in playlists:
            contained = self.db.playlist_contains(playlist.id, ids)
            label = playlist.name
            if contained and len(contained) == len(set(ids)):
                label += "   (ya incluida)" if len(set(ids)) == 1 else "   (ya incluidas)"
            action = menu.addAction(icon("playlist", TEXT, 16), label)
            action.triggered.connect(partial(self._add_tracks_to_playlist, playlist.id, tracks))
            if current_view == ("playlist", playlist.id):
                action.setToolTip("Playlist que estás viendo")
        if not playlists:
            empty = menu.addAction("Todavía no hay playlists")
            empty.setEnabled(False)
        menu.addSeparator()
        new_action = menu.addAction(icon("add", TEXT, 16), "Nueva playlist…")
        new_action.triggered.connect(lambda: self._add_to_new_playlist(tracks))
        menu.exec(pos)
        menu.deleteLater()  # si no, cada clic derecho deja un menú en memoria

    def _add_to_new_playlist(self, tracks: list[Track]) -> None:
        pid = self._create_playlist()
        if pid is not None:
            self._add_tracks_to_playlist(pid, tracks)

    def _add_tracks_to_playlist(self, playlist_id: int, tracks: list[Track], _checked: bool = False) -> None:
        playlist = self.db.playlist(playlist_id)
        if playlist is None:
            return
        ids = list(dict.fromkeys(t.id for t in tracks))  # sin repetidos dentro de la selección
        existing = self.db.playlist_contains(playlist_id, ids)
        allow_duplicates = False
        if existing:
            if len(ids) == 1:
                choice = ask(
                    self,
                    "Canción ya incluida",
                    f"«{tracks[0].title}» ya está en «{playlist.name}».",
                    [
                        ("No agregar", QMessageBox.ButtonRole.RejectRole),
                        ("Agregar repetida", QMessageBox.ButtonRole.AcceptRole),
                    ],
                    informative="¿Quieres que aparezca otra vez en la playlist?",
                )
                if choice != 1:
                    return
                allow_duplicates = True
            elif len(existing) == len(ids):
                choice = ask(
                    self,
                    "Canciones ya incluidas",
                    f"Las {len(ids)} canciones ya están en «{playlist.name}».",
                    [
                        ("No agregar", QMessageBox.ButtonRole.RejectRole),
                        ("Agregar repetidas", QMessageBox.ButtonRole.AcceptRole),
                    ],
                )
                if choice != 1:
                    return
                allow_duplicates = True
            else:
                choice = ask(
                    self,
                    "Algunas canciones ya están",
                    f"{len(existing)} de las {len(ids)} canciones ya están en «{playlist.name}».",
                    [
                        ("Agregar solo las nuevas", QMessageBox.ButtonRole.AcceptRole),
                        ("Agregar todas (con repeticiones)", QMessageBox.ButtonRole.AcceptRole),
                        ("Cancelar", QMessageBox.ButtonRole.RejectRole),
                    ],
                )
                if choice not in (0, 1):
                    return
                allow_duplicates = choice == 1

        added = self.db.add_to_playlist(playlist_id, ids, allow_duplicates=allow_duplicates)
        self.sidebar.set_playlists(self.db.playlists())
        if self.sidebar.current_view() == ("playlist", playlist_id) and not self.player_bar.search.text():
            self._render_playlist(playlist_id)
        self.statusBar().showMessage(
            f"Se {'agregó' if added == 1 else 'agregaron'} {plural(added, 'canción', 'canciones')} "
            f"a «{playlist.name}».",
            6000,
        )

    def _remove_from_playlist(self, tracks: list[Track]) -> None:
        kind, playlist_id = self.sidebar.current_view()
        if kind != "playlist" or playlist_id is None:
            return
        entries = [t.entry_id for t in tracks if t.entry_id is not None]
        if len(entries) > 1:
            choice = ask(
                self,
                "Quitar de la playlist",
                f"¿Quitar {len(entries)} canciones de la playlist?",
                [("Quitar", QMessageBox.ButtonRole.AcceptRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
                informative="Las canciones siguen en la biblioteca y los archivos no se tocan.",
            )
            if choice != 0:
                return
        removed = self.db.remove_playlist_entries(entries)
        self.sidebar.set_playlists(self.db.playlists())
        self._render_playlist(playlist_id)
        self.statusBar().showMessage(
            f"Se {'quitó' if removed == 1 else 'quitaron'} {plural(removed, 'canción', 'canciones')} "
            "de la playlist (los archivos no se tocaron).",
            6000,
        )

    def _remove_from_library(self, tracks: list[Track]) -> None:
        ids = {t.id for t in tracks}
        if not ids:
            return
        what = f"«{tracks[0].title}»" if len(ids) == 1 else plural(len(ids), "canción", "canciones")
        choice = ask(
            self,
            "Quitar de la biblioteca",
            f"¿Quitar {what} de la biblioteca?",
            [("Quitar", QMessageBox.ButtonRole.DestructiveRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Warning,
            "También se quitarán de tus playlists. Los archivos originales NO se borran del disco; "
            "podrás importarlos de nuevo cuando quieras.",
        )
        if choice != 0:
            return
        if len(ids) >= 10:
            self._safety_backup("antes-de-quitar-canciones")
        self.player.remove_tracks(ids)
        removed = self.db.remove_tracks(ids)
        self._reload_library()
        self.sidebar.set_playlists(self.db.playlists())
        self._refresh_view()
        self.statusBar().showMessage(
            f"Se {'quitó' if removed == 1 else 'quitaron'} {plural(removed, 'canción', 'canciones')} de la biblioteca.",
            6000,
        )

    # ================================================================== archivos faltantes

    def _handle_missing(self, track: Track) -> None:
        choice = ask(
            self,
            "Archivo no encontrado",
            f"No se encuentra el archivo de «{track.title}».",
            [
                ("Localizar archivo…", QMessageBox.ButtonRole.AcceptRole),
                ("Quitar de la biblioteca", QMessageBox.ButtonRole.DestructiveRole),
                ("Cancelar", QMessageBox.ButtonRole.RejectRole),
            ],
            QMessageBox.Icon.Warning,
            f"Ubicación guardada:\n{track.path}\n\nPuede que se haya movido, renombrado o eliminado, "
            "o que esté en una unidad (USB, red) que no está conectada.",
        )
        if choice == 0:
            self._locate_track(track)
        elif choice == 1:
            self._remove_from_library([track])

    def _review_first_missing(self) -> None:
        track = self.content.first_missing_track()
        if track is not None:
            self._handle_missing(track)

    def _locate_track(self, track: Track) -> None:
        old_dir = os.path.dirname(track.path)
        start = old_dir if os.path.isdir(old_dir) else self.settings.value("import/last_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(
            self, f"Localizar «{track.title}»", start, f"{AUDIO_FILE_FILTER};;Todos los archivos (*.*)"
        )
        if not path:
            return
        if not self._relocate(track, path, show_errors=True):
            return

        # Si faltan otras canciones de la misma carpeta, probar la nueva carpeta.
        new_dir = os.path.dirname(path)
        candidates = [
            t
            for t in self.library
            if t.id != track.id
            and not t.check_available()
            and path_key(os.path.dirname(t.path)) == path_key(old_dir)
            and os.path.isfile(os.path.join(new_dir, os.path.basename(t.path)))
        ]
        fixed = 1
        if candidates:
            choice = ask(
                self,
                "Otras canciones encontradas",
                f"En la nueva carpeta también están otras {plural(len(candidates), 'canción', 'canciones')} "
                "que faltaban.",
                [("Actualizar también", QMessageBox.ButtonRole.AcceptRole), ("No", QMessageBox.ButtonRole.RejectRole)],
                informative=f"Carpeta: {new_dir}",
            )
            if choice == 0:
                for other in candidates:
                    if self._relocate(other, os.path.join(new_dir, os.path.basename(other.path)), show_errors=False):
                        fixed += 1

        self._reload_library()
        self.player.update_tracks({t.id: t for t in self.library})
        self._refresh_view()
        self.statusBar().showMessage(
            f"Ubicación actualizada para {plural(fixed, 'canción', 'canciones')}. Sus playlists se conservan.",
            8000,
        )

    def _relocate(self, track: Track, path: str, show_errors: bool) -> bool:
        scanned, failure = scan_file(path)
        if scanned is None:
            if show_errors:
                reason = failure.reason if failure else "Error desconocido."
                QMessageBox.warning(
                    self, "No se pudo usar el archivo", f"«{os.path.basename(path)}» no se puede usar:\n\n{reason}"
                )
            return False
        try:
            self.db.relocate_track(
                track.id, scanned.path, scanned.metadata, scanned.cover_hash, scanned.cover_bytes
            )
        except DuplicatePathError as exc:
            if show_errors:
                QMessageBox.warning(self, "Archivo ya importado", str(exc))
            return False
        return True

    def _show_in_folder(self, track: Track) -> None:
        if not track.check_available():
            self._handle_missing(track)
            return
        if sys.platform == "win32":
            # Una sola cadena: con «/select,» separado, una ruta con comas y sin espacios abría otra carpeta.
            subprocess.Popen(f'"{_EXPLORER}" /select,"{os.path.normpath(track.path)}"')
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(track.path)))

    # ================================================================== reproducción

    def _on_play_requested(self, tracks: list[Track], index: int) -> None:
        if not tracks or not 0 <= index < len(tracks):
            return
        if not tracks[index].check_available():
            self.content.refresh_track(tracks[index])
            self._handle_missing(tracks[index])
            return
        self.player.play_queue(tracks, index)

    def _on_shuffle_play(self, tracks: list[Track]) -> None:
        available = [i for i, t in enumerate(tracks) if t.check_available()]
        if not available:
            if tracks:
                QMessageBox.information(self, "Sin canciones disponibles", "Ninguna canción de esta lista está disponible en el disco.")
            return
        self.player.set_shuffle(True)
        self.player.play_queue(tracks, random.choice(available))

    def _toggle_play(self) -> None:
        if self.player.current_track is not None:
            self.player.toggle_play()
            return
        tracks = self.content.visible_tracks()
        selected = self.content.selected_tracks()
        start = tracks.index(selected[0]) if selected and selected[0] in tracks else 0
        if tracks:
            self._on_play_requested(tracks, start)

    def _nudge_volume(self, delta: int) -> None:
        slider = self.player_bar.volume
        slider.setValue(max(0, min(100, slider.value() + delta)))

    def _on_track_changed(self, track: Track | None) -> None:
        self.player_bar.set_track(track)
        self.content.set_current_track(track.id if track else None)
        if track is None:
            self.setWindowTitle(APP_NAME)
            return
        self.setWindowTitle(f"{track.title} — {track.artist} · {APP_NAME}")

    def _on_track_started(self, track: Track) -> None:
        """La canción empezó a sonar de verdad (no basta con cargarla, p. ej. al terminar la cola)."""
        played_at = self.db.mark_played(track.id)
        for cached in self.library:
            if cached.id == track.id:
                cached.last_played_at = played_at
                break

    def _on_duration_changed(self, duration: int) -> None:
        if duration <= 0:
            return
        self.player_bar.set_duration(duration)
        track = self.player.current_track
        if track is not None and track.duration_ms <= 0:
            # mutagen no pudo calcularla al importar: se guarda la que informa Qt.
            track.duration_ms = duration
            self.db.update_duration(track.id, duration)
            for cached in self.library:
                if cached.id == track.id:
                    cached.duration_ms = duration
            self.content.refresh_track(track)

    def _on_player_error(self, track: Track | None, message: str) -> None:
        self.statusBar().showMessage(message, 10000)
        details = f"\n\nCanción: {track.title}\nArchivo: {track.path}" if track else ""
        QMessageBox.warning(self, "No se puede reproducir", message + details)

    def _on_track_skipped(self, track: Track) -> None:
        self.content.refresh_track(track)
        self.statusBar().showMessage(
            f"Se omitió «{track.title}»: no se encuentra el archivo ({track.path}).", 8000
        )

    def _on_shuffle_changed(self, enabled: bool) -> None:
        self.player_bar.set_shuffle(enabled)
        self.act_shuffle.blockSignals(True)
        self.act_shuffle.setChecked(enabled)
        self.act_shuffle.blockSignals(False)

    def _on_repeat_changed(self, mode: int) -> None:
        self.player_bar.set_repeat(mode)
        text = {RepeatMode.OFF: "desactivada", RepeatMode.ALL: "toda la lista", RepeatMode.ONE: "una canción"}
        if not getattr(self, "_restoring", False):
            self.statusBar().showMessage(f"Repetición: {text[RepeatMode(mode)]}", 3000)

    # ================================================================== abrir archivos desde Windows

    def open_files(self, paths: list[str]) -> None:
        """Archivos recibidos al arrancar o desde «Abrir con»: se importan si hace falta y se reproducen."""
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        if not paths:
            return
        log.info("Abrir %d archivo(s) desde Windows", len(paths))
        new, problems = [], []
        for path in paths:
            if self.db.track_id_for_path(path) is not None:
                continue
            if in_skipped_folder(path):
                problems.append(f"• {os.path.basename(path)}: está en una carpeta del programa (originales convertidos o copias para revisar)")
                continue
            scanned, failure = scan_file(path)
            if scanned is None:
                problems.append(f"• {os.path.basename(path)}: {failure.reason if failure else 'error desconocido'}")
            else:
                new.append(scanned)
        if new:
            self.db.add_tracks(new)
            self._reload_library()
            self._refresh_view()
            self.statusBar().showMessage(
                f"Se agregaron {plural(len(new), 'canción', 'canciones')} a la biblioteca.", 6000
            )
        by_key = {path_key(t.path): t for t in self.library}
        tracks = [by_key[path_key(p)] for p in paths if path_key(p) in by_key]
        if tracks:
            # Windows abre una copia por archivo: las que llegan unos segundos después de otra apertura
            # se agregan a la cola en vez de reemplazarla (si no, solo sonaría la última).
            now = time.monotonic()
            if now - getattr(self, "_last_open_at", -100.0) < 4.0 and self.player.has_queue:
                self.player.append_tracks(tracks)
                self.statusBar().showMessage(f"Agregadas a la cola: {plural(len(tracks), 'canción', 'canciones')}.", 5000)
            else:
                self._on_play_requested(tracks, 0)
            self._last_open_at = now
        if problems:
            QMessageBox.warning(self, "No se pudieron abrir", "\n".join(problems))

    # ================================================================== sonido

    def _check_system_volume(self, playing: bool) -> None:
        """Si la música suena en el programa pero Windows está silenciado o a 0 %, avisarlo."""
        if not playing:
            return
        volume = win_audio.read_system_volume()
        if volume is not None and volume.silent:
            reason = "silenciado" if volume.muted else "al 0 %"
            self.statusBar().showMessage(
                f"Atención: el sonido de Windows está {reason}: súbelo con el icono del altavoz de la barra de tareas.", 15000
            )
            log.warning("Reproduciendo con el sonido de Windows %s", reason)

    # ================================================================== ecualizador

    def _restore_equalizer(self) -> None:
        state = self.prefs.equalizer()
        settings = EqSettings(tuple(state["gains"]), state["preamp"], state["prevent_clipping"])
        self._apply_equalizer(bool(state["enabled"]), settings)

    def _apply_equalizer(self, enabled: bool, settings: EqSettings) -> None:
        self.player.set_equalizer(enabled, settings)
        self.player_bar.set_equalizer_on(enabled)

    def _open_equalizer(self) -> None:
        """Ventana del ecualizador (no bloquea: se puede dejar abierta mientras suena la música)."""
        dialog = getattr(self, "_eq_dialog", None)
        if dialog is None:
            dialog = EqualizerDialog(self.prefs, self._apply_equalizer, self)
            self._eq_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _test_sound(self) -> None:
        """Toca un tono corto por el mismo camino que las canciones y muestra el diagnóstico."""
        tone = data_dir() / "tono-de-prueba.wav"
        if not tone.exists():
            import math
            import struct
            import wave

            rate = 44100
            with wave.open(str(tone), "wb") as out:
                out.setnchannels(2)
                out.setsampwidth(2)
                out.setframerate(rate)
                frames = bytearray()
                for i in range(int(rate * 1.2)):
                    fade = min(1.0, i / 2000, (rate * 1.2 - i) / 2000)
                    value = int(9000 * fade * math.sin(2 * math.pi * 523.25 * i / rate))  # do (C5)
                    frames += struct.pack("<hh", value, value)
                out.writeframes(bytes(frames))
        was_playing = self.player.is_playing
        if was_playing:
            self.player.pause()
        for old in (getattr(self, "_tone_player", None), getattr(self, "_tone_output", None)):
            if old is not None:  # la prueba anterior: se libera en vez de acumular reproductores
                if isinstance(old, QMediaPlayer):
                    old.stop()
                old.deleteLater()
        self._tone_player = QMediaPlayer(self)
        self._tone_output = QAudioOutput(self.player.output_device(), self)
        self._tone_output.setVolume(max(0.3, self.player_bar.volume.value() / 100))
        self._tone_player.setAudioOutput(self._tone_output)
        self._tone_player.setSource(QUrl.fromLocalFile(str(tone)))
        self._tone_player.play()

        volume = win_audio.read_system_volume()
        if volume is None:
            windows = "no se pudo leer"
        else:
            windows = f"{volume.percent} %" + (" (SILENCIADO)" if volume.muted else "")
        program = "silenciado" if self.player_bar.btn_mute.isChecked() else f"{self.player_bar.volume.value()} %"
        # En el Mezclador de Windows el programa instalado aparece con su nombre; desde el código, como Python.
        mixer_name = "Reproductor de Música" if getattr(sys, "frozen", False) else os.path.splitext(os.path.basename(sys.executable))[0]
        log.info("Prueba de sonido: salida=%s, Windows=%s, programa=%s", self.player.output_name(), windows, program)
        QMessageBox.information(
            self,
            "Probar sonido",
            "Se está tocando un tono corto.\n\n"
            f"Salida de audio: {self.player.output_name()}\n"
            f"Volumen de Windows: {windows}\n"
            f"Volumen del programa: {program}\n\n"
            "Si no lo escuchas:\n"
            "• Revisa que esa salida sea la de tus altavoces o auriculares (icono del altavoz de la barra de tareas).\n"
            f"• Abre el Mezclador de volumen de Windows y comprueba que «{mixer_name}» no esté silenciado.\n"
            "• Si usas Bluetooth o HDMI, conéctalos antes de reproducir o vuelve a elegirlos como salida.",
        )
        if was_playing:
            self.player.play()

    # ================================================================== respaldos y registro

    def _safety_backup(self, reason: str) -> None:
        """Respaldo antes de una operación difícil de deshacer. Si falla, se registra y se sigue."""
        if backup.create_backup(self.db.conn, reason) is None:
            self.statusBar().showMessage("Aviso: no se pudo crear el respaldo previo (detalles en el registro).", 8000)

    def _backup_now(self) -> None:
        path = backup.create_backup(self.db.conn, "manual")
        if path is None:
            QMessageBox.warning(self, "Respaldo", f"No se pudo crear el respaldo. Detalles en:\n{error_log.log_path()}")
        else:
            QMessageBox.information(
                self, "Respaldo",
                f"Respaldo creado y verificado:\n{path}\n\n"
                f"Se conservan los {backup.KEEP_RECENT} más recientes y uno por semana de las últimas {backup.KEEP_WEEKS} semanas.",
            )

    def _open_backup_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(backup.backup_dir())))

    def _open_error_log(self) -> None:
        path = error_log.log_path()
        if not path.exists():
            QMessageBox.information(self, "Registro de errores", "Todavía no hay nada registrado.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ================================================================== otros

    def _about(self) -> None:
        QMessageBox.about(
            self,
            f"Acerca de {APP_NAME}",
            f"<b>{APP_NAME}</b> — versión {__version__}<br>Reproductor de archivos de audio locales hecho con Python, "
            f"PySide6 y Qt Multimedia.<br><br>Autor: <b>{AUTHOR_NAME}</b><br>"
            f"Contacto: <a href=\"mailto:{CONTACT_EMAIL}\">{CONTACT_EMAIL}</a><br><br>"
            f"<b>Aviso:</b> {DISCLAIMER}<br><br>La biblioteca y las playlists se guardan en:<br>"
            f"<code>{self.db.path}</code><br><br>El programa no incluye ni descarga música: "
            "solo reproduce los archivos que tú eliges.<br><br>"
            "Software libre bajo la licencia <b>GNU GPL versión 3 o posterior</b>: puedes usarlo, copiarlo, "
            "modificarlo y compartirlo, siempre que entregues también su código fuente bajo la misma licencia. "
            "Se distribuye sin ninguna garantía. El código fuente se entrega junto con el instalador. Licencias "
            f"de los componentes de terceros:<br><code>{resource_path('licencias')}</code>",
        )
