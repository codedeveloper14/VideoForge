import threading

from apiflask import APIFlask
from flask import jsonify, request

from src.core.config import config
from src.domain.services import flow_animation_service, gentube_animation_service
from src.infrastructure.ai_providers import flow_bridge
from src.infrastructure.jobs.task_tracker import register_task_tracker
from src.infrastructure.payments.stripe_service import ensure_stripe_table
from src.infrastructure.storage import docs_repository
from src.infrastructure.storage.usage_repository import ensure_tables
from src.presentation.auth_middleware import register_auth_middleware
from src.presentation.routes.auth import auth_bp
from src.presentation.routes.docs import admin_docs_bp, docs_bp
from src.presentation.routes.editor import editor_bp
from src.presentation.routes.flow import flow_bp
from src.presentation.routes.frontend import frontend_bp
from src.presentation.routes.gentube import gentube_bp
from src.presentation.routes.grok import grok_bp
from src.presentation.routes.health import health_bp
from src.presentation.routes.idea2video import idea2video_bp
from src.presentation.routes.meta import meta_bp
from src.presentation.routes.plans import plans_bp
from src.presentation.routes.projects import projects_bp
from src.presentation.routes.quick_render import quick_render_bp
from src.presentation.routes.qwen import qwen_bp
from src.presentation.routes.render import render_bp
from src.presentation.routes.script import audio_bp, guion_bp
from src.presentation.routes.stripe import stripe_bp, stripe_pages_bp
from src.presentation.routes.updates import updates_bp
from src.presentation.routes.usage import usage_bp
from src.presentation.routes.user import user_bp
from src.presentation.routes.voice import voice_bp

_DOCS_PATHS = ("/docs", "/openapi.json", "/redoc")


def _register_docs_port_gate(app: APIFlask) -> None:
    """El mismo `app` se sirve en dos puertos (ver `main.py`): flask_port (8080,
    para la API real + el futuro frontend estatico) y docs_port (8081, dedicado
    a Swagger/OpenAPI). Sin este gate, /docs tambien respondería en el puerto
    8080 -- se oculta ahi para que ese puerto quede "limpio" para el frontend,
    y el testeo de la API con Swagger siempre viva en 8081."""

    @app.before_request
    def _gate_docs():
        if request.path.startswith(_DOCS_PATHS) and f":{config.docs_port}" not in request.host:
            return jsonify({"error": "not found"}), 404
        return None


def _ensure_db_schema() -> None:
    """CREATE TABLE/ALTER TABLE contra el MySQL remoto (Contabo) -- idempotente,
    solo hace falta una vez por cambio de schema, no en cada arranque de cada
    usuario. Corre en un hilo de fondo para no bloquear app.run(): las tablas ya
    existen en produccion, asi que ninguna ruta depende de que esto termine antes
    de poder atender requests."""
    ensure_tables()
    ensure_stripe_table()
    docs_repository.ensure_tables()


def create_app() -> APIFlask:
    app = APIFlask(__name__, title=f"{config.app_name} API", version="0.1.0")
    app.config["DEBUG"] = config.debug

    threading.Thread(target=_ensure_db_schema, daemon=True, name="VF-DB-Schema").start()

    _register_docs_port_gate(app)
    register_auth_middleware(app)
    register_task_tracker(app)

    app.register_blueprint(health_bp)
    app.register_blueprint(updates_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(plans_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(editor_bp)
    app.register_blueprint(grok_bp)
    app.register_blueprint(qwen_bp)
    app.register_blueprint(render_bp)
    app.register_blueprint(quick_render_bp)
    app.register_blueprint(meta_bp)
    app.register_blueprint(guion_bp)
    app.register_blueprint(audio_bp)
    app.register_blueprint(stripe_bp)
    app.register_blueprint(stripe_pages_bp)
    app.register_blueprint(usage_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(docs_bp)
    app.register_blueprint(admin_docs_bp)
    app.register_blueprint(gentube_bp)
    app.register_blueprint(flow_bp)
    app.register_blueprint(idea2video_bp)
    app.register_blueprint(frontend_bp)

    gentube_animation_service.sync_profiles_async()
    flow_bridge.start_ws_server(flow_animation_service.log)
    # Antes solo se arrancaba el WS (5557) aqui -- el bridge HTTP (5556, el canal
    # que background.js SIEMPRE usa para reportar resultados via sendResultHttp(),
    # incluso cuando el WS esta activo) recien arrancaba de forma perezosa dentro
    # de _run_batch/_bridge_generate, la primera vez que el usuario le daba a
    # generar. En ese intervalo, pollBridge()/sendResultHttp() de la extension
    # (activos desde que Chrome carga, no desde que se genera) pegaban contra un
    # puerto cerrado. Arrancarlo aqui, simetrico al WS, lo deja listo desde el
    # boot igual que 5557.
    flow_bridge.start_bridge(flow_animation_service.log)
    return app
