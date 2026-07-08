from apiflask import APIBlueprint
from flask import jsonify, request, send_file

from src.domain.services import render_service, usage_service
from src.presentation.auth_middleware import get_current_user
from src.utils.logger import get_logger

logger = get_logger(__name__)

render_bp = APIBlueprint("render", __name__, url_prefix="/api")


@render_bp.post("/render_inteligente")
def render_inteligente():
    """Render local hibrido (Modal GPU para imagenes + FFmpeg local para videos).
    Multipart form: project_name, render_mode, guion, resolucion, modelo, whisper_backend,
    transicion, trans_dur, movimiento, shake + archivo audio (opcional, si no se reusa el del proyecto)."""
    username = get_current_user()
    if username:
        ok, msg, extra = usage_service.check_limit(username, "video", 1)
        if not ok:
            return jsonify({"error": msg, "limit_reached": True, "limit_type": "video", "extra": extra}), 429

    try:
        result = render_service.start_render(
            project_name=request.form.get("project_name", ""),
            render_mode=request.form.get("render_mode", "smart"),
            guion=request.form.get("guion", "").strip(),
            resolucion=request.form.get("resolucion", "1920x1080"),
            modelo=request.form.get("modelo", "base"),
            whisper_backend=request.form.get("whisper_backend", "whisperx"),
            transicion=request.form.get("transicion", "none"),
            trans_dur=float(request.form.get("trans_dur", "0.8")),
            movimiento=request.form.get("movimiento", "none"),
            shake=request.form.get("shake", "false") == "true",
            audio_upload=request.files.get("audio"),
            username=username,
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("render_inteligente error")
        return jsonify({"error": str(exc)}), 500


@render_bp.get("/estado/<job_id>")
def estado_job(job_id):
    job = render_service.get_job(job_id)
    if job is None:
        return jsonify({"error": "Job no encontrado"}), 404
    return jsonify(job)


@render_bp.get("/descargar_render/<job_id>")
def descargar_render(job_id):
    job = render_service.get_job(job_id)
    if job is None:
        return jsonify({"error": "no encontrado"}), 404
    path = render_service.get_job_video_path(job_id)
    if not path:
        return jsonify({"error": "video no listo"}), 404
    return send_file(path, as_attachment=True, download_name=f"render_{job_id}.mp4")
