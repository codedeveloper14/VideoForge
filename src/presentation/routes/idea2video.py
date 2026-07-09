from apiflask import APIBlueprint
from flask import jsonify, send_file

from src.domain.services import idea2video_service
from src.presentation.schemas.idea2video import (
    Idea2VideoAutopilotInSchema,
    Idea2VideoImageQuerySchema,
    Idea2VideoScriptInSchema,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

idea2video_bp = APIBlueprint("idea2video", __name__, url_prefix="/api/idea2video")


@idea2video_bp.post("/script")
@idea2video_bp.input(Idea2VideoScriptInSchema)
def script(json_data):
    try:
        result = idea2video_service.generate_script(
            idea=json_data["idea"], dur_sec=json_data["dur"], style=json_data["style"],
            tone=json_data["tone"], audience=json_data["audience"],
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


@idea2video_bp.post("/autopilot")
@idea2video_bp.input(Idea2VideoAutopilotInSchema)
def autopilot(json_data):
    try:
        result = idea2video_service.start_autopilot(
            script=json_data["script"], title=json_data.get("title", ""),
            voice_id=json_data.get("voice_id", ""), ref_image=json_data.get("ref_image"),
            mode=json_data.get("mode", "rapido"),
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@idea2video_bp.get("/autopilot/<job_id>")
def autopilot_status(job_id):
    result = idea2video_service.get_autopilot_status(job_id)
    if result is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(result)


@idea2video_bp.post("/autopilot/<job_id>/abrir_carpeta")
def autopilot_abrir_carpeta(job_id):
    try:
        idea2video_service.open_autopilot_folder(job_id)
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@idea2video_bp.get("/ap_imagen")
@idea2video_bp.input(Idea2VideoImageQuerySchema, location="query")
def ap_imagen(query_data):
    path = idea2video_service.get_autopilot_image(query_data["project"], query_data["file"])
    if not path:
        return "", 404
    resp = send_file(str(path))
    resp.headers["Cache-Control"] = "no-store, no-cache"
    return resp
