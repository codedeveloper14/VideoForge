from apiflask import APIBlueprint
from flask import abort, jsonify

from src.domain.services import docs_service
from src.presentation.auth_middleware import get_current_user
from src.presentation.schemas.docs import DocInSchema, HelpSubmitInSchema
from src.utils.logger import get_logger

logger = get_logger(__name__)

docs_bp = APIBlueprint("docs", __name__, url_prefix="/api")
admin_docs_bp = APIBlueprint("admin_docs", __name__, url_prefix="/api/admin/docs")


def _require_admin() -> str:
    """Aborta con 403 si el usuario actual no es admin. Devuelve el username.
    El original solo protegia la pagina HTML de administracion, no estas rutas de
    API -- cualquier usuario autenticado podia crear/editar/borrar docs llamandolas
    directo. Se corrige aqui: cada ruta admin valida el rol server-side."""
    username = get_current_user()
    if not docs_service.is_admin(username):
        abort(403)
    return username


@docs_bp.get("/docs")
def public_docs():
    try:
        return jsonify(docs_service.list_public_docs())
    except Exception as exc:
        logger.exception("api_docs_public error")
        return jsonify({"error": str(exc)}), 500


@docs_bp.post("/help")
@docs_bp.input(HelpSubmitInSchema)
def submit_help(json_data):
    username = get_current_user()
    try:
        docs_service.submit_help_report(username, json_data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("api_help_submit error")
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True})


@admin_docs_bp.get("")
def admin_list():
    _require_admin()
    try:
        return jsonify(docs_service.list_admin_docs())
    except Exception as exc:
        logger.exception("api_admin_docs_list error")
        return jsonify({"error": str(exc)}), 500


@admin_docs_bp.post("")
@admin_docs_bp.input(DocInSchema)
def admin_create(json_data):
    username = _require_admin()
    try:
        new_id = docs_service.create_doc(json_data, username)
        return jsonify({"id": new_id}), 201
    except Exception as exc:
        logger.exception("api_admin_docs_create error")
        return jsonify({"error": str(exc)}), 500


@admin_docs_bp.put("/<int:doc_id>")
@admin_docs_bp.input(DocInSchema)
def admin_update(json_data, doc_id):
    _require_admin()
    try:
        docs_service.update_doc(doc_id, json_data)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.exception("api_admin_docs_update error")
        return jsonify({"error": str(exc)}), 500


@admin_docs_bp.delete("/<int:doc_id>")
def admin_delete(doc_id):
    _require_admin()
    try:
        docs_service.delete_doc(doc_id)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.exception("api_admin_docs_delete error")
        return jsonify({"error": str(exc)}), 500
