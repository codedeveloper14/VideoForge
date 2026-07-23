from apiflask import APIBlueprint
from flask import jsonify, request, send_file

from src.domain.services import quick_render_service
from src.infrastructure.jobs import job_registry, task_tracker
from src.utils.logger import get_logger

logger = get_logger(__name__)

quick_render_bp = APIBlueprint("quick_render", __name__, url_prefix="/api")


@quick_render_bp.post("/generar")
def generar():
    """El pipeline original: sube guion + audio + imagenes directo (sin proyecto) y
    genera el video. Multipart form: guion, resolucion, fade, modelo, whisper_backend,
    transicion, movimiento, trans_dur, shake + audio + imagen_0, imagen_1, ..."""
    try:
        img_keys = sorted(
            (k for k in request.files if k.startswith("imagen_")),
            key=lambda x: int(x.split("_")[1]),
        )
        result = quick_render_service.start_render(
            audio_upload=request.files.get("audio"),
            guion=request.form.get("guion", ""),
            image_uploads=[request.files[k] for k in img_keys],
            resolucion=request.form.get("resolucion", "1920x1080"),
            fade=float(request.form.get("fade", "0")),
            modelo=request.form.get("modelo", "base"),
            whisper_backend=request.form.get("whisper_backend", "whisperx"),
            transicion=request.form.get("transicion", "none"),
            movimiento=request.form.get("movimiento", "none"),
            trans_dur=float(request.form.get("trans_dur", "0.8")),
            shake=request.form.get("shake", "false"),
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("generar_video error")
        return jsonify({"error": str(exc)}), 500


@quick_render_bp.get("/descargar/<job_id>")
def descargar(job_id):
    path = quick_render_service.get_job_video_path(job_id)
    if not path:
        return jsonify({"error": "Video no encontrado"}), 404
    return send_file(path, as_attachment=True, download_name=f"video_{job_id}.mp4")


@quick_render_bp.get("/multitask/jobs")
def multitask_jobs():
    """Actividad para el panel de tareas del frontend: jobs de render (con progreso
    real) + tareas sincronas breves (task_tracker), ordenados por mas reciente."""
    task_tracker.clean_old_tasks()
    result = []
    for job in job_registry.all_jobs():
        result.append(
            {
                "id": job.get("id", ""),
                "estado": job.get("estado", "?"),
                "progreso": job.get("progreso", 0),
                "mensaje": job.get("mensaje", ""),
                "inicio": job.get("inicio", 0),
                "video_url": job.get("video_url"),
                "tipo": job.get("tipo", "render"),
                "proyecto": job.get("proyecto", ""),
            }
        )
    for task in task_tracker.all_tasks():
        result.append(
            {
                "id": task.get("id", ""),
                "estado": task.get("estado", "?"),
                "progreso": task.get("progreso", 0),
                "mensaje": task.get("mensaje", ""),
                "inicio": task.get("inicio", 0),
                "video_url": None,
                "tipo": task.get("tipo", "tarea"),
                "proyecto": task.get("proyecto", ""),
            }
        )
    result.sort(key=lambda x: x["inicio"], reverse=True)
    return jsonify(result)
