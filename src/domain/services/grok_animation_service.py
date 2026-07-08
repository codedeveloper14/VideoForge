import json
import tempfile
import threading
import time
import zipfile
from io import BytesIO
from pathlib import Path

from src.domain.services.project_service import sanitize_name
from src.infrastructure.ai_providers import grok_process, grok_service
from src.infrastructure.storage import project_repository
from src.utils.logger import get_logger
from src.utils.paths import get_grok_accounts_dir, get_grok_downloads_dir
from src.utils.platform_utils import open_folder

logger = get_logger(__name__)

_state = {
    "proc": None,
    "log_lines": [],
    "finished": False,
    "project_dir": None,
    "images": [],
    "total": 0,
    "regen_count": 0,
}


def _tail_process(proc):
    try:
        for line in iter(proc.stdout.readline, b""):
            _state["log_lines"].append(line.decode("utf-8", errors="replace").rstrip())
    except Exception:
        pass
    _state["finished"] = True


# ─────────────────────────────────────────────────────────────────
# Sesiones de cuenta
# ─────────────────────────────────────────────────────────────────

def list_sessions() -> list[dict]:
    accounts_dir = get_grok_accounts_dir()
    grok_service.ensure_accounts_setup(accounts_dir)
    return grok_service.list_account_sessions(accounts_dir)


def start_account_login(account_name: str) -> None:
    """Lanza el login (Playwright, ventana visible) en un hilo de fondo."""
    accounts_dir = get_grok_accounts_dir()
    grok_service.ensure_accounts_setup(accounts_dir)
    folder = grok_service.account_dir(accounts_dir, account_name)
    folder.mkdir(parents=True, exist_ok=True)
    _state["log_lines"].append(f"Abriendo Chrome — inicia sesion en grok.com y cierra la ventana.")

    def _run():
        ok, message = grok_service.login_account_managed(folder, folder.name)
        _state["log_lines"].append(message)

    threading.Thread(target=_run, daemon=True).start()


def delete_session(account_name: str) -> None:
    accounts_dir = get_grok_accounts_dir()
    grok_service.delete_account_session(accounts_dir, account_name)


# ─────────────────────────────────────────────────────────────────
# Animacion por lote
# ─────────────────────────────────────────────────────────────────

def start_batch(project_name: str, images: list[tuple[str, object]],
                 prompt: str, slots: int, aspect_ratio: str, video_length: int,
                 resolution: str) -> dict:
    """`images` es una lista de (filename, file_storage) donde file_storage tiene .save(path)."""
    if _state["proc"] and _state["proc"].poll() is None:
        _state["proc"].terminate()

    name = sanitize_name(project_name)
    if not name:
        raise ValueError("Selecciona un proyecto en la barra superior antes de animar.")

    proj_dir = project_repository.create_project(name)
    accounts_dir = get_grok_accounts_dir()
    grok_service.ensure_accounts_setup(accounts_dir)

    if not images:
        raise ValueError("No se recibieron imagenes")

    img_dir = proj_dir / "imagen"
    img_dir.mkdir(parents=True, exist_ok=True)
    images_meta = []
    for i, (filename, file_storage) in enumerate(images):
        dest = img_dir / filename
        if not dest.exists():
            file_storage.save(str(dest))
        images_meta.append({"index": i + 1, "name": filename, "path": str(dest)})

    stage_names = [m["name"] for m in images_meta]

    (proj_dir / "guion").mkdir(parents=True, exist_ok=True)
    (proj_dir / "guion" / "config.txt").write_text(
        f"prompt: {prompt}\nslots: {slots}\naspect_ratio: {aspect_ratio}\n"
        f"video_length: {video_length}\nresolution: {resolution}\n"
    )

    _state.update({
        "log_lines": [], "finished": False, "project_dir": str(proj_dir),
        "images": images_meta, "total": len(images_meta),
    })

    stage_list_path = proj_dir / "guion" / "animate_this_run.json"
    stage_list_path.write_text(json.dumps(stage_names))

    proc = grok_process.spawn_worker([
        str(img_dir),
        "--output-dir", str(proj_dir / "video"),
        "--filter-file", str(stage_list_path),
        "--slots", str(slots),
        "--prompt", prompt,
        "--aspect-ratio", aspect_ratio,
        "--video-length", str(video_length),
        "--resolution", resolution,
    ], cwd=accounts_dir.parent)
    _state["proc"] = proc

    threading.Thread(target=_tail_process, args=(proc,), daemon=True).start()

    return {"ok": True, "pid": proc.pid, "project_dir": str(proj_dir), "project_name": name}


def start_regen(project_name: str, video_name: str, prompt: str, aspect_ratio: str,
                 video_length: int, resolution: str) -> dict:
    name = sanitize_name(project_name)
    if _state["project_dir"]:
        proj_dir = Path(_state["project_dir"])
    elif name:
        proj_dir = project_repository.project_dir(name)
        _state["project_dir"] = str(proj_dir)
    else:
        raise ValueError("Sin proyecto activo")

    _state["regen_count"] = _state.get("regen_count", 0) + 1
    _state["finished"] = False

    vid_stem = Path(video_name).stem
    img_dir = proj_dir / "imagen"
    matches = [
        p for p in img_dir.iterdir()
        if p.is_file() and p.stem == vid_stem
        and p.suffix.lower().lstrip(".") in project_repository.IMAGE_EXTS
    ]
    if not matches:
        raise FileNotFoundError(f"No hay imagen con stem {vid_stem}")
    img_path = matches[0]

    old_vid = proj_dir / "video" / video_name
    if old_vid.exists():
        old_vid.unlink()

    tmp_dir = Path(tempfile.mkdtemp())
    import shutil
    shutil.copy2(str(img_path), str(tmp_dir / img_path.name))

    accounts_dir = get_grok_accounts_dir()
    target_name = f"{img_path.stem}.mp4"

    def _run():
        video_dir = proj_dir / "video"
        snap_before = {f.name for f in video_dir.glob("*.mp4")}
        proc = grok_process.spawn_worker([
            str(tmp_dir),
            "--output-dir", str(video_dir),
            "--slots", "1",
            "--prompt", prompt,
            "--aspect-ratio", aspect_ratio,
            "--video-length", str(video_length),
            "--resolution", resolution,
        ], cwd=accounts_dir.parent)
        for line in iter(proc.stdout.readline, b""):
            _state["log_lines"].append(line.decode("utf-8", errors="replace").rstrip())
        proc.wait()

        snap_after = {f.name for f in video_dir.glob("*.mp4")}
        new_files = snap_after - snap_before
        if new_files:
            if target_name not in new_files:
                src = video_dir / sorted(new_files)[0]
                try:
                    src.rename(video_dir / target_name)
                except Exception as exc:
                    _state["log_lines"].append(f"[regen] rename error: {exc}")
            _state["log_lines"].append(f"Regen completado: {target_name}")
        else:
            dl_dir = get_grok_downloads_dir()
            dl_videos = sorted(dl_dir.glob("*.mp4"), key=lambda f: f.stat().st_mtime)
            if dl_videos:
                shutil.copy2(str(dl_videos[-1]), str(video_dir / target_name))
                _state["log_lines"].append(f"Regen completado (desde downloads): {target_name}")
            else:
                _state["log_lines"].append(f"Regen termino pero no se encontro el video: {target_name}")

        _state["regen_count"] = max(0, _state.get("regen_count", 1) - 1)
        if _state["regen_count"] == 0:
            _state["finished"] = True
        shutil.rmtree(str(tmp_dir), ignore_errors=True)

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True}


def stop() -> None:
    if _state["proc"] and _state["proc"].poll() is None:
        _state["proc"].terminate()
    _state["finished"] = True


def get_log_state(offset: int) -> dict:
    finished = _state["finished"] or (_state["proc"] is not None and _state["proc"].poll() is not None)
    lines = _state["log_lines"][offset:]
    video_dir = Path(_state["project_dir"]) / "video" if _state["project_dir"] else None
    try:
        videos_done = len(list(video_dir.glob("*.mp4"))) if video_dir and video_dir.is_dir() else 0
    except Exception:
        videos_done = 0
    return {
        "lines": lines,
        "next_offset": offset + len(lines),
        "finished": finished,
        "videos_done": videos_done,
        "videos_total": int(_state.get("total") or 0),
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
    fallback_dir = get_grok_downloads_dir()
    candidate = (fallback_dir / filename).resolve()
    try:
        candidate.relative_to(fallback_dir.resolve())
    except ValueError:
        return None
    return candidate


def _active_video_dir(project_name: str) -> Path:
    if project_name:
        return project_repository.project_dir(project_name) / "video"
    if _state["project_dir"]:
        return Path(_state["project_dir"]) / "video"
    return get_grok_downloads_dir()


def build_videos_zip(project_name: str) -> tuple[BytesIO, str] | None:
    video_dir = _active_video_dir(project_name)
    videos = sorted(video_dir.glob("*.mp4")) if video_dir.exists() else []
    if not videos:
        return None
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for v in videos:
            zf.write(str(v), v.name)
    buf.seek(0)
    zip_name = f"{sanitize_name(project_name) or 'grok_videos'}_videos.zip"
    return buf, zip_name


def open_videos_folder(project_name: str) -> None:
    video_dir = _active_video_dir(project_name)
    video_dir.mkdir(parents=True, exist_ok=True)
    open_folder(str(video_dir))
