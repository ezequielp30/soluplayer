"""Propuestas de título (y artista) a partir del nombre del archivo."""

from __future__ import annotations

import os
import re

# Número de pista al inicio: "01 - ", "01. ", "1-", "3)", "01 " (con cero inicial), "CD1-03 ".
# Un número sin separador ni cero inicial es parte del nombre: «99 Luftballons», «50 Cent», «100 Años».
_TRACK_NUMBER = re.compile(
    r"^\s*(?:cd\s*\d+\s*[-_. ]\s*)?(?:\d{1,3}\s*[-_.)]\s*|0\d{1,2}\s+)", re.IGNORECASE
)
_SEPARATOR = re.compile(r"\s+[-–—]\s+")


def suggest_from_filename(path: str, detect_artist: bool = True) -> tuple[str, str | None]:
    """Devuelve (título, artista o None).

    Ejemplos:
        "03 - Queen - Bohemian Rhapsody.mp3" -> ("Bohemian Rhapsody", "Queen")
        "07_mi_cancion.flac"                 -> ("mi cancion", None)
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    text = stem.replace("_", " ")
    text = _TRACK_NUMBER.sub("", text, count=1) or text
    text = " ".join(text.split())

    artist = None
    if detect_artist:
        parts = _SEPARATOR.split(text, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            artist, text = parts[0].strip(), parts[1].strip()

    return (text or stem.strip() or "Sin título"), artist
