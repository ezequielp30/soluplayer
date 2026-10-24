"""Árbol de carpetas a partir de las rutas de la biblioteca (sin dependencias de la interfaz)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .models import Track


@dataclass
class FolderNode:
    path: str
    name: str
    children: dict[str, "FolderNode"] = field(default_factory=dict)
    direct: int = 0  # canciones directamente en esta carpeta
    total: int = 0  # canciones en esta carpeta y sus subcarpetas

    def sorted_children(self) -> list["FolderNode"]:
        return sorted(self.children.values(), key=lambda n: n.name.casefold())


def folder_key(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def display_name(path: str) -> str:
    name = os.path.basename(os.path.normpath(path))
    if not name:  # raíz de una unidad, p. ej. "C:\"
        drive = os.path.splitdrive(path)[0] or path
        return f"Disco {drive}"
    return name


def build_folder_tree(tracks: list[Track]) -> list[FolderNode]:
    """Devuelve las carpetas raíz. Las cadenas de carpetas sin música se compactan:
    C:\\ › Users › Ana › Música (con subcarpetas) se muestra a partir de «Música»."""
    top: dict[str, FolderNode] = {}
    for track in tracks:
        folder = os.path.dirname(os.path.normpath(track.path))
        drive, rest = os.path.splitdrive(folder)
        parts = [p for p in rest.replace("/", os.sep).split(os.sep) if p]
        anchor = drive + os.sep if drive else os.sep
        node = top.setdefault(folder_key(anchor), FolderNode(anchor, display_name(anchor)))
        node.total += 1
        current = anchor
        for part in parts:
            current = os.path.join(current, part)
            node = node.children.setdefault(folder_key(current), FolderNode(current, part))
            node.total += 1
        node.direct += 1

    roots = []
    for node in top.values():
        while node.direct == 0 and len(node.children) == 1:
            node = next(iter(node.children.values()))
        roots.append(node)
    return sorted(roots, key=lambda n: n.path.casefold())


def tracks_in_folder(tracks: list[Track], folder: str, recursive: bool = True) -> list[Track]:
    key = folder_key(folder)
    prefix = key.rstrip(os.sep) + os.sep
    result = []
    for track in tracks:
        track_dir = folder_key(os.path.dirname(track.path))
        if track_dir == key or (recursive and track_dir.startswith(prefix)):
            result.append(track)
    return sorted(result, key=lambda t: (folder_key(os.path.dirname(t.path)), os.path.basename(t.path).casefold()))


def breadcrumb(folder: str, roots: list[FolderNode]) -> list[tuple[str, str]]:
    """[(nombre, ruta)] desde la carpeta raíz mostrada hasta `folder`."""
    key = folder_key(folder)
    for root in roots:
        root_key = folder_key(root.path)
        if key == root_key or key.startswith(root_key.rstrip(os.sep) + os.sep):
            trail = [(display_name(root.path), root.path)]
            node = root
            while folder_key(node.path) != key:
                node = next(
                    (c for k, c in node.children.items() if key == k or key.startswith(k.rstrip(os.sep) + os.sep)),
                    None,
                )
                if node is None:
                    break
                trail.append((node.name, node.path))
            return trail
    return [(display_name(folder), folder)]
