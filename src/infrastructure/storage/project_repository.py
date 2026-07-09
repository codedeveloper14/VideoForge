import json
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


# El proyecto acumulo distintos nombres de archivo de guion segun que ruta lo escribio
# (edicion normal, render directo, render desde el editor). Un solo orden de busqueda
# aqui evita que cada ruta reinvente su propia lista de fallback (y las diverjan).
_GUION_FALLBACK_NAMES = (
    "guion_fragmentado.txt",
    "guion_render.txt",
    "guion_editor.txt",
    "guion.txt",
)


def find_guion_file(project: str) -> Path | None:
    guion_dir = project_dir(project) / "guion"
    for name in _GUION_FALLBACK_NAMES:
        candidate = guion_dir / name
        if candidate.exists():
            return candidate
    root_fallback = project_dir(project) / "guion.txt"
    return root_fallback if root_fallback.exists() else None


def read_guion_lines(project: str) -> list[str]:
    """Lineas no vacias del guion (una escena por linea), buscando en todos los
    nombres de archivo conocidos por orden de prioridad. Vacia si no hay guion."""
    path = find_guion_file(project)
    if not path:
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_guion_variant(project: str, filename: str, texto: str) -> Path:
    """Escribe el guion en un nombre de archivo especifico (p. ej. guion_editor.txt),
    sin tocar guion_fragmentado.txt (el archivo canonico del editor de guion normal)."""
    guion_dir = project_dir(project) / "guion"
    guion_dir.mkdir(parents=True, exist_ok=True)
    path = guion_dir / filename
    path.write_text(texto, encoding="utf-8")
    return path


def list_audio_files(project: str) -> list[Path]:
    audio_dir = project_dir(project) / "audio"
    if not audio_dir.exists():
        return []
    files = [f for f in audio_dir.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTS]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files


def write_audio_file(project: str, filename: str, data: bytes) -> Path:
    audio_dir = project_dir(project) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    path = audio_dir / filename
    path.write_bytes(data)
    return path


def write_editor_plan(project: str, escenas: list[dict]) -> Path:
    editor_dir = project_dir(project) / "editor"
    editor_dir.mkdir(parents=True, exist_ok=True)
    path = editor_dir / "plan_edicion.json"
    path.write_text(json.dumps({"escenas": escenas}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_editor_plan(project: str) -> dict | None:
    """Busca el plan de edicion guardado por write_editor_plan, con los mismos
    fallbacks de ubicacion que el editor visual (proyecto/editor, raiz, guion/)."""
    proj = project_dir(project)
    for candidate in (proj / "editor" / "plan_edicion.json",
                      proj / "plan_edicion.json",
                      proj / "guion" / "plan_edicion.json"):
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                return None
    return None


def find_timestamps_file(project: str) -> Path | None:
    proj = project_dir(project)
    for candidate in (proj / "editor" / "timestamps_escenas.json",
                      proj / "timestamps_escenas.json",
                      proj / "guion" / "timestamps_escenas.json"):
        if candidate.exists():
            return candidate
    return None


def write_scene_timestamps(project: str, records: list[dict]) -> Path:
    path = project_dir(project) / "timestamps_escenas.json"
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
