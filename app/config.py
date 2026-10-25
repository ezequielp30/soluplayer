"""Constantes y rutas de la aplicación."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Reproductor de Música"
ORG_NAME = "ReproductorMusica"  # ubica los ajustes y la biblioteca en el disco: no cambiarlo
AUTHOR_NAME = "Ezequiel Perez"
CONTACT_EMAIL = "ezequielp30@gmail.com"
DISCLAIMER = (
    "Uso bajo su propia responsabilidad. Este programa se entrega «tal cual», sin garantías de ningún tipo. "
    "El autor no se hace responsable por pérdidas de datos, daños en archivos o cualquier otro perjuicio "
    "derivado de su uso. Antes de usar las funciones que modifican archivos (convertir, ajustar volumen, "
    "mover, renombrar o enviar a la Papelera), haga una copia de seguridad de su música."
)

# La reproducción la hace el FFmpeg que trae PySide6 (no depende de los códecs instalados
# en Windows 10/11): MP3, AAC, ALAC, FLAC, Vorbis, Opus, WMA (1/2/Pro/Lossless/Voice),
# Monkey's Audio, WavPack, TTA, DSD, AC3/E-AC3, DTS, PCM/ADPCM…

# Formatos cuyas etiquetas lee mutagen: si no puede leerlas, el archivo se da por dañado.
TAGGED_EXTENSIONS = frozenset(
    {
        ".mp3", ".mp2",
        ".flac",
        ".wav",
        ".ogg", ".oga", ".opus",
        ".m4a", ".m4b", ".aac",
        ".wma",
        ".aif", ".aiff", ".aifc",
        ".ape",  # Monkey's Audio
        ".wv",  # WavPack
        ".tta",  # True Audio
        ".dsf", ".dff",  # DSD
        ".ac3",
    }
)
# Formatos que se reproducen pero cuyas etiquetas mutagen no lee: se importan con el
# nombre del archivo como título y la duración se completa al reproducirlos.
UNTAGGED_EXTENSIONS = frozenset({".mka", ".webm", ".caf", ".dts", ".eac3", ".amr", ".3ga"})

SUPPORTED_EXTENSIONS = TAGGED_EXTENSIONS | UNTAGGED_EXTENSIONS

AUDIO_FILE_FILTER = "Archivos de audio ({})".format(
    " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
)

RECENT_LIMIT = 100


def resource_path(*parts: str) -> Path:
    """Ruta a un recurso incluido (ícono…), tanto ejecutando desde el código como empaquetado."""
    import sys

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)


def data_dir() -> Path:
    """Carpeta donde se guarda la base de datos (fuera de la carpeta del proyecto).

    Se puede cambiar con la variable de entorno MUSICPLAYER_DATA_DIR.
    """
    override = os.environ.get("MUSICPLAYER_DATA_DIR")
    if override:
        base = Path(override)
    else:
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        base = Path(root) / ORG_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def database_path() -> Path:
    return data_dir() / "biblioteca.db"
