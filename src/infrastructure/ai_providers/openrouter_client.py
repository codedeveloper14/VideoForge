import requests

from src.core.config import config
from src.utils.logger import get_logger

logger = get_logger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def sanitize_prompt(original: str) -> str | None:
    """Reescribe un prompt de imagen rechazado por moderacion via OpenRouter,
    manteniendo la intencion original. Devuelve None si no hay API key o falla."""
    text = (original or "").strip()
    if len(text) < 4 or not config.openrouter_api_key:
        return None

    system = (
        "Tu tarea es reescribir el prompt de generación de imagen del usuario para que sea más apto "
        "para la generación y tenga más probabilidades de pasar la censura y las políticas de seguridad "
        "del proveedor, sin dejar de estar relacionado con la intención, el tema y el estilo del prompt original. "
        "Mantén el mismo idioma que el prompt original. Responde únicamente con el prompt reescrito, sin comillas, "
        "sin explicaciones ni títulos."
    )
    try:
        r = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {config.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://studio-ivr.app",
                "X-Title": "Studio IVR Whisk sanitize",
            },
            json={
                "model": config.openrouter_whisk_sanitize_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": "Prompt original:\n" + text},
                ],
                "max_tokens": 700,
                "temperature": 0.32,
            },
            timeout=(12, 48),
        )
        if r.status_code != 200:
            return None
        content = (r.json().get("choices") or [{}])[0].get("message", {}).get("content")
        if not content or not str(content).strip():
            return None
        out = str(content).strip()
        if (out.startswith('"') and out.endswith('"')) or (out.startswith("'") and out.endswith("'")):
            out = out[1:-1].strip()
        return out if out and out != text else None
    except Exception as exc:
        logger.warning("sanitize_prompt error: %s", exc)
        return None
