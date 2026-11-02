"""Organizador de MP3, sin ventanas: qué archivos examinar. Nada de este módulo modifica la música."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator

from .acoustid_lookup import Match, Recording
from .file_locator import _SKIPPED_FOLDERS as SYSTEM_FOLDERS
from .importer import SKIPPED_FOLDERS as PROGRAM_FOLDERS
from .online_lookup import _similar
from .title_format import clean_song_title, main_artist

PENDING_FOLDER = "PENDIENTES_REVISION"
BACKUP_FOLDER = "RESPALDOS_MP3"
_SKIPPED = frozenset(SYSTEM_FOLDERS) | frozenset(PROGRAM_FOLDERS) | {PENDING_FOLDER.casefold(), BACKUP_FOLDER.casefold()}

DECISION_AUTO, DECISION_REVIEW = "automatica", "revisar"
_SAME_NAME = 0.72  # parecido a partir del cual dos títulos o dos artistas se toman por el mismo
_GENERIC_NAME = re.compile(r"^(?:pista|track|audio|cancion|canción|song|unknown|desconocid[oa]|sin t[ií]tulo|grabaci[oó]n)?[\s_-]*\d*$", re.I)
_VERSIONS = (
    ("Remix", re.compile(r"\bremix\b", re.I)),
    ("Cover", re.compile(r"\bcover\b", re.I)),
    ("Instrumental", re.compile(r"\b(?:instrumental|karaoke|pista)\b", re.I)),
    ("Acustico", re.compile(r"\bac[uú]stic[oa]?\b|\bacoustic\b", re.I)),
    ("En Vivo", re.compile(r"\ben vivo\b|[(\[-]\s*live\b", re.I)),
)


@dataclass(frozen=True)
class Confidence:
    """Niveles configurables en Preferencias."""

    auto_score: float = 0.90  # parecido mínimo de la huella para procesar sola una canción
    strong_score: float = 0.97  # el mínimo si además el resultado contradice el nombre actual
    max_duration_diff_s: float = 5.0


@dataclass(frozen=True)
class Identification:
    decision: str
    reason: str  # por qué necesita revisión; también por qué se aceptó
    score: float = 0.0
    title: str = ""
    artist: str = ""
    version: str = ""  # «En Vivo», «Remix», «Cover», «Instrumental», «Acustico» o vacío si no consta
    recording_id: str = ""
    candidates: tuple[str, ...] = ()  # «Título - Artista» de las posibles coincidencias


def version_of(recording: Recording) -> str:
    """Solo lo que consta en los datos: si no consta, vacío. «Original» no se afirma nunca."""
    for name, pattern in _VERSIONS:
        if pattern.search(recording.title):
            return name
    return "En Vivo" if "Live" in recording.secondary_types else ""


def _is_generic(name: str) -> bool:
    return bool(_GENERIC_NAME.match(clean_song_title(name)))


def _agrees(recording: Recording, current_name: str) -> bool:
    plain = current_name.casefold()
    return any(_similar(part, recording.title) >= _SAME_NAME for part in re.split(r"\s+-\s+", current_name)) or (
        recording.title.casefold() in plain
    )


def identify(matches: list[Match], duration_s: float, current_names: Iterable[str], confidence: Confidence) -> Identification:
    """Decide con varias señales y no inventa: lo que no esté claro queda para revisar, con sus posibles coincidencias.
    `current_names` son el título de la etiqueta y el nombre del archivo; ayudan, pero no bastan para aceptar nada."""
    found = [m for m in matches if m.recordings]
    if not matches:
        return Identification(DECISION_REVIEW, "Su huella no está en AcoustID.")
    if not found:
        return Identification(DECISION_REVIEW, "AcoustID conoce la huella, pero no tiene datos de la canción.", matches[0].score)
    best = found[0]
    all_recordings = [r for m in found for r in m.recordings]
    candidates = tuple(dict.fromkeys(f"{r.title} - {r.artists[0]}" for r in all_recordings))[:8]

    def review(reason: str) -> Identification:
        return Identification(DECISION_REVIEW, reason, best.score, candidates=candidates)

    if best.score < confidence.auto_score:
        return review(f"La huella se parece solo en un {best.score:.0%}.")
    chosen = min(best.recordings, key=lambda r: abs(r.duration_s - duration_s) if r.duration_s else float("inf"))
    if chosen.duration_s and abs(chosen.duration_s - duration_s) > confidence.max_duration_diff_s:
        return review(f"La duración no coincide: {abs(chosen.duration_s - duration_s):.0f} s de diferencia.")
    same_score = [r for m in found if m.score >= best.score - 0.02 for r in m.recordings]
    if any(_similar(r.title, chosen.title) < _SAME_NAME for r in same_score):
        return review("Hay coincidencias igual de buenas con títulos distintos.")
    if len({main_artist("", r.artists[0]).casefold() for r in same_score}) > 1:
        return review("Hay coincidencias igual de buenas con artistas distintos.")
    names = [n for n in current_names if n and not _is_generic(n)]
    if names and not any(_agrees(chosen, n) for n in names) and best.score < confidence.strong_score:
        return review("El resultado contradice el nombre actual y la huella no es lo bastante exacta.")
    version = version_of(chosen)
    title = clean_song_title(chosen.title)
    if version and version.casefold() not in title.casefold():
        title = f"{title} ({version})"
    return Identification(
        DECISION_AUTO, f"Huella {best.score:.0%}.", best.score, title, main_artist("", chosen.artists[0]), version,
        chosen.recording_id, candidates,
    )


def collect_mp3(
    roots: Iterable[str], cancelled: Callable[[], bool] = lambda: False, on_problem: Callable[[str, OSError], None] | None = None,
) -> Iterator[tuple[str, int, int]]:
    """Da (ruta, tamaño, fecha) de cada MP3 bajo estas carpetas o unidades, sin repetir carpetas si las raíces se
    solapan. Sirve para colecciones enormes: no carga la lista completa en memoria y no sigue enlaces. Una carpeta o
    un archivo sin permiso se avisa y se sigue con el resto."""
    seen: set[str] = set()
    pending = list(reversed(list(roots)))
    while pending and not cancelled():
        folder = pending.pop()
        key = os.path.normcase(os.path.abspath(folder))
        if key in seen:
            continue
        seen.add(key)
        try:
            with os.scandir(folder) as scan:
                entries = sorted(scan, key=lambda e: e.name.casefold())
        except OSError as exc:
            if on_problem is not None:
                on_problem(folder, exc)
            continue
        below = []
        for entry in entries:
            if cancelled():
                return
            try:
                if entry.is_dir(follow_symlinks=False):
                    if not entry.is_junction() and entry.name.casefold() not in _SKIPPED:
                        below.append(entry.path)
                elif entry.is_file(follow_symlinks=False) and os.path.splitext(entry.name)[1].lower() == ".mp3":
                    info = entry.stat()
                    yield entry.path, info.st_size, info.st_mtime_ns
            except OSError as exc:
                if on_problem is not None:
                    on_problem(entry.path, exc)
        pending.extend(reversed(below))
