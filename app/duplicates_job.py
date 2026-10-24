"""Búsqueda de canciones repetidas en su propio hilo (comparar contenido y leer la calidad lleva tiempo)."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from .duplicates import find_duplicates
from .metadata import Quality, audio_quality
from .models import Track

log = logging.getLogger(__name__)


class FindDuplicatesWorker(QObject):
    progress = Signal(int, int, str)
    # (grupos o None si se canceló, calidad por id de canción, error)
    finished = Signal(object, object, str)

    def __init__(self, tracks: list[Track], mode: str) -> None:
        super().__init__()
        self._tracks = tracks
        self._mode = mode
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _report(self, done: int, total: int) -> bool:
        self.progress.emit(done, total, "")
        return not self._cancelled

    @Slot()
    def run(self) -> None:
        try:
            groups = find_duplicates(self._tracks, self._mode, self._report)
            qualities: dict[int, Quality | None] = {}
            if groups:
                copies = [t for g in groups for t in g.tracks]
                for index, track in enumerate(copies):
                    if self._cancelled:
                        groups = None
                        break
                    self.progress.emit(index, len(copies), "")
                    qualities[track.id] = audio_quality(track.path) if track.available else None
            self.finished.emit(groups, qualities, "")
        except Exception as exc:  # nunca dejar el hilo colgado
            log.exception("Error al buscar canciones repetidas")
            self.finished.emit(None, {}, str(exc))
