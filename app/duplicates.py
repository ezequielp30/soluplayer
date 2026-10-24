"""Detección de canciones repetidas en la biblioteca (sin dependencias de la interfaz)."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Callable

from .metadata import UNKNOWN_ALBUM
from .models import Track
from .utils import normalize_text, path_key

MODE_METADATA = "metadata"  # mismo título y artista, duración parecida
MODE_CONTENT = "content"  # archivos idénticos byte a byte

DURATION_TOLERANCE_MS = 3000

ProgressCallback = Callable[[int, int], bool]  # (hecho, total) -> False para cancelar


@dataclass
class DuplicateGroup:
    tracks: list[Track]
    keep_id: int  # copia propuesta para conservar

    @property
    def keep(self) -> Track:
        return next(t for t in self.tracks if t.id == self.keep_id)


def file_size(track: Track) -> int:
    try:
        return os.path.getsize(track.path) if track.available else 0
    except OSError:
        return 0


def _choose_keep(tracks: list[Track]) -> int:
    """Prefiere: archivo disponible > archivo más grande (suele ser mejor calidad) > el importado antes."""
    return min(tracks, key=lambda t: (not t.available, -file_size(t), t.id)).id


def _make_group(tracks: list[Track]) -> DuplicateGroup:
    ordered = sorted(tracks, key=lambda t: t.id)
    return DuplicateGroup(ordered, _choose_keep(ordered))


def find_duplicates(
    tracks: list[Track], mode: str = MODE_METADATA, progress: ProgressCallback | None = None
) -> list[DuplicateGroup] | None:
    """Devuelve los grupos de canciones repetidas, o None si se canceló."""
    if mode == MODE_CONTENT:
        return _by_content(tracks, progress)
    return _by_metadata(tracks)


_GENERIC_TITLE = re.compile(
    r"^(?:(?:pista|track|piste|faixa|titel|title|tema|cancion|song|audio)[\s._-]*\d+"  # «Pista 1», «Track03»
    r"|\d+"  # «01»
    r"|untitled|sin titulo|unknown|desconocido|audio track|)$"
)


def _metadata_key(track: Track) -> tuple[str, ...]:
    """Clave «misma canción». Con un título genérico («Pista 1», «Track 03», «01», vacío) título y artista
    no bastan: se exige además el mismo álbum y, si no hay álbum, la misma carpeta. Si no, «Pista 1» de
    cinco discos distintos parecería la misma canción. Un título real con artista desconocido (sacado
    del nombre del archivo, p. ej. «Dios manda lluvia») sí se compara entre carpetas."""
    title = normalize_text(" ".join(track.title.split()))
    artist = normalize_text(" ".join(track.artist.split()))
    album = normalize_text(" ".join(track.album.split()))
    key: tuple[str, ...] = (title, artist)
    if _GENERIC_TITLE.match(title):
        key += (album,)
        if album in ("", normalize_text(UNKNOWN_ALBUM)):
            key += (path_key(os.path.dirname(track.path)),)
    return key


def _by_metadata(tracks: list[Track]) -> list[DuplicateGroup]:
    buckets: dict[tuple[str, ...], list[Track]] = {}
    for track in tracks:
        buckets.setdefault(_metadata_key(track), []).append(track)

    groups: list[DuplicateGroup] = []
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        # Dentro del mismo título/artista se separan versiones de duración distinta (p. ej. una versión
        # en vivo). Se compara con la PRIMERA del grupo: comparar con la última encadenaría duraciones
        # sin límite (180 s, 182 s, 184 s… acabarían juntas).
        known = sorted((t for t in bucket if t.duration_ms > 0), key=lambda t: t.duration_ms)
        unknown = [t for t in bucket if t.duration_ms <= 0]
        clusters: list[list[Track]] = []
        for track in known:
            if clusters and track.duration_ms - clusters[-1][0].duration_ms <= DURATION_TOLERANCE_MS:
                clusters[-1].append(track)
            else:
                clusters.append([track])
        # Duración desconocida: solo se une si no hay duda de a qué grupo pertenece.
        if unknown:
            if len(clusters) == 1:
                clusters[0].extend(unknown)
            elif not clusters:
                clusters.append(unknown)
        groups.extend(_make_group(c) for c in clusters if len(c) >= 2)
    return sorted(groups, key=lambda g: normalize_text(g.tracks[0].title))


def _sha1(path: str) -> str | None:
    digest = hashlib.sha1()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _by_content(tracks: list[Track], progress: ProgressCallback | None) -> list[DuplicateGroup] | None:
    by_size: dict[int, list[Track]] = {}
    for track in tracks:
        size = file_size(track)
        if size > 0:
            by_size.setdefault(size, []).append(track)
    # Solo se calcula el hash de archivos que comparten tamaño.
    candidates = [t for same in by_size.values() if len(same) >= 2 for t in same]

    by_hash: dict[str, list[Track]] = {}
    for index, track in enumerate(candidates):
        if progress is not None and not progress(index, len(candidates)):
            return None
        digest = _sha1(track.path)
        if digest:
            by_hash.setdefault(digest, []).append(track)
    if progress is not None:
        progress(len(candidates), len(candidates))
    groups = [_make_group(same) for same in by_hash.values() if len(same) >= 2]
    return sorted(groups, key=lambda g: normalize_text(g.tracks[0].title))
