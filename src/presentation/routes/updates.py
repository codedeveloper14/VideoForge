from apiflask import APIBlueprint

from src.infrastructure.update_check import check_for_update
from src.presentation.schemas.updates import UpdateCheckOutSchema

updates_bp = APIBlueprint("updates", __name__, url_prefix="/api")


@updates_bp.get("/updates/check")
@updates_bp.output(UpdateCheckOutSchema)
def get_update_check():
    status = check_for_update()
    return {
        "current_version": status.current_version,
        "latest_version": status.latest_version,
        "update_available": status.update_available,
        "release_url": status.release_url,
    }
