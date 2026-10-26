"""Búsqueda de datos de canciones en bases de datos en línea (sin dependencias de la interfaz).

Fuentes gratuitas y sin cuenta ni clave:
  - MusicBrainz (https://musicbrainz.org): base abierta y colaborativa; máx. 1 consulta/segundo.
  - Deezer (https://developers.deezer.com): rápida, buena para música popular, carátulas grandes.
  - iTunes Search (Apple): muy precisa, pero Apple limita a unas 20 consultas por minuto.

Solo se envía el título y el artista de la canción. Nada se escribe en los archivos de audio.
"""

from __future__ import annotations

import http.client
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from . import __version__
from .metadata import UNKNOWN_ALBUM, UNKNOWN_ARTIST
from .models import Track
from .titles import suggest_from_filename
from .utils import no_markup, normalize_text

log = logging.getLogger(__name__)

USER_AGENT = f"ReproductorMusica/{__version__} (aplicacion de escritorio)"
TIMEOUT_S = 12


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    min_interval_s: float  # pausa mínima entre consultas (límites de cada servicio)
    description: str


SOURCES: dict[str, Source] = {
    "musicbrainz": Source("musicbrainz", "MusicBrainz", 1.1, "Base abierta y muy completa (1 consulta por segundo)."),
    "deezer": Source("deezer", "Deezer", 0.15, "Rápida, buena para música popular, carátulas grandes."),
    "itunes": Source("itunes", "iTunes (Apple)", 3.2, "Muy precisa, pero lenta en bibliotecas grandes (≈20 consultas/min)."),
}
DEFAULT_SOURCES = ("musicbrainz", "deezer")


class LookupError_(Exception):
    """Fallo al consultar un servicio. El mensaje es apto para el usuario."""


@dataclass
class Candidate:
    source: str
    title: str
    artist: str
    album: str
    duration_ms: int
    cover_url: str | None = None
    score: float = 0.0  # 0..1, parecido con la canción buscada

    def __post_init__(self) -> None:
        # Vienen de internet (MusicBrainz lo edita cualquiera): nunca deben poder dibujarse como HTML.
        self.title, self.artist, self.album = no_markup(self.title), no_markup(self.artist), no_markup(self.album)

    @property
    def source_name(self) -> str:
        return SOURCES[self.source].name


@dataclass
class Query:
    title: str
    artist: str | None
    duration_ms: int = 0

    @staticmethod
    def from_track(track: Track) -> "Query":
        """Usa las etiquetas; si faltan, intenta sacar título y artista del nombre del archivo."""
        artist = track.artist if track.artist and track.artist != UNKNOWN_ARTIST else None
        title = track.title
        cleaned, guessed_artist = suggest_from_filename(title + ".x", detect_artist=artist is None)
        title = cleaned or title
        if artist is None and guessed_artist:
            artist = guessed_artist
        return Query(title=title, artist=artist, duration_ms=track.duration_ms)


# ---------------------------------------------------------------------- red

_last_call: dict[str, float] = {}
_lock = threading.Lock()


def _wait_turn(source: Source) -> None:
    with _lock:
        elapsed = time.monotonic() - _last_call.get(source.key, 0.0)
        if elapsed < source.min_interval_s:
            time.sleep(source.min_interval_s - elapsed)
        _last_call[source.key] = time.monotonic()


class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """Sigue redirecciones solo a https: a http (texto plano) u otro esquema ni siquiera se hace la petición."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_HttpsOnlyRedirect)


def _get_json(source: Source, url: str) -> dict:
    for attempt in range(2):
        _wait_turn(source)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with _opener.open(request, timeout=TIMEOUT_S) as response:
                data = json.load(response)
            if not isinstance(data, dict):
                raise ValueError("la respuesta no es un objeto JSON")
            return data
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429, 503) and attempt == 0:
                time.sleep(4)  # el servicio pidió ir más despacio: se reintenta una vez
                continue
            raise LookupError_(f"{source.name} respondió con un error ({exc.code}). Inténtalo más tarde.") from exc
        except urllib.error.URLError as exc:
            raise LookupError_(
                f"No se pudo conectar con {source.name}. Revisa tu conexión a internet."
            ) from exc
        except (TimeoutError, OSError) as exc:
            raise LookupError_(f"{source.name} tardó demasiado en responder.") from exc
        except (ValueError, http.client.HTTPException) as exc:  # JSON roto o respuesta cortada
            raise LookupError_(f"{source.name} devolvió una respuesta no válida.") from exc
    raise LookupError_(f"{source.name} está limitando las consultas. Inténtalo más tarde.")


def _lucene(text: str) -> str:
    return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", text)


def search_musicbrainz(query: Query, limit: int = 8) -> list[Candidate]:
    terms = f'recording:"{_lucene(query.title)}"'
    if query.artist:
        terms += f' AND artist:"{_lucene(query.artist)}"'
    url = "https://musicbrainz.org/ws/2/recording/?fmt=json&limit=%d&query=%s" % (limit, urllib.parse.quote(terms))
    data = _get_json(SOURCES["musicbrainz"], url)
    results = []
    for rec in data.get("recordings", []):
        credit = rec.get("artist-credit") or []
        artist = "".join(c.get("name", "") + c.get("joinphrase", "") for c in credit).strip()
        release = _original_release(rec.get("releases") or [])
        cover = f"https://coverartarchive.org/release/{release['id']}/front-500" if release.get("id") else None
        results.append(
            Candidate("musicbrainz", rec.get("title", ""), artist, release.get("title", ""), int(rec.get("length") or 0), cover)
        )
    return results


def _original_release(releases: list[dict]) -> dict:
    """Elige el álbum de estudio original: oficial, de tipo «Album» sin ser recopilación
    ni directo, y el más antiguo. Si no hay ninguno así, el primero oficial."""
    if not releases:
        return {}

    def rank(release: dict) -> tuple:
        group = release.get("release-group") or {}
        secondary = group.get("secondary-types") or []
        return (
            release.get("status") != "Official",
            group.get("primary-type") != "Album",
            bool(secondary),  # Compilation, Live, Soundtrack…
            release.get("date") or "9999",
        )

    return min(releases, key=rank)


def search_deezer(query: Query, limit: int = 8) -> list[Candidate]:
    text = f"{query.artist} {query.title}" if query.artist else query.title
    url = "https://api.deezer.com/search?limit=%d&q=%s" % (limit, urllib.parse.quote(text))
    data = _get_json(SOURCES["deezer"], url)
    if "error" in data:
        raise LookupError_("Deezer rechazó la consulta. Inténtalo más tarde.")
    results = []
    for item in data.get("data", []):
        album = item.get("album") or {}
        results.append(
            Candidate(
                "deezer",
                item.get("title", ""),
                (item.get("artist") or {}).get("name", ""),
                album.get("title", ""),
                int(item.get("duration") or 0) * 1000,
                album.get("cover_big") or album.get("cover_medium"),
            )
        )
    return results


def search_itunes(query: Query, limit: int = 8) -> list[Candidate]:
    text = f"{query.artist} {query.title}" if query.artist else query.title
    url = "https://itunes.apple.com/search?entity=song&limit=%d&term=%s" % (limit, urllib.parse.quote(text))
    data = _get_json(SOURCES["itunes"], url)
    results = []
    for item in data.get("results", []):
        art = item.get("artworkUrl100")
        results.append(
            Candidate(
                "itunes",
                item.get("trackName", ""),
                item.get("artistName", ""),
                item.get("collectionName", ""),
                int(item.get("trackTimeMillis") or 0),
                art.replace("100x100bb", "600x600bb") if art else None,
            )
        )
    return results


_SEARCHERS = {"musicbrainz": search_musicbrainz, "deezer": search_deezer, "itunes": search_itunes}


# ---------------------------------------------------------------------- coincidencia

_BRACKETS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
_SUFFIX = re.compile(r"\s+[-–]\s+(remaster|remasterizad|live|en vivo|version|versión|edit|mono|stereo).*$", re.IGNORECASE)
_LIVE = re.compile(r"\b(live|en vivo|ao vivo|directo)\b", re.IGNORECASE)


def _core(text: str) -> str:
    text = _SUFFIX.sub("", _BRACKETS.sub("", text or ""))
    text = re.sub(r"\bremasteri[sz]ad[oa]\b.*$", "", text, flags=re.IGNORECASE)
    return " ".join(normalize_text(text).split())


def _similar(a: str, b: str) -> float:
    a, b = _core(a), _core(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def score(query: Query, candidate: Candidate) -> float:
    title = _similar(query.title, candidate.title)
    if query.duration_ms > 0 and candidate.duration_ms > 0:
        diff = abs(query.duration_ms - candidate.duration_ms) / 1000
        duration = 1.0 if diff <= 3 else max(0.0, 1 - (diff - 3) / 30)
    else:
        duration = 0.5
    if query.artist:
        value = 0.55 * title + 0.30 * _similar(query.artist, candidate.artist) + 0.15 * duration
    else:
        value = 0.75 * title + 0.25 * duration
    # Una versión en vivo no es la canción de estudio que se buscaba (y viceversa).
    if bool(_LIVE.search(candidate.title + " " + candidate.album)) != bool(_LIVE.search(query.title)):
        value -= 0.12
    return max(0.0, min(1.0, value))


@dataclass
class LookupResult:
    candidates: list[Candidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    failed_sources: list[str] = field(default_factory=list)  # claves de las fuentes que fallaron

    @property
    def best(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None


def lookup(query: Query, sources: list[str], limit_per_source: int = 6, keep: int = 8) -> LookupResult:
    """Consulta las fuentes elegidas y devuelve las mejores coincidencias, sin repetidos."""
    result = LookupResult()
    if not query.title.strip():
        return result
    for key in sources:
        try:
            found = _SEARCHERS[key](query, limit_per_source)
        except LookupError_ as exc:
            result.errors.append(str(exc))
            result.failed_sources.append(key)
            continue
        except Exception as exc:  # respuesta con un formato inesperado: no se pierden las demás fuentes
            log.warning("Respuesta inesperada de %s: %r", key, exc)
            result.errors.append(f"{SOURCES[key].name} devolvió datos con un formato inesperado.")
            result.failed_sources.append(key)
            continue
        for candidate in found:
            candidate.score = score(query, candidate)
            result.candidates.append(candidate)
    result.candidates.sort(key=lambda c: c.score, reverse=True)
    unique, seen = [], set()
    for candidate in result.candidates:
        key = (normalize_text(candidate.title), normalize_text(candidate.artist), normalize_text(candidate.album))
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    result.candidates = unique[:keep]
    return result


def needs_data(track: Track) -> bool:
    """Canción con datos incompletos: sin artista o álbum, o con un título que parece nombre de archivo."""
    looks_like_file = bool(re.match(r"^\s*\d{1,3}\s*[-_.]", track.title)) or "_" in track.title
    return track.artist == UNKNOWN_ARTIST or track.album == UNKNOWN_ALBUM or looks_like_file


def download(url: str, limit_bytes: int = 8 * 1024 * 1024) -> bytes | None:
    """Descarga una carátula. Devuelve None si no existe o falla (no es un error grave)."""
    if url.lower().startswith("http://"):
        url = "https://" + url[7:]  # las fuentes sirven las carátulas también por https: sin texto plano
    if not url.lower().startswith("https://"):
        return None  # nunca leer archivos locales (file://) ni otros esquemas
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with _opener.open(request, timeout=TIMEOUT_S) as response:
            if not response.geturl().lower().startswith("https://"):
                return None  # una redirección a http (o a otro esquema) no se sigue
            data = response.read(limit_bytes + 1)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException):
        return None
    return data if 0 < len(data) <= limit_bytes else None
