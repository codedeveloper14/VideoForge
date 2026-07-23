import re
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

from src.domain.services.project_service import sanitize_name
from src.infrastructure.ai_providers import qwen_bridge, qwen_service
from src.infrastructure.storage import project_repository
from src.utils.logger import get_logger
from src.utils.paths import get_qwen_accounts_dir
from src.utils.platform_utils import open_folder

logger = get_logger(__name__)

_MAX_LOG_LINES = 1500

# Estado indexado por proyecto (sanitize_name) -- antes era un unico dict a
# nivel de modulo: lanzar un segundo lote (otro proyecto) no mataba el hilo
# del primero, pero SI pisaba _state["project_dir"]/["images"], y ambos
# hilos seguian escribiendo en la MISMA lista de log_lines -- logs y
# progreso de dos proyectos distintos quedaban entrelazados en lo que fuera
# que la UI estuviera pollenado. Con _batches cada proyecto tiene su propio
# log_lines/cancel_event/project_dir.
_batches: dict[str, dict] = {}
_batches_lock = threading.Lock()
_last_project: str | None = None


def _new_batch_state() -> dict:
    return {
        "running": False,
        "log_lines": [],
        "finished": False,
        "project_dir": None,
        "images": [],
        "total": 0,
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
    line = f"[QWEN] {msg}"
    with _batches_lock:
        batch["log_lines"].append(line)
        if len(batch["log_lines"]) > _MAX_LOG_LINES:
            batch["log_lines"] = batch["log_lines"][-_MAX_LOG_LINES:]


# ─────────────────────────────────────────────────────────────────
# Sesiones
# ─────────────────────────────────────────────────────────────────


def list_sessions() -> list[dict]:
    accounts_dir = get_qwen_accounts_dir()
    qwen_service.ensure_accounts(accounts_dir)
    return qwen_service.list_account_sessions(accounts_dir)


def start_account_login(account_name: str) -> None:
    accounts_dir = get_qwen_accounts_dir()
    qwen_service.ensure_accounts(accounts_dir)
    folder = qwen_service.account_dir(accounts_dir, account_name)
    folder.mkdir(parents=True, exist_ok=True)
    logger.info("[QWEN] Abriendo Chromium - inicia sesion en chat.qwen.ai.")

    def _log(msg: str) -> None:
        logger.info("[QWEN] %s", msg)

    def _run():
        saved = qwen_service.login_account_managed(folder, log_callback=_log)
        # Encadenado: login guardado -> reabrir el mismo perfil con la
        # extension cargada y dejarlo corriendo (bridge para create_chat/
        # submit_completion). Sin esto, "Login" solo dejaria el token
        # guardado pero ningun navegador conectado para el bridge.
        if saved:
            try:
                qwen_service.open_bridge_session(folder, account_name, log_callback=_log)
            except Exception as exc:
                _log(f"[ERROR] [{account_name}] No se pudo abrir el bridge: {exc}")

    threading.Thread(target=_run, daemon=True).start()


def delete_session(account_name: str) -> None:
    qwen_service.delete_account_session(get_qwen_accounts_dir(), account_name)


# Fallback automatico (ver unificacion de deteccion de sesion, tomando a Flow de
# referencia): si al arrancar un lote no hay NINGUNA cuenta con sesion utilizable,
# abrimos Chromium aislado para la primera cuenta en vez de exigir que el usuario
# vaya a la pestana Cuentas y apriete "Login" a mano. Cooldown por cuenta para no
# reabrir una ventana en cada intento fallido consecutivo.
_auto_login_last_attempt: dict[str, float] = {}
_AUTO_LOGIN_COOLDOWN = 60.0


def _trigger_auto_login_if_needed(accounts_dir: Path, log) -> None:
    folders = [f for f in sorted(accounts_dir.iterdir()) if f.is_dir()] if accounts_dir.exists() else []
    target = folders[0].name if folders else "account_1"
    now = time.time()
    if now - _auto_login_last_attempt.get(target, 0) < _AUTO_LOGIN_COOLDOWN:
        return
    _auto_login_last_attempt[target] = now
    log(f"[{target}] Sin sesion disponible - abriendo Chromium automaticamente para iniciar sesion.")
    start_account_login(target)


# ─────────────────────────────────────────────────────────────────
# Animacion por lote (in-process, ThreadPoolExecutor)
# ─────────────────────────────────────────────────────────────────


def _is_retryable_error(msg: str) -> bool:
    m = (msg or "").lower()
    if any(
        s in m
        for s in (
            "ratelimited",
            "too many requests",
            "queue limit exceeded",
            "task queue limit exceeded",
            "internal_error",
            "429",
            "timed out",
            "timeout",
            "connection aborted",
            "connection reset",
            "max retries exceeded",
            "remote end closed connection",
        )
    ):
        return True
    return bool(re.search(r"\bhttp 5\d\d\b", m))


_BRIDGE_JOB_RETRY_DELAY_SEC = 15.0


def _run_job_via_bridge(job: dict, timeout_sec: float, cancel_ev: threading.Event | None, log) -> dict | None:
    """Genera el video entero via DOM real en el navegador conectado para esta
    cuenta (qwen_bridge.js: click en '+', 'Crear Video', adjuntar imagen,
    escribir prompt, click Enviar, esperar el <video> real) -- un fetch()
    directo a create_chat/submit_completion, aunque salga de esa misma
    pestaña autenticada, choca con el mismo challenge del WAF de Alibaba que
    curl_cffi (confirmado en vivo: fetch() nunca ejecuta el JS del challenge).
    Mismo patron que _run_job_via_bridge en vibes_animation_service.py: 2
    intentos, requestId nuevo por intento, espera con Event (timeout_sec+30s
    de margen -- acá timeout_sec es el tiempo real de generacion, no solo el
    round-trip de crear el chat), cleanup siempre al final."""
    result = None
    for attempt in range(2):
        request_id = str(uuid.uuid4())
        job_with_id = dict(job, requestId=request_id)
        event = qwen_bridge.register_result_waiter(request_id)
        qwen_bridge.enqueue_request(job_with_id)

        deadline = time.time() + timeout_sec + 30
        result = None
        while time.time() < deadline:
            if cancel_ev and cancel_ev.is_set():
                break
            event.wait(timeout=2.0)
            event.clear()
            result = qwen_bridge.try_pop_result(request_id)
            if result is not None:
                break
        qwen_bridge.remove_from_queue(request_id)
        qwen_bridge.cleanup_waiter(request_id)

        if cancel_ev and cancel_ev.is_set():
            return None
        if result is not None and result.get("status") == 200 and result.get("videoUrl") and not result.get("error"):
            return result
        if attempt == 0:
            motivo = result.get("error") if result else "timeout"
            log(
                f"[bridge] la generacion en el navegador tardo mas de lo esperado ({motivo}), "
                f"reintentando en {int(_BRIDGE_JOB_RETRY_DELAY_SEC)}s..."
            )
            time.sleep(_BRIDGE_JOB_RETRY_DELAY_SEC)
    return result


def _build_generate_call(
    account_name: str,
    token: str,
    img_path: Path,
    prompt: str,
    size: str,
    out_path: str,
    timeout_sec: int,
    cookie_header: str,
    session_meta: dict,
    cancel_ev: threading.Event | None,
    log,
):
    """Hibrido aprobado: si esta cuenta tiene su Chromium (con la extension)
    conectado ahora mismo, la generacion entera corre ahi via DOM real
    (qwen_bridge.js simula el click de verdad -- confirmado en vivo que
    esquiva el WAF de Alibaba, a diferencia de un fetch() directo a
    create_chat/submit_completion); si no, cae al path de Python de siempre
    (curl_cffi) -- mejor esfuerzo en vez de dejar la cuenta inutil por no
    tener el navegador abierto. Qwen exige imagen de referencia siempre -- no
    hay modo texto-puro (ver comentario en start_batch)."""

    def call():
        if account_name in qwen_bridge.connected_accounts():
            aspect = qwen_service.QWEN_SIZE_MAP.get(size, "16:9")
            job = {
                "account": account_name,
                "imagePath": str(img_path.resolve()),
                "prompt": prompt,
                "size": aspect,
                "timeoutSec": timeout_sec,
            }
            bridge_result = _run_job_via_bridge(job, timeout_sec, cancel_ev, log)
            if not bridge_result or bridge_result.get("error") or not bridge_result.get("videoUrl"):
                raise RuntimeError(
                    (bridge_result or {}).get("error") or "Sin respuesta del navegador conectado (timeout)"
                )
            qwen_service.download_video(bridge_result["videoUrl"], out_path)
        else:
            qwen_service.generate_one(
                token,
                str(img_path),
                prompt,
                size,
                out_path,
                timeout_sec=timeout_sec,
                cookie_header=cookie_header,
                session_meta=session_meta,
            )

    return call


def _generate_with_retries(
    account_name: str,
    out_name: str,
    total: int,
    cancel_ev: threading.Event | None,
    log,
    done: dict,
    done_lock: threading.Lock,
    call,
) -> None:
    """Reintentos + manejo de WAF para el batch por imagenes (i2v) -- `call` es
    la llamada real (bridge o qwen_service.generate_one segun corresponda)."""
    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        if cancel_ev and cancel_ev.is_set():
            return
        try:
            call()
            with done_lock:
                done["n"] += 1
            log(f"[{account_name}] [OK] {out_name} ({done['n']}/{total})")
            return
        except qwen_service.QwenWafBlockedError:
            # Bloqueo del WAF de Alibaba -- no un error puntual de esta
            # imagen/video. Reintentar contra el mismo muro no sirve de nada
            # y solo satura los logs; se corta el loop de una vez.
            with done_lock:
                done["n"] += 1
            log(
                f"[{account_name}] [ERROR] La sesion de Qwen fue rechazada o bloqueada "
                f"por Alibaba. Revisa tu cuenta o vuelve a iniciar sesion en la app."
            )
            return
        except Exception as exc:
            err = str(exc)
            if attempt < max_attempts and _is_retryable_error(err):
                wait_s = min(90, 12 * attempt)
                log(f"[{account_name}] {out_name} retry {attempt}/{max_attempts - 1} en {wait_s}s ({err[:90]})")
                time.sleep(wait_s)
                continue
            with done_lock:
                done["n"] += 1
            log(f"[{account_name}] [ERROR] {out_name}: {err}")
            return


def _batch_worker(
    name: str, proj_dir: Path, prompt: str, size: str, slots: int, timeout_sec: int, image_names: list[str]
) -> None:
    batch = _get_batch(name)

    def log(msg: str) -> None:
        _append_log(batch, msg)

    try:
        img_dir = proj_dir / "imagen"
        vid_dir = proj_dir / "video"
        vid_dir.mkdir(parents=True, exist_ok=True)
        # Solo las imagenes subidas/seleccionadas en ESTA corrida -- no todo lo
        # que haya en imagen/ (puede tener sobrantes de un paso anterior del
        # pipeline, p. ej. Flow/GenTube). Mismo criterio que el filter-file de
        # Grok (grok_animation_service.py), adaptado a que Qwen corre in-process
        # (ThreadPoolExecutor) en vez de un worker por subprocess.
        imgs = [
            img_dir / n
            for n in image_names
            if (img_dir / n).is_file() and (img_dir / n).suffix.lower().lstrip(".") in project_repository.IMAGE_EXTS
        ]
        if not imgs:
            log("[ERROR] No hay imagenes para animar.")
            batch.update(finished=True, running=False)
            return

        accounts_dir = get_qwen_accounts_dir()
        tokens = qwen_service.tokens_for_run(accounts_dir)
        if not tokens:
            log("[ERROR] No hay cuentas Qwen activas. Inicia sesion primero en Cuentas.")
            try:
                _trigger_auto_login_if_needed(accounts_dir, log)
            except Exception as exc:
                log(f"[ERROR] No se pudo abrir Chromium automaticamente: {exc}")
            batch.update(finished=True, running=False)
            return

        n_accounts = max(1, len(tokens))
        maxw = max(1, min(max(1, int(slots or 1)), 8))
        submit_delay = 0.35 if maxw > 1 else 0.0
        log(
            f"Iniciando lote Qwen: {len(imgs)} imagen(es), {n_accounts} cuenta(s), "
            f"slots={slots} --> efectivos={maxw}, delay={submit_delay:.1f}s"
        )
        log(
            f"Transporte HTTP: {'curl_cffi(chromium impersonation)' if qwen_service.HAS_CURL_CFFI else 'requests estandar'}"
        )

        cancel_ev = batch["cancel_event"]
        done = {"n": 0}
        done_lock = threading.Lock()

        def run_one(i, img_path):
            if cancel_ev and cancel_ev.is_set():
                return
            account_name, token, cookie_header, session_meta = tokens[i % n_accounts]
            out_name = f"{img_path.stem}.mp4"
            out_path = str(vid_dir / out_name)
            if Path(out_path).is_file():
                with done_lock:
                    done["n"] += 1
                log(f"[{out_name}] ya existe ({done['n']}/{len(imgs)})")
                return
            log(f"[{account_name}] Generando {out_name} ({i + 1}/{len(imgs)})")
            _generate_with_retries(
                account_name,
                out_name,
                len(imgs),
                cancel_ev,
                log,
                done,
                done_lock,
                _build_generate_call(
                    account_name, token, img_path, prompt, size, out_path, timeout_sec,
                    cookie_header, session_meta, cancel_ev, log,
                ),
            )

        with ThreadPoolExecutor(max_workers=maxw) as ex:
            futures = []
            for i, img_path in enumerate(imgs):
                futures.append(ex.submit(run_one, i, img_path))
                if submit_delay > 0:
                    time.sleep(submit_delay)
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as exc:
                    log(f"[WARNING] Worker error: {exc}")

        batch.update(finished=True, running=False)
        log("Lote Qwen finalizado.")
    except Exception as exc:
        batch.update(finished=True, running=False)
        log(f"[ERROR] Error batch Qwen: {exc}")


def start_batch(
    project_name: str,
    images: list[tuple[str, object]],
    prompt: str,
    slots: int,
    size: str,
    timeout_sec: int,
    aspect_ratio: str,
) -> dict:
    global _last_project

    name = sanitize_name(project_name)
    if not name:
        raise ValueError("Selecciona un proyecto en la barra superior antes de animar.")
    # Qwen exige imagen de referencia -- a diferencia de Vibes, la interfaz
    # oficial de Qwen no tiene un modo "Create Video" desde texto puro (solo
    # anima una imagen adjunta); un intento anterior de T2V se revirtio.
    if not images:
        raise ValueError("No se recibieron imagenes")

    batch = _get_batch(name)
    # Si el MISMO proyecto ya tiene un lote corriendo, cancelalo antes de
    # pisar su estado -- nunca toca el cancel_event de otro proyecto.
    old_cancel = batch.get("cancel_event")
    if old_cancel and not batch.get("finished", True):
        old_cancel.set()

    proj_dir = project_repository.create_project(name)

    if size not in qwen_service.QWEN_SIZE_MAP:
        inverse = {v: k for k, v in qwen_service.QWEN_SIZE_MAP.items()}
        size = inverse.get(aspect_ratio, "1280x720")

    (proj_dir / "guion").mkdir(parents=True, exist_ok=True)
    (proj_dir / "guion" / "config_qwen.txt").write_text(
        f"prompt: {prompt}\nslots: {slots}\nsize: {size}\naspect_ratio: {aspect_ratio}\n",
        encoding="utf-8",
    )

    cancel_ev = threading.Event()
    _last_project = name

    img_dir = proj_dir / "imagen"
    images_meta = []
    for i, (filename, file_storage) in enumerate(images):
        dest = img_dir / filename
        if not dest.exists():
            file_storage.save(str(dest))
        images_meta.append({"index": i + 1, "name": filename, "path": str(dest)})

    batch.update(
        {
            "running": True,
            "log_lines": [],
            "finished": False,
            "project_dir": str(proj_dir),
            "images": images_meta,
            "total": len(images_meta),
            "cancel_event": cancel_ev,
        }
    )
    image_names = [m["name"] for m in images_meta]
    threading.Thread(
        target=_batch_worker, args=(name, proj_dir, prompt, size, slots, timeout_sec, image_names), daemon=True
    ).start()

    return {"ok": True, "pid": f"qwen-{int(time.time())}", "project_dir": str(proj_dir), "project_name": name}


def start_regen(project_name: str, video_name: str, prompt: str, size: str) -> dict:
    global _last_project

    name = _resolve_name(project_name)
    if not name:
        raise ValueError("Sin proyecto activo")
    proj_dir = project_repository.project_dir(name)
    batch = _get_batch(name)
    batch["project_dir"] = str(proj_dir)
    _last_project = name

    img_stem = Path(video_name).stem
    img_dir = proj_dir / "imagen"
    matches = [p for p in img_dir.iterdir() if p.is_file() and p.stem == img_stem]
    if not matches:
        raise FileNotFoundError(f"No hay imagen con stem {img_stem}")

    old_vid = proj_dir / "video" / f"{img_stem}.mp4"
    if old_vid.exists():
        try:
            old_vid.unlink()
        except Exception:
            pass

    if size not in qwen_service.QWEN_SIZE_MAP:
        size = "1280x720"

    tokens = qwen_service.tokens_for_run(get_qwen_accounts_dir())
    if not tokens:
        raise ValueError("No hay cuentas Qwen activas")
    account_name, token, cookie_header, session_meta = tokens[0]

    batch.update(finished=False, running=True)

    def _run():
        try:
            _append_log(batch, f"[{account_name}] Regen {img_stem}.mp4")
            qwen_service.generate_one(
                token,
                str(matches[0]),
                prompt,
                size,
                str(proj_dir / "video" / f"{img_stem}.mp4"),
                timeout_sec=900,
                cookie_header=cookie_header,
                session_meta=session_meta,
            )
            _append_log(batch, f"[{account_name}] [OK] Regen completado: {img_stem}.mp4")
        except qwen_service.QwenWafBlockedError:
            _append_log(
                batch,
                f"[{account_name}] [ERROR] La sesion de Qwen fue rechazada o bloqueada "
                f"por Alibaba. Revisa tu cuenta o vuelve a iniciar sesion en la app.",
            )
        except Exception as exc:
            _append_log(batch, f"[{account_name}] [ERROR] Regen error: {exc}")
        batch.update(running=False, finished=True)

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True}


def stop(project_name: str = "") -> None:
    name = _resolve_name(project_name)
    if not name:
        return
    batch = _get_batch(name)
    ev = batch.get("cancel_event")
    if ev:
        ev.set()
    batch.update(running=False, finished=True)
    _append_log(batch, "Lote marcado para detener.")


def get_log_state(offset: int, project_name: str = "") -> dict:
    name = _resolve_name(project_name)
    if not name:
        return {"lines": [], "next_offset": offset, "finished": True, "videos_done": 0, "videos_total": 0}
    batch = _get_batch(name)
    lines = batch["log_lines"][offset:]
    video_dir = Path(batch["project_dir"]) / "video" if batch["project_dir"] else None
    try:
        videos_done = len(list(video_dir.glob("*.mp4"))) if video_dir and video_dir.is_dir() else 0
    except Exception:
        videos_done = 0
    return {
        "lines": lines,
        "next_offset": offset + len(lines),
        "finished": bool(batch["finished"]),
        "videos_done": videos_done,
        "videos_total": int(batch.get("total") or 0),
    }


# ─────────────────────────────────────────────────────────────────
# Videos generados
# ─────────────────────────────────────────────────────────────────


def list_videos(project_name: str) -> dict:
    if not project_name:
        return {"videos": [], "total": 0, "done": 0, "project_dir": "", "project_name": ""}
    name = sanitize_name(project_name)
    videos = sorted(f.name for f in project_repository.list_videos(name))
    return {
        "videos": videos,
        "total": len(videos),
        "done": len(videos),
        "project_dir": str(project_repository.project_dir(name)),
        "project_name": name,
    }


def get_video_path(project_name: str, filename: str) -> Path | None:
    if project_name:
        return project_repository.resolve_safe_file(project_name, "video", filename)
    name = _last_project
    proj_dir = _batches.get(name, {}).get("project_dir") if name else None
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
    name = _last_project
    proj_dir = _batches.get(name, {}).get("project_dir") if name else None
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
    proj_label = (
        sanitize_name(project_name)
        if project_name
        else Path(_batches.get(_last_project, {}).get("project_dir", "")).name
    )
    return buf, f"{proj_label}_videos_qwen.zip"


def open_videos_folder(project_name: str) -> Path:
    video_dir = _active_video_dir(project_name)
    if not video_dir:
        raise ValueError("Sin proyecto activo")
    video_dir.mkdir(parents=True, exist_ok=True)
    open_folder(str(video_dir))
    return video_dir
