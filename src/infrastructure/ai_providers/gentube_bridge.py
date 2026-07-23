"""Bridge de deteccion de sesion para gentube.app -- a diferencia de Flow/Qwen/
Vibes, GenTube no genera vía DOM en vivo (usa Playwright aislado headless, ver
gentube_service.run_batch), asi que este bridge SOLO detecta si el usuario ya tiene
una sesion iniciada en gentube.app en su Chrome real -- no hay cola de jobs.

Las cookies de sesion de Clerk (__session/__session_yakpvnhU) son httpOnly y ademas
JWT de vida corta (Clerk las rota cada ~1 minuto) -- por eso la deteccion la hace
background.js via chrome.cookies.getAll (unico API que puede leer cookies httpOnly
desde la extension) en el alarm "hb" existente, y el account_hash NO se calcula en
JS a partir de esa cookie rotante: se calcula aca, del lado Python, a partir del
email que gentube_service.probe_session() ya decodifica del JWT -- un identificador
estable, a diferencia de la cookie misma."""

from src.infrastructure.ai_providers import gentube_service
from src.infrastructure.ai_providers.account_presence_bridge import AccountPresenceBridge

_SEEN_TTL = 45.0

_presence = AccountPresenceBridge(seen_ttl=_SEEN_TTL)


def connected_accounts() -> list[str]:
    return _presence.connected_accounts()


def set_session_from_cookie(cookie_str: str) -> dict:
    """Valida `cookie_str` (mismo formato que gentube_service.probe_session espera)
    y, si es una sesion real, registra su presencia y dispara los listeners con
    {"cookie","email"}. Devuelve el resultado del probe para que la ruta HTTP pueda
    responder algo util sin repetir la validacion."""
    probe = gentube_service.probe_session(cookie_str)
    if not probe.get("ok"):
        return probe
    email = probe.get("user") or ""
    account_hash = "gt:" + (email or cookie_str[:32])
    _presence.register(account_hash)
    _presence.set_session(account_hash, {"cookie": cookie_str, "email": email})
    return probe


def add_session_listener(fn) -> None:
    _presence.add_session_listener(fn)
