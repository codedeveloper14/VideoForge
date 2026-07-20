import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

from src.domain.services.project_service import sanitize_name
from src.infrastructure.ai_providers import qwen_service
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
    logger.info("[QWEN] Abriendo Chromium - inicia sesion en chat.qwen.ai y cierra.")

    def _run():
        qwen_service.login_account_managed(folder, log_callback=lambda msg: logger.info("[QWEN] %s", msg))

    threading.Thread(target=_run, daemon=True).start()


def delete_session(account_name: str) -> None:
    qwen_service.delete_account_session(get_qwen_accounts_dir(), account_name)


# ─────────────────────────────────────────────────────────────────
# Animacion por lote (in-process, ThreadPoolExecutor)
# ─────────────────────────────────────────────────────────────────


def _is_retryable_error(msg: str) -> bool:
    m = (msg or "").lower()
    return any(
        s in m
        for s in (
            "ratelimited",
            "too many requests",
            "queue limit exceeded",
            "task queue limit exceeded",
            "internal_error",
            "429",
        )
    )


def _batch_worker(name: str, proj_dir: Path, prompt: str, size: str, slots: int, timeout_sec: int) -> None:
    batch = _get_batch(name)

    def log(msg: str) -> None:
        _append_log(batch, msg)

    try:
        img_dir = proj_dir / "imagen"
        vid_dir = proj_dir / "video"
        vid_dir.mkdir(parents=True, exist_ok=True)
        imgs = [
            p
            for p in sorted(img_dir.iterdir())
            if p.is_file() and p.suffix.lower().lstrip(".") in project_repository.IMAGE_EXTS
        ]
        if not imgs:
            log("[ERROR] No hay imagenes para animar.")
            batch.update(finished=True, running=False)
            return

        accounts_dir = get_qwen_accounts_dir()
        tokens = qwen_service.tokens_for_run(accounts_dir)
        if not tokens:
            log("[ERROR] No hay cuentas Qwen activas. Inicia sesion primero en Cuentas.")
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
            max_attempts = 4
            for attempt in range(1, max_attempts + 1):
                if cancel_ev and cancel_ev.is_set():
                    return
                try:
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
                    with done_lock:
                        done["n"] += 1
                    log(f"[{account_name}] [OK] {out_name} ({done['n']}/{len(imgs)})")
                    return
                except qwen_service.QwenWafBlockedError:
                    # Bloqueo del WAF de Alibaba -- no un error puntual de esta
                    # imagen. Reintentar contra el mismo muro no sirve de nada
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
                        log(
                            f"[{account_name}] {out_name} retry {attempt}/{max_attempts - 1} en {wait_s}s ({err[:90]})"
                        )
                        time.sleep(wait_s)
                        continue
                    with done_lock:
                        done["n"] += 1
                    log(f"[{account_name}] [ERROR] {out_name}: {err}")
                    return

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
    if not images:
        raise ValueError("No se recibieron imagenes")

    batch = _get_batch(name)
    # Si el MISMO proyecto ya tiene un lote corriendo, cancelalo antes de
    # pisar su estado -- nunca toca el cancel_event de otro proyecto.
    old_cancel = batch.get("cancel_event")
    if old_cancel and not batch.get("finished", True):
        old_cancel.set()

    proj_dir = project_repository.create_project(name)
    img_dir = proj_dir / "imagen"
    images_meta = []
    for i, (filename, file_storage) in enumerate(images):
        dest = img_dir / filename
        if not dest.exists():
            file_storage.save(str(dest))
        images_meta.append({"index": i + 1, "name": filename, "path": str(dest)})

    if size not in qwen_service.QWEN_SIZE_MAP:
        inverse = {v: k for k, v in qwen_service.QWEN_SIZE_MAP.items()}
        size = inverse.get(aspect_ratio, "1280x720")

    (proj_dir / "guion").mkdir(parents=True, exist_ok=True)
    (proj_dir / "guion" / "config_qwen.txt").write_text(
        f"prompt: {prompt}\nslots: {slots}\nsize: {size}\naspect_ratio: {aspect_ratio}\n",
        encoding="utf-8",
    )

    cancel_ev = threading.Event()
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
    _last_project = name
    threading.Thread(
        target=_batch_worker, args=(name, proj_dir, prompt, size, slots, timeout_sec), daemon=True
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
    proj_label = sanitize_name(project_name) if project_name else Path(_state["project_dir"]).name
    return buf, f"{proj_label}_videos_qwen.zip"


def open_videos_folder(project_name: str) -> Path:
    video_dir = _active_video_dir(project_name)
    if not video_dir:
        raise ValueError("Sin proyecto activo")
    video_dir.mkdir(parents=True, exist_ok=True)
    open_folder(str(video_dir))
    return video_dir
