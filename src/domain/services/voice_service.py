import base64
import json
import time

from src.domain.services import usage_service
from src.domain.services.project_service import sanitize_name
from src.infrastructure.ai_providers import n8n_client
from src.infrastructure.storage import project_repository, user_repository
from src.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_CHARS = 900
_SKIP_KEYS = {"ID Voz", "Nombre Voz", "row_number", "id", "voice_id"}


def _normalize_voices(data):
    out = None
    if isinstance(data, list):
        out = data
        if out and isinstance(out[0], dict) and not out[0].get("voice_id") and not out[0].get("ID Voz"):
            for key in ("data", "voces", "voices", "items", "results", "rows", "list"):
                v = out[0].get(key)
                if isinstance(v, list):
                    out = v
                    break
    elif isinstance(data, dict):
        for key in ("data", "voces", "voices", "items", "results", "rows", "list"):
            v = data.get(key)
            if isinstance(v, list):
                out = v
                break
    if out is None:
        return None

    normed = []
    for item in out:
        if not isinstance(item, dict):
            continue
        item = dict(item)
        if "ID Voz" not in item:
            vid = item.get("voice_id") or item.get("id") or ""
            if vid:
                item["ID Voz"] = vid
        if item.get("ID Voz") and "Nombre Voz" not in item:
            vname = item.get("name") or item.get("voice_name") or ""
            if not vname:
                for k, v in item.items():
                    if k not in _SKIP_KEYS and isinstance(v, str) and v.strip():
                        vname = v.strip()
                        break
            item["Nombre Voz"] = vname or item["ID Voz"]
        if item.get("ID Voz"):
            normed.append(item)
    return normed


def get_voices() -> tuple[str, int]:
    """Devuelve (body_json_str, status_code)."""
    try:
        r = n8n_client.n8n_request("GET", n8n_client.VOCES_URL, timeout=20, attempts=3)
    except Exception as exc:
        return json.dumps({"error": str(exc)}), 500

    if r.status_code >= 400:
        return r.text, r.status_code
    try:
        data = r.json()
    except Exception:
        return r.text, r.status_code

    out = _normalize_voices(data)
    if out is not None:
        return json.dumps(out, ensure_ascii=False), 200
    return r.text, r.status_code


def _sanitize_tts_text(text: str) -> str:
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    text = text.replace('"', "'").replace("\\", " ")
    return " ".join(text.split()).strip()


def _split_text(text: str, max_chars: int) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        end_pos = start + max_chars
        if end_pos >= len(text):
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
            break
        cut = -1
        for i in range(end_pos, start + max_chars // 2, -1):
            if text[i] in ".!?":
                cut = i + 1
                break
        if cut == -1:
            for i in range(end_pos, start + max_chars // 2, -1):
                if text[i] == " ":
                    cut = i
                    break
        if cut == -1:
            cut = end_pos
        chunk = text[start:cut].strip()
        if chunk:
            chunks.append(chunk)
        start = cut
    return chunks


def generate_voice(username: str | None, voice_id: str, text: str) -> dict:
    """Genera audio TTS via n8n en fragmentos. Devuelve un dict listo para jsonify.

    Incluye {status_code: int} para que la ruta sepa que codigo HTTP usar.
    """
    if username:
        char_count = len(text)
        allowed, message, extra = usage_service.check_limit(username, "tts", char_count)
        if not allowed:
            return {
                "error": message, "limit_reached": True, "limit_type": "tts",
                "extra": extra, "status_code": 429,
            }
    else:
        char_count = 0

    clean = _sanitize_tts_text(text)
    chunks = _split_text(clean, _MAX_CHARS) if len(clean) > _MAX_CHARS else [clean]

    all_fragments = []
    for chunk in chunks:
        try:
            r = n8n_client.n8n_request(
                "POST", n8n_client.GENERAR_URL,
                json_payload={"data": chunk, "voice_id": voice_id},
                timeout=300, attempts=3,
            )
            result = r.json()
            res = result[0] if isinstance(result, list) else result
            if isinstance(res, dict) and res.get("fragments"):
                for frag in res["fragments"]:
                    frag["chunkText"] = chunk
                    all_fragments.append(frag)
            else:
                err = res.get("message", str(res)[:120]) if isinstance(res, dict) else str(res)[:120]
                return {"error": f"n8n error: {err}", "status_code": 500}
        except Exception as exc:
            return {"error": str(exc), "status_code": 500}

    if not all_fragments:
        return {"error": "No se generaron fragmentos", "status_code": 500}

    if username:
        try:
            user = user_repository.get_user_full(username)
            if user:
                usage_service.record_usage(user["id"], tts_chars=char_count)
        except Exception as exc:
            logger.warning("No se pudo registrar uso de TTS: %s", exc)

    return {"fragments": all_fragments, "status_code": 200}


def merge_audio(project_name: str, payload: dict) -> tuple[str, int]:
    """Fusiona fragmentos de audio via n8n y guarda el resultado en el proyecto. Devuelve (body, status)."""
    try:
        r = n8n_client.n8n_request(
            "POST", n8n_client.FUSIONAR_URL, json_payload=payload, timeout=360, attempts=5,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}), 500

    if r.status_code >= 400:
        return json.dumps({"error": f"n8n merge-audio respondio {r.status_code}: {r.text[:300]}"}), 502
    try:
        result = r.json()
    except Exception:
        return json.dumps({"error": f"Respuesta invalida de merge-audio: {r.text[:200]}"}), 502

    raw = result[0] if isinstance(result, list) else result
    if project_name and isinstance(raw, dict) and raw.get("finalAudio"):
        name = sanitize_name(project_name)
        audio_str = raw["finalAudio"]
        if audio_str.startswith("data:"):
            try:
                _, b64 = audio_str.split(",", 1)
                filename = f"voz_completa_{int(time.time())}.wav"
                project_repository.write_audio_file(name, filename, base64.b64decode(b64))
            except Exception as exc:
                logger.warning("No se pudo guardar audio fusionado: %s", exc)

    return r.text, r.status_code


def clone_voice(payload: dict) -> tuple[str, int]:
    try:
        r = n8n_client.n8n_request("POST", n8n_client.CLONAR_URL, json_payload=payload, timeout=120, attempts=3)
        return r.text, r.status_code
    except Exception as exc:
        return json.dumps({"error": str(exc)}), 500
