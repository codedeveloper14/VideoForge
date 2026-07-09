"""El bridge de comunicacion con la extension de Chrome para Flow: un servidor
WebSocket (5557, preferido) y un servidor HTTP crudo de polling (5556, fallback para
cuando el service worker de la extension no puede sostener una conexion WS, p. ej. en
un .exe compilado sin la lib `websockets`). Ambos hablan el mismo protocolo de cola de
requests + resultados que consume el motor de generacion (ver flow_animation_service)."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BRIDGE_PORT = 5556
WS_PORT = 5557

_CORS_ALLOWED_ORIGINS = ("https://labs.google", "https://aistudio.google.com", "https://gemini.google.com")
_HTTP_SEEN_TTL = 60.0

_started = {"bridge": False, "ws": False}
_bind_ok = {"bridge": False, "ws": False}

_bridge_queue: list[dict] = []
_bridge_q_lock = threading.Lock()
_bridge_results: dict[str, dict] = {}
_bridge_r_lock = threading.Lock()
_bridge_r_events: dict[str, threading.Event] = {}

_ws_clients: dict[str, object] = {}
_ws_clients_lock = threading.Lock()

_http_seen: dict[str, float] = {}
_http_seen_lock = threading.Lock()

# La extension envia su bearer fresco al registrarse: {account_hash: {"bearer","ts"}}
_bearer_cache: dict[str, dict] = {}
_bearer_cache_lock = threading.Lock()


def get_cached_bearer(account_hash: str) -> str:
    with _bearer_cache_lock:
        entry = _bearer_cache.get(account_hash)
        return entry["bearer"] if entry else ""


def set_cached_bearer(account_hash: str, bearer: str) -> None:
    with _bearer_cache_lock:
        _bearer_cache[account_hash] = {"bearer": bearer, "ts": time.time()}


def get_connected_accounts() -> list[str]:
    with _ws_clients_lock:
        ws_accounts = set(_ws_clients.keys())
    now = time.time()
    with _http_seen_lock:
        stale = [a for a, t in _http_seen.items() if now - t > _HTTP_SEEN_TTL]
        for a in stale:
            del _http_seen[a]
        http_accounts = set(_http_seen.keys())
    # Cuentas con bearer reciente en cache (<=10 min) tambien cuentan como conectadas,
    # aunque el service worker haya muerto y ya no se rastreen por WS/HTTP.
    with _bearer_cache_lock:
        bearer_accounts = {h for h, e in _bearer_cache.items() if e.get("bearer") and now - e.get("ts", 0) < 600}
    return list(ws_accounts | http_accounts | bearer_accounts)


def ws_push(account_hash: str, request_data: dict) -> bool:
    with _ws_clients_lock:
        ws = _ws_clients.get(account_hash)
    if not ws:
        return False
    try:
        ws.send(json.dumps({"type": "generate", "requests": [request_data]}))
        return True
    except Exception:
        with _ws_clients_lock:
            if _ws_clients.get(account_hash) is ws:
                del _ws_clients[account_hash]
        return False


def ws_drain_queue(account_hash: str) -> None:
    with _bridge_q_lock:
        remaining, to_send = [], []
        for r in _bridge_queue:
            if r.get("account_hash", "") == account_hash and len(to_send) < 10:
                to_send.append(r)
            else:
                remaining.append(r)
        _bridge_queue[:] = remaining
    for req in to_send:
        ws_push(account_hash, req)


def enqueue_request(request_data: dict) -> None:
    with _bridge_q_lock:
        _bridge_queue.append(request_data)


def remove_from_queue(request_id: str) -> None:
    with _bridge_q_lock:
        _bridge_queue[:] = [r for r in _bridge_queue if r.get("requestId") != request_id]


def clear_queue_for_account(account_hash: str) -> None:
    with _bridge_q_lock:
        _bridge_queue[:] = [r for r in _bridge_queue if r.get("account_hash") != account_hash]


def clear_queue() -> None:
    with _bridge_q_lock:
        _bridge_queue.clear()


def get_ws_clients() -> dict:
    with _ws_clients_lock:
        return dict(_ws_clients)


def remove_ws_client(account_hash: str) -> None:
    with _ws_clients_lock:
        _ws_clients.pop(account_hash, None)


def get_http_seen_accounts() -> set[str]:
    now = time.time()
    with _http_seen_lock:
        stale = [a for a, t in _http_seen.items() if now - t > _HTTP_SEEN_TTL]
        for a in stale:
            del _http_seen[a]
        return set(_http_seen.keys())


def remove_http_seen(account_hash: str) -> None:
    with _http_seen_lock:
        _http_seen.pop(account_hash, None)


def get_bearer_cache_hashes() -> set[str]:
    """Hashes con bearer en cache, sin filtrar por antiguedad (a diferencia de
    get_connected_accounts, que solo cuenta bearers de los ultimos 10 min)."""
    with _bearer_cache_lock:
        return {h for h, e in _bearer_cache.items() if e.get("bearer")}


def register_result_waiter(request_id: str) -> threading.Event:
    event = threading.Event()
    with _bridge_r_lock:
        _bridge_r_events[request_id] = event
    return event


def try_pop_result(request_id: str) -> dict | None:
    """No bloqueante: devuelve el resultado si ya llego, sin tocar el waiter (el
    llamador sigue esperando en su propio Event hasta el timeout)."""
    with _bridge_r_lock:
        return _bridge_results.pop(request_id, None)


def cleanup_waiter(request_id: str) -> None:
    with _bridge_r_lock:
        _bridge_r_events.pop(request_id, None)
        _bridge_results.pop(request_id, None)


def status() -> dict:
    with _bridge_q_lock:
        pending = len(_bridge_queue)
    with _ws_clients_lock:
        ws_clients = list(_ws_clients.keys())
    return {
        "pending": pending, "ws_clients": ws_clients,
        "bridge_port": BRIDGE_PORT, "ws_port": WS_PORT,
        "bridge_ok": _bind_ok["bridge"], "ws_ok": _bind_ok["ws"],
    }


def start_ws_server(log) -> None:
    if _started["ws"]:
        return
    _started["ws"] = True
    try:
        import websockets.sync.server as ws_sync
    except ImportError:
        log("[Flow] websockets no instalado - WebSocket desactivado.")
        return

    def _handler(ws):
        account_hash = None
        log("[Flow] WS: cliente conectado")
        try:
            for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                t = msg.get("type", "")
                if t == "register":
                    account_hash = msg.get("account_hash", "")
                    if account_hash:
                        with _ws_clients_lock:
                            _ws_clients[account_hash] = ws
                        bearer_from_ext = msg.get("bearer", "")
                        if bearer_from_ext:
                            set_cached_bearer(account_hash, bearer_from_ext)
                            log(f"[Flow] WS: cuenta registrada {account_hash} (bearer OK)")
                            ws_drain_queue(account_hash)
                        else:
                            log(f"[Flow] WS: cuenta registrada {account_hash} (sin bearer)")
                elif t == "result":
                    rid = msg.get("requestId", "")
                    if rid:
                        with _bridge_r_lock:
                            _bridge_results[rid] = msg
                            ev = _bridge_r_events.get(rid)
                        if ev:
                            ev.set()
                        log(f"[Flow] WS: resultado recibido {rid[:12]}... status={msg.get('status', '?')}")
                elif t == "token_ready":
                    pass
        except Exception as exc:
            log(f"[Flow] WS: cliente desconectado: {exc}")
        finally:
            if account_hash:
                with _ws_clients_lock:
                    if _ws_clients.get(account_hash) is ws:
                        del _ws_clients[account_hash]
                log(f"[Flow] WS: cuenta desregistrada {account_hash}")

    def _run():
        try:
            server = ws_sync.serve(_handler, "0.0.0.0", WS_PORT, ping_interval=None)
            _bind_ok["ws"] = True
            log(f"[Flow] WebSocket server en puerto {WS_PORT}")
            server.serve_forever()
        except OSError as exc:
            _bind_ok["ws"] = False
            if "address already in use" in str(exc).lower() or "10048" in str(exc):
                log(f"[Flow] WS puerto {WS_PORT} ya en uso (instancia previa activa)")
            else:
                log(f"[Flow] WS no pudo iniciar: {exc}")

    threading.Thread(target=_run, daemon=True).start()
    time.sleep(0.3)


def _cors_headers(handler: BaseHTTPRequestHandler) -> None:
    origin = handler.headers.get("Origin", "") if hasattr(handler, "headers") else ""
    if origin and any(origin == o or origin.endswith("." + o.split("//")[1]) for o in _CORS_ALLOWED_ORIGINS):
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Access-Control-Allow-Credentials", "true")
        handler.send_header("Vary", "Origin")
    else:
        handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Access-Control-Request-Private-Network")
    handler.send_header("Access-Control-Allow-Private-Network", "true")


def start_bridge(log) -> None:
    if _started["bridge"]:
        return
    _started["bridge"] = True

    class _Handler(BaseHTTPRequestHandler):
        def _json_resp(self, code, data):
            body = json.dumps(data).encode()
            self.send_response(code)
            _cors_headers(self)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self):
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n)) if n else {}

        def do_OPTIONS(self):
            self.send_response(204)
            _cors_headers(self)
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            account = qs.get("account", [""])[0]

            if account:
                with _http_seen_lock:
                    _http_seen[account] = time.time()

            if parsed.path == "/health":
                self._json_resp(200, {"ok": True})
                return

            if parsed.path.startswith("/flow-register"):
                if account:
                    log(f"[Flow] Bridge: cuenta registrada via HTTP: {account}")
                self._json_resp(200, {"ok": True, "account": account})
                return

            if parsed.path in ("/flow-generate-poll", "/flow-bridge-status"):
                reqs = []
                with _bridge_q_lock:
                    remaining = []
                    for r in _bridge_queue:
                        if len(reqs) < 10 and (not account or r.get("account_hash", "") == account):
                            reqs.append(r)
                        else:
                            remaining.append(r)
                    _bridge_queue[:] = remaining

                if parsed.path == "/flow-bridge-status":
                    self._json_resp(200, status())
                else:
                    self._json_resp(200, {"requests": reqs, "request": reqs[0] if reqs else None})
                return

            self._json_resp(404, {"error": "not found"})

        def do_POST(self):
            if self.path == "/flow-generate-result":
                try:
                    body = self._read_body()
                    rid = body.get("requestId", "")
                    if rid:
                        with _bridge_r_lock:
                            _bridge_results[rid] = body
                            ev = _bridge_r_events.get(rid)
                        if ev:
                            ev.set()
                        log(f"[Flow] Bridge: resultado recibido {rid[:12]}... status={body.get('status', '?')}")
                    self._json_resp(200, {"ok": True})
                except Exception:
                    self._json_resp(400, {"ok": False})
            elif self.path == "/flow-register-bearer":
                try:
                    body = self._read_body()
                    account = body.get("account", "")
                    bearer = body.get("bearer", "")
                    if account and bearer:
                        set_cached_bearer(account, bearer)
                        log(f"[Flow] Bearer recibido de extension: {account[:8]}...")
                    self._json_resp(200, {"ok": True})
                except Exception:
                    self._json_resp(400, {"ok": False})
            elif self.path == "/flow-reset-fingerprint":
                # Deshabilitado: borrar cookies de auth de Google causa 403 en loop.
                # Solo acusar recibo para que la extension no falle.
                try:
                    self._read_body()
                except Exception:
                    pass
                self._json_resp(200, {"ok": True, "reset": []})
            else:
                self._json_resp(404, {"error": "not found"})

        def log_message(self, *args):
            pass

    try:
        srv = ThreadingHTTPServer(("0.0.0.0", BRIDGE_PORT), _Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _bind_ok["bridge"] = True
        log(f"[Flow] Bridge HTTP en puerto {BRIDGE_PORT}")
    except OSError as exc:
        if "10048" in str(exc) or "address already in use" in str(exc).lower():
            _bind_ok["bridge"] = True
            log(f"[Flow] Bridge HTTP ya activo en puerto {BRIDGE_PORT}")
        else:
            _bind_ok["bridge"] = False
            log(f"[Flow] Bridge HTTP no pudo iniciar: {exc}")

    start_ws_server(log)
