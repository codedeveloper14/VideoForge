import base64
import mimetypes
import threading
import time
import uuid as uuid_lib
import zipfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import requests

from src.domain.services.project_service import sanitize_name
from src.infrastructure.ai_providers import chrome_launcher, vibes_bridge, vibes_client
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
    if not vibes_client.check_session(cookies):
        return [{"name": _ACCOUNT_NAME, "active": False, "user": "sesion expirada"}]
    username = vibes_client.get_account_username(cookies)
    return [{"name": _ACCOUNT_NAME, "active": True, "user": username or "vibes.ai"}]


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
    OJO: www.vibes.ai es el dominio verificado para la cookie de sesion (ver
    vibes_client.py, comentario sobre BASE_URL) -- vibes_bridge.js (el script nuevo
    que genera via DOM) esta registrado en manifest.json solo para "vibes.ai/*" sin
    www; si ese mismatch resulta ser un problema real (necesita confirmarse en vivo
    con DevTools), lo correcto es ampliar el match de manifest.json a www tambien,
    NO mover esto a la URL sin www (rompería la cookie de sesion, ver mismo comentario)."""
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
    timeout_sec: int,
    images: list[tuple[str, object]] | None = None,
    ref_image_b64: str | None = None,
) -> dict:
    """`images`, si se pasa, es una lista de (filename, file_storage) -- una imagen
    del proyecto por job, "slots" videos c/u (mismo patron que Grok/Qwen). Sin
    imagenes, cae al modo de siempre: 1 prompt (+ ref_image_b64 opcional) -> "slots"
    variaciones."""
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

    images_meta: list[dict] = []
    if images:
        img_dir = proj_dir / "imagen"
        img_dir.mkdir(parents=True, exist_ok=True)
        for i, (filename, file_storage) in enumerate(images):
            ext = Path(filename or "").suffix or ".jpg"
            # Nombre unico por indice (no por nombre original) -- evita que dos
            # imagenes subidas con el mismo nombre colapsen en un solo archivo.
            dest = img_dir / f"{i + 1:05d}_src{ext}"
            file_storage.save(str(dest))
            images_meta.append({"index": i + 1, "name": filename or f"{i + 1:05d}.jpg", "path": str(dest)})

    total = len(images_meta) * slots if images_meta else slots
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
            "total": total,
            "done": 0,
            "cancel_event": cancel_ev,
        }
    )
    _last_project = name
    if images_meta:
        threading.Thread(
            target=_batch_worker_images,
            args=(name, vid_dir, prompt.strip(), slots, timeout_sec, cancel_ev, images_meta),
            daemon=True,
        ).start()
    else:
        threading.Thread(
            target=_batch_worker,
            args=(name, vid_dir, prompt.strip(), slots, timeout_sec, cancel_ev, ref_image_b64),
            daemon=True,
        ).start()

    return {
        "ok": True,
        "pid": f"vibes-{int(time.time())}",
        "project_dir": str(proj_dir),
        "project_name": name,
    }


def _wait_for_connected_accounts(cancel_ev: threading.Event, log) -> list[str]:
    connected = vibes_bridge.connected_accounts()
    if connected:
        return connected
    log("Esperando a que la extension se conecte (abre Chrome en vibes.ai, max 45s)...")
    wait_start = time.time()
    while time.time() - wait_start < 45:
        if cancel_ev.is_set():
            return []
        connected = vibes_bridge.connected_accounts()
        if connected:
            log(f"[OK] Extension conectada en {int(time.time() - wait_start)}s")
            return connected
        time.sleep(1)
    log(
        "[ERROR] La extension no se conecto. Abri Chrome (boton de abajo), "
        "inicia sesion en vibes.ai y esperá a que se registre."
    )
    return []


_JOB_RETRY_DELAY_SEC = 15.0


def _run_job_via_bridge(
    job: dict,
    timeout_sec: float,
    cancel_ev: threading.Event,
    log: Callable[[str], None] = lambda _msg: None,
) -> dict | None:
    """Encola `job` en vibes_bridge.py (consumido por vibes_bridge.js en la pestaña
    real) y espera su resultado. vibes_bridge.js ya reintenta las fallas cortas
    (500 esporadicos, condiciones de carrera de segundos) contra vibes.ai, pero un
    job que agota esos reintentos cortos se perdia del todo -- vibes.ai devuelve 500
    con frecuencia bajo su propia carga (ver comentarios en vibes_bridge.js), asi que
    una espera mas larga antes de reencolar el job COMPLETO desde cero (una sola vez)
    recupera casos que los reintentos cortos del lado del navegador no alcanzan a
    cubrir. Se reintenta tanto si vino un error explicito como si nunca llego
    respuesta (timeout) -- ambos son sintoma de la misma inestabilidad del lado de
    vibes.ai."""
    result = None
    for attempt in range(2):
        request_id = str(uuid_lib.uuid4())
        job_with_id = dict(job, requestId=request_id)
        event = vibes_bridge.register_result_waiter(request_id)
        vibes_bridge.enqueue_request(job_with_id)

        deadline = time.time() + timeout_sec + 30
        result = None
        while time.time() < deadline:
            if cancel_ev.is_set():
                break
            event.wait(timeout=2.0)
            event.clear()
            result = vibes_bridge.try_pop_result(request_id)
            if result is not None:
                break
        vibes_bridge.remove_from_queue(request_id)
        vibes_bridge.cleanup_waiter(request_id)

        if cancel_ev.is_set():
            return None
        if result is not None and result.get("status") == 200 and not result.get("error"):
            return result
        if attempt == 0:
            motivo = result.get("error") if result else "timeout"
            log(f"vibes.ai fallo ({motivo}), reintentando job completo en {int(_JOB_RETRY_DELAY_SEC)}s...")
            time.sleep(_JOB_RETRY_DELAY_SEC)
    return result


def _batch_worker_images(
    name: str,
    vid_dir: Path,
    prompt: str,
    slots: int,
    timeout_sec: int,
    cancel_ev: threading.Event,
    images_meta: list[dict],
) -> None:
    """Una imagen del proyecto por job -- la extension la adjunta como "ingredient"
    en el compositor real de vibes.ai antes de escribir el prompt y generar, igual
    que si el usuario la subiera a mano (mismo patron que Grok/Qwen). slots = videos
    por imagen."""
    batch = _get_batch(name)

    def log(msg: str) -> None:
        _append_log(batch, msg)

    total = len(images_meta)
    log(f"{total} imagen(es) - {slots} video(s) c/u - prompt: {prompt[:80]}")

    connected = _wait_for_connected_accounts(cancel_ev, log)
    if not connected:
        batch.update(finished=True, running=False)
        return
    if len(connected) > 1:
        log(f"[OK] {len(connected)} cuentas de vibes.ai conectadas: reparto round-robin entre ellas.")

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://vibes.ai/"})
    downloaded_total = 0
    dl_lock = threading.Lock()

    def process_one(i: int, img_meta: dict) -> None:
        nonlocal downloaded_total
        if cancel_ev.is_set():
            return
        img_path = Path(img_meta.get("path", ""))
        try:
            img_bytes = img_path.read_bytes()
        except Exception as exc:
            log(f"[ERROR] [{i + 1}/{total}] No se pudo leer {img_meta.get('name')}: {exc}")
            return
        mime = mimetypes.guess_type(img_path.name)[0] or "image/jpeg"
        account = connected[i % len(connected)]

        job = {
            "account": account,
            "prompt": prompt,
            "slots": slots,
            "timeoutSec": timeout_sec,
            "imageBase64": base64.b64encode(img_bytes).decode("ascii"),
            "imageMime": mime,
            "imageName": img_meta.get("name") or f"{i + 1:05d}.jpg",
        }
        log(f"[{i + 1}/{total}] Job encolado ({img_meta.get('name')}, cuenta={account})")
        result = _run_job_via_bridge(
            job, timeout_sec, cancel_ev, log=lambda m: log(f"[{i + 1}/{total}] {m}")
        )

        if not result:
            log(f"[ERROR] [{i + 1}/{total}] Sin respuesta de vibes.ai (timeout, reintento agotado).")
            return
        if result.get("status") != 200 or result.get("error"):
            log(f"[ERROR] [{i + 1}/{total}] vibes.ai: {result.get('error', 'fallo desconocido')}")
            return

        urls = result.get("videos") or []
        stem = Path(img_meta["name"]).stem
        for j, url in enumerate(urls):
            if cancel_ev.is_set():
                break
            try:
                resp = session.get(url, timeout=120)
                resp.raise_for_status()
                suffix = f"_{j + 1}" if len(urls) > 1 else ""
                out_path = vid_dir / f"{stem}{suffix}.mp4"
                out_path.write_bytes(resp.content)
                with dl_lock:
                    downloaded_total += 1
                    batch["done"] = downloaded_total
                log(f"[{i + 1}/{total}] Descargado: {out_path.name}")
            except Exception as exc:
                log(f"[ERROR] [{i + 1}/{total}] Descarga fallo para video {j + 1}: {exc}")

    concurrency = total or 1
    log(f"Enviando {total} generacion(es) (envio serializado por la extension, espera en paralelo)...")
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(process_one, i, img_meta) for i, img_meta in enumerate(images_meta)]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as exc:
                log(f"[ERROR] tarea fallo: {exc}")

    batch.update(finished=True, running=False)
    log(f"Vibes finalizado: {downloaded_total} video(s) generados.")


def _decode_ref_image(ref_image_b64: str, log) -> tuple[bytes, str, str] | None:
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
        return None
    return image_bytes, mime, f"reference.{ext}"


def _batch_worker(
    name: str,
    vid_dir: Path,
    prompt: str,
    slots: int,
    timeout_sec: int,
    cancel_ev: threading.Event,
    ref_image_b64: str | None = None,
) -> None:
    """Genera via vibes_bridge.py (cola en memoria consultada por vibes_bridge.js,
    el content script "world":"MAIN" que escribe el prompt y clickea "Generate" de
    verdad en el DOM real de vibes.ai) -- el fetch() automatizado de vibes_client.py
    (generate_video_via_bridge) siempre es rechazado por vibes.ai con "Generation
    failed to start", sesion valida o no; ver vibes_bridge.js para el detalle."""
    batch = _get_batch(name)

    def log(msg: str) -> None:
        _append_log(batch, msg)

    connected = _wait_for_connected_accounts(cancel_ev, log)
    if not connected:
        batch.update(finished=True, running=False)
        return

    account = connected[0]
    log(f"1 batch de {slots} video(s) - cuenta {account}")

    image_b64: str | None = None
    image_mime = ""
    image_name = ""
    if ref_image_b64:
        decoded = _decode_ref_image(ref_image_b64, log)
        if decoded:
            log("Imagen de referencia incluida.")
            image_bytes, image_mime, image_name = decoded
            image_b64 = base64.b64encode(image_bytes).decode("ascii")

    if cancel_ev.is_set():
        log("Detenido por el usuario.")
        batch.update(finished=True, running=False)
        return

    job = {
        "account": account,
        "prompt": prompt,
        "slots": slots,
        "timeoutSec": timeout_sec,
    }
    if image_b64:
        job["imageBase64"] = image_b64
        job["imageMime"] = image_mime
        job["imageName"] = image_name
    log("Job encolado...")
    # Id propio para nombrar los archivos descargados -- independiente del
    # requestId interno de _run_job_via_bridge, que cambia entre el intento
    # original y el reintento (mismo job, requestId nuevo cada vez).
    batch_file_id = str(uuid_lib.uuid4())[:8]
    result = _run_job_via_bridge(job, timeout_sec, cancel_ev, log=log)

    if cancel_ev.is_set():
        log("Detenido por el usuario.")
        batch.update(finished=True, running=False)
        return

    if not result:
        log("[ERROR] Sin respuesta de vibes.ai (timeout, reintento agotado).")
        batch.update(finished=True, running=False)
        return
    if result.get("status") != 200 or result.get("error"):
        log(f"[ERROR] vibes.ai: {result.get('error', 'fallo desconocido')}")
        batch.update(finished=True, running=False)
        return

    urls = result.get("videos") or []
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://vibes.ai/"})
    videos_done = 0
    for i, url in enumerate(urls):
        if cancel_ev.is_set():
            log("Detenido por el usuario.")
            break
        try:
            resp = session.get(url, timeout=120)
            resp.raise_for_status()
            out_path = vid_dir / f"vibes_{batch_file_id}_{i}.mp4"
            out_path.write_bytes(resp.content)
            videos_done += 1
            with _batches_lock:
                batch["done"] = videos_done
            log(f"[OK] video {i + 1}/{len(urls)} descargado: {out_path.name}")
        except Exception as exc:
            log(f"[ERROR] descarga video {i + 1} fallo: {exc}")

    log(f"Vibes finalizado: {videos_done}/{slots} video(s) generados.")
    batch.update(finished=True, running=False)


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
