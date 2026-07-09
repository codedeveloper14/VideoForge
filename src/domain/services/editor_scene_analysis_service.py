import json
import re

import requests

from src.core.config import config
from src.utils.logger import get_logger

logger = get_logger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODELS = [
    "google/gemini-2.0-flash-001",
    "google/gemini-flash-1.5",
    "openai/gpt-4o-mini",
    "anthropic/claude-haiku-4-5",
    "meta-llama/llama-3.1-8b-instruct:free",
]
_BATCH = 20

_SYSTEM_PROMPT = (
    "Eres un editor de documentales BBC/Netflix experto en dinamismo visual. "
    "Responde SOLO con un array JSON valido, sin markdown ni texto extra.\n\n"
    "CAMPOS DE CADA OBJETO (usa null si no aplica):\n"
    "tipo | texto_overlay | texto_secundario | texto_overlay_pos | ref_label | "
    "google_query | google_query_2 | split_label_1 | split_label_2 | color_accent | numero_capitulo\n\n"
    "REGLA DE ORO DEL TEXTO_OVERLAY:\n"
    "texto_overlay = MAXIMO 3-4 PALABRAS. Es un TITULO o DATO, NO una oracion.\n"
    "CORRECTO: 'San Pedro', 'Pescador', '1492', '33 anos', '$30 mil millones'\n"
    "PROHIBIDO: frases largas, el texto completo de la escena, oraciones.\n"
    "Para escenas normales sin dato clave: texto_overlay = null.\n\n"
    "TIPOS — CUANDO USARLOS Y COMO:\n"
    "intro_dinamica: SIEMPRE escena 1. texto_overlay = TITULO del video (3-5 palabras, NO narración, NO preguntas, NO frases). EJEMPLO: 'Generacion X' o 'La Historia del Arte'.\n"
    "normal: narracion sin elemento visual especifico. texto_overlay = null. USAR LO MENOS POSIBLE.\n"
    "lower_third: hay un nombre, sigla, lugar o dato que conviene etiquetar abajo-izq mientras narra. texto_overlay = la etiqueta (2-4 palabras).\n"
    "  EJEMPLO: 'La CIA, la NSA, el FBI controlan...' --> lower_third, texto_overlay='CIA, NSA, FBI'\n"
    "  EJEMPLO: 'Los soviéticos lanzaron el Sputnik...' --> lower_third, texto_overlay='Sputnik, 1957'\n"
    "texto_enfasis: hay una CIFRA, FECHA o DATO impactante. texto_overlay = solo el dato.\n"
    "  EJEMPLO: '...costó 30 mil millones de dólares...' --> texto_enfasis, texto_overlay='$30 mil millones', color_accent=FFD700\n"
    "  EJEMPLO: 'En 1961, en plena Guerra Fría...' --> texto_enfasis, texto_overlay='1961', color_accent=00CFFF\n"
    "nombre_persona: se menciona una persona por PRIMERA VEZ con nombre propio. texto_overlay=nombre, texto_secundario=cargo.\n"
    "  EJEMPLO: 'Simon Pedro, pescador de Galilea...' --> nombre_persona, texto_overlay='Simon Pedro', texto_secundario='Apostol'\n"
    "texto_lateral: se describe un OFICIO, PROFESION o ACTIVIDAD. imagen ilustrativa centrada + titulo arriba.\n"
    "  EJEMPLO: 'era carpintero de profesion...' --> texto_lateral, texto_overlay='Carpintero', google_query='medieval carpenter illustration'\n"
    "  EJEMPLO: 'pescadores del Mar de Galilea...' --> texto_lateral, texto_overlay='Pescador', google_query='ancient fisherman nets illustration'\n"
    "ref_persona: se menciona figura historica conocida. imagen Google pantalla completa. ref_label='Nombre, fecha'.\n"
    "  EJEMPLO: 'Julio Cesar conquisto...' --> ref_persona, google_query='Julius Caesar portrait Roman', ref_label='Julio Cesar, 100 a.C.'\n"
    "ref_lugar: se menciona lugar, ciudad, pais o edificio. imagen Google pantalla completa. ref_label='Lugar, epoca'.\n"
    "  EJEMPLO: '...en Jerusalen, bajo el Imperio Romano...' --> ref_lugar, google_query='Jerusalem ancient Roman period aerial', ref_label='Jerusalen, siglo I'\n"
    "google_fullscreen: concepto visual fuerte sin persona ni lugar fijo: objeto, tecnologia, fenomeno, animal, epoca.\n"
    "  EJEMPLO: 'un satelite espía sobrevolando...' --> google_fullscreen, google_query='spy satellite orbit Earth photo'\n"
    "  EJEMPLO: 'la Red ARPANET conectaba...' --> google_fullscreen, google_query='ARPANET network diagram 1970s'\n"
    "ref_doble: comparacion EXPLICITA de dos personas, grupos o conceptos.\n"
    "  EJEMPLO: 'los romanos vs los judios...' --> ref_doble, split_label_1='Romanos', split_label_2='Judios'\n"
    "broll: escena descriptiva/contextual — imagen IA de fondo + imagen Google esquina. google_query obligatoria.\n"
    "quote_animado: CITA TEXTUAL dicha por alguien. texto_overlay = la cita completa.\n"
    "  EJEMPLO: 'dijo: Sobre esta roca edificare mi iglesia...' --> quote_animado, texto_overlay='Sobre esta roca edificare mi iglesia'\n"
    "titulo_capitulo: cambio claro de tema o era. max 3 por video. numero_capitulo obligatorio.\n\n"
    "REGLAS DE VARIEDAD — OBLIGATORIAS:\n"
    "1. Escena 1 = SIEMPRE intro_dinamica.\n"
    "2. Nombre propio mencionado en la escena --> ref_persona o nombre_persona EN ESA ESCENA.\n"
    "3. Lugar geografico mencionado --> ref_lugar EN ESA ESCENA.\n"
    "4. Cifra/fecha importante --> texto_enfasis EN ESA ESCENA.\n"
    "5. Cita textual directa --> quote_animado.\n"
    "6. Oficio/actividad descrita --> texto_lateral.\n"
    "7. NUNCA mas de 2 'normal' seguidos. Si llevas 2 normales, el siguiente DEBE ser otro tipo.\n"
    "8. MINIMO 50% de escenas con tipo != normal. Si el lote tiene 20 escenas, minimo 10 deben ser no-normal.\n"
    "9. google_query SIEMPRE en ingles especifico con contexto: 'Julius Caesar portrait Roman senator', no solo 'Julius Caesar'.\n"
    "10. color_accent: ffffff=normal, FFD700=positivo/impacto, FF3333=drama/conflicto/muerte, 00CFFF=ciencia/tecnologia.\n"
    "CRITICO: Asigna el tipo a la escena donde se MENCIONA la entidad, NO a la escena siguiente.\n"
    "RESPONDE SOLO EL ARRAY JSON, exactamente N objetos para N escenas."
)

_OVERLAY_LIMITS = {
    "texto_enfasis": (3, 25),
    "intro_dinamica": (5, 40),
    "titulo_capitulo": (4, 30),
    "nombre_persona": (4, 35),
    "texto_lateral": (2, 20),
    "lower_third": (4, 32),
    "ref_doble": (3, 25),
}
_NARRATION_PREFIXES = (
    "alguna",
    "algun",
    "por que",
    "sabes",
    "sabias",
    "imagina",
    "has ",
    "que ",
    "como ",
    "cuando ",
    "donde ",
    "si ",
)
_REF_TIPOS_SHIFT = {
    "ref_persona",
    "ref_lugar",
    "google_fullscreen",
    "broll",
    "lower_third",
    "nombre_persona",
    "texto_enfasis",
}
_SHIFT_FROM_TIPOS = ("normal", "lower_third", "texto_enfasis", "texto_lateral", "broll", "google_fullscreen")
_KW_TRANS = {
    "north korea": "corea",
    "korea": "corea",
    "tokyo": "tokio",
    "south china": "china del sur",
    "china": "china",
    "japan": "japón",
    "russia": "rusia",
    "soviet": "soviét",
    "syria": "siria",
    "iran": "irán",
    "iraq": "irak",
    "ukraine": "ucrania",
    "israel": "israel",
    "pakistan": "pakistán",
    "france": "franci",
    "germany": "alemani",
    "london": "londre",
    "paris": "paris",
    "berlin": "berlín",
    "washington": "washington",
    "virginia": "virginia",
    "cold war": "guerra fría",
    "convoy": "convoy",
    "nuclear": "nuclear",
    "vessel": "barco",
    "submarine": "submarino",
}
_WEAK_KWS = {
    "para",
    "este",
    "esta",
    "como",
    "pero",
    "cada",
    "solo",
    "todo",
    "tres",
    "otro",
    "otra",
    "del",
    "las",
    "los",
    "una",
    "unos",
    "unas",
    "que",
    "con",
    "sin",
    "por",
    "entre",
    "sobre",
    "desde",
    "hasta",
    "hay",
    "fue",
    "era",
    "son",
    "sus",
    "muy",
    "bien",
    "nada",
    "algo",
    "cuando",
    "donde",
    "porque",
    "aunque",
    "siempre",
    "nunca",
    "año",
    "años",
    "vez",
    "veces",
    "parte",
    "lugar",
    "tiempo",
    "vida",
    "de",
    "la",
    "el",
    "en",
    "al",
    "se",
    "su",
    "un",
    "es",
    "no",
    "lo",
}


def _robust_parse(text: str):
    """Repara/parsea la respuesta del LLM: quita fences markdown, comas colgantes,
    y si el JSON viene truncado reconstruye array u objetos completos por conteo
    de llaves/corchetes en vez de fallar directo."""
    s = text.strip()
    s = re.sub(r"```(?:json)?\s*", "", s)
    s = re.sub(r"```", "", s)
    s = s.strip()
    s = re.sub(r"//[^\n]*", "", s)
    s = re.sub(r",\s*([}\]])", r"\1", s)
    try:
        return json.loads(s)
    except Exception:
        pass

    bs = s.find("[")
    if bs != -1:
        depth, be, in_str, esc = 0, -1, False, False
        for ci, ch in enumerate(s[bs:], bs):
            if esc:
                esc = False
                continue
            if ch == "\\" and in_str:
                esc = True
                continue
            if ch == '"' and not esc:
                in_str = not in_str
            if not in_str:
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        be = ci + 1
                        break
        if be > bs:
            cleaned = re.sub(r",\s*([}\]])", r"\1", s[bs:be])
            try:
                return json.loads(cleaned)
            except Exception:
                pass
            frag, recovered, depth2, obj_start, in_str2, esc2 = s[bs:], [], 0, -1, False, False
            for ci, ch in enumerate(frag):
                if esc2:
                    esc2 = False
                    continue
                if ch == "\\" and in_str2:
                    esc2 = True
                    continue
                if ch == '"' and not esc2:
                    in_str2 = not in_str2
                if not in_str2:
                    if ch == "{":
                        if depth2 == 0:
                            obj_start = ci
                        depth2 += 1
                    elif ch == "}":
                        depth2 -= 1
                        if depth2 == 0 and obj_start >= 0:
                            obj_text = re.sub(r",\s*([}\]])", r"\1", frag[obj_start : ci + 1])
                            try:
                                recovered.append(json.loads(obj_text))
                                obj_start = -1
                            except Exception:
                                pass
            if recovered:
                logger.info("editor_analizar: JSON truncado, recuperados %d objetos", len(recovered))
                return recovered

    brk = s.find("{")
    if brk != -1:
        depth3, brke, in_str3, esc3 = 0, -1, False, False
        for ci, ch in enumerate(s[brk:], brk):
            if esc3:
                esc3 = False
                continue
            if ch == "\\" and in_str3:
                esc3 = True
                continue
            if ch == '"' and not esc3:
                in_str3 = not in_str3
            if not in_str3:
                if ch == "{":
                    depth3 += 1
                elif ch == "}":
                    depth3 -= 1
                    if depth3 == 0:
                        brke = ci + 1
                        break
        if brke > brk:
            cleaned = re.sub(r",\s*([}\]])", r"\1", s[brk:brke])
            try:
                obj = json.loads(cleaned)
                if isinstance(obj, dict):
                    for key in ("escenas", "scenes", "resultado", "data", "items"):
                        if isinstance(obj.get(key), list):
                            return obj[key]
                    return obj
            except Exception:
                pass

    try:
        from json_repair import repair_json

        repaired = repair_json(s, return_objects=True)
        if repaired:
            return repaired
    except ImportError:
        pass
    raise ValueError(f"No se pudo parsear JSON. Inicio: {s[:200]!r}")


def _sanitize_overlay(text, tipo: str) -> str | None:
    if not text:
        return None
    t = " ".join(str(text).strip().split())
    if not t:
        return None
    if tipo == "quote_animado":
        return t[:150] if len(t) > 150 else t
    if tipo == "intro_dinamica":
        narration_signs = (
            t.startswith("¿"),
            t.startswith("¡"),
            t.startswith("?"),
            "?" in t,
            len(t.split()) > 5,
            any(t.lower().startswith(w) for w in _NARRATION_PREFIXES),
        )
        if any(narration_signs):
            return None
    max_w, max_c = _OVERLAY_LIMITS.get(tipo, (5, 35))
    words = t.split()
    if len(words) > max_w:
        t = " ".join(words[:max_w])
    if len(t) > max_c:
        t = t[:max_c].rsplit(" ", 1)[0] if " " in t[:max_c] else t[:max_c]
    if tipo in ("normal", "broll", "ref_persona", "ref_lugar", "google_fullscreen"):
        if len(t.split()) > 4 or len(t) > 30:
            return None
    return t.strip() or None


def _call_openrouter_batch(system_prompt: str, user_text: str, api_key: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://studio-ivr.app",
    }
    resp, last_err = None, None
    for model in _MODELS:
        try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                "max_tokens": 6000,
                "temperature": 0.5,
            }
            resp = requests.post(_OPENROUTER_URL, headers=headers, json=payload, timeout=90)
            if resp.status_code == 200:
                if (resp.json().get("choices", [{}])[0].get("finish_reason", "")) == "length":
                    last_err = f"{model} truncado"
                    continue
                break
            last_err = f"HTTP {resp.status_code} {model}: {resp.text[:120]}"
        except Exception as exc:
            last_err = str(exc)

    if resp is None or resp.status_code != 200:
        raise Exception(last_err or "Todos los modelos fallaron")

    resp_json = resp.json()
    if "choices" not in resp_json:
        err = resp_json.get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else str(resp_json)
        raise Exception(f"OpenRouter sin 'choices': {str(msg)[:200]}")
    return resp_json


def _build_keywords(scene: dict) -> set[str]:
    """Keywords para buscar en el texto de la escena anterior (deteccion de desfase)."""
    kws = set()
    tipo = scene.get("tipo", "normal")

    for part in re.findall(r"[a-záéíóúüñ]{3,}", (scene.get("ref_label") or "").lower()):
        if part not in _WEAK_KWS:
            kws.add(part)

    overlay = (scene.get("texto_overlay") or "").strip()
    if overlay:
        for part in re.split(r"[,\s%]+", overlay):
            part = part.strip().lower()
            if len(part) >= 2 and part not in _WEAK_KWS:
                kws.add(part)

    query = (scene.get("google_query") or "").lower()
    for en, es in _KW_TRANS.items():
        if en in query:
            for w in es.split():
                if len(w) > 3 and w not in _WEAK_KWS:
                    kws.add(w)

    if tipo == "texto_enfasis":
        own_text = (scene.get("texto") or "").lower()
        own_words = [w for w in re.findall(r"[a-záéíóúüñ]{5,}", own_text) if w not in _WEAK_KWS]
        kws.update(own_words[:5])

    return kws


def analizar_escenas(escenas: list[dict], project_name: str) -> list[dict]:
    """Clasifica cada escena en un tipo cinematografico (intro, lower_third, quote,
    ref_persona/lugar, etc.) y asigna overlays/queries de imagen via OpenRouter,
    en lotes de 20 escenas con una lista de modelos de fallback."""
    api_key = (config.openrouter_api_key or "").strip()
    if not escenas:
        raise ValueError("Sin escenas")

    n_total = len(escenas)
    analisis: list[dict] = []
    for bi in range((n_total + _BATCH - 1) // _BATCH):
        ini, fin = bi * _BATCH, min(bi * _BATCH + _BATCH, n_total)
        sub = escenas[ini:fin]
        n = len(sub)
        user_text = (
            f"Video: {project_name or 'sin nombre'}\n"
            f"Escenas {ini + 1} a {fin} de {n_total} totales:\n"
            + "\n".join(f"{ini + j + 1}. {e.get('texto', '').strip()}" for j, e in enumerate(sub))
            + f"\n\nRECUERDA: De estas {n} escenas, MINIMO {max(1, n // 2)} deben ser tipo != normal. "
            f"Busca activamente: nombres propios-->nombre_persona/ref_persona, "
            f"lugares-->ref_lugar, cifras/fechas-->texto_enfasis, "
            f"oficios-->texto_lateral, citas textuales-->quote_animado, "
            f"siglas/etiquetas-->lower_third, conceptos visuales-->google_fullscreen.\n"
            f"Devuelve EXACTAMENTE {n} objetos JSON en el array, uno por escena, en orden."
        )
        resp_json = _call_openrouter_batch(_SYSTEM_PROMPT, user_text, api_key)
        raw = resp_json["choices"][0]["message"]["content"].strip()
        try:
            lote = _robust_parse(raw)
        except Exception as exc:
            logger.info("editor_analizar: parse error lote %d: %s", bi + 1, exc)
            lote = [{"tipo": "normal"} for _ in sub]

        if not isinstance(lote, list):
            lote = [lote] if isinstance(lote, dict) else []
        while len(lote) < n:
            lote.append({"tipo": "normal"})
        lote = lote[:n]
        analisis.extend(lote)

    result = []
    for i, esc in enumerate(escenas):
        meta = analisis[i] if i < len(analisis) else {}
        tipo = meta.get("tipo", "normal")
        overlay = _sanitize_overlay(meta.get("texto_overlay"), tipo)

        if tipo == "intro_dinamica" and not overlay and project_name:
            pn_words = project_name.replace("_", " ").replace("-", " ").strip().split()
            overlay = " ".join(pn_words[:5]) if pn_words else None

        result.append(
            {
                "indice": i,
                "texto": esc.get("texto", ""),
                "imagen_file": esc.get("imagen_file", ""),
                "tipo": tipo,
                "texto_overlay": overlay,
                "texto_overlay_pos": meta.get("texto_overlay_pos", "bottom_center"),
                "texto_secundario": meta.get("texto_secundario"),
                "ref_label": meta.get("ref_label"),
                "google_query": meta.get("google_query"),
                "google_query_2": meta.get("google_query_2"),
                "split_lado": meta.get("split_lado", "left"),
                "split_label_1": meta.get("split_label_1"),
                "split_label_2": meta.get("split_label_2"),
                "color_accent": meta.get("color_accent", "#ffffff"),
                "numero_capitulo": meta.get("numero_capitulo"),
                "ref_image_url": None,
                "ref_image_b64": None,
                "ref_image_url_2": None,
                "ref_image_b64_2": None,
                "habilitado": True,
            }
        )

    # Correccion de desfase: el LLM a veces asigna el tipo visual a la escena que
    # EMPIEZA con el tema, pero la mencion oral ocurre al FINAL de la escena anterior.
    # Si las keywords del tipo visual aparecen en el texto de la escena anterior, adelantar.
    move_fields = [
        "tipo",
        "texto_overlay",
        "texto_overlay_pos",
        "texto_secundario",
        "ref_label",
        "google_query",
        "google_query_2",
        "split_label_1",
        "split_label_2",
        "color_accent",
        "numero_capitulo",
    ]
    for i in range(1, len(result)):
        scene, prev = result[i], result[i - 1]
        if scene["tipo"] not in _REF_TIPOS_SHIFT or prev["tipo"] not in _SHIFT_FROM_TIPOS:
            continue
        kws = _build_keywords(scene)
        if not kws:
            continue
        prev_text = (prev.get("texto") or "").lower()
        hits = [w for w in kws if w in prev_text and w not in _WEAK_KWS]
        if not hits:
            continue
        logger.info("editor_analizar: sync E%d->E%d '%s' hits=%s", i + 1, i, scene["tipo"], hits[:3])
        for field in move_fields:
            result[i - 1][field] = scene[field]
        result[i]["tipo"] = "normal"
        result[i]["google_query"] = None
        result[i]["ref_label"] = None
        result[i]["texto_overlay"] = _sanitize_overlay(
            analisis[i].get("texto_overlay") if i < len(analisis) else None, "normal"
        )

    return result
