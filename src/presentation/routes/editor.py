import re

from apiflask import APIBlueprint
from flask import jsonify, request, send_file

from src.domain.services import (
    editor_scene_analysis_service,
    editor_visual_service,
    enriched_render_service,
    render_service,
)
from src.infrastructure.ai_providers import image_search_client
from src.infrastructure.storage import project_repository
from src.presentation.schemas.editor import (
    EditorBuscarImagenInSchema,
    EditorCargarPlanQuerySchema,
    EditorProxyImagenInSchema,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

editor_bp = APIBlueprint("editor", __name__, url_prefix="/api/editor")


@editor_bp.post("/analizar")
def analizar():
    """Clasifica cada escena (tipo cinematografico, overlays, queries de imagen) via IA.
    Body libre (no schema estricto): {escenas: [{texto, imagen_file}], project_name}."""
    data = request.get_json(silent=True) or {}
    escenas = data.get("escenas", [])
    project_name = data.get("project_name", "")
    try:
        result = editor_scene_analysis_service.analizar_escenas(escenas, project_name)
        return jsonify({"escenas": result})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("editor_analizar error")
        return jsonify({"error": str(exc)}), 500


@editor_bp.post("/buscar_imagen")
@editor_bp.input(EditorBuscarImagenInSchema)
def buscar_imagen(json_data):
    urls = image_search_client.search_images(
        json_data["query"],
        n=json_data["n"],
        serper_key=json_data["serper_key"],
        pexels_key=json_data["pexels_key"],
    )
    return jsonify({"urls": urls})


@editor_bp.post("/guardar_plan")
def guardar_plan():
    """Persiste el plan de edicion (escenas con metadatos). Body libre: {project_name, escenas}."""
    data = request.get_json(silent=True) or {}
    project_name = (data.get("project_name") or "").strip()
    if not project_name:
        return jsonify({"error": "Falta project_name"}), 400
    path = project_repository.write_editor_plan(project_name, data.get("escenas", []))
    return jsonify({"ok": True, "path": str(path)})


@editor_bp.get("/cargar_plan")
@editor_bp.input(EditorCargarPlanQuerySchema, location="query")
def cargar_plan(query_data):
    project = query_data["project"].strip()
    if not project:
        return jsonify({"existe": False})
    plan = project_repository.read_editor_plan(project)
    if plan is None:
        return jsonify({"existe": False})
    return jsonify({"existe": True, **plan})


@editor_bp.post("/proxy_imagen")
@editor_bp.input(EditorProxyImagenInSchema)
def proxy_imagen(json_data):
    result = image_search_client.proxy_image_b64(json_data["url"])
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@editor_bp.post("/render_enriquecido")
def render_enriquecido():
    """Render con efectos del editor: overlays de texto sincronizados, Ken Burns,
    split-screen, imagenes de referencia. Body libre: {project_name, escenas,
    resolucion, transicion, trans_dur, pexels_key, unsplash_key}. Reutiliza el mismo
    job registry que /api/render_inteligente -- se consulta via /api/estado/<job_id>
    y se descarga via /api/descargar_render/<job_id>."""
    data = request.get_json(silent=True) or {}
    try:
        result = enriched_render_service.start_render(
            project_name=data.get("project_name", ""),
            escenas=data.get("escenas", []),
            resolucion=data.get("resolucion", "1920x1080"),
            transicion=data.get("transicion", "xfade"),
            trans_dur=float(data.get("trans_dur", 0.6)),
            pexels_key=data.get("pexels_key", ""),
            unsplash_key=data.get("unsplash_key", ""),
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("editor_render_enriquecido error")
        return jsonify({"error": str(exc)}), 500


@editor_bp.get("/proyecto/<proj_name>")
def proyecto(proj_name):
    """Datos del proyecto para el editor visual (imagenes, guion, audio, plan, timestamps)."""
    proj_name = re.sub(r"[^\w\-]", "_", proj_name.strip())
    if not proj_name:
        return jsonify({"error": "proyecto requerido"}), 400
    try:
        data = editor_visual_service.get_project_data(proj_name)
    except FileNotFoundError:
        return jsonify({"error": "proyecto no encontrado"}), 404
    resp = jsonify(data)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@editor_bp.get("/imagen/<proj_name>/<filename>")
def imagen(proj_name, filename):
    path = project_repository.resolve_safe_file(proj_name, "imagen", filename)
    if not path or not path.exists():
        return jsonify({"error": "no encontrado"}), 404
    resp = send_file(str(path))
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    return resp


@editor_bp.get("/audio/<proj_name>/<filename>")
def audio(proj_name, filename):
    path = project_repository.resolve_safe_file(proj_name, "audio", filename)
    if not path or not path.exists():
        return jsonify({"error": "no encontrado"}), 404
    resp = send_file(str(path))
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    return resp


@editor_bp.get("/transcribir/<proj_name>")
def transcribir(proj_name):
    """Transcribe (cascada automatica de backends) y asigna timestamps por escena,
    con el mismo algoritmo que el Render normal. Cachea en timestamps_escenas.json."""
    proj_name = re.sub(r"[^\w\-]", "_", proj_name.strip())
    if not proj_name:
        return jsonify({"error": "proyecto requerido"}), 400
    try:
        result = editor_visual_service.transcribe_project(proj_name)
    except FileNotFoundError:
        return jsonify({"error": "proyecto no encontrado"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        logger.exception("editor_transcribir error")
        return jsonify({"error": str(exc)}), 500
    resp = jsonify(result)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@editor_bp.get("/estado/<job_id>")
def estado(job_id):
    """Polling de estado para el editor visual -- mismo job registry que /api/estado."""
    job = render_service.get_job(job_id)
    if job is None:
        return jsonify({"error": "no encontrado"}), 404
    resp = jsonify(job)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp
