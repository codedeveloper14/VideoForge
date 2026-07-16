from apiflask import APIBlueprint
from flask import jsonify, send_file

from src.domain.services import vibes_animation_service
from src.presentation.schemas.vibes import (
    VibesAbrirCarpetaInSchema,
    VibesAccountInSchema,
    VibesIniciarInSchema,
    VibesLogQuerySchema,
    VibesVideoQuerySchema,
    VibesVideosQuerySchema,
)

vibes_bp = APIBlueprint("vibes", __name__, url_prefix="/api/vibes")


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
@vibes_bp.input(VibesIniciarInSchema)
def iniciar(json_data):
    video_params = {
        "aspect_ratio": json_data["aspect_ratio"],
        "resolution": json_data["resolution"],
        "prompt_model": json_data["prompt_model"],
        "image_model": json_data["image_model"],
        "video_model": json_data["video_model"],
        "batch_variation": json_data["batch_variation"],
    }
    try:
        result = vibes_animation_service.start_batch(
            json_data["project_name"],
            json_data["prompt"],
            json_data["slots"],
            video_params,
            json_data["timeout"],
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@vibes_bp.post("/detener")
def detener():
    vibes_animation_service.stop()
    return jsonify({"ok": True})


@vibes_bp.get("/log")
@vibes_bp.input(VibesLogQuerySchema, location="query")
def log(query_data):
    return jsonify(vibes_animation_service.get_log_state(query_data["offset"]))


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
