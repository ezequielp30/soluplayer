"""Trabajadores (en su propio hilo) de «Buscar datos en internet». No tocan la biblioteca ni la interfaz."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from .artwork import make_thumbnail
from .models import Track
from .online_lookup import SOURCES, Candidate, LookupResult, Query, download, lookup

# (canción, propuesta elegida, carátula ya reducida o None)
Update = tuple[Track, Candidate, bytes | None]


class LookupWorker(QObject):
    progress = Signal(int, int, str)
    found = Signal(int, object)  # índice de fila, LookupResult
    finished = Signal(bool)  # cancelado

    def __init__(self, queries: list[Query], sources: list[str]) -> None:
        super().__init__()
        self._queries = queries
        self._sources = sources
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        total = len(self._queries)
        sources = list(self._sources)
        strikes: dict[str, int] = {}
        for index, query in enumerate(self._queries):
            if self._cancelled:
                break
            self.progress.emit(index, total, query.title)
            try:
                result = lookup(query, sources)
            except Exception as exc:  # nunca dejar el hilo colgado
                result = LookupResult(errors=[f"Error inesperado: {exc}"])
            # Una base que falla 2 veces seguidas (caída o muy lenta) se deja de lado en esta
            # búsqueda, para no esperar su tiempo límite en cada canción.
            for key in list(sources):
                strikes[key] = strikes.get(key, 0) + 1 if key in result.failed_sources else 0
                if strikes[key] >= 2 and len(sources) > 1:
                    sources.remove(key)
                    result.errors.append(
                        f"{SOURCES[key].name} no responde: se omite en el resto de esta búsqueda."
                    )
            self.found.emit(index, result)
        self.progress.emit(total, total, "")
        self.finished.emit(self._cancelled)


class CoverWorker(QObject):
    """Descarga y reduce las carátulas de las propuestas elegidas."""

    progress = Signal(int, int)
    finished = Signal(object)  # list[Update]

    def __init__(self, chosen: list[tuple[Track, Candidate]], with_covers: bool) -> None:
        super().__init__()
        self._chosen = chosen
        self._with_covers = with_covers
        self._cancelled = False

    def cancel(self) -> None:
        """Deja de descargar carátulas; los datos elegidos se guardan igual (sin la carátula)."""
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        updates: list[Update] = []
        for index, (track, candidate) in enumerate(self._chosen):
            self.progress.emit(index, len(self._chosen))
            cover = None
            if self._with_covers and candidate.cover_url and not self._cancelled:
                try:
                    data = download(candidate.cover_url)
                    cover = make_thumbnail(data) if data else None
                except Exception:  # una carátula que falla no impide guardar los datos
                    cover = None
            updates.append((track, candidate, cover))
        self.finished.emit(updates)
