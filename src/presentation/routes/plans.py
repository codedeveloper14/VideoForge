from apiflask import APIBlueprint

from src.domain.models.plan import PLANS
from src.presentation.schemas.plans import PlanOutSchema

plans_bp = APIBlueprint("plans", __name__, url_prefix="/api")


@plans_bp.get("/plans")
@plans_bp.output(PlanOutSchema(many=True))
def list_plans():
    """Lista todos los planes disponibles (sin info sensible)."""
    out = []
    for key, plan in PLANS.items():
        tts_day = plan.get("tts_chars_per_day")
        out.append({
            "id": key,
            "name": plan["name"],
            "emoji": plan["emoji"],
            "price_usd": plan["price_usd"],
            "videos_per_day": plan.get("videos_per_day"),
            "videos_per_month": plan.get("videos_per_month"),
            "audio_hours_per_month": plan.get("audio_hours_per_month"),
            "shorts_per_month": plan.get("shorts_per_month"),
            "tts_mins_per_day": (tts_day // 900) if tts_day else None,
            "max_video_minutes": plan["max_video_minutes"],
            "highlight": plan.get("highlight", False),
        })
    return out
