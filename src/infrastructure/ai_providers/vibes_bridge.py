"""Cola en memoria para la generacion de video en vibes.ai, consultada por polling
HTTP normal a traves del MISMO puerto Flask que sirve el resto de la app (igual que
meta_bridge.js hace con /api/meta/ext-poll) -- nada de servidores WebSocket o HTTP
aparte. Un intento anterior con un servidor WS/HTTP dedicado en puertos propios
(5560/5561) resulto poco confiable (handshakes que se cuelgan, puertos zombie de
corridas previas) -- el patron de Meta, reusando el Flask ya activo, es el que de
verdad funciona en este entorno.

Delega en AccountPresenceBridge (ver account_presence_bridge.py) -- este modulo solo
expone wrappers con el mismo nombre/firma que antes, para no tocar ningun caller."""

from src.infrastructure.ai_providers.account_presence_bridge import AccountPresenceBridge

_SEEN_TTL = 30.0

_presence = AccountPresenceBridge(seen_ttl=_SEEN_TTL, queue_account_field="account", queue_account_default="default")


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
