from apiflask import APIFlask

from src.core.config import config
from src.infrastructure.payments.stripe_service import ensure_stripe_table
from src.infrastructure.storage.usage_repository import ensure_tables
from src.presentation.auth_middleware import register_auth_middleware
from src.presentation.routes.auth import auth_bp
from src.presentation.routes.health import health_bp
from src.presentation.routes.plans import plans_bp
from src.presentation.routes.stripe import stripe_bp, stripe_pages_bp
from src.presentation.routes.usage import usage_bp
from src.presentation.routes.user import user_bp


def create_app() -> APIFlask:
    app = APIFlask(__name__, title=f"{config.app_name} API", version="0.1.0")
    app.config["DEBUG"] = config.debug

    ensure_tables()
    ensure_stripe_table()

    register_auth_middleware(app)

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(plans_bp)
    app.register_blueprint(stripe_bp)
    app.register_blueprint(stripe_pages_bp)
    app.register_blueprint(usage_bp)
    return app
