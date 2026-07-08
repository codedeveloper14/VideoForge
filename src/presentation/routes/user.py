from apiflask import APIBlueprint
from flask import jsonify

from src.domain.models.plan import PLANS, normalize_plan_key
from src.domain.services import usage_service
from src.infrastructure.payments.stripe_service import get_payment_history
from src.infrastructure.storage import user_repository
from src.presentation.auth_middleware import get_current_user
from src.presentation.schemas.user import PaymentOutSchema, UserProfileOutSchema

user_bp = APIBlueprint("user", __name__, url_prefix="/api/user")


@user_bp.get("/profile")
@user_bp.output(UserProfileOutSchema)
def profile():
    username = get_current_user()
    if not username:
        return jsonify({"error": "No autenticado"}), 401
    user = user_repository.get_user_full(username)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    usage = usage_service.get_month_usage(user["id"])
    plan_key = normalize_plan_key(user["plan"])
    plan = PLANS[plan_key]

    sub_date = user.get("subscription_date")
    if sub_date and hasattr(sub_date, "strftime"):
        sub_date = sub_date.strftime("%Y-%m-%d")

    return {
        "username": user["username"],
        "email": user["email"],
        "plan": plan_key,
        "plan_name": plan["name"],
        "subscription_date": sub_date,
        "usage": {
            "videos": usage["videos"],
            "tts_chars": usage["tts_chars"],
            "shorts": usage["shorts"],
        },
        "limits": {
            "videos_per_month": plan["videos_per_month"],
            "tts_chars_per_month": plan["tts_chars_per_month"],
            "audio_hours_per_month": plan["audio_hours_per_month"],
            "shorts_per_month": plan["shorts_per_month"],
            "max_video_minutes": plan["max_video_minutes"],
            "videos_per_day": plan.get("videos_per_day"),
            "tts_chars_per_day": plan["tts_chars_per_day"],
        },
        "payment": {
            "activated_at": str(user.get("created_at", "")),
            "expires_at": str(user.get("plan_expires_at", "") or ""),
        },
    }


@user_bp.get("/payments")
@user_bp.output(PaymentOutSchema(many=True))
def payments():
    username = get_current_user()
    if not username:
        return jsonify({"error": "No autenticado"}), 401
    return get_payment_history(username)
