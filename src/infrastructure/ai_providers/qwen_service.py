import json
import mimetypes
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from src.infrastructure.ai_providers.chrome_launcher import find_chromium_exe
from src.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from curl_cffi import requests as _cf_requests

    HAS_CURL_CFFI = True
except Exception:
    _cf_requests = None
    HAS_CURL_CFFI = False

QWEN_BASE = "https://chat.qwen.ai"
QWEN_API_BASE = f"{QWEN_BASE}/api"
QWEN_CHAT_NEW_URL = f"{QWEN_API_BASE}/v2/chats/new"
QWEN_CHAT_COMPLETIONS_URL = f"{QWEN_API_BASE}/v2/chat/completions"
QWEN_TASK_STATUS_URL = f"{QWEN_API_BASE}/v1/tasks/status/{{task_id}}"
QWEN_STS_TOKEN_URL = f"{QWEN_API_BASE}/v2/files/getstsToken"
QWEN_MODEL_T2V = "qwen3.5-plus"
QWEN_MODEL_I2V = "qwen3.5-plus"
QWEN_SIZE_MAP = {
    "1280x720": "16:9",
    "720x1280": "9:16",
    "960x960": "1:1",
    "1920x1080": "16:9",
    "1080x1920": "9:16",
}


def qwen_post(url: str, **kwargs):
    if HAS_CURL_CFFI:
        try:
            return _cf_requests.post(url, impersonate="chrome", default_headers=False, **kwargs)
        except TypeError:
            return _cf_requests.post(url, impersonate="chrome", **kwargs)
        except Exception:
            pass
    return requests.post(url, **kwargs)


def qwen_get(url: str, **kwargs):
    if HAS_CURL_CFFI:
        try:
            return _cf_requests.get(url, impersonate="chrome", default_headers=False, **kwargs)
        except TypeError:
            return _cf_requests.get(url, impersonate="chrome", **kwargs)
        except Exception:
            pass
    return requests.get(url, **kwargs)


def qwen_headers(token: str, cookie_header: str = "", session_meta: dict | None = None) -> dict:
    h = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Origin": QWEN_BASE,
        "Referer": f"{QWEN_BASE}/",
        "source": "web",
        "Version": "0.2.30",
    }
    if cookie_header:
        h["Cookie"] = cookie_header
    sm = session_meta or {}
    if sm.get("x_statsig_id"):
        h["x-statsig-id"] = str(sm["x_statsig_id"])
    if sm.get("baggage"):
        h["baggage"] = str(sm["baggage"])
    if sm.get("sentry_trace"):
        h["sentry-trace"] = str(sm["sentry_trace"])
    return h


# ─────────────────────────────────────────────────────────────────
# Cuentas / sesiones
# ─────────────────────────────────────────────────────────────────


def account_dir(accounts_dir: Path, name: str) -> Path:
    safe = re.sub(r"[^\w\-]", "_", (name or "").strip())[:60]
    return accounts_dir / safe


def ensure_accounts(accounts_dir: Path, count: int = 10) -> None:
    accounts_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, count + 1):
        (accounts_dir / f"account_{i}").mkdir(parents=True, exist_ok=True)


def account_token(path: Path) -> str:
    tf = path / "token.txt"
    if not tf.is_file():
        return ""
    try:
        return tf.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def load_cookies(path: Path) -> list[dict]:
    cf = path / "cookies_auto.json"
    if not cf.is_file():
        return []
    try:
        arr = json.loads(cf.read_text(encoding="utf-8"))
        return [c for c in arr if isinstance(c, dict) and c.get("name")] if isinstance(arr, list) else []
    except Exception:
        return []


def cookie_header_from_cookies(cookies: list[dict]) -> str:
    try:
        return "; ".join(
            f"{str(c.get('name', '')).strip()}={str(c.get('value', '')).strip()}"
            for c in (cookies or [])
            if str(c.get("name", "")).strip()
        )
    except Exception:
        return ""


def load_session_meta(path: Path) -> dict:
    smf = path / "session_meta.json"
    if not smf.is_file():
        return {}
    try:
        d = json.loads(smf.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def delete_account_session(accounts_dir: Path, account_name: str) -> None:
    base = account_dir(accounts_dir, account_name)
    for fname in ("token.txt", "cookies_auto.json"):
        f = base / fname
        if f.exists():
            f.unlink()


def test_token(token: str, cookie_header: str = "", session_meta: dict | None = None) -> tuple[bool, str]:
    try:
        resp = qwen_get(
            f"{QWEN_API_BASE}/v1/tasks/status/nonexistent-test",
            headers=qwen_headers(token, cookie_header=cookie_header, session_meta=session_meta),
            timeout=15,
        )
        if resp.status_code in (200, 404):
            return True, "ok"
        if resp.status_code == 401:
            return False, "Token invalido/expirado"
        return False, f"HTTP {resp.status_code}"
    except Exception as exc:
        return False, str(exc)


# ─────────────────────────────────────────────────────────────────
# Verificacion de red en background: list_account_sessions() NO debe bloquear
# al llamador con requests HTTP en vivo (antes hacia test_token() secuencial
# por cada cuenta, hasta N x 15s de timeout dentro del propio GET /sesiones --
# eso es lo que producia "Network Error" en el frontend cuando la red estaba
# lenta/inalcanzable: algo aguas abajo terminaba cortando la conexion antes de
# que Flask lograra responder). Ahora list_account_sessions() solo lee disco
# (igual que Grok) y devuelve el ultimo resultado de verificacion en cache si
# existe; la verificacion real corre en un ThreadPoolExecutor en paralelo, en
# un hilo de fondo separado, y solo se dispara una vez por ciclo (no se apila
# un verify nuevo mientras el anterior sigue corriendo).
_verify_cache: dict[str, tuple[bool, str]] = {}
_verify_lock = threading.Lock()
_verify_inflight = False


def _verify_one(folder: Path) -> tuple[str, tuple[bool, str] | None]:
    tk = account_token(folder)
    if not tk:
        return folder.name, None
    ck = load_cookies(folder)
    cookie_header = cookie_header_from_cookies(ck)
    sm = load_session_meta(folder)
    result = test_token(tk, cookie_header=cookie_header, session_meta=sm)
    return folder.name, result


def _verify_accounts_background(folders: list[Path]) -> None:
    global _verify_inflight
    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for name, result in ex.map(_verify_one, folders):
                if result is None:
                    continue
                with _verify_lock:
                    _verify_cache[name] = result
    finally:
        with _verify_lock:
            _verify_inflight = False


def list_account_sessions(accounts_dir: Path) -> list[dict]:
    global _verify_inflight
    folders = [f for f in sorted(accounts_dir.iterdir()) if f.is_dir()]
    rows = []
    needs_verify = False
    for folder in folders:
        tk = account_token(folder)
        ck = load_cookies(folder)
        if not tk:
            rows.append({"name": folder.name, "active": False, "user": "sin sesion", "has_cookies": bool(ck)})
            continue
        cached = _verify_cache.get(folder.name)
        if cached is not None:
            active, detail = cached
        else:
            # Sin verificacion todavia: hay token en disco -- lo mostramos
            # optimistamente como activo (igual que Grok con la cookie "sso")
            # mientras el ThreadPoolExecutor confirma en paralelo.
            active, detail = True, "sin verificar"
            needs_verify = True
        rows.append({"name": folder.name, "active": bool(active), "user": detail, "has_cookies": bool(ck)})

    if needs_verify:
        with _verify_lock:
            already_running = _verify_inflight
            if not already_running:
                _verify_inflight = True
        if not already_running:
            threading.Thread(target=_verify_accounts_background, args=(folders,), daemon=True).start()

    return rows


def tokens_for_run(accounts_dir: Path) -> list[tuple[str, str, str, dict]]:
    tokens = []
    for folder in sorted(accounts_dir.iterdir()):
        if not folder.is_dir():
            continue
        tk = account_token(folder)
        if not tk:
            continue
        ck = load_cookies(folder)
        cookie_header = cookie_header_from_cookies(ck)
        sm = load_session_meta(folder)
        ok, _ = test_token(tk, cookie_header=cookie_header, session_meta=sm)
        if ok:
            tokens.append((folder.name, tk, cookie_header, sm))
    return tokens


# ─────────────────────────────────────────────────────────────────
# Generacion (upload -> chat -> completion -> poll -> download)
# ─────────────────────────────────────────────────────────────────


def _extract_token_from_storage_entries(entries) -> str:
    for k, v in entries:
        ks = str(k or "").lower()
        vs = str(v or "").strip()
        if not vs:
            continue
        candidates = [vs]
        try:
            if (vs.startswith("{") and vs.endswith("}")) or (vs.startswith("[") and vs.endswith("]")):
                stack = [json.loads(vs)]
                while stack:
                    cur = stack.pop()
                    if isinstance(cur, dict):
                        for kk, vv in cur.items():
                            lkk = str(kk).lower()
                            if isinstance(vv, dict | list):
                                stack.append(vv)
                            else:
                                sv = str(vv or "").strip()
                                if ("token" in lkk or "access" in lkk or "bearer" in lkk) and len(sv) > 30:
                                    candidates.append(sv)
                    elif isinstance(cur, list):
                        stack.extend(cur)
        except Exception:
            pass
        for c in candidates:
            token = c
            if token.lower().startswith("bearer "):
                token = token.split(" ", 1)[1].strip()
            if len(token) > 30 and (
                ("." in token) or ("token" in ks) or ("access" in ks) or ("bearer" in ks)
            ):
                return token
    return ""


def create_chat(token: str, chat_type: str = "i2v", cookie_header: str = "", session_meta=None) -> str:
    payload = {
        "title": "New Chat",
        "models": [QWEN_MODEL_T2V],
        "chat_mode": "normal",
        "chat_type": chat_type,
        "timestamp": int(time.time() * 1000),
        "project_id": "",
    }
    resp = qwen_post(
        QWEN_CHAT_NEW_URL, headers=qwen_headers(token, cookie_header, session_meta), json=payload, timeout=30
    )
    if resp.status_code != 200:
        raise RuntimeError(f"create_chat HTTP {resp.status_code}: {resp.text[:180]}")
    data = resp.json()
    chat_id = ((data.get("data") or {}).get("id") or "").strip()
    if not data.get("success") or not chat_id:
        raise RuntimeError(f"create_chat invalid response: {json.dumps(data)[:220]}")
    return chat_id


def upload_image_oss(token: str, image_path: str, cookie_header: str = "", session_meta=None) -> dict:
    fname = os.path.basename(image_path)
    fsize = os.path.getsize(image_path)
    mime, _ = mimetypes.guess_type(image_path)
    mime = mime or "image/png"
    sts_resp = qwen_post(
        QWEN_STS_TOKEN_URL,
        headers=qwen_headers(token, cookie_header, session_meta),
        json={"filename": fname, "filesize": fsize, "filetype": "image"},
        timeout=25,
    )
    if sts_resp.status_code != 200:
        raise RuntimeError(f"STS HTTP {sts_resp.status_code}: {sts_resp.text[:180]}")
    sts_data = sts_resp.json()
    if not sts_data.get("success"):
        raise RuntimeError(f"STS failed: {json.dumps(sts_data)[:220]}")
    data = sts_data.get("data") or {}
    file_url = data.get("file_url") or ""
    file_id = data.get("file_id") or str(uuid.uuid4())
    file_path_oss = data.get("file_path") or ""
    if not file_path_oss:
        raise RuntimeError("STS sin file_path")
    if not file_url:
        oss_key = data.get("oss_key", "")
        bucket_url = data.get("bucket_url", "https://qwen-webui-prod.oss-accelerate.aliyuncs.com")
        file_url = f"{bucket_url}/{oss_key}" if oss_key else ""
    if not file_url:
        raise RuntimeError("STS sin file_url")

    try:
        import oss2
    except Exception as exc:
        raise RuntimeError("Falta dependencia oss2 (pip install oss2)") from exc

    with open(image_path, "rb") as f:
        img_bytes = f.read()
    auth = oss2.StsAuth(
        data.get("access_key_id", ""), data.get("access_key_secret", ""), data.get("security_token", "")
    )
    endpoint = f"https://{data.get('endpoint', 'oss-accelerate.aliyuncs.com')}"
    bucket = oss2.Bucket(auth, endpoint, data.get("bucketname", "qwen-webui-prod"))
    put = bucket.put_object(file_path_oss, img_bytes, headers={"Content-Type": mime})
    if put.status not in (200, 201):
        raise RuntimeError(f"OSS upload HTTP {put.status}")

    ts_now = int(time.time() * 1000)
    uid = file_path_oss.split("/")[0] if "/" in file_path_oss else ""
    return {
        "type": "image",
        "file": {
            "created_at": ts_now,
            "data": {},
            "filename": fname,
            "hash": None,
            "id": file_id,
            "user_id": uid,
            "meta": {"name": fname, "size": fsize, "content_type": mime},
            "update_at": ts_now,
        },
        "id": file_id,
        "url": file_url,
        "name": fname,
        "collection_name": "",
        "progress": 0,
        "status": "uploaded",
        "size": fsize,
        "error": "",
        "itemId": str(uuid.uuid4()),
        "file_type": mime,
        "showType": "image",
        "file_class": "vision",
        "uploadTaskId": str(uuid.uuid4()),
    }


def submit_completion(
    token: str,
    chat_id: str,
    prompt: str,
    chat_type: str = "i2v",
    size: str = "16:9",
    files=None,
    cookie_header: str = "",
    session_meta=None,
) -> str:
    url = f"{QWEN_CHAT_COMPLETIONS_URL}?chat_id={chat_id}"
    ts = int(time.time())
    msg = {
        "fid": str(uuid.uuid4()),
        "parentId": None,
        "childrenIds": [str(uuid.uuid4())],
        "role": "user",
        "content": prompt,
        "user_action": "chat",
        "files": files or [],
        "timestamp": ts,
        "models": [QWEN_MODEL_T2V],
        "chat_type": chat_type,
        "feature_config": {
            "thinking_enabled": False,
            "output_schema": "phase",
            "research_mode": "normal",
            "auto_thinking": False,
            "thinking_mode": "Fast",
            "auto_search": True,
        },
        "extra": {"meta": {"subChatType": chat_type, "size": size}},
        "sub_chat_type": chat_type,
        "parent_id": None,
    }
    model = QWEN_MODEL_T2V if chat_type == "t2v" else QWEN_MODEL_I2V
    payload = {
        "stream": False,
        "version": "2.1",
        "incremental_output": True,
        "chat_id": chat_id,
        "chat_mode": "normal",
        "model": model,
        "parent_id": None,
        "messages": [msg],
        "timestamp": ts,
        "size": size,
    }
    h = qwen_headers(token, cookie_header, session_meta)
    h["X-Request-Id"] = str(uuid.uuid4())
    resp = qwen_post(url, headers=h, json=payload, timeout=40)
    if resp.status_code == 401:
        raise RuntimeError("Token invalido/expirado")
    if resp.status_code != 200:
        raise RuntimeError(f"completion HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if not data.get("success"):
        d = data.get("data") or {}
        code = (d.get("code") or "").lower()
        details = d.get("details") or data.get("message") or data.get("error") or "error"
        raise RuntimeError(f"{code}: {details}")
    for m in (data.get("data") or {}).get("messages", []):
        task_id = (((m.get("extra") or {}).get("wanx") or {}).get("task_id") or "").strip()
        if task_id:
            return task_id
    raise RuntimeError("completion sin task_id")


def poll_task(
    token: str,
    task_id: str,
    timeout_sec: int = 600,
    poll_interval: int = 5,
    cookie_header: str = "",
    session_meta=None,
) -> dict:
    url = QWEN_TASK_STATUS_URL.format(task_id=task_id)
    started = time.time()
    time.sleep(15)
    while time.time() - started < timeout_sec:
        resp = qwen_get(url, headers=qwen_headers(token, cookie_header, session_meta), timeout=20)
        if resp.status_code == 401:
            return {"ok": False, "error": "Token expirado (401)"}
        if resp.status_code != 200:
            time.sleep(poll_interval)
            continue
        data = resp.json()
        st = (data.get("task_status") or "").lower()
        if st == "success":
            vu = (data.get("content") or "").strip()
            return {"ok": True, "video_url": vu} if vu else {"ok": False, "error": "Task completado sin URL"}
        if st in ("failed", "error"):
            return {"ok": False, "error": data.get("message") or "Generacion fallida"}
        time.sleep(poll_interval)
    return {"ok": False, "error": f"Timeout ({timeout_sec}s)"}


def download_video(video_url: str, output_path: str) -> str:
    resp = qwen_get(video_url, timeout=180)
    if resp.status_code != 200:
        raise RuntimeError(f"download HTTP {resp.status_code}")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)
    return output_path


def generate_one(
    token: str,
    image_path: str,
    prompt: str,
    size: str,
    output_path: str,
    timeout_sec: int = 600,
    cookie_header: str = "",
    session_meta=None,
) -> str:
    file_obj = upload_image_oss(token, image_path, cookie_header, session_meta)
    chat_id = create_chat(token, "i2v", cookie_header, session_meta)
    aspect = QWEN_SIZE_MAP.get(size, "16:9")
    task_id = submit_completion(
        token, chat_id, prompt, "i2v", aspect, [file_obj], cookie_header, session_meta
    )
    result = poll_task(token, task_id, timeout_sec, 5, cookie_header, session_meta)
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "Task error")
    download_video(result["video_url"], output_path)
    return task_id


# ─────────────────────────────────────────────────────────────────
# Login interactivo (Playwright, captura token Bearer + cookies)
# ─────────────────────────────────────────────────────────────────


def _norm_token(raw) -> str:
    t = str(raw or "").strip().strip('"').strip("'")
    if t.lower().startswith("bearer "):
        t = t.split(" ", 1)[1].strip()
    return t


def _is_token_like(raw) -> bool:
    t = _norm_token(raw)
    if len(t) < 30:
        return False
    if "." in t and len(t.split(".")) >= 2:
        return True
    return len(t) >= 48


def login_account_managed(folder: Path, log_callback=None) -> None:
    """Login interactivo con perfil temporal; captura token Bearer + cookies + session meta."""

    def log(msg: str):
        if log_callback:
            log_callback(msg)

    import shutil
    import tempfile

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log(f"[ERROR] [{folder.name}] Playwright no instalado.")
        return

    tmp_profile = Path(tempfile.gettempdir()) / f"qwen_tmp_{folder.name}"
    try:
        if tmp_profile.exists():
            shutil.rmtree(tmp_profile)
        tmp_profile.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as pw:
            exe = find_chromium_exe()
            ctx = pw.chromium.launch_persistent_context(
                str(tmp_profile),
                headless=False,
                executable_path=exe,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--no-first-run"],
                viewport={"width": 1280, "height": 900},
                ignore_https_errors=True,
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            token_box = {"token": ""}
            session_meta_capture: dict = {}

            def on_req(req):
                h = req.headers or {}
                auth = h.get("authorization") or h.get("Authorization") or ""
                if _is_token_like(auth):
                    token_box["token"] = _norm_token(auth)
                sid = h.get("x-statsig-id") or h.get("X-Statsig-Id") or ""
                if sid and not session_meta_capture.get("x_statsig_id"):
                    session_meta_capture["x_statsig_id"] = sid.strip()
                bag = h.get("baggage") or ""
                if bag and not session_meta_capture.get("baggage"):
                    session_meta_capture["baggage"] = bag.strip()
                st = h.get("sentry-trace") or h.get("Sentry-Trace") or ""
                if st and not session_meta_capture.get("sentry_trace"):
                    session_meta_capture["sentry_trace"] = st.strip()

            def on_resp(resp):
                try:
                    txt = resp.text() or ""
                except Exception:
                    txt = ""
                if not txt or len(txt) > 150000:
                    return
                m = re.search(
                    r'"(?:access_?token|accessToken|id_?token|token)"\s*:\s*"([^"]{30,})"', txt, re.I
                )
                if m and _is_token_like(m.group(1)):
                    token_box["token"] = _norm_token(m.group(1))

            def save_cookies_snapshot() -> int:
                try:
                    cookies = ctx.cookies("https://chat.qwen.ai")
                except Exception:
                    cookies = []
                if not cookies:
                    return 0
                cookie_list = [
                    {
                        "name": c.get("name", ""),
                        "value": c.get("value", ""),
                        "domain": c.get("domain", ".chat.qwen.ai"),
                        "path": c.get("path", "/"),
                        "httpOnly": bool(c.get("httpOnly", False)),
                        "secure": bool(c.get("secure", True)),
                    }
                    for c in cookies
                ]
                (folder / "cookies_auto.json").write_text(json.dumps(cookie_list, indent=2), encoding="utf-8")
                for c in cookie_list:
                    n = str(c.get("name", "")).lower()
                    v = str(c.get("value", ""))
                    if any(k in n for k in ("token", "auth", "session", "jwt", "access")) and _is_token_like(
                        v
                    ):
                        token_box["token"] = _norm_token(v)
                        break
                return len(cookie_list)

            page.on("request", on_req)
            ctx.on("request", on_req)
            page.on("response", on_resp)
            ctx.on("response", on_resp)
            try:
                page.goto("https://chat.qwen.ai/", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass

            deadline = time.time() + 360
            saved = False
            last_invalid_token = ""
            storage_js = (
                "() => { const r=[]; "
                "for (let i=0;i<localStorage.length;i++){const k=localStorage.key(i); r.push([k, localStorage.getItem(k)]);} "
                "for (let i=0;i<sessionStorage.length;i++){const k=sessionStorage.key(i); r.push([k, sessionStorage.getItem(k)]);} "
                "return r; }"
            )
            while time.time() < deadline:
                tk = _norm_token(token_box.get("token") or "")
                if not tk:
                    try:
                        tk = _extract_token_from_storage_entries(page.evaluate(storage_js) or [])
                    except Exception:
                        pass
                ccount = save_cookies_snapshot()
                if tk:
                    ok, detail = test_token(tk)
                    if ok:
                        (folder / "token.txt").write_text(tk, encoding="utf-8")
                        if session_meta_capture:
                            (folder / "session_meta.json").write_text(
                                json.dumps(session_meta_capture, indent=2), encoding="utf-8"
                            )
                        log(f"[OK] [{folder.name}] Sesion guardada (token + {ccount} cookies).")
                        saved = True
                        break
                    elif tk != last_invalid_token:
                        last_invalid_token = tk
                        log(
                            f"[{folder.name}] Token detectado pero aun no valido ({detail}). Esperando login completo..."
                        )
                time.sleep(2)

            if not saved:
                try:
                    save_cookies_snapshot()
                    tk2 = _extract_token_from_storage_entries(page.evaluate(storage_js) or [])
                    if tk2 and test_token(tk2)[0]:
                        (folder / "token.txt").write_text(tk2, encoding="utf-8")
                        if session_meta_capture:
                            (folder / "session_meta.json").write_text(
                                json.dumps(session_meta_capture, indent=2), encoding="utf-8"
                            )
                        log(f"[OK] [{folder.name}] Sesion guardada al cierre (token + cookies).")
                        saved = True
                except Exception:
                    pass

            try:
                ctx.close()
            except Exception:
                pass
            if not saved:
                log(
                    f"[WARNING] [{folder.name}] Browser cerrado sin token valido. Cookies guardadas si estuvieron disponibles."
                )
    except Exception as exc:
        log(f"[ERROR] [{folder.name}] Error: {exc}")
    finally:
        try:
            shutil.rmtree(tmp_profile, ignore_errors=True)
        except Exception:
            pass
