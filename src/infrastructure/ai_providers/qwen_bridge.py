"""Cola en memoria para create_chat/submit_completion en chat.qwen.ai, consultada por
polling HTTP normal a traves del MISMO puerto Flask que sirve el resto de la app --
mismo patron que vibes_bridge.py (nada de servidores WebSocket o HTTP aparte).

A diferencia de Vibes (una sola sesion, account="default" fijo), cada cuenta Qwen
corre en su PROPIO proceso de Chromium (perfil propio, extension propia) -- por
eso `account` acá es siempre el nombre real de la cuenta (account_1, account_2, ...)
en vez de un valor fijo, y varias cuentas pueden estar conectadas en simultaneo sin
que hagan falta mapas cuenta->tab (eso ya lo resuelve tener un proceso por cuenta)."""

import threading
import time

_queue: list[dict] = []
_q_lock = threading.Lock()
_results: dict[str, dict] = {}
_r_lock = threading.Lock()
_r_events: dict[str, threading.Event] = {}

_seen: dict[str, float] = {}
_seen_lock = threading.Lock()
_SEEN_TTL = 30.0


def connected_accounts() -> list[str]:
    now = time.time()
    with _seen_lock:
        stale = [a for a, t in _seen.items() if now - t > _SEEN_TTL]
        for a in stale:
            del _seen[a]
        return list(_seen.keys())


def register(account: str) -> None:
    if account:
        with _seen_lock:
            _seen[account] = time.time()


def enqueue_request(request_data: dict) -> None:
    with _q_lock:
        _queue.append(request_data)


def poll(account: str, max_take: int = 1) -> list[dict]:
    register(account)
    with _q_lock:
        taken, remaining = [], []
        for r in _queue:
            if len(taken) < max_take and (not account or r.get("account", "") == account):
                taken.append(r)
            else:
                remaining.append(r)
        _queue[:] = remaining
    return taken


def remove_from_queue(request_id: str) -> None:
    with _q_lock:
        _queue[:] = [r for r in _queue if r.get("requestId") != request_id]


def register_result_waiter(request_id: str) -> threading.Event:
    event = threading.Event()
    with _r_lock:
        _r_events[request_id] = event
    return event


def post_result(request_id: str, payload: dict) -> None:
    if not request_id:
        return
    with _r_lock:
        _results[request_id] = payload
        ev = _r_events.get(request_id)
    if ev:
        ev.set()


def try_pop_result(request_id: str) -> dict | None:
    with _r_lock:
        return _results.pop(request_id, None)


def cleanup_waiter(request_id: str) -> None:
    with _r_lock:
        _r_events.pop(request_id, None)
        _results.pop(request_id, None)
