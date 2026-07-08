import shutil
from pathlib import Path

from src.utils.paths import get_jobs_dir

PROJECT_SUBDIRS = ("imagen", "audio", "guion", "video", "video_final")
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "bmp"}


def creation_time(path: Path) -> float:
    st = path.stat()
    return getattr(st, "st_birthtime", None) or st.st_mtime


def project_dir(name: str) -> Path:
    return get_jobs_dir() / name


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
