"""Hoja de estilos (QSS) generada a partir de la paleta del tema activo."""

from __future__ import annotations

import logging

from ..config import data_dir
from .theme import Palette

log = logging.getLogger(__name__)

FONT = '"Segoe UI Variable Text", "Segoe UI", sans-serif'
FONT_DISPLAY = '"Segoe UI Variable Display", "Segoe UI", sans-serif'
FONT_DIGITS = '"Cascadia Mono", "Consolas", monospace'  # tiempos de la pantalla, como un visor digital


_CHEVRONS = {"down": "M6 9l6 6 6-6", "right": "M9 6l6 6-6 6"}


def _chevron(direction: str, color: str) -> str:
    """Flecha («chevron») en PNG con el color del tema, para las listas desplegables y el árbol de
    carpetas. Las hojas de estilo de Qt solo aceptan imágenes desde archivo; se generan en PNG (no SVG)
    para no depender del complemento de imágenes SVG en el programa instalado. Devuelve la ruta para
    url(…) con barras normales, o "" si no se pudo crear (Qt usa entonces su flecha estándar)."""
    try:
        from PySide6.QtCore import QByteArray, QRectF, Qt
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer

        folder = data_dir() / "estilo"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"chevron-{direction}-{color.lstrip('#')}.png"
        if not path.exists():
            svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="none" '
                f'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" '
                f'd="{_CHEVRONS[direction]}"/></svg>'
            )
            image = QImage(48, 48, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(0, 0, 48, 48))
            painter.end()
            if not image.save(str(path), "PNG"):
                raise OSError(f"no se pudo guardar {path}")
        return path.as_posix()
    except Exception as exc:  # una flecha que falta no debe impedir que el programa arranque
        log.warning("No se pudo crear la flecha %s: %s", direction, exc)
        return ""


def _arrow_rules(p: Palette) -> str:
    down, right = _chevron("down", p.muted), _chevron("right", p.muted)
    rules = """
QComboBox::drop-down {{ border: none; width: 26px; subcontrol-origin: padding; subcontrol-position: center right; }}
"""
    # Ojo: una regla genérica «QTreeView::branch { background: … }» hace que Qt dibuje rayas verticales
    # en la sangría de la fila seleccionada; el fondo de la sangría se fija solo en la barra lateral.
    if down:
        rules += f"QComboBox::down-arrow {{{{ image: url(\"{down}\"); width: 12px; height: 12px; }}}}\n"
        rules += (
            "QTreeView::branch:open:has-children:!has-siblings, QTreeView::branch:open:has-children:has-siblings "
            f"{{{{ image: url(\"{down}\"); }}}}\n"
        )
    if right:
        rules += (
            "QTreeView::branch:closed:has-children:!has-siblings, QTreeView::branch:closed:has-children:has-siblings "
            f"{{{{ image: url(\"{right}\"); }}}}\n"
        )
    return rules.replace("{{", "{").replace("}}", "}")


def _mix(color: str, base: str, amount: float) -> str:
    """«color» sobre «base» con opacidad «amount», como hex (QSS no mezcla colores por sí mismo)."""
    a, b = color.lstrip("#"), base.lstrip("#")
    return "#" + "".join(
        f"{round(int(a[i:i + 2], 16) * amount + int(b[i:i + 2], 16) * (1 - amount)):02x}" for i in (0, 2, 4)
    )


def build_stylesheet(p: Palette) -> str:
    soft = 0.10 if p.dark else 0.08  # intensidad de la píldora de los títulos de sección
    return _arrow_rules(p) + f"""
* {{
    font-family: {FONT};
    font-size: 10pt;
    color: {p.text};
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
}}
QMainWindow, #ContentPanel, QDialog {{ background: {p.bg}; }}
QToolTip {{
    background: {p.elevated};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 6px;
    padding: 5px 8px;
}}

/* ---------- barra de menús y menús ---------- */
QMenuBar {{ background: {p.bar}; padding: 2px 6px; }}
QMenuBar::item {{ background: transparent; padding: 5px 10px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {p.hover}; }}
QMenu {{
    background: {p.elevated};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{ padding: 7px 26px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
QMenu::item:disabled {{ color: {p.muted}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 8px; }}
QMenu::icon {{ padding-left: 8px; }}

/* ---------- barra del reproductor ---------- */
#PlayerBar {{
    background: {p.bar};
    border-bottom: 1px solid {p.border};
}}
/* La canción actual va en una «pantalla» como el visor LCD de los reproductores clásicos. */
#NowPlaying {{
    background: {p.lcd_bg};
    border: 1px solid {_mix(p.lcd_text, p.lcd_bg, 0.18)};
    border-radius: 12px;
}}
#NowPlaying QLabel {{ background: transparent; }}
#NowTitle {{ font-weight: 600; font-size: 10.5pt; color: {p.lcd_text}; }}
#NowSubtitle {{ color: {p.lcd_muted}; font-size: 9pt; }}
#TimeLabel {{ color: {p.lcd_muted}; font-family: {FONT_DIGITS}; font-size: 8.5pt; min-width: 40px; }}
#NowPlaying QSlider::groove:horizontal {{ background: {_mix(p.lcd_text, p.lcd_bg, 0.22)}; }}
#NowPlaying QSlider::sub-page:horizontal {{ background: {p.lcd_text}; }}
#NowPlaying QSlider::handle:horizontal {{ background: {p.lcd_text}; }}
#NowPlaying QSlider::sub-page:horizontal:disabled, #NowPlaying QSlider::handle:horizontal:disabled {{
    background: {_mix(p.lcd_muted, p.lcd_bg, 0.5)};
}}
QToolButton {{
    border: none;
    border-radius: 8px;
    padding: 5px;
    background: transparent;
}}
QToolButton:hover {{ background: {p.hover}; }}
QToolButton:pressed {{ background: {p.border}; }}
QToolButton:checked {{ background: {p.accent_soft}; }}
QToolButton:focus {{ outline: none; }}
QToolButton#ThemeCard {{
    border: 2px solid transparent;
    border-radius: 12px;
    padding: 6px 6px 4px 6px;
    font-size: 9pt;
}}
QToolButton#ThemeCard:hover {{ background: {p.hover}; }}
QToolButton#ThemeCard:checked {{ background: {p.accent_soft}; border: 2px solid {p.accent}; font-weight: 600; }}
QToolButton#PlayButton {{
    background: {p.accent};
    border-radius: 22px;
}}
QToolButton#PlayButton:hover {{ background: {p.accent_hover}; }}
QToolButton#PlayButton:pressed {{ background: {p.accent}; padding-top: 6px; }}

QLineEdit {{
    background: {p.elevated};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 6px 8px;
    selection-background-color: {p.accent_soft};
}}
QLineEdit:focus {{ border: 1px solid {p.accent}; }}
QLineEdit#SearchField {{
    border-radius: 20px;
    padding: 8px 14px 8px 8px;
    min-width: 140px;
    min-height: 24px;
    font-size: 11.5pt;
}}

QSlider {{ min-height: 18px; }}
QSlider::groove:horizontal {{
    height: 4px;
    background: {p.border if p.dark else _mix(p.faint, p.bg, 0.55)};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {p.accent};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {p.text};
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{ background: {p.accent_hover}; }}
QSlider::sub-page:horizontal:disabled {{ background: {p.border}; }}
QSlider::handle:horizontal:disabled {{ background: {p.border}; }}

/* ---------- ecualizador ---------- */
#EqBoard {{ background: {p.elevated}; border: 1px solid {p.border}; border-radius: 12px; padding: 10px; }}
#EqValue {{ color: {p.accent_text}; font-size: 8.5pt; font-weight: 600; min-width: 34px; }}
#EqBandLabel {{ color: {p.muted}; font-size: 8.5pt; }}
#EqDivider {{ color: {p.border}; }}
QSlider#EqSlider {{ min-width: 26px; background: transparent; }}
QSlider#EqSlider::groove:vertical {{ background: transparent; border: none; width: 26px; }}
QSlider#EqSlider::add-page:vertical {{ background: {p.accent}; border-radius: 2px; margin: 0 11px; }}
QSlider#EqSlider::sub-page:vertical {{ background: {p.border}; border-radius: 2px; margin: 0 11px; }}
QSlider#EqSlider::handle:vertical {{
    background: {p.text};
    height: 14px;
    width: 14px;
    margin: 0 6px;
    border-radius: 7px;
}}
QSlider#EqSlider::handle:vertical:hover {{ background: {p.accent_hover}; }}
QSlider#EqSlider::add-page:vertical:disabled {{ background: {p.faint}; }}
QSlider#EqSlider::handle:vertical:disabled {{ background: {p.faint}; }}
#EqSwitch {{ font-weight: 600; }}

/* ---------- barra lateral ---------- */
#Sidebar {{
    background: {p.sidebar};
    border-right: 1px solid {p.sidebar if p.dark else p.border};
}}
/* Títulos de sección: cada uno con su color e icono, sobre una píldora tenue del mismo color. */
#SectionHeader {{ border-radius: 7px; }}
#SectionHeader[section="library"] {{ background: {_mix(p.sec_library, p.sidebar, soft)}; }}
#SectionHeader[section="playlists"] {{ background: {_mix(p.sec_playlists, p.sidebar, soft)}; }}
#SectionHeader[section="folders"] {{ background: {_mix(p.sec_folders, p.sidebar, soft)}; }}
#SectionHeader QLabel {{ background: transparent; }}
#SectionTitle {{ font-size: 8pt; font-weight: 700; }}
#SectionHeader[section="library"] #SectionTitle {{ color: {p.sec_library}; }}
#SectionHeader[section="playlists"] #SectionTitle {{ color: {p.sec_playlists}; }}
#SectionHeader[section="folders"] #SectionTitle {{ color: {p.sec_folders}; }}
#SidebarHint {{ color: {p.muted}; font-size: 8.5pt; padding-left: 8px; }}
#Sidebar QListWidget, #Sidebar QTreeWidget {{
    background: transparent;
    border: none;
    outline: none;
}}
#Sidebar QListWidget::item, #Sidebar QTreeWidget::item {{
    border-radius: 8px;
    padding: 4px 6px;
    margin: 1px 0;
    color: {p.text};
}}
#Sidebar QListWidget::item:hover {{ background: {p.hover}; }}
/* En Carpetas el hover resalta el texto: un fondo se partiría en dos bloques (Qt pinta aparte la sangría). */
#Sidebar QTreeWidget::item:hover {{ background: transparent; color: {p.accent_text}; }}
#Sidebar QListWidget::item:selected, #Sidebar QTreeWidget::item:selected {{
    background: {p.accent_soft};
    color: {p.text};
    font-weight: 600;
}}
/* En las listas, la fila elegida lleva además una marca del acento a la izquierda. */
#Sidebar QListWidget::item:selected {{ border-left: 3px solid {p.accent}; padding-left: 3px; }}
#Sidebar QTreeWidget {{ show-decoration-selected: 0; }}
/* La sangría de la fila seleccionada con el fondo de la barra: se resalta la fila como un solo bloque
   (con «transparent» Qt la pinta igual con el color de selección). */
#Sidebar QTreeWidget::branch:selected, #Sidebar QTreeWidget::branch:hover {{ background: {p.sidebar}; }}
#Sidebar QSplitter::handle {{ background: transparent; }}

/* ---------- panel principal ---------- */
#HeaderTitle {{ font-family: {FONT_DISPLAY}; font-size: 24pt; font-weight: 700; }}
#HeaderSubtitle {{ color: {p.muted}; }}
#Breadcrumb {{ color: {p.muted}; font-size: 9pt; }}
QPushButton {{
    background: {p.elevated};
    border: 1px solid {p.border};
    border-radius: 9px;
    padding: 7px 14px;
}}
QPushButton:hover {{ background: {p.hover}; }}
QPushButton:pressed {{ background: {p.border}; }}
QPushButton:focus {{ border: 1px solid {p.accent}; }}
QPushButton:disabled {{ color: {p.faint}; }}
QPushButton::menu-indicator {{ subcontrol-position: right center; right: 8px; }}
QPushButton#PrimaryButton {{
    background: {p.accent};
    color: {p.on_accent};
    border: none;
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{ background: {p.accent_hover}; }}
/* Foco del botón ámbar: un anillo claro dentro del relleno (un borde negro parecía un error). */
QPushButton#PrimaryButton:focus {{ border: 2px solid {p.accent_soft}; }}
QPushButton#DangerButton {{ color: {p.danger}; border: 1px solid {p.danger}; }}
QPushButton#DangerButton:disabled {{ color: {p.faint}; border: 1px solid {p.border}; }}
#DialogNote {{ color: {p.muted}; }}
QToolButton#InfoButton {{
    border: 1px solid {p.border};
    border-radius: 9px;
    min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px;
    padding: 0;
    color: {p.muted};
    font-size: 8pt;
    font-weight: 700;
}}
QToolButton#InfoButton:hover {{ color: {p.accent_text}; border-color: {p.accent_text}; }}
#ResultBanner {{ border-radius: 8px; padding: 6px 10px; color: {p.text}; }}
#ResultBanner[kind="ok"] {{ background: {_mix(p.success, p.bg, 0.14)}; }}
#ResultBanner[kind="warn"] {{ background: {p.warning_soft}; }}
#MissingBanner {{
    background: {p.warning_soft};
    border-radius: 10px;
}}
#MissingBanner QLabel {{ color: {p.text}; }}
#EmptyTitle {{ font-family: {FONT_DISPLAY}; font-size: 15pt; font-weight: 600; }}
#EmptyMessage {{ color: {p.muted}; }}

QTableView, QTreeView, QListView {{
    background: {p.bg};
    alternate-background-color: {p.row_alt};
    border: none;
    outline: none;
}}
QTableView {{ selection-background-color: {p.accent_soft}; selection-color: {p.text}; }}
QTableView::item {{ padding: 0 8px; border: none; }}
QTableView::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {p.bg};
    color: {p.muted};
    border: none;
    border-bottom: 1px solid {p.border};
    padding: 8px;
    font-size: 9pt;
    font-weight: 600;
}}
QHeaderView::up-arrow, QHeaderView::down-arrow {{ width: 10px; height: 10px; }}
#GroupList {{
    background: {p.bg};
    border: none;
    border-right: 1px solid {p.border};
}}
#GroupList::item {{ padding: 7px 8px; border-radius: 8px; margin: 1px 6px; }}
#GroupList::item:hover {{ background: {p.hover}; }}
#GroupList::item:selected {{ background: {p.accent_soft}; color: {p.text}; font-weight: 600; }}
QSplitter::handle {{ background: {p.border}; }}
QStatusBar {{ background: {p.bar}; color: {p.muted}; border-top: 1px solid {p.border}; }}
QStatusBar::item {{ border: none; }}

/* ---------- diálogos ---------- */
QGroupBox {{
    border: 1px solid {p.border};
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {p.muted}; }}
QComboBox {{
    background: {p.elevated};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 5px 10px;
}}
QComboBox:focus {{ border: 1px solid {p.accent}; }}
QComboBox QAbstractItemView {{
    background: {p.elevated};
    border: 1px solid {p.border};
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
}}
QProgressBar {{
    background: {p.border};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 4px; }}

/* ---------- barras de desplazamiento ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {p.border if p.dark else _mix(p.faint, p.bg, 0.6)};
    border-radius: 3px;
    min-height: 32px;
    min-width: 32px;
}}
QScrollBar::handle:hover {{ background: {p.faint}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
