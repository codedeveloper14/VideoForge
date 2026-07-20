from apiflask import APIBlueprint
from flask import Response, jsonify, request, send_file

from src.domain.services import flow_animation_service
from src.infrastructure.ai_providers import flow_bridge, vibes_client
from src.presentation.schemas.flow import (
    FlowImageQuerySchema,
    FlowImagesQuerySchema,
    FlowMtimeQuerySchema,
    FlowProfileDumpQuerySchema,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

flow_bp = APIBlueprint("flow", __name__, url_prefix="/api/flow")


def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@flow_bp.route("/save-cookie", methods=["POST", "OPTIONS"])
def save_cookie():
    if request.method == "OPTIONS":
        return _cors(Response("", 204))
    data = request.get_json(force=True, silent=True) or {}
    idx = int(data.get("account", data.get("account_id", 0)))
    cookie = (data.get("cookie") or data.get("cookie_str") or "").strip()
    try:
        result = flow_animation_service.save_account_cookie(idx, cookie)
        return _cors(jsonify(result))
    except ValueError as exc:
        return _cors(jsonify({"error": str(exc)})), 400
    except Exception as exc:
        logger.exception("flow save_cookie error")
        return _cors(jsonify({"error": str(exc)})), 500


@flow_bp.get("/profile-dump")
@flow_bp.input(FlowProfileDumpQuerySchema, location="query")
def profile_dump(query_data):
    return _cors(jsonify(flow_animation_service.profile_dump(query_data["idx"])))


@flow_bp.get("/accounts")
def accounts():
    return jsonify({"accounts": flow_animation_service.check_accounts()})


@flow_bp.get("/bridge-status")
def bridge_status():
    flow_bridge.start_bridge(flow_animation_service.log)
    status = flow_bridge.status()
    # El bridge (WS/HTTP 5556/5557) es compartido con Vibes -- sin este filtro, la
    # tarjeta "Estado de Google Flow" del panel de Flow lista tambien la pestaña de
    # vibes.ai (hash fijo VIBES_ACCOUNT_HASH, "vibes:default"), confundiendo al usuario.
    status["accounts"] = [
        a for a in status.get("accounts", []) if a.get("account_hash") != vibes_client.VIBES_ACCOUNT_HASH
    ]
    return _cors(jsonify(status))


@flow_bp.post("/login")
def login():
    data = request.get_json(force=True, silent=True) or {}
    idx = int(data.get("account", data.get("account_id", 0)))
    try:
        return jsonify(flow_animation_service.start_login(idx))
    except Exception as exc:
        logger.exception("flow login error")
        return jsonify({"error": str(exc)}), 500


@flow_bp.get("/chromium-status")
def chromium_status():
    return _cors(jsonify({"profiles": flow_animation_service.chromium_status()}))


@flow_bp.post("/open-all")
def open_all():
    flow_animation_service.auto_open_browsers()
    return jsonify({"ok": True})


@flow_bp.post("/reset-chromium")
def reset_chromium():
    return _cors(jsonify(flow_animation_service.reset_chromium()))


@flow_bp.post("/reset-chromium-profile")
def reset_chromium_profile():
    data = request.get_json(force=True, silent=True) or {}
    try:
        idx = int(data.get("idx", -1))
        return _cors(jsonify(flow_animation_service.reset_chromium_profile(idx)))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@flow_bp.post("/run-prompts")
def run_prompts():
    flow_animation_service.log("[Flow] /api/flow/run-prompts recibido")
    data = request.get_json(force=True, silent=True) or {}
    model = data.get("model", "NANO_BANANA_2")
    default_slots = 5 if model == "IMAGE_GENERATION_001_IMAGEN4" else 2
    try:
        result = flow_animation_service.start_run(
            prompts=data.get("prompts", []),
            out_dir=data.get("output_dir", ""),
            slots=max(1, min(10, int(data.get("slots", default_slots)))),
            aspect=data.get("aspect_ratio", "IMAGE_ASPECT_RATIO_LANDSCAPE"),
            model=model,
            max_retries=max(1, min(5, int(data.get("max_retries", 2)))),
            ref_image=(data.get("reference_image") or "").strip() or None,
            auto_open=bool(data.get("auto_open")),
            browser_mode=(data.get("browser_mode") or "auto").strip().lower(),
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409


@flow_bp.post("/stop")
def stop():
    flow_animation_service.stop()
    return jsonify({"ok": True})


@flow_bp.post("/reset-lock")
def reset_lock():
    return jsonify(flow_animation_service.reset_lock())


@flow_bp.post("/retry")
def retry():
    data = request.get_json(force=True, silent=True) or {}
    try:
        result = flow_animation_service.retry_one(
            out_dir=(data.get("output_dir") or "").strip(),
            idx=data.get("index"),
            filename=(data.get("filename") or "").strip(),
            fallback_prompts=data.get("fallback_prompts") or [],
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@flow_bp.get("/status")
def status():
    since = int(request.args.get("since", 0))
    return jsonify(flow_animation_service.get_status(since))


@flow_bp.get("/full-log")
def full_log():
    return flow_animation_service.get_full_log(), 200, {"Content-Type": "text/plain; charset=utf-8"}


@flow_bp.post("/abrir_carpeta")
def abrir_carpeta():
    try:
        return jsonify(flow_animation_service.abrir_carpeta())
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400


@flow_bp.get("/images")
@flow_bp.input(FlowImagesQuerySchema, location="query")
def images(query_data):
    return jsonify({"images": flow_animation_service.list_images(query_data["dir"])})


@flow_bp.get("/mtime")
@flow_bp.input(FlowMtimeQuerySchema, location="query")
def mtime(query_data):
    return jsonify({"mtime": flow_animation_service.get_mtime(query_data["dir"], query_data["file"])})


@flow_bp.get("/image")
@flow_bp.input(FlowImageQuerySchema, location="query")
def image(query_data):
    path = flow_animation_service.get_image_path(query_data["dir"], query_data["file"])
    if not path:
        return "", 404
    resp = send_file(path)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp
