"""Trabajos en segundo plano del organizador de MP3. No tocan la biblioteca ni la interfaz."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import islice
from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot

from . import fingerprint, organizer
from .organizer_db import FileRow, OrganizerDb
from .utils import path_key

log = logging.getLogger(__name__)

BATCH_SIZE = 50  # lo que se pierde como mucho si se corta la luz: se retoma desde ahí
_MAX_PROCESSES = 4


@dataclass
class AnalysisResult:
    found: int = 0
    computed: int = 0
    damaged: int = 0
    reused: int = 0
    cancelled: bool = False
    problems: list[str] = field(default_factory=list)


class AnalyzeWorker(QObject):
    """Recorre las carpetas y calcula las huellas que falten. Solo lee los archivos de música. Lo ya analizado no se
    repite mientras el archivo no cambie, así que detenerlo o cortarse no pierde trabajo."""

    progress = Signal(int, int, str)
    finished = Signal(object)  # AnalysisResult

    def __init__(self, roots: list[str], db_path=None, compute: Callable = fingerprint.compute) -> None:
        super().__init__()
        self._roots = roots
        self._db_path = db_path
        self._compute = compute
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        result = AnalysisResult()
        try:
            db = OrganizerDb(self._db_path)
            try:
                self._analyze(db, result)
            finally:
                db.close()
        except fingerprint.ToolMissing as exc:
            result.problems.append(str(exc))
        except Exception as exc:  # nunca dejar el hilo colgado: «terminado» se avisa siempre
            log.exception("Error inesperado al analizar")
            result.problems.append(str(exc))
        result.cancelled = self._cancelled
        self.finished.emit(result)

    def _analyze(self, db: OrganizerDb, result: AnalysisResult) -> None:
        def problem(path: str, exc: OSError) -> None:
            result.problems.append(f"{path}: {exc.strerror or exc}")

        files = organizer.collect_mp3(self._roots, lambda: self._cancelled, problem)
        chosen: set[str] = set()
        while batch := list(islice(files, 500)):
            result.found += len(batch)
            chosen.update(path_key(entry[0]) for entry in batch)
            db.register(batch)
            self.progress.emit(0, 0, f"Se encontraron {result.found} canciones…")
        if self._cancelled:
            return
        # Solo lo elegido esta vez: en la base puede haber pendientes de otras carpetas o de archivos que ya no están.
        pending = [row for row in db.pending_analysis() if path_key(row.path) in chosen]
        result.reused = max(0, result.found - len(pending))
        total = len(pending)
        with ThreadPoolExecutor(max_workers=min(_MAX_PROCESSES, os.cpu_count() or 1)) as pool:
            for start in range(0, total, BATCH_SIZE):
                if self._cancelled:
                    return
                self._analyze_batch(db, pool, pending[start:start + BATCH_SIZE], result)
                done = min(start + BATCH_SIZE, total)
                self.progress.emit(done, total, os.path.basename(pending[done - 1].path))

    def _analyze_batch(self, db: OrganizerDb, pool: ThreadPoolExecutor, batch: list[FileRow], result: AnalysisResult) -> None:
        fingerprints, damaged = [], []
        for row, outcome in zip(batch, pool.map(self._try_compute, batch)):
            if isinstance(outcome, fingerprint.ToolMissing):
                raise outcome
            if isinstance(outcome, fingerprint.DamagedFile):
                damaged.append((row.id, str(outcome)))
            else:
                fingerprints.append((row.id, outcome.duration_s, outcome.value))
        db.save_results(fingerprints, damaged)
        result.computed += len(fingerprints)
        result.damaged += len(damaged)

    def _try_compute(self, row: FileRow):
        try:
            return self._compute(row.path)
        except (fingerprint.DamagedFile, fingerprint.ToolMissing) as exc:
            return exc

