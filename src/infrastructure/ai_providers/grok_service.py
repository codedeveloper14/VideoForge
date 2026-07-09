import base64
import json
import mimetypes
import random
import sys
import time
import uuid
from pathlib import Path

import requests

from src.infrastructure.ai_providers.chrome_launcher import find_chromium_exe
from src.utils.logger import get_logger

logger = get_logger(__name__)

GROK_BASE = "https://grok.com"
UPLOAD_URL = f"{GROK_BASE}/rest/app-chat/upload-file"
CONV_URL = f"{GROK_BASE}/rest/app-chat/conversations/new"
ASSET_BASE = "https://assets.grok.com"

SLOTS_MAX = 12


def http_browser_fingerprint() -> dict:
    """Mismo fingerprint que un Chrome 124 real; debe coincidir con el SO para evitar anti-bot."""
    if sys.platform == "win32":
        return {
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "sec_ch_ua_platform": '"Windows"',
        }
    if sys.platform == "darwin":
        return {
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "sec_ch_ua_platform": '"macOS"',
        }
    return {
        "user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua_platform": '"Linux"',
    }


def _creation_time(path: Path) -> float:
    """Fecha de creacion real (macOS: st_birthtime; Linux/Win: st_mtime)."""
    st = path.stat()
    return getattr(st, "st_birthtime", None) or st.st_mtime


def get_images(source: str) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    p = Path(source)
    if p.is_dir():
        imgs = [f for f in p.iterdir() if f.suffix.lower() in exts]
    elif p.is_file():
        imgs = [p]
    else:
        imgs = []
    if not imgs:
        logger.error("No se encontraron imagenes en %s", source)
        return []

    imgs.sort(key=_creation_time)
    logger.info("%d imagen(es) - orden por fecha de creacion", len(imgs))
    return imgs


def _rid() -> str:
    return str(uuid.uuid4())


def _hdrs(ref: str = f"{GROK_BASE}/imagine", session_meta: dict | None = None) -> dict:
    meta = session_meta or {}
    trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]
    sample_rand = round(random.uniform(0.1, 0.99), 17)
    sentry_rel = meta.get("sentry_release", "78c3d15bba7fcf5626222ce6e26baf5c0705b262")
    statsig_id = meta.get("statsig_id", "")
    fp = http_browser_fingerprint()
    h = {
        "accept": "*/*",
        "accept-language": "es-CO,es;q=0.9,ko;q=0.8,de;q=0.7,ru;q=0.6",
        "origin": GROK_BASE,
        "referer": ref,
        "priority": "u=1, i",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": fp["sec_ch_ua_platform"],
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": fp["user_agent"],
        "sentry-trace": f"{trace_id}-{span_id}-0",
        "baggage": (
            f"sentry-environment=production,"
            f"sentry-release={sentry_rel},"
            f"sentry-public_key=b311e0f2690c81f25e2c4cf6d4f7ce1c,"
            f"sentry-trace_id={trace_id},"
            f"sentry-org_id=4508179396558848,"
            f"sentry-sampled=false,"
            f"sentry-sample_rand={sample_rand},"
            f"sentry-sample_rate=0"
        ),
        "traceparent": f"00-{uuid.uuid4().hex}-{uuid.uuid4().hex[:16]}-00",
        "x-xai-request-id": _rid(),
    }
    if statsig_id:
        h["x-statsig-id"] = statsig_id
    return h


def _resolve(raw: str) -> str:
    return raw if raw.startswith("http") else f"{ASSET_BASE}/{raw.lstrip('/')}"


def _deep(obj, depth: int = 0):
    if depth > 6:
        return None
    if (
        isinstance(obj, str)
        and obj.startswith("http")
        and any(x in obj for x in [".mp4", ".webm", "vidgen", "video"])
    ):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            found = _deep(v, depth + 1)
            if found:
                return found
    if isinstance(obj, list):
        for item in obj:
            found = _deep(item, depth + 1)
            if found:
                return found
    return None


class GrokAccountClient:
    """Cada slot usa su propia instancia (requests.Session no es thread-safe)."""

    def __init__(
        self,
        account_name,
        slot_id,
        cookies_dict,
        session_meta,
        prompt,
        aspect_ratio,
        video_length,
        resolution,
        sse_dump_dir: Path,
    ):
        self.label = f"{account_name}-s{slot_id}"
        self.prompt = prompt
        self.aspect_ratio = aspect_ratio
        self.video_length = video_length
        self.resolution = resolution
        self.session_meta = session_meta or {}
        self.cookies_dict = dict(cookies_dict)
        self.sse_dump_dir = sse_dump_dir
        self.session = requests.Session()
        for name, value in self.cookies_dict.items():
            self.session.cookies.set(name, value, domain=".grok.com")

    def _upload(self, image_path: Path):
        mime, _ = mimetypes.guess_type(str(image_path))
        mime = mime or "image/jpeg"
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        payload = {
            "fileName": image_path.name,
            "fileMimeType": mime,
            "content": b64,
            "fileSource": "IMAGINE_SELF_UPLOAD_FILE_SOURCE",
        }
        logger.info("[%s] [1/3] Subiendo %s...", self.label, image_path.name)
        for attempt in range(2):
            try:
                hdrs = {**_hdrs(session_meta=self.session_meta), "content-type": "application/json"}
                r = self.session.post(UPLOAD_URL, json=payload, headers=hdrs, timeout=60)
                if r.status_code in (401, 403) and attempt == 0:
                    logger.warning("[%s] %s upload", self.label, r.status_code)
                    continue
                if not r.ok:
                    logger.error("[%s] Upload %s: %s", self.label, r.status_code, r.text[:200])
                    return None, None
                data = r.json()
                fid = (
                    data.get("fileMetadataId")
                    or data.get("fileId")
                    or data.get("id")
                    or data.get("attachmentId")
                )
                furi = data.get("fileUri", "")
                uid = self.session.cookies.get("x-userid", "x")
                aurl = (
                    f"{ASSET_BASE}/{furi}"
                    if furi
                    else data.get("url") or data.get("assetUrl") or f"{ASSET_BASE}/users/{uid}/{fid}/content"
                )
                logger.info("[%s] fileId=%s", self.label, fid)
                return fid, aurl
            except Exception as exc:
                logger.error("[%s] Upload err: %s", self.label, exc)
                return None, None
        return None, None

    def _build_payload(self, fid, aurl):
        return {
            "temporary": True,
            "modelName": "grok-3",
            "message": f"{aurl} {self.prompt} --mode=custom",
            "fileAttachments": [fid],
            "toolOverrides": {"videoGen": True},
            "enableSideBySide": False,
            "responseMetadata": {"experiments": [], "modelConfigOverride": {"modelMap": {}}},
        }

    def _parse_sse(self, response):
        video_url = None
        conv_id = None
        video_id = None
        lines = []
        uid = self.session.cookies.get("x-userid", "")
        for raw in response.iter_lines(decode_unicode=True):
            lines.append(raw or "")
            if not raw:
                continue
            payload = raw[5:].strip() if raw.startswith("data:") else raw.strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                data = json.loads(payload)
            except Exception:
                continue
            result = data.get("result", {})
            if not conv_id:
                conv = result.get("conversation", {})
                conv_id = conv.get("conversationId") or result.get("conversationId") or result.get("id")
            resp = result.get("response", {})
            svgr = resp.get("streamingVideoGenerationResponse")
            if svgr:
                prog = svgr.get("progress", 0)
                rv = svgr.get("videoUrl", "")
                logger.info("[%s] %s%%", self.label, prog)
                vid = svgr.get("videoId") or svgr.get("videoPostId") or svgr.get("postId")
                if vid and not video_id:
                    video_id = vid
                    logger.info("[%s] videoId=%s", self.label, video_id)
                if rv:
                    video_url = _resolve(rv)
                if prog == 100 and rv:
                    logger.info("[%s] [OK] 100%% url=%s", self.label, video_url)
                    break
            for media in resp.get("generatedMedia") or result.get("generatedMedia") or []:
                ru = media.get("url") or media.get("videoUrl") or media.get("mediaUrl") or ""
                mt = (media.get("mediaType") or "").lower()
                if ru:
                    u = _resolve(ru)
                    if "video" in mt or ru.endswith((".mp4", ".webm")):
                        video_url = u
                        break
        (self.sse_dump_dir / f"sse_dump_{self.label}.txt").write_text("\n".join(lines))
        logger.info("[%s] SSE fin - conv=%s vid=%s url=%s", self.label, conv_id, video_id, video_url)
        if video_url:
            return video_url
        if video_id and uid:
            url = f"{ASSET_BASE}/users/{uid}/generated/{video_id}/generated_video.mp4?cache=1"
            logger.info("[%s] URL construida: %s", self.label, url)
            return url
        if conv_id:
            logger.info("[%s] Polleando %s...", self.label, conv_id)
            return self._poll(conv_id)
        return None

    def _poll(self, conv_id):
        url = f"{GROK_BASE}/rest/app-chat/conversations/{conv_id}/responses"
        deadline = time.time() + 600
        while time.time() < deadline:
            try:
                r = self.session.get(url, headers=_hdrs(session_meta=self.session_meta), timeout=30)
                if r.ok:
                    found = _deep(r.json())
                    if found:
                        return found
            except Exception as exc:
                logger.warning("[%s] Poll: %s", self.label, exc)
            time.sleep(6)
        logger.error("[%s] Poll timeout.", self.label)
        return None

    def animate(self, image_path: Path):
        fid, aurl = self._upload(image_path)
        if not fid:
            return None
        payload = self._build_payload(fid, aurl)
        logger.info("[%s] [2/3] Generando video...", self.label)
        for attempt in range(2):
            try:
                hdrs = {**_hdrs(session_meta=self.session_meta), "content-type": "application/json"}
                r = self.session.post(CONV_URL, json=payload, headers=hdrs, timeout=30, stream=True)
                if r.status_code in (401, 403) and attempt == 0:
                    logger.warning("[%s] %s", self.label, r.status_code)
                    continue
                if not r.ok:
                    logger.error("[%s] Conv %s: %s", self.label, r.status_code, r.text[:200])
                    return None
                logger.info("[%s] [3/3] Esperando SSE...", self.label)
                return self._parse_sse(r)
            except Exception as exc:
                logger.error("[%s] Animate: %s", self.label, exc)
                return None
        return None

    def download(self, url: str, dest: Path, pending_file: Path) -> bool:
        """Espera 15s (CDN) + retry cada 20s hasta 10 min."""
        hdrs = _hdrs(session_meta=self.session_meta)
        hdrs["referer"] = "https://grok.com/"
        logger.info("[%s] Descargando --> %s (15s CDN...)", self.label, dest.name)
        time.sleep(15)
        deadline = time.time() + 600
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            try:
                with self.session.get(url, stream=True, timeout=180, headers=hdrs) as r:
                    if r.status_code == 404:
                        logger.info("[%s] CDN 404 intento %d - 20s...", self.label, attempt)
                        time.sleep(20)
                        continue
                    r.raise_for_status()
                    with open(dest, "wb") as f:
                        for chunk in r.iter_content(65536):
                            f.write(chunk)
                    logger.info(
                        "[%s] [OK] %s (%dKB) intento %d",
                        self.label,
                        dest.name,
                        dest.stat().st_size // 1024,
                        attempt,
                    )
                    return True
            except requests.exceptions.HTTPError as exc:
                code = exc.response.status_code if exc.response else "?"
                logger.warning("[%s] HTTP %s intento %d", self.label, code, attempt)
                time.sleep(20)
            except Exception as exc:
                logger.warning("[%s] DL err %d: %s", self.label, attempt, exc)
                time.sleep(20)
        logger.error("[%s] [ERROR] Timeout descarga: %s", self.label, url)
        with pending_file.open("a") as f:
            f.write(url + "\n")
        return False


def login_account(folder: Path) -> bool:
    """Abre un browser (Playwright) para que el usuario inicie sesion y captura las cookies."""
    from playwright.sync_api import sync_playwright

    profile_dir = folder / "chromium_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    captured: dict = {}
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 800},
            locale="es-CO",
            timezone_id="America/Bogota",
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.add_init_script(
            """
            Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
            Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
            window.chrome={runtime:{},loadTimes:function(){},csi:function(){},app:{}};
        """
        )

        def on_req(req):
            h = req.headers
            sid = h.get("x-statsig-id", "")
            if sid and not captured.get("statsig_id"):
                captured["statsig_id"] = sid
                logger.info("[%s] statsig_id [OK]", folder.name)
            bag = h.get("baggage", "")
            if "sentry-release=" in bag and not captured.get("sentry_release"):
                for part in bag.split(","):
                    if part.strip().startswith("sentry-release="):
                        captured["sentry_release"] = part.split("=", 1)[1].strip()

        page.on("request", on_req)
        page.goto(f"{GROK_BASE}/imagine", timeout=60000)
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        logger.info("[%s] *** Inicia sesion en el browser *** (max 3 min)", folder.name)
        for _ in range(180):
            ck = {c["name"]: c["value"] for c in ctx.cookies("https://grok.com")}
            if ck.get("sso"):
                logger.info("[%s] [OK] Login OK", folder.name)
                break
            time.sleep(1)
        else:
            logger.error("[%s] Timeout login", folder.name)
            ctx.close()
            return False
        time.sleep(3)
        try:
            page.reload()
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(2)
        raw = ctx.cookies("https://grok.com")
        ctx.close()

    clist = [
        {
            "name": c["name"],
            "value": c["value"],
            "domain": ".grok.com",
            "path": "/",
            "httpOnly": False,
            "secure": True,
        }
        for c in raw
    ]
    (folder / "cookies_auto.json").write_text(json.dumps(clist, indent=2))
    (folder / "session_meta.json").write_text(json.dumps(captured, indent=2))
    logger.info("[%s] Cookies y meta guardados [OK]", folder.name)
    return True


def make_clients(
    folder: Path,
    slots: int,
    prompt: str,
    aspect_ratio: str,
    video_length: int,
    resolution: str,
    sse_dump_dir: Path,
) -> list[GrokAccountClient]:
    """Devuelve `slots` instancias independientes (una session cada una)."""
    cookies_file = folder / "cookies_auto.json"
    meta_file = folder / "session_meta.json"
    if not cookies_file.exists():
        logger.warning("[%s] Sin cookies_auto.json - omitiendo", folder.name)
        return []
    cookies = {c["name"]: c["value"] for c in json.loads(cookies_file.read_text()) if "name" in c}
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    clients = [
        GrokAccountClient(
            folder.name, i, cookies, meta, prompt, aspect_ratio, video_length, resolution, sse_dump_dir
        )
        for i in range(1, slots + 1)
    ]
    logger.info(
        "[%s] %d slot(s) - statsig=%s", folder.name, slots, "[OK]" if meta.get("statsig_id") else "[ERROR]"
    )
    return clients


# ─────────────────────────────────────────────────────────────────
# Gestion de cuentas/sesiones (usado por la UI "Sesiones")
# ─────────────────────────────────────────────────────────────────


def account_dir(accounts_dir: Path, name: str) -> Path:
    """Sanitiza el nombre de cuenta para que no pueda escapar accounts_dir."""
    import re

    safe = re.sub(r"[^\w\-]", "_", (name or "").strip())[:60]
    return accounts_dir / safe


def ensure_accounts_setup(accounts_dir: Path, count: int = 10) -> None:
    """Garantiza accounts_dir/account_1..account_N y un README."""
    accounts_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, count + 1):
        (accounts_dir / f"account_{i}").mkdir(parents=True, exist_ok=True)
    readme = accounts_dir / "README.txt"
    if not readme.exists():
        readme.write_text(
            "Carpetas de cuentas para Grok.\n"
            "1) Abre 'Sesiones' en la app.\n"
            "2) Inicia sesion en cada cuenta (account_1, account_2, ...).\n"
            "3) El sistema guarda cookies en cookies_auto.json dentro de cada carpeta.\n",
            encoding="utf-8",
        )


def list_account_sessions(accounts_dir: Path) -> list[dict]:
    result = []
    for folder in sorted(accounts_dir.iterdir()):
        if not folder.is_dir():
            continue
        ck_file = folder / "cookies_auto.json"
        active = False
        user = ""
        if ck_file.exists():
            try:
                cookies = json.loads(ck_file.read_text())
                ck_dict = {c["name"]: c["value"] for c in cookies if isinstance(c, dict)}
                active = bool(ck_dict.get("sso"))
                uid_cookie = ck_dict.get("x-userid", "")
                user = uid_cookie[:20] if uid_cookie else (f"{len(cookies)} ck" if active else "sin sesion")
            except Exception:
                active = ck_file.stat().st_size > 50
        result.append({"name": folder.name, "active": active, "user": user, "has_cookies": ck_file.exists()})
    return result


def delete_account_session(accounts_dir: Path, account_name: str) -> None:
    ck_file = account_dir(accounts_dir, account_name) / "cookies_auto.json"
    if ck_file.exists():
        ck_file.unlink()


def _valid_statsig_id(sid) -> bool:
    if not sid or not isinstance(sid, str):
        return False
    sid = sid.strip()
    if len(sid) < 8 or len(sid) > 256:
        return False
    bad_markers = (
        "error",
        "undefined",
        "typeerror",
        "exception",
        "cannot read",
        "null",
        "nan",
        "syntaxerror",
    )
    return not any(bad in sid.lower() for bad in bad_markers)


def _valid_sentry_release(release) -> bool:
    if not release or not isinstance(release, str):
        return False
    release = release.strip()
    if len(release) < 8 or len(release) > 64:
        return False
    return all(c in "0123456789abcdefABCDEF" for c in release)


def login_account_managed(folder: Path, folder_name: str) -> tuple[bool, str]:
    """Login interactivo con perfil temporal (usado por la UI HTTP 'Sesiones').

    A diferencia de login_account() (perfil persistente, usado por el CLI de
    scripts/grok_worker.py), este usa un perfil temporal limpio en cada intento
    y valida mas estrictamente los tokens statsig/sentry capturados.
    """
    import shutil
    import tempfile

    from playwright.sync_api import sync_playwright

    temp_profile = Path(tempfile.gettempdir()) / f"grok_tmp_{folder_name}"
    if temp_profile.exists():
        shutil.rmtree(temp_profile)
    temp_profile.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as pw:
            exe = find_chromium_exe()

            ctx = pw.chromium.launch_persistent_context(
                str(temp_profile),
                headless=False,
                executable_path=exe,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--no-first-run"],
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            session_meta_capture: dict = {}

            def on_req(req):
                h = req.headers
                sid = h.get("x-statsig-id", "")
                if sid and _valid_statsig_id(sid) and not session_meta_capture.get("statsig_id"):
                    session_meta_capture["statsig_id"] = sid.strip()
                bag = h.get("baggage", "")
                if "sentry-release=" in bag and not session_meta_capture.get("sentry_release"):
                    for part in bag.split(","):
                        if part.strip().startswith("sentry-release="):
                            rel = part.split("=", 1)[1].strip()
                            if _valid_sentry_release(rel):
                                session_meta_capture["sentry_release"] = rel

            page.on("request", on_req)

            try:
                page.goto("https://grok.com/imagine", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass

            saved = False
            deadline = time.time() + 300
            while time.time() < deadline:
                try:
                    cookies = ctx.cookies("https://grok.com")
                except Exception:
                    break
                ck_dict = {c["name"]: c["value"] for c in cookies}
                if ck_dict.get("sso"):
                    cookie_list = [
                        {
                            "name": c["name"],
                            "value": c["value"],
                            "domain": ".grok.com",
                            "path": "/",
                            "httpOnly": c.get("httpOnly", False),
                            "secure": c.get("secure", True),
                        }
                        for c in cookies
                    ]
                    (folder / "cookies_auto.json").write_text(json.dumps(cookie_list, indent=2))
                    meta_file = folder / "session_meta.json"
                    if session_meta_capture:
                        meta_file.write_text(json.dumps(session_meta_capture, indent=2))
                    elif meta_file.exists():
                        meta_file.unlink()
                    saved = True
                    time.sleep(1)
                    try:
                        ctx.close()
                    except Exception:
                        pass
                    return True, (
                        f"[OK] [{folder_name}] Sesion guardada (sso={ck_dict['sso'][:12]}... | "
                        f"{len(cookies)} cookies{' | session_meta OK' if session_meta_capture else ''})."
                    )
                time.sleep(2)

            if not saved:
                try:
                    ctx.close()
                except Exception:
                    pass
                return (
                    False,
                    f"[WARNING] [{folder_name}] Browser cerrado sin guardar sesion (cookie 'sso' no detectada).",
                )
    except ImportError:
        return False, f"[ERROR] [{folder_name}] Playwright no instalado."
    except Exception as exc:
        return False, f"[ERROR] [{folder_name}] Error: {exc}"
    finally:
        try:
            shutil.rmtree(temp_profile, ignore_errors=True)
        except Exception:
            pass
