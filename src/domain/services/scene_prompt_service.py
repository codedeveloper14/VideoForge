import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from src.core.config import config
from src.domain.services import scene_prompt_templates as tpl
from src.infrastructure.ai_providers.whisk_client import mk_https_session
from src.utils.logger import get_logger

logger = get_logger(__name__)

_BAD_SUFFIX_PAT = re.compile(
    r",?\s+(depicted in|illustrated with|framed within|set against|shown as"
    r"|captured in|presented as|portrayed in|rendered in|displayed in"
    r"|visualized (as|with)|drawn in|created in)\b.*$",
    re.IGNORECASE,
)
_NON_PROMPT_PAT = re.compile(
    r"^(here (are|is)|the following|below (are|is)|visual prompts?|prompts?:|scenes?:)",
    re.IGNORECASE,
)


def segment_script(guion_text: str) -> tuple[list[dict], list[str]]:
    """Fragmentacion semantica: acumula clausulas por puntuacion hasta un minimo
    de palabras por escena. Devuelve (bloques, fragmentos_fuente)."""
    scene_min_words = max(8, int(os.environ.get("GUION_MIN_WORDS_PER_SCENE", "12")))
    tiny_tail_words = max(4, int(os.environ.get("GUION_TINY_TAIL_WORDS", "6")))

    clean_text = re.sub(r"\s+", " ", (guion_text or "").replace("\r", " ").replace("\n", " ")).strip()
    clauses = re.findall(r"[^.?!,;:]+[.?!,;:]*", clean_text)
    fragmentos = [c.strip() for c in clauses if c and c.strip()]

    chunks = []
    chunk: list[str] = []
    words = 0
    for cl in fragmentos:
        w = len(cl.split())
        if w <= 0:
            continue
        chunk.append(cl)
        words += w
        if words >= scene_min_words:
            chunks.append(" ".join(chunk).strip())
            chunk = []
            words = 0
    if chunk:
        tail = " ".join(chunk).strip()
        if chunks and words < tiny_tail_words:
            chunks[-1] = (chunks[-1] + " " + tail).strip()
        else:
            chunks.append(tail)

    bloques = []
    for bloque_id, t in enumerate(chunks, 1):
        palabras = len(t.split())
        bloques.append({
            "bloque_global_id": bloque_id, "fragmento_id": bloque_id, "bloque_id": 1,
            "texto_original": t, "palabras": palabras,
            "segundos_estimados": max(2, round(palabras / 2.5)),
            "prompt_imagen": None, "palabras_clave": [],
        })
    return bloques, fragmentos


def _clean_prompt(txt: str) -> str:
    txt = txt.strip()
    txt = _BAD_SUFFIX_PAT.sub("", txt).strip().rstrip(",").strip()
    if _NON_PROMPT_PAT.match(txt):
        return ""
    word_count = len(txt.split())
    if word_count < 4 or word_count > 90:
        return ""
    return txt


def _parse_batch_output(raw: str, batch: list[dict]) -> dict[int, str]:
    """Quita 'N. ' por linea; prioriza numeros que coincidan con bloque_global_id."""
    expected_ids = [b["bloque_global_id"] for b in batch]
    lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    by_id: dict[int, str] = {}
    for ln in lines:
        m = re.match(r"^(\d+)\.\s+(.*)$", ln)
        if m:
            num = int(m.group(1))
            txt = _clean_prompt(m.group(2))
            if num in expected_ids and txt:
                by_id[num] = txt
    cleaned = []
    for ln in lines:
        t = re.sub(r"^\d+\.\s+", "", ln).strip()
        t = _clean_prompt(t)
        if t:
            cleaned.append(t)
    for j, gid in enumerate(expected_ids):
        if by_id.get(gid):
            continue
        if j < len(cleaned):
            by_id[gid] = cleaned[j]
    return by_id


def _escenas_texto(batch: list[dict]) -> str:
    return "\n".join(
        f"{b['bloque_global_id']}. {(b.get('texto_original') or '').strip().replace(chr(10), ' ')}"
        for b in batch
    )


_or_local = threading.local()


def _or_session(pool_size: int) -> requests.Session:
    s = getattr(_or_local, "s", None)
    if s is None:
        try:
            s = mk_https_session(max(4, int(pool_size)))
        except Exception:
            s = requests.Session()
        _or_local.s = s
    return s


def _select_system_prompt(prompt_mode: str, prompt_style: str) -> str:
    if prompt_mode == "stick":
        return tpl.SYS_STICK_HISTORY_AGENT if prompt_style == "history" else tpl.SYS_STICK_AGENT
    if prompt_mode == "ultrarealismo":
        return tpl.SYS_ULTRAREALISMO_AGENT
    return tpl.SYS_N8N_AGENT


def _openrouter_models() -> list[str]:
    env_model = (os.environ.get("OPENROUTER_MODEL") or "").strip()
    models = [env_model] if env_model else []
    for m in ("openai/gpt-4o-mini", "anthropic/claude-3.5-haiku-20241022",
              "anthropic/claude-3.5-haiku", "anthropic/claude-sonnet-4.6"):
        if m not in models:
            models.append(m)
    return models


def _gen_batch(batch: list[dict], guion_text: str, estilo_efectivo: str,
               prompt_mode: str, active_sys: str, or_models: list[str], temperature: float) -> dict[int, str]:
    if not batch:
        return {}
    if prompt_mode == "stick":
        scene_txt = " ".join(b.get("texto_original", "").strip() for b in batch)
        user_msg = f"Guión completo del video (contexto):\n{guion_text}\n\nEscena actual: {scene_txt}"
        max_tokens = 700
    else:
        user_msg = (f"Descripción de imagen de referencia (estilo): {estilo_efectivo}\n"
                    f"Escenas a generar: {_escenas_texto(batch)}")
        n_scenes = len(batch)
        try:
            tps = int((os.environ.get("OPENROUTER_MAX_TOKENS_PER_SCENE") or "68").strip())
        except ValueError:
            tps = 68
        tps = max(52, min(110, tps))
        max_tokens = min(8000, max(448, n_scenes * tps))

    n_scenes = len(batch)
    last_net = None
    for attempt in range(2):
        try:
            hit_rate_limit = False
            saw_400 = False
            for model in or_models:
                r = _or_session(4).post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {config.openrouter_api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://studio-ivr.app",
                        "X-Title": "Studio IVR",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "system", "content": active_sys},
                                     {"role": "user", "content": user_msg}],
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                    timeout=(12, min(180, 28 + n_scenes * 4)),
                )
                try:
                    d = r.json()
                except Exception:
                    logger.warning("[prompt-batch] HTTP %s %s (sin JSON)", r.status_code, model)
                    if r.status_code in (429, 502, 503, 504):
                        hit_rate_limit = True
                        break
                    continue
                if r.status_code == 200:
                    try:
                        content = str((d.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()
                    except Exception:
                        content = ""
                    if content:
                        if prompt_mode == "stick":
                            return {batch[0]["bloque_global_id"]: content.strip()}
                        return _parse_batch_output(content, batch)
                    continue
                logger.warning("[prompt-batch] HTTP %s %s %s", r.status_code, model, str(d)[:100])
                if r.status_code == 401:
                    return {}
                if r.status_code in (429, 502, 503, 504):
                    hit_rate_limit = True
                    break
                if r.status_code == 400:
                    saw_400 = True
                    continue
                if r.status_code == 404:
                    continue
                return {}
            if hit_rate_limit:
                time.sleep(min(4.0, 0.35 * (2 ** attempt)) + random.random() * 0.12)
                continue
            if saw_400:
                time.sleep(min(2.0, 0.25 * (2 ** attempt)) + random.random() * 0.08)
                continue
            return {}
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError,
                requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError) as exc:
            last_net = exc
            time.sleep(min(3.5, 0.28 * (2 ** attempt)) + random.random() * 0.1)
        except Exception as exc:
            logger.warning("[prompt-batch] Error: %s", exc)
            return {}
    if last_net:
        logger.warning("[prompt-batch] Error: %s", last_net)
    return {}


def _gen_batch_safe(batch, guion_text, estilo_efectivo, prompt_mode, active_sys, or_models, temperature) -> dict:
    """Si OpenRouter devuelve menos lineas de las esperadas, subdivide el lote
    hasta completar o agotar sublotes."""
    if not batch:
        return {}
    mapping = _gen_batch(batch, guion_text, estilo_efectivo, prompt_mode, active_sys, or_models, temperature)
    if len(mapping) >= len(batch) or len(batch) <= 1:
        return mapping
    missing_ratio = 1.0 - (len(mapping) / max(1, len(batch)))
    if missing_ratio <= 0.08:
        return mapping
    mid = max(1, len(batch) // 2)
    left, right = batch[:mid], batch[mid:]
    if not right:
        return mapping
    merged = {}
    merged.update(_gen_batch_safe(left, guion_text, estilo_efectivo, prompt_mode, active_sys, or_models, temperature))
    merged.update(_gen_batch_safe(right, guion_text, estilo_efectivo, prompt_mode, active_sys, or_models, temperature))
    merged.update(mapping)
    return merged


def _fallback_fill(bloques: list[dict], prompt_mode: str, estilo_efectivo: str) -> None:
    missing = [b for b in bloques if not (b.get("prompt_imagen") or "").strip()]
    if not missing:
        return
    if prompt_mode == "stick":
        for b in missing:
            b["prompt_imagen"] = (b.get("texto_original") or "").strip().replace("\n", " ")
        return
    estilo_tail = (estilo_efectivo or "").strip()
    if len(estilo_tail) > 220:
        estilo_tail = estilo_tail[:220].rstrip(" ,.;") + "."
    for b in missing:
        base = (b.get("texto_original") or "").strip().replace("\n", " ")
        if len(base) > 180:
            base = base[:180].rstrip(" ,.;") + "."
        b["prompt_imagen"] = (
            f"Literal visual representation of: {base}. Main subject and action must match the scene text, "
            f"with coherent composition and consistent style. {estilo_tail}"
        ).strip()


def generate_prompts(guion_text: str, output_mode: str, prompt_mode: str, prompt_style: str,
                      estilo_ref: str) -> dict:
    """Segmenta el guion en escenas y genera un prompt de imagen por escena via OpenRouter.
    Reproduce el mismo systemMessage/plantilla que el flujo n8n original."""
    if not guion_text.strip():
        raise ValueError("Guion vacio")

    estilo_fuente = "texto" if estilo_ref else "default"
    estilo_efectivo = estilo_ref if estilo_ref else tpl.DEFAULT_ESTILO

    bloques, fragmentos = segment_script(guion_text)

    if output_mode == "solo_saltos":
        return {
            "metadata": {"total_escenas": len(bloques), "total_prompts": 0, "total_fragmentos": len(fragmentos)},
            "escenas": bloques,
        }

    active_sys = _select_system_prompt(prompt_mode, prompt_style)
    or_models = _openrouter_models()
    try:
        or_temperature = float((os.environ.get("OPENROUTER_TEMPERATURE") or "0.38").strip())
    except ValueError:
        or_temperature = 0.38

    scene_batch = max(1, int(os.environ.get("OPENROUTER_SCENE_BATCH", "96")))
    if prompt_mode == "stick":
        scene_batch = 1
    total_scene_count = max(1, len(bloques))
    if total_scene_count >= 120:
        scene_batch = max(scene_batch, 110)
    if total_scene_count >= 300:
        scene_batch = max(scene_batch, 120)

    cpu = os.cpu_count() or 4
    default_parallel = max(6, min(12, cpu + 2))
    parallel_batches = max(1, int(os.environ.get("OPENROUTER_PARALLEL_BATCHES", str(default_parallel))))

    chunks = [bloques[i:i + scene_batch] for i in range(0, len(bloques), scene_batch)]
    workers = min(parallel_batches, len(chunks))

    def run_chunk(chunk):
        return _gen_batch_safe(chunk, guion_text, estilo_efectivo, prompt_mode, active_sys, or_models, or_temperature)

    if workers <= 1:
        mappings = [run_chunk(c) for c in chunks]
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            mappings = list(ex.map(run_chunk, chunks))

    for chunk, mapping in zip(chunks, mappings):
        for b in chunk:
            gid = b["bloque_global_id"]
            if mapping.get(gid):
                b["prompt_imagen"] = mapping[gid]

    missing = [b for b in bloques if not (b.get("prompt_imagen") or "").strip()]
    if missing and len(bloques) >= 180:
        try:
            retry_cap = int((os.environ.get("OPENROUTER_MISSING_RETRY_CAP") or "120").strip())
        except ValueError:
            retry_cap = 120
        retry_cap = max(0, min(300, retry_cap))
        if retry_cap > 0:
            to_retry = missing[:retry_cap]
            sub_step = 12
            subs = [to_retry[i:i + sub_step] for i in range(0, len(to_retry), sub_step)]
            with ThreadPoolExecutor(max_workers=2) as ex:
                maps = list(ex.map(
                    lambda s: _gen_batch(s, guion_text, estilo_efectivo, prompt_mode, active_sys,
                                          or_models, or_temperature),
                    subs,
                ))
            for sub, m in zip(subs, maps):
                for b in sub:
                    v = (m.get(b["bloque_global_id"]) or "").strip()
                    if v:
                        b["prompt_imagen"] = v

    _fallback_fill(bloques, prompt_mode, estilo_efectivo)

    meta = {
        "total_escenas": len(bloques),
        "total_prompts": sum(1 for b in bloques if b["prompt_imagen"]),
        "total_fragmentos": len(fragmentos),
        "estilo_fuente": estilo_fuente,
    }
    if estilo_fuente == "imagen" and estilo_ref:
        meta["descripcion_estilo_para_reuso"] = estilo_ref
    return {"metadata": meta, "escenas": bloques}
