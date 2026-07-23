from apiflask import APIBlueprint
from flask import jsonify, request, send_file

from src.domain.services import gentube_animation_service
from src.infrastructure.ai_providers import gentube_bridge
from src.presentation.schemas.gentube import GentubeRunPromptsInSchema
from src.utils.logger import get_logger

logger = get_logger(__name__)

gentube_bp = APIBlueprint("gentube", __name__, url_prefix="/api/gentube")


# ─────────────────────────────────────────────────────────────────
# Bridge de deteccion de sesion (background.js hace chrome.cookies.getAll en
# gentube.app y postea aca -- ver gentube_bridge.py y el comentario del alarm
# "hb" en extensions/flow_extension/background.js).
# ─────────────────────────────────────────────────────────────────


@gentube_bp.post("/bridge-register")
def bridge_register():
    data = request.get_json(silent=True) or {}
    probe = gentube_bridge.set_session_from_cookie(data.get("cookie", ""))
    return jsonify({"ok": bool(probe.get("ok"))})


@gentube_bp.get("/status")
def status():
    return jsonify(gentube_animation_service.get_status())


@gentube_bp.get("/check-login")
def check_login():
    return jsonify(profiles=gentube_animation_service.check_login())


@gentube_bp.post("/login")
def login():
    data = request.get_json(force=True, silent=True) or {}
    account_id = int(data.get("profile", data.get("account_id", 0)))
    try:
        result = gentube_animation_service.start_login(account_id, data.get("cookie", ""))
        return jsonify(result)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@gentube_bp.post("/run-prompts")
@gentube_bp.input(GentubeRunPromptsInSchema)
def run_prompts(json_data):
    try:
        result = gentube_animation_service.start_run(
            json_data["prompts"],
            json_data["slots"],
            json_data["repeat"],
            json_data["output_dir"],
            json_data["ratio"],
            json_data["quality"],
            browser_mode=json_data.get("browser_mode", "chromium"),
        )
        return jsonify(result)
    except (ValueError, RuntimeError) as exc:
        status_code = 409 if isinstance(exc, RuntimeError) else 400
        return jsonify({"error": str(exc)}), status_code


@gentube_bp.post("/stop")
def stop():
    gentube_animation_service.stop()
    return jsonify({"ok": True})


@gentube_bp.post("/reset")
def reset():
    gentube_animation_service.reset()
    return jsonify({"ok": True})


@gentube_bp.get("/images")
def images():
    return jsonify(gentube_animation_service.list_images(request.args.get("dir")))


@gentube_bp.get("/image/<path:name>")
def image(name):
    path = gentube_animation_service.get_image_path(name, request.args.get("dir"))
    if not path:
        return jsonify({"error": "not found"}), 404
    return send_file(path)


@gentube_bp.post("/clear-images")
def clear_images():
    data = request.get_json(silent=True) or {}
    gentube_animation_service.clear_images(data.get("output_dir"))
    return jsonify({"ok": True})
