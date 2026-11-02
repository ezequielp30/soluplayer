"""Saber si hay una versión nueva publicada en GitHub. Solo pregunta y avisa: nunca descarga ni instala nada."""

from __future__ import annotations

import http.client
import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from . import __version__
from .online_lookup import _opener

log = logging.getLogger(__name__)

RELEASES_PAGE = "https://github.com/ezequielp30/soluplayer/releases"
_LATEST_API = "https://api.github.com/repos/ezequielp30/soluplayer/releases/latest"
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_TIMEOUT_S = 15
_NO_CONNECTION = "No se pudo consultar GitHub. Revisa tu conexión a internet."


class UpdateError(Exception):
    """El texto se le muestra a la persona."""


@dataclass(frozen=True)
class Release:
    version: str
    url: str


def _parts(version: str) -> tuple[int, int, int] | None:
    match = _VERSION.match((version or "").strip())
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def is_newer(version: str, current: str = __version__) -> bool:
    """Una versión ilegible nunca es más nueva: ante la duda, no se avisa."""
    new, now = _parts(version), _parts(current)
    return new is not None and now is not None and new > now


def _safe_page(url: object) -> str:
    """Solo se abre una página de este repositorio, diga lo que diga la respuesta."""
    return url if isinstance(url, str) and url.startswith(RELEASES_PAGE + "/") else RELEASES_PAGE


def fetch_latest() -> Release:
    request = urllib.request.Request(
        _LATEST_API,
        headers={"User-Agent": f"ReproductorMusica/{__version__}", "Accept": "application/vnd.github+json"},
    )
    try:
        with _opener.open(request, timeout=_TIMEOUT_S) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"GitHub respondió con un error ({exc.code}). Inténtalo más tarde.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(_NO_CONNECTION) from exc
    except (ValueError, http.client.HTTPException) as exc:
        raise UpdateError("GitHub devolvió una respuesta no válida. Inténtalo más tarde.") from exc
    tag = data.get("tag_name") if isinstance(data, dict) else None
    if not isinstance(tag, str) or _parts(tag) is None:
        raise UpdateError("GitHub devolvió una respuesta no válida. Inténtalo más tarde.")
    return Release(tag.strip().lstrip("v"), _safe_page(data.get("html_url")))


class UpdateCheckWorker(QObject):
    """Consulta GitHub en su propio hilo: la música y la ventana siguen respondiendo."""

    finished = Signal(object, str)  # Release o None, y el problema si lo hubo

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(fetch_latest(), "")
        except UpdateError as exc:
            log.info("No se pudo buscar actualizaciones: %s", exc)
            self.finished.emit(None, str(exc))
        except Exception:  # nunca dejar el hilo colgado: «terminado» se avisa siempre
            log.exception("Error inesperado al buscar actualizaciones")
            self.finished.emit(None, _NO_CONNECTION)
