"""Propone el título con el formato «Canción - Quién la canta» a partir de títulos como los de YouTube.

Los títulos traen de todo: «Artista - Canción (Video Oficial)», «Canción | Álbum | Artista», y el artista
guardado a veces es el canal de donde se bajó. Cuando la propuesta no es segura se marca `sure=False`: la
ventana la deja sin elegir para que la revise una persona. Sin ventanas ni archivos (fácil de probar).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .utils import clean_title, normalize_text

_JUNK_MARK = re.compile(r"v[ií]deo|oficial|official|lyric|letra|\baudio\b|visuali[sz]er|\bhd\b|\bhq\b|\b4k\b|^m[uú]sica$", re.I)
_KEEP_MARK = re.compile(r"\b(en vivo|live|ac[uú]stic|feat|ft\b)", re.I)
_BRACKETS = re.compile(r"\(([^()]*)\)|\[([^\[\]]*)\]|\{([^{}]*)\}")
_ONLY_JUNK = re.compile(
    r"^(?:(?:v[ií]deos?|videoclip|clip|oficial|official|lyrics?|letras?|audio|visuali[sz]er|hd|hq|4k|m[uú]sica|musical"
    r"|medley|con|de|y|and|with)[\s,.:;!_&-]*)+$",
    re.I,
)
_TAIL_JUNK = re.compile(
    r"[\s,.:;_-]*\b(?:(?:v[ií]deo\s*(?:de\s+)?)?(?:lyrics?|letras?)(?:\s+(?:lyrics?|letras?))*(?:\s+(?:v[ií]deo\s*)?(?:oficial|official))?"
    r"|con\s+letras?|v[ií]deo\s*(?:clip|musical|oficial|official)?(?:\s+(?:con\s+letra|oficial|official|lyrics?))*"
    r"|v[ií]deoclip|official\s+(?:music\s+|lyrics?\s+)?v[ií]deo|audio(?:\s+(?:oficial|official))?|oficial)\s*$",
    re.I,
)
_LEAD_JUNK = re.compile(r"^(?:v[ií]deo\s*\d*[.:)\s-]*(?=\S)|(?:v[ií]deo\s+)?oficial\s+|[A-Z]{1,5}\s?\d{2,}\s+)", re.I)
_HASHTAG = re.compile(r"(?<!\S)#\w+")
_EXTENSION = re.compile(r"\.(?:wmv|mp4|avi|flv|mkv|webm|mp3|m4a)$", re.I)
_SEPARATOR = re.compile(r"\s*\|+\s*|\s*//\s*|\s+[-–—~]+\s*|[-–—~]+\s+|\s{2,}|\s+by\s+")
_TIGHT_DASH = re.compile(r"(?<=\S)[-–—](?=\S)")
_PROTECTED = re.compile(r'\([^()]*\)|\[[^\[\]]*\]|"[^"]*"|“[^”]*”')
_PROTECT = str.maketrans({"-": "", "–": "", "—": "", "|": "", "~": "", "/": "", " ": ""})
_UNPROTECT = {v: chr(k) for k, v in _PROTECT.items()}
_NAME_SUFFIX = re.compile(r"\s+(?:oficial|official|music|musica|vevo|en espanol|ofi\w*)$")
_CHANNEL = re.compile(
    r"\d$|\.$|\b(?:m[uú]sica cristiana|cristian[oa]s?|canal|channel|tv|iglesia|records?|videos?|play|label|oficial|official)\b", re.I
)


@dataclass(frozen=True)
class Proposal:
    song: str
    singer: str
    sure: bool

    @property
    def title(self) -> str:
        return f"{self.song} - {self.singer}" if self.singer else self.song


def _tidy(text: str) -> str:
    return " ".join(text.split()).strip(" -–—~|,;:_+")


def _strip_end_symbols(text: str) -> str:
    """Quita adornos del final («◄◄», «⚔️»): nunca letras, números ni puntuación normal."""
    while text and unicodedata.category(text[-1]) in ("So", "Sk", "Cf", "Mn", "Zs"):
        text = text[:-1]
    return text


def _protect(text: str) -> str:
    """Lo que está entre paréntesis o comillas no se parte («(Glorea - En Vivo)»)."""
    return _PROTECTED.sub(lambda m: m.group().translate(_PROTECT), text)


def _unprotect(text: str) -> str:
    return "".join(_UNPROTECT.get(c, c) for c in text)


def strip_noise(title: str) -> str:
    """Sin lo que agrega YouTube: «(Video Oficial)», «[Audio]», «#hashtag», adornos, «.wmv». Conserva los
    espacios dobles: separan datos («Cuando estoy en tu presencia   New Wine»)."""
    def bracket(match: re.Match) -> str:
        inner = next(g for g in match.groups() if g is not None)
        return "" if _JUNK_MARK.search(inner.strip()) and not _KEEP_MARK.search(inner) else match.group()

    text = clean_title(title or "").strip()
    text = _BRACKETS.sub(bracket, text)
    text = _HASHTAG.sub("", text)
    text = _EXTENSION.sub("", _strip_end_symbols(text.strip()))
    return _LEAD_JUNK.sub("", _strip_end_symbols(text.strip())).strip()


def _strip_segment(segment: str) -> str:
    previous = None
    while segment != previous:
        previous = segment
        segment = _tidy(_TAIL_JUNK.sub("", _strip_end_symbols(segment)))
    return _tidy(segment.replace("@", ""))


def _segments(text: str) -> list[str]:
    parts: list[str] = []
    for raw in _SEPARATOR.split(_protect(text)):
        part = _strip_segment(_unprotect(raw))
        if part and not _ONLY_JUNK.match(part) and normalize_text(part) not in {normalize_text(p) for p in parts}:
            parts.append(part)
    return parts


def _plain_name(artist: str) -> str:
    """El artista guardado sin lo que agregan los canales: «Montesanto Oficial», «Ingrid Rosario Music»."""
    name = normalize_text(artist or "").strip(" .")
    shorter = _NAME_SUFFIX.sub("", name)
    return shorter if len(shorter) >= 3 else name


class KnownSingers(Counter):
    """Nombres que se pueden tomar por cantantes y en cuántas canciones están. `artists` son los guardados como
    artista; los demás solo se repiten en varios títulos, y pueden ser una canción con varias versiones."""

    artists: frozenset[str] = frozenset()


def known_singers(tracks: Iterable[tuple[str, str]]) -> KnownSingers:
    artists: Counter[str] = Counter()
    seen: Counter[str] = Counter()
    for title, artist in tracks:
        if artist:
            artists[_plain_name(artist)] += 1
        for segment in _segments(strip_noise(title)):
            seen[normalize_text(segment)] += 1
    names = set(artists)
    artists.update({name: count for name, count in seen.items() if count >= 2})
    known = KnownSingers({n: c for n, c in artists.items() if len(n) >= 3})
    known.artists = frozenset(n for n in names if len(n) >= 3)
    return known


def _outside_brackets(text: str) -> str:
    return _PROTECTED.sub(" ", text)


def _mentions(segment: str, name: str) -> bool:
    """El segmento es ese nombre o lo trae con palabras enteras («Raisa Diaz ft Chanel»). Lo que está entre
    paréntesis no cuenta: «Tu amor no tiene fin (Generación 12)» no es de Generación 12."""
    plain = normalize_text(_outside_brackets(segment))
    return bool(name) and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", plain) is not None


def _best_known(segments: list[str], singers: KnownSingers) -> int | None:
    """El segmento que trae el nombre conocido más largo, primero entre los artistas guardados; a igual largo,
    el último («Canción - Cantante»)."""
    for names in (singers.artists, singers):
        scored = [(max((len(n) for n in names if _mentions(s, n)), default=0), i) for i, s in enumerate(segments)]
        best, index = max(scored)
        if best:
            return index
    return None


def propose(title: str, artist: str, singers: KnownSingers) -> Proposal:
    segments = _segments(strip_noise(title))
    tag = _plain_name(artist)
    if len(segments) == 1 and _TIGHT_DASH.search(segments[0]):  # «Estar contigo-Miguel Cassina»
        tight = [_strip_segment(p) for p in _TIGHT_DASH.split(segments[0])]
        if len(tight) == 2 and all(tight) and (_best_known(tight, singers) is not None or any(_mentions(p, tag) for p in tight)):
            segments = tight
    if not segments:
        return Proposal(clean_title(title), artist, False)
    if len(segments) == 1:
        return _one_segment(segments[0], artist, singers)
    for index, segment in enumerate(segments):
        if _mentions(segment, tag):
            others = [s for i, s in enumerate(segments) if i != index]
            return _result(others[0], segment, len(segments) <= 3)
    index = _best_known(segments, singers)
    if index is None:  # lo más común es «Canción - Cantante»: pero sin confirmar, que lo revise una persona
        return _result(segments[0], segments[1], False)
    others = [s for i, s in enumerate(segments) if i != index]
    named_too = any(_mentions(o, n) for o in others for n in singers.artists)
    starts_with_name = any(normalize_text(segments[index]).startswith(n) for n in singers if _mentions(segments[index], n))
    return _result(others[0], segments[index], len(segments) == 2 and not named_too and starts_with_name)


def _result(song: str, singer: str, sure: bool) -> Proposal:
    if song.startswith("(") and song.endswith(")"):  # «Gracias por la Cruz - (Anna y Ricky)»: el paréntesis es quien canta
        song, singer, sure = singer, song[1:-1].strip(), False
    return Proposal(song.replace('"', "").replace("“", "").replace("”", "").strip(), _one_credit(singer), sure)


def _one_credit(singer: str) -> str:
    """Sin nombres repetidos, y sin la lista de compositores («Montesanto, John Sullivan Dwight, Adolphe Adam»)."""
    names = [n.strip() for n in singer.split(",") if n.strip()]
    unique = [n for i, n in enumerate(names) if normalize_text(n) not in {normalize_text(o) for o in names[:i]}]
    return unique[0] if len(unique) >= 3 else ", ".join(unique)


def _one_segment(text: str, artist: str, singers: KnownSingers) -> Proposal:
    plain = normalize_text(text)
    tag = _plain_name(artist)
    if plain == tag:
        return Proposal(text, artist, False)
    # Primero el artista guardado; los demás, solo nombres de varias palabras («Digno» es una canción).
    raw_tag = normalize_text(artist or "").strip(" .")
    others = sorted((n for n in singers if singers[n] >= 2 and " " in n), key=len, reverse=True)
    for name in [raw_tag, tag, *others]:  # «isabelle valdez Una oracion», «Digno De Adorar I MISSION MUSICA»
        if not name:
            continue
        if plain.startswith(name + " "):
            return _result(_tidy(text[len(name):]), _tidy(text[:len(name)]), True)
        if plain.endswith(" " + name):
            song = re.sub(r"\s+[Il]$", "", _tidy(text[:-len(name)]))  # una «I» puesta en lugar de «|»
            return _result(song, _tidy(text[-len(name):]), True)
    looks_like_a_name = len((artist or "").split()) >= 2 and all(w[:1].isupper() or not w[:1].isalpha() for w in artist.split())
    trusted = (singers[tag] >= 2 or looks_like_a_name) and not _CHANNEL.search(artist or "")
    return _result(text, _display_artist(artist), trusted)


def _display_artist(artist: str) -> str:
    return re.sub(r"\s+(?:oficial|official)\.?$", "", (artist or "").strip(), flags=re.I)
