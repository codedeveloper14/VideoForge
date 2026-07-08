import base64
import os
import queue
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from src.infrastructure.ai_providers import openrouter_client
from src.infrastructure.ai_providers.whisk_client import WhiskClient, WhiskExpired, tls_workers, to_b64
from src.infrastructure.ai_providers.whisk_pool import WhiskPool
from src.utils.logger import get_logger
from src.utils.paths import get_cookies_dir, get_whisk_downloads_dir, get_whisk_profiles_dir

logger = get_logger(__name__)

NUM_ACCOUNTS = 5
POLLINATION_WEBHOOK = os.environ.get(
    "POLLINATION_WEBHOOK",
    "https://n8n-n8n.y9c1cn.easypanel.host/webhook/3dab8315-b12b-4c76-9b7c-91fc67daf120",
)

_state = {
    "running": False, "step": "idle",
    "progress": 0, "total": 0, "images_saved": 0,
    "log": [], "output_dir": None, "last_error": None,
    "accounts": [
        {"id": i, "status": "idle", "slots": [], "jobs": 0, "logged_in": False, "user": ""}
        for i in range(NUM_ACCOUNTS)
    ],
}
_stop_event = threading.Event()
_lock = threading.Lock()
_subject_path: list[str | None] = [None]

_playwright_ok: bool | None = None


def _log(msg: str) -> None:
    logger.info(msg)
    with _lock:
        _state["log"].append(msg)
        if len(_state["log"]) > 800:
            _state["log"] = _state["log"][-800:]


def _cancel_requested() -> bool:
    return _stop_event.is_set()


def playwright_installed() -> bool:
    global _playwright_ok
    if _playwright_ok is None:
        try:
            import playwright  # noqa: F401
            _playwright_ok = True
        except ImportError:
            _playwright_ok = False
    return _playwright_ok


def _cookie_file(account_id: int) -> Path:
    return get_cookies_dir() / f"account_{account_id}.txt"


def sync_profile_rows() -> None:
    """Actualiza _state['accounts'] leyendo cookies y probando sesion en paralelo."""
    from src.infrastructure.ai_providers.whisk_client import probe_session

    def _one(i: int):
        ck_f = _cookie_file(i)
        if not ck_f.is_file():
            return i, {"logged_in": False, "user": "", "has_file": False, "err": ""}
        try:
            ck = ck_f.read_text(encoding="utf-8").strip()
        except Exception:
            return i, {"logged_in": False, "user": "", "has_file": False, "err": "read"}
        if not ck:
            return i, {"logged_in": False, "user": "", "has_file": False, "err": ""}
        pr = probe_session(ck)
        return i, {"logged_in": pr["ok"], "user": pr.get("user", ""), "has_file": True, "err": pr.get("error", "")}

    results = {}
    try:
        with ThreadPoolExecutor(max_workers=NUM_ACCOUNTS) as ex:
            futs = [ex.submit(_one, i) for i in range(NUM_ACCOUNTS)]
            for fut in as_completed(futs, timeout=22):
                try:
                    idx, row = fut.result()
                    results[idx] = row
                except Exception:
                    pass
    except Exception:
        pass
    for i in range(NUM_ACCOUNTS):
        if i not in results:
            results[i] = {"logged_in": False, "user": "", "has_file": False, "err": "timeout"}

    with _lock:
        for i in range(NUM_ACCOUNTS):
            row = results[i]
            acc = _state["accounts"][i]
            acc["logged_in"] = row["logged_in"]
            acc["user"] = row.get("user", "")
            if row["logged_in"]:
                if acc.get("status") in ("expired", "done"):
                    acc["status"] = "idle"
            elif row.get("has_file"):
                acc["status"] = "expired"
            else:
                acc["status"] = "idle"


# ─────────────────────────────────────────────────────────────────
# Worker (un hilo por imagen)
# ─────────────────────────────────────────────────────────────────

def _worker(idx: int, prompt: str, pool: WhiskPool, out_dir: str, total: int,
            ev_q: queue.Queue, cancel_ev: threading.Event) -> dict:
    """Genera la imagen idx con reintentos acotados. Ante rate-limits rota cuenta;
    ante IDs expirados renueva hasta un maximo; ante bloqueo de contenido u otros
    fallos persistentes omite la imagen y el lote sigue (render con parciales)."""
    import random

    if cancel_ev.is_set() or _cancel_requested():
        return {"idx": idx, "ok": False}

    fname = f"img_{idx + 1:05d}.png"
    path = os.path.join(out_dir, fname)
    attempt = 0
    timeout_streak = 0
    conn_streak = 0
    expired_hits = 0
    sanitize_once = False

    max_attempts = max(4, min(120, int(os.environ.get("WHISK_MAX_ATTEMPTS_PER_IMAGE", "16"))))
    max_expired = max(2, min(30, int(os.environ.get("WHISK_MAX_EXPIRED_RESETS_PER_IMAGE", "8"))))

    while not cancel_ev.is_set() and not _cancel_requested():
        attempt += 1
        if attempt > max_attempts:
            _log(f"[{idx + 1}/{total}] Omitida tras {max_attempts} intentos - sigue el lote.")
            ev_q.put(("fail", idx))
            return {"idx": idx, "ok": False, "skip": "max_attempts"}

        client = pool.get_client(cancel_ev)
        if client is None:
            ev_q.put(("fail", idx))
            return {"idx": idx, "ok": False}

        client._log(f"[{idx + 1}/{total}] intento {attempt}: {prompt[:60]}")
        seed = random.randint(1, 999_999)

        if cancel_ev.is_set() or _cancel_requested():
            pool.release_client(client)
            ev_q.put(("fail", idx))
            return {"idx": idx, "ok": False}

        try:
            raw = client.generate(prompt, seed=seed)
            with open(path, "wb") as fh:
                fh.write(raw)
            client._log(f"[OK] [{idx + 1}] {fname} ({len(raw) // 1024} KB)")
            pool.mark_ok(client)
            timeout_streak = 0
            conn_streak = 0
            acc_id = int(client.label[1]) if client.label[1:2].isdigit() else 0
            with _lock:
                _state["accounts"][acc_id]["jobs"] = _state["accounts"][acc_id].get("jobs", 0) + 1
                _state["accounts"][acc_id]["status"] = "running"
            ev_q.put(("done", idx))
            return {"idx": idx, "ok": True, "path": path}

        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout,
                requests.exceptions.Timeout):
            pool.release_client(client)
            timeout_streak += 1
            wait = min(2 * timeout_streak, 10)
            client._log(f"Timeout [{idx + 1}] (streak={timeout_streak}) - reintentando en {wait}s...")
            for _ in range(wait):
                if cancel_ev.is_set() or _cancel_requested():
                    break
                time.sleep(1)

        except requests.exceptions.ConnectionError as exc:
            pool.release_client(client)
            conn_streak += 1
            ev_q.put(("conn_err", idx))
            wait = min(4 + conn_streak * 3, 45)
            client._log(f"Error de conexion [{idx + 1}]: {str(exc)[:80]} - reintentando en {wait}s...")
            if conn_streak >= 8:
                client._log(f"[{idx + 1}/{total}] Omitida por conectividad inestable (racha={conn_streak}).")
                ev_q.put(("fail", idx))
                return {"idx": idx, "ok": False, "skip": "conn_streak"}
            for _ in range(wait):
                if cancel_ev.is_set() or _cancel_requested():
                    break
                time.sleep(1)

        except RuntimeError as exc:
            msg = str(exc)
            msg_l = msg.lower()
            if "whisk_blocked_content" in msg_l or "bloqueado por política" in msg_l:
                pool.release_client(client)
                if not sanitize_once:
                    new_prompt = openrouter_client.sanitize_prompt(prompt)
                    sanitize_once = True
                    if new_prompt:
                        client._log(f"[{idx + 1}/{total}] Prompt reescrito (OpenRouter) - reintentando...")
                        prompt = new_prompt
                        attempt -= 1
                        continue
                client._log(f"[{idx + 1}/{total}] Omitida - Whisk bloqueo el prompt (politica/moderacion).")
                ev_q.put(("fail", idx))
                return {"idx": idx, "ok": False, "skip": "blocked"}

            if "429" in msg_l or "rate limit" in msg_l or "demasiadas" in msg_l:
                pool.mark_ratelimited(client, cooldown=65.0)
            elif any(k in msg_l for k in ("cookie", "expirada", "401", "403", "inválida", "invalida",
                                           "unauthorized", "unauthenticated")):
                client._log(f"Sesion invalida [{idx + 1}] - renovando...")
                pool.mark_ratelimited(client, cooldown=20.0)
                pool.reset_client_async(client)
            else:
                pool.release_client(client)
                wait = min(5 * attempt, 30)
                client._log(f"[WARNING] Error [{idx + 1}] intento {attempt}: {str(exc)[:120]} "
                            f"- reintentando en {wait}s")
                for _ in range(wait):
                    if cancel_ev.is_set() or _cancel_requested():
                        break
                    time.sleep(1)

        except WhiskExpired:
            expired_hits += 1
            if expired_hits >= max_expired:
                pool.release_client(client)
                client._log(f"[{idx + 1}/{total}] Omitida tras {expired_hits} renovaciones de workflow.")
                ev_q.put(("fail", idx))
                return {"idx": idx, "ok": False, "skip": "expired_cap"}
            client._log(f"IDs expirados [{idx + 1}] - renovando en bg...")
            pool.mark_ratelimited(client, cooldown=15.0)
            pool.reset_client_async(client)

        except Exception as exc:
            pool.release_client(client)
            if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
                timeout_streak += 1
                wait = min(2 * timeout_streak, 10)
                client._log(f"Timeout inesperado [{idx + 1}] - reintentando en {wait}s...")
            else:
                wait = min(5 * attempt, 30)
                client._log(f"[WARNING] Error inesperado [{idx + 1}] intento {attempt}: "
                            f"{str(exc)[:120]} - reintentando en {wait}s")
            for _ in range(wait):
                if cancel_ev.is_set() or _cancel_requested():
                    break
                time.sleep(1)

    ev_q.put(("fail", idx))
    return {"idx": idx, "ok": False}


def _make_placeholder_image() -> str | None:
    try:
        placeholder = tempfile.mktemp(suffix=".jpg")
        try:
            from PIL import Image
            img = Image.new("RGB", (512, 288), (245, 245, 245))
            img.save(placeholder, "JPEG", quality=85)
        except ImportError:
            jpeg = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
                    b"\xff\xd9")
            Path(placeholder).write_bytes(jpeg)
        _log("Sin imagen de referencia - usando placeholder neutro")
        return placeholder
    except Exception as exc:
        _log(f"[WARNING] No se pudo crear placeholder: {exc}")
        return None


def _run_batch_core(prompts: list[str], slots_per_acc: int, subj_path: str | None, out_dir: str) -> None:
    base = []
    for i in range(NUM_ACCOUNTS):
        ck_f = _cookie_file(i)
        if ck_f.is_file():
            ck = ck_f.read_text(encoding="utf-8").strip()
            if ck:
                base.append(WhiskClient(ck, label=f"C{i}"))

    if not base:
        _log("[ERROR] No hay cuentas. Guarda al menos una cookie en cookies/account_0.txt")
        with _lock:
            _state["last_error"] = "Whisk: no hay cookies en cookies/ (account_*.txt)."
        _state["step"] = "idle"
        return

    slot_clients = [WhiskClient(b.cookie, label=f"C{b.label[1]}S{s}")
                    for b in base for s in range(slots_per_acc)]

    total = len(prompts)
    n_slots = len(slot_clients)
    _log(f"{total} imagenes - {n_slots} slots ({len(base)} ctas x {slots_per_acc}) - rotacion automatica")

    def _create_project(c: WhiskClient):
        try:
            if _cancel_requested():
                return None
            acc_id = int(c.label[1]) if c.label[1:2].isdigit() else 0
            with _lock:
                _state["accounts"][acc_id]["status"] = "starting"
                sl = _state["accounts"][acc_id].setdefault("slots", [])
                sl_idx = int(c.label[3]) if len(c.label) > 3 and c.label[3:4].isdigit() else 0
                while len(sl) <= sl_idx:
                    sl.append("")
            c.workflow_id = c.create_project()
            return c
        except Exception as exc:
            c._log(f"[ERROR] create_project fallido: {exc}")
            return None

    w1 = tls_workers(n_slots)
    _log(f"Fase 1/3 - creando proyectos (hasta {w1} en paralelo)...")
    with ThreadPoolExecutor(max_workers=w1) as ex:
        with_project = [c for c in ex.map(_create_project, slot_clients) if c is not None]

    if not with_project:
        tail = "\n".join(_state.get("log", [])[-40:])
        msg = ("Whisk: sesion expirada (HTTP 401). Reinicia sesion en Google Labs / Whisk y vuelve a exportar cookies."
               if ("401" in tail or "Unauthorized" in tail)
               else "Whisk: no se pudo crear ningun proyecto (cookies invalidas o sin acceso).")
        _log("[ERROR] Ningun slot pudo crear proyecto. Verifica las cookies.")
        with _lock:
            _state["last_error"] = msg
        _state["step"] = "idle"
        return

    if _cancel_requested():
        _log("Detenido antes de analizar imagen.")
        _state["step"] = "idle"
        return

    subj_path_real = subj_path
    if not subj_path or not os.path.isfile(str(subj_path)):
        subj_path_real = _make_placeholder_image()

    shared_b64 = None
    shared_cap = None
    if subj_path_real and os.path.isfile(str(subj_path_real)):
        try:
            _log("Fase 2/3 - analizando imagen (1 vez para todos los slots)...")
            shared_b64 = to_b64(subj_path_real)
            shared_cap = with_project[0]._caption(shared_b64, with_project[0].workflow_id)
            _log(f"Caption: {shared_cap[:70]}")
        except Exception as exc:
            _log(f"[WARNING] Caption compartido fallo ({exc}) - se intentara por slot")
            shared_b64 = None

    def _upload_subject(c: WhiskClient):
        for attempt in range(3):
            try:
                if _cancel_requested():
                    return None
                if shared_b64 and shared_cap:
                    mid = c._upload_img(shared_b64, shared_cap, c.workflow_id)
                    c.subject_refs = [{"caption": shared_cap, "mediaGenerationId": mid}]
                    c._log(f"Sujeto OK - {shared_cap[:50]}")
                elif subj_path_real and os.path.isfile(str(subj_path_real)):
                    c.subject_refs = [c.upload_subject(subj_path_real, c.workflow_id)]
                else:
                    c.subject_refs = []
                acc_id = int(c.label[1]) if c.label[1:2].isdigit() else 0
                with _lock:
                    _state["accounts"][acc_id]["status"] = "running"
                return c
            except Exception as exc:
                if attempt < 2:
                    wait = 4 * (attempt + 1)
                    c._log(f"[WARNING] upload_subject intento {attempt + 1}/3: {exc} - reintentando en {wait}s...")
                    time.sleep(wait)
                else:
                    c._log(f"[ERROR] upload_subject fallido tras 3 intentos: {exc} - slot descartado")
                    return None

    w3 = tls_workers(len(with_project))
    _log(f"Fase 3/3 - subiendo sujeto (hasta {w3} en paralelo)...")
    with ThreadPoolExecutor(max_workers=w3) as ex:
        ready = [c for c in ex.map(_upload_subject, with_project) if c is not None]

    if not ready:
        _log("[ERROR] Ningun slot pudo inicializarse. Verifica las cookies.")
        with _lock:
            _state["last_error"] = "Whisk: fallo la subida de la imagen de referencia o la sesion."
        _state["step"] = "idle"
        return

    if _cancel_requested():
        _log("Detenido antes de generar imagenes.")
        _state["step"] = "idle"
        return

    _log(f"[OK] {len(ready)} slots listos - generando {total} imagenes...")
    os.makedirs(out_dir, exist_ok=True)

    cancel_ev = threading.Event()
    ev_q: queue.Queue = queue.Queue()
    pool = WhiskPool(ready, subj_path, jobs_for=lambda c: _state["accounts"][WhiskPool._acc_id(c)].get("jobs", 0),
                      log=_log)

    executor = ThreadPoolExecutor(max_workers=len(ready))
    active: dict = {}
    next_idx = 0
    enumerated = list(enumerate(prompts))
    stop_shutdown = False
    target_parallel = len(ready)
    conn_events: list[float] = []
    conn_cooldown_until = 0.0

    def try_submit():
        nonlocal next_idx
        if time.time() < conn_cooldown_until:
            return
        while len(active) < target_parallel and next_idx < len(enumerated):
            if _cancel_requested():
                return
            i, pr = enumerated[next_idx]
            next_idx += 1
            fut = executor.submit(_worker, i, pr, pool, out_dir, total, ev_q, cancel_ev)
            active[fut] = i

    try:
        try_submit()
        while next_idx < len(enumerated) or active:
            if _cancel_requested() and not stop_shutdown:
                cancel_ev.set()
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    executor.shutdown(wait=False)
                except Exception:
                    pass
                stop_shutdown = True

            for fut in list(active):
                if fut.done() and fut.cancelled():
                    del active[fut]

            try:
                ev_type, ev_idx = ev_q.get(timeout=0.35)
                if ev_type == "conn_err":
                    now = time.time()
                    conn_events.append(now)
                    conn_events[:] = [t for t in conn_events if now - t <= 45.0]
                    threshold = max(6, target_parallel * 2)
                    if len(conn_events) >= threshold and target_parallel > 1:
                        new_p = max(1, target_parallel // 2)
                        if new_p < target_parallel:
                            target_parallel = new_p
                            conn_cooldown_until = now + 8.0
                            _log(f"Conectividad inestable detectada ({len(conn_events)} errores/45s) "
                                 f"--> bajando paralelismo a {target_parallel} slot(s).")
                    continue
                if ev_type in ("done", "fail"):
                    with _lock:
                        _state["progress"] += 1
                        if ev_type == "done":
                            _state["images_saved"] += 1
                    for fut in list(active):
                        if active.get(fut) == ev_idx:
                            del active[fut]
                            break
                    if not _cancel_requested():
                        try_submit()
            except queue.Empty:
                pass

            if stop_shutdown and not active:
                break
    finally:
        try:
            if not stop_shutdown:
                executor.shutdown(wait=True)
        except Exception:
            pass

    if not _cancel_requested():
        files = sorted(Path(out_dir).glob("img_*.png"), key=lambda f: f.name)
        renamed = []
        for n, f in enumerate(files, 1):
            tgt = f.parent / f"img_{n:05d}.png"
            if f == tgt:
                renamed.append(tgt)
            else:
                tmp = Path(tempfile.mktemp(dir=str(f.parent), suffix=".png"))
                f.rename(tmp)
                renamed.append((tmp, tgt))
        final = []
        for item in renamed:
            if isinstance(item, tuple):
                tmp, tgt = item
                tmp.rename(tgt)
                final.append(tgt)
            else:
                final.append(item)
        t0 = 1_700_000_000.0
        for n, f in enumerate(final, 1):
            try:
                os.utime(str(f), (t0 + n, t0 + n))
            except Exception:
                pass
        got = int(_state.get("images_saved") or 0)
        missing = max(0, total - got)
        if missing:
            _log(f"Lote terminado. {got}/{total} imagenes guardadas ({missing} omitidas). "
                 "Puedes renderizar con las existentes.")
        else:
            _log(f"Completado. {got}/{total} imagenes.")
        _state["last_error"] = None
        _state["step"] = "done"
    else:
        _log("Detenido por el usuario.")
        _state["step"] = "idle"


def _run_batch(prompts: list[str], slots_per_acc: int, subj_path: str | None, out_dir: str) -> None:
    """Envoltorio: garantiza running=False y cuentas en idle aunque el core falle."""
    try:
        _run_batch_core(prompts, slots_per_acc, subj_path, out_dir)
    except Exception as exc:
        logger.exception("Error fatal en batch Whisk")
        _log(f"[ERROR] Error fatal en batch Whisk: {exc}")
        _state["last_error"] = str(exc)[:400]
        _state["step"] = "idle"
    finally:
        _state["running"] = False
        try:
            sync_profile_rows()
        except Exception:
            for i in range(NUM_ACCOUNTS):
                _state["accounts"][i]["status"] = "idle"


# ─────────────────────────────────────────────────────────────────
# API publica
# ─────────────────────────────────────────────────────────────────

def get_status() -> dict:
    with _lock:
        st = {**_state, "log": list(_state.get("log") or [])[-140:]}
    st["playwright_ok"] = playwright_installed()
    return st


def stop() -> None:
    if not _stop_event.is_set():
        _log("Deteniendo...")
    _stop_event.set()


def list_images() -> dict:
    d = _state.get("output_dir") or str(get_whisk_downloads_dir())
    files = sorted(Path(d).glob("img_*")) if Path(d).exists() else []
    return {"images": [f.name for f in files], "count": len(files)}


def get_image_path(name: str) -> Path | None:
    d = _state.get("output_dir") or str(get_whisk_downloads_dir())
    base = Path(d).resolve()
    candidate = (base / name).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def clear_images() -> None:
    dirs_to_clear = {str(get_whisk_downloads_dir())}
    if _state.get("output_dir"):
        dirs_to_clear.add(str(_state["output_dir"]))
    for d in dirs_to_clear:
        try:
            for f in Path(d).glob("img_*"):
                try:
                    f.unlink()
                except Exception:
                    pass
        except Exception:
            pass
    with _lock:
        _state["images_saved"] = 0


def open_output_folder() -> str:
    from src.utils.platform_utils import open_folder
    target = str(_state.get("output_dir") or get_whisk_downloads_dir())
    if not os.path.isdir(target):
        raise FileNotFoundError("Carpeta no disponible")
    open_folder(target)
    return target


def check_login() -> list[dict]:
    try:
        sync_profile_rows()
    except Exception:
        pass
    with _lock:
        return [
            {"id": i, "logged_in": bool(_state["accounts"][i].get("logged_in")),
             "user": _state["accounts"][i].get("user", "")}
            for i in range(NUM_ACCOUNTS)
        ]


def login_with_cookie(profile_id: int, cookie: str) -> dict:
    from src.infrastructure.ai_providers.whisk_client import clean_cookie
    ck = clean_cookie(cookie)
    result = WhiskClient(ck, label=f"C{profile_id}").test_auth()
    if not result["ok"]:
        raise ValueError(result.get("error", "Cookie invalida o expirada"))
    _cookie_file(profile_id).write_text(ck, encoding="utf-8")
    _log(f"[C{profile_id}] [OK] Cookie guardada directamente")
    threading.Thread(target=sync_profile_rows, daemon=True).start()
    return {"user": result.get("user", "")}


def _playwright_login(profile_id: int) -> None:
    """Abre Chrome, usuario inicia sesion, captura cookies al detectar auth."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _log(f"[C{profile_id}] [ERROR] Playwright no instalado.")
        return

    profile_dir = str(get_whisk_profiles_dir() / f"chrome_profile_{profile_id}")
    os.makedirs(profile_dir, exist_ok=True)
    _log(f"[C{profile_id}] Abriendo Chrome - inicia sesion y navega a labs.google/fx/tools/whisk")

    try:
        with sync_playwright() as pw:
            import glob
            local = os.environ.get("LOCALAPPDATA", "")
            candidates = glob.glob(os.path.join(local, "ms-playwright", "chromium-*", "chrome-win*", "chrome.exe")) \
                if local else []
            exe = candidates[0] if candidates else None
            ctx = pw.chromium.launch_persistent_context(
                profile_dir, headless=False, executable_path=exe,
                args=["--no-first-run", "--disable-blink-features=AutomationControlled"],
                ignore_https_errors=True,
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto("https://labs.google/fx/tools/whisk", timeout=20000)
            except Exception:
                pass

            saved = False
            while True:
                try:
                    cookies = ctx.cookies()
                except Exception:
                    break

                google_ck = [c for c in cookies if any(
                    d in c.get("domain", "") for d in
                    ("labs.google", "google.com", "accounts.google.com", "googleapis.com"))]
                auth_names = {"SID", "__Secure-1PSID", "__Secure-3PSID", "SAPISID", "APISID"}
                has_auth = any(c["name"] in auth_names for c in google_ck)

                if has_auth and len(google_ck) >= 5:
                    ck_str = "; ".join(f"{c['name']}={c['value']}" for c in google_ck)
                    try:
                        result = WhiskClient(ck_str, label=f"C{profile_id}").test_auth()
                        if result["ok"]:
                            _cookie_file(profile_id).write_text(ck_str, encoding="utf-8")
                            _log(f"[C{profile_id}] [OK] Cookie guardada - {result.get('user', '')}")
                            saved = True
                            threading.Thread(target=sync_profile_rows, daemon=True).start()
                    except Exception:
                        pass

                if saved:
                    time.sleep(1)
                    try:
                        ctx.close()
                    except Exception:
                        pass
                    break
                time.sleep(2)

            if not saved:
                _log(f"[C{profile_id}] [WARNING] Browser cerrado sin guardar sesion")
    except Exception as exc:
        _log(f"[C{profile_id}] [ERROR] Browser error: {exc}")


def start_browser_login(profile_id: int) -> None:
    threading.Thread(target=_playwright_login, args=(profile_id,), daemon=True).start()


def set_subject_b64(b64: str, ext: str) -> str:
    ext = (ext or "jpg").lower().lstrip(".")
    if ext not in ("jpg", "jpeg", "png", "webp", "gif", "bmp"):
        ext = "jpg"
    raw = base64.b64decode(b64)
    path = str(get_whisk_downloads_dir() / f"_subject.{ext}")
    with open(path, "wb") as fh:
        fh.write(raw)
    _subject_path[0] = path
    _log(f"Sujeto guardado: _subject.{ext} ({len(raw) // 1024} KB)")
    return path


def set_subject_file(file_storage, filename: str) -> str:
    ext = Path(filename).suffix.lower() or ".jpg"
    path = str(get_whisk_downloads_dir() / f"_subject{ext}")
    file_storage.save(path)
    _subject_path[0] = path
    _log(f"Sujeto guardado (multipart): {path}")
    return path


def clear_subject() -> None:
    _subject_path[0] = None


def run_prompts(prompts: list[str], slots: int, repeat: int, output_dir: str) -> dict:
    if _state["running"]:
        raise RuntimeError("Ya hay una corrida en progreso")
    if not prompts:
        raise ValueError("Sin prompts - escribe al menos uno")

    slots = max(1, slots)
    repeat = max(1, repeat)
    out_dir = output_dir.strip() or str(get_whisk_downloads_dir())

    import uuid
    raw_prompts = [p for p in prompts for _ in range(repeat)]
    all_prompts = [p + f" [v{i + 1}-{uuid.uuid4().hex[:6]}]" for i, p in enumerate(raw_prompts)]
    total = len(all_prompts)

    if _subject_path[0] and not os.path.isfile(str(_subject_path[0])):
        _subject_path[0] = None

    os.makedirs(out_dir, exist_ok=True)
    for f in Path(out_dir).glob("img_*"):
        try:
            f.unlink()
        except Exception:
            pass

    _stop_event.clear()
    with _lock:
        prev = {i: {"logged_in": _state["accounts"][i].get("logged_in", False),
                     "user": _state["accounts"][i].get("user", "")}
                for i in range(NUM_ACCOUNTS)}
        _state.update({
            "running": True, "step": "running", "progress": 0, "total": total,
            "images_saved": 0, "log": [], "output_dir": out_dir, "last_error": None,
            "accounts": [{"id": i, "status": "idle", "slots": [], "jobs": 0,
                          "logged_in": prev[i]["logged_in"], "user": prev[i]["user"]}
                         for i in range(NUM_ACCOUNTS)],
        })

    threading.Thread(target=_run_batch, args=(all_prompts, slots, _subject_path[0], out_dir), daemon=True).start()
    return {"total": total, "message": f"{total} imagen(es) en cola - {slots} slot(s)"}


def pollination_generate(prompts: list[str], ratio: str, width: int, height: int, output_dir: str) -> dict:
    """Proxy al webhook n8n de Pollination; guarda img_* en la misma carpeta que Whisk."""
    if not prompts:
        raise ValueError("Sin prompts")

    out_dir = output_dir.strip() or str(get_whisk_downloads_dir())
    os.makedirs(out_dir, exist_ok=True)

    payload = {"prompts": prompts, "ratio": ratio, "width": width, "height": height}
    r = requests.post(POLLINATION_WEBHOOK, json=payload, timeout=600)
    r.raise_for_status()
    try:
        result = r.json()
    except ValueError as exc:
        ct = (r.headers.get("content-type") or "").lower()
        raise RuntimeError(f"n8n no devolvio JSON valido (content-type={ct}, body={r.text[:400]})") from exc

    if isinstance(result, dict) and "images" in result:
        images_list = result["images"]
    elif isinstance(result, list):
        images_list = result
    else:
        images_list = [result]

    def _extract_b64_mime(item):
        if not isinstance(item, dict):
            return None, None
        j = item.get("json") or {}
        return item.get("base64") or j.get("base64"), item.get("mime") or j.get("mime") or "image/png"

    def _next_img_index() -> int:
        mx = 0
        if not Path(out_dir).exists():
            return 1
        for f in Path(out_dir).glob("img_*"):
            try:
                mx = max(mx, int(f.stem.split("_", 1)[1]))
            except (ValueError, IndexError):
                pass
        return mx + 1

    idx = _next_img_index()
    saved = []
    for item in images_list:
        b64, mime = _extract_b64_mime(item)
        if not b64:
            continue
        b64 = "".join(str(b64).split())
        try:
            raw_img = base64.b64decode(b64, validate=False)
        except Exception:
            continue
        m = (mime or "image/png").lower()
        ext = ".jpg" if ("jpeg" in m or "jpg" in m) else ".webp" if "webp" in m else ".png"
        fname = f"img_{idx:05d}{ext}"
        Path(out_dir, fname).write_bytes(raw_img)
        saved.append(fname)
        idx += 1

    if not saved:
        raise RuntimeError("n8n no devolvio imagenes base64 validas")

    with _lock:
        _state["output_dir"] = out_dir
    return {"images": saved, "count": len(saved), "output_dir": out_dir}


threading.Thread(target=lambda: (time.sleep(1.2), sync_profile_rows()), daemon=True).start()
