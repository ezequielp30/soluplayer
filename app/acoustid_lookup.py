"""Consulta de huellas en AcoustID (sin dependencias de la interfaz). Se envían la huella y la duración; nunca el audio.
Servicio gratuito para uso no comercial, máximo 3 consultas por segundo. Exige clave de aplicación."""

from __future__ import annotations

import http.client
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .online_lookup import USER_AGENT, _opener

REGISTER_URL = "https://acoustid.org/new-application"
_LOOKUP_URL = "https://api.acoustid.org/v2/lookup"
_META = "recordings releasegroups compress"
_TIMEOUT_S = 30
_MIN_INTERVAL_S = 0.34  # 3 consultas por segundo
_RETRIES = 3
_RETRY_WAIT_S = 3.0
_ERROR_INVALID_KEY = 4

_lock = threading.Lock()
_last_call = 0.0


class InvalidKey(Exception):
    """AcoustID rechazó la clave: no sirve seguir consultando."""


class ServiceError(Exception):
    """El servicio no respondió bien (sin internet, saturado…). No dice nada sobre la canción: se reintenta después."""


@dataclass(frozen=True)
class Recording:
    recording_id: str
    title: str
    artists: tuple[str, ...]  # en el orden de los créditos: el primero es el principal
    duration_s: float
    secondary_types: tuple[str, ...]  # de sus álbumes en MusicBrainz: «Live», «Compilation»…


@dataclass(frozen=True)
class Match:
    score: float
    recordings: tuple[Recording, ...]


def _wait_turn() -> None:
    global _last_call
    with _lock:
        pause = _MIN_INTERVAL_S - (time.monotonic() - _last_call)
        if pause > 0:
            time.sleep(pause)
        _last_call = time.monotonic()


def _error_code(body: bytes) -> int | None:
    try:
        return json.loads(body)["error"]["code"]
    except (ValueError, KeyError, TypeError):
        return None


def _post(key: str, duration: int, fingerprint: str, meta: str = _META) -> bytes:
    data = urllib.parse.urlencode(
        {"format": "json", "client": key, "duration": duration, "fingerprint": fingerprint, "meta": meta}
    ).encode()
    request = urllib.request.Request(_LOOKUP_URL, data=data, headers={"User-Agent": USER_AGENT})
    _wait_turn()
    with _opener.open(request, timeout=_TIMEOUT_S) as response:
        return response.read()


def check_key(key: str) -> None:
    """Comprueba la clave sin enviar ninguna canción: AcoustID mira la clave antes que la huella."""
    try:
        _post(key, 1, "AQAA", "")
    except urllib.error.HTTPError as exc:
        if _error_code(exc.read()) == _ERROR_INVALID_KEY:
            raise InvalidKey from exc
        if exc.code >= 500:
            raise ServiceError("AcoustID no responde bien ahora. Inténtalo más tarde.") from exc
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        raise ServiceError("No se pudo conectar con AcoustID. Revisa tu conexión a internet.") from exc


def lookup_raw(key: str, duration_s: float, fingerprint: str) -> str:
    """La respuesta tal como llega, para guardarla en la caché. Reintenta lo que suele ser pasajero."""
    for attempt in range(_RETRIES):
        wait = _RETRY_WAIT_S * (attempt + 1)
        try:
            return _post(key, int(round(duration_s)), fingerprint).decode("utf-8")
        except urllib.error.HTTPError as exc:
            if _error_code(exc.read()) == _ERROR_INVALID_KEY:
                raise InvalidKey from exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt == _RETRIES - 1:
                raise ServiceError(f"AcoustID respondió con un error ({exc.code}).") from exc
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, UnicodeDecodeError) as exc:
            if attempt == _RETRIES - 1:
                raise ServiceError("No se pudo conectar con AcoustID. Revisa tu conexión a internet.") from exc
        time.sleep(wait)
    raise ServiceError("AcoustID no responde.")


def parse(raw: str) -> list[Match]:
    """Solo lo que trae datos. Una respuesta rara es un error del servicio, no «canción sin coincidencia»."""
    try:
        data = json.loads(raw)
        if data["status"] != "ok":
            raise ServiceError("AcoustID devolvió un error.")
        return sorted((_match(item) for item in data.get("results") or []), key=lambda m: -m.score)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ServiceError("AcoustID devolvió una respuesta no válida.") from exc


def _match(item: dict) -> Match:
    recordings = []
    for record in item.get("recordings") or []:
        title = (record.get("title") or "").strip()
        artists = tuple(a["name"].strip() for a in record.get("artists") or [] if (a.get("name") or "").strip())
        if not title or not artists:
            continue
        types = {t for group in record.get("releasegroups") or [] for t in group.get("secondarytypes") or []}
        recordings.append(Recording(record.get("id", ""), title, artists, float(record.get("duration") or 0), tuple(sorted(types))))
    return Match(float(item.get("score") or 0), tuple(recordings))
