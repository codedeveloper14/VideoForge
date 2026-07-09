import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

import requests

from src.infrastructure.ai_providers import meta_accounts
from src.infrastructure.ai_providers.chrome_launcher import find_chromium_exe
from src.infrastructure.ai_providers.meta_gql_client import META_BASE, META_UA
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _NoOpLog(msg: str) -> None:
    pass


def _sanitize_vars(obj, prompt_val):
    if isinstance(obj, dict):
        return {k: _sanitize_vars(v, prompt_val) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_vars(v, prompt_val) for v in obj]
    if isinstance(obj, str):
        if prompt_val and obj == prompt_val:
            return "__PROMPT__"
        if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", obj, re.I):
            return "__CONV_ID__"
    return obj


def generate_playwright_intercept(
    browser,
    acct_folder: Path,
    cookie_list: list,
    api_state: dict,
    prompt: str,
    image_path: str | None = None,
    out_path: str | None = None,
    timeout_sec: int = 300,
    slot_id: int = 0,
    log: Callable[[str], None] = _NoOpLog,
) -> dict:
    """Generacion via Playwright con interceptacion completa de requests.

    Captura: OAuth token, generation doc_id, variables template -> se guardan
    en api_state.json para las siguientes llamadas 100% HTTP ("learn once,
    HTTP forever"). Devuelve el mismo shape que meta_gql_client.generate_http.
    """
    result = {"url": None, "saved": False, "error": None}
    video_candidates: list[str] = []
    collecting = [False]
    submitted = [False]
    ctx = None

    captured_oauth = [api_state.get("oauth_token", "")]
    captured_gen_doc = [api_state.get("gen_doc_id", "")]
    captured_gen_vars = [api_state.get("gen_variables_template", None)]
    all_post_log: list[str] = []

    def on_request(req):
        try:
            url = req.url
            hdrs = req.headers
            post_data = req.post_data or ""
            method = req.method or ""

            auth = hdrs.get("authorization", "")
            if "OAuth ecto1:" in auth and not captured_oauth[0]:
                captured_oauth[0] = auth.split("OAuth ecto1:", 1)[1].strip()
                log(f"[S{slot_id}] OAuth capturado ({captured_oauth[0][:16]}...)")

            if method == "POST" and "graphql" in url and post_data:
                try:
                    body = json.loads(post_data)
                    doc_id = body.get("doc_id", "")
                    variables = body.get("variables", {})
                    skip = {
                        "e7f802582dbfed8e181b012e010993eb",
                        "c32bbe999c48e64e855dc63177d5153f",
                        "344570a4b8110dd9848829731d35c74a",
                    }
                    if doc_id and doc_id not in skip and not captured_gen_doc[0]:
                        captured_gen_doc[0] = doc_id
                        captured_gen_vars[0] = _sanitize_vars(variables, prompt)
                        log(f"[S{slot_id}] Gen doc_id: {doc_id[:20]}...")
                except Exception:
                    pass

            if submitted[0] and method == "POST" and post_data:
                host = url.split("/")[2].lower() if url.startswith("http") else ""
                if "meta.ai" in host or "facebook.com" in host:
                    entry = f"{url[:70]} --> {post_data[:120]}"
                    if entry not in all_post_log:
                        all_post_log.append(entry)
                        log(f"[S{slot_id}] {entry[:140]}")
        except Exception:
            pass

    def on_response(resp):
        if not collecting[0]:
            return
        try:
            ct = resp.headers.get("content-type", "")
            url = resp.url
            host = url.split("/")[2].lower() if url.startswith("http") else ""
            if (
                (
                    "video/mp4" in ct
                    or "video/webm" in ct
                    or ".mp4" in url
                    or ".webm" in url
                    or (host.startswith("video-") and "fbcdn.net" in host)
                )
                and url.startswith("http")
                and url not in video_candidates
            ):
                video_candidates.append(url)
                log(f"[S{slot_id}] {url[:90]}...")
        except Exception:
            pass

    try:
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900}, ignore_https_errors=True, user_agent=META_UA
        )
        if cookie_list:
            try:
                ctx.add_cookies(cookie_list)
            except Exception as exc:
                log(f"[S{slot_id}] [WARNING] Cookies: {exc}")

        page = ctx.new_page()
        page.on("request", on_request)
        page.on("response", on_response)

        log(f"[S{slot_id}] Iniciando (captura API)...")
        try:
            page.goto(f"{META_BASE}/create", timeout=30000, wait_until="domcontentloaded")
            time.sleep(1.5)
        except Exception as exc:
            log(f"[S{slot_id}] [WARNING] Carga: {exc}")

        if image_path and Path(image_path).is_file():
            try:
                file_input = page.query_selector("input[type='file']")
                if not file_input:
                    for sel in (
                        "button[aria-label*='ttach']",
                        "button[aria-label*='mage']",
                        "div[role='button'][aria-label*='ttach']",
                        "[data-testid*='attach']",
                    ):
                        try:
                            btn = page.query_selector(sel)
                            if btn:
                                btn.click()
                                time.sleep(0.3)
                                break
                        except Exception:
                            continue
                    file_input = page.query_selector("input[type='file']")
                if file_input:
                    file_input.set_input_files(image_path)
                    time.sleep(0.7)
                    log(f"[S{slot_id}] {Path(image_path).name}")
                else:
                    log(f"[S{slot_id}] [WARNING] Sin input archivo.")
            except Exception as exc:
                log(f"[S{slot_id}] [WARNING] Adjuntar: {exc}")

        typed = False
        for sel in (
            "div[contenteditable='true']",
            "div[role='textbox']",
            "textarea[placeholder]",
            "textarea",
            "input[type='text']",
        ):
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    time.sleep(0.1)
                    el.fill(prompt)
                    time.sleep(0.2)
                    typed = True
                    log(f"[S{slot_id}] {prompt[:60]}...")
                    break
            except Exception:
                continue

        if not typed:
            result["error"] = "Sin campo de texto - verifica sesion"
        else:
            sent = False
            submitted[0] = True
            for sel in (
                "button[aria-label*='end']",
                "button[type='submit']",
                "div[role='button'][aria-label*='end']",
                "[data-testid*='send']",
                "button[aria-label*='enerate']",
                "button[aria-label*='nimate']",
            ):
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_enabled():
                        btn.click()
                        sent = True
                        break
                except Exception:
                    continue
            if not sent:
                page.keyboard.press("Enter")

            collecting[0] = True
            log(f"[S{slot_id}] Generando (Playwright)...")
            deadline = time.time() + timeout_sec
            interval = 3
            while time.time() < deadline:
                time.sleep(interval)
                if video_candidates:
                    result["url"] = video_candidates[-1]
                    break
                try:
                    for v in page.query_selector_all("video[src]"):
                        src = v.get_attribute("src") or ""
                        if src.startswith("http") and src not in video_candidates:
                            video_candidates.append(src)
                            log(f"[S{slot_id}] DOM: {src[:80]}...")
                except Exception:
                    pass
                interval = min(interval + 2, 10)

            if not result["url"]:
                result["error"] = "Timeout: no se detecto video"

    except Exception as exc:
        result["error"] = f"Error: {exc}"
    finally:
        try:
            if ctx:
                ctx.close()
        except Exception:
            pass

    new_state = dict(api_state)
    if captured_oauth[0]:
        new_state["oauth_token"] = captured_oauth[0]
    if captured_gen_doc[0]:
        new_state["gen_doc_id"] = captured_gen_doc[0]
    if captured_gen_vars[0] is not None:
        new_state["gen_variables_template"] = captured_gen_vars[0]
    if new_state != api_state:
        meta_accounts.save_api_state(acct_folder, new_state)
        log(f"[S{slot_id}] api_state.json actualizado.")

    if result["error"] or not result["url"]:
        return result

    if out_path:
        log(f"[S{slot_id}] Descargando {Path(out_path).name}...")
        try:
            h = {"User-Agent": META_UA, "Accept": "*/*", "Referer": f"{META_BASE}/create"}
            r = requests.get(result["url"], headers=h, timeout=120, stream=True)
            r.raise_for_status()
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "wb") as fh:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)
            result["saved"] = True
            log(f"[S{slot_id}] [OK] {Path(out_path).name}")
        except Exception as exc:
            result["error"] = f"Error descarga: {exc}"

    return result


def login_account_managed(folder: Path, folder_name: str, log: Callable[[str], None] = _NoOpLog) -> None:
    """Login interactivo (perfil persistente) que intercepta headers Set-Cookie
    para capturar la cookie de sesion 'ecto_*' de meta.ai/facebook.com."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log(f"[ERROR] [{folder_name}] Playwright no instalado.")
        return

    tmp_profile = str(folder / "chromium_profile")
    Path(tmp_profile).mkdir(parents=True, exist_ok=True)

    intercepted: dict = {}

    def on_response(resp):
        try:
            sc = resp.headers.get("set-cookie", "")
            if not sc:
                return
            first_part = sc.split(";")[0].strip()
            if "=" not in first_part:
                return
            name, _, value = first_part.partition("=")
            name, value = name.strip(), value.strip()
            if name and name not in intercepted:
                try:
                    dom = urlparse(resp.url).hostname or ".meta.ai"
                    if not dom.startswith("."):
                        dom = "." + dom
                except Exception:
                    dom = ".meta.ai"
                intercepted[name] = {
                    "name": name,
                    "value": value,
                    "domain": dom,
                    "path": "/",
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "None",
                }
                if name in ("ecto", "datr", "ps_l", "ps_n"):
                    log(f"Cookie interceptada: {name}={value[:16]}... (dom={dom})")
        except Exception:
            pass

    try:
        with sync_playwright() as pw:
            exe = find_chromium_exe()

            ctx = pw.chromium.launch_persistent_context(
                tmp_profile,
                headless=False,
                executable_path=exe,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--no-first-run"],
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("response", on_response)
            ctx.on("response", on_response)

            log(f"[{folder_name}] Navegando a meta.ai...")
            try:
                page.goto("https://www.meta.ai/", timeout=30000)
                page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass

            meta_domains = [
                "https://www.meta.ai",
                "https://meta.ai",
                "https://auth.meta.ai",
                "https://auth.meta.com",
                "https://www.facebook.com",
                "https://facebook.com",
            ]

            def collect_all_cookies():
                pool = {}
                pool.update(intercepted)
                try:
                    for c in ctx.cookies():
                        pool.setdefault(c["name"], c)
                except Exception:
                    pass
                for dom in meta_domains:
                    try:
                        for c in ctx.cookies(dom):
                            pool.setdefault(c["name"], c)
                    except Exception:
                        pass
                return list(pool.values())

            saved = False
            deadline = time.time() + 300
            last_log_t = 0
            while time.time() < deadline:
                time.sleep(2)
                all_cookies = collect_all_cookies()
                now = time.time()
                if now - last_log_t > 15:
                    last_log_t = now
                    all_names = [c["name"] for c in all_cookies]
                    ecto_found = [n for n in all_names if n.startswith("ecto")]
                    log(
                        f"[{folder_name}] Todos los nombres: {all_names} | ecto*={ecto_found} "
                        f"| intercept={list(intercepted.keys())}"
                    )

                ecto_cookie = next((c for c in all_cookies if c["name"].startswith("ecto")), None)
                if ecto_cookie:
                    cookie_list = [
                        {
                            "name": c["name"],
                            "value": c["value"],
                            "domain": c.get("domain", ".meta.ai"),
                            "path": c.get("path", "/"),
                            "httpOnly": c.get("httpOnly", False),
                            "secure": c.get("secure", True),
                            "sameSite": c.get("sameSite", "None"),
                        }
                        for c in all_cookies
                    ]
                    (folder / "cookies_auto.json").write_text(json.dumps(cookie_list, indent=2))
                    log(
                        f"[OK] [{folder_name}] Sesion guardada! {ecto_cookie['name']}={ecto_cookie['value'][:16]}... "
                        f"| {len(cookie_list)} cookies"
                    )
                    saved = True
                    time.sleep(1)
                    try:
                        ctx.close()
                    except Exception:
                        pass
                    break

            if not saved:
                all_cookies_f = collect_all_cookies()
                all_names_f = [c["name"] for c in all_cookies_f]
                ecto_names = [n for n in all_names_f if n.startswith("ecto")]
                log(
                    f"[WARNING] [{folder_name}] Timeout. Cookies: {all_names_f} | ecto*={ecto_names} "
                    f"| intercept={list(intercepted.keys())}"
                )
                try:
                    ctx.close()
                except Exception:
                    pass
    except Exception as exc:
        log(f"[ERROR] [{folder_name}] Error: {exc}")
