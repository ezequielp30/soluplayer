"""Diálogos: informe de importación, opciones de carpeta y nombres de playlist."""

from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QToolTip,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import backup
from ..file_ops import move_to_trash
from ..importer import ImportFailure
from ..online_lookup import SOURCES
from ..preferences import Preferences
from . import theme
from .theme_picker import ThemePicker
from ..utils import plural


class FolderImportDialog(QDialog):
    """Confirma la carpeta y pregunta si se incluyen las subcarpetas."""

    def __init__(self, folder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Importar carpeta")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Se buscarán archivos de audio compatibles en:"))
        path = QLabel(f"<b>{_escape(folder)}</b>")
        path.setWordWrap(True)
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path)
        self.recursive = QCheckBox("Incluir también todas las subcarpetas")
        self.recursive.setChecked(True)
        layout.addSpacing(6)
        layout.addWidget(self.recursive)
        note = QLabel(
            "Los archivos no se moverán, renombrarán ni eliminarán. "
            "Las canciones que ya estén en la biblioteca no se agregarán de nuevo."
        )
        note.setWordWrap(True)
        note.setObjectName("EmptyMessage")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Importar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ImportReportDialog(QDialog):
    def __init__(
        self,
        added: int,
        duplicates: list[str],
        failures: list[ImportFailure],
        ignored: int,
        cancelled: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resultado de la importación")
        self.resize(720, 460 if failures or duplicates else 200)
        layout = QVBoxLayout(self)

        danger = theme.color("danger")
        lines = []
        if cancelled:
            lines.append("<b>La importación se canceló.</b> Se conservaron las canciones leídas hasta ese momento.")
        if added:
            lines.append(f"Se importaron <b>{plural(added, 'canción', 'canciones')}</b>.")
        else:
            lines.append("No se importó ninguna canción nueva.")
        if duplicates:
            lines.append(
                f"• {plural(len(duplicates), 'archivo')} ya "
                f"{'estaba' if len(duplicates) == 1 else 'estaban'} en la biblioteca y se "
                f"{'omitió' if len(duplicates) == 1 else 'omitieron'}."
            )
        if failures:
            lines.append(
                f"• <span style='color:{danger}'><b>{plural(len(failures), 'archivo')} no se "
                f"{'pudo' if len(failures) == 1 else 'pudieron'} agregar.</b></span> El motivo aparece abajo."
            )
        corrupt_count = sum(1 for f in failures if f.corrupt)
        if corrupt_count:
            lines.append(
                f"• {plural(corrupt_count, 'archivo')} "
                f"{'está dañado o vacío' if corrupt_count == 1 else 'están dañados o vacíos'}. "
                "Aparecen marcados abajo: si quieres, puedes enviarlos a la Papelera de reciclaje."
            )
        if ignored:
            lines.append(
                f"• Se ignoraron {plural(ignored, 'archivo')} que no son de audio compatible "
                "(imágenes, textos, etc.)."
            )
        summary = QLabel("<br>".join(lines))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self._corrupt_items: list[QTreeWidgetItem] = []
        self.tree: QTreeWidget | None = None
        if failures or duplicates:
            tree = QTreeWidget()
            tree.setHeaderLabels(["Archivo", "Motivo"])
            tree.setRootIsDecorated(False)
            tree.setAlternatingRowColors(True)
            for failure in failures:
                item = QTreeWidgetItem([os.path.basename(failure.path) or failure.path, failure.reason])
                item.setToolTip(0, failure.path)
                item.setToolTip(1, failure.reason)
                item.setData(0, Qt.ItemDataRole.UserRole, failure.path)
                if failure.corrupt:
                    # Solo los archivos dañados o vacíos se ofrecen para enviar a la papelera.
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    # Sin marcar por defecto: mutagen puede no entender un archivo que sí se reproduce.
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                    self._corrupt_items.append(item)
                tree.addTopLevelItem(item)
            for path in duplicates:
                item = QTreeWidgetItem([os.path.basename(path), "Ya estaba en la biblioteca."])
                item.setToolTip(0, path)
                item.setForeground(1, Qt.GlobalColor.gray)
                tree.addTopLevelItem(item)
            tree.header().resizeSection(0, 300)
            tree.itemChanged.connect(lambda *_: self._update_trash_button())
            layout.addWidget(tree, 1)
            self.tree = tree

        self.trash_result = QLabel()
        self.trash_result.setWordWrap(True)
        self.trash_result.hide()
        layout.addWidget(self.trash_result)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Aceptar")
        self.trash_button = buttons.addButton("", QDialogButtonBox.ButtonRole.ActionRole)
        self.trash_button.setToolTip(
            "Envía a la Papelera de reciclaje los archivos dañados marcados. Podrás recuperarlos desde la Papelera."
        )
        self.trash_button.clicked.connect(self._trash_selected)
        self.trash_button.setVisible(bool(self._corrupt_items))
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self._update_trash_button()

    def _checked_corrupt(self) -> list[QTreeWidgetItem]:
        return [
            item
            for item in self._corrupt_items
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable and item.checkState(0) == Qt.CheckState.Checked
        ]

    def _update_trash_button(self) -> None:
        count = len(self._checked_corrupt())
        self.trash_button.setText(f"Enviar a la papelera los dañados ({count})…")
        self.trash_button.setEnabled(count > 0)

    def _trash_selected(self) -> None:
        items = self._checked_corrupt()
        if not items:
            return
        choice = ask(
            self,
            "Enviar archivos dañados a la papelera",
            f"¿Enviar {plural(len(items), 'archivo dañado', 'archivos dañados')} a la Papelera de reciclaje?",
            [("Enviar a la papelera", QMessageBox.ButtonRole.DestructiveRole), ("Cancelar", QMessageBox.ButtonRole.RejectRole)],
            QMessageBox.Icon.Warning,
            "No se borran de forma definitiva: podrás recuperarlos desde la Papelera de Windows.",
        )
        if choice != 0:
            return
        paths = [item.data(0, Qt.ItemDataRole.UserRole) for item in items]
        moved, failed = move_to_trash(paths)
        failed_reasons = dict(failed)
        for item, path in zip(items, paths, strict=True):
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(0, Qt.ItemDataRole.CheckStateRole, None)
            if path in failed_reasons:
                item.setText(1, f"No se envió a la papelera: {failed_reasons[path]}")
                item.setForeground(1, Qt.GlobalColor.darkRed)
            else:
                item.setText(1, "Enviado a la Papelera de reciclaje.")
                item.setForeground(1, Qt.GlobalColor.darkGreen)
        self.trashed_paths = getattr(self, "trashed_paths", []) + moved
        message = f"{plural(len(moved), 'archivo enviado', 'archivos enviados')} a la Papelera."
        if failed:
            message += f" {plural(len(failed), 'archivo')} no se pudo enviar (el motivo aparece en la lista)."
        self.trash_result.setText(message)
        self.trash_result.show()
        self._update_trash_button()


class PlaylistNameDialog(QDialog):
    """Pide un nombre y lo valida con la función dada (que lanza ValueError con el motivo)."""

    def __init__(self, title: str, label: str, initial: str, validate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self._validate = validate
        self.result_value = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(label))
        self.edit = QLineEdit(initial)
        self.edit.selectAll()
        self.edit.setMaxLength(120)
        layout.addWidget(self.edit)
        self.error = QLabel()
        self.error.setStyleSheet(f"color: {theme.color('danger')};")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Aceptar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.edit.textChanged.connect(lambda _: self.error.hide())

    def _try_accept(self) -> None:
        try:
            self.result_value = self._validate(self.edit.text())
        except ValueError as exc:
            self.error.setText(str(exc))
            self.error.show()
            self.edit.setFocus()
            return
        self.accept()


class PreferencesDialog(QDialog):
    def __init__(self, prefs: Preferences, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferencias")
        self.setMinimumWidth(520)
        self._prefs = prefs
        outer = QVBoxLayout(self)
        tabs = QTabWidget()
        outer.addWidget(tabs)
        theme_page, general_page = QWidget(), QWidget()
        tabs.addTab(theme_page, "Tema")
        tabs.addTab(general_page, "General")
        layout = QVBoxLayout(general_page)
        theme_layout = QVBoxLayout(theme_page)

        appearance = QGroupBox("Elige un tema")
        appearance_layout = QVBoxLayout(appearance)
        self._original_theme = theme.mode()
        self.theme_picker = ThemePicker(prefs.theme)
        self.theme_buttons = self.theme_picker.buttons
        # Vista previa en vivo: el tema elegido se aplica al momento; «Cancelar» vuelve al anterior.
        self.theme_picker.chosen.connect(lambda key: theme.apply(QApplication.instance(), key))
        appearance_layout.addWidget(self.theme_picker)
        appearance_layout.addWidget(note_label("Se aplica al instante como vista previa; «Guardar» lo deja para las próximas veces."))
        theme_layout.addWidget(appearance)
        theme_layout.addStretch(1)

        online = QGroupBox("Datos en internet (Herramientas → Buscar datos en internet)")
        online_layout = QVBoxLayout(online)
        online_layout.addWidget(QLabel("Bases de datos que se usan por defecto:"))
        self.source_boxes: dict[str, QCheckBox] = {}
        for key, source in SOURCES.items():
            box = QCheckBox(f"{source.name} — {source.description}")
            box.setChecked(key in prefs.online_sources)
            self.source_boxes[key] = box
            online_layout.addWidget(box)
        self.online_covers = QCheckBox("Descargar también la carátula")
        self.online_covers.setChecked(prefs.online_covers)
        online_layout.addWidget(self.online_covers)
        layout.addWidget(online)

        group = QGroupBox("Importación de música")
        group_layout = QVBoxLayout(group)
        self.ask_titles = QCheckBox(
            "Al importar, preguntar si quiero completar los títulos de las canciones que no tienen título"
        )
        self.ask_titles.setChecked(prefs.ask_titles_on_import)
        hint = QLabel(
            "Si una canción no trae el título en sus etiquetas, se te mostrará un título propuesto "
            "(a partir del nombre del archivo) que podrás revisar y editar antes de agregarla. "
            "Los títulos se guardan solo en la biblioteca: los archivos no se modifican."
        )
        hint.setWordWrap(True)
        hint.setObjectName("EmptyMessage")
        self.detect_artist = QCheckBox("Proponer también el artista si el nombre es «Artista - Título»")
        self.detect_artist.setChecked(prefs.detect_artist_in_filename)
        self.detect_artist.setEnabled(self.ask_titles.isChecked())
        self.ask_titles.toggled.connect(self.detect_artist.setEnabled)
        group_layout.addWidget(self.ask_titles)
        group_layout.addWidget(hint)
        group_layout.addSpacing(4)
        group_layout.addWidget(self.detect_artist)
        layout.addWidget(group)

        library = QGroupBox("Biblioteca")
        library_layout = QVBoxLayout(library)
        self.remove_missing = QCheckBox(
            "Al abrir el programa, revisar si faltan canciones o carpetas en el disco (y preguntar si quitarlas)"
        )
        self.remove_missing.setChecked(prefs.remove_missing_on_start)
        library_layout.addWidget(self.remove_missing)
        library_layout.addWidget(note_label(
            "Se quitan solo de la biblioteca y de las playlists (no se borra ningún archivo), con un respaldo "
            "previo. Las de un disco externo o de red desconectado se conservan hasta que vuelva a estar."
        ))
        layout.addWidget(library)
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _save(self) -> None:
        # Primero se valida y después se guarda: cada preferencia se escribe al instante, así que
        # guardar algo antes de validar haría que «Cancelar» no deshiciera nada.
        chosen = [k for k, box in self.source_boxes.items() if box.isChecked()]
        if not chosen:
            QMessageBox.information(self, "Datos en internet", "Marca al menos una base de datos.")
            return
        self._prefs.ask_titles_on_import = self.ask_titles.isChecked()
        self._prefs.detect_artist_in_filename = self.detect_artist.isChecked()
        self._prefs.remove_missing_on_start = self.remove_missing.isChecked()
        self._prefs.theme = self.theme_picker.selected()
        self._prefs.online_sources = chosen
        self._prefs.online_covers = self.online_covers.isChecked()
        self.accept()

    def reject(self) -> None:
        # Se descarta la vista previa: vuelve el tema que había al abrir Preferencias.
        if theme.mode() != self._original_theme:
            theme.apply(QApplication.instance(), self._original_theme)
        super().reject()


class TitleReviewDialog(QDialog):
    """Muestra las canciones sin título con una propuesta editable.

    `rows` = lista de (ruta, título propuesto, artista propuesto o None).
    Tras aceptar, `results()` devuelve {índice: (título, artista o None)} de las filas marcadas.
    """

    COL_USE, COL_FILE, COL_TITLE, COL_ARTIST = range(4)

    def __init__(self, rows: list[tuple[str, str, str | None]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Canciones sin título")
        self.resize(820, 480)
        layout = QVBoxLayout(self)
        intro = QLabel(
            f"Se {'detectó' if len(rows) == 1 else 'detectaron'} <b>{plural(len(rows), 'canción', 'canciones')} "
            "sin título</b> en sus etiquetas.<br>¿Quieres agregarles estos títulos? Puedes editarlos "
            "(doble clic en la celda) y desmarcar las que prefieras dejar con el nombre del archivo."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(note_label("Solo se guarda en la biblioteca; los archivos no se modifican."))

        self.table = QTableWidget(len(rows), 4)
        self.table.setHorizontalHeaderLabels(["", "Archivo", "Título", "Artista"])
        tidy_table(self.table)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_USE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_FILE, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(self.COL_TITLE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_ARTIST, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(self.COL_FILE, 240)
        header.resizeSection(self.COL_ARTIST, 180)
        for row, (path, title, artist) in enumerate(rows):
            use = QTableWidgetItem()
            use.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            use.setCheckState(Qt.CheckState.Checked)
            file_item = QTableWidgetItem(os.path.basename(path))
            file_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            file_item.setToolTip(path)
            artist_item = QTableWidgetItem(artist or "")
            artist_item.setToolTip("Déjalo vacío para mantener el artista actual")
            self.table.setItem(row, self.COL_USE, use)
            self.table.setItem(row, self.COL_FILE, file_item)
            self.table.setItem(row, self.COL_TITLE, QTableWidgetItem(title))
            self.table.setItem(row, self.COL_ARTIST, artist_item)
        layout.addWidget(self.table, 1)

        self.check_all = QCheckBox("Marcar todas")
        self.check_all.setChecked(True)
        self.check_all.toggled.connect(self._set_all)
        layout.addWidget(self.check_all)

        buttons = QDialogButtonBox()
        apply = buttons.addButton("Agregar con estos títulos", QDialogButtonBox.ButtonRole.AcceptRole)
        apply.setObjectName("PrimaryButton")
        buttons.addButton("Omitir (usar el nombre del archivo)", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.table.rowCount()):
            self.table.item(row, self.COL_USE).setCheckState(state)

    def results(self) -> dict[int, tuple[str, str | None]]:
        chosen: dict[int, tuple[str, str | None]] = {}
        for row in range(self.table.rowCount()):
            if self.table.item(row, self.COL_USE).checkState() != Qt.CheckState.Checked:
                continue
            title = " ".join(self.table.item(row, self.COL_TITLE).text().split())
            artist = " ".join(self.table.item(row, self.COL_ARTIST).text().split()) or None
            if title:
                chosen[row] = (title, artist)
        return chosen


def ask(parent: QWidget, title: str, text: str, buttons: list[tuple[str, QMessageBox.ButtonRole]],
        icon=QMessageBox.Icon.Question, informative: str = "") -> int:
    """Pregunta con botones en español. Devuelve el índice del botón elegido (-1 si se cierra)."""
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    if informative:
        box.setInformativeText(informative)
    created = [box.addButton(label, role) for label, role in buttons]
    if created:
        box.setDefaultButton(created[0])
    box.exec()
    clicked = box.clickedButton()
    return created.index(clicked) if clicked in created else -1


def backup_before(parent: QWidget, conn, reason: str) -> bool:
    """Respaldo de la biblioteca antes de modificar archivos. Si falla, pregunta si seguir sin él.
    Devuelve False si el usuario prefiere cancelar."""
    if backup.create_backup(conn, reason) is not None:
        return True
    return confirm_without_backup(parent)


def confirm_without_backup(parent: QWidget) -> bool:
    """El respaldo previo falló: ¿seguir sin él? (Por defecto, no.)"""
    return ask(
        parent,
        "Respaldo",
        "No se pudo crear el respaldo de la biblioteca antes de empezar.",
        [("Cancelar", QMessageBox.ButtonRole.RejectRole),
         ("Continuar sin respaldo", QMessageBox.ButtonRole.DestructiveRole)],
        QMessageBox.Icon.Warning,
        "Los detalles están en el registro (Ayuda → Abrir registro de errores). Puede deberse a falta de "
        "espacio en el disco. La operación se puede deshacer igualmente, pero sin respaldo no se podría "
        "recuperar la biblioteca si algo saliera mal.",
    ) == 1


def note_label(text: str) -> QLabel:
    """Texto secundario de un diálogo. El color lo pone la hoja de estilos (#DialogNote), así que
    cambia solo con el tema (un color escrito dentro del texto no se actualizaría)."""
    label = QLabel(text)
    label.setObjectName("DialogNote")
    label.setWordWrap(True)
    return label


def tool_intro(text: str, details: str) -> QWidget:
    """Encabezado compacto de las herramientas: una sola línea y un «?» con la explicación completa
    (como hacen foobar2000, Picard o MusicBee: lo necesario a la vista y el detalle a pedido)."""
    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    label = note_label(text)
    label.setWordWrap(False)
    info = QToolButton()
    info.setObjectName("InfoButton")
    info.setText("?")
    info.setToolTip(details)
    info.setCursor(Qt.CursorShape.WhatsThisCursor)
    info.clicked.connect(lambda: QToolTip.showText(info.mapToGlobal(info.rect().bottomLeft()), details, info))
    row.addWidget(label)
    row.addWidget(info)
    row.addStretch(1)
    return widget


class StatusLabel(QLabel):
    """Línea de estado que solo ocupa lugar cuando tiene algo que decir (vacía, se oculta)."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DialogNote")
        self.hide()

    def setText(self, text: str) -> None:  # noqa: N802 (nombre de Qt)
        super().setText(text)
        self.setVisible(bool(text))


class ResultBanner(QLabel):
    """Resultado de la última operación en una franja dentro de la ventana (en lugar de un aviso emergente).
    Se oculta al empezar otra operación."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ResultBanner")
        self.setWordWrap(True)
        self.hide()

    def show_result(self, text: str, ok: bool = True) -> None:
        self.setProperty("kind", "ok" if ok else "warn")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText(("✓  " if ok else "⚠  ") + text)
        self.show()

    def clear(self) -> None:
        self.setText("")
        self.hide()


def empty_state() -> tuple[QWidget, Callable[[str, str], None]]:
    """Estado vacío para el lugar de una tabla (como el del panel principal): título y explicación
    centrados. Devuelve el widget y una función para cambiar sus textos."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.addStretch(1)
    title = QLabel()
    title.setObjectName("EmptyTitle")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    message = QLabel()
    message.setObjectName("EmptyMessage")
    message.setAlignment(Qt.AlignmentFlag.AlignCenter)
    message.setWordWrap(True)
    layout.addWidget(title)
    layout.addWidget(message)
    layout.addStretch(2)

    def set_text(heading: str, text: str) -> None:
        title.setText(heading)
        message.setText(text)

    return widget, set_text


def set_primary(button: QPushButton, primary: bool) -> None:
    """Marca o desmarca el botón ámbar (la acción principal de la zona) y redibuja su estilo."""
    if (button.objectName() == "PrimaryButton") == primary:
        return
    button.setObjectName("PrimaryButton" if primary else "")
    button.style().unpolish(button)
    button.style().polish(button)


def tidy_table(table) -> None:
    """Aspecto común de las tablas de los diálogos: sin cuadrícula y encabezados alineados a la izquierda."""
    table.setShowGrid(False)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
