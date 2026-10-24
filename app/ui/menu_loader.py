"""Menús de la ventana principal leídos de un archivo de Qt Designer (assets/menus.ui).

Así los menús se editan de forma gráfica con Qt Designer: agregar separadores, mover opciones entre menús,
cambiar textos, atajos o el orden, crear submenús. El código solo conecta cada opción (por su nombre de
objeto, p. ej. «act_history») con lo que hace.

Se lee el XML directamente (sin QtUiTools) para no agrandar el programa instalado. Reglas de seguridad:
- Si el archivo editado tiene un error, se usa la copia original (menus.original.ui) y se avisa; si
  también falla, se arma un menú básico con todas las opciones para que el programa arranque igual.
- Una opción nueva que todavía no tiene función en el código aparece desactivada, con una explicación.
- Si se borra una opción del archivo, el programa sigue funcionando (esa opción simplemente no aparece).
- Un atajo repetido, o uno que el programa ya usa en sus listas (Supr, F2, Enter, Esc), no se asigna:
  si se asignara, Qt no sabría a cuál obedecer y no funcionaría ninguno. Se avisa cuál fue.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMenu, QMenuBar

from ..config import resource_path

log = logging.getLogger(__name__)

MENUS_FILE = resource_path("assets", "menus.ui")
ORIGINAL_FILE = resource_path("assets", "menus.original.ui")

# Teclas que ya usan la tabla de canciones y las listas de la barra lateral (quitar, renombrar,
# reproducir, cancelar). Asignarlas a un menú las dejaría sin efecto en todas partes.
RESERVED_SHORTCUTS = {QKeySequence(k).toString() for k in ("Del", "F2", "Return", "Enter", "Esc", "Backspace")}


class MenuFileError(Exception):
    """El archivo de menús no se pudo leer. El mensaje es apto para el usuario."""


@dataclass
class ActionSpec:
    name: str
    text: str = ""
    shortcut: str = ""
    checkable: bool = False
    tooltip: str = ""
    visible: bool = True
    enabled: bool = True


@dataclass
class MenuSpec:
    name: str
    title: str
    # ("action", nombre) | ("separator", "") | ("menu", MenuSpec)
    items: list[tuple[str, object]] = field(default_factory=list)


@dataclass
class MenusSpec:
    # Contenido de la barra en orden: ("menu", MenuSpec) | ("action", nombre) (opción suelta en la barra)
    items: list[tuple[str, object]]
    actions: dict[str, ActionSpec]
    warnings: list[str] = field(default_factory=list)

    @property
    def menus(self) -> list[MenuSpec]:
        return [value for kind, value in self.items if kind == "menu"]


def _prop(element: ET.Element, name: str) -> ET.Element | None:
    for prop in element.findall("property"):
        if prop.get("name") == name and len(prop):
            return prop[0]
    return None


def _text(element: ET.Element, name: str) -> str:
    value = _prop(element, name)
    return (value.text or "") if value is not None and value.tag == "string" else ""


def _bool(element: ET.Element, name: str, default: bool) -> bool:
    value = _prop(element, name)
    if value is None or value.tag != "bool":
        return default
    return (value.text or "").strip().lower() == "true"


def parse(path: Path | str) -> MenusSpec:
    path = Path(path)
    try:
        root = ET.parse(path).getroot()
    except FileNotFoundError as exc:
        raise MenuFileError(f"No se encuentra el archivo de menús «{path.name}».") from exc
    except ET.ParseError as exc:
        raise MenuFileError(f"El archivo de menús «{path.name}» está dañado ({exc}).") from exc
    except OSError as exc:  # sin permiso, una carpeta con ese nombre, disco con errores…
        raise MenuFileError(f"No se pudo leer el archivo de menús «{path.name}» ({exc.strerror or exc}).") from exc
    menubar = next((w for w in root.iter("widget") if w.get("class") == "QMenuBar"), None)
    if menubar is None:
        raise MenuFileError(f"El archivo «{path.name}» no tiene barra de menús (QMenuBar).")

    warnings: list[str] = []
    actions: dict[str, ActionSpec] = {}
    for element in root.iter("action"):
        name = element.get("name", "")
        text = _text(element, "text")
        if not text:
            warnings.append(f"La opción «{name}» no tiene texto: se muestra con su nombre interno.")
        actions[name] = ActionSpec(
            name=name,
            text=text,
            shortcut=_text(element, "shortcut"),
            checkable=_bool(element, "checkable", False),
            tooltip=_text(element, "toolTip") or _text(element, "statusTip"),
            visible=_bool(element, "visible", True),
            enabled=_bool(element, "enabled", True),
        )

    def read_menu(element: ET.Element, depth: int = 0) -> MenuSpec:
        submenus = {w.get("name"): w for w in element.findall("widget") if w.get("class") == "QMenu"}
        spec = MenuSpec(element.get("name", ""), _text(element, "title") or element.get("name", ""))
        for add in element.findall("addaction"):
            name = add.get("name", "")
            if name == "separator":
                spec.items.append(("separator", ""))
            elif name in submenus and depth < 8:
                spec.items.append(("menu", read_menu(submenus[name], depth + 1)))
            elif name in actions:
                spec.items.append(("action", name))
            else:
                log.warning("Menú «%s»: la opción «%s» no está definida; se omite", spec.title, name)
        return spec

    top = {w.get("name"): w for w in menubar.findall("widget") if w.get("class") == "QMenu"}
    items: list[tuple[str, object]] = []
    for add in menubar.findall("addaction"):
        name = add.get("name", "")
        if name in top:
            items.append(("menu", read_menu(top[name])))
        elif name in actions:
            items.append(("action", name))  # opción puesta directamente en la barra
    if not items:
        raise MenuFileError(f"La barra de menús de «{path.name}» está vacía.")
    return MenusSpec(items, actions, warnings)


def basic_spec(handlers: dict[str, Callable[[], None] | None]) -> MenusSpec:
    """Último recurso si ni el archivo editado ni el original se pueden leer: un único menú con todas
    las opciones, para que el programa arranque y se pueda usar."""
    names = list(handlers)
    actions = {n: ActionSpec(n, text=n.removeprefix("act_").replace("_", " ").capitalize()) for n in names}
    return MenusSpec([("menu", MenuSpec("menu_basico", "&Menú", [("action", n) for n in names]))], actions)


def load(path: Path = MENUS_FILE, original: Path = ORIGINAL_FILE) -> tuple[MenusSpec | None, str]:
    """Devuelve (menús, aviso). Si el archivo editado falla, usa la copia original y explica por qué.
    Si también falla la original, devuelve (None, aviso): hay que usar basic_spec()."""
    try:
        return parse(path), ""
    except MenuFileError as exc:
        log.error("%s Se usan los menús originales.", exc)
        first = str(exc)
    try:
        return parse(original), f"{first} Se usan los menús originales."
    except MenuFileError as exc:
        log.error("Tampoco se pudo leer la copia original: %s", exc)
        return None, f"{first} Tampoco se pudo leer la copia original ({exc}); se muestra un menú básico."


def build(
    window: QMainWindow,
    bar: QMenuBar,
    spec: MenusSpec,
    handlers: dict[str, Callable[[], None] | None],
) -> tuple[dict[str, QAction], dict[str, QMenu]]:
    """Crea los menús en `bar`. `handlers` asocia el nombre de cada opción con lo que hace (None = la
    opción se conecta aparte, p. ej. una casilla). Devuelve las opciones y los menús por nombre.
    Los avisos (atajos repetidos o reservados…) quedan en spec.warnings."""
    actions: dict[str, QAction] = {}
    menus: dict[str, QMenu] = {}
    used_shortcuts: dict[str, str] = {}

    def make_action(name: str) -> QAction:
        info = spec.actions[name]
        action = QAction(info.text or name, window)
        action.setObjectName(name)
        if info.shortcut:
            key = QKeySequence(info.shortcut).toString()
            label = (info.text or name).replace("&", "")
            if key in RESERVED_SHORTCUTS:
                spec.warnings.append(f"El atajo «{key}» de «{label}» ya lo usa el programa en sus listas: no se asignó.")
            elif key in used_shortcuts:
                spec.warnings.append(f"El atajo «{key}» está repetido («{used_shortcuts[key]}» y «{label}»): se dejó solo en la primera.")
            elif key:
                used_shortcuts[key] = label
                action.setShortcut(QKeySequence(info.shortcut))
        action.setCheckable(info.checkable)
        if info.tooltip:
            action.setToolTip(info.tooltip)
            action.setStatusTip(info.tooltip)
        if name in handlers:
            slot = handlers[name]
            if slot is not None:
                action.triggered.connect(lambda _checked=False, s=slot: s())
            action.setEnabled(info.enabled)
        else:
            # Opción agregada en Qt Designer que todavía no tiene función en el programa.
            action.setEnabled(False)
            action.setStatusTip("Esta opción todavía no tiene una función asignada en el programa.")
            log.info("Opción de menú sin función asignada: %s", name)
        action.setVisible(info.visible)
        window.addAction(action)  # los atajos funcionan aunque el menú esté cerrado
        return action

    def get_action(name: str) -> QAction:
        if name not in actions:  # la misma opción en dos lugares: un solo objeto
            actions[name] = make_action(name)
        return actions[name]

    def fill(menu: QMenu, menu_spec: MenuSpec) -> None:
        menu.setObjectName(menu_spec.name)
        menus[menu_spec.name] = menu
        for kind, value in menu_spec.items:
            if kind == "separator":
                menu.addSeparator()
            elif kind == "menu":
                fill(menu.addMenu(value.title), value)
            else:
                menu.addAction(get_action(value))

    for kind, value in spec.items:
        if kind == "menu":
            fill(bar.addMenu(value.title), value)
        else:
            bar.addAction(get_action(value))
    missing = sorted(set(handlers) - set(actions))
    if missing:
        log.info("Opciones que no aparecen en el archivo de menús (no se mostrarán): %s", ", ".join(missing))
    return actions, menus
