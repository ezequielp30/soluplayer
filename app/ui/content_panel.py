"""Panel principal: encabezado, tabla de canciones, agrupaciones y estados vacíos."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableView,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ..models import Track
from ..utils import format_total, plural
from . import theme
from .covers import CoverProvider
from .icons import ACCENT, MUTED, TEXT, icon
from .track_model import (
    COL_ACTION,
    COL_ALBUM,
    COL_ARTIST,
    COL_DURATION,
    COL_TITLE,
    ROW_COVER_SIZE,
    TRACK_ROLE,
    TrackSortProxy,
    TrackTableModel,
)

HEADER_COVER = 92

MODE_LIBRARY = "library"
MODE_PLAYLIST = "playlist"
MODE_SEARCH = "search"


@dataclass
class Group:
    label: str
    tracks: list[Track]
    cover_hash: str | None = None


@dataclass
class EmptyAction:
    text: str
    callback: Callable[[], None]
    primary: bool = False


def describe_tracks(tracks: list[Track]) -> str:
    """'12 canciones · 48 min · 2 no disponibles' (la duración solo cuenta las disponibles)."""
    available = [t for t in tracks if t.available]
    parts = [plural(len(tracks), "canción", "canciones")]
    total = sum(t.duration_ms for t in available)
    if total:
        parts.append(format_total(total))
    missing = len(tracks) - len(available)
    if missing:
        parts.append(f"{missing} no disponible" + ("s" if missing != 1 else ""))
    return " · ".join(parts)


class EmptyState(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel()
        self.title.setObjectName("EmptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message = QLabel()
        self.message.setObjectName("EmptyMessage")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.message.setMaximumWidth(460)
        self.buttons = QHBoxLayout()
        self.buttons.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon)
        layout.addWidget(self.title)
        layout.addWidget(self.message, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(6)
        layout.addLayout(self.buttons)

    def configure(self, icon_name: str, title: str, message: str, actions: list[EmptyAction]) -> None:
        self._icon_name = icon_name
        self.icon.setPixmap(icon(icon_name, "faint", 52).pixmap(52, 52))
        self.title.setText(title)
        self.message.setText(message)
        while self.buttons.count():
            widget = self.buttons.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for action in actions:
            button = QPushButton(action.text)
            if action.primary:
                button.setObjectName("PrimaryButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(action.callback)
            self.buttons.addWidget(button)

    def refresh_icons(self) -> None:
        if getattr(self, "_icon_name", None):
            self.icon.setPixmap(icon(self._icon_name, "faint", 52).pixmap(52, 52))


class ContentPanel(QFrame):
    play_requested = Signal(object, int)
    shuffle_play_requested = Signal(object)
    add_to_playlist_requested = Signal(object, QPoint)
    remove_from_playlist_requested = Signal(object)
    remove_from_library_requested = Signal(object)
    locate_requested = Signal(object)
    show_in_folder_requested = Signal(object)
    import_files_requested = Signal()
    import_folder_requested = Signal()
    missing_review_requested = Signal()
    folder_requested = Signal(str)
    online_lookup_requested = Signal(object)  # canciones a buscar en internet
    rename_file_requested = Signal(object)  # Track
    move_files_requested = Signal(object)  # list[Track]
    trash_files_requested = Signal(object)  # list[Track]

    def __init__(self, covers: CoverProvider, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ContentPanel")
        self._covers = covers
        self._mode = MODE_LIBRARY
        self._groups: list[Group] = []
        self._group_noun = ("", "")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(12)

        # Encabezado
        header = QHBoxLayout()
        header.setSpacing(16)
        self.header_cover = QLabel()
        self.header_cover.setFixedSize(HEADER_COVER, HEADER_COVER)
        header.addWidget(self.header_cover)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addStretch(1)
        self.breadcrumb = QLabel()
        self.breadcrumb.setObjectName("Breadcrumb")
        self.breadcrumb.setTextFormat(Qt.TextFormat.RichText)
        self.breadcrumb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.breadcrumb.linkActivated.connect(self.folder_requested.emit)
        self.breadcrumb.hide()
        titles.addWidget(self.breadcrumb)
        self.title = QLabel()
        self.title.setObjectName("HeaderTitle")
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title_font = self.title.font()
        title_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98)  # titular algo más compacto
        self.title.setFont(title_font)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("HeaderSubtitle")
        self.subtitle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.btn_play = QPushButton(" Reproducir")
        self.btn_play.setObjectName("PrimaryButton")
        self.btn_shuffle = QPushButton(" Aleatorio")
        self.btn_add = QPushButton(" Agregar a playlist")
        self.btn_add.setToolTip("Agrega las canciones seleccionadas a una playlist (selecciona primero en la lista)")
        self.btn_import = QPushButton(" Importar música")
        self.btn_online = QPushButton(" Datos en internet")
        self.btn_online.setToolTip(
            "Busca título, artista, álbum y carátula en bases de datos de música (MusicBrainz, Deezer, iTunes).\n"
            "Usa las canciones seleccionadas o, si no hay selección, todas las de esta lista."
        )
        self.btn_online.clicked.connect(self._online_from_button)
        for button in (self.btn_play, self.btn_shuffle, self.btn_add, self.btn_import, self.btn_online):
            button.setIconSize(QSize(16, 16))
        import_menu = QMenu(self.btn_import)
        import_menu.addAction("Importar carpeta…", self.import_folder_requested.emit)
        import_menu.addAction("Importar archivos…", self.import_files_requested.emit)
        self.btn_import.setMenu(import_menu)
        for button in (self.btn_play, self.btn_shuffle, self.btn_add, self.btn_import, self.btn_online):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        buttons.addWidget(self.btn_play)
        buttons.addWidget(self.btn_shuffle)
        buttons.addWidget(self.btn_add)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_online)
        buttons.addWidget(self.btn_import)
        titles.addSpacing(8)
        titles.addLayout(buttons)
        header.addLayout(titles, 1)
        layout.addLayout(header)

        # Aviso de archivos faltantes
        self.missing_banner = QFrame()
        self.missing_banner.setObjectName("MissingBanner")
        banner_layout = QHBoxLayout(self.missing_banner)
        banner_layout.setContentsMargins(10, 6, 10, 6)
        warn = QLabel()
        self._banner_icon = warn
        self.missing_text = QLabel()
        self.missing_text.setWordWrap(True)
        self.btn_missing = QPushButton("Localizar el primero…")
        self.btn_missing.clicked.connect(self.missing_review_requested.emit)
        banner_layout.addWidget(warn)
        banner_layout.addWidget(self.missing_text, 1)
        banner_layout.addWidget(self.btn_missing)
        self.missing_banner.hide()
        layout.addWidget(self.missing_banner)
        self._breadcrumb_trail: list[tuple[str, str]] | None = None

        # Cuerpo: tabla (con lista de grupos opcional) o estado vacío
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)
        self.group_list = QListWidget()
        self.group_list.setObjectName("GroupList")
        self.group_list.setIconSize(QSize(32, 32))
        self.group_list.setMinimumWidth(170)
        # Nombres largos se recortan con «…» en vez de mostrar una barra horizontal.
        self.group_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.group_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.group_list.setWordWrap(False)
        self.group_list.currentRowChanged.connect(self._on_group_changed)
        self.splitter.addWidget(self.group_list)

        self.model = TrackTableModel(covers, self)
        self.proxy = TrackSortProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        self.table.setIconSize(QSize(ROW_COVER_SIZE, ROW_COVER_SIZE))
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(ROW_COVER_SIZE + 14)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.table.horizontalHeader().setHighlightSections(False)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hh.setSectionResizeMode(COL_TITLE, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(COL_ARTIST, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_ALBUM, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_DURATION, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_ACTION, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(COL_ARTIST, 190)
        hh.resizeSection(COL_ALBUM, 210)
        hh.resizeSection(COL_DURATION, 80)
        hh.resizeSection(COL_ACTION, 44)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.clicked.connect(self._on_click)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_buttons())
        self.splitter.addWidget(self.table)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([230, 800])
        self.stack.addWidget(self.splitter)

        self.empty = EmptyState()
        self.stack.addWidget(self.empty)

        enter = QAction(self.table)
        enter.setShortcuts([QKeySequence(Qt.Key.Key_Return), QKeySequence(Qt.Key.Key_Enter)])
        enter.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        enter.triggered.connect(lambda: self._on_double_click(self.table.currentIndex()))
        delete = QAction(self.table)
        delete.setShortcut(QKeySequence(QKeySequence.StandardKey.Delete))
        delete.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        delete.triggered.connect(self._delete_selected)
        self.table.addActions([enter, delete])

        self.btn_play.clicked.connect(self._play_all)
        self.btn_shuffle.clicked.connect(lambda: self.shuffle_play_requested.emit(self.visible_tracks()))
        self.btn_add.clicked.connect(self._add_selected_from_button)
        self.refresh_icons()

    # ------------------------------------------------------------------ API pública

    @property
    def mode(self) -> str:
        return self._mode

    def show_tracks(
        self,
        title: str,
        tracks: list[Track],
        mode: str,
        empty: tuple[str, str, str, list[EmptyAction]],
        subtitle: str | None = None,
        cover_hash: str | None = None,
        show_cover: bool = False,
        breadcrumb: list[tuple[str, str]] | None = None,
    ) -> None:
        """Muestra una lista de canciones. 'empty' = (icono, título, mensaje, acciones).

        `breadcrumb` = [(nombre, ruta)] de carpetas; cada tramo salvo el último es un enlace.
        """
        self._mode = mode
        self._groups = []
        self.group_list.hide()
        self._set_breadcrumb(breadcrumb)
        self.title.setToolTip("")
        self.title.setText(title)
        self.subtitle.setText(subtitle if subtitle is not None else describe_tracks(tracks))
        self._set_header_cover(show_cover, cover_hash)
        self._set_table(tracks)
        self._show_body(bool(tracks), empty)

    def set_title(self, title: str) -> None:
        self.title.setText(title)

    def set_title_tooltip(self, text: str) -> None:
        self.title.setToolTip(text)

    def add_subtitle_note(self, note: str) -> None:
        """Agrega una aclaración al resumen bajo el título («12 canciones · 48 min  ·  <nota>»)."""
        self.subtitle.setText(f"{self.subtitle.text()}  ·  {note}")

    def show_groups(
        self,
        title: str,
        groups: list[Group],
        noun: tuple[str, str],
        empty: tuple[str, str, str, list[EmptyAction]],
        group_icon: str,
        keep_selection: bool = True,
    ) -> None:
        """Vista agrupada (Artistas, Álbumes) con lista de grupos a la izquierda."""
        previous = self._current_group_label() if keep_selection else None
        self._mode = MODE_LIBRARY
        self._groups = groups
        self._group_noun = noun
        self.title.setToolTip("")  # que no quede la ruta de la carpeta vista antes
        self.title.setText(title)
        self._set_breadcrumb(None)
        self._set_header_cover(False, None)
        self.group_list.blockSignals(True)
        self.group_list.clear()
        for group in groups:
            item = QListWidgetItem(group.label)
            if group_icon == "cover":
                item.setIcon(self._covers.pixmap(group.cover_hash, 32))
            else:
                item.setIcon(icon(group_icon, MUTED, 20))
            item.setData(Qt.ItemDataRole.UserRole, group_icon)
            item.setToolTip(f"{group.label}\n{describe_tracks(group.tracks)}")
            self.group_list.addItem(item)
        self.group_list.blockSignals(False)
        self.group_list.show()
        self._show_body(bool(groups), empty)
        if groups:
            labels = [g.label for g in groups]
            row = labels.index(previous) if previous in labels else 0
            if self.group_list.currentRow() == row:
                self._on_group_changed(row)
            else:
                self.group_list.setCurrentRow(row)
            # Que el artista o álbum elegido se vea en la lista (si no, queda fuera de la vista).
            QTimer.singleShot(0, lambda r=row: self.group_list.scrollToItem(
                self.group_list.item(r), QAbstractItemView.ScrollHint.PositionAtCenter
            ) if self.group_list.item(r) is not None else None)
        else:
            self.subtitle.setText(f"0 {noun[1]}")
            self._set_table([])

    def visible_tracks(self) -> list[Track]:
        """Canciones en el orden en que se ven (respeta el orden por columna elegido)."""
        return [
            self.proxy.index(row, 0).data(TRACK_ROLE) for row in range(self.proxy.rowCount())
        ]

    def selected_tracks(self) -> list[Track]:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        return [self.proxy.index(row, 0).data(TRACK_ROLE) for row in rows]

    def set_current_track(self, track_id: int | None) -> None:
        self.model.set_current_track(track_id)

    def refresh_track(self, track: Track) -> None:
        self.model.refresh_track(track)
        self._update_missing_banner()

    # ------------------------------------------------------------------ interno

    def refresh_icons(self) -> None:
        """Vuelve a dibujar iconos y colores que no salen de la hoja de estilos (cambio de tema)."""
        self.btn_play.setIcon(icon("play", "on_accent", 16))
        self.btn_shuffle.setIcon(icon("shuffle", ACCENT, 16))
        self.btn_add.setIcon(icon("add", TEXT, 16))
        self.btn_import.setIcon(icon("folder_plus", TEXT, 16))
        self.btn_online.setIcon(icon("globe", TEXT, 16))
        self._banner_icon.setPixmap(icon("warning", "warning", 18).pixmap(18, 18))
        self.empty.refresh_icons()
        self._set_breadcrumb(self._breadcrumb_trail)
        self.model.repaint_all()
        for row in range(self.group_list.count()):
            item = self.group_list.item(row)
            group_icon = item.data(Qt.ItemDataRole.UserRole)
            if group_icon and group_icon != "cover":
                item.setIcon(icon(group_icon, MUTED, 20))

    def _set_breadcrumb(self, trail: list[tuple[str, str]] | None) -> None:
        self._breadcrumb_trail = trail
        if not trail or len(trail) < 2:
            self.breadcrumb.hide()
            return
        link = theme.color(ACCENT)
        parts = []
        for name, path in trail[:-1]:
            href = html.escape(path, quote=True)
            parts.append(f'<a href="{href}" style="color:{link}; text-decoration:none">{html.escape(name)}</a>')
        parts.append(html.escape(trail[-1][0]))
        self.breadcrumb.setText("  ›  ".join(parts))
        self.breadcrumb.setToolTip("Haz clic en una carpeta para subir a ella")
        self.breadcrumb.show()

    def _set_header_cover(self, visible: bool, cover_hash: str | None) -> None:
        self.header_cover.setVisible(visible)
        if visible:
            self.header_cover.setPixmap(self._covers.pixmap(cover_hash, HEADER_COVER))

    def _set_table(self, tracks: list[Track]) -> None:
        self.proxy.sort(-1)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.model.set_tracks(tracks)
        self.table.scrollToTop()
        self._update_missing_banner()
        self._update_buttons()

    def _show_body(self, has_content: bool, empty: tuple[str, str, str, list[EmptyAction]]) -> None:
        if has_content:
            self.stack.setCurrentWidget(self.splitter)
        else:
            self.empty.configure(*empty)
            self.stack.setCurrentWidget(self.empty)
        self._update_buttons()

    def _update_buttons(self) -> None:
        # Sin canciones se ocultan: el estado vacío ya ofrece las acciones útiles (importar, etc.).
        has_tracks = self.stack.currentWidget() is self.splitter and self.model.rowCount() > 0
        for button in (self.btn_play, self.btn_shuffle, self.btn_add, self.btn_online):
            button.setVisible(has_tracks)
        selected = len(self.table.selectionModel().selectedRows())
        self.btn_online.setText(f" Datos en internet ({selected})" if selected > 1 else " Datos en internet")
        count = len(self.table.selectionModel().selectedRows())
        self.btn_add.setText(f" Agregar a playlist ({count})" if count > 1 else " Agregar a playlist")

    def _update_missing_banner(self) -> None:
        missing = [t for t in self.model.tracks() if not t.available]
        if not missing:
            self.missing_banner.hide()
            return
        count = len(missing)
        self.missing_text.setText(
            f"{plural(count, 'canción', 'canciones')} de esta lista no "
            f"{'se encuentra' if count == 1 else 'se encuentran'} en su ubicación. "
            "Los archivos pueden haberse movido, renombrado o eliminado, o estar en una "
            "unidad desconectada. Puedes volver a localizarlos con clic derecho → «Localizar archivo…»."
        )
        self.missing_banner.show()

    def first_missing_track(self) -> Track | None:
        return next((t for t in self.visible_tracks() if not t.available), None)

    def _current_group_label(self) -> str | None:
        item = self.group_list.currentItem()
        return item.text() if item is not None else None

    def _on_group_changed(self, row: int) -> None:
        if not 0 <= row < len(self._groups):
            return
        group = self._groups[row]
        singular, plural_noun = self._group_noun
        count = len(self._groups)
        self.subtitle.setText(
            f"{count} {singular if count == 1 else plural_noun}  ·  {group.label}: {describe_tracks(group.tracks)}"
        )
        self._set_table(group.tracks)

    def _play_all(self) -> None:
        tracks = self.visible_tracks()
        if tracks:
            self.play_requested.emit(tracks, 0)

    def _on_double_click(self, index) -> None:
        if index.isValid():
            self.play_requested.emit(self.visible_tracks(), index.row())

    def _on_click(self, index) -> None:
        if index.isValid() and index.column() == COL_ACTION:
            track = index.data(TRACK_ROLE)
            rect = self.table.visualRect(index)
            pos = self.table.viewport().mapToGlobal(rect.bottomLeft())
            self.add_to_playlist_requested.emit([track], pos)

    def _add_selected_from_button(self) -> None:
        tracks = self.selected_tracks()
        pos = self.btn_add.mapToGlobal(self.btn_add.rect().bottomLeft())
        if not tracks:
            QToolTip.showText(
                pos,
                "Primero selecciona una o más canciones de la lista\n"
                "(clic, Ctrl+clic o Mayús+clic) y vuelve a pulsar este botón.\n"
                "También puedes usar el botón + de cada canción.",
                self.btn_add,
            )
            return
        self.add_to_playlist_requested.emit(tracks, pos)

    def _online_from_button(self) -> None:
        tracks = self.selected_tracks() or self.visible_tracks()
        if tracks:
            self.online_lookup_requested.emit(tracks)

    def _delete_selected(self) -> None:
        tracks = self.selected_tracks()
        if not tracks:
            return
        if self._mode == MODE_PLAYLIST:
            self.remove_from_playlist_requested.emit(tracks)
        else:
            self.remove_from_library_requested.emit(tracks)

    def _table_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        if not self.table.selectionModel().isRowSelected(index.row(), index.parent()):
            self.table.selectRow(index.row())
        tracks = self.selected_tracks()
        if not tracks:
            return
        first = tracks[0]
        global_pos = self.table.viewport().mapToGlobal(pos)

        menu = QMenu(self)
        menu.addAction(icon("play", TEXT, 16), "Reproducir", lambda: self._on_double_click(index))
        menu.addAction(
            icon("add", TEXT, 16),
            "Agregar a playlist…",
            lambda: self.add_to_playlist_requested.emit(tracks, global_pos),
        )
        label = "Buscar datos en internet…" if len(tracks) == 1 else f"Buscar datos en internet ({len(tracks)})…"
        menu.addAction(icon("globe", TEXT, 16), label, lambda: self.online_lookup_requested.emit(tracks))
        menu.addSeparator()
        if len(tracks) == 1:
            if not first.available:
                menu.addAction(
                    icon("warning", "warning", 16), "Localizar archivo…", lambda: self.locate_requested.emit(first)
                )
            else:
                menu.addAction(
                    icon("folder", TEXT, 16),
                    "Mostrar en el Explorador",
                    lambda: self.show_in_folder_requested.emit(first),
                )
                menu.addAction(icon("edit", TEXT, 16), "Renombrar archivo…", lambda: self.rename_file_requested.emit(first))
        available = [t for t in tracks if t.available]
        if available:
            count = "" if len(available) == 1 else f" ({len(available)})"
            menu.addAction(icon("move", TEXT, 16), f"Mover a otra carpeta{count}…", lambda: self.move_files_requested.emit(available))
        if self._mode == MODE_PLAYLIST:
            label = "Quitar de la playlist" if len(tracks) == 1 else f"Quitar {len(tracks)} canciones de la playlist"
            menu.addAction(label, lambda: self.remove_from_playlist_requested.emit(tracks))
        else:
            label = "Quitar de la biblioteca…" if len(tracks) == 1 else f"Quitar {len(tracks)} canciones de la biblioteca…"
            menu.addAction(label, lambda: self.remove_from_library_requested.emit(tracks))
        if available:
            label = "Enviar archivo a la Papelera…" if len(available) == 1 else f"Enviar {len(available)} archivos a la Papelera…"
            menu.addAction(icon("trash", "danger", 16), label, lambda: self.trash_files_requested.emit(available))
        menu.exec(global_pos)
        menu.deleteLater()  # si no, cada clic derecho deja un menú en memoria
