"""Propone el título con el formato «Canción - Quién la canta» a partir de títulos como los de YouTube.

Los títulos traen de todo: «Artista - Canción (Video Oficial)», «Canción | Álbum | Artista», y el artista
guardado a veces es el canal de donde se bajó. Cuando la propuesta no es segura se marca `sure=False`: la
ventana la deja sin elegir para que la revise una persona. Sin ventanas ni archivos (fácil de probar).
"""

from __future__ import annotations

import os
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
# La numeración del disco o de la lista de reproducción: «3-4 de 19 », «12/19 », «06. », «7 - », «4ª », «001_», «01-», «2.».
# No «3 Días», «7 de Mayo», «1º de Mayo» ni «24/7 Adoración» (el total no puede ser menor que el número).
_COUNT = re.compile(r"^\d{1,3}\s*(?:[-–—]\s*(\d{1,3})\s*)?(?:de|of|/)\s*(\d{1,3})(?=[\s.:)-]|$)[\s.:)–—-]*", re.I)
_NUMBER = re.compile(
    r"^(?:\d{1,2}\s*[.)–—-]\s+|\d{1,2}[ªº]\s+(?!del?\b)|\d{1,3}\s*_\s*|0\d{1,2}\s*[.)–—-]\s*(?=\S)|0\d\s+|\d{1,2}\.(?=[^\W\d]))", re.I
)
_CREDIT_WORD = r"(?:feat\.?|ft\.?|featuring)(?=\s)"
_CREDIT_IN_BRACKETS = re.compile(rf"\s*[(\[]\s*{_CREDIT_WORD}[^)\]]*[)\]]", re.I)
_CREDIT_TO_END = re.compile(rf"\s+{_CREDIT_WORD}.*$", re.I)
_ARTIST_VERSION = re.compile(r"\s*[(\[]\s*(?:en vivo|live|ac[uú]stic[oa]?|oficial|official)\s*[)\]]\s*$", re.I)
_YOUTUBE_TOPIC = re.compile(r"\s+-\s+topic$", re.I)
_NAME_LETTERS = str.maketrans({"ß": "ss", "Æ": "AE", "æ": "ae", "Ø": "O", "ø": "o", "Đ": "D", "đ": "d", "Ł": "L", "ł": "l"})
_HASHTAG = re.compile(r"(?<!\S)#\w+")
_GENERIC_SONG = re.compile(r"^(?:pista|track|tema)\s*\d*$", re.I)
_FILE_COPY = re.compile(r"\s*\(\d+\)$")  # «Canción - Cantante (2).mp3»
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


def _strip_numbering(text: str) -> str:
    count = _COUNT.match(text)
    if count:
        first = int(count.group(1) or re.match(r"\d+", text).group())
        rest = text[count.end():] if int(count.group(2)) >= max(first, 3) else text
    else:
        rest = _NUMBER.sub("", text)
    return clean_title(rest).strip() if rest.strip() else text


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
    return _strip_numbering(_LEAD_JUNK.sub("", _strip_end_symbols(text.strip())).strip())


def _strip_segment(segment: str) -> str:
    previous = None
    while segment != previous:
        previous = segment
        segment = _tidy(_TAIL_JUNK.sub("", _strip_end_symbols(segment)))
    return _tidy(segment.replace("@", ""))


def clean_song_title(title: str) -> str:
    """El título sin numeración de pista, sin lo que agrega YouTube y sin colaboradores. Conserva tildes y versión."""
    text = _CREDIT_TO_END.sub("", _CREDIT_IN_BRACKETS.sub("", strip_noise(title)))
    return _tidy(text)


def confirmed_title(title: str) -> str:
    """Un título ya decidido (por la base de datos o a mano): sin colaboradores ni signos al inicio, pero sin tocar sus
    números, que pueden ser parte del título («99 - Problems»)."""
    return _tidy(_CREDIT_TO_END.sub("", _CREDIT_IN_BRACKETS.sub("", clean_title(title or "").strip())))


def main_artist(artist: str, confirmed: str = "") -> str:
    """Un solo artista. `confirmed` es el primero que da una base de datos: manda sobre el texto. Sin ella se corta en
    «ft.», «feat.» y comas, pero no en «&» ni en «y»: «Ana y Ricky» o «Israel & New Breed» pueden ser un solo nombre."""
    if confirmed.strip():
        return confirmed.strip()
    name = _YOUTUBE_TOPIC.sub("", _display_artist(artist))
    name = _CREDIT_TO_END.sub("", _CREDIT_IN_BRACKETS.sub("", f" {name}")).split(",")[0]
    return _tidy(_ARTIST_VERSION.sub("", name)).rstrip(".")


def _plain_name_part(text: str) -> str:
    """Solo letras sin tildes (Ñ → N), números y espacios: «¿Qué? (En Vivo)» → «Que En Vivo». Vacío si no queda nada."""
    letters = unicodedata.normalize("NFKD", text.translate(_NAME_LETTERS).replace("&", " y "))
    plain = "".join(c for c in letters if not unicodedata.combining(c)).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Za-z0-9 ]+", " ", plain.replace("'", "")).split())


def file_stem(title: str, artist: str) -> str:
    """«TITULO - ARTISTA», sin extensión, para el nombre del archivo. Solo el nombre pierde tildes y puntuación: las
    etiquetas las conservan. El título ya viene decidido: si lleva un número, es parte de él («7 Dias», «1999»). Vacío
    si el título no deja nada escribible (otro alfabeto): el nombre no se toca y la canción queda por revisar."""
    song = _plain_name_part(title)
    singer = _plain_name_part(artist)
    if not song:
        return ""
    return f"{song} - {singer}" if singer else song


def has_file_name(title: str, artist: str) -> bool:
    """¿Título y artista dejan algo escribible? El nombre del archivo lleva los dos."""
    return bool(_plain_name_part(title)) and bool(_plain_name_part(artist))


def has_foreign_letters(text: str) -> bool:
    """¿Lleva letras que el nombre del archivo perdería? «夜に駆ける (En Vivo)» se quedaría solo en «En Vivo»."""
    return any(c.isalpha() and not c.isascii() for c in unicodedata.normalize("NFKD", text.translate(_NAME_LETTERS)))


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


def propose(title: str, artist: str, singers: KnownSingers, path: str = "") -> Proposal:
    """`path`: el archivo de la canción; su nombre ayuda con las que el título no alcanza para resolver."""
    proposal = _from_title(title, artist, singers)
    return _with_file_name(proposal, path, artist, singers) if path and not proposal.sure else proposal


def _with_file_name(proposal: Proposal, path: str, artist: str, singers: KnownSingers) -> Proposal:
    """Si el nombre coincide en la canción y en quién canta, la propuesta queda confirmada. Si dice otra cosa, se
    propone lo del nombre, pero sigue por revisar: a veces es de otra canción. Sin «Canción - Cantante» claro, nada."""
    stem = _FILE_COPY.sub("", os.path.splitext(os.path.basename(path))[0])
    parts = _segments(strip_noise(stem))
    if len(parts) != 2:
        return proposal
    index = _best_known(parts, singers)
    if index is None:
        tag = _plain_name(artist)
        index = next((i for i, part in enumerate(parts) if _mentions(part, tag)), None)
    if index is None:
        return proposal
    singer, song = parts[index], parts[1 - index]
    if _GENERIC_SONG.match(song):  # «Nancy Amancio - Pista 06.mp3» no dice qué canción es
        return proposal
    if _same_name(singer, proposal.singer) and _same_name(song, proposal.song):
        return Proposal(proposal.song, proposal.singer, True)
    return _result(song, singer, False)


def _same_name(one: str, other: str) -> bool:
    return bool(one and other) and (_mentions(one, normalize_text(_outside_brackets(other))) or _mentions(other, normalize_text(_outside_brackets(one))))


def _from_title(title: str, artist: str, singers: KnownSingers) -> Proposal:
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
