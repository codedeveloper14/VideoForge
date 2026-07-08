import re
import shutil
from pathlib import Path

from src.utils.paths import get_jobs_dir

PROJECT_SUBDIRS = ("imagen", "audio", "guion", "video", "video_final")
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "bmp"}


def creation_time(path: Path) -> float:
    st = path.stat()
    return getattr(st, "st_birthtime", None) or st.st_mtime


def sanitize_name(raw: str) -> str:
    return re.sub(r"[^\w\-]", "_", (raw or "").strip())[:60]


def project_dir(name: str) -> Path:
    """Siempre resuelve dentro de jobs/: sanitiza el nombre para que ningun
    llamador pueda escapar el directorio de jobs via el nombre de proyecto."""
    return get_jobs_dir() / sanitize_name(name)


def create_project(name: str) -> Path:
    proj = project_dir(name)
    for sub in PROJECT_SUBDIRS:
        (proj / sub).mkdir(parents=True, exist_ok=True)
    return proj


def list_project_dirs() -> list[Path]:
    jobs = get_jobs_dir()
    dirs = []
    for d in sorted(jobs.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        subs = {s.name for s in d.iterdir() if s.is_dir()}
        if not any(x in subs for x in ("imagen", "audio", "video")):
            continue
        dirs.append(d)
    return dirs


def count_files(dir_path: Path, pattern: str = "*") -> int:
    return len(list(dir_path.glob(pattern))) if dir_path.exists() else 0


def delete_project(name: str) -> tuple[bool, str]:
    jobs = get_jobs_dir()
    proj = jobs / name
    if not proj.exists():
        return True, "not_found"
    try:
        proj.resolve().relative_to(jobs.resolve())
    except ValueError:
        return False, "Ruta invalida"
    if not proj.is_dir():
        return False, "No es directorio"
    shutil.rmtree(str(proj))
    return True, ""


def resolve_safe_file(project: str, subdir: str, filename: str) -> Path | None:
    """Resuelve un archivo dentro de jobs/<project>/<subdir>/<filename>, rechazando
    cualquier intento de escapar ese directorio (path traversal) via el filename."""
    base = (project_dir(project) / subdir).resolve()
    candidate = (base / filename).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def list_images(project: str) -> list[Path]:
    img_dir = project_dir(project) / "imagen"
    if not img_dir.exists():
        return []
    return [f for f in img_dir.iterdir() if f.is_file() and f.suffix.lower().lstrip(".") in IMAGE_EXTS]


def list_videos(project: str) -> list[Path]:
    vid_dir = project_dir(project) / "video"
    return list(vid_dir.glob("*.mp4")) if vid_dir.exists() else []


def list_final_videos(project: str) -> list[str]:
    vf_dir = project_dir(project) / "video_final"
    if not vf_dir.exists():
        return []
    return sorted(f.name for f in vf_dir.glob("*.mp4"))


def ensure_final_videos_dir(project: str) -> Path:
    d = project_dir(project) / "video_final"
    d.mkdir(parents=True, exist_ok=True)
    return d


AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".aac"}


def write_guion(project: str, texto: str, prompts: str = "") -> None:
    guion_dir = project_dir(project) / "guion"
    guion_dir.mkdir(parents=True, exist_ok=True)
    (guion_dir / "guion_fragmentado.txt").write_text(texto, encoding="utf-8")
    if prompts:
        (guion_dir / "prompts_imagen.txt").write_text(prompts, encoding="utf-8")


def read_guion(project: str) -> tuple[str, str, bool]:
    guion_dir = project_dir(project) / "guion"
    path_texto = guion_dir / "guion_fragmentado.txt"
    path_prompts = guion_dir / "prompts_imagen.txt"
    if not path_texto.exists():
        return "", "", False
    prompts = path_prompts.read_text(encoding="utf-8") if path_prompts.exists() else ""
    return path_texto.read_text(encoding="utf-8"), prompts, True


def list_audio_files(project: str) -> list[Path]:
    audio_dir = project_dir(project) / "audio"
    if not audio_dir.exists():
        return []
    files = [f for f in audio_dir.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTS]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files
