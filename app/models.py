"""Objetos de datos compartidos entre módulos."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace


@dataclass
class Track:
    id: int
    path: str
    title: str
    artist: str
    album: str
    genre: str
    duration_ms: int
    added_at: str
    last_played_at: str | None = None
    cover_hash: str | None = None
    loudness_lufs: float | None = None  # sonoridad medida (EBU R128)
    true_peak_db: float | None = None  # pico real (dBTP)
    norm_gain_db: float = 0.0  # dB ya escritos en el MP3 por «Ajustar volumen» (0 = sin ajuste; para revertir)
    # Id de la fila en playlist_tracks cuando la canción se muestra dentro de
    # una playlist (permite quitar una repetición concreta).
    entry_id: int | None = None
    available: bool = True

    def check_available(self) -> bool:
        self.available = os.path.isfile(self.path)
        return self.available

    def copy(self, **changes) -> "Track":
        return replace(self, **changes)


def unreachable_root(path: str) -> str | None:
    """La raíz de la ruta (la letra del disco o el recurso de red) en minúsculas si no responde (disco desconectado,
    servidor apagado). Sirve para no consultar canción por canción un disco caído: en red cada consulta
    puede esperar varios segundos y la ventana quedaría «No responde»."""
    root = os.path.splitdrive(path)[0]
    return root.casefold() if root and not os.path.exists(root + "\\") else None


@dataclass
class Playlist:
    id: int
    name: str
    track_count: int = 0
