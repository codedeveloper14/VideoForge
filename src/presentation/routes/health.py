from apiflask import APIBlueprint

from src.core.config import config
from src.presentation.schemas.health import HealthOutSchema

health_bp = APIBlueprint("health", __name__, url_prefix="/api")


@health_bp.get("/health")
@health_bp.output(HealthOutSchema)
def get_health():
    return {"status": "ok", "app": config.app_name}
