from apiflask import APIBlueprint
from flask import jsonify, request, send_file

from src.domain.services import project_service
from src.infrastructure.storage import project_repository
from src.presentation.schemas.projects import (
    CreateProjectInSchema,
    CreateProjectOutSchema,
    ImagenFileQuerySchema,
    ProjectContentOutSchema,
    ProjectNameInSchema,
    ProjectOutSchema,
    ProjectQuerySchema,
    ProjectRefInSchema,
    VideoFileQuerySchema,
    VideoFinalQuerySchema,
    VideosFinalOutSchema,
)

projects_bp = APIBlueprint("projects", __name__, url_prefix="/api/proyectos")

_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


@projects_bp.get("/imagen_file")
@projects_bp.input(ImagenFileQuerySchema, location="query")
def imagen_file(query_data):
    project = project_service.sanitize_name(query_data["project"])
    path = project_repository.resolve_safe_file(project, "imagen", query_data["file"])
    if not path or not path.exists():
        return "", 404
    resp = send_file(str(path), mimetype=_IMAGE_MIME.get(path.suffix.lower(), "image/jpeg"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@projects_bp.get("/video_file")
@projects_bp.input(VideoFileQuerySchema, location="query")
def video_file(query_data):
    """Sirve un clip de jobs/<project>/video/<file> -- el equivalente de imagen_file()
    para la galeria de assets del Paso 5 (Renderizado), que necesita mostrar los
    videos ya generados en el proyecto ademas de las imagenes."""
    project = project_service.sanitize_name(query_data["project"])
    path = project_repository.resolve_safe_file(project, "video", query_data["file"])
    if not path or not path.exists():
        return "", 404
    resp = send_file(str(path), mimetype="video/mp4", conditional=True)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@projects_bp.post("/subir_imagen")
def subir_imagen():
    """Sube manualmente una imagen a jobs/<project>/imagen -- la galeria del Paso 5
    (Renderizado) refresca su contenido despues via /proyectos/contenido."""
    project = request.form.get("project", "")
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "Falta el archivo"}), 400
    try:
        safe_name = project_service.upload_project_image(project, file.filename, file.read())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "file": safe_name})


@projects_bp.post("/subir_video")
def subir_video():
    """Sube manualmente un video (.mp4) a jobs/<project>/video."""
    project = request.form.get("project", "")
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "Falta el archivo"}), 400
    try:
        safe_name = project_service.upload_project_video(project, file.filename, file.read())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "file": safe_name})


@projects_bp.post("/crear")
@projects_bp.input(CreateProjectInSchema)
@projects_bp.output(CreateProjectOutSchema)
def crear(json_data):
    try:
        return project_service.create_project(json_data["nombre"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@projects_bp.get("/listar")
@projects_bp.output(ProjectOutSchema(many=True))
def listar():
    return project_service.list_projects()


@projects_bp.get("/contenido")
@projects_bp.input(ProjectQuerySchema, location="query")
@projects_bp.output(ProjectContentOutSchema)
def contenido(query_data):
    return project_service.get_project_content(query_data["project"])


@projects_bp.post("/borrar")
@projects_bp.input(ProjectNameInSchema)
def borrar(json_data):
    raw_name = json_data.get("nombre") or json_data.get("name") or ""
    ok, message = project_service.delete_project(raw_name)
    if not ok:
        return jsonify({"error": message}), 400
    return jsonify({"ok": True, "nombre": project_service.sanitize_name(raw_name), "msg": message or None})


@projects_bp.get("/videos_final")
@projects_bp.input(ProjectQuerySchema, location="query")
@projects_bp.output(VideosFinalOutSchema)
def videos_final(query_data):
    return {"videos": project_service.list_final_videos(query_data["project"])}


@projects_bp.get("/video_final")
@projects_bp.input(VideoFinalQuerySchema, location="query")
def video_final(query_data):
    path = project_repository.resolve_safe_file(query_data["project"], "video_final", query_data["file"])
    if not path or not path.exists():
        return jsonify({"error": "not found"}), 404
    return send_file(
        str(path),
        as_attachment=query_data["dl"] == "1",
        download_name=query_data["file"],
        mimetype="video/mp4",
        conditional=True,
    )


@projects_bp.post("/abrir_video_final")
@projects_bp.input(ProjectRefInSchema)
def abrir_video_final(json_data):
    try:
        path = project_service.open_final_videos_folder(json_data["project"])
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except OSError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    return jsonify(ok=True, path=str(path))
