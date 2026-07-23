from apiflask import APIBlueprint
from flask import jsonify, request

from src.domain.services import voice_service
from src.presentation.auth_middleware import get_current_user
from src.presentation.schemas.voice import VozGenerarInSchema

voice_bp = APIBlueprint("voice", __name__, url_prefix="/api/voz")

_JSON_HEADERS = {"Content-Type": "application/json; charset=utf-8"}


@voice_bp.get("/voces")
def voces():
    """Lista las voces disponibles (proxy a n8n, normaliza la forma de la respuesta)."""
    body, status = voice_service.get_voices()
    return body, status, _JSON_HEADERS


@voice_bp.post("/generar")
@voice_bp.input(VozGenerarInSchema)
def generar(json_data):
    """Genera audio TTS via n8n. Verifica el limite de caracteres/mes del plan del usuario."""
    username = get_current_user()
    result = voice_service.generate_voice(username, json_data["voice_id"], json_data["data"])
    status_code = result.pop("status_code")
    return jsonify(result), status_code


@voice_bp.post("/fusionar")
def fusionar():
    """Fusiona fragmentos de audio via n8n y guarda el audio final en el proyecto."""
    data = request.get_json(silent=True) or {}
    project_name = data.pop("project_name", "")
    body, status = voice_service.merge_audio(project_name, data)
    return body, status, _JSON_HEADERS


@voice_bp.post("/clonar")
def clonar():
    """Proxy de clonacion de voz hacia n8n."""
    data = request.get_json(silent=True) or {}
    body, status = voice_service.clone_voice(data)
    return body, status, _JSON_HEADERS
