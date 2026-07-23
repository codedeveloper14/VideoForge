import os
import threading
import time

from src.domain.services.account_slot_assigner import SlotAssigner
from src.infrastructure.ai_providers import gentube_bridge, gentube_service
from src.utils.logger import get_logger
from src.utils.paths import get_gentube_cookies_dir

logger = get_logger(__name__)

_state = {
    "running": False,
    "step": "idle",
    "progress": 0,
    "total": 0,
    "images_saved": 0,
    "log": [],
    "output_dir": "",
    "last_error": "",
    "started_at": 0.0,
    "last_activity": 0.0,
    "accounts": [
        {"id": i, "logged_in": False, "user": "", "has_cookie": False}
        for i in range(gentube_service.NUM_ACCOUNTS)
    ],
}
_lock = threading.Lock()
_stop_event = threading.Event()

# Salvavidas: si un batch se cuelga (browser sin responder, red caida) sin
# levantar excepcion, "running" quedaria en True para siempre y el usuario nunca
# podria reintentar. Dos condiciones lo liberan, la que ocurra primero (misma
# logica que flow_animation_service._release_if_stale): inactividad real (sin
# lineas de log nuevas) o un techo absoluto de seguridad.
INACTIVITY_TIMEOUT_SECONDS = 180
MAX_RUN_SECONDS = 21600  # 6h -- backstop puro, la inactividad ya cubre el caso "colgado"


def _release_if_stale() -> None:
    went_stale = False
    reason = ""
    with _lock:
        started = _state.get("started_at") or 0.0
        last_activity = _state.get("last_activity") or started
        now = time.time()
        if _state["running"] and started:
            if last_activity and (now - last_activity) > INACTIVITY_TIMEOUT_SECONDS:
                reason = "Generacion sin actividad - liberada automaticamente"
            elif (now - started) > MAX_RUN_SECONDS:
                reason = "Tiempo de espera agotado"
        if reason:
            _state.update(running=False, step="idle", last_error=reason)
            _stop_event.set()
            went_stale = True
    if went_stale:
        _log(f"[gentube] Lock de generacion liberado automaticamente ({reason})")


def _log(msg: str) -> None:
    with _lock:
        _state["log"].append(msg)
        _state["last_activity"] = time.time()
        if len(_state["log"]) > 600:
            _state["log"] = _state["log"][-600:]
    logger.info("[gentube] %s", msg)


def _apply_sync_results(results: dict[int, dict]) -> None:
    with _lock:
        for i in range(gentube_service.NUM_ACCOUNTS):
            row = results.get(i, {"logged_in": False, "user": ""})
            _state["accounts"][i]["logged_in"] = row["logged_in"]
            _state["accounts"][i]["user"] = row.get("user", "")
            _state["accounts"][i]["has_cookie"] = row["logged_in"]


def sync_profiles_async() -> None:
    threading.Thread(target=lambda: _apply_sync_results(gentube_service.sync_profiles()), daemon=True).start()


# ── Deteccion automatica de sesion via la extension (bridge de Chrome) ───────────
# gentube_bridge.py detecta la cookie de Clerk via background.js (chrome.cookies,
# ver el comentario de ese modulo) y avisa aca en cuanto hay una sesion valida --
# igual que Flow, sin que el usuario tenga que pegar ninguna cookie a mano.
_slot_assigner: SlotAssigner | None = None
# Serializa TODO el cuerpo de _on_bridge_session -- el alarm de la extension
# corre cada 30s, pero un service worker que se reinicia a mitad de sesion (o
# un doble disparo) puede generar dos llamadas casi simultaneas. Sin este lock,
# una lectura de cookie_path(idx) durante la ventana de otra escritura al MISMO
# archivo podia devolver contenido truncado, hacer fallar la reconciliacion de
# identidad y terminar creando un slot "fantasma" duplicado para la misma
# cuenta real (bug confirmado en produccion 2026-07-23).
_bridge_session_lock = threading.Lock()


def _get_slot_assigner() -> SlotAssigner:
    global _slot_assigner
    if _slot_assigner is None:
        _slot_assigner = SlotAssigner(
            sidecar_dir=get_gentube_cookies_dir(),
            prefix="gt_account",
            num_slots=gentube_service.NUM_ACCOUNTS,
            valid_hash_prefix="gt:",
        )
    return _slot_assigner


def _find_slot_for_existing_identity(email: str) -> int | None:
    """Reconcilia con cuentas guardadas en disco ANTES de que existiera este bridge
    (sin sidecar hash->slot, p. ej. una cookie pegada a mano hace tiempo) -- si
    alguna YA es la misma cuenta real (mismo email/sub que probe_session ya
    decodifica), hay que reusar ESE slot en vez de crear uno nuevo. Sin este
    chequeo, la primera vez que el bridge detecta una cuenta que el usuario ya
    habia logueado antes, la trata como "otra cuenta" (el slot con la cookie
    vieja aparece "ocupado" por alguien mas) y termina duplicando la MISMA sesion
    real en dos slots distintos."""
    if not email:
        return None
    for i in range(gentube_service.NUM_ACCOUNTS):
        existing = gentube_service.read_cookie(i)
        if not existing:
            continue
        existing_probe = gentube_service.probe_session(existing)
        if existing_probe.get("ok") and existing_probe.get("user") == email:
            return i
    return None


def _write_cookie_atomic(idx: int, cookie: str) -> None:
    """Escritura atomica (temp + os.replace) -- un lector concurrente (p. ej.
    check-login/sync_profiles corriendo en su propio hilo) nunca debe poder ver
    el archivo a mitad de escribir."""
    path = gentube_service.cookie_path(idx)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(cookie, encoding="utf-8")
    os.replace(tmp, path)


def _on_bridge_session(account_hash: str, meta: dict) -> None:
    cookie = meta.get("cookie", "")
    email = meta.get("email", "")
    if not cookie:
        return
    with _bridge_session_lock:
        idx = _find_slot_for_existing_identity(email)
        if idx is not None:
            # Reconciliado con una cuenta que ya existia en disco -- registrar el
            # atajo en memoria para que la PROXIMA deteccion de este mismo hash no
            # tenga que volver a escanear el disco entero (mas rapido y elimina la
            # ventana de carrera con escrituras concurrentes).
            _get_slot_assigner().bind(account_hash, idx)
        else:
            idx = _get_slot_assigner().assign_slot(
                account_hash, slot_taken_on_disk=lambda i: bool(gentube_service.read_cookie(i))
            )
        if idx is None:
            _log(
                f"[WARNING] Sin slots libres (limite {gentube_service.NUM_ACCOUNTS}) - "
                f"sesion de {email or 'gentube.app'} descartada"
            )
            return
        try:
            _write_cookie_atomic(idx, cookie)
        except Exception:
            return
        _get_slot_assigner().write_sidecar(idx, account_hash, {"email": email})
        with _lock:
            was_logged_in = _state["accounts"][idx]["logged_in"]
            _state["accounts"][idx].update({"logged_in": True, "user": email, "has_cookie": True})
        if not was_logged_in:
            _log(f"[C{idx}] Sesion detectada automaticamente via extension: {email or 'gentube.app'}")


gentube_bridge.add_session_listener(_on_bridge_session)


def get_status() -> dict:
    _release_if_stale()
    with _lock:
        st = {
            "running": _state["running"],
            "step": _state["step"],
            "progress": _state["progress"],
            "total": _state["total"],
            "images_saved": _state["images_saved"],
            "log": list(_state["log"]),
            "output_dir": _state["output_dir"],
            "last_error": _state.get("last_error", ""),
            "accounts": [dict(a) for a in _state["accounts"]],
        }
    st["playwright_ok"] = gentube_service.playwright_available()
    ext_accounts = gentube_bridge.connected_accounts()
    st["ext_connected"] = len(ext_accounts)
    st["ext_accounts"] = ext_accounts
    return st


def check_login() -> list[dict]:
    _apply_sync_results(gentube_service.sync_profiles())
    with _lock:
        return [{"id": a["id"], "logged_in": a["logged_in"], "user": a["user"]} for a in _state["accounts"]]


def start_login(account_id: int, cookie: str = "") -> dict:
    account_id = max(0, min(account_id, gentube_service.NUM_ACCOUNTS - 1))
    cookie = (cookie or "").strip()
    if cookie:
        probe = gentube_service.probe_session(cookie)
        if not probe["ok"]:
            raise ValueError("Cookie invalida o expirada - verifica que hayas copiado la cookie correcta.")
        gentube_service.cookie_path(account_id).write_text(cookie, encoding="utf-8")
        _log(f"  [C{account_id}] [OK] Cookie guardada directamente - {probe.get('user', '')}")
        sync_profiles_async()
        return {"ok": True, "user": probe.get("user", "")}

    threading.Thread(target=gentube_service.playwright_login, args=(account_id, _log), daemon=True).start()
    return {"ok": True}


def start_run(
    prompts: list[str],
    slots: int,
    repeat: int,
    output_dir: str,
    ratio: str,
    quality: str,
    browser_mode: str = "chromium",
) -> dict:
    global _stop_event
    prompts = [p for p in prompts if str(p).strip()]
    slots = max(1, min(8, slots))
    repeat = max(1, min(20, repeat))
    output_dir = (output_dir or "").strip()
    if browser_mode not in ("chrome", "chromium"):
        browser_mode = "chromium"

    if not prompts:
        raise ValueError("Sin prompts")
    if not output_dir:
        raise ValueError("Sin output_dir")

    _release_if_stale()
    with _lock:
        if _state.get("running"):
            raise RuntimeError("Ya hay una generacion en curso")
        _state["log"] = []
        _state["running"] = True
        _state["step"] = "starting"
        _state["progress"] = 0
        _state["total"] = len(prompts) * repeat
        _state["images_saved"] = 0
        _state["last_error"] = ""
        _state["started_at"] = time.time()
        _state["last_activity"] = time.time()

    _stop_event = threading.Event()
    stop_event = _stop_event

    def _run_and_release():
        try:
            gentube_service.run_batch(
                prompts, slots, repeat, output_dir, _state, _lock, stop_event, _log, browser_mode=browser_mode
            )
        except Exception as exc:
            logger.exception("[gentube] error fatal en batch")
            with _lock:
                _state.update(running=False, step="idle", last_error=str(exc))
            _log(f"[gentube] ERROR fatal en batch: {exc}")

    threading.Thread(target=_run_and_release, daemon=True).start()
    return {"ok": True, "message": f"Iniciado {len(prompts) * repeat} imagenes"}


def stop() -> None:
    _stop_event.set()
    with _lock:
        _state.update(running=False, step="idle", progress=0, total=0)


def reset() -> None:
    global _stop_event
    _stop_event = threading.Event()
    _stop_event.set()
    with _lock:
        _state.update(running=False, step="idle", progress=0, total=0, images_saved=0, log=[])


# out_dir explicito (siempre preferido) -- _state["output_dir"] solo se actualiza
# cuando efectivamente CORRE un lote de generacion, asi que sin esto, cambiar de
# proyecto activo sin haber generado todavia en el nuevo mostraba la galeria/
# carpeta/imagen del ULTIMO proyecto donde se genero, no la del proyecto que se
# esta viendo en pantalla ahora mismo.
def _resolve_dir(out_dir: str | None) -> str:
    d = (out_dir or "").strip()
    if d:
        return d
    return (_state.get("output_dir") or "").strip()


def list_images(out_dir: str | None = None) -> dict:
    d = _resolve_dir(out_dir)
    if not d or not os.path.isdir(d):
        return {"images": [], "count": 0}
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    imgs = sorted(
        (f for f in os.listdir(d) if os.path.splitext(f)[1].lower() in exts),
        key=lambda f: os.path.getmtime(os.path.join(d, f)),
        reverse=True,
    )
    return {"images": imgs, "count": len(imgs)}


def get_image_path(name: str, out_dir: str | None = None) -> str | None:
    d = _resolve_dir(out_dir)
    if not d:
        return None
    path = os.path.join(d, os.path.basename(name))
    return path if os.path.isfile(path) else None


def clear_images(out_dir: str | None = None) -> None:
    d = _resolve_dir(out_dir)
    if not d or not os.path.isdir(d):
        return
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    for f in os.listdir(d):
        if os.path.splitext(f)[1].lower() in exts:
            try:
                os.remove(os.path.join(d, f))
            except Exception:
                pass
    with _lock:
        _state["images_saved"] = 0
