import re
from pathlib import Path

from werkzeug.utils import secure_filename

from src.infrastructure.storage import project_repository
from src.infrastructure.storage.project_repository import sanitize_name
from src.utils.platform_utils import open_folder

_SCENE_NUM_RE = re.compile(r"^(?:img|flow)_(\d+)$", re.IGNORECASE)

# El render (render_service.py) solo lee "*.mp4" del directorio video/ -- aceptar
# otro formato aca dejaria el archivo subido invisible para el pipeline real.
_UPLOAD_VIDEO_EXTS = {"mp4"}


def scene_sort_key(path: Path):
    """Ordena por numero de escena (img_00001/flow_0001...); si no matchea, por fecha de creacion."""
    match = _SCENE_NUM_RE.match(path.stem)
    if match:
        return (0, int(match.group(1)), path.stem.lower())
    return (1, project_repository.creation_time(path), path.stem.lower())


def create_project(raw_name: str) -> dict:
    name = sanitize_name(raw_name)
    if not name:
        raise ValueError("Nombre invalido")
    proj = project_repository.create_project(name)
    return {"ok": True, "nombre": name, "ruta": str(proj)}


def list_projects() -> list[dict]:
    out = []
    for d in project_repository.list_project_dirs():
        out.append(
            {
                "nombre": d.name,
                "ruta": str(d),
                "videos": project_repository.count_files(d / "video", "*.mp4"),
                "audios": project_repository.count_files(d / "audio", "*"),
                "creado": d.stat().st_ctime,
            }
        )
    out.sort(key=lambda x: x["creado"], reverse=True)
    return out


def get_project_content(project_name: str) -> dict:
    img_dir = project_repository.project_dir(project_name) / "imagen"
    vid_dir = project_repository.project_dir(project_name) / "video"

    images = sorted(project_repository.list_images(project_name), key=scene_sort_key)
    videos = sorted(project_repository.list_videos(project_name), key=scene_sort_key)
    vid_by_stem = {v.stem: v.name for v in videos}

    seen_stems = set()
    scenes = []
    for img in images:
        seen_stems.add(img.stem)
        vid = vid_by_stem.get(img.stem)
        scenes.append({"index": img.stem, "image": img.name, "video": vid, "has_video": vid is not None})

    for v in videos:
        if v.stem not in seen_stems:
            seen_stems.add(v.stem)
            scenes.append({"index": v.stem, "image": None, "video": v.name, "has_video": True})

    def _content_scene_sort_key(scene: dict):
        if scene["image"] and (img_dir / scene["image"]).exists():
            return scene_sort_key(img_dir / scene["image"])
        if scene["video"] and (vid_dir / scene["video"]).exists():
            return scene_sort_key(vid_dir / scene["video"])
        return (2, 0.0, "")

    scenes.sort(key=_content_scene_sort_key)

    return {
        "scenes": scenes,
        "total": len(scenes),
        "with_video": sum(1 for s in scenes if s["has_video"]),
        "images_only": sum(1 for s in scenes if not s["has_video"]),
        "debug": {
            "img_dir": str(img_dir),
            "img_count": len(images),
            "vid_count": len(videos),
            "img_dir_exists": img_dir.exists(),
        },
    }


def _ext_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def upload_project_image(project_name: str, filename: str, data: bytes) -> str:
    """Sube manualmente una imagen especifica a jobs/<project>/imagen -- usada por
    la galeria del Paso 5 para asignar/reemplazar un asset puntual (en vez de
    depender solo de lo que ya haya en el proyecto)."""
    name = sanitize_name(project_name)
    if not name:
        raise ValueError("Proyecto invalido")
    safe = secure_filename(filename or "")
    if not safe or _ext_of(safe) not in project_repository.IMAGE_EXTS:
        raise ValueError("Formato de imagen no soportado")
    project_repository.write_image_file(name, safe, data)
    return safe


def upload_project_video(project_name: str, filename: str, data: bytes) -> str:
    """Sube manualmente un video especifico a jobs/<project>/video -- solo .mp4,
    que es lo unico que render_service.py lee del directorio."""
    name = sanitize_name(project_name)
    if not name:
        raise ValueError("Proyecto invalido")
    safe = secure_filename(filename or "")
    if not safe or _ext_of(safe) not in _UPLOAD_VIDEO_EXTS:
        raise ValueError("Formato de video no soportado (solo .mp4)")
    project_repository.write_video_file(name, safe, data)
    return safe


def delete_project(raw_name: str) -> tuple[bool, str]:
    name = sanitize_name(raw_name)
    if not name:
        return False, "Nombre invalido"
    return project_repository.delete_project(name)


def list_final_videos(project_name: str) -> list[str]:
    return project_repository.list_final_videos(project_name)


def open_final_videos_folder(raw_project_name: str) -> Path:
    name = sanitize_name(raw_project_name)
    if not name:
        raise ValueError("Falta el nombre del proyecto")
    d = project_repository.ensure_final_videos_dir(name)
    open_folder(str(d))
    return d
