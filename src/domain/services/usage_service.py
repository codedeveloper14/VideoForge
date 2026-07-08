from src.domain.models.plan import PLANS, chars_to_min, normalize_plan_key
from src.infrastructure.storage import usage_repository, user_repository


def get_today_usage(user_id: int) -> dict:
    return usage_repository.get_today_usage(user_id)


def get_month_usage(user_id: int) -> dict:
    return usage_repository.get_month_usage(user_id)


def record_usage(user_id: int, videos: int = 0, tts_chars: int = 0, shorts: int = 0) -> bool:
    videos = max(0, min(videos, 10))
    tts_chars = max(0, min(tts_chars, 500_000))
    return usage_repository.record_usage(user_id, videos=videos, tts_chars=tts_chars, shorts=shorts)


def check_limit(username: str, check_type: str, amount: int = 1) -> tuple[bool, str, dict]:
    """
    Verifica si el usuario puede realizar la accion.
    check_type: 'video' | 'tts' | 'short'
    amount: para 'tts', numero de caracteres; para 'video'/'short', siempre 1.
    Los limites de video, shorts y tts son mensuales.
    """
    user = user_repository.get_user_full(username)
    if not user:
        return False, "Usuario no encontrado", {}

    plan_key = normalize_plan_key(user["plan"])
    plan = PLANS[plan_key]
    usage = get_month_usage(user["id"])

    if check_type == "video":
        limit, used = plan["videos_per_month"], usage["videos"]
        if limit is None:
            return True, "", {"used": used, "limit": None, "remaining": None}
        if used >= limit:
            return False, (
                f"Has alcanzado el límite de {limit} videos/mes de tu plan {plan['name']}. "
                f"Haz upgrade para continuar."
            ), {"used": used, "limit": limit, "remaining": 0, "type": "video", "plan": plan_key}
        return True, "", {"used": used, "limit": limit, "remaining": limit - used}

    if check_type == "short":
        limit, used = plan["shorts_per_month"], usage["shorts"]
        if limit is None:
            return True, "", {"used": used, "limit": None, "remaining": None}
        if used >= limit:
            return False, (
                f"Has alcanzado el límite de {limit} shorts/mes de tu plan {plan['name']}. "
                f"Haz upgrade para continuar."
            ), {"used": used, "limit": limit, "remaining": 0, "type": "short", "plan": plan_key}
        return True, "", {"used": used, "limit": limit, "remaining": limit - used}

    if check_type == "tts":
        limit, used = plan["tts_chars_per_month"], usage["tts_chars"]
        if limit is None:
            return True, "", {"used": used, "limit": None, "remaining": None}
        remaining = max(0, limit - used)
        if used + amount > limit:
            return False, (
                f"Límite de audio alcanzado: {plan['audio_hours_per_month']}h/mes (plan {plan['name']}). "
                f"Disponible: {chars_to_min(remaining)}. Haz upgrade para más."
            ), {"used": used, "limit": limit, "remaining": remaining, "type": "tts", "plan": plan_key}
        return True, "", {"used": used, "limit": limit, "remaining": remaining - amount}

    return True, "", {}


def check_video_duration(username: str, duration_seconds: float) -> tuple[bool, str]:
    user = user_repository.get_user_full(username)
    if not user:
        return False, "Usuario no encontrado"

    plan_key = normalize_plan_key(user["plan"])
    plan = PLANS[plan_key]
    max_min = plan.get("max_video_minutes")

    if max_min is None:
        return True, ""
    if duration_seconds > max_min * 60:
        dur_min = duration_seconds / 60
        return False, (
            f"El audio ({dur_min:.1f} min) supera el límite de {max_min} min/video "
            f"de tu plan {plan['name']}. Haz upgrade para videos más largos."
        )
    return True, ""
