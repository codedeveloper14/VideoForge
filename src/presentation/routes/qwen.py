from apiflask import APIBlueprint
from flask import current_app, jsonify, request, send_file

from src.domain.services import qwen_animation_service
from src.infrastructure.ai_providers import qwen_bridge
from src.presentation.schemas.qwen import (
    QwenAbrirCarpetaInSchema,
    QwenAccountInSchema,
    QwenDetenerInSchema,
    QwenLogQuerySchema,
    QwenRegenerarInSchema,
    QwenVideoQuerySchema,
    QwenVideosQuerySchema,
)

qwen_bp = APIBlueprint("qwen", __name__, url_prefix="/api/qwen")


def _qwen_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Access-Control-Request-Private-Network"
    )
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


# ─────────────────────────────────────────────────────────────────
# Bridge de la extension para chat.qwen.ai (qwen_bridge.js hace polling normal
# via el mismo puerto Flask que sirve el resto de la app -- ver qwen_bridge.py).
# Cada cuenta corre en su propio proceso de Chromium, asi que `account` es
# siempre el nombre real (account_1, account_2, ...), no un valor fijo.
# ─────────────────────────────────────────────────────────────────


@qwen_bp.route("/poll", methods=["GET", "OPTIONS"])
def poll():
    if request.method == "OPTIONS":
        return _qwen_cors(current_app.make_response("")), 204
    account = request.args.get("account", "")
    max_raw = request.args.get("max", "1")
    try:
        max_take = max(1, int(max_raw))
    except (ValueError, TypeError):
        max_take = 1
    reqs = qwen_bridge.poll(account, max_take)
    return _qwen_cors(jsonify({"requests": reqs}))


@qwen_bp.route("/result", methods=["POST", "OPTIONS"])
def result():
    if request.method == "OPTIONS":
        return _qwen_cors(current_app.make_response("")), 204
    data = request.get_json(silent=True) or {}
    qwen_bridge.post_result(data.get("requestId", ""), data)
    return _qwen_cors(jsonify({"ok": True}))


@qwen_bp.get("/sesiones")
def sesiones():
    try:
        return jsonify({"accounts": qwen_animation_service.list_sessions()})
    except Exception as exc:
        return jsonify({"accounts": [], "error": str(exc)})


@qwen_bp.post("/login_cuenta")
@qwen_bp.input(QwenAccountInSchema)
def login_cuenta(json_data):
    qwen_animation_service.start_account_login(json_data["account"])
    return jsonify({"ok": True, "message": f"Chromium abierto para {json_data['account']}"})


@qwen_bp.post("/borrar_sesion")
@qwen_bp.input(QwenAccountInSchema)
def borrar_sesion(json_data):
    qwen_animation_service.delete_session(json_data["account"])
    return jsonify({"ok": True})


@qwen_bp.post("/iniciar")
def iniciar():
    """Multipart form: project_name, prompt, slots, size, timeout, aspect_ratio
    + archivos imagen_0, imagen_1, ..."""
    project_name = request.form.get("project_name", "").strip()
    prompt = request.form.get("prompt", "Cinematic slow zoom")
    slots = int(request.form.get("slots", 2))
    size = request.form.get("size", "1280x720")
    timeout_sec = int(request.form.get("timeout", 900))
    aspect_ratio = request.form.get("aspect_ratio", "16:9")

    img_keys = sorted(
        (k for k in request.files if k.startswith("imagen_")),
        key=lambda x: int(x.split("_")[1]),
    )
    images = [(request.files[k].filename, request.files[k]) for k in img_keys]

    try:
        result = qwen_animation_service.start_batch(
            project_name,
            images,
            prompt,
            slots,
            size,
            timeout_sec,
            aspect_ratio,
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@qwen_bp.post("/regenerar")
@qwen_bp.input(QwenRegenerarInSchema)
def regenerar(json_data):
    try:
        result = qwen_animation_service.start_regen(
            json_data["project_name"],
            json_data["video_name"],
            json_data["prompt"],
            json_data["size"],
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404


@qwen_bp.post("/detener")
@qwen_bp.input(QwenDetenerInSchema)
def detener(json_data):
    qwen_animation_service.stop(json_data["project"])
    return jsonify({"ok": True})


@qwen_bp.get("/log")
@qwen_bp.input(QwenLogQuerySchema, location="query")
def log(query_data):
    return jsonify(qwen_animation_service.get_log_state(query_data["offset"], query_data["project"]))


@qwen_bp.get("/videos")
@qwen_bp.input(QwenVideosQuerySchema, location="query")
def videos(query_data):
    return jsonify(qwen_animation_service.list_videos(query_data["project"]))


@qwen_bp.get("/video")
@qwen_bp.input(QwenVideoQuerySchema, location="query")
def video(query_data):
    path = qwen_animation_service.get_video_path(query_data["project"], query_data["file"])
    if not path or not path.exists():
        return jsonify({"error": "not found"}), 404
    return send_file(
        str(path),
        as_attachment=query_data["dl"] == "1",
        download_name=query_data["file"],
        mimetype="video/mp4",
        conditional=True,
    )


@qwen_bp.get("/descargar_todas")
@qwen_bp.input(QwenVideosQuerySchema, location="query")
def descargar_todas(query_data):
    result = qwen_animation_service.build_videos_zip(query_data["project"])
    if not result:
        return jsonify({"error": "Sin videos"}), 404
    buf, zip_name = result
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=zip_name)


@qwen_bp.post("/abrir_carpeta")
@qwen_bp.input(QwenAbrirCarpetaInSchema)
def abrir_carpeta(json_data):
    try:
        qwen_animation_service.open_videos_folder(json_data["project"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"ok": True})
