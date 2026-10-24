"""Barra lateral: vistas de la biblioteca y playlists del usuario."""

from __future__ import annotations

import os

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSplitter,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..folders import FolderNode, display_name, folder_key
from ..models import Playlist
from ..utils import plural
from . import theme
from .icons import MUTED, TEXT, icon

LIBRARY_VIEWS = [
    ("recent", "Recientes", "recent"),
    ("artists", "Artistas", "artist"),
    ("albums", "Álbumes", "album"),
    ("songs", "Canciones", "song"),
]

ITEM_HEIGHT = 32
_ID_ROLE = Qt.ItemDataRole.UserRole


class Sidebar(QFrame):
    view_selected = Signal(str, object)  # tipo de vista, id de playlist o None
    create_playlist_requested = Signal()
    rename_playlist_requested = Signal(int)
    delete_playlist_requested = Signal(int)
    play_playlist_requested = Signal(int)
    import_folder_requested = Signal()
    play_folder_requested = Signal(str, bool)  # ruta, aleatorio
    folder_add_to_playlist_requested = Signal(str, QPoint)
    folder_show_in_explorer_requested = Signal(str)
    folder_rescan_requested = Signal(str)
    folder_rename_requested = Signal(str)
    folder_create_requested = Signal(str)  # carpeta donde crear una subcarpeta
    folder_trash_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setMinimumWidth(190)
        self.setMaximumWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(4)

        layout.addWidget(self._section_label("Biblioteca"))
        self.library_list = self._make_list()
        self.library_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for kind, label, icon_name in LIBRARY_VIEWS:
            item = QListWidgetItem(icon(icon_name, MUTED, 18), label)
            item.setData(_ID_ROLE, kind)
            item.setSizeHint(QSize(0, ITEM_HEIGHT))
            self.library_list.addItem(item)
        self.library_list.setFixedHeight(ITEM_HEIGHT * len(LIBRARY_VIEWS) + 4 * len(LIBRARY_VIEWS))
        layout.addWidget(self.library_list)
        layout.addSpacing(12)

        # Playlists y Carpetas comparten el espacio restante; el divisor permite repartirlo.
        sections = QSplitter(Qt.Orientation.Vertical)
        sections.setChildrenCollapsible(False)
        sections.setHandleWidth(10)
        layout.addWidget(sections, 1)

        playlists_panel = QWidget()
        playlists_layout = QVBoxLayout(playlists_panel)
        playlists_layout.setContentsMargins(0, 0, 0, 0)
        playlists_layout.setSpacing(4)
        self.btn_new = self._header_button("Nueva playlist", self.create_playlist_requested.emit)
        playlists_layout.addLayout(self._section_header("Playlists", self.btn_new))

        self.playlist_list = self._make_list()
        self.playlist_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_list.customContextMenuRequested.connect(self._playlist_menu)
        self.playlist_list.itemDoubleClicked.connect(
            lambda item: self.play_playlist_requested.emit(item.data(_ID_ROLE))
        )
        playlists_layout.addWidget(self.playlist_list, 1)

        self.empty_playlists = QLabel("Aún no tienes playlists.\nPulsa + para crear una.")
        self.empty_playlists.setObjectName("SectionLabel")
        self.empty_playlists.setWordWrap(True)
        playlists_layout.addWidget(self.empty_playlists)
        sections.addWidget(playlists_panel)

        folders_panel = QWidget()
        folders_layout = QVBoxLayout(folders_panel)
        folders_layout.setContentsMargins(0, 0, 0, 0)
        folders_layout.setSpacing(4)
        self.btn_add_folder = self._header_button("Importar carpeta…", self.import_folder_requested.emit, "folder_plus")
        folders_layout.addLayout(self._section_header("Carpetas", self.btn_add_folder))

        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setIconSize(QSize(18, 18))
        self.folder_tree.setIndentation(14)
        self.folder_tree.setUniformRowHeights(True)
        self.folder_tree.setAnimated(True)
        self.folder_tree.setExpandsOnDoubleClick(False)  # doble clic = reproducir la carpeta
        self.folder_tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.folder_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.folder_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_tree.customContextMenuRequested.connect(self._folder_menu)
        self.folder_tree.itemDoubleClicked.connect(
            lambda item, _col: self.play_folder_requested.emit(item.data(0, _ID_ROLE), False)
        )
        folders_layout.addWidget(self.folder_tree, 1)

        self.empty_folders = QLabel("Las carpetas de tu música aparecerán aquí al importarla.")
        self.empty_folders.setObjectName("SectionLabel")
        self.empty_folders.setWordWrap(True)
        folders_layout.addWidget(self.empty_folders)
        sections.addWidget(folders_panel)
        sections.setSizes([180, 320])
        self.sections = sections

        # Atajos sobre la playlist seleccionada
        rename = QAction(self.playlist_list)
        rename.setShortcut(QKeySequence(Qt.Key.Key_F2))
        rename.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        rename.triggered.connect(self._rename_current)
        delete = QAction(self.playlist_list)
        delete.setShortcut(QKeySequence(QKeySequence.StandardKey.Delete))
        delete.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        delete.triggered.connect(self._delete_current)
        self.playlist_list.addActions([rename, delete])

        self.library_list.currentItemChanged.connect(self._on_library_changed)
        self.playlist_list.currentItemChanged.connect(self._on_playlist_changed)
        self.folder_tree.currentItemChanged.connect(self._on_folder_changed)

    # ------------------------------------------------------------------ construcción

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("SectionLabel")
        return label

    def _section_header(self, text: str, button: QToolButton) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._section_label(text))
        header.addStretch(1)
        header.addWidget(button)
        return header

    @staticmethod
    def _header_button(tooltip: str, slot, icon_name: str = "add") -> QToolButton:
        button = QToolButton()
        button.setIcon(icon(icon_name, MUTED, 16))
        button.setProperty("icon_name", icon_name)
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        # Lambda a propósito: clicked envía «checked» y las señales de destino no aceptan argumentos.
        button.clicked.connect(lambda: slot())
        return button

    @staticmethod
    def _make_list() -> QListWidget:
        widget = QListWidget()
        widget.setIconSize(QSize(18, 18))
        widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        widget.setTextElideMode(Qt.TextElideMode.ElideRight)
        return widget

    # ------------------------------------------------------------------ API pública

    def set_playlists(self, playlists: list[Playlist]) -> None:
        """Recarga la lista conservando la selección actual si sigue existiendo."""
        selected = self.current_playlist_id()
        self.playlist_list.blockSignals(True)
        self.playlist_list.clear()
        for playlist in playlists:
            item = QListWidgetItem(icon("playlist", MUTED, 18), playlist.name)
            item.setData(_ID_ROLE, playlist.id)
            item.setToolTip(f"{playlist.name}\n{plural(playlist.track_count, 'canción', 'canciones')}")
            item.setSizeHint(QSize(0, ITEM_HEIGHT))
            self.playlist_list.addItem(item)
            if playlist.id == selected:
                self.playlist_list.setCurrentItem(item)
        self.playlist_list.blockSignals(False)
        self.empty_playlists.setVisible(not playlists)

    def select_library(self, kind: str) -> None:
        for row in range(self.library_list.count()):
            if self.library_list.item(row).data(_ID_ROLE) == kind:
                if self.library_list.currentRow() == row:
                    self._on_library_changed(self.library_list.item(row), None)
                else:
                    self.library_list.setCurrentRow(row)
                return

    def select_playlist(self, playlist_id: int) -> None:
        for row in range(self.playlist_list.count()):
            if self.playlist_list.item(row).data(_ID_ROLE) == playlist_id:
                if self.playlist_list.currentRow() == row:
                    self._on_playlist_changed(self.playlist_list.item(row), None)
                else:
                    self.playlist_list.setCurrentRow(row)
                return

    def refresh_icons(self) -> None:
        """Vuelve a dibujar los iconos con los colores del tema activo."""
        for row, (_kind, _label, icon_name) in enumerate(LIBRARY_VIEWS):
            self.library_list.item(row).setIcon(icon(icon_name, MUTED, 18))
        for button in (self.btn_new, self.btn_add_folder):
            button.setIcon(icon(button.property("icon_name"), MUTED, 16))
        for row in range(self.playlist_list.count()):
            self.playlist_list.item(row).setIcon(icon("playlist", MUTED, 18))
        for item in self._folder_items():
            item.setIcon(0, icon("folder", MUTED, 18))
            if not os.path.isdir(item.data(0, _ID_ROLE)):
                item.setForeground(0, theme.qcolor("faint"))

    def set_folders(self, roots: list[FolderNode]) -> None:
        """Recarga el árbol conservando las carpetas abiertas y la seleccionada."""
        expanded = {
            folder_key(item.data(0, _ID_ROLE)) for item in self._folder_items() if item.isExpanded()
        }
        first_load = self.folder_tree.topLevelItemCount() == 0
        current = self.current_folder()
        selected_key = folder_key(current) if current else None

        self.folder_tree.blockSignals(True)
        self.folder_tree.clear()

        def add(node: FolderNode, parent) -> None:
            label = display_name(node.path) if parent is self.folder_tree else node.name
            item = QTreeWidgetItem([f"{label}  ({node.total})"])
            item.setIcon(0, icon("folder", MUTED, 18))
            item.setData(0, _ID_ROLE, node.path)
            exists = os.path.isdir(node.path)
            tip = f"{node.path}\n{plural(node.total, 'canción', 'canciones')}"
            if not exists:
                tip += "\nAtención: esta carpeta no se encuentra (¿se movió o la unidad está desconectada?)"
                item.setForeground(0, theme.qcolor("faint"))
            item.setToolTip(0, tip)
            if isinstance(parent, QTreeWidget):
                parent.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for child in node.sorted_children():
                add(child, item)
            key = folder_key(node.path)
            # La primera vez se abren las raíces para que se vean sus subcarpetas.
            item.setExpanded(key in expanded or (first_load and parent is self.folder_tree))
            if key == selected_key:
                self.folder_tree.setCurrentItem(item)

        for root in roots:
            add(root, self.folder_tree)
        self.folder_tree.blockSignals(False)
        self.empty_folders.setVisible(not roots)

    def select_folder(self, path: str) -> None:
        key = folder_key(path)
        for item in self._folder_items():
            if folder_key(item.data(0, _ID_ROLE)) == key:
                parent = item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                if self.folder_tree.currentItem() is item and item.isSelected():
                    self._on_folder_changed(item, None)
                else:
                    self.folder_tree.setCurrentItem(item)
                self.folder_tree.scrollToItem(item)
                return

    def _folder_items(self) -> list[QTreeWidgetItem]:
        """Todas las carpetas del árbol. Se recorre a mano: un QTreeWidgetItemIterator vivo
        mientras se llama a clear() provoca un cierre inesperado del programa."""
        items: list[QTreeWidgetItem] = []
        stack = [self.folder_tree.topLevelItem(i) for i in range(self.folder_tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            items.append(item)
            stack.extend(item.child(i) for i in range(item.childCount()))
        return items

    def current_folder(self) -> str | None:
        item = self.folder_tree.currentItem()
        return item.data(0, _ID_ROLE) if item is not None and item.isSelected() else None

    def current_view(self) -> tuple[str, int | str | None]:
        item = self.playlist_list.currentItem()
        if item is not None and item.isSelected():
            return "playlist", item.data(_ID_ROLE)
        folder = self.current_folder()
        if folder is not None:
            return "folder", folder
        item = self.library_list.currentItem()
        return (item.data(_ID_ROLE) if item else "songs"), None

    def current_playlist_id(self) -> int | None:
        item = self.playlist_list.currentItem()
        return item.data(_ID_ROLE) if item is not None else None

    # ------------------------------------------------------------------ interno

    def _on_library_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        self._clear(self.playlist_list)
        self._clear_tree()
        self.view_selected.emit(current.data(_ID_ROLE), None)

    def _on_playlist_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        self._clear(self.library_list)
        self._clear_tree()
        self.view_selected.emit("playlist", current.data(_ID_ROLE))

    def _on_folder_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        if current is None:
            return
        self._clear(self.library_list)
        self._clear(self.playlist_list)
        current.setSelected(True)
        self.view_selected.emit("folder", current.data(0, _ID_ROLE))

    @staticmethod
    def _clear(widget: QListWidget) -> None:
        widget.blockSignals(True)
        widget.setCurrentRow(-1)
        widget.clearSelection()
        widget.blockSignals(False)

    def _clear_tree(self) -> None:
        self.folder_tree.blockSignals(True)
        self.folder_tree.setCurrentItem(None)
        self.folder_tree.clearSelection()
        self.folder_tree.blockSignals(False)

    def _rename_current(self) -> None:
        pid = self.current_playlist_id()
        if pid is not None:
            self.rename_playlist_requested.emit(pid)

    def _delete_current(self) -> None:
        pid = self.current_playlist_id()
        if pid is not None:
            self.delete_playlist_requested.emit(pid)

    def _playlist_menu(self, pos) -> None:
        item = self.playlist_list.itemAt(pos)
        menu = QMenu(self)
        if item is not None:
            pid = item.data(_ID_ROLE)
            menu.addAction(icon("play", TEXT, 16), "Reproducir", lambda: self.play_playlist_requested.emit(pid))
            menu.addSeparator()
            menu.addAction("Renombrar…", lambda: self.rename_playlist_requested.emit(pid))
            menu.addAction("Eliminar…", lambda: self.delete_playlist_requested.emit(pid))
            menu.addSeparator()
        menu.addAction(icon("add", TEXT, 16), "Nueva playlist…", self.create_playlist_requested.emit)
        menu.exec(self.playlist_list.viewport().mapToGlobal(pos))
        menu.deleteLater()  # si no, cada clic derecho deja un menú en memoria

    def _folder_menu(self, pos) -> None:
        item = self.folder_tree.itemAt(pos)
        global_pos = self.folder_tree.viewport().mapToGlobal(pos)
        menu = QMenu(self)
        if item is not None:
            path = item.data(0, _ID_ROLE)
            menu.addAction(icon("play", TEXT, 16), "Reproducir carpeta", lambda: self.play_folder_requested.emit(path, False))
            menu.addAction(icon("shuffle", TEXT, 16), "Reproducir en aleatorio", lambda: self.play_folder_requested.emit(path, True))
            menu.addAction(
                icon("add", TEXT, 16),
                "Agregar carpeta a playlist…",
                lambda: self.folder_add_to_playlist_requested.emit(path, global_pos),
            )
            menu.addSeparator()
            menu.addAction(icon("folder", TEXT, 16), "Mostrar en el Explorador", lambda: self.folder_show_in_explorer_requested.emit(path))
            menu.addAction("Buscar música nueva en esta carpeta", lambda: self.folder_rescan_requested.emit(path))
            menu.addSeparator()
            menu.addAction(icon("edit", TEXT, 16), "Renombrar carpeta…", lambda: self.folder_rename_requested.emit(path))
            menu.addAction(icon("folder_plus", TEXT, 16), "Nueva subcarpeta…", lambda: self.folder_create_requested.emit(path))
            menu.addAction(icon("trash", "danger", 16), "Enviar carpeta a la Papelera…", lambda: self.folder_trash_requested.emit(path))
            if item.childCount():
                menu.addSeparator()
                menu.addAction("Expandir todo", lambda: self._expand_all(item, True))
                menu.addAction("Contraer todo", lambda: self._expand_all(item, False))
            menu.addSeparator()
        menu.addAction(icon("add", TEXT, 16), "Importar otra carpeta…", self.import_folder_requested.emit)
        menu.exec(global_pos)
        menu.deleteLater()  # si no, cada clic derecho deja un menú en memoria

    @staticmethod
    def _expand_all(item: QTreeWidgetItem, expand: bool) -> None:
        item.setExpanded(expand)
        for i in range(item.childCount()):
            Sidebar._expand_all(item.child(i), expand)
