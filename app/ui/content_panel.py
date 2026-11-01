"""Panel principal: encabezado, tabla de canciones, agrupaciones y estados vacíos."""

from __future__ import annotations

import html
import random
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QItemSelectionModel, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
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
    COL_FILE,
    COL_GENRE,
    COL_TITLE,
    DEFAULT_SONG_COLUMNS,
    ORDER_COLUMNS,
    ORDER_DEFAULT,
    ORDER_MANUAL,
    ORDER_OTHER,
    ORDER_RANDOM,
    SONG_COLUMNS,
    ROW_COVER_SIZE,
    TRACK_ROLE,
    TrackSortProxy,
    TrackTableModel,
    move_rows,
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


class ReorderTable(QTableView):
    """Tabla de canciones que, si se permite, se ordena arrastrando filas. No mueve nada por su cuenta:
    avisa con rows_dropped(filas, fila de destino) y el panel arma y guarda el orden nuevo."""

    rows_dropped = Signal(list, int)

    def set_reorderable(self, enabled: bool) -> None:
        self.setDragEnabled(enabled)
        self.setAcceptDrops(enabled)
        self.setDropIndicatorShown(enabled)
        self.setDragDropOverwriteMode(False)
        self.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove if enabled else QAbstractItemView.DragDropMode.NoDragDrop
        )

    def reorderable(self) -> bool:
        return self.dragDropMode() == QAbstractItemView.DragDropMode.InternalMove

    def dropEvent(self, event) -> None:
        if event.source() is not self or not self.reorderable():
            event.ignore()
            return
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        if index.isValid():
            target = index.row() + (1 if pos.y() > self.visualRect(index).center().y() else 0)
        else:
            target = self.model().rowCount()
        rows = sorted({i.row() for i in self.selectionModel().selectedRows()})
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()  # el modelo no borra filas (no tiene removeRows): soltar no quita ninguna canción
        self.stopAutoScroll()
        self.setState(QAbstractItemView.State.NoState)
        self.viewport().update()
        if rows:
            self.rows_dropped.emit(rows, target)


class ContentPanel(QFrame):
    play_requested = Signal(object, int)
    shuffle_play_requested = Signal(object)
    add_to_playlist_requested = Signal(object, QPoint)
    remove_from_playlist_requested = Signal(object)
    remove_from_library_requested = Signal(object)
    locate_requested = Signal(object)
    import_files_requested = Signal()
    import_folder_requested = Signal()
    missing_review_requested = Signal()
    folder_requested = Signal(str)
    online_lookup_requested = Signal(object)  # canciones a buscar en internet
    rename_file_requested = Signal(object)  # Track
    move_files_requested = Signal(object)  # list[Track]
    trash_files_requested = Signal(object)  # list[Track]
    reorder_requested = Signal(object)  # list[Track] en el orden nuevo (arrastradas o Alt+↑/↓)
    reset_order_requested = Signal()
    columns_changed = Signal(list)  # datos visibles elegidos con clic derecho en los encabezados
    order_mode_changed = Signal(str, bool)  # orden elegido; True si hay que volver a armar la lista

    def __init__(self, covers: CoverProvider, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ContentPanel")
        self._covers = covers
        self._mode = MODE_LIBRARY
        self._reset_label: str | None = None
        self._order_mode = ORDER_DEFAULT
        self._player_shuffle = False  # el botón aleatorio de la barra: suena al azar, sea cual sea el orden
        self._mixes: dict[frozenset, list] = {}  # la mezcla de cada lista: refrescarla no vuelve a mezclar
        self._new_mix = False
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
        # Siempre a la vista, junto al resumen: en qué orden está la lista y cómo va a sonar (y desde aquí se cambia).
        self.order_label = QLabel("Orden:")
        self.order_combo = QComboBox()
        self.order_combo.setToolTip("En qué orden está esta lista y en cuál va a sonar. Cada lista recuerda el suyo.")
        self.order_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.order_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.order_combo.activated.connect(self._on_order_chosen)
        self.order_note = QLabel()
        self.order_note.setObjectName("DialogNote")
        summary = QHBoxLayout()
        summary.setSpacing(8)
        summary.addWidget(self.subtitle, 1)
        summary.addWidget(self.order_note)
        summary.addSpacing(4)
        summary.addWidget(self.order_label)
        summary.addWidget(self.order_combo)
        titles.addLayout(summary)
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
        self.table = ReorderTable()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        self.table.setIconSize(QSize(ROW_COVER_SIZE, ROW_COVER_SIZE))
        self.table.verticalHeader().setDefaultSectionSize(ROW_COVER_SIZE + 14)
        self.table.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.verticalHeader().setSectionsClickable(False)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.table.horizontalHeader().setHighlightSections(False)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hh.setSectionResizeMode(COL_TITLE, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(COL_ARTIST, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_ALBUM, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_GENRE, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_FILE, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_DURATION, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(COL_ACTION, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(COL_ARTIST, 190)
        hh.resizeSection(COL_ALBUM, 210)
        hh.resizeSection(COL_GENRE, 130)
        hh.resizeSection(COL_FILE, 220)
        hh.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hh.customContextMenuRequested.connect(self._header_menu)
        hh.sortIndicatorChanged.connect(self._on_header_sort)
        self._columns: list[str] = []
        self.set_columns(DEFAULT_SONG_COLUMNS)
        hh.resizeSection(COL_DURATION, 80)
        hh.resizeSection(COL_ACTION, 44)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.clicked.connect(self._on_click)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_buttons())
        self.table.rows_dropped.connect(self._move_rows)
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
        move_up = QAction(self.table)
        move_up.setShortcut(QKeySequence(Qt.Modifier.ALT | Qt.Key.Key_Up))
        move_up.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        move_up.triggered.connect(lambda: self._nudge_selected(-1))
        move_down = QAction(self.table)
        move_down.setShortcut(QKeySequence(Qt.Modifier.ALT | Qt.Key.Key_Down))
        move_down.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        move_down.triggered.connect(lambda: self._nudge_selected(1))
        self.table.addActions([enter, delete, move_up, move_down])

        self.btn_play.clicked.connect(self._play_all)
        self.btn_shuffle.clicked.connect(lambda: self.shuffle_play_requested.emit(self.shuffle_visible()))
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
        reorderable: bool = False,
        reset_label: str | None = None,
        order_mode: str = ORDER_DEFAULT,
        has_manual: bool = False,
        default_label: str | None = "Predeterminado",
    ) -> None:
        """Muestra una lista de canciones. 'empty' = (icono, título, mensaje, acciones).

        `breadcrumb` = [(nombre, ruta)] de carpetas; cada tramo salvo el último es un enlace.
        `reorderable`: se puede ordenar a mano (arrastrar o Alt+↑/↓); el orden nuevo llega por reorder_requested.
        `reset_label`: texto de la opción del clic derecho que vuelve al orden de siempre (reset_order_requested).
        `order_mode`: orden elegido para esta lista; `tracks` viene en «Mi orden» o en el predeterminado, y las
        columnas o el aleatorio se aplican aquí. `has_manual`: hay un orden a mano guardado («Mi orden»).
        `default_label`: cómo se llama el orden predeterminado de esta lista (None: no tiene).
        """
        self._mode = mode
        self.table.set_reorderable(reorderable)
        self._reset_label = reset_label if reorderable else None
        self._groups = []
        self.group_list.hide()
        self._set_breadcrumb(breadcrumb)
        self.title.setToolTip("")
        self.title.setText(title)
        self.subtitle.setText(subtitle if subtitle is not None else describe_tracks(tracks))
        self._set_header_cover(show_cover, cover_hash)
        self._fill_order_combo(order_mode, has_manual, default_label)
        self._set_table(tracks)
        self._apply_order_mode()
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
        reorderable: bool = False,
        reset_label: str | None = None,
        order_mode: str = ORDER_DEFAULT,
        has_manual: bool = False,
        default_label: str | None = "Predeterminado",
    ) -> None:
        """Vista agrupada (Artistas, Álbumes) con lista de grupos a la izquierda. Con `reorderable`, las
        canciones de cada grupo se ordenan a mano (current_group_label() dice de cuál es el orden nuevo)."""
        previous = self._current_group_label() if keep_selection else None
        self._mode = MODE_LIBRARY
        self.table.set_reorderable(reorderable)
        self._reset_label = reset_label if reorderable else None
        self._groups = groups
        self._group_noun = noun
        self.title.setToolTip("")  # que no quede la ruta de la carpeta vista antes
        self.title.setText(title)
        self._set_breadcrumb(None)
        self._set_header_cover(False, None)
        self._fill_order_combo(order_mode, has_manual, default_label)
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

    def current_group_label(self) -> str | None:
        return self._current_group_label() if self._groups else None

    def set_current_group_tracks(self, tracks: list[Track]) -> None:
        """El grupo elegido quedó en otro orden: se recuerda para cuando se vuelva a él."""
        row = self.group_list.currentRow()
        if 0 <= row < len(self._groups):
            self._groups[row].tracks = list(tracks)

    def shuffle_visible(self) -> list[Track]:
        """«Aleatorio»: mezcla a la vista las canciones mostradas y devuelve la lista en ese orden. No se guarda
        como orden manual hasta que se mueva alguna (entonces se guarda lo que se ve)."""
        tracks = self._shuffle_table()
        self.table.clearSelection()
        self.table.scrollToTop()
        if tracks and "mezcladas al azar" not in self.subtitle.text():
            self.add_subtitle_note("mezcladas al azar")
        self.set_order_mode(ORDER_RANDOM)
        self.order_mode_changed.emit(ORDER_RANDOM, False)
        return tracks

    @staticmethod
    def _mix_key(track: Track) -> tuple:
        return track.id, track.entry_id  # en una playlist, cada repetición es otra entrada

    def _shuffle_table(self, keep: bool = False) -> list[Track]:
        """Mezcla lo que se ve. Con `keep`, la misma lista de canciones conserva la mezcla que ya tenía (cada
        refresco, p. ej. al renombrar un archivo, no debe cambiar el orden mientras suena)."""
        tracks = self.visible_tracks()
        songs = frozenset(self._mix_key(t) for t in tracks)
        previous = self._mixes.get(songs) if keep else None
        if previous is not None:
            place = {key: i for i, key in enumerate(previous)}
            tracks.sort(key=lambda t: place[self._mix_key(t)])
        else:
            random.shuffle(tracks)
            self._mixes[songs] = [self._mix_key(t) for t in tracks]
        self._clear_header_sort()
        self.model.set_tracks(tracks)
        return tracks

    def _clear_header_sort(self) -> None:
        header = self.table.horizontalHeader()
        header.blockSignals(True)  # no es un clic del usuario
        self.proxy.sort(-1)
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        header.blockSignals(False)
        header.viewport().update()

    # ------------------------------------------------------------------ orden de la lista

    def order_mode(self) -> str:
        return self._order_mode

    def _fill_order_combo(self, mode: str, has_manual: bool, default_label: str | None) -> None:
        combo = self.order_combo
        combo.blockSignals(True)
        combo.clear()
        if has_manual:
            combo.addItem("Mi orden", ORDER_MANUAL)
        if default_label:
            combo.addItem(default_label, ORDER_DEFAULT)
        for key, label, _col, _desc in ORDER_COLUMNS:
            combo.addItem(label, key)
        combo.addItem("Aleatorio", ORDER_RANDOM)
        combo.blockSignals(False)
        self.set_order_mode(mode)

    def set_order_mode(self, mode: str) -> None:
        """Muestra en el selector en qué orden está la lista (no reordena nada)."""
        combo = self.order_combo
        if combo.findData(mode) < 0:
            labels = {ORDER_MANUAL: "Mi orden", ORDER_OTHER: "Por la columna elegida"}
            if mode in labels:
                combo.blockSignals(True)
                combo.insertItem(0, labels[mode], mode)
                combo.blockSignals(False)
            else:
                mode = combo.itemData(0)
        self._order_mode = mode
        combo.blockSignals(True)
        combo.setCurrentIndex(combo.findData(mode))
        combo.blockSignals(False)
        self._update_order_note()

    def set_player_shuffle(self, enabled: bool) -> None:
        """El botón aleatorio de la barra: mientras esté encendido, lo que suena no sigue el orden de la lista."""
        self._player_shuffle = enabled
        self._update_order_note()

    def _update_order_note(self) -> None:
        if self._player_shuffle:
            self.order_note.setText("⚠ Aleatorio de la barra encendido: suena al azar, no en este orden")
            self.order_note.setToolTip("Elige un orden aquí, o apaga el botón aleatorio de la barra de arriba.")
        else:
            self.order_note.setText("Suena de arriba abajo")
            self.order_note.setToolTip("Las canciones suenan en el orden en que se ven, siguiendo los números.")

    def _apply_order_mode(self) -> None:
        """La lista ya está cargada: aplica la columna o el aleatorio elegidos para ella."""
        if self._order_mode == ORDER_RANDOM:
            self._shuffle_table(keep=not self._new_mix)
            self._new_mix = False
            return
        for key, _label, column, descending in ORDER_COLUMNS:
            if key == self._order_mode:
                order = Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder
                header = self.table.horizontalHeader()
                header.blockSignals(True)
                self.proxy.sort(column, order)
                header.setSortIndicator(column, order)
                header.blockSignals(False)
                header.viewport().update()
                return

    def _on_order_chosen(self, _index: int) -> None:
        mode = self.order_combo.currentData()
        if mode == self._order_mode and mode != ORDER_RANDOM:
            return
        self._new_mix = mode == ORDER_RANDOM  # elegir «Aleatorio» otra vez es pedir otra mezcla
        self._order_mode = mode
        self._update_order_note()
        self.order_mode_changed.emit(mode, True)

    def _on_header_sort(self, column: int, order: Qt.SortOrder) -> None:
        """Clic en un encabezado: la lista queda ordenada por esa columna y el selector lo dice."""
        if column < 0:
            return
        descending = order == Qt.SortOrder.DescendingOrder
        mode = next((k for k, _l, c, d in ORDER_COLUMNS if c == column and d == descending), ORDER_OTHER)
        self.set_order_mode(mode)
        self.order_mode_changed.emit(mode, False)

    def columns(self) -> list[str]:
        return list(self._columns)

    def set_columns(self, keys: list[str]) -> None:
        """Qué datos de cada canción se ven, además del título (claves de SONG_COLUMNS)."""
        self._columns = [key for key, _label, _col in SONG_COLUMNS if key in keys]
        for key, _label, col in SONG_COLUMNS:
            if col is not None:
                self.table.setColumnHidden(col, key not in self._columns)
        self.table.verticalHeader().setVisible("number" in self._columns)
        covers = "cover" in self._columns
        self.model.set_show_covers(covers)
        self.table.setIconSize(QSize(ROW_COVER_SIZE, ROW_COVER_SIZE) if covers else QSize(18, 18))
        self.table.verticalHeader().setDefaultSectionSize(ROW_COVER_SIZE + 14 if covers else 32)

    def _header_menu(self, pos) -> None:
        menu = QMenu(self)
        title = menu.addAction("Título (siempre visible)")
        title.setEnabled(False)
        for key, label, _col in SONG_COLUMNS:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(key in self._columns)
            action.toggled.connect(lambda on, k=key: self._toggle_column(k, on))
        menu.addSeparator()
        menu.addAction("Más opciones en Herramientas → Preferencias → Canciones").setEnabled(False)
        menu.exec(self.table.horizontalHeader().mapToGlobal(pos))
        menu.deleteLater()  # si no, cada clic derecho deja un menú en memoria

    def _toggle_column(self, key: str, on: bool) -> None:
        keys = [k for k in self._columns if k != key] + ([key] if on else [])
        self.set_columns(keys)
        self.columns_changed.emit(self.columns())

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
        self._clear_header_sort()
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
        for widget in (self.btn_play, self.btn_shuffle, self.btn_add, self.btn_online,
                       self.order_label, self.order_combo, self.order_note):
            widget.setVisible(has_tracks)
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
            "unidad desconectada. Clic derecho → «Localizar archivo» los busca en tus discos."
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
        self._apply_order_mode()

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

    def _move_rows(self, rows: list[int], target: int) -> None:
        """Pone las filas elegidas antes de `target` (en el orden en que se ven) y avisa del orden nuevo.
        Si la lista estaba ordenada por una columna, ese orden visible pasa a ser el orden manual."""
        visible = self.visible_tracks()
        ordered = move_rows(visible, rows, target)
        if all(a is b for a, b in zip(ordered, visible)):
            return
        moved = {id(visible[r]) for r in rows if 0 <= r < len(visible)}
        scroll = self.table.verticalScrollBar().value()
        self._clear_header_sort()
        self.model.set_tracks(ordered)
        self.table.verticalScrollBar().setValue(scroll)
        selection = self.table.selectionModel()
        first = None
        for row, track in enumerate(ordered):
            if id(track) in moved:
                index = self.proxy.index(row, 0)
                selection.select(
                    index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
                )
                if first is None:
                    first = index
                    selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.NoUpdate)
        if first is not None:
            self.table.scrollTo(first)
        self.reorder_requested.emit(ordered)

    def _move_to_position(self, position: int) -> None:
        """Lleva las canciones seleccionadas al número `position` de la lista (la primera de ellas queda ahí)."""
        rows = sorted(index.row() for index in self.table.selectionModel().selectedRows())
        total = self.proxy.rowCount()
        if not rows or not self.table.reorderable():
            return
        wanted = max(1, min(position, total - len(rows) + 1)) - 1
        target = next(t for t in range(total + 1) if t - sum(1 for r in rows if r < t) == wanted)
        self._move_rows(rows, target)

    def _ask_position(self) -> None:
        rows = sorted(index.row() for index in self.table.selectionModel().selectedRows())
        if not rows:
            return
        total = self.proxy.rowCount()
        dialog = QInputDialog(self)
        dialog.setInputMode(QInputDialog.InputMode.IntInput)
        dialog.setWindowTitle("Mover a la posición")
        what = "esta canción" if len(rows) == 1 else f"estas {len(rows)} canciones"
        dialog.setLabelText(f"¿A qué número de la lista mover {what}? (de 1 a {total})")
        dialog.setIntRange(1, total)
        dialog.setIntValue(rows[0] + 1)
        dialog.setOkButtonText("Mover")
        dialog.setCancelButtonText("Cancelar")
        if dialog.exec():
            self._move_to_position(dialog.intValue())
        dialog.deleteLater()

    def _nudge_selected(self, step: int) -> None:
        """Alt+↑ / Alt+↓: sube o baja una fila las canciones seleccionadas."""
        if not self.table.reorderable():
            return
        rows = sorted(index.row() for index in self.table.selectionModel().selectedRows())
        if not rows:
            return
        target = rows[0] - 1 if step < 0 else rows[-1] + 2
        if 0 <= target <= self.proxy.rowCount():
            self._move_rows(rows, target)

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
            menu.addAction(
                icon("folder", TEXT, 16) if first.available else icon("warning", "warning", 16),
                "Localizar archivo",
                lambda: self.locate_requested.emit(first),
            )
            if first.available:
                menu.addAction(icon("edit", TEXT, 16), "Renombrar archivo…", lambda: self.rename_file_requested.emit(first))
        available = [t for t in tracks if t.available]
        if available:
            count = "" if len(available) == 1 else f" ({len(available)})"
            menu.addAction(icon("move", TEXT, 16), f"Mover a otra carpeta{count}…", lambda: self.move_files_requested.emit(available))
        if self.table.reorderable():
            menu.addSeparator()
            up = menu.addAction(icon("arrow_up", TEXT, 16), "Subir", lambda: self._nudge_selected(-1))
            up.setShortcut(QKeySequence(Qt.Modifier.ALT | Qt.Key.Key_Up))
            down = menu.addAction(icon("arrow_down", TEXT, 16), "Bajar", lambda: self._nudge_selected(1))
            down.setShortcut(QKeySequence(Qt.Modifier.ALT | Qt.Key.Key_Down))
            menu.addAction("Mover al principio", lambda: self._move_to_position(1))
            menu.addAction("Mover al final", lambda: self._move_to_position(self.proxy.rowCount()))
            menu.addAction("Mover a la posición…", self._ask_position)
            if self._reset_label:
                menu.addAction(self._reset_label, self.reset_order_requested.emit)
            menu.addSeparator()
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
