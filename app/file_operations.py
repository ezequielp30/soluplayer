"""Coordinador de las operaciones que modifican archivos del usuario (sin ventanas).

Reúne en un solo sitio lo que antes estaba repartido entre la ventana principal y los diálogos, y
garantiza siempre el mismo orden:

    respaldo de la biblioteca → soltar el archivo si está sonando → operar → actualizar la biblioteca → avisar

Las ventanas solo piden confirmación y muestran el resultado. También arma el «Historial de cambios en
archivos»: reuniones de repetidas, conversiones a MP3 y ajustes de volumen, con su forma de deshacerlos.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from . import backup, converter, file_history, file_manager, journal, mp3gain, review_folder
from .database import Database
from .duplicates import DuplicateGroup
from .file_ops import move_to_trash
from .models import Track
from .utils import long_path, path_key, plural

log = logging.getLogger(__name__)

KIND_REVIEW = "reunion"
KIND_CONVERSION = "conversion"
KIND_VOLUME = "volumen"
KIND_FILES = "archivos"  # renombrar y mover (app/file_history.py)

# (id de la copia que se conserva, copias a quitar)
DuplicatesPlan = list[tuple[int, list[Track]]]


@dataclass
class HistoryEntry:
    kind: str
    when: datetime | None
    title: str
    detail: str
    status: str  # texto para el usuario
    can_undo: bool
    count: int = 0
    session: object = None
    location: str = ""  # carpeta relacionada («Abrir carpeta»)


@dataclass
class UndoOutcome:
    restored: int
    problems: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class DuplicatesOutcome:
    removed: int
    trashed: list[str]
    failed: dict[str, str]
    trash: bool

    @property
    def message(self) -> str:
        text = f"Se {'quitó' if self.removed == 1 else 'quitaron'} {plural(self.removed, 'copia', 'copias')} de la biblioteca"
        if self.trash:
            n = len(self.trashed)
            text += f" y {plural(n, 'archivo')} {'se envió' if n == 1 else 'se enviaron'} a la Papelera."
        else:
            text += "."
        if self.failed:
            text += (
                f" {plural(len(self.failed), 'archivo')} no se pudo enviar a la Papelera y se dejó en la biblioteca: "
                + "; ".join(f"{os.path.basename(p)} ({r})" for p, r in self.failed.items())
            )
        return text


@dataclass
class SetAsideOutcome:
    folder: str
    moved: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def library_root(library: list[Track]) -> str:
    """La carpeta principal de la música: la más profunda que contiene a la MAYORÍA de las canciones (una
    suelta en Descargas no la lleva a la raíz del disco). Nunca la raíz de un disco o de un recurso de red,
    ni Windows o Archivos de programa: en ese caso «» (no hay una carpeta principal clara)."""
    folders = [long_path(os.path.dirname(t.path)) for t in library if t.available]
    if not folders:
        return ""
    counts: dict[str, int] = {}
    shown: dict[str, str] = {}
    for folder in folders:
        current = folder.rstrip("\\/")
        while True:
            key = os.path.normcase(current)
            counts[key] = counts.get(key, 0) + 1
            shown.setdefault(key, current)
            parent = os.path.dirname(current)
            if parent == current or not parent:
                break
            current = parent
    majority = [k for k, n in counts.items() if n * 2 > len(folders)]
    if not majority:
        return ""
    best = shown[max(majority, key=len)]  # la más profunda
    drive, rest = os.path.splitdrive(best)
    system = [os.environ.get(v, "") for v in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)")]
    if rest.strip("\\/") == "" or any(s and os.path.normcase(best).startswith(os.path.normcase(s)) for s in system):
        return ""
    return best


@dataclass
class GatherOutcome:
    session: review_folder.Session
    problems: list[review_folder.Skipped]
    error: str = ""  # no se pudo actualizar la biblioteca: se devolvió todo


def _when(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


class FileOperations:
    def __init__(
        self,
        db: Database,
        release_files: Callable[[set[int]], None],
        forget_tracks: Callable[[set[int]], None],
        on_changed: Callable[[], None],
        confirm_without_backup: Callable[[], bool],
    ) -> None:
        """`release_files`: el reproductor suelta esas canciones si están sonando.
        `forget_tracks`: el reproductor las quita de su cola (se van de la biblioteca).
        `on_changed`: recargar la biblioteca y refrescar la ventana.
        `confirm_without_backup`: preguntar si seguir cuando el respaldo previo falla."""
        self.db = db
        self._release = release_files
        self._forget = forget_tracks
        self._on_changed = on_changed
        self._confirm_without_backup = confirm_without_backup

    # ------------------------------------------------------------------ comunes

    def _prepare(self, reason: str, track_ids: set[int]) -> bool:
        """Respaldo y soltar los archivos. False si el usuario prefiere no seguir sin respaldo."""
        if backup.create_backup(self.db.conn, reason) is None and not self._confirm_without_backup():
            log.info("Operación cancelada: no se pudo crear el respaldo «%s»", reason)
            return False
        self._release(track_ids)
        return True

    def changed(self) -> None:
        self._on_changed()

    # ------------------------------------------------------------------ repetidas

    def remove_duplicates(self, plan: DuplicatesPlan, trash: bool, library: list[Track]) -> DuplicatesOutcome | None:
        """Quita copias repetidas de la biblioteca (y opcionalmente envía sus archivos a la Papelera)."""
        remove_ids = {t.id for _, tracks in plan for t in tracks}
        if not self._prepare("antes-de-repetidas", set()):
            return None
        # Si alguna copia está sonando, se descarga del reproductor para que Windows libere el archivo.
        self._forget(remove_ids)
        failed: dict[str, str] = {}
        trashed: list[str] = []
        if trash:
            by_id = {t.id: t for t in library}
            existing = []
            for keep_id, tracks in plan:
                keep = by_id.get(keep_id)
                if keep is None or not os.path.exists(keep.path):
                    # La copia «conservada» no está en el disco: enviar las demás dejaría la canción
                    # sin ningún archivo. No se envía nada de este grupo.
                    for track in tracks:
                        if os.path.exists(track.path):
                            failed[track.path] = (
                                "La copia que conservas no se encuentra en el disco: no se envió para no quedarte sin ninguna."
                            )
                    continue
                for track in tracks:
                    if not os.path.exists(track.path):
                        continue
                    # El mismo archivo físico con otra ruta (unidad mapeada, enlace…): enviarlo
                    # a la Papelera borraría también la copia que se conserva.
                    if keep is not None and os.path.exists(keep.path) and os.path.samefile(track.path, keep.path):
                        continue
                    existing.append(track.path)
            trashed, failed_list = move_to_trash(existing)
            failed.update(failed_list)
        groups = [
            (keep_id, [t.id for t in tracks if t.path not in failed])  # si no se pudo enviar, sigue en la biblioteca
            for keep_id, tracks in plan
        ]
        removed = self.db.merge_duplicate_groups(groups)
        self._on_changed()
        return DuplicatesOutcome(removed, trashed, failed, trash)

    def gather(self, session: review_folder.Session, groups: list[DuplicateGroup], skipped, report=None) -> GatherOutcome | None:
        """Mueve las copias de cada canción repetida a la carpeta de revisión (plan ya confirmado)."""
        if not self._prepare("antes-de-reunir-repetidas", {m.track_id for m in session.moves}):
            return None
        session, failed = review_folder.execute(session, groups, report)
        try:
            self.db.update_track_paths([(m.track_id, m.target) for m in session.moves])
        except sqlite3.Error as exc:
            # La biblioteca no se pudo actualizar: se devuelven los archivos para no dejar rutas rotas.
            log.error("No se pudieron guardar las rutas nuevas (%s); se deshace la reunión", exc)
            review_folder.undo(session)
            self._on_changed()
            return GatherOutcome(session, list(skipped) + failed, str(exc))
        self._on_changed()
        return GatherOutcome(session, list(skipped) + failed)

    # ------------------------------------------------------------------ conversión a MP3

    def begin_conversion(self, session: converter.ConversionSession) -> bool:
        if not self._prepare("antes-de-convertir-a-mp3", {i.track_id for i in session.items}):
            return False
        session.save()  # el plan queda anotado antes de crear nada
        return True

    def record_converted(self, item: converter.Conversion, session: converter.ConversionSession) -> str:
        """Un MP3 creado y verificado: la biblioteca pasa al MP3 y después el original se guarda aparte.
        Primero la biblioteca: si no acepta la ruta nueva, el original no se toca y el MP3 recién creado
        se quita. Devuelve «» si salió bien, o el motivo del fallo."""
        try:
            # Mismo id: las playlists siguen intactas.
            self.db.update_track_paths([(item.track_id, item.mp3)])
        except sqlite3.Error as exc:
            log.error("La biblioteca no aceptó %s (%s); se quita el MP3 y el original queda igual", item.mp3, exc)
            try:
                os.remove(item.mp3)
            except OSError:
                pass
            return "la biblioteca no pudo usar el MP3; el original quedó como estaba."
        try:
            converter.move_original(item, session)  # anota el destino ANTES de mover
        except OSError as exc:
            log.warning("No se pudo mover el original %s: %s", item.original, exc)
        self.db.save_loudness([(item.track_id, None, None)])  # el volumen del MP3 se medirá de nuevo
        self.db.set_norm_gains([(item.track_id, 0.0)])
        item.done = True
        session.save()
        return ""

    def finish_conversion(self, session: converter.ConversionSession) -> None:
        session.status = converter.STATUS_DONE
        session.save()
        self._on_changed()

    # ------------------------------------------------------------------ volumen

    def begin_volume_adjust(self, track_ids: set[int]) -> bool:
        return self._prepare("antes-de-ajustar-volumen", track_ids)

    def record_volume(self, track: Track, steps: int, total_steps: int) -> None:
        """Un MP3 ajustado. Se guarda en el acto: si algo se detiene a mitad, queda anotado."""
        from .loudness import plausible

        measured = track.loudness_lufs is not None and plausible(track.loudness_lufs, None)
        self.db.save_loudness([(
            track.id,
            # La marca «no se pudo medir» no es un número: no se le suman los pasos (sería una medición falsa).
            track.loudness_lufs + steps * mp3gain.STEP_DB if measured else track.loudness_lufs,
            track.true_peak_db + steps * mp3gain.STEP_DB if track.true_peak_db is not None else None,
        )])
        # El total sale de la anotación del propio archivo (fuente fiable), no de una suma en memoria.
        self.db.set_norm_gains([(track.id, round(total_steps * mp3gain.STEP_DB, 2))])  # con signo

    def save_measurements(self, rows: list[tuple[int, float | None, float | None]]) -> None:
        if rows:
            self.db.save_loudness(rows)

    def recover_volume_from_file(self, track_id: int, annotated_steps: int) -> None:
        """El MP3 dice que ya fue ajustado y la biblioteca no lo recuerda (respaldo restaurado,
        canción reimportada…): se recupera desde el archivo, así se puede revertir."""
        self.db.set_norm_gains([(track_id, round(annotated_steps * mp3gain.STEP_DB, 2))])

    def sync_volume_annotations(self, library: list[Track], playing_id: int | None) -> tuple[int, int]:
        """La biblioteca dice «ajustada» pero el MP3 no tiene la anotación (respaldo viejo restaurado, álbum
        copiado encima…): manda el archivo, así que la biblioteca vuelve a «sin ajuste». Nunca se escribe en
        el MP3 sin que el usuario lo pida: una anotación falsa haría que «Revertir» bajara el volumen de más.
        Todo ajuste del programa escribe su anotación junto con el audio. Devuelve (corregidas, sin leer)."""
        stale: list[tuple[int, float]] = []
        failed = 0
        for track in library:
            if track.norm_gain_db == 0 or not track.path.lower().endswith(".mp3") or not track.available:
                continue
            try:
                if mp3gain.read_applied_steps(track.path) == 0:
                    stale.append((track.id, 0.0))
            except Exception as exc:
                failed += 1
                log.warning("No se pudo leer el ajuste de volumen de %s: %s", track.path, exc)
        if stale:
            # Respaldo antes: si fue un editor de etiquetas el que borró la anotación (el audio sigue
            # ajustado), el dato se puede recuperar desde Herramientas → Respaldos.
            backup.create_backup(self.db.conn, "antes-de-corregir-volumen")
            self.db.set_norm_gains(stale)
        if stale or failed:
            log.info("Ajustes de volumen sin anotación en el MP3: %d corregidos en la biblioteca, %d sin leer", len(stale), failed)
        return len(stale), failed

    # ------------------------------------------------------------------ historial y deshacer

    def history(self, library: list[Track]) -> list[HistoryEntry]:
        """Todas las operaciones sobre archivos, de la más reciente a la más antigua."""
        entries: list[HistoryEntry] = []
        for s in review_folder.list_sessions():
            moved = s.moved()
            undone = s.status == review_folder.STATUS_UNDONE
            # Solo se puede devolver lo que sigue en la carpeta de revisión (si se borró, no hay qué deshacer).
            present = [m for m in moved if os.path.exists(m.target)]
            state = "Deshecha" if undone else ("Interrumpida" if s.status == review_folder.STATUS_RUNNING else "Hecha")
            if not undone and moved and not present:
                state = "Ya no están los archivos"
            entries.append(HistoryEntry(
                KIND_REVIEW, _when(s.created_at), "Reunir repetidas para revisar",
                f"{plural(len(moved) if not undone else len(s.moves), 'archivo')} → {s.destination}",
                state, can_undo=not undone and bool(present), count=len(present), session=s, location=s.destination,
            ))
        for s in converter.list_sessions():
            pending = converter.pending_items(s)
            undone = s.status == converter.STATUS_UNDONE
            # Solo se puede deshacer una conversión cuyo original sigue en algún lado (en su sitio o guardado).
            restorable = [i for i in pending if os.path.exists(i.original) or (i.moved_to and os.path.exists(i.moved_to))]
            state = "Deshecha" if undone else ("Interrumpida" if s.status == converter.STATUS_RUNNING else "Hecha")
            if not undone and pending and not restorable:
                state = "Ya no están los originales"
            entries.append(HistoryEntry(
                KIND_CONVERSION, _when(s.created_at), "Convertir a MP3",
                f"{plural(len(pending) if not undone else len(s.items), 'canción', 'canciones')} · originales en {s.originals_root}",
                state, can_undo=not undone and bool(restorable), count=len(restorable), session=s, location=s.originals_root,
            ))
        for s in file_history.list_sessions():
            pending = s.pending()
            undone = s.status == journal.STATUS_UNDONE
            running = s.status == journal.STATUS_RUNNING  # cortada a mitad: el plan, no lo hecho
            first = s.changes[0] if s.changes else None
            if s.kind == file_history.KIND_MOVE:
                moved = len(pending) if running else len(s.changes)
                detail = f"{plural(moved, 'archivo')} → {os.path.dirname(first.target) if first else ''}"
            else:
                detail = f"{os.path.basename(first.source.rstrip(chr(92) + '/'))} → {os.path.basename(first.target.rstrip(chr(92) + '/'))}" if first else ""
            if undone:
                state = "Deshecha"
            elif running:
                state = "Interrumpida"
            else:
                state = "Hecha" if pending else "Ya no se puede deshacer"
            entries.append(HistoryEntry(
                KIND_FILES, _when(s.created_at), file_history.TITLES.get(s.kind, s.kind), detail, state,
                can_undo=not undone and bool(pending), count=len(pending), session=s,
                location=os.path.dirname(first.target) if first else "",
            ))
        adjusted = [t for t in library if t.norm_gain_db != 0]
        if adjusted:
            entries.append(HistoryEntry(
                KIND_VOLUME, None, "Ajustar volumen (MP3, sin pérdida)",
                f"{plural(len(adjusted), 'canción ajustada', 'canciones ajustadas')} · se revierten desde la ventana de volumen",
                "Vigente", can_undo=True, count=len(adjusted),
            ))
        entries.sort(key=lambda e: (e.when is not None, e.when or datetime.min), reverse=True)
        return entries

    # ------------------------------------------------------------------ gestión de archivos y carpetas

    @staticmethod
    def tracks_in(folder: str, library: list[Track]) -> list[Track]:
        """Canciones de la biblioteca dentro de una carpeta (incluye subcarpetas)."""
        prefix = path_key(folder).rstrip("\\/") + os.sep
        return [t for t in library if path_key(t.path).startswith(prefix)]

    def rename_track_file(self, track: Track, new_name: str) -> str:
        """Renombra el archivo de una canción. Devuelve la ruta nueva (lanza FileManagerError)."""
        if not self._prepare("antes-de-renombrar", {track.id}):
            raise file_manager.FileManagerError("Operación cancelada.")
        new_path = file_manager.rename_file(track.path, new_name)
        try:
            self.db.update_track_paths([(track.id, new_path)])
        except sqlite3.Error as exc:
            os.rename(new_path, track.path)  # la biblioteca no lo aceptó: todo como estaba
            raise file_manager.FileManagerError(f"No se pudo actualizar la biblioteca ({exc}); no se cambió nada.") from exc
        file_history.record(file_history.KIND_RENAME_FILE, [file_history.Change(track.path, new_path, [track.id])])
        self._on_changed()
        return new_path

    def rename_folder(self, folder: str, new_name: str, library: list[Track]) -> str:
        """Renombra una carpeta; las canciones de dentro (y sus playlists) pasan a la ruta nueva."""
        inside = self.tracks_in(folder, library)
        if not self._prepare("antes-de-renombrar-carpeta", {t.id for t in inside}):
            raise file_manager.FileManagerError("Operación cancelada.")
        # Lo que queda de cada ruta dentro de la carpeta, con nombres largos: una canción guardada como
        # «C:\MUSICA~1\…» también está dentro de «C:\Música larga». Se calcula antes, mientras existen.
        base = long_path(folder)
        relative = {t.id: os.path.relpath(long_path(t.path), base) for t in inside}
        new_folder = file_manager.rename_folder(folder, new_name)
        changes = [(t.id, os.path.join(new_folder, relative[t.id])) for t in inside]
        try:
            self.db.update_track_paths(changes)
        except sqlite3.Error as exc:
            os.rename(new_folder, folder)
            raise file_manager.FileManagerError(f"No se pudo actualizar la biblioteca ({exc}); no se cambió nada.") from exc
        file_history.record(file_history.KIND_RENAME_FOLDER, [file_history.Change(folder, new_folder, [t.id for t in inside])])
        self._on_changed()
        return new_folder

    def move_tracks(self, tracks: list[Track], destination: str) -> file_manager.MoveResult:
        """Mueve los archivos de varias canciones a otra carpeta (las playlists se conservan). El plan se anota
        antes de empezar y la biblioteca se actualiza archivo por archivo: si se corta la luz a mitad, al abrir
        reconcile_interrupted_moves() deja cada canción donde quedó su archivo."""
        result = file_manager.MoveResult()
        if not self._prepare("antes-de-mover", {t.id for t in tracks}):
            return result
        by_path = {t.path: t for t in tracks}
        # En el plan solo entra lo que de verdad se puede mover (el archivo está y el destino está libre): si
        # no, tras un corte, otro archivo con el mismo nombre en el destino pasaría por movido.
        session = file_history.begin(file_history.KIND_MOVE, [
            file_history.Change(p, target, [t.id]) for p, t in by_path.items()
            if os.path.isfile(p) and not os.path.exists(target := os.path.join(destination, os.path.basename(p)))
        ])
        for source, track in by_path.items():
            step = file_manager.move_files([source], destination)
            result.failed.extend(step.failed)
            if step.failed and session is not None:
                # No se movió: sale del plan ya, para que un corte después no lo confunda con un archivo
                # que ya estaba en el destino con el mismo nombre.
                session.changes = [c for c in session.changes if c.source != source]
                try:
                    session.save()
                except OSError as exc:
                    log.warning("No se pudo actualizar el plan del movimiento: %s", exc)
            for moved_from, target in step.moved:
                try:
                    self.db.update_track_paths([(track.id, target)])
                except sqlite3.Error as exc:
                    log.error("No se pudo actualizar la biblioteca tras mover %s: %s", moved_from, exc)
                    result.failed.append((moved_from, self._put_back(target, moved_from, exc)))
                    continue
                result.moved.append((moved_from, target))
        done = [file_history.Change(s, d, [by_path[s].id]) for s, d in result.moved]
        if session is not None:
            file_history.finish(session, done)
        else:
            file_history.record(file_history.KIND_MOVE, done)
        self._on_changed()
        return result

    @staticmethod
    def _put_back(target: str, source: str, exc: Exception) -> str:
        """La biblioteca no aceptó la ruta nueva: el archivo vuelve a su carpeta (también desde otro disco,
        con la copia segura). Devuelve el motivo para el usuario, diciendo dónde quedó de verdad."""
        back = file_manager.move_files([target], os.path.dirname(source))
        if back.moved and os.path.exists(source):
            return f"No se pudo actualizar la biblioteca ({exc}); se devolvió a su carpeta."
        log.error("Tampoco se pudo devolver %s a %s: %s", target, source, back.failed)
        return f"No se pudo actualizar la biblioteca ({exc}) ni devolver el archivo: quedó en {target}"

    def reconcile_interrupted_moves(self) -> int:
        """Al abrir: un «Mover a otra carpeta» que quedó a medias (corte de luz, cierre forzado). Las canciones
        cuyo archivo ya llegó al destino pasan a apuntar ahí (así no se ofrece quitarlas de las playlists) y el
        movimiento queda en el Historial para deshacerlo. Devuelve cuántas se reconciliaron."""
        fixed = 0
        for session in file_history.interrupted_sessions():
            for c in session.changes:
                temp = file_manager.moving_temp(c.target)
                if os.path.exists(temp) and os.path.exists(c.source):
                    try:
                        os.remove(temp)  # copia a medias: el original sigue entero en su sitio
                        log.info("Temporal sobrante borrado (movimiento cortado): %s", temp)
                    except OSError:
                        pass
            done = [c for c in session.changes if journal.was_moved(c.source, c.target)]
            # Ni en el origen ni en el destino (p. ej. el pendrive de destino no está conectado): todavía
            # no se sabe dónde quedó, así que el plan se conserva y esas canciones siguen protegidas.
            unknown = [c for c in session.changes if not os.path.exists(c.source) and not os.path.exists(c.target)]
            try:
                self.db.update_track_paths([(track_id, c.target) for c in done for track_id in c.track_ids])
            except sqlite3.Error as exc:
                log.error("No se pudo reconciliar el movimiento interrumpido %s: %s", session.id, exc)
                continue  # se intenta otra vez en el próximo arranque
            if not unknown:
                file_history.finish(session, done)
            fixed += len(done)
            log.info("Movimiento interrumpido %s: %d archivo(s) ya estaban en el destino", session.id, len(done))
        if fixed:
            self._on_changed()
        return fixed

    def set_aside(self, items: list[tuple[Track, str]], library: list[Track], folder: str | None = None) -> SetAsideOutcome:
        """Mueve las canciones que no se pueden igualar a «_Volumen sin igualar» en la carpeta principal de
        la música, con un LEEME.txt que dice qué es cada una. Mover seguro: respaldo previo, nunca pisa nada,
        las playlists se conservan y se deshace desde el Historial."""
        if folder is None:  # sin carpeta elegida: «_Volumen sin igualar» en la carpeta principal
            folder = self.set_aside_folder(library)
            if not folder:
                raise file_manager.FileManagerError(
                    "No hay una carpeta principal clara para tu música (las canciones están repartidas en la raíz del "
                    "disco o en carpetas del sistema): no se apartó nada."
                )
        created = not os.path.isdir(folder)
        os.makedirs(folder, exist_ok=True)
        reasons = {t.path: reason for t, reason in items}
        result = self.move_tracks([t for t, _r in items], folder)
        if result.moved:
            when = datetime.now().strftime("%d/%m/%Y %H:%M")
            lines = []
            if not os.path.exists(os.path.join(folder, "LEEME.txt")):
                lines += [
                    "Canciones que no se pudieron igualar al volumen del resto",
                    "=========================================================",
                    "",
                    "El Reproductor de Música iguala el volumen DENTRO de los MP3 (sin recomprimir ni distorsionar),",
                    "para que suenen parejos en cualquier reproductor. Estas canciones no se pudieron igualar:",
                    "  · Picos altos: son más bajas que el resto, pero subirlas más las haría distorsionar.",
                    "  · No se pudo medir: el archivo está dañado o no tiene audio.",
                    "  · Otro formato: no son MP3 y no se pueden ajustar sin recomprimir (perder calidad).",
                    "Siguen en tu biblioteca y en tus playlists. Para devolverlas a su lugar:",
                    "Herramientas → Historial de cambios en archivos → «Mover a otra carpeta» → Deshacer.",
                ]
            lines += ["", f"Apartadas el {when}:"]
            lines += [f"  {os.path.basename(target)} — {reasons.get(source, '')}  (estaba en {os.path.dirname(source)})"
                      for source, target in result.moved]
            try:
                # newline="": los \r\n van tal cual (en modo texto Windows los volvería \r\r\n).
                with open(os.path.join(folder, "LEEME.txt"), "a", encoding="utf-8-sig", newline="") as handle:
                    handle.write("\r\n".join(lines) + "\r\n")
            except OSError as exc:
                log.warning("No se pudo escribir el LEEME de %s: %s", folder, exc)
        elif created:
            try:
                os.rmdir(folder)  # no se movió nada: no queda una carpeta vacía
            except OSError:
                pass
        return SetAsideOutcome(folder, result.moved, result.failed)

    def set_aside_folder(self, library: list[Track]) -> str:
        """Dónde quedaría la carpeta de las apartadas («» si no hay una carpeta principal clara)."""
        from .loudness import SET_ASIDE_FOLDER

        root = library_root(library)
        return os.path.join(root, SET_ASIDE_FOLDER) if root else ""

    def trash_tracks(self, tracks: list[Track]) -> tuple[int, list[tuple[str, str]]]:
        """Envía los archivos de las canciones a la Papelera y las quita de la biblioteca y de las playlists.
        Las que no se pudieron enviar se quedan como estaban. Devuelve (enviadas, [(ruta, motivo)])."""
        if not self._prepare("antes-de-borrar", set()):
            return 0, []
        ids = {t.id for t in tracks}
        self._forget(ids)  # suelta el archivo si está sonando y lo saca de la cola
        moved, failed = move_to_trash([t.path for t in tracks])
        sent = set(moved)
        self.db.remove_tracks([t.id for t in tracks if t.path in sent])
        self._on_changed()
        return len(moved), failed

    def trash_folder(self, folder: str, library: list[Track]) -> int:
        """Envía una carpeta entera a la Papelera y quita de la biblioteca las canciones de dentro."""
        inside = self.tracks_in(folder, library)
        if not self._prepare("antes-de-borrar-carpeta", set()):
            raise file_manager.FileManagerError("Operación cancelada.")
        self._forget({t.id for t in inside})
        file_manager.trash_folder(folder)
        removed = self.db.remove_tracks([t.id for t in inside])
        self._on_changed()
        return removed

    def undoable_track_ids(self) -> set[int]:
        """Canciones que, aunque falte su archivo, deshacer una operación del Historial recuperaría: las de
        una reunión de repetidas cuyo archivo sigue en la carpeta de revisión, y las de una conversión cuyo
        original sigue guardado (deshacer lo devuelve y la biblioteca vuelve a él)."""
        ids: set[int] = set()
        # Una reunión de repetidas que se puede deshacer (también interrumpida, o «Hecha» sin llegar a
        # guardar la biblioteca): sus canciones están en la carpeta de revisión y deshacer las devuelve.
        for s in review_folder.list_sessions():
            if s.status == review_folder.STATUS_UNDONE:
                continue
            ids.update(m.track_id for m in s.moved() if os.path.exists(m.target))
        # Un «Mover a otra carpeta» interrumpido cuyo destino todavía no se puede ver (disco desconectado).
        for s in file_history.interrupted_sessions():
            ids.update(i for c in s.changes if not os.path.exists(c.source) for i in c.track_ids)
        for s in converter.list_sessions():
            if s.status == converter.STATUS_UNDONE:
                continue
            for item in s.items:
                if os.path.exists(item.original) or (item.moved_to and os.path.exists(item.moved_to)):
                    ids.add(item.track_id)
        return ids

    def remove_missing(self, tracks: list[Track]) -> int:
        """Quita de la biblioteca (y de las playlists) canciones cuyo archivo ya no existe. Con respaldo
        previo; si el respaldo falla, no se quita nada. No toca ningún archivo de música."""
        if not tracks:
            return 0
        if backup.create_backup(self.db.conn, "antes-de-quitar-faltantes") is None:
            log.warning("No se quitaron las canciones faltantes: no se pudo crear el respaldo previo")
            return 0
        ids = {t.id for t in tracks}
        self._forget(ids)
        removed = self.db.remove_tracks(ids)
        log.info("Quitadas de la biblioteca %d canciones cuyo archivo ya no existe:\n%s",
                 removed, "\n".join(f"  {t.path}" for t in tracks))
        self._on_changed()
        return removed

    def interrupted(self) -> list[HistoryEntry]:
        """Operaciones que quedaron a medias por un cierre inesperado (las que no tocaron nada se cierran solas)."""
        found = []
        for s in review_folder.interrupted_sessions():
            if not s.moved():
                s.status = review_folder.STATUS_UNDONE
                s.save()
                continue
            found.append(HistoryEntry(KIND_REVIEW, _when(s.created_at), "reunión de repetidas", "", "Interrumpida",
                                      True, len(s.moved()), s, s.destination))
        for s in converter.interrupted_sessions():
            pending = converter.pending_items(s)
            if not pending:
                s.status = converter.STATUS_UNDONE
                s.save()
                continue
            found.append(HistoryEntry(KIND_CONVERSION, _when(s.created_at), "conversión a MP3", "", "Interrumpida",
                                      True, len(pending), s, s.originals_root))
        return found

    def undo(self, entry: HistoryEntry) -> UndoOutcome:
        """Deshace una reunión de repetidas o una conversión. (El volumen se revierte con su ventana,
        porque reescribir los MP3 lleva tiempo y va en su propio hilo.)"""
        if entry.kind == KIND_REVIEW:
            return self._undo_review(entry.session)
        if entry.kind == KIND_CONVERSION:
            return self._undo_conversion(entry.session)
        if entry.kind == KIND_FILES:
            return self._undo_files(entry.session)
        raise ValueError(f"No se puede deshacer aquí: {entry.kind}")

    def _undo_files(self, session: file_history.FileSession) -> UndoOutcome:
        """Deshace un renombre o un movimiento: cada archivo vuelve a su lugar y la biblioteca con él."""
        ids = {i for c in session.changes for i in c.track_ids}
        self._release(ids)
        if not self._prepare("antes-de-deshacer", set()):
            return UndoOutcome(0, [], "Operación cancelada.")

        def back(change: file_history.Change) -> None:
            current = {t.id: t.path for t in self.db.all_tracks() if t.id in set(change.track_ids)}
            target = change.target.rstrip("\\/")
            changes = []
            for track_id, path in current.items():
                if os.path.normcase(path) == os.path.normcase(change.target):
                    changes.append((track_id, change.source))  # un archivo
                else:
                    changes.append((track_id, os.path.join(change.source, os.path.relpath(path, target))))  # carpeta
            self.db.update_track_paths(changes)

        restored, problems = file_history.undo(session, on_restored=back)
        self._on_changed()
        message = f"Se {'deshizo' if len(restored) == 1 else 'deshicieron'} {plural(len(restored), 'cambio', 'cambios')}."
        if problems:
            message += f"\n\nNo se pudieron deshacer {len(problems)}:\n" + "\n".join(f"• {p}" for p in problems[:20])
        return UndoOutcome(len(restored), problems, message)

    def _undo_review(self, session: review_folder.Session) -> UndoOutcome:
        self._release({m.track_id for m in session.moved()})
        # La biblioteca se actualiza archivo por archivo, en cuanto cada uno vuelve a su lugar.
        restored, problems = review_folder.undo(
            session, on_restored=lambda m: self.db.update_track_paths([(m.track_id, m.source)])
        )
        self._on_changed()
        texts = [f"{os.path.basename(p.path)}: {p.reason}" for p in problems]
        message = f"Se devolvieron {plural(len(restored), 'archivo')} a su carpeta original."
        if texts:
            message += f"\n\nNo se pudieron devolver {len(texts)}:\n" + "\n".join(f"• {t}" for t in texts[:20])
        return UndoOutcome(len(restored), texts, message)

    def _undo_conversion(self, session: converter.ConversionSession) -> UndoOutcome:
        self._release({i.track_id for i in converter.pending_items(session)})
        def back_to_original(item: converter.Conversion) -> None:
            self.db.update_track_paths([(item.track_id, item.original)])
            self.db.save_loudness([(item.track_id, None, None)])
            self.db.set_norm_gains([(item.track_id, 0.0)])

        restored, problems = converter.undo(session, on_restored=back_to_original)
        self._on_changed()
        message = (
            f"Se {'deshizo' if len(restored) == 1 else 'deshicieron'} {plural(len(restored), 'conversión', 'conversiones')}: "
            "los originales volvieron a su sitio y los MP3 creados fueron a la Papelera."
        )
        if problems:
            message += "\n\nProblemas:\n" + "\n".join(f"• {p}" for p in problems[:15])
        return UndoOutcome(len(restored), list(problems), message)
