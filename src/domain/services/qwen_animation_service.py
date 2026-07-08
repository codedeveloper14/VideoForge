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

_state = {
    "running": False,
    "log_lines": [],
    "finished": False,
    "project_dir": None,
    "images": [],
    "total": 0,
    "cancel_event": None,
}
_lock = threading.Lock()


def _log(msg: str) -> None:
    line = f"[QWEN] {msg}"
    with _lock:
        _state["log_lines"].append(line)
        if len(_state["log_lines"]) > _MAX_LOG_LINES:
            _state["log_lines"] = _state["log_lines"][-_MAX_LOG_LINES:]


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
    _log(f"Abriendo Chromium - inicia sesion en chat.qwen.ai y cierra.")

    def _run():
        qwen_service.login_account_managed(folder, log_callback=_log)

    threading.Thread(target=_run, daemon=True).start()


def delete_session(account_name: str) -> None:
    qwen_service.delete_account_session(get_qwen_accounts_dir(), account_name)


# ─────────────────────────────────────────────────────────────────
# Animacion por lote (in-process, ThreadPoolExecutor)
# ─────────────────────────────────────────────────────────────────

def _is_retryable_error(msg: str) -> bool:
    m = (msg or "").lower()
    return any(s in m for s in (
        "ratelimited", "too many requests", "queue limit exceeded",
        "task queue limit exceeded", "internal_error", "429",
    ))


def _batch_worker(proj_dir: Path, prompt: str, size: str, slots: int, timeout_sec: int) -> None:
    try:
        img_dir = proj_dir / "imagen"
        vid_dir = proj_dir / "video"
        vid_dir.mkdir(parents=True, exist_ok=True)
        imgs = [
            p for p in sorted(img_dir.iterdir())
            if p.is_file() and p.suffix.lower().lstrip(".") in project_repository.IMAGE_EXTS
        ]
        if not imgs:
            _log("[ERROR] No hay imagenes para animar.")
            _state.update(finished=True, running=False)
            return

        accounts_dir = get_qwen_accounts_dir()
        tokens = qwen_service.tokens_for_run(accounts_dir)
        if not tokens:
            _log("[ERROR] No hay cuentas Qwen activas. Inicia sesion primero en Cuentas.")
            _state.update(finished=True, running=False)
            return

        n_accounts = max(1, len(tokens))
        maxw = max(1, min(max(1, int(slots or 1)), 8))
        submit_delay = 0.35 if maxw > 1 else 0.0
        _log(f"Iniciando lote Qwen: {len(imgs)} imagen(es), {n_accounts} cuenta(s), "
             f"slots={slots} --> efectivos={maxw}, delay={submit_delay:.1f}s")
        _log(f"Transporte HTTP: {'curl_cffi(chromium impersonation)' if qwen_service.HAS_CURL_CFFI else 'requests estandar'}")

        cancel_ev = _state["cancel_event"]
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
                _log(f"[{out_name}] ya existe ({done['n']}/{len(imgs)})")
                return
            _log(f"[{account_name}] Generando {out_name} ({i + 1}/{len(imgs)})")
            max_attempts = 4
            for attempt in range(1, max_attempts + 1):
                if cancel_ev and cancel_ev.is_set():
                    return
                try:
                    qwen_service.generate_one(
                        token, str(img_path), prompt, size, out_path,
                        timeout_sec=timeout_sec, cookie_header=cookie_header, session_meta=session_meta,
                    )
                    with done_lock:
                        done["n"] += 1
                    _log(f"[{account_name}] [OK] {out_name} ({done['n']}/{len(imgs)})")
                    return
                except Exception as exc:
                    err = str(exc)
                    if attempt < max_attempts and _is_retryable_error(err):
                        wait_s = min(90, 12 * attempt)
                        _log(f"[{account_name}] {out_name} retry {attempt}/{max_attempts - 1} en {wait_s}s ({err[:90]})")
                        time.sleep(wait_s)
                        continue
                    with done_lock:
                        done["n"] += 1
                    _log(f"[{account_name}] [ERROR] {out_name}: {err}")
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
                    _log(f"[WARNING] Worker error: {exc}")

        _state.update(finished=True, running=False)
        _log("Lote Qwen finalizado.")
    except Exception as exc:
        _state.update(finished=True, running=False)
        _log(f"[ERROR] Error batch Qwen: {exc}")


def start_batch(project_name: str, images: list[tuple[str, object]], prompt: str, slots: int,
                 size: str, timeout_sec: int, aspect_ratio: str) -> dict:
    name = sanitize_name(project_name)
    if not name:
        raise ValueError("Selecciona un proyecto en la barra superior antes de animar.")
    if not images:
        raise ValueError("No se recibieron imagenes")

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
        f"prompt: {prompt}\nslots: {slots}\nsize: {size}\naspect_ratio: {aspect_ratio}\n", encoding="utf-8",
    )

    cancel_ev = threading.Event()
    _state.update({
        "running": True, "log_lines": [], "finished": False, "project_dir": str(proj_dir),
        "images": images_meta, "total": len(images_meta), "cancel_event": cancel_ev,
    })
    threading.Thread(target=_batch_worker, args=(proj_dir, prompt, size, slots, timeout_sec), daemon=True).start()

    return {"ok": True, "pid": f"qwen-{int(time.time())}", "project_dir": str(proj_dir), "project_name": name}


def start_regen(project_name: str, video_name: str, prompt: str, size: str) -> dict:
    name = sanitize_name(project_name)
    if _state["project_dir"]:
        proj_dir = Path(_state["project_dir"])
    elif name:
        proj_dir = project_repository.project_dir(name)
    else:
        raise ValueError("Sin proyecto activo")

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

    _state.update(finished=False, running=True)

    def _run():
        try:
            _log(f"[{account_name}] Regen {img_stem}.mp4")
            qwen_service.generate_one(
                token, str(matches[0]), prompt, size, str(proj_dir / "video" / f"{img_stem}.mp4"),
                timeout_sec=900, cookie_header=cookie_header, session_meta=session_meta,
            )
            _log(f"[{account_name}] [OK] Regen completado: {img_stem}.mp4")
        except Exception as exc:
            _log(f"[{account_name}] [ERROR] Regen error: {exc}")
        _state.update(running=False, finished=True)

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True}


def stop() -> None:
    ev = _state.get("cancel_event")
    if ev:
        ev.set()
    _state.update(running=False, finished=True)
    _log("Lote marcado para detener.")


def get_log_state(offset: int) -> dict:
    lines = _state["log_lines"][offset:]
    video_dir = Path(_state["project_dir"]) / "video" if _state["project_dir"] else None
    try:
        videos_done = len(list(video_dir.glob("*.mp4"))) if video_dir and video_dir.is_dir() else 0
    except Exception:
        videos_done = 0
    return {
        "lines": lines, "next_offset": offset + len(lines), "finished": bool(_state["finished"]),
        "videos_done": videos_done, "videos_total": int(_state.get("total") or 0),
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
        "videos": videos, "total": len(videos), "done": len(videos),
        "project_dir": str(project_repository.project_dir(name)), "project_name": name,
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
    return buf, f"{proj_label}_videos_qwen.zip"


def open_videos_folder(project_name: str) -> Path:
    video_dir = _active_video_dir(project_name)
    if not video_dir:
        raise ValueError("Sin proyecto activo")
    video_dir.mkdir(parents=True, exist_ok=True)
    open_folder(str(video_dir))
    return video_dir
