from apiflask import APIFlask

from src.core.config import config
from src.infrastructure.payments.stripe_service import ensure_stripe_table
from src.infrastructure.jobs.task_tracker import register_task_tracker
from src.infrastructure.storage import docs_repository
from src.infrastructure.storage.usage_repository import ensure_tables
from src.presentation.auth_middleware import register_auth_middleware
from src.presentation.routes.auth import auth_bp
from src.presentation.routes.docs import admin_docs_bp, docs_bp
from src.presentation.routes.editor import editor_bp
from src.presentation.routes.grok import grok_bp
from src.presentation.routes.health import health_bp
from src.presentation.routes.meta import meta_bp
from src.presentation.routes.plans import plans_bp
from src.presentation.routes.projects import projects_bp
from src.presentation.routes.quick_render import quick_render_bp
from src.presentation.routes.qwen import qwen_bp
from src.presentation.routes.render import render_bp
from src.presentation.routes.script import audio_bp, guion_bp
from src.presentation.routes.stripe import stripe_bp, stripe_pages_bp
from src.presentation.routes.usage import usage_bp
from src.presentation.routes.user import user_bp
from src.presentation.routes.voice import voice_bp
from src.presentation.routes.whisk import pollination_bp, whisk_bp


def create_app() -> APIFlask:
    app = APIFlask(__name__, title=f"{config.app_name} API", version="0.1.0")
    app.config["DEBUG"] = config.debug

    ensure_tables()
    ensure_stripe_table()
    docs_repository.ensure_tables()

    register_auth_middleware(app)
    register_task_tracker(app)

    app.register_blueprint(health_bp)
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
    app.register_blueprint(whisk_bp)
    app.register_blueprint(pollination_bp)
    app.register_blueprint(docs_bp)
    app.register_blueprint(admin_docs_bp)
    return app
