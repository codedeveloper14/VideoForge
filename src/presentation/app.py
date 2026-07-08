from apiflask import APIFlask

from src.core.config import config
from src.presentation.routes.health import health_bp


def create_app() -> APIFlask:
    app = APIFlask(__name__, title=f"{config.app_name} API", version="0.1.0")
    app.config["DEBUG"] = config.debug
    app.register_blueprint(health_bp)
    return app
