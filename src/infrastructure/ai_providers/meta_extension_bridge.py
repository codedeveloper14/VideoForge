import base64
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from src.utils.logger import get_logger

logger = get_logger(__name__)

_NoOpLog: Callable[[str], None] = lambda msg: None

_TAB_STALE_S = 300  # segundos sin poll -> tab considerada desconectada (5 min)
_BRIDGE_SILENCE_TTL = 100  # segundos sin ningun poll -> SW crash confirmado -> re-queue

_LOGIN_URL_PATTERNS = (
    "facebook.com/login", "facebook.com/auth", "accounts.google.com",
    "accounts.facebook.com", "login.facebook.com", "meta.ai/login",
    "meta.ai/signup", "meta.ai/auth",
)


class MetaExtensionBridge:
    """Cola en memoria compartida entre el batch worker (productor) y el
    content script de la extension (consumidor via polling HTTP).

    Flujo: Flask encola un job -> la extension hace polling y lo recoge ->
    manipula el DOM en la pestana real de meta.ai -> devuelve la URL del
    video -> Flask la descarga. Cero Playwright, cero navegadores extra.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._queue: list[dict] = []
        self._results: dict[str, dict] = {}
        self._events: dict[str, threading.Event] = {}
        self._inflight: dict[str, dict] = {}
        self._tabs: dict[str, dict] = {}
        self.desired_slots = 4
        self._last_poll = 0.0
        self._last_login_warn = 0.0
        self.batch_id = 0

    def reset_for_new_batch(self, slots: int) -> None:
        self.desired_slots = max(1, slots)
        self.batch_id = int(time.time())
        with self._lock:
            self._queue.clear()
            self._events.clear()
            self._results.clear()
            self._inflight.clear()

    def connected(self) -> list[str]:
        """Todas las tabs registradas en los ultimos 5 min (incluye las en login)."""
        now = time.time()
        with self._lock:
            stale = [h for h, v in self._tabs.items() if now - v.get("ts", 0) > _TAB_STALE_S]
            for h in stale:
                del self._tabs[h]
            return list(self._tabs.keys())

    @staticmethod
    def is_ready_url(url: str) -> bool:
        """True si la tab esta en una URL donde puede generar (cualquier meta.ai
        que no sea login/auth explicito). URL vacia = bridge antiguo, asumir lista."""
        if not url:
            return True
        url_lower = url.lower()
        if any(pat in url_lower for pat in _LOGIN_URL_PATTERNS):
            return False
        return "meta.ai" in url_lower

    def create_tabs(self) -> list[str]:
        """Tabs listas para recibir trabajo (excluye las que estan en login)."""
        now = time.time()
        with self._lock:
            return [
                h for h, v in self._tabs.items()
                if now - v.get("ts", 0) <= _TAB_STALE_S and self.is_ready_url(v.get("url", ""))
            ]

    def register(self, account: str, tab_url: str) -> dict:
        if account:
            with self._lock:
                prev = self._tabs.get(account, {})
                self._tabs[account] = {"ts": time.time(), "url": tab_url or prev.get("url", "")}
        return {"ok": True, "account": account, "max_concurrent": self.desired_slots, "batch_id": self.batch_id}

    def poll(self, account: str, tab_url: str, max_take: int, log: Callable[[str], None] = _NoOpLog) -> dict:
        now = time.time()
        prev_poll_time = self._last_poll
        bridge_silence = now - prev_poll_time
        requeued: list[dict] = []

        with self._lock:
            self._last_poll = now
            if account:
                prev = self._tabs.get(account, {})
                self._tabs[account] = {"ts": now, "url": tab_url or prev.get("url", "")}

            if bridge_silence > _BRIDGE_SILENCE_TTL and self._inflight:
                for rid, info in list(self._inflight.items()):
                    if rid not in self._results and rid in self._events:
                        requeued.append(info["job"])
                        del self._inflight[rid]
                if requeued:
                    self._queue[:] = requeued + self._queue

            total_pending = len(self._queue)
            stored_url = self._tabs.get(account, {}).get("url", "")
            on_login_page = bool(stored_url and not self.is_ready_url(stored_url))

            if on_login_page:
                to_send = []
                if now - self._last_login_warn >= 30:
                    self._last_login_warn = now
                    log(f"[WARNING] ext-poll: on_login_page - acct={account[:8] if account else '?'} "
                        f"url={stored_url[:80] if stored_url else '(vacia)'} --> jobs bloqueados")
            else:
                remaining, to_send = [], []
                for r in self._queue:
                    acct_match = (not r.get("account_hash")) or (not account) or r["account_hash"] == account
                    if len(to_send) < max_take and acct_match:
                        to_send.append(r)
                    else:
                        remaining.append(r)
                self._queue[:] = remaining
                for r in to_send:
                    self._inflight[r["requestId"]] = {"job": r, "ts": now}
                if to_send:
                    log(f"ext-poll: despachando {len(to_send)} job(s) --> cola={len(remaining)}")
                if max_take == 0 and total_pending > 0:
                    log(f"[WARNING] ext-poll: max_take=0 - bridge al limite, {total_pending} en cola")

        if requeued:
            log(f"Re-encolados {len(requeued)} jobs (bridge silent {bridge_silence:.0f}s > "
                f"{_BRIDGE_SILENCE_TTL}s) --> cola={total_pending}")

        response = {
            "requests": to_send, "request": to_send[0] if to_send else None,
            "total_pending": total_pending, "max_concurrent": self.desired_slots, "batch_id": self.batch_id,
        }
        if on_login_page:
            response["on_login_page"] = True
        return response

    def post_result(self, request_id: str, url: str | None, error: str | None,
                     log: Callable[[str], None] = _NoOpLog) -> None:
        if not request_id:
            return
        with self._lock:
            self._results[request_id] = {"url": url or None, "error": error or None}
            ev = self._events.get(request_id)
            self._inflight.pop(request_id, None)
        if ev:
            ev.set()
        log(f"Ext resultado: {request_id[:8]}... url={str(url or '')[:60]}")

    def enqueue_job(self, image_path: str, prompt: str, account_hash: str = "") -> tuple[str, threading.Event]:
        """Codifica la imagen en base64 y encola un job. Devuelve (request_id, event)."""
        rid = str(uuid.uuid4())
        ev = threading.Event()
        image_b64 = ""
        filename = "image.jpg"
        if image_path and Path(image_path).is_file():
            raw = Path(image_path).read_bytes()
            filename = Path(image_path).name
            mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
            image_b64 = f"data:{mime};base64," + base64.b64encode(raw).decode()
        req = {"requestId": rid, "image_b64": image_b64, "prompt": prompt,
               "filename": filename, "account_hash": account_hash or ""}
        with self._lock:
            self._events[rid] = ev
            self._queue.append(req)
        return rid, ev

    def pop_result(self, request_id: str) -> dict | None:
        with self._lock:
            result = self._results.pop(request_id, None)
            self._events.pop(request_id, None)
            return result

    def is_still_queued(self, request_id: str) -> bool:
        with self._lock:
            return any(r["requestId"] == request_id for r in self._queue)

    def cancel_job(self, request_id: str) -> None:
        with self._lock:
            self._queue[:] = [r for r in self._queue if r["requestId"] != request_id]
            self._events.pop(request_id, None)
            self._inflight.pop(request_id, None)

    def clear_pending_queue(self) -> int:
        """Vacia la cola de jobs no despachados aun (no toca los eventos ya en
        vuelo -- esos colectores siguen vivos esperando su resultado)."""
        with self._lock:
            cleared = len(self._queue)
            self._queue.clear()
            self._inflight.clear()
            return cleared

    def generate_blocking(self, image_path: str, prompt: str, account_hash: str | None = None,
                           timeout_sec: int = 300, slot_id: int = 0, cancel_ev=None,
                           log: Callable[[str], None] = _NoOpLog) -> dict:
        """Encola un job y bloquea hasta que la extension responda, timeout, o cancelacion."""
        rid, ev = self.enqueue_job(image_path, prompt, account_hash or "")
        log(f"[S{slot_id}] Ext bridge --> {Path(image_path).name if image_path else '?'}")

        deadline = time.time() + timeout_sec
        while not ev.wait(timeout=1.0):
            if cancel_ev and cancel_ev.is_set():
                self.cancel_job(rid)
                return {"url": None, "error": "Cancelado"}
            if time.time() >= deadline:
                self.cancel_job(rid)
                return {"url": None, "error": "Timeout: extension no respondio"}
        return self.pop_result(rid) or {}

    @staticmethod
    def cors(response):
        """Headers CORS necesarios para que www.meta.ai llame a 127.0.0.1.
        Access-Control-Allow-Private-Network es requerido desde Chrome ~98 (PNA policy)."""
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Access-Control-Request-Private-Network"
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response
