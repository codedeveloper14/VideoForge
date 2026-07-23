from apiflask import APIBlueprint
from flask import current_app, jsonify, request, send_file

from src.domain.services import vibes_animation_service
from src.infrastructure.ai_providers import vibes_bridge
from src.presentation.schemas.vibes import (
    VibesAbrirCarpetaInSchema,
    VibesAccountInSchema,
    VibesDetenerInSchema,
    VibesLogQuerySchema,
    VibesVideoQuerySchema,
    VibesVideosQuerySchema,
)

vibes_bp = APIBlueprint("vibes", __name__, url_prefix="/api/vibes")


def _vibes_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Access-Control-Request-Private-Network"
    )
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


# ─────────────────────────────────────────────────────────────────
# Bridge de la extension para vibes.ai (vibes_bridge.js hace polling normal
# via el mismo puerto Flask que sirve el resto de la app -- ver vibes_bridge.py)
# ─────────────────────────────────────────────────────────────────


@vibes_bp.route("/poll", methods=["GET", "OPTIONS"])
def poll():
    if request.method == "OPTIONS":
        return _vibes_cors(current_app.make_response("")), 204
    account = request.args.get("account", "default")
    max_raw = request.args.get("max", "1")
    try:
        max_take = max(1, int(max_raw))
    except (ValueError, TypeError):
        max_take = 1
    reqs = vibes_bridge.poll(account, max_take)
    return _vibes_cors(jsonify({"requests": reqs}))


@vibes_bp.route("/result", methods=["POST", "OPTIONS"])
def result():
    if request.method == "OPTIONS":
        return _vibes_cors(current_app.make_response("")), 204
    data = request.get_json(silent=True) or {}
    vibes_bridge.post_result(data.get("requestId", ""), data)
    return _vibes_cors(jsonify({"ok": True}))


# ─────────────────────────────────────────────────────────────────
# Sesion
# ─────────────────────────────────────────────────────────────────


@vibes_bp.get("/sesiones")
def sesiones():
    try:
        return jsonify({"accounts": vibes_animation_service.list_sessions()})
    except Exception as exc:
        return jsonify({"accounts": [], "error": str(exc)})


@vibes_bp.post("/login_cuenta")
@vibes_bp.input(VibesAccountInSchema)
def login_cuenta(json_data):
    name = vibes_animation_service.start_account_login(json_data["account"])
    return jsonify({"ok": True, "message": f"Abriendo login de Vibes para {name}"})


@vibes_bp.post("/borrar_sesion")
@vibes_bp.input(VibesAccountInSchema)
def borrar_sesion(json_data):
    vibes_animation_service.delete_session(json_data["account"])
    return jsonify({"ok": True})


@vibes_bp.post("/launch_chrome")
def launch_chrome():
    try:
        result = vibes_animation_service.launch_chrome()
        return jsonify(result)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 400


# ─────────────────────────────────────────────────────────────────
# Generacion por lote
# ─────────────────────────────────────────────────────────────────


@vibes_bp.post("/iniciar")
def iniciar():
    """Multipart form: project_name, prompt, slots, timeout, reference_image (b64,
    solo si NO se suben imagenes) + archivos imagen_0, imagen_1, ... (opcionales --
    una por job, "slots" videos c/u; sin imagenes cae al modo prompt+variaciones)."""
    project_name = request.form.get("project_name", "").strip()
    prompt = request.form.get("prompt", "")
    slots = int(request.form.get("slots", 1))
    timeout_sec = int(request.form.get("timeout", 300))
    reference_image = request.form.get("reference_image") or None

    img_keys = sorted(
        (k for k in request.files if k.startswith("imagen_")),
        key=lambda x: int(x.split("_")[1]),
    )
    images = [(request.files[k].filename, request.files[k]) for k in img_keys] or None

    try:
        result = vibes_animation_service.start_batch(
            project_name,
            prompt,
            slots,
            timeout_sec,
            images=images,
            ref_image_b64=reference_image if not images else None,
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@vibes_bp.post("/detener")
@vibes_bp.input(VibesDetenerInSchema)
def detener(json_data):
    vibes_animation_service.stop(json_data["project"])
    return jsonify({"ok": True})


@vibes_bp.get("/log")
@vibes_bp.input(VibesLogQuerySchema, location="query")
def log(query_data):
    return jsonify(vibes_animation_service.get_log_state(query_data["offset"], query_data["project"]))


@vibes_bp.get("/videos")
@vibes_bp.input(VibesVideosQuerySchema, location="query")
def videos(query_data):
    return jsonify(vibes_animation_service.list_videos(query_data["project"]))


@vibes_bp.get("/video")
@vibes_bp.input(VibesVideoQuerySchema, location="query")
def video(query_data):
    path = vibes_animation_service.get_video_path(query_data["project"], query_data["file"])
    if not path or not path.exists():
        return jsonify({"error": "not found"}), 404
    return send_file(
        str(path),
        as_attachment=query_data["dl"] == "1",
        download_name=query_data["file"],
        mimetype="video/mp4",
        conditional=True,
    )


@vibes_bp.get("/descargar_todas")
@vibes_bp.input(VibesVideosQuerySchema, location="query")
def descargar_todas(query_data):
    result = vibes_animation_service.build_videos_zip(query_data["project"])
    if not result:
        return jsonify({"error": "Sin videos"}), 404
    buf, zip_name = result
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=zip_name)


@vibes_bp.post("/abrir_carpeta")
@vibes_bp.input(VibesAbrirCarpetaInSchema)
def abrir_carpeta(json_data):
    try:
        vibes_animation_service.open_videos_folder(json_data["project"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"ok": True})
