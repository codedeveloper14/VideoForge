"""Presencia de cuenta + cola de jobs compartida entre los bridges de extension de
Chrome (Flow, Qwen, Vibes, y los nuevos de GenTube/Grok). Extrae el patron que antes
estaba triplicado casi caracter por caracter en flow_bridge.py (parte HTTP),
qwen_bridge.py y vibes_bridge.py: una cola en memoria de jobs pendientes, un mapa de
"visto hace poco" con TTL para saber que cuentas estan conectadas, y (para los modulos
que lo necesitan) una cache de sesion con metadata + listeners para avisar en cuanto
llega una sesion nueva.

Cada proveedor instancia SU PROPIA AccountPresenceBridge -- no hay estado compartido
entre proveedores, cada uno calibra su TTL segun el intervalo real de su content
script/alarm."""

import threading
import time
from typing import Callable


class AccountPresenceBridge:
    def __init__(
        self,
        seen_ttl: float = 30.0,
        queue_account_field: str = "account",
        queue_account_default: str = "",
    ):
        self._seen_ttl = seen_ttl
        self._queue_account_field = queue_account_field
        self._queue_account_default = queue_account_default

        self._queue: list[dict] = []
        self._q_lock = threading.Lock()

        self._results: dict[str, dict] = {}
        self._r_lock = threading.Lock()
        self._r_events: dict[str, threading.Event] = {}

        self._seen: dict[str, float] = {}
        self._seen_lock = threading.Lock()

        self._sessions: dict[str, dict] = {}
        self._sessions_lock = threading.Lock()

        self._listeners: list[Callable[[str, dict], None]] = []

    # ---- presencia ----

    def register(self, account: str) -> None:
        if account:
            with self._seen_lock:
                self._seen[account] = time.time()

    def connected_accounts(self) -> list[str]:
        now = time.time()
        with self._seen_lock:
            stale = [a for a, t in self._seen.items() if now - t > self._seen_ttl]
            for a in stale:
                del self._seen[a]
            return list(self._seen.keys())

    def forget(self, account: str) -> None:
        with self._seen_lock:
            self._seen.pop(account, None)

    # ---- cola de jobs ----

    def enqueue_request(self, request_data: dict) -> None:
        with self._q_lock:
            self._queue.append(request_data)

    def take(self, account: str, max_take: int = 1) -> list[dict]:
        """Extrae hasta max_take jobs de la cola para `account`, sin marcar
        presencia (a diferencia de poll()). `account` vacio matchea cualquiera."""
        field = self._queue_account_field
        default = self._queue_account_default
        with self._q_lock:
            taken, remaining = [], []
            for r in self._queue:
                if len(taken) < max_take and (not account or r.get(field, default) == account):
                    taken.append(r)
                else:
                    remaining.append(r)
            self._queue[:] = remaining
        return taken

    def poll(self, account: str, max_take: int = 1) -> list[dict]:
        """Conveniencia usada por Qwen/Vibes: registra presencia y extrae jobs
        en un solo paso."""
        self.register(account)
        return self.take(account, max_take)

    def remove_from_queue(self, request_id: str) -> None:
        with self._q_lock:
            self._queue[:] = [r for r in self._queue if r.get("requestId") != request_id]

    def clear_queue_for_account(self, account: str) -> None:
        field = self._queue_account_field
        with self._q_lock:
            self._queue[:] = [r for r in self._queue if r.get(field) != account]

    def clear_queue(self) -> None:
        with self._q_lock:
            self._queue.clear()

    def queue_length(self) -> int:
        with self._q_lock:
            return len(self._queue)

    # ---- resultados ----

    def register_result_waiter(self, request_id: str) -> threading.Event:
        event = threading.Event()
        with self._r_lock:
            self._r_events[request_id] = event
        return event

    def post_result(self, request_id: str, payload: dict) -> None:
        if not request_id:
            return
        with self._r_lock:
            self._results[request_id] = payload
            ev = self._r_events.get(request_id)
        if ev:
            ev.set()

    def try_pop_result(self, request_id: str) -> dict | None:
        with self._r_lock:
            return self._results.pop(request_id, None)

    def cleanup_waiter(self, request_id: str) -> None:
        with self._r_lock:
            self._r_events.pop(request_id, None)
            self._results.pop(request_id, None)

    # ---- sesion con metadata (bearer/cookies/email) + listeners ----
    # Generaliza el patron _bearer_cache + _session_listeners de flow_bridge.py,
    # para que los bridges nuevos (GenTube, Grok) no tengan que reimplementarlo.

    def set_session(self, account_key: str, meta: dict, session_ttl: float = 600.0) -> None:
        with self._sessions_lock:
            self._sessions[account_key] = {"meta": dict(meta), "ts": time.time(), "ttl": session_ttl}
        for fn in list(self._listeners):
            try:
                fn(account_key, dict(meta))
            except Exception:
                pass

    def get_session(self, account_key: str) -> dict | None:
        with self._sessions_lock:
            entry = self._sessions.get(account_key)
            return dict(entry["meta"]) if entry else None

    def session_keys(self, fresh_only: bool = True) -> set[str]:
        now = time.time()
        with self._sessions_lock:
            if not fresh_only:
                return set(self._sessions.keys())
            return {k for k, e in self._sessions.items() if now - e["ts"] < e["ttl"]}

    def add_session_listener(self, fn: Callable[[str, dict], None]) -> None:
        self._listeners.append(fn)
