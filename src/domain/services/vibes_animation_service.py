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

# Estado indexado por proyecto (sanitize_name) -- antes era un unico dict de
# modulo (_state): lanzar un lote para un proyecto B pisaba _state["project_dir"]/
# ["total"]/["done"] del proyecto A, y ambos seguian escribiendo en la MISMA
# lista de log_lines mientras corrian en paralelo -- el mismo bug que ya
# reparamos en Qwen. Con _batches cada proyecto tiene su propio log_lines/
# cancel_event/project_dir/total/done.
_batches: dict[str, dict] = {}
_batches_lock = threading.Lock()
_last_project: str | None = None


def _new_batch_state() -> dict:
    return {
        "running": False,
        "log_lines": [],
        "finished": False,
        "project_dir": None,
        "total": 0,
        "done": 0,
        "cancel_event": None,
    }


def _get_batch(name: str) -> dict:
    with _batches_lock:
        return _batches.setdefault(name, _new_batch_state())


def _resolve_name(project_name: str) -> str:
    name = sanitize_name(project_name or "")
    if name:
        return name
    return _last_project or ""


def _append_log(batch: dict, msg: str) -> None:
    line = f"[VIBES] {msg}"
    with _batches_lock:
        batch["log_lines"].append(line)
        if len(batch["log_lines"]) > _MAX_LOG_LINES:
            batch["log_lines"] = batch["log_lines"][-_MAX_LOG_LINES:]


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
    logger.info("[VIBES] Abriendo login de Vibes -- inicia sesion en la ventana y esperá a que se cierre sola.")

    def _run():
        vibes_client.login_account_managed(_ACCOUNT_IDX, log=lambda msg: logger.info("[VIBES] %s", msg))

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
            logger.info("[VIBES] [OK] Chrome abierto en vibes.ai -- deja la pestaña abierta mientras generas.")
            proc.wait()
            logger.info("[VIBES] Chrome (Vibes) cerrado.")
        except Exception as exc:
            logger.info("[VIBES] [ERROR] Lanzando Chrome: %s", exc)

    threading.Thread(target=_monitor, daemon=True).start()
    return {"ok": True, "message": "Chrome abriendo en vibes.ai"}


# ─────────────────────────────────────────────────────────────────
# Generacion por lote -- prompt -> N batches (Vibes no anima imagenes
# subidas: genera imagen+video en el mismo batch a partir del prompt).
# ─────────────────────────────────────────────────────────────────


def start_batch(
    project_name: str,
    prompt: str,
    slots: int,
    video_params: dict,
    timeout_sec: int,
    ref_image_b64: str | None = None,
) -> dict:
    global _last_project

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
    # Cada batch trae hasta 4 videos si batch_variation esta activo (default) --
    # "total" tiene que contar videos, no tandas, o la barra de progreso marca
    # "100%" con 1/4 de lo que en realidad se genero por tanda.
    n_variations = 4 if video_params.get("batch_variation", True) else 1
    cancel_ev = threading.Event()
    batch = _get_batch(name)
    # Si el MISMO proyecto ya tenia un lote corriendo, cancelalo antes de pisar
    # su estado -- nunca toca el cancel_event de otro proyecto en paralelo.
    old_cancel = batch.get("cancel_event")
    if old_cancel and not batch.get("finished", True):
        old_cancel.set()
    batch.update(
        {
            "running": True,
            "log_lines": [],
            "finished": False,
            "project_dir": str(proj_dir),
            "total": slots * n_variations,
            "done": 0,
            "cancel_event": cancel_ev,
        }
    )
    _last_project = name
    threading.Thread(
        target=_batch_worker,
        args=(name, vid_dir, prompt.strip(), slots, video_params, timeout_sec, cancel_ev, ref_image_b64),
        daemon=True,
    ).start()

    return {
        "ok": True,
        "pid": f"vibes-{int(time.time())}",
        "project_dir": str(proj_dir),
        "project_name": name,
    }


def _batch_worker(
    name: str,
    vid_dir: Path,
    prompt: str,
    slots: int,
    video_params: dict,
    timeout_sec: int,
    cancel_ev: threading.Event,
    ref_image_b64: str | None = None,
) -> None:
    batch = _get_batch(name)

    def log(msg: str) -> None:
        _append_log(batch, msg)

    cookies = vibes_client.load_cookies(_ACCOUNT_IDX) or []
    project_id = vibes_client.ensure_project(cookies, _ACCOUNT_IDX, log=log)
    if not project_id:
        log("[ERROR] No se pudo resolver/crear un proyecto en Vibes.")
        batch.update(finished=True, running=False)
        return

    log(f"{slots} batch(es) - proyecto Vibes {project_id}")

    ref_image: dict | None = None
    if ref_image_b64:
        import base64

        log("Imagen de referencia incluida - subiendo a Vibes...")
        mime = "image/jpeg"
        raw_b64 = ref_image_b64
        if "," in ref_image_b64:
            header, raw_b64 = ref_image_b64.split(",", 1)
            if "image/png" in header:
                mime = "image/png"
            elif "image/webp" in header:
                mime = "image/webp"
        ext = {"image/png": "png", "image/webp": "webp"}.get(mime, "jpg")
        try:
            image_bytes = base64.b64decode(raw_b64)
        except Exception as exc:
            log(f"[WARNING] Imagen de referencia invalida ({exc}) - generando sin referencia")
            image_bytes = None
        if image_bytes:
            upload_result = vibes_client.upload_reference_image_via_bridge(
                image_bytes, filename=f"reference.{ext}", log=log
            )
            if upload_result.get("error"):
                log(f"[WARNING] Subida de imagen de referencia fallo: {upload_result['error']} - generando sin referencia")
            else:
                ref_image = {
                    "media_ent_id": upload_result["media_ent_id"],
                    "cdn_url": upload_result["cdn_url"],
                }

    videos_done = 0
    for i in range(slots):
        if cancel_ev.is_set():
            log("Detenido por el usuario.")
            break
        log(f"[{i + 1}/{slots}] generando...")
        result = vibes_client.generate_video_via_bridge(
            prompt,
            project_id=project_id,
            out_dir=str(vid_dir),
            cookie_list=cookies,
            timeout_sec=timeout_sec,
            slot_id=i,
            ref_image=ref_image,
            log=log,
            **video_params,
        )
        n_videos = len(result.get("videos", []))
        if result.get("error"):
            log(f"[ERROR] [{i + 1}/{slots}] {result['error']}")
        else:
            log(f"[OK] [{i + 1}/{slots}] {n_videos} video(s)")
        videos_done += n_videos
        with _batches_lock:
            batch["done"] = videos_done

    batch.update(finished=True, running=False)
    log(f"Vibes finalizado: {videos_done}/{batch['total']} video(s) generados ({slots} tanda(s) procesadas).")


def stop(project_name: str = "") -> None:
    """Cancela solo el lote del proyecto indicado -- nunca toca el cancel_event
    de otro proyecto corriendo en paralelo."""
    name = _resolve_name(project_name)
    if not name:
        return
    batch = _get_batch(name)
    ev = batch.get("cancel_event")
    if ev:
        ev.set()
    batch.update(running=False, finished=True)
    _append_log(batch, "Detener recibido.")


def get_log_state(offset: int, project_name: str = "") -> dict:
    name = _resolve_name(project_name)
    if not name:
        return {"lines": [], "next_offset": offset, "finished": True}
    batch = _get_batch(name)
    lines = batch["log_lines"][offset:]
    return {
        "lines": lines,
        "next_offset": offset + len(lines),
        "finished": bool(batch["finished"]),
    }


def list_videos(project_name: str) -> dict:
    if not project_name:
        return {"videos": [], "total": 0, "done": 0, "project_dir": "", "project_name": ""}
    name = sanitize_name(project_name)
    videos = sorted(f.name for f in project_repository.list_videos(name))
    batch = _batches.get(name)
    with _batches_lock:
        total = (batch.get("total") or 0) if batch else 0
        done = (batch.get("done") or 0) if batch else 0
    return {
        "videos": videos,
        "total": total,
        "done": done,
        "project_dir": str(project_repository.project_dir(name)),
        "project_name": name,
    }


def _last_project_dir() -> str | None:
    if not _last_project:
        return None
    batch = _batches.get(_last_project)
    return batch.get("project_dir") if batch else None


def get_video_path(project_name: str, filename: str) -> Path | None:
    if project_name:
        return project_repository.resolve_safe_file(project_name, "video", filename)
    proj_dir = _last_project_dir()
    if proj_dir:
        video_dir = Path(proj_dir) / "video"
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
    proj_dir = _last_project_dir()
    if proj_dir:
        return Path(proj_dir) / "video"
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
    if project_name:
        proj_label = sanitize_name(project_name)
    else:
        proj_dir = _last_project_dir()
        proj_label = Path(proj_dir).name if proj_dir else "vibes"
    return buf, f"{proj_label}_videos_vibes.zip"


def open_videos_folder(project_name: str) -> Path:
    video_dir = _active_video_dir(project_name)
    if not video_dir:
        raise ValueError("Sin proyecto activo")
    video_dir.mkdir(parents=True, exist_ok=True)
    open_folder(str(video_dir))
    return video_dir
