from apiflask import APIBlueprint
from flask import jsonify, send_file

from src.domain.services import scene_prompt_service, script_service
from src.infrastructure.ai_providers import openai_vision_client
from src.infrastructure.storage import project_repository
from src.presentation.schemas.script import (
    AnalyzeImageInSchema,
    AudioArchivoQuerySchema,
    AudioCargarOutSchema,
    AudioCargarQuerySchema,
    GuionCargarOutSchema,
    GuionCargarQuerySchema,
    GuionGuardarInSchema,
    N8nProxyInSchema,
)

guion_bp = APIBlueprint("guion", __name__, url_prefix="/api/guion")
audio_bp = APIBlueprint("audio", __name__, url_prefix="/api/audio")

_AUDIO_MIME = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}


@guion_bp.post("/guardar")
@guion_bp.input(GuionGuardarInSchema)
def guardar(json_data):
    try:
        return script_service.save_script(json_data["project_name"], json_data["texto"], json_data["prompts"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@guion_bp.get("/cargar")
@guion_bp.input(GuionCargarQuerySchema, location="query")
@guion_bp.output(GuionCargarOutSchema)
def cargar(query_data):
    return script_service.load_script(query_data["project"])


@guion_bp.post("/analyze_image")
@guion_bp.input(AnalyzeImageInSchema)
def analyze_image(json_data):
    out = openai_vision_client.analyze_image_b64(json_data["image_base64"], json_data["mime_type"])
    if not out.get("ok"):
        status = int(out.get("status") or 400)
        return jsonify({k: v for k, v in out.items() if k != "ok"}), status
    return jsonify({"ok": True, "descripcion_completa": out["descripcion_completa"], "json": out.get("json")})


@guion_bp.post("/n8n_proxy")
@guion_bp.input(N8nProxyInSchema)
def n8n_proxy(json_data):
    estilo_ref = (
        json_data["descripcion_estilo"].strip()
        or json_data["descripcion_referencia"].strip()
        or json_data["estilo"].strip()
    )
    try:
        result = scene_prompt_service.generate_prompts(
            json_data["guion"],
            json_data["output_mode"],
            json_data["prompt_mode"],
            json_data["prompt_style"],
            estilo_ref,
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@audio_bp.get("/cargar")
@audio_bp.input(AudioCargarQuerySchema, location="query")
@audio_bp.output(AudioCargarOutSchema)
def audio_cargar(query_data):
    return script_service.list_audio(query_data["project"])


@audio_bp.get("/archivo")
@audio_bp.input(AudioArchivoQuerySchema, location="query")
def audio_archivo(query_data):
    path = project_repository.resolve_safe_file(query_data["project"], "audio", query_data["file"])
    if not path or not path.exists():
        return jsonify({"error": "not found"}), 404
    return send_file(
        str(path),
        mimetype=_AUDIO_MIME.get(path.suffix.lower(), "audio/mpeg"),
        download_name=query_data["file"],
        as_attachment=False,
    )
