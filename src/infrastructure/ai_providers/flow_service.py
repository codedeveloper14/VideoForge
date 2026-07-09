"""Cliente de bajo nivel para Google Flow (labs.google/fx/tools/flow): manejo de
cookies/sesion por cuenta. La automatizacion real (Chromium, WS/HTTP bridge, el motor
de generacion por lotes) vive en modulos separados -- ver flow_animation_service.py."""

from pathlib import Path

import requests

from src.utils.logger import get_logger
from src.utils.paths import get_flow_cookies_dir

logger = get_logger(__name__)

NUM_ACCOUNTS = 10
ACTIVE_SLOTS = 5
FLOW_URL = "https://labs.google/fx/tools/flow"
SESSION_URL = "https://labs.google/fx/api/auth/session"


def account_hash(value: str) -> str:
    h = 5381
    for c in value:
        h = ((h << 5) + h + ord(c)) & 0xFFFFFFFF
    return format(h, "08x")


def cookie_path(account_idx: int) -> Path:
    return get_flow_cookies_dir() / f"account_{account_idx}.txt"


def load_cookie(account_idx: int) -> str:
    path = cookie_path(account_idx)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def save_cookie(account_idx: int, cookie: str) -> None:
    cookie_path(account_idx).write_text(cookie, encoding="utf-8")


def get_session(cookie_str: str) -> dict:
    """Consulta la sesion de Flow con la cookie dada. {"bearer","email"} vacios si
    la cookie es invalida/expirada o la request falla."""
    try:
        r = requests.get(
            SESSION_URL, headers={"cookie": cookie_str, "Content-Type": "application/json"}, timeout=20
        )
        if r.status_code == 200:
            data = r.json()
            bearer = data.get("access_token", "")
            user = data.get("user", {})
            email = user.get("email") or user.get("name") or ""
            return {"bearer": bearer, "email": email}
    except Exception as exc:
        logger.info("flow_service.get_session error: %s", exc)
    return {"bearer": "", "email": ""}


def get_bearer(cookie_str: str) -> str:
    return get_session(cookie_str).get("bearer", "")
