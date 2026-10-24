"""Lectura de metadatos de audio con mutagen (sin dependencias de Qt)."""

from __future__ import annotations

import base64
import math
import os
from dataclasses import dataclass

import mutagen
from mutagen import MutagenError
from mutagen.flac import Picture
from mutagen.id3 import ID3

UNKNOWN_ARTIST = "Artista desconocido"
UNKNOWN_ALBUM = "Álbum desconocido"
UNKNOWN_GENRE = "Sin género"

_FRONT_COVER = 3


class MetadataError(Exception):
    """El archivo no se pudo leer como audio. El mensaje es apto para el usuario.

    `corrupt` distingue un archivo dañado de un problema de acceso (permisos, disco),
    para no ofrecer borrar archivos que en realidad están bien.
    """

    def __init__(self, message: str, corrupt: bool = True) -> None:
        super().__init__(message)
        self.corrupt = corrupt


@dataclass
class AudioMetadata:
    title: str
    artist: str
    album: str
    genre: str
    duration_ms: int
    cover: bytes | None
    # False cuando la etiqueta no existe y se usó un valor de reemplazo.
    has_title_tag: bool = True
    has_artist_tag: bool = True


def read_metadata(path: str) -> AudioMetadata:
    """Lee título, artista, álbum, género, duración y carátula.

    Lanza MetadataError si el archivo está dañado o no es audio reconocible.
    """
    try:
        audio = mutagen.File(path)
    except PermissionError as exc:
        raise MetadataError("No hay permiso para leer el archivo.", corrupt=False) from exc
    except OSError as exc:
        raise MetadataError(f"No se pudo leer el archivo ({exc.strerror or exc}).", corrupt=False) from exc
    except MutagenError as exc:
        raise MetadataError("El archivo parece dañado o no es un audio válido.") from exc
    except Exception as exc:  # mutagen puede lanzar errores variados con archivos corruptos
        raise MetadataError("El archivo parece dañado o tiene un formato no reconocido.") from exc

    if audio is None:
        raise MetadataError("No se reconoce el contenido como un archivo de audio.")

    try:  # algunos formatos la calculan al pedirla y pueden fallar (p. ej. un DSF con frecuencia 0)
        length = float(getattr(getattr(audio, "info", None), "length", 0) or 0)
    except Exception:
        length = 0.0
    if not math.isfinite(length) or not 0 <= length < 10**7:  # más de ~115 días: dato absurdo
        length = 0.0  # desconocida: el reproductor la completa al sonar
    duration_ms = int(round(length * 1000))

    easy_tags = _easy_tags(path)
    sources = [t for t in (easy_tags, audio.tags) if t]

    title = _first(sources, "title", "Title", "TIT2", "\xa9nam")
    artist = _first(sources, "artist", "Author", "TPE1", "\xa9ART", "albumartist", "TPE2", "aART")
    album = _first(sources, "album", "WM/AlbumTitle", "TALB", "\xa9alb")
    genre = _first(sources, "genre", "WM/Genre", "TCON", "\xa9gen")

    return AudioMetadata(
        title=title or os.path.splitext(os.path.basename(path))[0],
        artist=artist or UNKNOWN_ARTIST,
        album=album or UNKNOWN_ALBUM,
        genre=genre or UNKNOWN_GENRE,
        duration_ms=max(0, duration_ms),
        cover=_read_cover(audio),
        has_title_tag=bool(title),
        has_artist_tag=bool(artist),
    )


def basic_metadata(path: str) -> AudioMetadata:
    """Datos mínimos para un formato sin etiquetas legibles; la duración la completa el reproductor."""
    return AudioMetadata(
        title=os.path.splitext(os.path.basename(path))[0],
        artist=UNKNOWN_ARTIST,
        album=UNKNOWN_ALBUM,
        genre=UNKNOWN_GENRE,
        duration_ms=0,
        cover=None,
        has_title_tag=False,
        has_artist_tag=False,
    )


def _easy_tags(path: str):
    try:
        easy = mutagen.File(path, easy=True)
    except Exception:
        return None
    return getattr(easy, "tags", None) if easy is not None else None


def _first(sources, *keys: str) -> str:
    for tags in sources:
        for key in keys:
            try:
                value = tags.get(key)
            except Exception:
                value = None
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                value = value[0] if value else None
                if value is None:
                    continue
            text = str(value).strip().strip("\x00")
            if text:
                return text
    return ""


def _read_cover(audio) -> bytes | None:
    try:
        pictures = getattr(audio, "pictures", None)  # FLAC
        if pictures:
            return _pick_picture(pictures)

        tags = audio.tags
        if not tags:
            return None

        if isinstance(tags, ID3):  # MP3, WAV y AIFF con ID3
            apics = tags.getall("APIC")
            return _pick_picture(apics) if apics else None

        covr = tags.get("covr")  # MP4 / M4A
        if covr:
            return bytes(covr[0])

        blocks = tags.get("metadata_block_picture")  # Ogg Vorbis / Opus
        if blocks:
            decoded = [Picture(base64.b64decode(b)) for b in blocks]
            return _pick_picture(decoded)
    except Exception:
        return None
    return None


def _pick_picture(pictures) -> bytes | None:
    # La portada si la hay; si no, la primera imagen que tenga datos (una vacía no sirve).
    usable = [p for p in pictures if getattr(p, "data", None)]
    front = [p for p in usable if getattr(p, "type", None) == _FRONT_COVER]
    chosen = (front or usable or [None])[0]
    return bytes(chosen.data) if chosen is not None else None


# ---------------------------------------------------------------------- calidad


@dataclass(frozen=True)
class Quality:
    kbps: int | None
    sample_rate: int | None
    channels: int | None
    codec: str

    def text(self) -> str:
        parts = []
        if self.kbps:
            parts.append(f"{self.kbps} kbps")
        if self.sample_rate:
            parts.append(f"{self.sample_rate / 1000:g} kHz")
        if self.channels:
            parts.append({1: "mono", 2: "estéreo"}.get(self.channels, f"{self.channels} canales"))
        return " · ".join(parts) or "—"


def audio_quality(path: str) -> Quality:
    """Calidad leída de la cabecera del archivo (no lo modifica). Valores desconocidos → None."""
    codec = os.path.splitext(path)[1].lstrip(".").upper()
    try:
        info = mutagen.File(path).info
    except Exception:
        return Quality(None, None, None, codec)
    bitrate = getattr(info, "bitrate", 0) or 0
    return Quality(
        round(bitrate / 1000) if bitrate else None,
        getattr(info, "sample_rate", None) or None,
        getattr(info, "channels", None) or None,
        codec,
    )
