from apiflask import APIBlueprint
from flask import jsonify

from src.domain.services import usage_service
from src.infrastructure.storage import user_repository
from src.presentation.auth_middleware import get_current_user
from src.presentation.schemas.usage import UsageCheckInSchema, UsageRecordInSchema

usage_bp = APIBlueprint("usage", __name__, url_prefix="/api/usage")


@usage_bp.post("/check")
@usage_bp.input(UsageCheckInSchema)
def check(json_data):
    """Verifica si el usuario puede realizar la accion. Consulta la BD, no confia solo en el cliente."""
    username = get_current_user()
    if not username:
        return jsonify({"allowed": False, "message": "No autenticado"}), 401
    allowed, msg, extra = usage_service.check_limit(username, json_data["type"], json_data["amount"])
    return jsonify({"allowed": allowed, "message": msg, "extra": extra})


@usage_bp.post("/record")
@usage_bp.input(UsageRecordInSchema)
def record(json_data):
    """Registra uso completado. Solo acepta valores positivos y razonables."""
    username = get_current_user()
    if not username:
        return jsonify({"ok": False, "error": "No autenticado"}), 401
    user = user_repository.get_user_full(username)
    if not user:
        return jsonify({"ok": False, "error": "Usuario no encontrado"}), 404
    ok = usage_service.record_usage(user["id"], videos=json_data["videos"], tts_chars=json_data["tts_chars"])
    return jsonify({"ok": ok})
