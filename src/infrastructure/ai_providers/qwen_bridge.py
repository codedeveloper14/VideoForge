"""Cola en memoria para create_chat/submit_completion en chat.qwen.ai, consultada por
polling HTTP normal a traves del MISMO puerto Flask que sirve el resto de la app --
mismo patron que vibes_bridge.py (nada de servidores WebSocket o HTTP aparte).

A diferencia de Vibes (una sola sesion, account="default" fijo), cada cuenta Qwen
corre en su PROPIO proceso de Chromium (perfil propio, extension propia) -- por
eso `account` acá es siempre el nombre real de la cuenta (account_1, account_2, ...)
en vez de un valor fijo, y varias cuentas pueden estar conectadas en simultaneo sin
que hagan falta mapas cuenta->tab (eso ya lo resuelve tener un proceso por cuenta).

Delega en AccountPresenceBridge (ver account_presence_bridge.py) -- este modulo solo
expone wrappers con el mismo nombre/firma que antes, para no tocar ningun caller."""

from src.infrastructure.ai_providers.account_presence_bridge import AccountPresenceBridge

_SEEN_TTL = 30.0

_presence = AccountPresenceBridge(seen_ttl=_SEEN_TTL)


def connected_accounts() -> list[str]:
    return _presence.connected_accounts()


def register(account: str) -> None:
    _presence.register(account)


def enqueue_request(request_data: dict) -> None:
    _presence.enqueue_request(request_data)


def poll(account: str, max_take: int = 1) -> list[dict]:
    return _presence.poll(account, max_take)


def remove_from_queue(request_id: str) -> None:
    _presence.remove_from_queue(request_id)


def register_result_waiter(request_id: str):
    return _presence.register_result_waiter(request_id)


def post_result(request_id: str, payload: dict) -> None:
    _presence.post_result(request_id, payload)


def try_pop_result(request_id: str) -> dict | None:
    return _presence.try_pop_result(request_id)


def cleanup_waiter(request_id: str) -> None:
    _presence.cleanup_waiter(request_id)
