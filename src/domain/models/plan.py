# Limites diarios/mensuales por plan.
# tts_chars_per_month: ~900 chars/min de audio TTS.
# max_video_minutes: None = ilimitado.
PLANS = {
    "free": {
        "name": "Free", "emoji": "🆓",
        "videos_per_month": 3, "shorts_per_month": 0,
        "audio_hours_per_month": 0,
        "tts_chars_per_month": 18_000,
        "tts_chars_per_day": 3_000,
        "max_video_minutes": None, "price_usd": 0,
        "color": "#64748b", "highlight": False,
    },
    "basico": {
        "name": "Básico", "emoji": "🌱",
        "videos_per_month": 45, "shorts_per_month": 15,
        "audio_hours_per_month": 30,
        "tts_chars_per_month": 1_620_000,
        "tts_chars_per_day": 54_000,
        "max_video_minutes": None, "price_usd": 75,
        "color": "#22d3a0", "highlight": False,
    },
    "pro": {
        "name": "Pro", "emoji": "⚡",
        "videos_per_month": 60, "shorts_per_month": 25,
        "audio_hours_per_month": 45,
        "tts_chars_per_month": 2_430_000,
        "tts_chars_per_day": 81_000,
        "max_video_minutes": None, "price_usd": 105,
        "color": "#7c6aff", "highlight": True,
    },
    "ultra": {
        "name": "Ultra", "emoji": "🔥",
        "videos_per_month": 75, "shorts_per_month": 35,
        "audio_hours_per_month": 60,
        "tts_chars_per_month": 3_240_000,
        "tts_chars_per_day": 108_000,
        "max_video_minutes": None, "price_usd": 145,
        "color": "#fbbf24", "highlight": False,
    },
    "unlimited": {
        "name": "Ilimitado", "emoji": "♾️",
        "videos_per_month": None, "shorts_per_month": None,
        "audio_hours_per_month": None,
        "tts_chars_per_month": None,
        "tts_chars_per_day": None,
        "max_video_minutes": None, "price_usd": 350,
        "color": "#c084fc", "highlight": False,
    },
}

# Alias de nombres de plan alternativos en la BD --> clave canonica.
PLAN_ALIASES = {
    "starter": "basico",
    "basic": "basico",
    "basico": "basico",
    "free": "free",
    "standard": "pro",
    "premium": "pro",
    "advanced": "pro",
    "enterprise": "unlimited",
    "business": "ultra",
    "ilimitado": "unlimited",
    "unlimited": "unlimited",
}


def normalize_plan_key(raw: str) -> str:
    """Convierte cualquier nombre de plan de la BD al key canonico (basico/pro/ultra/unlimited)."""
    key = str(raw or "basico").lower().strip()
    key = PLAN_ALIASES.get(key, key)
    return key if key in PLANS else "basico"


def chars_to_min(chars: int) -> str:
    """Convierte caracteres TTS a un string legible de minutos/segundos."""
    minutes = chars / 900
    if minutes < 1:
        return f"{int(minutes * 60)}s"
    return f"{minutes:.0f} min"
