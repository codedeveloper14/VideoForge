import re
from dataclasses import dataclass

import requests

from src.core.config import config

_RELEASES_URL = "https://api.github.com/repos/codedeveloper14/VideoForge/releases/latest"
_TIMEOUT_SECONDS = 4


@dataclass(frozen=True)
class UpdateStatus:
    current_version: str
    latest_version: str | None
    update_available: bool
    release_url: str | None


def _parse_version(tag: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", tag)
    return tuple(int(p) for p in parts) or (0,)


def check_for_update() -> UpdateStatus:
    """Consulta el ultimo release publico de GitHub y compara contra config.app_version.
    Falla en silencio ante cualquier problema (sin internet, rate-limit, repo caido,
    JSON inesperado) devolviendo "no hay actualizacion" en vez de propagar el error --
    este chequeo es secundario y nunca debe romper ni bloquear el arranque de la app."""
    try:
        response = requests.get(_RELEASES_URL, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        latest_tag = data["tag_name"]
        release_url = data.get("html_url")
    except Exception:
        return UpdateStatus(
            current_version=config.app_version,
            latest_version=None,
            update_available=False,
            release_url=None,
        )

    update_available = _parse_version(latest_tag) > _parse_version(config.app_version)
    return UpdateStatus(
        current_version=config.app_version,
        latest_version=latest_tag,
        update_available=update_available,
        release_url=release_url,
    )
