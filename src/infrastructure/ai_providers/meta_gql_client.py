import copy
import json
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

META_BASE = "https://www.meta.ai"
META_GQL = f"{META_BASE}/api/graphql"
META_UPLOAD_BASE = "https://rupload.meta.ai/gen_ai_document_gen_ai_tenant"

_META_DOC_WARMUP = "e7f802582dbfed8e181b012e010993eb"
_META_DOC_MODE = "c32bbe999c48e64e855dc63177d5153f"
_META_DOC_CARD = "344570a4b8110dd9848829731d35c74a"
_META_DOC_SEND_MSG = "26999e5d1366c257595b7fafa7822c31"
_META_DOC_FETCH_CONV = "4fd795143fc5b90fc1fc3ca716bdbb86"

META_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_META_GQL_ACCEPT = "*/*"  # application/json --> HTTP 406; Meta solo acepta */*


def _NoOpLog(msg: str) -> None:
    pass


def cookies_for_requests(cookie_list: list) -> dict:
    return {c["name"]: c["value"] for c in cookie_list if isinstance(c, dict) and "name" in c}


def fetch_lsd(session: requests.Session) -> str:
    """GET meta.ai/create una vez y extrae el token LSD (CSRF) que Meta exige en todos los POST GQL."""
    try:
        r = session.get(
            f"{META_BASE}/create",
            headers={
                "user-agent": META_UA,
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=20,
        )
        m = re.search(r'"LSD",\[\],\{"token":"([^"]{4,32})"', r.text)
        if m:
            return m.group(1)
        m = re.search(r'name=["\']lsd["\']\s+value=["\']([^"\']{4,32})["\']', r.text)
        if m:
            return m.group(1)
        m = re.search(r'"lsd"\s*:\s*"([A-Za-z0-9_\-]{4,32})"', r.text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def gql_headers(cookie_dict: dict, lsd: str = "") -> dict:
    h = {
        "accept": _META_GQL_ACCEPT,
        "content-type": "application/json",
        "origin": META_BASE,
        "referer": f"{META_BASE}/create",
        "user-agent": META_UA,
        "x-asbd-id": "129477",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }
    if lsd:
        h["x-fb-lsd"] = lsd
    return h


def upload_headers(oauth_token: str, file_size: int, filename: str, mime: str = "image/jpeg") -> dict:
    auth_val = oauth_token if oauth_token.startswith("OAuth") else f"OAuth ecto1:{oauth_token}"
    return {
        "authorization": auth_val,
        "desired_upload_handler": "genai_document",
        "ecto_auth_token": "true",
        "is_abra_user": "true",
        "offset": "0",
        "x-entity-length": str(file_size),
        "x-entity-name": filename,
        "x-entity-type": mime,
        "content-type": mime,
        "origin": META_BASE,
        "referer": f"{META_BASE}/",
        "user-agent": META_UA,
    }


def _patch_vars(obj, prompt_val, conv_id_val, doc_ref_val, msg_id_val):
    if isinstance(obj, dict):
        return {k: _patch_vars(v, prompt_val, conv_id_val, doc_ref_val, msg_id_val) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_patch_vars(v, prompt_val, conv_id_val, doc_ref_val, msg_id_val) for v in obj]
    if isinstance(obj, str):
        if obj == "__PROMPT__":
            return prompt_val
        if obj == "__CONV_ID__":
            return conv_id_val
        if obj == "__DOC_REF__":
            return doc_ref_val or ""
        if obj == "__MSG_ID__":
            return msg_id_val
        if obj == "__UNIQUE_MSG_ID__":
            return str(time.time_ns() // 1000)[:19]
    return obj


def _find_generated_video_url(buf: str) -> str | None:
    """Busca 'url' dentro de generatedVideo:{...} con brace-tracking (regex simple
    falla si hay objetos anidados)."""
    pos = 0
    while True:
        gv_idx = buf.find('"generatedVideo"', pos)
        if gv_idx == -1:
            return None
        pos = gv_idx + 16
        ci = buf.find(":", gv_idx + 16)
        if ci == -1 or ci > gv_idx + 40:
            continue
        vi = ci + 1
        while vi < len(buf) and buf[vi] in " \t\n\r":
            vi += 1
        if vi >= len(buf) or buf[vi] != "{":
            continue
        depth = 0
        obj_end = -1
        for j in range(vi, min(vi + 8192, len(buf))):
            if buf[j] == "{":
                depth += 1
            elif buf[j] == "}":
                depth -= 1
                if depth == 0:
                    obj_end = j
                    break
        if obj_end == -1:
            return None  # objeto incompleto, esperar mas datos
        inner = buf[vi + 1 : obj_end]
        url_m = re.search(r'"url"\s*:\s*"(https?:[^"]+)"', inner)
        if url_m:
            return url_m.group(1).replace("\\/", "/")


def generate_http(
    cookie_list: list,
    api_state: dict,
    prompt: str,
    image_path: str | None = None,
    out_path: str | None = None,
    timeout_sec: int = 300,
    slot_id: int = 0,
    send_msg_tpl_fallback: str | None = None,
    log: Callable[[str], None] = _NoOpLog,
) -> dict:
    """Generacion pura HTTP -- sin browser, sin Playwright.

    Requiere api_state con al menos oauth_token, gen_doc_id, gen_variables_template.
    Devuelve {"url": str|None, "saved": bool, "error": str|None}.
    """
    result = {"url": None, "saved": False, "error": None}
    oauth_token = api_state.get("oauth_token", "")
    gen_doc_id = api_state.get("gen_doc_id", "")
    gen_vars_tpl = api_state.get("gen_variables_template", {})

    if not oauth_token or not gen_doc_id:
        result["error"] = "api_state incompleto - falta oauth_token o gen_doc_id"
        return result

    sess = requests.Session()
    cookie_dict = cookies_for_requests(cookie_list)
    sess.cookies.update(cookie_dict)

    lsd = api_state.get("_lsd") or fetch_lsd(sess)
    if lsd:
        log(f"[S{slot_id}] LSD={lsd[:8]}...")
    else:
        log(f"[S{slot_id}] [WARNING] LSD no encontrado - sesion expirada o rate-limit")

    gql_h = gql_headers(cookie_dict, lsd)
    conv_id = str(uuid.uuid4())
    msg_id = str(uuid.uuid4())

    try:
        r = sess.post(
            META_GQL,
            headers=gql_h,
            json={"doc_id": _META_DOC_WARMUP, "variables": {"conversationId": conv_id}},
            timeout=20,
        )
        r.raise_for_status()
    except Exception as exc:
        result["error"] = f"Warmup fallo: {exc}"
        return result

    try:
        r = sess.post(
            META_GQL,
            headers=gql_h,
            json={
                "doc_id": _META_DOC_MODE,
                "variables": {"input": {"conversationId": conv_id, "mode": "create"}},
            },
            timeout=20,
        )
        r.raise_for_status()
    except Exception as exc:
        result["error"] = f"SetMode fallo: {exc}"
        return result

    doc_ref = None
    if image_path and Path(image_path).is_file():
        img_bytes = Path(image_path).read_bytes()
        img_size = len(img_bytes)
        img_name = Path(image_path).name
        mime = "image/jpeg" if img_name.lower().endswith((".jpg", ".jpeg")) else "image/png"
        upload_url = f"{META_UPLOAD_BASE}/{uuid.uuid4()}"
        up_h = upload_headers(oauth_token, img_size, img_name, mime)
        try:
            r = sess.post(upload_url, headers=up_h, data=img_bytes, timeout=60)
            r.raise_for_status()
            raw_txt = r.text.strip()
            log(f"[S{slot_id}] rupload raw: {raw_txt[:120]}")
            try:
                body = r.json()
                doc_ref = (
                    body.get("h")
                    or body.get("handle")
                    or body.get("doc_id")
                    or body.get("id")
                    or body.get("media_id")
                )
            except Exception:
                doc_ref = None
            if not doc_ref and raw_txt:
                try:
                    doc_ref = int(raw_txt)
                except (ValueError, TypeError):
                    if raw_txt and not raw_txt.startswith("{") and len(raw_txt) < 80:
                        doc_ref = raw_txt
            log(f"[S{slot_id}] HTTP upload OK --> ref={str(doc_ref)[:40]}")
        except Exception as exc:
            log(f"[S{slot_id}] [WARNING] Upload fallo: {exc} - continuando sin imagen")
            doc_ref = None

    gen_vars = _patch_vars(copy.deepcopy(gen_vars_tpl), prompt, conv_id, doc_ref, msg_id)
    log(f"[S{slot_id}] gen_doc_id={gen_doc_id[:20]} vars={json.dumps(gen_vars)[:300]}")

    send_msg_tpl_raw = api_state.get("send_msg_tpl") or send_msg_tpl_fallback
    if send_msg_tpl_raw:
        try:
            send_msg_tpl_obj = (
                json.loads(send_msg_tpl_raw) if isinstance(send_msg_tpl_raw, str) else send_msg_tpl_raw
            )
            sm_vars = _patch_vars(send_msg_tpl_obj, prompt, conv_id, doc_ref, msg_id)
            log(f"[S{slot_id}] sendMessage --> conv={conv_id[:8]}... vars={json.dumps(sm_vars)[:200]}")
            r_sm = sess.post(
                META_GQL, headers=gql_h, json={"doc_id": _META_DOC_SEND_MSG, "variables": sm_vars}, timeout=30
            )
            if r_sm.ok:
                log(f"[S{slot_id}] [OK] sendMessage OK (HTTP {r_sm.status_code})")
            else:
                log(f"[S{slot_id}] [WARNING] sendMessage HTTP {r_sm.status_code} - continuando")
        except Exception as exc:
            log(f"[S{slot_id}] [WARNING] sendMessage fallo: {exc} - continuando sin prompt")
    else:
        log(f"[S{slot_id}] [WARNING] send_msg_tpl no disponible - generando sin prompt de texto")

    video_url_direct = None
    gen_attempt = 0
    GEN_MAX_RETRY = 8
    deadline_ts = time.time() + timeout_sec
    buf = ""

    while gen_attempt <= GEN_MAX_RETRY and time.time() < deadline_ts:
        gen_attempt += 1
        try:
            r = sess.post(
                META_GQL,
                headers=gql_h,
                json={"doc_id": gen_doc_id, "variables": gen_vars},
                timeout=(15, 90),
                stream=True,
            )
            if not r.ok:
                err_txt = ""
                try:
                    for chunk in r.iter_content(4096, decode_unicode=True):
                        err_txt += chunk if isinstance(chunk, str) else chunk.decode("utf-8", "replace")
                        if len(err_txt) > 500:
                            break
                except Exception:
                    pass
                log(f"[S{slot_id}] [WARNING] gen HTTP {r.status_code}: {err_txt[:300]}")
                result["error"] = f"HTTP {r.status_code}: {err_txt[:200]}"
                return result

            buf = ""
            had_progress = False
            last_log = time.time()
            log(f"[S{slot_id}] Leyendo stream SSE (intento {gen_attempt}/{GEN_MAX_RETRY + 1})...")
            try:
                for chunk in r.iter_content(8192, decode_unicode=True):
                    if isinstance(chunk, bytes):
                        chunk = chunk.decode("utf-8", "replace")
                    buf += chunk

                    if not had_progress and '"status":"IN_PROGRESS"' in buf:
                        had_progress = True

                    found_url = _find_generated_video_url(buf)
                    if found_url:
                        video_url_direct = found_url
                        break

                    if '"status":"COMPLETE"' in buf:
                        log(f"[S{slot_id}] COMPLETE - buscando URL... ultimos 400B: {buf[-400:]!r}")
                        fb_m = re.search(r'https?://video-[^\s"\'].*?fbcdn\.net[^\s"\']*', buf)
                        if fb_m:
                            video_url_direct = fb_m.group(0).replace("\\/", "/")
                            log(f"[S{slot_id}] [OK] URL fallback CDN: {video_url_direct[:80]}")
                            break

                    if '"status":"ERROR"' in buf or '"status":"FAILED"' in buf:
                        log(f"[S{slot_id}] [ERROR] Generacion ERROR en stream")
                        result["error"] = "ERROR de generacion (stream)"
                        return result

                    if time.time() - last_log > 15:
                        last_log = time.time()
                        log(f"[S{slot_id}] stream activo {len(buf)}B... ultimo: {buf[-100:]!r}")
            except Exception as exc:
                log(f"[S{slot_id}] [WARNING] Stream read error (intento {gen_attempt}): {exc}")
            finally:
                try:
                    r.close()
                except Exception:
                    pass

            if video_url_direct:
                break

            log(
                f"[S{slot_id}] Stream cerrado sin URL (intento {gen_attempt}) had_progress={had_progress} "
                f"buf={len(buf)}B ultimo: {buf[-300:]!r}"
            )

            if "event: complete" in buf and time.time() < deadline_ts:
                log(f"[S{slot_id}] SSE event:complete --> polling fetchConversation (conv={conv_id[:8]}...)")
                poll_interval = 10
                poll_count = 0
                MAX_POLLS = 30
                while poll_count < MAX_POLLS and time.time() < deadline_ts:
                    time.sleep(poll_interval)
                    poll_count += 1
                    try:
                        r_fc = sess.post(
                            META_GQL,
                            headers=gql_h,
                            json={"doc_id": _META_DOC_FETCH_CONV, "variables": {"id": conv_id}},
                            timeout=30,
                        )
                        fc_txt = r_fc.text
                        fc_url = _find_generated_video_url(fc_txt)
                        if not fc_url:
                            fc_fbm = re.search(r'https?://video-[^\s"\'].*?fbcdn\.net[^\s"\']*', fc_txt)
                            if fc_fbm:
                                fc_url = fc_fbm.group(0).replace("\\/", "/")
                        if fc_url:
                            log(
                                f"[S{slot_id}] [OK] URL via fetchConversation poll #{poll_count}: {fc_url[:80]}"
                            )
                            video_url_direct = fc_url
                            break
                        log(
                            f"[S{slot_id}] fetchConv poll #{poll_count}/{MAX_POLLS} - sin URL. "
                            f"ultimos 200B: {fc_txt[-200:]!r}"
                        )
                    except Exception as fc_e:
                        log(f"[S{slot_id}] [WARNING] fetchConv poll #{poll_count} error: {fc_e}")
                if video_url_direct:
                    break
                result["error"] = f"Timeout fetchConversation ({poll_count} polls) - sin URL"
                return result

            if had_progress and gen_attempt <= GEN_MAX_RETRY and time.time() < deadline_ts:
                retry_wait = min(3 + gen_attempt * 2, 20)
                log(f"[S{slot_id}] Stream caido sin event:complete --> reintentando gen en {retry_wait}s...")
                time.sleep(retry_wait)
            else:
                result["error"] = f"Stream SSE termino sin generatedVideo URL (intentos={gen_attempt})"
                return result

        except Exception as exc:
            log(f"[S{slot_id}] [WARNING] Gen trigger error (intento {gen_attempt}): {exc}")
            result["error"] = f"Gen trigger fallo: {exc}"
            return result

    log(
        f"[S{slot_id}] HTTP gen --> videoUrl={str(video_url_direct)[:60] or 'no encontrado'} "
        f"(intentos={gen_attempt} buf={len(buf)}B)"
    )
    if not video_url_direct:
        log(f"[S{slot_id}] Ultimos 400B del stream: {buf[-400:]!r}")
        result["error"] = f"Stream SSE termino sin generatedVideo URL (intentos={gen_attempt})"
        return result

    if out_path:
        try:
            h_dl = {"user-agent": META_UA, "referer": f"{META_BASE}/"}
            r_dl = sess.get(video_url_direct, headers=h_dl, timeout=120, stream=True)
            r_dl.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r_dl.iter_content(65536):
                    f.write(chunk)
            result["url"] = video_url_direct
            result["saved"] = True
            log(f"[S{slot_id}] [OK] Video descargado directamente del stream SSE")
            return result
        except Exception as exc:
            log(f"[S{slot_id}] [WARNING] Descarga directa fallo: {exc}")

    result["url"] = video_url_direct
    return result
