"""Cliente de bajo nivel para Google Flow (labs.google/fx/tools/flow): manejo de
cookies/sesion por cuenta. La automatizacion real (Chromium, WS/HTTP bridge, el motor
de generacion por lotes) vive en modulos separados -- ver flow_animation_service.py."""

import sys
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
    """Prefijo "flow:" -- el bridge (flow_bridge.py, puertos 5556/5557) es compartido
    con Vibes (ver vibes_client.VIBES_ACCOUNT_HASH), y antes ambos vivian en el mismo
    namespace de string plano: un fallback de enrutamiento en background.js (dispatch())
    podia mandar trafico de Flow a la pestaña de Vibes o viceversa sin que nada lo
    detectara. Namespacear por plataforma hace que un hash de una plataforma nunca
    pueda pasar una verificacion pensada para la otra, aunque el enrutamiento falle."""
    h = 5381
    for c in value:
        h = ((h << 5) + h + ord(c)) & 0xFFFFFFFF
    return "flow:" + format(h, "08x")


def cookie_path(account_idx: int) -> Path:
    return get_flow_cookies_dir() / f"account_{account_idx}.txt"


def _legacy_cookie_paths(account_idx: int) -> list[Path]:
    """Ubicaciones pre-refactor de _FLOW_COOKIES_DIR (old/launcher.py): carpeta
    "cookies/" compartida con Whisk, junto al ejecutable/script -- reemplazada en
    el commit 6107951 ("migrar Flow - Etapa A") por get_flow_cookies_dir() (AppData,
    carpeta propia) sin migrar las sesiones que ya existian ahi. Dos candidatos:
    (1) junto al ejecutable actual -- el caso real de un usuario que actualiza el
    instalador viejo in-place, misma carpeta de instalacion; (2) old/cookies/ --
    donde quedo el archivo en este repo especifico, porque Week 1 del refactor
    movio launcher.py (y su "cookies/" de al lado) a old/ tal cual, en vez de al
    root. load_cookie() los prueba en orden como fallback de lectura para no
    perder una sesion real ya guardada."""
    name = f"account_{account_idx}.txt"
    root = (
        Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[3]
    )
    return [root / "cookies" / name, root / "old" / "cookies" / name]


def load_cookie(account_idx: int) -> str:
    path = cookie_path(account_idx)
    current_size = path.stat().st_size if path.is_file() else -1

    # Si la cookie legacy es mas grande que la actual (la actual esta vacia, es un
    # resto chico/invalido post-migracion, o directamente no existe), gana la
    # legacy: se respalda la actual (si habia algo) y se reemplaza.
    for legacy in _legacy_cookie_paths(account_idx):
        if not legacy.is_file():
            continue
        legacy_size = legacy.stat().st_size
        if legacy_size <= current_size:
            continue
        try:
            value = legacy.read_text(encoding="utf-8").strip()
        except Exception:
            value = ""
        if not value:
            continue
        if current_size > 0:
            backup = path.with_name(path.name + ".bak")
            try:
                path.replace(backup)
                logger.info("Cookie de Flow chica/obsoleta (%d bytes) respaldada en %s", current_size, backup)
            except Exception:
                pass
        logger.info("Cookie de Flow migrada desde ubicacion pre-refactor (%d bytes): %s", legacy_size, legacy)
        save_cookie(account_idx, value)
        return value

    if path.is_file():
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""
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
