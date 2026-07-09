import base64
import json
import os
import re

import requests

from src.core.config import config
from src.utils.logger import get_logger

logger = get_logger(__name__)

_IMAGE_ANALYZE_PROMPT = """Eres un experto en análisis visual de personajes de animación. Analiza la imagen con máxima precisión.

## PASO 0: DETECTAR TIPO DE PERSONAJE
Primero determina: ¿es un ANIMAL o un HUMANO?
- Si es un ANIMAL: describe especie, colores, rasgos físicos del animal. El campo "ancla_prompt" DEBE empezar con el nombre del animal (ej: "gato tuxedo negro blanco ojos verdes estilo cartoon").
- Si es un HUMANO: sigue las instrucciones de abajo.

## PARA ANIMALES
- Especie exacta
- Colores del pelaje/cuerpo
- Rasgos faciales: color de ojos, forma
- Estilo de ilustración

## PARA HUMANOS
- Color exacto de cara/piel: si es blanca sin tono humano --> "cara blanca sin color de piel"
- Forma EXACTA de cabeza: círculo, elipse vertical, elipse horizontal. NO uses "ovalada" si es circular.
- Si cabeza grande respecto al cuerpo --> "cabeza grande en proporción al cuerpo" (NO usar "chibi")
- Ojos, cabello, vestimenta con colores exactos

## ESTILO
- Tipo de ilustración y trazo

## FORMATO — JSON válido únicamente:

{
  "tipo_personaje": "animal o humano",
  "personaje": {
    "especie_o_tipo": "",
    "color_cara_piel": "",
    "forma_cabeza": "",
    "proporciones": "",
    "rasgos_faciales": "",
    "cabello_o_pelaje": "",
    "vestimenta": "",
    "paleta_colores": ""
  },
  "estilo_animacion": {"tipo": "", "trazo": "", "sombreado": ""},
  "ancla_prompt": "",
  "descripcion_completa": ""
}

"ancla_prompt": 8-12 palabras con rasgos MÁS DISTINTIVOS.
- Siempre empieza con "personaje" (nunca "personaje chibi", nunca "chibi")
- Si es animal: empezar con el animal. Ej: "gato tuxedo negro blanco ojos verdes estilo cartoon 2D"
- Si es humano con cara blanca: escribir "cara blanca sin color de piel". Ej: "personaje cara blanca sin color de piel pelo negro uniforme gris"
"descripcion_completa": párrafo completo para contexto de estilo."""


def resolve_openai_api_key() -> str | None:
    return config.openai_api_key or config.openai_whisper_key


def parse_vision_output(txt: str) -> str:
    """Extrae descripcion_completa del texto/JSON devuelto por OpenAI."""
    txt = str(txt or "").strip()
    if not txt:
        return ""
    parsed = None
    try:
        parsed = json.loads(txt)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", txt)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                parsed = None
    if isinstance(parsed, dict):
        return str(parsed.get("descripcion_completa") or "").strip()
    return txt


def analyze_image_b64(b64: str, mime: str) -> dict:
    """Analiza imagen (OpenAI Vision). Devuelve:
    ok True  -> {"ok": True, "descripcion_completa": str, "ancla_prompt": str, "json": dict|None}
    ok False -> {"ok": False, "error": str, "status": int, ...}
    """
    b64 = re.sub(r"[\s\r\n]+", "", (b64 or "").strip())
    mime = (mime or "image/png").strip() or "image/png"
    if not b64:
        return {"ok": False, "error": "Falta image_base64", "status": 400}
    raw = None
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        try:
            raw = base64.b64decode(b64, validate=False)
        except Exception:
            return {"ok": False, "error": "image_base64 inválido", "status": 400}
    if not raw:
        return {"ok": False, "error": "Imagen vacía", "status": 400}
    if len(raw) > 20 * 1024 * 1024:
        return {"ok": False, "error": "Imagen demasiado grande (máx 20MB)", "status": 400}

    api_key = resolve_openai_api_key()
    if not api_key:
        return {
            "ok": False,
            "error": "Sin clave OpenAI: OPENAI_API_KEY_INLINE u OPENAI_WHISPER_KEY.",
            "status": 503,
            "code": "missing_openai_key",
        }

    data_url = f"data:{mime};base64,{b64}"
    img_detail = (os.environ.get("OPENAI_IMAGE_DETAIL") or "low").strip().lower()
    if img_detail not in ("low", "high", "auto"):
        img_detail = "low"
    try:
        max_tokens = int((os.environ.get("OPENAI_IMAGE_MAX_TOKENS") or "1400").strip())
    except ValueError:
        max_tokens = 1400
    max_tokens = max(400, min(2200, max_tokens))
    try:
        temperature = float((os.environ.get("OPENAI_IMAGE_TEMPERATURE") or "0.15").strip())
    except ValueError:
        temperature = 0.15

    payload = {
        "model": (os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-4o-mini").strip(),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _IMAGE_ANALYZE_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": img_detail}},
                ],
            }
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=(15, min(120, 45 + len(raw) // 200000)),
        )
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "error": f"OpenAI red: {exc}", "status": 502}

    if r.status_code != 200:
        try:
            err = r.json()
        except Exception:
            err = {"raw": r.text[:400]}
        return {
            "ok": False,
            "error": "OpenAI HTTP error",
            "status": 502,
            "detail": err,
            "http_status": r.status_code,
        }

    try:
        d = r.json()
        txt = str((d.get("choices") or [{}])[0].get("message", {}).get("content", "") or "").strip()
    except Exception:
        txt = ""
    if not txt:
        return {"ok": False, "error": "OpenAI sin contenido", "status": 502}

    parsed = None
    try:
        parsed = json.loads(txt)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", txt)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                parsed = None

    desc = parse_vision_output(txt)
    if isinstance(parsed, dict):
        desc2 = str(parsed.get("descripcion_completa") or "").strip()
        if desc2:
            desc = desc2
        ancla = str(parsed.get("ancla_prompt") or "").strip()
        return {"ok": True, "descripcion_completa": desc, "ancla_prompt": ancla, "json": parsed}
    return {"ok": True, "descripcion_completa": desc, "ancla_prompt": "", "json": None}
