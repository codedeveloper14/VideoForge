from apiflask import APIBlueprint
from flask import jsonify, request, send_file

from src.domain.services import grok_animation_service
from src.infrastructure.ai_providers import grok_session_bridge
from src.presentation.schemas.grok import (
    GrokAbrirCarpetaInSchema,
    GrokAccountInSchema,
    GrokDetenerInSchema,
    GrokLogQuerySchema,
    GrokRegenerarInSchema,
    GrokVideoQuerySchema,
    GrokVideosQuerySchema,
)

grok_bp = APIBlueprint("grok", __name__, url_prefix="/api/grok")


# ─────────────────────────────────────────────────────────────────
# Bridge de deteccion de sesion (background.js hace chrome.cookies.getAll en
# grok.com y postea aca -- SOLO detecta/captura sesion, la generacion sigue
# siendo API HTTP directa. Ver grok_session_bridge.py.)
# ─────────────────────────────────────────────────────────────────


@grok_bp.post("/bridge-register")
def bridge_register():
    data = request.get_json(silent=True) or {}
    result = grok_session_bridge.set_session_from_cookies(data.get("cookies", []))
    return jsonify({"ok": bool(result.get("ok"))})


@grok_bp.get("/sesiones")
def sesiones():
    try:
        return jsonify({"accounts": grok_animation_service.list_sessions()})
    except Exception as exc:
        return jsonify({"accounts": [], "error": str(exc)})


@grok_bp.post("/login_cuenta")
@grok_bp.input(GrokAccountInSchema)
def login_cuenta(json_data):
    grok_animation_service.start_account_login(json_data["account"])
    return jsonify({"ok": True, "message": f"Chrome abierto para {json_data['account']}"})


@grok_bp.post("/borrar_sesion")
@grok_bp.input(GrokAccountInSchema)
def borrar_sesion(json_data):
    grok_animation_service.delete_session(json_data["account"])
    return jsonify({"ok": True})


@grok_bp.post("/iniciar")
def iniciar():
    """Multipart form: project_name, prompt, slots, aspect_ratio, video_length,
    resolution + archivos imagen_0, imagen_1, ... (orden por sufijo numerico)."""
    project_name = request.form.get("project_name", "").strip()
    prompt = request.form.get("prompt", "Cinematic slow zoom")
    slots = int(request.form.get("slots", 3))
    aspect_ratio = request.form.get("aspect_ratio", "2:3")
    video_length = int(request.form.get("video_length", 6))
    resolution = request.form.get("resolution", "480p")

    img_keys = sorted(
        (k for k in request.files if k.startswith("imagen_")),
        key=lambda x: int(x.split("_")[1]),
    )
    images = [(request.files[k].filename, request.files[k]) for k in img_keys]

    try:
        result = grok_animation_service.start_batch(
            project_name,
            images,
            prompt,
            slots,
            aspect_ratio,
            video_length,
            resolution,
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@grok_bp.post("/regenerar")
@grok_bp.input(GrokRegenerarInSchema)
def regenerar(json_data):
    try:
        result = grok_animation_service.start_regen(
            json_data["project_name"],
            json_data["video_name"],
            json_data["prompt"],
            json_data["aspect_ratio"],
            json_data["video_length"],
            json_data["resolution"],
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404


@grok_bp.post("/detener")
@grok_bp.input(GrokDetenerInSchema)
def detener(json_data):
    grok_animation_service.stop(json_data["project"])
    return jsonify({"ok": True})


@grok_bp.get("/log")
@grok_bp.input(GrokLogQuerySchema, location="query")
def log(query_data):
    return jsonify(grok_animation_service.get_log_state(query_data["offset"], query_data["project"]))


@grok_bp.get("/videos")
@grok_bp.input(GrokVideosQuerySchema, location="query")
def videos(query_data):
    return jsonify(grok_animation_service.list_videos(query_data["project"]))


@grok_bp.get("/video")
@grok_bp.input(GrokVideoQuerySchema, location="query")
def video(query_data):
    path = grok_animation_service.get_video_path(query_data["project"], query_data["file"])
    if not path or not path.exists():
        return jsonify({"error": "not found"}), 404
    return send_file(
        str(path),
        as_attachment=query_data["dl"] == "1",
        download_name=query_data["file"],
        mimetype="video/mp4",
        conditional=True,
    )


@grok_bp.get("/descargar_todas")
@grok_bp.input(GrokVideosQuerySchema, location="query")
def descargar_todas(query_data):
    result = grok_animation_service.build_videos_zip(query_data["project"])
    if not result:
        return jsonify({"error": "Sin videos"}), 404
    buf, zip_name = result
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=zip_name)


@grok_bp.post("/abrir_carpeta")
@grok_bp.input(GrokAbrirCarpetaInSchema)
def abrir_carpeta(json_data):
    grok_animation_service.open_videos_folder(json_data["project"])
    return jsonify({"ok": True})
