"""Trabajos en segundo plano del organizador de MP3. No tocan la biblioteca ni la interfaz."""

from __future__ import annotations

import logging
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import islice
from typing import Callable

import mutagen
from PySide6.QtCore import QObject, Signal, Slot

from . import acoustid_lookup, fingerprint, normalizer, organizer, pending_review
from .metadata import MetadataError, read_metadata
from .organizer_db import FileRow, OrganizerDb, cache_key
from .title_format import clean_song_title, known_singers, main_artist, propose
from .utils import path_key

log = logging.getLogger(__name__)

BATCH_SIZE = 50  # lo que se pierde como mucho si se corta la luz: se retoma desde ahí
_MAX_PROCESSES = 4
CACHE_MAX_AGE_S = 30 * 24 * 3600  # una canción sin coincidencia puede tenerla más adelante
_SAVE_EVERY = 20
_SONG_ERRORS = (OSError, sqlite3.Error, mutagen.MutagenError)


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


@dataclass
class IdentifyResult:
    total: int = 0
    automatic: int = 0
    review: int = 0
    offline: int = 0
    from_cache: int = 0
    cancelled: bool = False
    invalid_key: bool = False
    problem: str = ""


class IdentifyWorker(QObject):
    """Consulta AcoustID por lo ya analizado y decide. No modifica la música. Si se corta internet o se detiene, se
    conserva lo hecho y se puede retomar: un fallo del servicio nunca marca una canción como dudosa."""

    progress = Signal(int, int, str)
    finished = Signal(object)  # IdentifyResult

    def __init__(self, key: str, confidence: organizer.Confidence, db_path=None, lookup: Callable = acoustid_lookup.lookup_raw) -> None:
        super().__init__()
        self._key = key
        self._confidence = confidence
        self._db_path = db_path
        self._lookup = lookup
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        result = IdentifyResult()
        try:
            db = OrganizerDb(self._db_path)
            try:
                self._identify(db, result)
            finally:
                db.close()
        except Exception as exc:  # nunca dejar el hilo colgado: «terminado» se avisa siempre
            log.exception("Error inesperado al identificar")
            result.problem = str(exc)
        result.cancelled = self._cancelled
        self.finished.emit(result)

    def _identify(self, db: OrganizerDb, result: IdentifyResult) -> None:
        pending = db.pending_identification()
        result.total = len(pending)
        if not self._key:
            self._propose_offline(db, pending, result)
            return
        batch: list[tuple[int, organizer.Identification]] = []
        try:
            for index, row in enumerate(pending):
                if self._cancelled:
                    return
                saved = db.fingerprint(row.id)
                if saved is None:
                    continue
                item = self._identify_one(db, row, *saved, result)
                batch.append((row.id, item))
                db.update_pending_review(row.id, item.reason, item.candidates)
                if item.decision == organizer.DECISION_AUTO:
                    result.automatic += 1
                else:
                    result.review += 1
                if len(batch) >= _SAVE_EVERY:
                    db.save_identifications(batch)
                    batch.clear()
                self.progress.emit(index + 1, result.total, os.path.basename(row.path))
        except acoustid_lookup.InvalidKey:
            result.invalid_key = True
        except acoustid_lookup.ServiceError as exc:
            result.problem = str(exc)
        finally:
            db.save_identifications(batch)

    def _propose_offline(self, db: OrganizerDb, pending: list[FileRow], result: IdentifyResult) -> None:
        """Sin clave: una propuesta por el título, para revisarla a mano. Nunca se procesa sola."""
        read = []
        for index, row in enumerate(pending):
            if self._cancelled:
                break
            try:
                meta = read_metadata(row.path)
            except (MetadataError, OSError):
                continue
            read.append((row, meta.title, meta.artist))
            if index % 50 == 0:
                self.progress.emit(index, len(pending) * 2, os.path.basename(row.path))
        singers = known_singers((title, artist) for _, title, artist in read)
        batch = []
        for row, title, artist in read:
            proposal = propose(title, artist, singers, row.path)
            batch.append((row.id, organizer.Identification(
                organizer.DECISION_OFFLINE, "Sin huella: propuesta por el título actual.", 0.0,
                clean_song_title(proposal.song), main_artist(proposal.singer),
            )))
        db.save_identifications(batch)
        result.offline = len(batch)

    def _identify_one(self, db: OrganizerDb, row: FileRow, duration: float, value: str, result: IdentifyResult) -> organizer.Identification:
        request_key = cache_key(duration, value)
        raw = db.cached("acoustid", request_key, CACHE_MAX_AGE_S)
        if raw is None:
            raw = self._lookup(self._key, duration, value)
            matches = acoustid_lookup.parse(raw)  # si es rara, no se guarda
            db.store_cached("acoustid", request_key, raw)
        else:
            result.from_cache += 1
            matches = acoustid_lookup.parse(raw)
        return organizer.identify(matches, duration, _current_names(row.path), self._confidence)


def _current_names(path: str) -> list[str]:
    names = [os.path.splitext(os.path.basename(path))[0]]
    try:
        meta = read_metadata(path)
        if meta.has_title_tag:
            names.append(meta.title)
    except (MetadataError, OSError):
        pass
    return names


@dataclass
class NormalizeResult:
    done: int = 0
    skipped: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)  # (ruta, motivo)
    cancelled: bool = False
    operation_id: int = 0


class NormalizeWorker(QObject):
    """Normaliza canción por canción. Detenerlo termina la que está en curso y sale: ninguna queda a medias. Una que
    falla se anota y no detiene a las demás. La biblioteca la actualiza el hilo principal con `applied`."""

    progress = Signal(int, int, str)
    applied = Signal(object)  # OperationItem
    finished = Signal(object)  # NormalizeResult

    def __init__(self, jobs: list, backup_folder: str | None = None, db_path=None) -> None:
        super().__init__()
        self._jobs = jobs
        self._backup_folder = backup_folder
        self._db_path = db_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        result = NormalizeResult()
        try:
            db = OrganizerDb(self._db_path)
            try:
                result.operation_id = db.begin_operation()
                self._normalize(db, result)
                db.finish_operation(result.operation_id)
            finally:
                db.close()
        except Exception as exc:  # nunca dejar el hilo colgado: «terminado» se avisa siempre
            log.exception("Error inesperado al normalizar")
            result.failed.append(("", str(exc)))
        result.cancelled = self._cancelled
        self.finished.emit(result)

    def _normalize(self, db: OrganizerDb, result: NormalizeResult) -> None:
        total = len(self._jobs)
        for index, job in enumerate(self._jobs):
            if self._cancelled:
                return
            row = db.file_by_id(job.file_id)
            path = row.path if row else ""
            self.progress.emit(index, total, os.path.basename(path))
            try:
                item = normalizer.normalize(db, result.operation_id, job, self._backup_folder)
            except normalizer.NormalizeError as exc:
                log.warning("No se normalizó %s: %s", path, exc)
                result.failed.append((path, str(exc)))
                continue
            except _SONG_ERRORS as exc:  # el problema es de esta canción: las demás siguen
                log.exception("Error al normalizar %s", path)
                result.failed.append((path, str(exc)))
                continue
            if item is None:
                result.skipped += 1
            else:
                result.done += 1
                self.applied.emit(item)
        self.progress.emit(total, total, "")


class RestoreWorker(QObject):
    """Devuelve las canciones a como estaban. La biblioteca la actualiza el hilo principal con `restored`."""

    progress = Signal(int, int, str)
    restored = Signal(object)  # OperationItem
    finished = Signal(list)  # (ruta, motivo) de las que no se pudieron restaurar

    def __init__(self, items: list, db_path=None) -> None:
        super().__init__()
        self._items = items
        self._db_path = db_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        problems: list[tuple[str, str]] = []
        try:
            db = OrganizerDb(self._db_path)
            try:
                for index, item in enumerate(self._items):
                    if self._cancelled:
                        break
                    self.progress.emit(index, len(self._items), os.path.basename(item.old_path))
                    try:
                        self.restored.emit(normalizer.restore(db, item))
                    except (normalizer.NormalizeError, *_SONG_ERRORS) as exc:
                        problems.append((item.old_path, str(exc)))
            finally:
                db.close()
        except Exception as exc:  # nunca dejar el hilo colgado
            log.exception("Error inesperado al restaurar")
            problems.append(("", str(exc)))
        self.finished.emit(problems)


@dataclass
class PendingResult:
    moved: int = 0
    returned: int = 0
    normalized: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)  # (ruta, motivo)
    cancelled: bool = False


class MoveToPendingWorker(QObject):
    """Lleva a PENDIENTES_REVISION las que quedaron para revisar, sin cambiar sus nombres ni sus etiquetas. Las
    dañadas no se mueven: no se trata de identificarlas. La biblioteca la actualiza el hilo principal con `moved`."""

    progress = Signal(int, int, str)
    moved = Signal(object)  # PendingSong
    finished = Signal(object)  # PendingResult

    def __init__(self, roots: list[str], file_ids: list[int] | None = None, db_path=None) -> None:
        super().__init__()
        self._roots = roots
        self._file_ids = file_ids
        self._db_path = db_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        result = PendingResult()
        try:
            db = OrganizerDb(self._db_path)
            try:
                self._move(db, result)
            finally:
                db.close()
        except Exception as exc:  # nunca dejar el hilo colgado
            log.exception("Error inesperado al mover a pendientes")
            result.failed.append(("", str(exc)))
        result.cancelled = self._cancelled
        self.finished.emit(result)

    def _move(self, db: OrganizerDb, result: PendingResult) -> None:
        rows = [(f, i) for f, i in db.identifications(self._file_ids) if i.decision == organizer.DECISION_REVIEW and db.open_pending(f) is None]
        for index, (file_id, item) in enumerate(rows):
            if self._cancelled:
                return
            row = db.file_by_id(file_id)
            self.progress.emit(index, len(rows), os.path.basename(row.path))
            try:
                self.moved.emit(pending_review.move_to_pending(db, file_id, pending_review.root_of(row.path, self._roots), item))
                result.moved += 1
            except (pending_review.PendingError, *_SONG_ERRORS) as exc:
                result.failed.append((row.path, str(exc)))
        self.progress.emit(len(rows), len(rows), "")


class ResolvePendingWorker(QObject):
    """Las pendientes ya identificadas: las devuelve a su ubicación original y las normaliza allí. Con `jobs`, también
    las que la persona corrigió a mano. Si no se puede normalizar, queda en su lugar como estaba, y se avisa."""

    progress = Signal(int, int, str)
    returned = Signal(object)  # PendingSong
    applied = Signal(object)  # OperationItem
    finished = Signal(object)  # PendingResult

    def __init__(self, jobs: list | None = None, backup_folder: str | None = None, db_path=None) -> None:
        super().__init__()
        self._jobs = jobs
        self._backup_folder = backup_folder
        self._db_path = db_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        result = PendingResult()
        try:
            db = OrganizerDb(self._db_path)
            try:
                self._resolve(db, result)
            finally:
                db.close()
        except Exception as exc:  # nunca dejar el hilo colgado
            log.exception("Error inesperado al devolver pendientes")
            result.failed.append(("", str(exc)))
        result.cancelled = self._cancelled
        self.finished.emit(result)

    def _resolve(self, db: OrganizerDb, result: PendingResult) -> None:
        waiting = {p.file_id: p for p in db.pending_songs()}
        jobs = self._jobs if self._jobs is not None else normalizer.jobs_from_identifications(db)
        jobs = [j for j in jobs if j.file_id in waiting]
        operation = db.begin_operation() if jobs else 0
        for index, job in enumerate(jobs):
            if self._cancelled:
                break
            pending = waiting[job.file_id]
            self.progress.emit(index, len(jobs), os.path.basename(pending.pending_path))
            try:
                self.returned.emit(pending_review.return_to_origin(db, pending))
                result.returned += 1
            except (pending_review.PendingError, *_SONG_ERRORS) as exc:
                result.failed.append((pending.pending_path, str(exc)))
                continue
            try:
                item = normalizer.normalize(db, operation, job, self._backup_folder)
            except (normalizer.NormalizeError, *_SONG_ERRORS) as exc:
                result.failed.append((pending.original_path, str(exc)))
                continue
            if item is not None:
                result.normalized += 1
                self.applied.emit(item)
        if operation:
            db.finish_operation(operation)
        self.progress.emit(len(jobs), len(jobs), "")
