"""Bridge de deteccion de sesion para grok.com -- SOLO detecta/captura sesion,
nunca genera: la generacion de Grok sigue siendo 100% API HTTP directa
(GrokAccountClient en grok_service.py, requests.Session/curl_cffi con las cookies
capturadas), sin tocar esta pieza.

Nombre distinto de grok_bridge.js (la extension ya trae ese archivo + su par
grok_upload_relay.js, un relay de upload de imagenes huerfano de otro flujo, sin
contraparte Python -- no reusar su mecanismo, evitar la confusion de nombres).

Igual que gentube_bridge.py, el account_hash no se calcula en JS a partir de una
cookie que puede rotar: se deriva aca de la cookie `sso` (identificador de sesion
de Grok), el unico dato con el que list_account_sessions() ya determina "activo"
hoy (ck_dict.get("sso"))."""

import hashlib

from src.infrastructure.ai_providers.account_presence_bridge import AccountPresenceBridge

_SEEN_TTL = 45.0

_presence = AccountPresenceBridge(seen_ttl=_SEEN_TTL)


def connected_accounts() -> list[str]:
    return _presence.connected_accounts()


def set_session_from_cookies(cookies: list[dict]) -> dict:
    """`cookies` es la lista cruda que manda background.js (chrome.cookies.getAll
    para grok.com). Valida que tenga `sso`, deriva un account_hash estable de su
    valor y dispara los listeners con {"cookies": [...]}."""
    if not isinstance(cookies, list):
        return {"ok": False}
    ck_dict = {c.get("name"): c.get("value") for c in cookies if isinstance(c, dict) and c.get("name")}
    sso = ck_dict.get("sso", "")
    if not sso:
        return {"ok": False}
    account_hash = "gr:" + hashlib.sha1(sso.encode("utf-8")).hexdigest()[:16]
    _presence.register(account_hash)
    _presence.set_session(account_hash, {"cookies": cookies})
    return {"ok": True}


def add_session_listener(fn) -> None:
    _presence.add_session_listener(fn)
