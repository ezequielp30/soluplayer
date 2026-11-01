"""Funciones auxiliares sin dependencias de la interfaz."""

from __future__ import annotations

import os
import re
import unicodedata


def format_time(ms: int) -> str:
    """Convierte milisegundos a m:ss o h:mm:ss."""
    seconds = max(0, int(ms) // 1000)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_total(ms: int) -> str:
    """Duración total legible: '1 h 23 min', '48 min' o '35 s'."""
    seconds = max(0, int(ms) // 1000)
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min"
    return f"{seconds} s"


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    word = singular if count == 1 else (plural_form or singular + "s")
    return f"{count} {word}"


# Letras que no se descomponen en «letra + tilde» (Łódź, Ørsted, Æon…): se pasan a su forma simple.
_PLAIN_LETTERS = str.maketrans({"ł": "l", "ø": "o", "æ": "ae", "œ": "oe", "đ": "d", "ð": "d", "þ": "th", "ħ": "h", "ı": "i", "ŀ": "l"})


def normalize_text(text: str) -> str:
    """Minúsculas y sin tildes, para buscar sin importar acentos."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().translate(_PLAIN_LETTERS)


_CLOSING = {"[": "]", "(": ")", "{": "}", "«": "»", "‹": "›", "“": "”", '"': '"'}


def clean_title(title: str) -> str:
    """El título sin los caracteres especiales del principio («►►Cuando…», «🔥El…», «| El…»). Si uno de ellos
    abre un corchete o paréntesis, se quita también el que lo cierra («[Oficial] Santo» → «Oficial Santo»).
    Los signos de apertura («¿», «¡») también se quitan; los números no son especiales. Un título hecho solo
    de signos queda como estaba."""
    text = (title or "").strip()
    start = re.match(r"^[\W_]+", text)
    if start is None or start.end() == len(text):
        return title
    rest = text[start.end():]
    for opening, closing in _CLOSING.items():
        if opening in start.group():
            rest = rest.replace(closing, "", 1)
    return " ".join(rest.split()) if "  " in rest else rest.strip()


def natural_key(text: str) -> str:
    """Clave para ordenar como espera una persona: sin distinguir mayúsculas ni tildes, sin contar los signos
    del principio («¡Aleluya», «(En vivo)…») y con los números como números (2 antes que 10)."""
    plain = normalize_text(text).strip()
    plain = re.sub(r"^[\W_]+", "", plain) or plain
    return re.sub(r"\d+", lambda m: m.group().zfill(12), plain)


def _long_path(path: str) -> str:
    """En Windows, «C:\\PROGRA~1\\…» → «C:\\Program Files\\…» (solo si existe; si no, queda igual)."""
    if os.name != "nt" or "~" not in path:
        return path
    import ctypes

    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetLongPathNameW(path, buffer, len(buffer))
    return buffer.value if 0 < length < len(buffer) else path


def no_markup(text: str) -> str:
    """Texto de etiquetas o de archivos ajenos que no puede parecer HTML: Qt dibuja como HTML cualquier
    texto que lo parezca (títulos, avisos, tooltips), y una etiqueta preparada podría hacer que Windows se
    conecte a otro equipo (p. ej. con una imagen «file://servidor/…»). Se ve casi igual: ‹ › en vez de < >."""
    if not text or ("<" not in text and ">" not in text):
        return text
    return text.replace("<", "‹").replace(">", "›")


def long_path(path: str) -> str:
    """La ruta con los nombres largos de Windows (si existe) y sin el prefijo «\\\\?\\»: así un
    «C:\\PROGRA~1\\…» y un «C:\\Program Files\\…» se pueden comparar y combinar."""
    if path.startswith("\\\\?\\UNC\\"):
        path = "\\\\" + path[8:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return _long_path(os.path.abspath(path))


_MAX_PATH = 259  # sin «rutas largas» activadas, Windows no admite rutas de 260 caracteres o más


def temp_beside(path: str, suffix: str) -> str:
    """Temporal junto a `path` («canción.mp3.convirtiendo.tmp»). Si con la terminación la ruta no cabría
    en Windows, un nombre corto en la misma carpeta (sigue terminando en `suffix`, así la limpieza al abrir
    lo reconoce). Siempre el mismo para la misma ruta."""
    temp = path + suffix
    if len(temp.encode("utf-16-le")) // 2 <= _MAX_PATH:
        return temp
    import hashlib

    digest = hashlib.sha1(os.path.basename(path).encode("utf-8")).hexdigest()[:8]
    short = os.path.join(os.path.dirname(path), f"~{digest}{suffix}")
    return short if len(short) < len(temp) else temp  # con un nombre ya corto no hay nada que ganar


def path_key(path: str) -> str:
    """Clave única de una ruta en Windows (mayúsculas/minúsculas, separadores, prefijo «\\\\?\\» y
    nombres cortos 8.3), para no importar dos veces el mismo archivo escrito de otra forma."""
    if path.startswith("\\\\?\\UNC\\"):
        path = "\\\\" + path[8:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return os.path.normcase(os.path.normpath(_long_path(os.path.abspath(path))))
