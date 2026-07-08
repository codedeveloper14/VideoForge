import re
from pathlib import Path

from src.infrastructure.storage import project_repository
from src.infrastructure.storage.project_repository import sanitize_name
from src.utils.platform_utils import open_folder

_SCENE_NUM_RE = re.compile(r"^(?:img|flow)_(\d+)$", re.IGNORECASE)


def _path_sort_key(path: Path):
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
        out.append({
            "nombre": d.name,
            "ruta": str(d),
            "videos": project_repository.count_files(d / "video", "*.mp4"),
            "audios": project_repository.count_files(d / "audio", "*"),
            "creado": d.stat().st_ctime,
        })
    out.sort(key=lambda x: x["creado"], reverse=True)
    return out


def get_project_content(project_name: str) -> dict:
    img_dir = project_repository.project_dir(project_name) / "imagen"
    vid_dir = project_repository.project_dir(project_name) / "video"

    images = sorted(project_repository.list_images(project_name), key=_path_sort_key)
    videos = sorted(project_repository.list_videos(project_name), key=_path_sort_key)
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

    def _scene_sort_key(scene: dict):
        if scene["image"] and (img_dir / scene["image"]).exists():
            return _path_sort_key(img_dir / scene["image"])
        if scene["video"] and (vid_dir / scene["video"]).exists():
            return _path_sort_key(vid_dir / scene["video"])
        return (2, 0.0, "")

    scenes.sort(key=_scene_sort_key)

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
