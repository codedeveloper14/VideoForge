from apiflask import APIBlueprint
from flask import current_app, jsonify, request, send_file

from src.domain.services import meta_animation_service
from src.domain.services.meta_animation_service import bridge
from src.infrastructure.ai_providers import vibes_bridge
from src.presentation.schemas.meta import (
    MetaAbrirCarpetaInSchema,
    MetaAccountInSchema,
    MetaLaunchChromeInSchema,
    MetaLogQuerySchema,
    MetaOpenDevmodeInSchema,
    MetaVideoQuerySchema,
    MetaVideosQuerySchema,
)

meta_bp = APIBlueprint("meta", __name__, url_prefix="/api/meta")


def _cors_empty():
    return bridge.cors(current_app.make_response(""))


def _vibes_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Access-Control-Request-Private-Network"
    )
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


# ─────────────────────────────────────────────────────────────────
# Bridge de la extension para vibes.ai (polling normal via el mismo
# puerto Flask -- ver comentario en vibes_bridge.py)
# ─────────────────────────────────────────────────────────────────


@meta_bp.route("/vibes-poll", methods=["GET", "OPTIONS"])
def vibes_poll():
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


@meta_bp.route("/vibes-result", methods=["POST", "OPTIONS"])
def vibes_result():
    if request.method == "OPTIONS":
        return _vibes_cors(current_app.make_response("")), 204
    data = request.get_json(silent=True) or {}
    vibes_bridge.post_result(data.get("requestId", ""), data)
    return _vibes_cors(jsonify({"ok": True}))


# ─────────────────────────────────────────────────────────────────
# Bridge de la extension de Chrome (meta_bridge.js hace polling aqui)
# ─────────────────────────────────────────────────────────────────


@meta_bp.route("/ext-register", methods=["GET", "POST", "OPTIONS"])
def ext_register():
    if request.method == "OPTIONS":
        return _cors_empty(), 204
    jb = request.get_json(silent=True) or {}
    account = request.args.get("account", "") or jb.get("account", "")
    tab_url = request.args.get("url", "") or jb.get("url", "")
    return bridge.cors(jsonify(bridge.register(account, tab_url)))


@meta_bp.route("/ext-poll", methods=["GET", "OPTIONS"])
def ext_poll():
    if request.method == "OPTIONS":
        return _cors_empty(), 204
    account = request.args.get("account", "")
    tab_url = request.args.get("url", "")
    max_raw = request.args.get("max", None)
    try:
        max_take = max(0, int(max_raw)) if max_raw is not None else 1
    except (ValueError, TypeError):
        max_take = 1
    return bridge.cors(
        jsonify(bridge.poll(account, tab_url, max_take, log=meta_animation_service.log_message))
    )


@meta_bp.route("/ext-result", methods=["POST", "OPTIONS"])
def ext_result():
    if request.method == "OPTIONS":
        return _cors_empty(), 204
    data = request.get_json(silent=True) or {}
    bridge.post_result(
        data.get("requestId", ""), data.get("url"), data.get("error"), log=meta_animation_service.log_message
    )
    return bridge.cors(jsonify({"ok": True}))


@meta_bp.route("/ext-learn", methods=["POST", "OPTIONS"])
def ext_learn():
    """La extension reporta lo que aprendio de la red (gen_doc_id, oauth_token...)."""
    if request.method == "OPTIONS":
        return _cors_empty(), 204
    data = request.get_json(silent=True) or {}
    account = data.get("account", "")
    state = data.get("state", {})
    if account and state:
        meta_animation_service.learn_ext_state(state)
        gen_did = state.get("gen_doc_id", "")
        sm_ready = bool(state.get("send_msg_did") and state.get("send_msg_tpl"))
        meta_animation_service.log_message(
            f"Aprendido [{account[:12]}]: gen_doc_id={gen_did or '?'} "
            f"send_msg={'OK' if sm_ready else 'FALTA'} "
            f"oauth={'OK' if state.get('oauth_token') else 'FALTA'} "
            f"vars_tpl={'OK' if state.get('gen_vars_tpl') else 'FALTA'}"
        )
    return bridge.cors(jsonify({"ok": True}))


@meta_bp.route("/ext-state", methods=["GET", "OPTIONS"])
def ext_state():
    """Devuelve credenciales estables para inyectar en nuevas pestanas."""
    if request.method == "OPTIONS":
        return _cors_empty(), 204
    safe = meta_animation_service.get_ext_state_safe()
    return bridge.cors(jsonify({"state": safe, "has_gen_doc_id": bool(safe.get("gen_doc_id"))}))


@meta_bp.route("/ext-captured", methods=["POST", "OPTIONS"])
def ext_captured():
    """Recibe el log de llamadas de red capturadas durante una generacion (solo diagnostico)."""
    if request.method == "OPTIONS":
        return _cors_empty(), 204
    data = request.get_json(silent=True) or {}
    account = data.get("account", "")
    rid = data.get("requestId", "")
    cap = data.get("captured", [])
    if cap:
        meta_animation_service.log_message(
            f"[{rid[:8]}] Capturadas {len(cap)} llamadas de red [{account[:12]}]"
        )
    return bridge.cors(jsonify({"ok": True}))


# ─────────────────────────────────────────────────────────────────
# Sesiones
# ─────────────────────────────────────────────────────────────────


@meta_bp.get("/sesiones")
def sesiones():
    try:
        return jsonify({"accounts": meta_animation_service.list_sessions()})
    except Exception as exc:
        return jsonify({"accounts": [], "error": str(exc)})


@meta_bp.post("/login_cuenta")
@meta_bp.input(MetaAccountInSchema)
def login_cuenta(json_data):
    folder_name = meta_animation_service.start_account_login(json_data["account"])
    return jsonify({"ok": True, "message": f"Chrome abierto para {folder_name}"})


@meta_bp.post("/borrar_sesion")
@meta_bp.input(MetaAccountInSchema)
def borrar_sesion(json_data):
    meta_animation_service.delete_session(json_data["account"])
    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────
# Generacion por lote
# ─────────────────────────────────────────────────────────────────


@meta_bp.post("/iniciar")
def iniciar():
    """Multipart form: project_name, prompt, slots, mode (ext|http), timeout
    + archivos imagen_0, imagen_1, ..."""
    project_name = request.form.get("project_name", "").strip()
    prompt = request.form.get("prompt", "Cinematic slow zoom")
    slots = int(request.form.get("slots", 1))
    mode = request.form.get("mode", "ext")
    timeout_sec = int(request.form.get("timeout", 900))

    img_keys = sorted(
        (k for k in request.files if k.startswith("imagen_")),
        key=lambda x: int(x.split("_")[1]),
    )
    images = [(request.files[k].filename, request.files[k]) for k in img_keys]

    try:
        result = meta_animation_service.start_batch(project_name, images, prompt, slots, mode, timeout_sec)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@meta_bp.post("/detener")
def detener():
    meta_animation_service.stop()
    return jsonify({"ok": True})


@meta_bp.get("/log")
@meta_bp.input(MetaLogQuerySchema, location="query")
def log(query_data):
    return jsonify(meta_animation_service.get_log_state(query_data["offset"]))


@meta_bp.get("/videos")
@meta_bp.input(MetaVideosQuerySchema, location="query")
def videos(query_data):
    return jsonify(meta_animation_service.list_videos(query_data["project"]))


@meta_bp.get("/video")
@meta_bp.input(MetaVideoQuerySchema, location="query")
def video(query_data):
    path = meta_animation_service.get_video_path(query_data["project"], query_data["file"])
    if not path or not path.exists():
        return jsonify({"error": "not found"}), 404
    return send_file(
        str(path),
        as_attachment=query_data["dl"] == "1",
        download_name=query_data["file"],
        mimetype="video/mp4",
        conditional=True,
    )


@meta_bp.get("/descargar_todas")
@meta_bp.input(MetaVideosQuerySchema, location="query")
def descargar_todas(query_data):
    result = meta_animation_service.build_videos_zip(query_data["project"])
    if not result:
        return jsonify({"error": "Sin videos"}), 404
    buf, zip_name = result
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=zip_name)


@meta_bp.post("/abrir_carpeta")
@meta_bp.input(MetaAbrirCarpetaInSchema)
def abrir_carpeta(json_data):
    try:
        meta_animation_service.open_videos_folder(json_data["project"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────
# Lanzar Chrome manualmente (worker permanente / modo dev)
# ─────────────────────────────────────────────────────────────────


@meta_bp.post("/launch_chrome")
@meta_bp.input(MetaLaunchChromeInSchema)
def launch_chrome(json_data):
    try:
        result = meta_animation_service.launch_chrome(json_data["account"], json_data["slots"])
        return jsonify(result)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 400


@meta_bp.post("/open_devmode")
@meta_bp.input(MetaOpenDevmodeInSchema)
def open_devmode(json_data):
    try:
        result = meta_animation_service.open_devmode(json_data["account"])
        return jsonify(result)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 400
