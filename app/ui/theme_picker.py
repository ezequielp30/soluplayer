"""Selector de temas con vista previa: una tarjeta por tema con una miniatura de la ventana dibujada con
sus colores (barra, lista lateral, botón de acento, filas de canciones). Al elegir una, el tema se
aplica en el acto a todo el programa; quien lo usa puede volver al anterior si se cancela."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QToolButton, QWidget

from . import theme

PREVIEW = QSize(132, 82)


def preview_pixmap(p: theme.Palette, ratio: float = 2.0) -> QPixmap:
    w, h = PREVIEW.width(), PREVIEW.height()
    pixmap = QPixmap(int(w * ratio), int(h * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
    painter.setClipPath(clip)
    painter.fillRect(QRectF(0, 0, w, h), QColor(p.bg))
    painter.fillRect(QRectF(0, 0, w, 18), QColor(p.bar))  # barra del reproductor
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(p.accent))
    painter.drawEllipse(QRectF(6, 3, 12, 12))  # botón reproducir
    painter.setBrush(QColor(p.muted))
    painter.drawRoundedRect(QRectF(24, 8, 46, 3), 1.5, 1.5)  # progreso
    painter.setBrush(QColor(p.accent))
    painter.drawRoundedRect(QRectF(24, 8, 20, 3), 1.5, 1.5)
    painter.fillRect(QRectF(0, 18, 38, h - 18), QColor(p.sidebar))  # barra lateral
    painter.setBrush(QColor(p.accent_soft))
    painter.drawRoundedRect(QRectF(4, 36, 30, 8), 3, 3)  # elemento seleccionado
    painter.setBrush(QColor(p.faint))
    for y in (26, 48, 58):
        painter.drawRoundedRect(QRectF(6, y, 22, 3), 1.5, 1.5)
    painter.setBrush(QColor(p.text))
    painter.drawRoundedRect(QRectF(46, 25, 40, 5), 2, 2)  # título
    for i, y in enumerate((38, 48, 58, 68)):
        if i % 2:
            painter.fillRect(QRectF(38, y - 3, w - 38, 9), QColor(p.row_alt))
        painter.setBrush(QColor(p.accent_text if i == 1 else p.text))
        painter.drawRoundedRect(QRectF(46, y, 44, 3), 1.5, 1.5)
        painter.setBrush(QColor(p.muted))
        painter.drawRoundedRect(QRectF(96, y, 26, 3), 1.5, 1.5)
    painter.setClipping(False)
    painter.setPen(QColor(p.border))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
    painter.end()
    return pixmap


def auto_pixmap() -> QPixmap:
    """«Automático»: mitad clara y mitad oscura."""
    light, dark = preview_pixmap(theme.ALUMINIUM), preview_pixmap(theme.GRAPHITE)
    result = QPixmap(light.size())
    result.setDevicePixelRatio(light.devicePixelRatio())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.drawPixmap(0, 0, light)
    half = light.width() / light.devicePixelRatio() / 2
    painter.setClipRect(QRectF(half, 0, half, PREVIEW.height()))
    painter.drawPixmap(0, 0, dark)
    painter.end()
    return result


class ThemePicker(QWidget):
    """Cuadrícula de tarjetas. `buttons` asocia la clave del tema con su tarjeta («light»/«dark» son
    alias de Aluminio/Grafito, por compatibilidad)."""

    chosen = Signal(str)

    def __init__(self, selected: str, parent: QWidget | None = None, columns: int = 4) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: dict[str, QToolButton] = {}
        entries = [(theme.MODE_AUTO, "Automático", auto_pixmap())]
        entries += [(key, p.name, preview_pixmap(p)) for key, p in theme.THEMES.items()]
        for index, (key, name, pixmap) in enumerate(entries):
            button = QToolButton()
            button.setObjectName("ThemeCard")
            button.setCheckable(True)
            button.setIcon(QIcon(pixmap))
            button.setIconSize(PREVIEW)
            button.setText(name)
            button.setToolTip("Sigue el modo claro u oscuro de Windows" if key == theme.MODE_AUTO else f"Tema {name}")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _c=False, k=key: self.chosen.emit(k))
            self._group.addButton(button)
            self.buttons[key] = button
            grid.addWidget(button, index // columns, index % columns)
        self.buttons[theme.MODE_LIGHT] = self.buttons["aluminio"]
        self.buttons[theme.MODE_DARK] = self.buttons["grafito"]
        self.select(selected)

    def select(self, key: str) -> None:
        button = self.buttons.get(key) or self.buttons[theme.MODE_AUTO]
        button.setChecked(True)

    def selected(self) -> str:
        for key, button in self.buttons.items():
            if button.isChecked() and key not in (theme.MODE_LIGHT, theme.MODE_DARK):
                return key
        return theme.MODE_AUTO
