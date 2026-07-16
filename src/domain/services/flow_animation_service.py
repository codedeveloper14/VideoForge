"""Orquestacion de Flow: estado compartido + cuentas/cookies (Etapa A), bridge WS/HTTP
(Etapa B, en flow_bridge.py) y el motor de generacion por lotes + ciclo de vida de
Chromium (Etapa C, este modulo)."""

import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Empty, Queue

import requests

from src.infrastructure.ai_providers import flow_bridge, flow_browser, flow_service
from src.infrastructure.ai_providers.openrouter_client import sanitize_prompt
from src.utils.logger import get_logger
from src.utils.paths import get_flow_profiles_dir
from src.utils.platform_utils import open_folder

logger = get_logger(__name__)

state = {
    "running": False,
    "step": "idle",
    "progress": 0,
    "total": 0,
    "images_saved": 0,
    "log": [],
    "last_error": None,
    "output_dir": None,
    "started_at": 0.0,
    "accounts": [
        {"index": i, "ok": False, "email": None, "jobs": 0} for i in range(flow_service.NUM_ACCOUNTS)
    ],
}
lock = threading.Lock()

# Salvavidas: si un batch se cuelga (red caida, browser sin responder, etc.) sin
# levantar excepcion, "running" quedaria en True para siempre y el usuario nunca
# podria reintentar. Se libera solo tras este tope, sin necesidad de "Detener".
MAX_RUN_SECONDS = 1800


def _release_if_stale() -> None:
    went_stale = False
    with lock:
        started = state.get("started_at") or 0.0
        if state["running"] and started and (time.time() - started) > MAX_RUN_SECONDS:
            state.update(running=False, step="idle", last_error="Tiempo de espera agotado")
            _stop_event.set()
            went_stale = True
    if went_stale:
        log("[Flow] Lock de generacion liberado automaticamente por timeout")


def log(msg: str) -> None:
    with lock:
        state["log"].append(msg)
        if len(state["log"]) > 600:
            state["log"] = state["log"][-600:]
    logger.info("[flow] %s", msg)


def save_account_cookie(idx: int, cookie: str) -> dict:
    idx = max(0, min(idx, flow_service.NUM_ACCOUNTS - 1))
    cookie = (cookie or "").strip()
    if not cookie:
        raise ValueError("cookie vacio")

    # Validar ANTES de guardar -- una cookie invalida no debe pisar una cookie
    # buena que ya estuviera guardada para esta cuenta.
    sess = flow_service.get_session(cookie)
    email = sess.get("email", "")
    ok = bool(sess.get("bearer", ""))
    if not ok:
        return {"ok": False, "error": "Cookie invalida o sesion expirada"}

    flow_service.save_cookie(idx, cookie)
    acc_hash = flow_service.account_hash(email)
    with lock:
        state["accounts"][idx].update({"ok": True, "email": email})
    return {"ok": True, "email": email, "hash": acc_hash}


def check_accounts() -> list[dict]:
    def _check_one(i):
        ck = flow_service.load_cookie(i)
        acc = {"index": i, "ok": False, "email": None, "cookie": bool(ck)}
        if not ck:
            return i, acc
        sess = flow_service.get_session(ck)
        bearer = sess.get("bearer", "")
        email = sess.get("email", "") or f"Cuenta {i + 1}"
        if bearer:
            acc["ok"] = True
            acc["email"] = f"{email} ok"
            with lock:
                state["accounts"][i].update({"ok": True, "email": acc["email"]})
        else:
            acc["ok"] = False
            acc["email"] = f"Cuenta {i + 1} - sesion expirada"
            with lock:
                state["accounts"][i].update({"ok": False})
        return i, acc

    result: list[dict | None] = [None] * flow_service.NUM_ACCOUNTS
    with ThreadPoolExecutor(max_workers=flow_service.NUM_ACCOUNTS) as ex:
        for i, acc in ex.map(_check_one, range(flow_service.NUM_ACCOUNTS)):
            result[i] = acc
    return result


def profile_dump(idx: int) -> dict:
    """Diagnostico: lista los archivos del perfil de Chromium de una cuenta."""
    profile_dir = str(get_flow_profiles_dir() / f"flow_profile_{idx}")
    result: dict = {"profile_dir": profile_dir, "files": [], "local_state_keys": []}

    for root, dirs, files in os.walk(profile_dir):
        depth = root.replace(profile_dir, "").count(os.sep)
        if depth > 2:
            dirs.clear()
            continue
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), profile_dir)
            try:
                size = os.path.getsize(os.path.join(root, f))
            except Exception:
                size = 0
            result["files"].append({"path": rel, "size": size})

    ls_path = os.path.join(profile_dir, "Local State")
    if os.path.isfile(ls_path):
        try:
            with open(ls_path, encoding="utf-8") as f:
                ls = json.load(f)
            result["local_state_keys"] = list(ls.keys())
        except Exception:
            pass

    return result


# ═══════════════════════════════════════════════════════════════════
# Etapa C: ciclo de vida de Chromium, rotacion de cuentas, y el motor
# de generacion por lotes.
# ═══════════════════════════════════════════════════════════════════

FLOW_GEN_URL_TPL = "https://aisandbox-pa.googleapis.com/v1/projects/{pid}/flowMedia:batchGenerateImages"

_chromium_procs: dict[int, threading.Thread] = {}
_chromium_lock = threading.Lock()

# Hashes de cuentas lanzadas por Playwright (cargadas de disco). Cuentas NO en este
# set = Chrome real del usuario.
_playwright_hashes: set[str] = set()
_playwright_hashes_lock = threading.Lock()

# Rotacion: active_slots arranca como los primeros N indices, backup_queue el resto.
# Una cuenta con rate-limit persistente se banea 1h y se reemplaza por el siguiente
# backup en la cola.
_active_slots = list(range(flow_service.ACTIVE_SLOTS))
_backup_queue = list(range(flow_service.ACTIVE_SLOTS, flow_service.NUM_ACCOUNTS))
_rotation_lock = threading.Lock()

_rl_hits: dict[str, list[float]] = {}
_rl_lock = threading.Lock()
_RL_WINDOW = 600
_RL_THRESHOLD = 3
_RL_DEBOUNCE = 20

_banned_until: dict[str, float] = {}
_banned_lock = threading.Lock()
_BAN_SECONDS = 3600

# Warmup: perfil recien abierto necesita ~45s antes de recibir generaciones para que
# reCAPTCHA no lo marque como automatizado con score bajo.
_warmup_until_idx: dict[int, float] = {}
_warmup_lock = threading.Lock()
_WARMUP_SECONDS = 45

# Semaforo global de descargas: limita conexiones simultaneas al CDN (flow-content.google
# cierra conexiones SSL cuando hay demasiadas a la vez).
_dl_sem = threading.Semaphore(8)

_stop_event = threading.Event()
_batch_id = 0
_last_batch: dict = {}


def is_banned(account_hash: str) -> bool:
    with _banned_lock:
        return time.time() < _banned_until.get(account_hash, 0.0)


def _close_chromium_by_idx(idx: int) -> None:
    """Termina el proceso Chromium del perfil indicado via psutil."""
    profile_path = str(flow_browser.profile_dir(idx))
    try:
        import psutil

        for p in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmd = " ".join(p.info.get("cmdline") or [])
                if profile_path in cmd and "--type=" not in cmd:
                    p.terminate()
                    log(f"[Flow] Browser perfil {idx + 1} cerrado (PID={p.pid})")
                    break
            except Exception:
                pass
    except ImportError:
        pass
    with _chromium_lock:
        _chromium_procs.pop(idx, None)


def _open_chromium_by_idx(idx: int) -> None:
    """Abre Chromium para el perfil indicado si no esta ya abierto."""
    with _chromium_lock:
        existing = _chromium_procs.get(idx)
        if existing is not None:
            if isinstance(existing, threading.Thread) and existing.is_alive():
                return
            _chromium_procs.pop(idx, None)

    # Marcar este hash como Playwright ahora (cuando realmente va a abrir), no antes
    # (donde correria para todas las cuentas de disco, Chrome real incluido).
    try:
        ck = flow_service.load_cookie(idx)
        if ck:
            sess = flow_service.get_session(ck)
            email = sess.get("email", "")
            if email:
                with _playwright_hashes_lock:
                    _playwright_hashes.add(flow_service.account_hash(email))
    except Exception:
        pass

    def _on_closed():
        with _chromium_lock:
            _chromium_procs.pop(idx, None)

    def _launch():
        try:
            flow_browser.playwright_login(idx, log, _on_closed)
        except Exception as exc:
            log(f"[Flow Acc{idx + 1}] Error auto-open: {exc}")
            with _chromium_lock:
                _chromium_procs.pop(idx, None)

    t = threading.Thread(target=_launch, daemon=True)
    t._flow_created_at = time.time()
    with _chromium_lock:
        _chromium_procs[idx] = t
    t.start()
    with _warmup_lock:
        _warmup_until_idx[idx] = time.time() + _WARMUP_SECONDS
    log(f"[Flow] Abriendo browser perfil {idx + 1} - warmup {_WARMUP_SECONDS}s...")


def rotate_account(account_hash: str, acc_idx: int) -> None:
    """Ban 1h para account_hash, cierra su browser y activa el siguiente backup.
    Seguro para llamar desde multiples workers (solo actua la primera vez)."""
    with _banned_lock:
        if time.time() < _banned_until.get(account_hash, 0.0):
            return
        _banned_until[account_hash] = time.time() + _BAN_SECONDS
    with _rl_lock:
        _rl_hits.pop(account_hash, None)
    log(f"[Flow] ROTACION - perfil {acc_idx + 1} ({account_hash[:8]}) baneado 1h por rate limit persistente")

    def _do_rotate():
        _close_chromium_by_idx(acc_idx)
        # IMPORTANTE: no abrir el browser de respaldo dentro de _rotation_lock
        # (_chromium_lock y _rotation_lock en orden inverso causarian deadlock).
        next_idx = None
        with _rotation_lock:
            if acc_idx in _active_slots:
                _active_slots.remove(acc_idx)
                _backup_queue.append(acc_idx)
            if _backup_queue:
                next_idx = _backup_queue.pop(0)
                _active_slots.append(next_idx)

        if next_idx is not None:
            log(f"[Flow] Activando perfil {next_idx + 1} como reemplazo")
            time.sleep(1.5)
            _open_chromium_by_idx(next_idx)
        else:
            log("[Flow] [WARNING] Sin mas perfiles de respaldo disponibles")

        def _reactivate():
            time.sleep(_BAN_SECONDS)
            with _banned_lock:
                _banned_until.pop(account_hash, None)
            with _rl_lock:
                _rl_hits.pop(account_hash, None)
            reopen = False
            with _rotation_lock:
                if acc_idx in _backup_queue:
                    _backup_queue.remove(acc_idx)
                if len(_active_slots) < flow_service.ACTIVE_SLOTS:
                    _active_slots.append(acc_idx)
                    reopen = True
                else:
                    _backup_queue.insert(0, acc_idx)
            if reopen:
                log(f"[Flow] Perfil {acc_idx + 1} reactivado tras 1h de ban")
                _open_chromium_by_idx(acc_idx)
            else:
                log(f"[Flow] Perfil {acc_idx + 1} regresa a respaldo (slots activos llenos)")

        threading.Thread(target=_reactivate, daemon=True).start()

    threading.Thread(target=_do_rotate, daemon=True).start()


def record_rl_hit(account_hash: str, acc_idx: int) -> bool:
    """Registra un hit de rate-limit con debounce por cuenta. Devuelve True si se
    activo rotacion (rate limit persistente detectado)."""
    now = time.time()
    with _rl_lock:
        hits = _rl_hits.setdefault(account_hash, [])
        if hits and now - hits[-1] < _RL_DEBOUNCE:
            return False
        hits.append(now)
        _rl_hits[account_hash] = [t for t in hits if t > now - _RL_WINDOW]
        count = len(_rl_hits[account_hash])

    if count >= _RL_THRESHOLD and not is_banned(account_hash):
        log(
            f"[Flow] [WARNING] Perfil {acc_idx + 1}: {count} rate limits en {_RL_WINDOW // 60}min --> rotacion"
        )
        rotate_account(account_hash, acc_idx)
        return True
    return False


def auto_open_browsers() -> None:
    """Abre Chromium para todos los slots activos que tengan cookie. Si ya hay
    Chrome real conectado (via el bridge), no abre Playwright en absoluto."""
    connected_all = set(flow_bridge.get_connected_accounts())
    with _playwright_hashes_lock:
        pw_hashes = set(_playwright_hashes)
    # Cuentas activas via extension Chrome (HTTP) son Chrome real aunque antes hayan
    # sido abiertas con Playwright -- quitar del set Playwright para detectarlas bien.
    pw_hashes -= flow_bridge.get_http_seen_accounts()
    real_hashes = connected_all - pw_hashes
    if real_hashes:
        log(f"[Flow] [OK] Chrome real conectado ({len(real_hashes)} cuenta(s)) - Playwright no abrira")
        return

    with _rotation_lock:
        active = list(_active_slots)
    opened = 0
    for idx in active:
        if not flow_service.load_cookie(idx):
            continue
        with _chromium_lock:
            existing = _chromium_procs.get(idx)
            if existing is not None and isinstance(existing, threading.Thread) and existing.is_alive():
                continue
        _open_chromium_by_idx(idx)
        opened += 1
        time.sleep(0.8)  # escalonar aperturas para no saturar el sistema
    if opened:
        log(f"[Flow] Auto-apertura Playwright: {opened} browser(s) iniciados")


def chromium_status() -> list[dict]:
    """Estado de cada perfil -- respuesta instantanea, sin llamadas HTTP."""
    with _chromium_lock:
        dead = []
        for idx, p in _chromium_procs.items():
            if isinstance(p, threading.Thread):
                if not p.is_alive():
                    dead.append(idx)
                else:
                    # Grace period: si el thread lleva <30s creado, Chrome probablemente
                    # sigue arrancando -- confiar en el thread y no escanear con psutil
                    # (evita falsos positivos cuando varios perfiles abren en secuencia).
                    age = time.time() - getattr(p, "_flow_created_at", time.time())
                    if age >= 30:
                        try:
                            import psutil

                            pd_check = str(flow_browser.profile_dir(idx)).lower().replace("\\", "/")
                            proc_alive = any(
                                pd_check in " ".join(px.info.get("cmdline") or []).lower().replace("\\", "/")
                                and "--type=" not in " ".join(px.info.get("cmdline") or [])
                                for px in psutil.process_iter(["pid", "cmdline"])
                            )
                            if not proc_alive:
                                dead.append(idx)
                        except Exception:
                            pass
        for idx in dead:
            _chromium_procs.pop(idx, None)
        open_idxs = set(_chromium_procs.keys())

    connected_hashes = set(flow_bridge.get_ws_clients().keys())

    result = []
    for i in range(flow_service.NUM_ACCOUNTS):
        ck = flow_service.load_cookie(i)
        email = ""
        try:
            with lock:
                raw = state["accounts"][i].get("email") or ""
            email = str(raw).replace(" ok", "").strip()
        except Exception:
            pass

        acc_hash = flow_service.account_hash(email) if email else None
        connected = bool(acc_hash and acc_hash in connected_hashes)
        if not email and ck:
            email = f"Perfil {i + 1} (cookie guardada)"

        with _rotation_lock:
            slot_type = "active" if i in _active_slots else "backup"
        with _banned_lock:
            ban_until = _banned_until.get(acc_hash, 0) if acc_hash else 0
        banned_secs = max(0, int(ban_until - time.time()))

        result.append(
            {
                "index": i,
                "open": i in open_idxs,
                "connected": connected,
                "email": email or f"Perfil {i + 1}",
                "has_cookie": bool(ck),
                "ext_dir": "",
                "slot_type": slot_type,
                "banned_secs": banned_secs,
            }
        )
    return result


def reset_chromium() -> dict:
    """Borra DEFINITIVAMENTE todos los perfiles Chromium/Playwright: mata procesos,
    elimina carpetas de perfil y limpia estado en memoria. No toca las cookies (ni
    las de Flow ni las de la extension de Chrome)."""
    import shutil

    killed: list[int] = []
    deleted: list[str] = []
    errors: list[str] = []

    base_dir = get_flow_profiles_dir()
    try:
        import psutil

        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmd = " ".join(proc.info.get("cmdline") or [])
                if "flow_profile_" in cmd and "--type=" not in cmd:
                    proc.kill()
                    killed.append(proc.info["pid"])
            except Exception:
                pass
    except Exception as exc:
        errors.append(f"psutil: {exc}")

    with _chromium_lock:
        _chromium_procs.clear()
    with _playwright_hashes_lock:
        _playwright_hashes.clear()
    for h in list(flow_bridge.get_ws_clients().keys()):
        flow_bridge.remove_ws_client(h)

    try:
        for item in os.listdir(base_dir):
            if item.startswith("flow_profile_"):
                p = base_dir / item
                try:
                    shutil.rmtree(p)
                    deleted.append(item)
                except Exception as exc:
                    errors.append(f"{item}: {exc}")
    except Exception as exc:
        errors.append(f"listdir: {exc}")

    log(f"[Flow] Reset Chromium: killed={killed} deleted={deleted} errors={errors}")
    return {"ok": True, "killed": killed, "deleted": deleted, "errors": errors}


def reset_chromium_profile(idx: int) -> dict:
    """Borra un perfil Chromium especifico por indice (0-based)."""
    import shutil

    if idx < 0 or idx >= flow_service.NUM_ACCOUNTS:
        raise ValueError("idx invalido")

    profile_path = flow_browser.profile_dir(idx)
    killed: list[int] = []
    errors: list[str] = []

    try:
        import psutil

        tag = f"flow_profile_{idx}"
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmd = " ".join(proc.info.get("cmdline") or [])
                if tag in cmd and "--type=" not in cmd:
                    proc.kill()
                    killed.append(proc.info["pid"])
            except Exception:
                pass
    except Exception as exc:
        errors.append(str(exc))

    with _chromium_lock:
        _chromium_procs.pop(idx, None)
    try:
        ck = flow_service.load_cookie(idx)
        if ck:
            sess = flow_service.get_session(ck)
            email = sess.get("email", "")
            if email:
                h = flow_service.account_hash(email)
                with _playwright_hashes_lock:
                    _playwright_hashes.discard(h)
                flow_bridge.remove_ws_client(h)
    except Exception as exc:
        errors.append(str(exc))

    deleted = False
    if profile_path.is_dir():
        try:
            shutil.rmtree(profile_path)
            deleted = True
        except Exception as exc:
            errors.append(str(exc))

    log(f"[Flow] Reset perfil {idx}: killed={killed} deleted={deleted} errors={errors}")
    return {"ok": True, "idx": idx, "killed": killed, "deleted": deleted, "errors": errors}


def start_login(idx: int) -> dict:
    idx = max(0, min(idx, flow_service.NUM_ACCOUNTS - 1))

    def _launch_with_log():
        try:
            flow_browser.playwright_login(idx, log, lambda: _chromium_procs.pop(idx, None))
        except Exception as exc:
            logger.exception("[Flow Acc%d] error critico al abrir Chromium", idx + 1)
            log(f"[Flow Acc{idx + 1}] Error critico al abrir Chromium: {exc}")
            with _chromium_lock:
                _chromium_procs.pop(idx, None)

    with _chromium_lock:
        existing = _chromium_procs.get(idx)
        if existing is not None:
            if isinstance(existing, threading.Thread) and not existing.is_alive():
                del _chromium_procs[idx]
            else:
                return {"ok": True, "message": f"Perfil {idx + 1} ya esta abierto", "already_open": True}
        t = threading.Thread(target=_launch_with_log, daemon=True)
        t._flow_created_at = time.time()
        _chromium_procs[idx] = t

    t.start()
    return {"ok": True, "message": f"Abriendo Chromium perfil {idx + 1}..."}


def _upload_reference_image(
    b64_data: str,
    mime_type: str,
    bearer: str,
    project_id: str,
    account_hash: str | None = None,
    filename: str = "reference.png",
) -> str:
    """Sube la imagen de referencia A TRAVES DEL BRIDGE -- la extension ejecuta el
    fetch con las cookies del navegador, evitando el 401 que daría un bearer de disco."""
    upload_url = "https://aisandbox-pa.googleapis.com/v1/flow/uploadImage"
    body = {
        "clientContext": {"projectId": project_id, "tool": "PINHOLE"},
        "imageBytes": b64_data,
        "fileName": filename,
        "mimeType": mime_type,
        "isHidden": False,
        "isUserUploaded": True,
    }
    try:
        result = _bridge_generate(json.dumps(body), bearer, upload_url, account_hash=account_hash, timeout=30)
        if result.get("error"):
            log(f"[Flow] Upload error: {result['error']}")
            return ""
        status = result.get("status", 0)
        resp_body = result.get("body", "")
        if status == 200:
            d = json.loads(resp_body)
            media = d.get("media") or {}
            name = d.get("name") or media.get("name") or d.get("imageName") or d.get("imageId") or ""
            if name:
                log(f"[Flow] Upload: name={name}")
                return name
            log(f"[Flow] Upload OK pero name no encontrado en: {list(d.keys())}")
        else:
            log(f"[Flow] Upload imagen ref HTTP {status}: {resp_body[:300]}")
    except Exception as exc:
        log(f"[Flow] Upload imagen ref error: {exc}")
    return ""


def _bridge_generate(
    body_json: str, bearer: str, url: str, account_hash: str | None = None, timeout: int = 120
) -> dict:
    flow_bridge.start_bridge(log)

    rid = str(uuid.uuid4())
    ev = flow_bridge.register_result_waiter(rid)
    req = {"requestId": rid, "url": url, "bearer": bearer, "body": body_json}
    if account_hash:
        req["account_hash"] = account_hash

    ws_clients = flow_bridge.get_ws_clients()
    ws_hashes = list(ws_clients.keys())

    # Si la cuenta asignada tiene HTTP polling activo pero NO WS, no redirigir a la
    # WS de otra cuenta (mandaria la tarea al browser equivocado) -- encolar para HTTP
    # polling de la cuenta asignada, salvo que consiga WS en la espera de gracia.
    assigned_has_http = (
        bool(account_hash)
        and account_hash not in ws_hashes
        and account_hash in flow_bridge.get_http_seen_accounts()
    )

    pushed = False
    if assigned_has_http:
        ws_grace = time.time() + 5
        while time.time() < ws_grace:
            if account_hash in flow_bridge.get_ws_clients():
                ws_hashes = list(flow_bridge.get_ws_clients().keys())
                break
            time.sleep(0.3)
        if account_hash not in ws_hashes:
            req["account_hash"] = account_hash
            flow_bridge.enqueue_request(req)
            log(f"[Flow] Bridge: HTTP poll queue -> {account_hash[:8]} req={rid[:12]}...")
            pushed = True

    if not pushed:
        try_order = []
        if account_hash and account_hash in ws_hashes:
            try_order.append(account_hash)
        for h in ws_hashes:
            if h not in try_order and not is_banned(h):
                try_order.append(h)

        for h in try_order:
            req["account_hash"] = h
            # Si el fallback es una cuenta distinta a la asignada, usar SU bearer para
            # que las cookies del browser coincidan con el Authorization header --
            # el mismatch cookies/bearer es la causa principal de 403 reCAPTCHA.
            if h != account_hash:
                alt_bearer = flow_bridge.get_cached_bearer(h)
                if alt_bearer:
                    req["bearer"] = alt_bearer
            if flow_bridge.ws_push(h, req):
                pushed = True
                log(f"[Flow] WS push -> {h[:8]} req={rid[:12]}...")
                break

        if not pushed:
            if account_hash:
                req["account_hash"] = account_hash
                req["bearer"] = bearer
            flow_bridge.enqueue_request(req)
            log(
                f"[Flow] Bridge: request encolado {rid[:12]}... cuenta={account_hash or 'any'} (HTTP polling)"
            )

    deadline = time.time() + timeout
    while time.time() < deadline:
        ev.wait(timeout=2.0)
        ev.clear()
        result = flow_bridge.try_pop_result(rid)
        if result is not None:
            flow_bridge.cleanup_waiter(rid)
            return result

    flow_bridge.remove_from_queue(rid)
    flow_bridge.cleanup_waiter(rid)
    acct_info = f" (cuenta={account_hash})" if account_hash else ""
    raise RuntimeError(
        f"Sin respuesta del bridge{acct_info}. Asegurate de tener Chrome abierto "
        "en labs.google/fx/tools/flow con la extension activa."
    )


def _sanitize_prompt_text(p: str) -> str:
    import unicodedata

    for a, b in (
        ("—", "-"),
        ("–", "-"),
        ("‘", "'"),
        ("’", "'"),
        ("“", '"'),
        ("”", '"'),
        ("…", "..."),
        ("«", '"'),
        ("»", '"'),
    ):
        p = p.replace(a, b)
    return " ".join("".join(c for c in p.strip() if unicodedata.category(c)[0] != "C" or c == " ").split())[
        :1500
    ]


def start_run(
    prompts: list,
    out_dir: str,
    slots: int,
    aspect: str,
    model: str,
    max_retries: int,
    ref_image: str | None = None,
    auto_open: bool = False,
) -> dict:
    global _batch_id
    if isinstance(prompts, str):
        prompts = [line.strip() for line in prompts.splitlines() if line.strip()]
    prompts = [p for p in (prompts or []) if str(p).strip()]
    if not prompts:
        raise ValueError("Sin prompts")
    out_dir = (out_dir or "").strip()
    if not out_dir:
        raise ValueError("output_dir requerido")

    _release_if_stale()
    with lock:
        if state["running"]:
            raise RuntimeError("Ya hay una generacion en curso")

    if auto_open:
        auto_open_browsers()

    with lock:
        _batch_id += 1
        my_batch_id = _batch_id
        state.update(
            {
                "running": True,
                "step": "running",
                "progress": 0,
                "total": len(prompts),
                "images_saved": 0,
                "last_error": None,
                "output_dir": out_dir,
                "log": [],
                "batch_id": my_batch_id,
                "started_at": time.time(),
            }
        )

    _last_batch.clear()
    _last_batch.update(
        {
            "prompts": prompts,
            "slots": slots,
            "aspect": aspect,
            "model": model,
            "retries": max_retries,
            "ref_image": ref_image,
        }
    )

    threading.Thread(
        target=_run_batch, args=(prompts, out_dir, slots, aspect, model, max_retries, ref_image), daemon=True
    ).start()
    return {"ok": True, "total": len(prompts)}


def retry_one(out_dir: str, idx: int, filename: str, fallback_prompts: list) -> dict:
    last = dict(_last_batch) if _last_batch else None
    if not last and fallback_prompts:
        last = {
            "prompts": fallback_prompts,
            "slots": 2,
            "aspect": "IMAGE_ASPECT_RATIO_LANDSCAPE",
            "model": "NANO_BANANA_2",
            "retries": 2,
            "ref_image": None,
        }

    if not out_dir or idx is None:
        raise ValueError(f"Faltan parametros out_dir={bool(out_dir)} idx={idx}")
    if not last:
        raise ValueError("Sin parametros - genera al menos una vez primero")
    prompts = last.get("prompts", [])
    if idx < 0 or idx >= len(prompts):
        raise ValueError(f"Indice {idx} fuera de rango (total: {len(prompts)})")

    if filename:
        old_path = os.path.join(out_dir, filename)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except Exception:
                pass

    def _retry():
        _run_batch(
            [prompts[idx]],
            out_dir,
            last.get("slots", 2),
            last.get("aspect", "IMAGE_ASPECT_RATIO_LANDSCAPE"),
            last.get("model", "NANO_BANANA_2"),
            last.get("retries", 2),
            last.get("ref_image"),
            start_index=idx,
        )

    threading.Thread(target=_retry, daemon=True).start()
    return {"ok": True}


def stop() -> None:
    _stop_event.set()
    with lock:
        state["running"] = False
        state["step"] = "idle"


def get_status(since: int) -> dict:
    _release_if_stale()
    with lock:
        st = {k: v for k, v in state.items() if k != "log"}
        all_logs = state["log"]
        st["last_log"] = list(all_logs[since : since + 50])
        st["log_total"] = len(all_logs)
    return st


def get_full_log() -> str:
    with lock:
        logs = list(state["log"])
        running = state["running"]
        step = state["step"]
    lines = [f"running={running} step={step} total={len(logs)} lines"] + logs
    return "\n".join(lines)


def _run_batch(
    prompts: list,
    out_dir: str,
    slots: int,
    aspect: str,
    model: str,
    max_retries: int,
    ref_image: str | None = None,
    start_index: int = 0,
    auto_open: bool = False,
) -> None:
    """Bridge-mode: el bearer viene de la extension via el cache del bridge (no de
    cookies en disco); semaforo por cuenta (1 request activa a la vez, evita 401/403
    en cascada); slots = workers globales limitados por cuentas conectadas; retry por
    rondas hasta completar el 100%; 400 UNSAFE marca el prompt como no reintentable."""
    try:
        _run_batch_inner(
            prompts, out_dir, slots, aspect, model, max_retries, ref_image, start_index, auto_open=auto_open
        )
    except Exception as exc:
        with lock:
            state["running"] = False
            state["step"] = "idle"
            state["last_error"] = str(exc)
        logger.exception("[Flow] error fatal en batch")
        log(f"[Flow] ERROR fatal en batch: {exc}")


def _run_batch_inner(
    prompts: list,
    out_dir: str,
    slots: int,
    aspect: str,
    model: str,
    max_retries: int,
    ref_image: str | None = None,
    start_index: int = 0,
    auto_open: bool = False,
) -> None:
    log(f"[Flow] ===== BATCH INNER START: {len(prompts)} prompts, out={out_dir[:60]} =====")
    _stop_event.clear()
    # Limpiar requests pendientes del batch anterior -- evita que un upload espere
    # detras de generaciones viejas que la extension aun tiene en su cola HTTP poll.
    flow_bridge.clear_queue()
    log(f"[Flow] stop_cleared={not _stop_event.is_set()} slots={slots} model={model}")
    os.makedirs(out_dir, exist_ok=True)
    with lock:
        my_batch_id = _batch_id

    # ── Cargar cuentas en paralelo ────────────────────────────────────
    accounts_ok: list[dict] = []
    acc_load_lock = threading.Lock()

    def _load_account(i):
        ck = flow_service.load_cookie(i)
        if not ck:
            return
        sess = flow_service.get_session(ck)
        bearer = sess.get("bearer", "")
        email = sess.get("email", "") or f"cuenta_{i}"
        if not bearer:
            return
        acc_hash = flow_service.account_hash(email)
        entry = {
            "index": i,
            "cookie": ck,
            "bearer": bearer,
            "bearer_lock": threading.Lock(),
            "email": email,
            "account_hash": acc_hash,
        }
        with acc_load_lock:
            if any(a["account_hash"] == acc_hash for a in accounts_ok):
                log(f"[Flow Acc{i + 1}] Duplicado ({email}), omitiendo")
                try:
                    flow_service.cookie_path(i).unlink()
                except Exception:
                    pass
                return
            accounts_ok.append(entry)
            with lock:
                state["accounts"][i].update({"ok": True, "email": f"{email} ok"})
        log(f"[Flow Acc{i + 1}] OK Hash: {acc_hash} ({email})")

    load_threads = [
        threading.Thread(target=_load_account, args=(i,), daemon=True)
        for i in range(flow_service.NUM_ACCOUNTS)
    ]
    for t in load_threads:
        t.start()
    for t in load_threads:
        t.join(timeout=25)

    # Agregar cuentas conectadas por WS (sin cookies) y por HTTP puro -- en un .exe
    # compilado sin `websockets`, la extension solo conecta por HTTP (/flow-register).
    connected_all = flow_bridge.get_connected_accounts()
    ws_now = flow_bridge.get_ws_clients()
    has_ws_accounts = bool(ws_now)
    all_connected_hashes = set(connected_all) | set(ws_now.keys())
    for ch in list(all_connected_hashes):
        if any(a["account_hash"] == ch for a in accounts_ok):
            continue
        src = "WS" if ch in ws_now else "HTTP"
        if src == "HTTP" and has_ws_accounts:
            if not flow_bridge.get_cached_bearer(ch):
                log(f"[Flow] Cuenta HTTP {ch[:8]} omitida (sin bearer, hay cuentas WS activas)")
                continue
        accounts_ok.append(
            {
                "index": len(accounts_ok),
                "cookie": "",
                "bearer": "",
                "bearer_lock": threading.Lock(),
                "email": f"{src}_{ch[:8]}",
                "account_hash": ch,
            }
        )
        log(f"[Flow] Cuenta {src} agregada: {ch}")

    flow_bridge.start_bridge(log)

    if auto_open:
        # Esperar hasta 3s para que Chrome real conecte antes de abrir Playwright
        # (chequea WS + HTTP bridge; Chrome real registra por HTTP antes que WS).
        ao_end = time.time() + 3
        while time.time() < ao_end:
            connected_ao = set(flow_bridge.get_connected_accounts())
            with _playwright_hashes_lock:
                pw_h_ao = set(_playwright_hashes)
            if connected_ao - pw_h_ao:
                break
            time.sleep(0.3)
        auto_open_browsers()

    # ── Esperar conexion de la extension al bridge (via WS o HTTP polling) ──
    # background.js hace GET /flow-generate-poll cada 1s; el WS se registra cuando
    # background.js/flow_content.js conecta al puerto 5557. Esperamos hasta 90s.
    log("[Flow] Esperando conexion de extensiones al bridge (max 90s)...")
    wait_deadline = time.time() + 90
    last_feedback = time.time()
    first_ready_time = None
    while time.time() < wait_deadline:
        ws_during = flow_bridge.get_ws_clients()
        ws_active_during = flow_bridge.get_bearer_cache_hashes()
        all_during = set(ws_during.keys()) | ws_active_during
        for ch in list(all_during):
            if not any(a["account_hash"] == ch for a in accounts_ok):
                accounts_ok.append(
                    {
                        "index": len(accounts_ok),
                        "cookie": "",
                        "bearer": "",
                        "bearer_lock": threading.Lock(),
                        "email": f"WS_{ch[:8]}",
                        "account_hash": ch,
                    }
                )
                log(f"[Flow] Cuenta WS detectada durante espera: {ch[:8]}")
                first_ready_time = None

        connected_check = set(flow_bridge.get_connected_accounts()) | set(flow_bridge.get_ws_clients().keys())
        connected_check |= flow_bridge.get_bearer_cache_hashes()
        n_check = len([a for a in accounts_ok if a["account_hash"] in connected_check])

        ws_now_set = set(flow_bridge.get_ws_clients().keys())
        bearer_now_set = flow_bridge.get_bearer_cache_hashes()
        http_now_set = flow_bridge.get_http_seen_accounts()
        n_http_bearer = sum(
            1
            for a in accounts_ok
            if a["account_hash"] in http_now_set
            and (a["account_hash"] in bearer_now_set or bool(a.get("bearer", "")))
        )
        n_ws_bearer = sum(
            1
            for a in accounts_ok
            if a["account_hash"] in ws_now_set
            and (a["account_hash"] in bearer_now_set or bool(a.get("bearer", "")))
        )

        # Prioridad Chrome: si hay extensiones Chrome (HTTP) con bearer, no esperar Playwright.
        if n_http_bearer > 0:
            if first_ready_time is None:
                first_ready_time = time.time()
            grace_elapsed = time.time() - first_ready_time
            grace_limit = 8
            if grace_elapsed >= grace_limit:
                log(f"[Flow] [OK] Chrome real listo ({n_http_bearer} cuenta(s)) - iniciando")
                break
            if time.time() - last_feedback >= 5:
                last_feedback = time.time()
                log(
                    f"[Flow] [OK] {n_http_bearer} Chrome OK - grace {int(grace_limit - grace_elapsed):.0f}s mas..."
                )
            time.sleep(0.3)
            continue

        # Sin Chrome real: esperar WS (Playwright) como fallback.
        if len(accounts_ok) > 0 and n_ws_bearer >= len(accounts_ok):
            if first_ready_time is None:
                first_ready_time = time.time()
            grace_elapsed = time.time() - first_ready_time
            all_disk_bearer = all(bool(a.get("bearer", "")) for a in accounts_ok)
            grace_limit = 0 if all_disk_bearer else 25
            if grace_elapsed >= grace_limit:
                log(f"[Flow] [OK] WS + bearer listo - iniciando ({n_ws_bearer} cuenta(s))")
                break
            if time.time() - last_feedback >= 5:
                last_feedback = time.time()
                log(
                    f"[Flow] [OK] {n_ws_bearer} cuenta(s) WS OK - grace {int(grace_limit - grace_elapsed):.0f}s mas..."
                )
            time.sleep(0.3)
            continue

        if n_check > 0 and time.time() > wait_deadline - 5:
            break
        if time.time() - last_feedback >= 5:
            last_feedback = time.time()
            elapsed = int(time.time() - (wait_deadline - 90))
            ws_info = f"{n_ws_bearer} con WS" if n_ws_bearer else "sin WS..."
            log(
                f"[Flow] Esperando extension Chrome... {elapsed}s ({n_check}/{len(accounts_ok)} conectada(s), {ws_info})"
            )
        time.sleep(0.3)

    connected_now = set(flow_bridge.get_connected_accounts()) | set(flow_bridge.get_ws_clients().keys())
    ws_active = flow_bridge.get_bearer_cache_hashes()
    connected_now |= ws_active

    existing_hashes = {a["account_hash"] for a in accounts_ok}
    for wh in ws_active:
        if wh not in existing_hashes:
            accounts_ok.append(
                {"account_hash": wh, "email": f"ws_{wh[:8]}", "cookie": "", "bearer_lock": threading.Lock()}
            )
            log(f"[Flow] [OK] Cuenta WS agregada: {wh[:8]}")

    if not accounts_ok:
        msg = "No hay cuentas Flow activas. Guarda la cookie en la seccion Flow."
        log(f"[Flow] {msg}")
        with lock:
            state.update({"running": False, "step": "idle", "last_error": msg})
        return

    n_connected = len([a for a in accounts_ok if a["account_hash"] in connected_now])
    if n_connected == 0:
        n_connected = len(accounts_ok)
        log("[Flow] Ninguna cuenta en bridge. Usando bearer de disco como fallback.")
    else:
        log(f"[Flow] {n_connected}/{len(accounts_ok)} cuenta(s) conectadas.")

    slots_user = max(1, min(slots, 10))

    log(f"[Flow] [OK] {len(accounts_ok)} cuenta(s) con cookie valida:")
    for a in accounts_ok:
        conn_state = "conectada" if a["account_hash"] in connected_now else "sin Chrome"
        cached_b = flow_bridge.get_cached_bearer(a["account_hash"])
        if cached_b:
            a["bearer"] = cached_b
            conn_state += " + bearer OK"
        log(f"[Flow]   . {a['email']} [{conn_state}]")

    n_total_accs = len(accounts_ok)
    max_workers = max(1, slots_user * n_total_accs)
    log(
        f"[Flow] {len(prompts)} prompts . {max_workers} workers ({n_total_accs} cuenta(s) x {slots_user} slots)"
    )

    ref_name = None
    real_ref_pid = None
    if ref_image:
        log("[Flow] Imagen de referencia incluida - subiendo al bridge...")
        ref_mime = "image/jpeg"
        ref_b64 = ref_image
        if "," in ref_image:
            ref_header, ref_b64 = ref_image.split(",", 1)
            if "image/png" in ref_header:
                ref_mime = "image/png"
            elif "image/webp" in ref_header:
                ref_mime = "image/webp"

        ws_hashes_for_upload = set(flow_bridge.get_ws_clients().keys())
        upload_order = (
            [a for a in accounts_ok if a["account_hash"] in ws_hashes_for_upload]
            + [
                a
                for a in accounts_ok
                if a["account_hash"] not in ws_hashes_for_upload and a["account_hash"] in connected_now
            ]
            + [a for a in accounts_ok if a["account_hash"] not in connected_now]
        )
        ref_pid = str(uuid.uuid4())
        for ref_acc in upload_order:
            ref_bearer = flow_bridge.get_cached_bearer(ref_acc["account_hash"]) or ref_acc.get("bearer", "")
            log(f"[Flow] Upload con {ref_acc['email']}...")
            ref_name = _upload_reference_image(
                ref_b64, ref_mime, ref_bearer, ref_pid, account_hash=ref_acc["account_hash"]
            )
            if ref_name:
                log(f"[Flow] Imagen subida - name={ref_name} (NARWHAL + imageInputs)")
                break
            log(f"[Flow] [WARNING] Upload fallo con {ref_acc['email']}, intentando siguiente cuenta...")
        if not ref_name:
            log(
                "[Flow] [WARNING] Upload de ref image fallo en todas las cuentas - generando sin referencia (NARWHAL)"
            )
    log("[Flow] Asegurate de tener Chrome en labs.google/fx/tools/flow con la extension.")

    if ref_name:
        import re as re_refpid

        m_refpid = re_refpid.search(r"projects/([^/]+)", ref_name)
        real_ref_pid = m_refpid.group(1) if m_refpid else ref_pid
        log(f"[Flow] Project ID de referencia: {real_ref_pid}")
        acc_project_ids = {a["account_hash"]: real_ref_pid for a in accounts_ok}
    else:
        acc_project_ids = {a["account_hash"]: str(uuid.uuid4()) for a in accounts_ok}

    # ── Cooldown por cuenta ────────────────────────────────────────────
    acc_cooldown = {a["account_hash"]: 0.0 for a in accounts_ok}
    acc_cooldown_lock = threading.Lock()
    COOLDOWN_429 = 10.0

    def _mark_cooldown(account_hash):
        with acc_cooldown_lock:
            acc_cooldown[account_hash] = time.time() + COOLDOWN_429
            email = next(
                (a["email"] for a in accounts_ok if a["account_hash"] == account_hash), account_hash[:8]
            )
            log(f"[Flow] {email} en cooldown {COOLDOWN_429:.0f}s (429)")

    def _is_available(account_hash):
        with acc_cooldown_lock:
            return time.time() >= acc_cooldown.get(account_hash, 0.0)

    # Semaforo por cuenta: limita requests activas simultaneas para evitar 429.
    acc_semaphores = {a["account_hash"]: threading.Semaphore(slots_user) for a in accounts_ok}
    # Cuentas HTTP-only (sin WS): serializar a 1 request simultaneo -- un burst de N
    # requests via HTTP-poll dispara CAPTCHA 403 (WS-push serializa internamente).
    ws_set_at_start = set(flow_bridge.get_ws_clients().keys())
    for a in accounts_ok:
        if a["account_hash"] not in ws_set_at_start:
            acc_semaphores[a["account_hash"]] = threading.Semaphore(1)
            log(
                f"[Flow] [WARNING] {a['account_hash'][:8]} sin WS --> concurrencia 1 (evitar CAPTCHA por burst)"
            )

    acc_fails = {a["account_hash"]: 0 for a in accounts_ok}
    acc_fails_lock = threading.Lock()
    acc_skip_until: dict[str, float] = {}

    rr_counter = [0]
    rr_lock = threading.Lock()

    def _mark_fail(account_hash, is_timeout=False):
        with acc_fails_lock:
            acc_fails[account_hash] = acc_fails.get(account_hash, 0) + 1
            n = acc_fails[account_hash]
            email = next(
                (a["email"] for a in accounts_ok if a["account_hash"] == account_hash), account_hash[:8]
            )
            if is_timeout:
                # Bridge timeout = browser muerto: desregistrar de WS/HTTP para
                # sacarla del pool y limpiar la cola para no bloquear otros workers.
                flow_bridge.remove_ws_client(account_hash)
                flow_bridge.remove_http_seen(account_hash)
                flow_bridge.clear_queue_for_account(account_hash)
            if n == 3:
                acc_skip_until[account_hash] = time.time() + 60
                log(f"[Flow] {email} excluida 60s")
            elif n == 4:
                acc_skip_until[account_hash] = time.time() + 120
                log(f"[Flow] {email} excluida 2min (falla reiterada)")
            elif n >= 5:
                acc_skip_until[account_hash] = time.time() + 600
                log(f"[Flow] {email} excluida 10min (sin respuesta persistente)")

    def _mark_success(account_hash):
        with acc_fails_lock:
            acc_fails[account_hash] = 0
            acc_skip_until.pop(account_hash, None)

    def _inject_new_accounts():
        """Agrega al batch cuentas que se conectaron despues del inicio (ej: perfil
        de respaldo activado por rotacion)."""
        new_entries = {h: flow_bridge.get_cached_bearer(h) for h in flow_bridge.get_bearer_cache_hashes()}
        existing = {a["account_hash"] for a in accounts_ok}
        used_indices = {a["index"] for a in accounts_ok if "index" in a}
        for nh, nbearer in new_entries.items():
            if nh in existing:
                continue
            now = time.time()
            new_idx = len(accounts_ok)
            # Heredar warmup: buscar perfil Chrome con warmup activo pero sin cuenta
            # aun -- al conectar, su indice dinamico (len(accounts_ok)) != el indice
            # del perfil Chrome que abrio rotation, asi que el warmup se perderia
            # sin este traspaso explicito.
            inherited_warmup = 0
            with _warmup_lock:
                for cidx, exp in sorted(_warmup_until_idx.items()):
                    if now < exp and cidx not in used_indices:
                        inherited_warmup = exp
                        break
            accounts_ok.append(
                {
                    "account_hash": nh,
                    "email": f"ws_{nh[:8]}",
                    "cookie": "",
                    "bearer": nbearer or "",
                    "bearer_lock": threading.Lock(),
                    "index": new_idx,
                }
            )
            nh_has_ws = nh in flow_bridge.get_ws_clients()
            acc_semaphores[nh] = threading.Semaphore(slots_user if nh_has_ws else 1)
            with acc_cooldown_lock:
                acc_cooldown[nh] = 0.0
            acc_fails[nh] = 0
            acc_project_ids[nh] = real_ref_pid if ref_name else str(uuid.uuid4())
            used_indices.add(new_idx)
            if inherited_warmup > 0:
                with _warmup_lock:
                    _warmup_until_idx[new_idx] = inherited_warmup
                log(
                    f"[Flow] Cuenta {nh[:8]} incorporada al batch - warmup heredado {int(inherited_warmup - now)}s"
                )
            else:
                min_warmup = now + 25
                with _warmup_lock:
                    _warmup_until_idx[new_idx] = min_warmup
                log(f"[Flow] Cuenta {nh[:8]} incorporada al batch - warmup 25s para estabilizar tab")

    def _pick_account() -> dict:
        """Elige cuenta disponible: SOLO cuentas con browser conectado. Si no hay
        ninguna conectada, espera -- nunca usa cuentas sin browser abierto."""
        last_no_connected_log = [0.0]
        warmup_log_ts: dict[int, float] = {}
        while not _stop_event.is_set():
            now = time.time()
            connected = flow_bridge.get_connected_accounts()
            pool = [a for a in accounts_ok if a["account_hash"] in connected]
            if not pool:
                if now - last_no_connected_log[0] > 10:
                    log("[Flow] Esperando que un browser se conecte al bridge...")
                    last_no_connected_log[0] = now
                time.sleep(1)
                continue

            def _in_warmup(a):
                a_idx = a.get("index", 99)
                with _warmup_lock:
                    until = _warmup_until_idx.get(a_idx, 0)
                if now < until:
                    secs_left = int(until - now)
                    last = warmup_log_ts.get(a_idx, 0)
                    if now - last > 15:
                        warmup_log_ts[a_idx] = now
                        log(f"[Flow] Perfil {a_idx + 1} en warmup - {secs_left}s restantes, skip")
                    return True
                warmup_log_ts.pop(a_idx, None)
                return False

            available = [
                a
                for a in pool
                if _is_available(a["account_hash"])
                and now > acc_skip_until.get(a["account_hash"], 0)
                and not is_banned(a["account_hash"])
                and not _in_warmup(a)
            ]
            if available:
                with rr_lock:
                    idx = rr_counter[0] % len(available)
                    rr_counter[0] += 1
                return available[idx]

            with acc_cooldown_lock:
                earliest = min((acc_cooldown.get(a["account_hash"], 0.0) for a in pool), default=now + 2)
            wait = max(0.5, earliest - now)
            if wait > 2:
                log(f"[Flow] Todas en cooldown - esperando {wait:.0f}s...")
            time.sleep(min(wait, 2.0))
        return accounts_ok[0]

    def _get_best_bearer(acc: dict) -> str:
        cached = flow_bridge.get_cached_bearer(acc["account_hash"])
        return cached or acc.get("bearer", "")

    def _refresh_bearer(acc: dict, bad_bearer: str = "") -> bool:
        """Intenta obtener bearer FRESCO, ignorando el que acaba de fallar."""
        cached = flow_bridge.get_cached_bearer(acc["account_hash"])
        if cached and cached != bad_bearer:
            acc["bearer"] = cached
            return True
        with acc["bearer_lock"]:
            new_b = flow_service.get_session(acc["cookie"]).get("bearer", "")
            if new_b and new_b != bad_bearer:
                acc["bearer"] = new_b
                return True
        return False

    # Timestamp del ultimo request por cuenta -- para espaciar requests minimo 1.5s
    # (con slots_user=10 y varias cuentas necesitamos separar los workers de una
    # misma cuenta, o Google los rechaza como burst).
    acc_last_req = {a["account_hash"]: 0.0 for a in accounts_ok}
    acc_last_lock = threading.Lock()
    ACC_MIN_GAP = max(1.5, slots_user * 0.2)

    def _wait_for_account_slot(account_hash):
        with acc_last_lock:
            last = acc_last_req.get(account_hash, 0.0)
            now = time.time()
            next_slot = max(now, last + ACC_MIN_GAP)
            acc_last_req[account_hash] = next_slot
            wait = next_slot - now
        if wait > 0.01:
            time.sleep(wait)

    job_q: Queue = Queue()
    unsafe: set[int] = set()
    saved_count = [0]
    res_lock = threading.Lock()

    completed: set[int] = set()
    completed_lock = threading.Lock()

    def _mark_complete(task_idx: int) -> bool:
        with completed_lock:
            if task_idx in completed:
                return False
            completed.add(task_idx)
            return True

    def _enqueue_missing() -> int:
        count = 0
        with completed_lock:
            done = set(completed)
        for i, p in enumerate(prompts):
            if i in unsafe or i in done:
                continue
            fpath = os.path.join(out_dir, f"flow_{i + 1:04d}.png")
            if os.path.isfile(fpath) and os.path.getsize(fpath) > 500:
                continue
            job_q.put((i, p))
            count += 1
        return count

    _enqueue_missing()

    # Fallback: si una tarea falla N veces con ref image (500), generar sin ref.
    ref_fail_count: dict[int, int] = {}
    ref_fail_lock = threading.Lock()
    REF_FAIL_LIMIT = 3

    def _worker(worker_id: int):
        label = f"[Flow W{worker_id + 1}]"
        while not _stop_event.is_set() and _batch_id == my_batch_id:
            try:
                task_idx, prompt = job_q.get(timeout=1)
            except Empty:
                break

            out_file = os.path.join(out_dir, f"flow_{task_idx + 1:04d}.png")
            with completed_lock:
                if task_idx in completed:
                    continue
            if os.path.isfile(out_file) and os.path.getsize(out_file) > 500:
                if _mark_complete(task_idx):
                    with res_lock:
                        saved_count[0] += 1
                    with lock:
                        state["progress"] = saved_count[0]
                        state["images_saved"] = saved_count[0]
                continue

            prompt = _sanitize_prompt_text(prompt)
            log(f"{label} [{task_idx + 1}/{len(prompts)}] {prompt[:55]}...")

            success = False
            for attempt in range(8):
                if _stop_event.is_set():
                    break

                acc = _pick_account()
                sem = acc_semaphores[acc["account_hash"]]

                n_left = job_q.qsize()
                if 0 < n_left < max_workers // 2:
                    import random

                    time.sleep(random.uniform(0.5, 2.5))

                if not sem.acquire(timeout=2):
                    job_q.put((task_idx, prompt))
                    import random

                    time.sleep(random.uniform(0.5, 1.5))
                    break

                result = None
                try:
                    bearer = _get_best_bearer(acc)
                    if not bearer:
                        log(f"{label} Sin bearer para {acc['email'][:12]} - esperando...")
                        for _ in range(30):
                            time.sleep(1)
                            bearer = flow_bridge.get_cached_bearer(acc["account_hash"])
                            if bearer:
                                acc["bearer"] = bearer
                                break
                        if not bearer:
                            idx_fb = acc.get("index", 99)
                            ck_fb = flow_service.load_cookie(idx_fb)
                            if ck_fb:
                                sess_fb = flow_service.get_session(ck_fb)
                                bearer = sess_fb.get("bearer", "")
                                if bearer:
                                    acc["cookie"] = ck_fb
                                    acc["bearer"] = bearer
                                    log(f"{label} Bearer obtenido de cookie disco")
                            if not bearer:
                                log(f"{label} Sin bearer tras 30s - saltando")
                                continue

                    _wait_for_account_slot(acc["account_hash"])
                    if _stop_event.is_set():
                        break
                    gen_pid = acc_project_ids.get(acc["account_hash"]) or str(uuid.uuid4())
                    session_id = ";" + str(int(time.time() * 1000))
                    api_url = FLOW_GEN_URL_TPL.format(pid=gen_pid)
                    import random

                    seed = random.randint(1, 999999)

                    prompt = prompt.strip().strip("\"'")
                    if model == "IMAGE_GENERATION_001_IMAGEN4":
                        prompt = prompt + ". Maintain same avatar style"

                    with ref_fail_lock:
                        task_ref_fails = ref_fail_count.get(task_idx, 0)
                    use_ref_now = bool(ref_name) and task_ref_fails < REF_FAIL_LIMIT

                    inner_req = {
                        "clientContext": {"projectId": gen_pid, "tool": "PINHOLE", "sessionId": session_id},
                        "imageModelName": (
                            "NARWHAL" if model in ("NANO_BANANA_2", "IMAGE_GENERATION_001_IMAGEN4") else model
                        ),
                        "imageAspectRatio": aspect,
                        "structuredPrompt": {"parts": [{"text": prompt}]},
                        "seed": seed,
                    }
                    if use_ref_now:
                        inner_req["imageInputs"] = [
                            {"imageInputType": "IMAGE_INPUT_TYPE_REFERENCE", "name": ref_name}
                        ]

                    req_body = {
                        "clientContext": {"projectId": gen_pid, "tool": "PINHOLE", "sessionId": session_id},
                        "mediaGenerationContext": {"batchId": str(uuid.uuid4())},
                        "useNewMedia": True,
                        "requests": [inner_req],
                    }

                    log(f"{label} --> bridge_generate acc={acc['account_hash'][:8]} url={api_url[40:80]}")
                    try:
                        result = _bridge_generate(
                            json.dumps(req_body),
                            bearer,
                            api_url,
                            account_hash=acc["account_hash"],
                            timeout=300,
                        )
                    except RuntimeError:
                        log(f"{label} Bridge timeout ({acc['account_hash'][:8]}) - re-encolando tarea")
                        _mark_fail(acc["account_hash"], is_timeout=True)
                        job_q.put((task_idx, prompt))
                        success = True
                        break
                finally:
                    sem.release()

                if result.get("error"):
                    err_str = result["error"][:80]
                    log(f"{label} intento {attempt + 1}: {err_str}")
                    time.sleep(8 if "tab_unreachable" in err_str else 2)
                    continue

                status = result.get("status", 0)
                resp_body = result.get("body", "")

                if status == 200:
                    try:
                        data = json.loads(resp_body)
                        media = data.get("media", [])
                        if not media:
                            raise RuntimeError("Sin imagenes en respuesta")
                        fife_url = media[0].get("image", {}).get("generatedImage", {}).get("fifeUrl")
                        if not fife_url:
                            raise RuntimeError("Sin fifeUrl")
                        dl_ok = False
                        for dl_try in range(4):
                            try:
                                with _dl_sem:
                                    r = requests.get(fife_url, timeout=30, verify=False)
                                r.raise_for_status()
                                with open(out_file, "wb") as fh:
                                    fh.write(r.content)
                                dl_ok = True
                                break
                            except Exception as dl_e:
                                if dl_try < 3:
                                    time.sleep(0.5 + dl_try)
                                else:
                                    raise dl_e
                        if not dl_ok:
                            raise RuntimeError("Descarga fallida tras 4 intentos")
                        log(f"{label} [OK] Imagen {task_idx + 1}")
                        _mark_success(acc["account_hash"])
                        if _mark_complete(task_idx):
                            with res_lock:
                                saved_count[0] += 1
                            with lock:
                                state["progress"] = saved_count[0]
                                state["images_saved"] = saved_count[0]
                        success = True
                        break
                    except Exception as e:
                        log(f"{label} intento {attempt + 1} error descarga: {e}")
                        time.sleep(1)

                elif status == 401:
                    bad_bearer = bearer
                    got_new = _refresh_bearer(acc, bad_bearer=bad_bearer)
                    if got_new:
                        log(f"{label} 401 bearer renovado - reintentando en 3s")
                        time.sleep(3)
                    else:
                        log(f"{label} 401 sin bearer fresco para {acc['email'][:12]} - pausa 10s")
                        time.sleep(10)

                elif status == 403:
                    _mark_fail(acc["account_hash"])
                    with acc_cooldown_lock:
                        acc_cooldown[acc["account_hash"]] = time.time() + 30.0
                    wait = 3 * (attempt + 1)
                    log(f"{label} 403 reCAPTCHA - cooldown 30s | body={resp_body[:300]}")
                    time.sleep(wait)

                elif status == 400:
                    if "unsafe" in resp_body.lower():
                        log(f"{label} 400 UNSAFE [{task_idx + 1}] - reescribiendo prompt...")
                        rewritten = sanitize_prompt(prompt)
                        if rewritten:
                            log(f"{label} Prompt reescrito: {rewritten[:80]}...")
                            prompt = rewritten
                            continue
                        log(f"{label} Reescritura fallida - prompt bloqueado")
                        unsafe.add(task_idx)
                        success = True
                        break
                    elif "invalid_argument" in resp_body.lower():
                        log(f"{label} 400 INVALID_ARGUMENT (intento {attempt + 1}) body={resp_body[:400]}")
                        unsafe.add(task_idx)
                        success = True
                        break
                    else:
                        log(f"{label} 400: {resp_body[:300]}")
                        break

                elif status == 429:
                    _mark_cooldown(acc["account_hash"])
                    email = acc.get("email", acc["account_hash"][:8])
                    acc_idx_429 = acc.get("index", 0)
                    log(f"{label} 429 - {email} en cooldown 30s, reencola tarea")
                    record_rl_hit(acc["account_hash"], acc_idx_429)
                    job_q.put((task_idx, prompt))
                    success = True
                    break

                else:
                    if status == 500 and use_ref_now:
                        with ref_fail_lock:
                            ref_fail_count[task_idx] = ref_fail_count.get(task_idx, 0) + 1
                            fail_cnt = ref_fail_count[task_idx]
                        log(
                            f"{label} 500 con imagen ref (intento {attempt + 1}, fallo_ref={fail_cnt}/{REF_FAIL_LIMIT}): {resp_body[:300]}"
                        )
                        if fail_cnt >= REF_FAIL_LIMIT:
                            log(
                                f"{label} [WARNING] Ref image falla consistentemente - proximos intentos usaran NARWHAL sin referencia"
                            )
                    else:
                        log(f"{label} intento {attempt + 1}: HTTP {status}")
                    time.sleep(2)

            if not success and task_idx not in unsafe:
                job_q.put((task_idx, prompt))

    # ── Monitor de cuentas nuevas (hilo independiente) ──────────────────
    # Detecta cuentas que se conectan mid-batch (ej: perfil de respaldo activado
    # por rotacion) sin depender de que los workers esten activos.
    def _account_monitor():
        while not _stop_event.is_set():
            try:
                _inject_new_accounts()
                for a in list(accounts_ok):
                    fresh = flow_bridge.get_cached_bearer(a["account_hash"])
                    if fresh and fresh != a.get("bearer", ""):
                        a["bearer"] = fresh
            except Exception:
                pass
            time.sleep(2)

    threading.Thread(target=_account_monitor, daemon=True).start()

    # ── Rondas hasta completar todo ──────────────────────────────────────
    round_num = 0
    max_rounds = 30
    log(
        f"[Flow] PRE-ROUND: stop={_stop_event.is_set()} max_workers={max_workers} q={job_q.qsize()} accs={len(accounts_ok)}"
    )
    while not _stop_event.is_set() and round_num < max_rounds:
        round_num += 1
        if job_q.empty():
            break
        pending = job_q.qsize()
        total_safe = len(prompts) - len(unsafe)
        done = saved_count[0]
        log(f"[Flow] Ronda {round_num}: {pending} pendientes, {done}/{total_safe} listas")

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = []
            for i in range(max_workers):
                if _stop_event.is_set():
                    break
                futs.append(ex.submit(_worker, i))
                time.sleep(0.05)
            for f in as_completed(futs):
                try:
                    f.result()
                except Exception as exc:
                    log(f"[Flow] Worker exception: {exc}")

        if not _stop_event.is_set():
            # Vaciar cualquier re-encole de workers antes de reconstruir la cola --
            # sin esto, cada ronda duplica los items pendientes.
            while not job_q.empty():
                try:
                    job_q.get_nowait()
                except Exception:
                    break
            if _enqueue_missing() == 0:
                break

    with lock:
        state["step"] = "done" if not _stop_event.is_set() else "idle"
        state["running"] = False
    total_safe = len(prompts) - len(unsafe)
    log(
        f"[Flow] Listo: {saved_count[0]}/{total_safe} imagenes"
        + (f" ({len(unsafe)} bloqueadas por Google)" if unsafe else "")
    )


def abrir_carpeta() -> dict:
    with lock:
        target = (state.get("output_dir") or "").strip()
    if not target or not os.path.isdir(target):
        raise ValueError("Sin carpeta de salida (ejecuta primero un lote).")
    open_folder(target)
    return {"ok": True, "path": target}


def list_images(dir_path: str) -> list[str]:
    d = (dir_path or "").strip()
    if not d or not os.path.isdir(d):
        return []
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    return sorted(
        (f for f in os.listdir(d) if os.path.splitext(f)[1].lower() in exts),
        key=lambda f: os.path.getmtime(os.path.join(d, f)),
    )


def get_mtime(dir_path: str, filename: str) -> float:
    if not dir_path or not filename:
        return 0.0
    path = os.path.join(dir_path, os.path.basename(filename))
    return os.path.getmtime(path) if os.path.isfile(path) else 0.0


def get_image_path(dir_path: str, filename: str) -> str | None:
    if not dir_path or not filename:
        return None
    path = os.path.join(dir_path, os.path.basename(filename))
    return path if os.path.isfile(path) else None
