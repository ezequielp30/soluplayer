"""Modelo de tabla para listas de canciones."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QByteArray, QMimeData, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QFont

from ..models import Track
from ..utils import format_time, natural_key
from . import theme
from .covers import CoverProvider
from .icons import ACCENT, MUTED, icon, padded_pixmap

import os

COL_TITLE, COL_ARTIST, COL_ALBUM, COL_GENRE, COL_FILE, COL_DURATION, COL_ACTION = range(7)
HEADERS = ["Título", "Artista", "Álbum", "Género", "Archivo", "Duración", ""]

# Datos que se pueden mostrar u ocultar (Preferencias → Canciones, o clic derecho en los encabezados).
# El título se ve siempre. "cover" no es una columna: la carátula pequeña junto al título.
SONG_COLUMNS = [
    ("number", "Número de orden (1, 2, 3…)", None),
    ("artist", "Artista", COL_ARTIST),
    ("album", "Álbum", COL_ALBUM),
    ("genre", "Género", COL_GENRE),
    ("file", "Nombre del archivo", COL_FILE),
    ("duration", "Duración", COL_DURATION),
    ("cover", "Carátula", None),
]
DEFAULT_SONG_COLUMNS = ["number", "artist", "album", "duration", "cover"]

# En qué orden está (y suena) una lista: el selector «Orden:» del panel.
ORDER_MANUAL, ORDER_DEFAULT, ORDER_RANDOM, ORDER_OTHER = "manual", "default", "random", "other"
ORDER_COLUMNS = [  # (clave, texto, columna, descendente)
    ("title_asc", "Título (A–Z)", COL_TITLE, False),
    ("title_desc", "Título (Z–A)", COL_TITLE, True),
    ("artist_asc", "Artista (A–Z)", COL_ARTIST, False),
    ("artist_desc", "Artista (Z–A)", COL_ARTIST, True),
    ("album_asc", "Álbum (A–Z)", COL_ALBUM, False),
    ("album_desc", "Álbum (Z–A)", COL_ALBUM, True),
    ("duration_asc", "Duración (cortas primero)", COL_DURATION, False),
    ("duration_desc", "Duración (largas primero)", COL_DURATION, True),
]
ROW_COVER_SIZE = 40

TRACK_ROLE = Qt.ItemDataRole.UserRole + 1
SORT_ROLE = Qt.ItemDataRole.UserRole + 2


def move_rows(items: list, rows: list[int], target: int) -> list:
    """Mueve las filas `rows` (en su orden) para que queden juntas antes de la fila `target` de `items`
    (len(items) = al final). Es lo que hace soltar canciones arrastradas."""
    chosen = sorted(set(r for r in rows if 0 <= r < len(items)))
    picked = set(chosen)
    rest = [item for i, item in enumerate(items) if i not in picked]
    target -= sum(1 for r in chosen if r < target)
    target = max(0, min(target, len(rest)))
    return rest[:target] + [items[r] for r in chosen] + rest[target:]


class TrackTableModel(QAbstractTableModel):
    def __init__(self, covers: CoverProvider, parent=None) -> None:
        super().__init__(parent)
        self._covers = covers
        self._tracks: list[Track] = []
        self._current_id: int | None = None
        self._show_covers = True
        self._bold = QFont()
        self._bold.setBold(True)
        self._italic = QFont()
        self._italic.setItalic(True)

    # ------------------------------------------------------------------ datos

    def set_tracks(self, tracks: list[Track]) -> None:
        self.beginResetModel()
        self._tracks = list(tracks)
        self.endResetModel()

    def tracks(self) -> list[Track]:
        return list(self._tracks)

    def track_at(self, row: int) -> Track | None:
        return self._tracks[row] if 0 <= row < len(self._tracks) else None

    def set_show_covers(self, show: bool) -> None:
        if show != self._show_covers:
            self._show_covers = show
            self.repaint_all()

    def set_current_track(self, track_id: int | None) -> None:
        self._current_id = track_id
        self.repaint_all()

    def repaint_all(self) -> None:
        """Vuelve a pedir colores e iconos (p. ej. tras cambiar de tema)."""
        if self._tracks:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._tracks) - 1, len(HEADERS) - 1))

    def refresh_track(self, track: Track) -> None:
        for row, existing in enumerate(self._tracks):
            if existing.id == track.id:
                self._tracks[row] = track.copy(entry_id=existing.entry_id)
                self.dataChanged.emit(self.index(row, 0), self.index(row, len(HEADERS) - 1))

    # ------------------------------------------------------------------ Qt

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._tracks)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(HEADERS)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled  # soltar entre filas (nunca «sobre» una canción)
        return super().flags(index) | Qt.ItemFlag.ItemIsDragEnabled

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def mimeData(self, indexes):
        """Arrastrar solo reordena dentro de la tabla (las filas las toma la vista): sin copiar los datos de
        cada canción, que con muchas seleccionadas incluía todas sus carátulas."""
        data = QMimeData()
        data.setData(self.mimeTypes()[0], QByteArray())
        return data

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[section]
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.TextAlignmentRole
            and section == COL_DURATION
        ):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        track = self._tracks[index.row()]
        col = index.column()
        is_current = track.id == self._current_id

        if role == TRACK_ROLE:
            return track
        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_TITLE:
                return track.title
            if col == COL_ARTIST:
                return track.artist
            if col == COL_ALBUM:
                return track.album
            if col == COL_GENRE:
                return track.genre
            if col == COL_FILE:
                return os.path.basename(track.path)
            if col == COL_DURATION:
                return format_time(track.duration_ms) if track.duration_ms else "—"
        if role == SORT_ROLE:
            if col == COL_DURATION:
                return track.duration_ms
            if col == COL_ACTION:
                return index.row()
            return natural_key(self.data(index, Qt.ItemDataRole.DisplayRole) or "")
        if role == Qt.ItemDataRole.DecorationRole:
            if col == COL_ACTION:
                return padded_pixmap("add_circle", MUTED, 20, ROW_COVER_SIZE)
            if col == COL_TITLE:
                if not track.available:
                    return icon("warning", "warning", ROW_COVER_SIZE if self._show_covers else 18)
                if self._show_covers:
                    return self._covers.pixmap(track.cover_hash, ROW_COVER_SIZE)
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == COL_ACTION:
                return "Agregar a playlist"
            if not track.available:
                return (
                    f"No se encuentra el archivo:\n{track.path}\n\n"
                    "Puede haberse movido, renombrado o eliminado, o estar en una unidad "
                    "desconectada. Haz clic derecho y elige «Localizar archivo»."
                )
            return f"{track.title}\n{track.artist} — {track.album}\n{track.path}"
        if role == Qt.ItemDataRole.ForegroundRole:
            if not track.available:
                return theme.qcolor("faint")
            if is_current:
                return theme.qcolor(ACCENT)
            if col in (COL_ARTIST, COL_ALBUM, COL_GENRE, COL_FILE, COL_DURATION):
                return theme.qcolor(MUTED)
        if role == Qt.ItemDataRole.FontRole:
            if is_current and track.available:
                return self._bold
            if not track.available:
                return self._italic
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == COL_DURATION:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if col == COL_ACTION:
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None


class TrackSortProxy(QSortFilterProxyModel):
    """Permite ordenar por columna. Sin orden elegido respeta el orden original."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSortRole(SORT_ROLE)
        self.setDynamicSortFilter(False)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        # El número de cada fila es su lugar en el orden que se ve (y que va a sonar), no el del modelo.
        if orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return section + 1
        return super().headerData(section, orientation, role)
