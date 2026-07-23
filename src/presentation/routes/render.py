import json

from apiflask import APIBlueprint
from flask import jsonify, request, send_file

from src.domain.services import render_service, usage_service
from src.presentation.auth_middleware import get_current_user
from src.utils.logger import get_logger

logger = get_logger(__name__)

render_bp = APIBlueprint("render", __name__, url_prefix="/api")


def _parse_filenames(raw: str | None) -> list[str] | None:
    """Decodifica la lista JSON de nombres de archivo que manda el panel de assets
    del Paso 5 (["img_00001.png", ...]). None si el campo no vino -- distinto de
    [] (usuario deselecciono todo a proposito) -- para que start_render sepa si
    debe filtrar o usar todo el proyecto como antes."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, list):
        return None
    return [str(x) for x in parsed if isinstance(x, str)]


@render_bp.post("/render_inteligente")
def render_inteligente():
    """Render local hibrido (Modal GPU para imagenes + FFmpeg local para videos).
    Multipart form: project_name, render_mode, guion, resolucion, modelo, whisper_backend,
    transicion, trans_dur, movimiento, shake, audio_filename, image_filenames (JSON),
    video_filenames (JSON) + archivo audio (opcional, si no se reusa el del proyecto)."""
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
            audio_filename=request.form.get("audio_filename") or None,
            image_filenames=_parse_filenames(request.form.get("image_filenames")),
            video_filenames=_parse_filenames(request.form.get("video_filenames")),
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


@render_bp.post("/render/detener")
def render_detener():
    """Cancela un render individual por job_id -- nunca afecta a otros renders
    en curso. Antes la unica forma de "destrabar" un render colgado era
    reiniciar el backend entero."""
    data = request.get_json(silent=True) or {}
    job_id = str(data.get("job_id", "")).strip()
    if not job_id:
        return jsonify({"error": "Falta job_id"}), 400
    if not render_service.stop_render(job_id):
        return jsonify({"error": "Job no encontrado o ya finalizado"}), 404
    return jsonify({"ok": True})


@render_bp.get("/descargar_render/<job_id>")
def descargar_render(job_id):
    job = render_service.get_job(job_id)
    if job is None:
        return jsonify({"error": "no encontrado"}), 404
    path = render_service.get_job_video_path(job_id)
    if not path:
        return jsonify({"error": "video no listo"}), 404
    return send_file(path, as_attachment=True, download_name=f"render_{job_id}.mp4")
