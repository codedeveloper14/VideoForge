import threading
import time
import zipfile
from io import BytesIO
from pathlib import Path

from src.domain.services.project_service import sanitize_name
from src.infrastructure.ai_providers import chrome_launcher, vibes_client
from src.infrastructure.ai_providers.meta_chrome_process import launch_chrome_with_extension
from src.infrastructure.storage import project_repository
from src.utils.logger import get_logger
from src.utils.platform_utils import open_folder

logger = get_logger(__name__)

_MAX_LOG_LINES = 1500
# Vibes hoy es una sola sesion por cliente (VIBES_ACCOUNT_HASH fijo en vibes_client,
# ver su comentario) -- a diferencia de Meta/Grok/Qwen no hay rotacion de cuentas.
_ACCOUNT_IDX = 0
_ACCOUNT_NAME = "vibes-default"

_state = {
    "running": False,
    "log_lines": [],
    "finished": False,
    "project_dir": None,
    "total": 0,
    "done": 0,
    "cancel_event": None,
}
_lock = threading.Lock()


def _log(msg: str) -> None:
    line = f"[VIBES] {msg}"
    with _lock:
        _state["log_lines"].append(line)
        if len(_state["log_lines"]) > _MAX_LOG_LINES:
            _state["log_lines"] = _state["log_lines"][-_MAX_LOG_LINES:]


# ─────────────────────────────────────────────────────────────────
# Sesion
# ─────────────────────────────────────────────────────────────────


def list_sessions() -> list[dict]:
    cookies = vibes_client.load_cookies(_ACCOUNT_IDX)
    if not cookies:
        return [{"name": _ACCOUNT_NAME, "active": False, "user": "sin sesion"}]
    active = vibes_client.check_session(cookies)
    return [{"name": _ACCOUNT_NAME, "active": active, "user": "vibes.ai" if active else "sesion expirada"}]


def start_account_login(_account_name: str) -> str:
    """Login real contra vibes.ai (OIDC), a diferencia del flujo viejo de Meta que
    abria meta.ai -- eso es lo que dejaba al usuario trabado, nunca llegaba a
    autenticar contra el dominio correcto."""
    _log("Abriendo login de Vibes -- inicia sesion en la ventana y esperá a que se cierre sola.")

    def _run():
        vibes_client.login_account_managed(_ACCOUNT_IDX, log=_log)

    threading.Thread(target=_run, daemon=True).start()
    return _ACCOUNT_NAME


def delete_session(_account_name: str) -> None:
    vibes_client.cookie_path(_ACCOUNT_IDX).unlink(missing_ok=True)


def launch_chrome() -> dict:
    """Abre una ventana de Chrome real con la extension cargada en vibes.ai.
    Necesario porque generate_video_via_bridge() requiere una pestana real conectada
    al bridge -- el fetch() automatizado (Playwright/requests) siempre es rechazado
    con "Generation failed to start" aunque la sesion sea valida (ver vibes_client.
    generate_video)."""
    exe = chrome_launcher.find_chromium_exe()
    if not exe:
        raise FileNotFoundError("Chrome/Edge no encontrado. Instala Google Chrome.")

    ext_dir = chrome_launcher.get_extension_dir()
    profile_dir = str(vibes_client.profile_dir(_ACCOUNT_IDX))
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    def _monitor():
        try:
            proc = launch_chrome_with_extension(exe, profile_dir, [str(ext_dir)], ["https://www.vibes.ai/"])
            _log("[OK] Chrome abierto en vibes.ai -- deja la pestaña abierta mientras generas.")
            proc.wait()
            _log("Chrome (Vibes) cerrado.")
        except Exception as exc:
            _log(f"[ERROR] Lanzando Chrome: {exc}")

    threading.Thread(target=_monitor, daemon=True).start()
    return {"ok": True, "message": "Chrome abriendo en vibes.ai"}


# ─────────────────────────────────────────────────────────────────
# Generacion por lote -- prompt -> N batches (Vibes no anima imagenes
# subidas: genera imagen+video en el mismo batch a partir del prompt).
# ─────────────────────────────────────────────────────────────────


def start_batch(project_name: str, prompt: str, slots: int, video_params: dict, timeout_sec: int) -> dict:
    name = sanitize_name(project_name) if project_name else ""
    if not name:
        raise ValueError("Selecciona un proyecto antes de generar.")
    if not prompt or not prompt.strip():
        raise ValueError("Escribe un prompt antes de generar.")

    cookies = vibes_client.load_cookies(_ACCOUNT_IDX)
    if not cookies or not vibes_client.check_session(cookies):
        raise ValueError("Inicia sesión en Vibes primero (botón Login del panel de sesiones).")

    proj_dir = project_repository.create_project(name)
    vid_dir = proj_dir / "video"
    vid_dir.mkdir(parents=True, exist_ok=True)

    slots = max(1, min(slots, 12))
    cancel_ev = threading.Event()
    _state.update(
        {
            "running": True,
            "log_lines": [],
            "finished": False,
            "project_dir": str(proj_dir),
            "total": slots,
            "done": 0,
            "cancel_event": cancel_ev,
        }
    )
    threading.Thread(
        target=_batch_worker,
        args=(vid_dir, prompt.strip(), slots, video_params, timeout_sec, cancel_ev),
        daemon=True,
    ).start()

    return {
        "ok": True,
        "pid": f"vibes-{int(time.time())}",
        "project_dir": str(proj_dir),
        "project_name": name,
    }


def _batch_worker(
    vid_dir: Path,
    prompt: str,
    slots: int,
    video_params: dict,
    timeout_sec: int,
    cancel_ev: threading.Event,
) -> None:
    cookies = vibes_client.load_cookies(_ACCOUNT_IDX) or []
    project_id = vibes_client.ensure_project(cookies, _ACCOUNT_IDX, log=_log)
    if not project_id:
        _log("[ERROR] No se pudo resolver/crear un proyecto en Vibes.")
        _state.update(finished=True, running=False)
        return

    _log(f"{slots} batch(es) - proyecto Vibes {project_id}")

    for i in range(slots):
        if cancel_ev.is_set():
            _log("Detenido por el usuario.")
            break
        _log(f"[{i + 1}/{slots}] generando...")
        result = vibes_client.generate_video_via_bridge(
            prompt,
            project_id=project_id,
            out_dir=str(vid_dir),
            cookie_list=cookies,
            timeout_sec=timeout_sec,
            slot_id=i,
            log=_log,
            **video_params,
        )
        if result.get("error"):
            _log(f"[ERROR] [{i + 1}/{slots}] {result['error']}")
        else:
            _log(f"[OK] [{i + 1}/{slots}] {len(result.get('videos', []))} video(s)")
        with _lock:
            _state["done"] = i + 1

    _state.update(finished=True, running=False)
    _log(f"Vibes finalizado: {_state['done']}/{slots} batch(es) procesados.")


def stop() -> None:
    ev = _state.get("cancel_event")
    if ev:
        ev.set()
    _state.update(running=False, finished=True)
    _log("Detener recibido.")


def get_log_state(offset: int) -> dict:
    lines = _state["log_lines"][offset:]
    return {
        "lines": lines,
        "next_offset": offset + len(lines),
        "finished": bool(_state["finished"]),
    }


def list_videos(project_name: str) -> dict:
    if not project_name:
        return {"videos": [], "total": 0, "done": 0, "project_dir": "", "project_name": ""}
    name = sanitize_name(project_name)
    videos = sorted(f.name for f in project_repository.list_videos(name))
    with _lock:
        total = _state.get("total") or 0
        done = _state.get("done") or 0
    return {
        "videos": videos,
        "total": total,
        "done": done,
        "project_dir": str(project_repository.project_dir(name)),
        "project_name": name,
    }


def get_video_path(project_name: str, filename: str) -> Path | None:
    if project_name:
        return project_repository.resolve_safe_file(project_name, "video", filename)
    if _state["project_dir"]:
        video_dir = Path(_state["project_dir"]) / "video"
        candidate = (video_dir / filename).resolve()
        try:
            candidate.relative_to(video_dir.resolve())
        except ValueError:
            return None
        return candidate
    return None


def _active_video_dir(project_name: str) -> Path | None:
    if project_name:
        return project_repository.project_dir(project_name) / "video"
    if _state["project_dir"]:
        return Path(_state["project_dir"]) / "video"
    return None


def build_videos_zip(project_name: str) -> tuple[BytesIO, str] | None:
    video_dir = _active_video_dir(project_name)
    if not video_dir:
        return None
    videos = sorted(video_dir.glob("*.mp4")) if video_dir.exists() else []
    if not videos:
        return None
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for v in videos:
            zf.write(str(v), v.name)
    buf.seek(0)
    proj_label = sanitize_name(project_name) if project_name else Path(_state["project_dir"]).name
    return buf, f"{proj_label}_videos_vibes.zip"


def open_videos_folder(project_name: str) -> Path:
    video_dir = _active_video_dir(project_name)
    if not video_dir:
        raise ValueError("Sin proyecto activo")
    video_dir.mkdir(parents=True, exist_ok=True)
    open_folder(str(video_dir))
    return video_dir
