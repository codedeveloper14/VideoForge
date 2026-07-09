import json

from src.domain.services import render_service, scene_timestamp_service
from src.domain.services.project_service import scene_sort_key
from src.infrastructure.ai_providers import whisper_client
from src.infrastructure.media import ffmpeg_utils
from src.infrastructure.storage import project_repository
from src.utils.logger import get_logger

logger = get_logger(__name__)

_EDITOR_IMG_EXTS = {"jpg", "jpeg", "png", "webp"}


def _read_valid_timestamps(project_name: str) -> list[dict]:
    """Lee timestamps_escenas.json cacheado y lo valida: bueno = contiguo (sin huecos
    > 0.4s), duracion promedio >= 2s. Si parece el mapeo 1:1 crudo de whisper (malo),
    se borra para que se regenere en la proxima transcripcion."""
    path = project_repository.find_timestamps_file(project_name)
    if not path:
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not raw:
        return []

    avg_dur = sum(t.get("duracion", 0) for t in raw) / len(raw)
    gaps = sum(1 for i in range(1, len(raw)) if raw[i].get("inicio", 0) - raw[i - 1].get("fin", 0) > 0.4)
    gap_ratio = gaps / max(1, len(raw) - 1)
    if avg_dur >= 2.0 and gap_ratio < 0.15:
        return raw

    logger.info("editor_visual: timestamps cacheados rechazados (avg=%.2fs gaps=%d/%d) - se eliminan",
                avg_dur, gaps, len(raw) - 1)
    try:
        path.unlink()
    except Exception:
        pass
    return []


def get_project_data(project_name: str) -> dict:
    """Datos del proyecto para el editor visual: imagenes, guion, audio, plan
    enriquecido (con imagen_url resuelta por escena) y timestamps cacheados."""
    proj_dir = project_repository.project_dir(project_name)
    if not proj_dir.exists():
        raise FileNotFoundError("proyecto no encontrado")

    img_dir = proj_dir / "imagen"
    image_paths = sorted(
        (f for f in img_dir.iterdir() if f.is_file() and f.suffix.lower().lstrip(".") in _EDITOR_IMG_EXTS),
        key=scene_sort_key,
    ) if img_dir.exists() else []
    images = [f"/api/editor/imagen/{project_name}/{p.name}" for p in image_paths]

    guion_path = project_repository.find_guion_file(project_name)
    guion = ""
    if guion_path:
        try:
            guion = guion_path.read_text(encoding="utf-8")
        except Exception:
            guion = ""

    audio_files = project_repository.list_audio_files(project_name)
    audio_url = f"/api/editor/audio/{project_name}/{audio_files[0].name}" if audio_files else None

    plan = project_repository.read_editor_plan(project_name)
    escenas = []
    if plan:
        escenas = plan.get("escenas", plan) if isinstance(plan, dict) else plan

    img_lookup = {p.name.lower(): url for p, url in zip(image_paths, images)}
    for i, esc in enumerate(escenas or []):
        fn = (esc.get("imagen_file") or "").lower()
        idx = esc.get("indice", i)
        if fn and fn in img_lookup:
            esc["imagen_url"] = img_lookup[fn]
        elif idx < len(images):
            esc["imagen_url"] = images[idx]
        elif i < len(images):
            esc["imagen_url"] = images[i]
        else:
            esc["imagen_url"] = None

    timestamps = _read_valid_timestamps(project_name)

    return {"name": project_name, "images": images, "guion": guion,
            "audio_url": audio_url, "escenas": escenas, "timestamps": timestamps}


def transcribe_project(project_name: str) -> dict:
    """Transcribe con WhisperX (cascada automatica) y asigna timestamps por escena
    usando el mismo algoritmo que el Render normal. Cachea el resultado en
    timestamps_escenas.json; si ya hay una cache valida, la devuelve sin retranscribir."""
    proj_dir = project_repository.project_dir(project_name)
    if not proj_dir.exists():
        raise FileNotFoundError("proyecto no encontrado")

    cached = _read_valid_timestamps(project_name)
    if cached:
        segs_out = [{"start": float(t.get("inicio", 0)), "end": float(t.get("fin", 0)),
                     "text": t.get("texto", ""), "seg_idx": t.get("escena", 1) - 1}
                    for t in cached]
        return {"segments": segs_out, "total": len(segs_out), "source": "cache"}

    audio_files = project_repository.list_audio_files(project_name)
    if not audio_files:
        raise ValueError("no se encontro audio en el proyecto")
    audio_path = str(audio_files[0])

    guion_lines = project_repository.read_guion_lines(project_name)
    if not guion_lines:
        raise ValueError("No se encontro guion en el proyecto")

    duracion_total = ffmpeg_utils.ffprobe_duration(audio_path)
    if duracion_total <= 0:
        duracion_total = sum(max(1.5, len(line.split()) / 2.5) for line in guion_lines)

    segmentos, all_words, source = whisper_client.transcribe_with_fallback(audio_path)

    if source == "guion_estimate" or not segmentos:
        timestamps = scene_timestamp_service.proporcional(guion_lines, duracion_total)
    else:
        timestamps = scene_timestamp_service.assign_timestamps_auto(
            guion_lines, segmentos, all_words, duracion_total)

    ts_records = [
        {"escena": i + 1, "seg_idx": i, "texto": guion_lines[i] if i < len(guion_lines) else "",
         "inicio": t["inicio"], "fin": t["fin"], "duracion": t["duracion"],
         "score": t.get("score", 1.0), "source": source}
        for i, t in enumerate(timestamps)
    ]
    project_repository.write_scene_timestamps(project_name, ts_records)

    segs_out = [{"start": t["inicio"], "end": t["fin"], "text": t["texto"], "seg_idx": i}
                for i, t in enumerate(ts_records)]
    return {"segments": segs_out, "total": len(segs_out), "source": source}


def start_render(*, project: str, guion: str = "", resolucion: str = "1920x1080",
                  transicion: str = "xfade", trans_dur: float = 0.6,
                  movimiento: str = "none", modelo: str = "base",
                  render_mode: str = "smart") -> dict:
    """Dispara el render final desde el editor visual. Delega en
    render_service.start_render (el mismo worker/job registry que /api/render_inteligente)
    en vez de reimplementar la busqueda de audio/imagenes/videos. Por decision explicita
    del usuario, esta puerta de entrada NO aplica limite de plan (a diferencia de
    /api/render_inteligente) -- asi se comportaba el original."""
    return render_service.start_render(
        project_name=project, render_mode=render_mode, guion=guion, resolucion=resolucion,
        modelo=modelo, whisper_backend="whisperx", transicion=transicion, trans_dur=trans_dur,
        movimiento=movimiento, shake=False, audio_upload=None, username=None,
    )
