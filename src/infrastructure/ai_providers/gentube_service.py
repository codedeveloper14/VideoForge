import base64
import json
import os
import queue
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.infrastructure.ai_providers.chrome_launcher import find_chromium_exe
from src.utils.logger import get_logger
from src.utils.paths import get_gentube_cookies_dir, get_gentube_profiles_dir

logger = get_logger(__name__)

NUM_ACCOUNTS = 5
GENTUBE_URL = "https://www.gentube.app/create"
_SESSION_COOKIE_NAMES = {"__session", "__session_yakpvnhU"}


def cookie_path(account_id: int) -> Path:
    return get_gentube_cookies_dir() / f"account_{account_id}.txt"


def read_cookie(account_id: int) -> str:
    path = cookie_path(account_id)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def playwright_available() -> bool:
    try:
        import importlib

        return importlib.util.find_spec("playwright") is not None
    except Exception:
        return False


def probe_session(cookie_str: str) -> dict:
    """Verifica sesion de gentube (Clerk). Si tiene __session = esta logueado.
    Decodifica el JWT para extraer el email, sin llamada de red."""
    if not cookie_str:
        return {"ok": False, "user": ""}
    parts = {p.split("=")[0].strip(): p.split("=", 1)[1].strip() for p in cookie_str.split(";") if "=" in p}
    has_session = any(k in _SESSION_COOKIE_NAMES and v for k, v in parts.items())
    if not has_session:
        return {"ok": False, "user": ""}

    user = ""
    try:
        for name in _SESSION_COOKIE_NAMES:
            val = parts.get(name, "")
            if val and "." in val:
                payload = val.split(".")[1]
                payload += "=" * (4 - len(payload) % 4)
                data = json.loads(base64.b64decode(payload).decode("utf-8", errors="ignore"))
                user = data.get("email") or data.get("sub") or ""
                if user:
                    break
    except Exception:
        pass
    return {"ok": True, "user": user}


def sync_profiles() -> dict[int, dict]:
    """Lee las cookies guardadas y verifica cada sesion en paralelo. Borra las
    cookies invalidas del disco."""

    def _one(i):
        ck = read_cookie(i)
        if not ck:
            return i, {"logged_in": False, "user": ""}
        probe = probe_session(ck)
        if not probe["ok"]:
            try:
                cookie_path(i).unlink()
            except Exception:
                pass
            return i, {"logged_in": False, "user": ""}
        return i, {"logged_in": True, "user": probe.get("user", "")}

    results: dict[int, dict] = {}
    try:
        with ThreadPoolExecutor(max_workers=NUM_ACCOUNTS) as ex:
            futures = [ex.submit(_one, i) for i in range(NUM_ACCOUNTS)]
            for fut in as_completed(futures, timeout=20):
                try:
                    idx, row = fut.result()
                    results[idx] = row
                except Exception:
                    pass
    except Exception:
        pass
    return results


def playwright_login(account_id: int, log) -> None:
    """Abre Chrome, el usuario inicia sesion en gentube.app, captura la cookie de
    sesion (Clerk) y la guarda en disco. Bloqueante -- correr en un hilo."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log(f"  [C{account_id}] [ERROR] Playwright no instalado.")
        return

    profile_dir = str(get_gentube_profiles_dir() / f"gt_profile_{account_id}")
    os.makedirs(profile_dir, exist_ok=True)
    log(f"  [C{account_id}] Abriendo Chrome - inicia sesion en gentube.app")

    try:
        with sync_playwright() as pw:
            exe = find_chromium_exe()
            ctx = pw.chromium.launch_persistent_context(
                profile_dir,
                headless=False,
                executable_path=exe,
                args=["--no-first-run", "--disable-blink-features=AutomationControlled"],
                ignore_https_errors=True,
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(GENTUBE_URL, timeout=20000)
            except Exception:
                pass

            saved = False
            while True:
                try:
                    cookies = ctx.cookies()
                except Exception:
                    break  # browser cerrado por el usuario

                gt_cookies = [
                    c
                    for c in cookies
                    if "gentube" in c.get("domain", "").lower() or "clerk" in c.get("domain", "").lower()
                ]
                session_cookies = [c for c in gt_cookies if c["name"] in _SESSION_COOKIE_NAMES]

                if session_cookies:
                    ck_str = "; ".join(f"{c['name']}={c['value']}" for c in gt_cookies)
                    probe = probe_session(ck_str)
                    if probe["ok"]:
                        cookie_path(account_id).write_text(ck_str, encoding="utf-8")
                        log(f"  [C{account_id}] [OK] Cookie guardada - {probe.get('user', '')}")
                        saved = True

                if saved:
                    time.sleep(1)
                    try:
                        ctx.close()
                    except Exception:
                        pass
                    break

                time.sleep(2)

            if not saved:
                log(f"  [C{account_id}] [WARNING] Browser cerrado sin guardar sesion")
    except Exception as exc:
        log(f"  [C{account_id}] [ERROR] Error: {exc}")


_GENERATE_JS = """
() => {
    // 1. Limpiar y escribir prompt en textarea
    const ta = document.querySelector('textarea');
    if (!ta) return 'no_textarea';
    ta.focus();
    const nativeSet = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype, 'value').set;
    nativeSet.call(ta, %(prompt)s);
    ta.dispatchEvent(new Event('input', {bubbles:true}));
    ta.dispatchEvent(new Event('change', {bubbles:true}));

    // 2. Instalar MutationObserver + interval poll ANTES del click
    window.__gt_img = null;
    window.__gt_pre = new Set(
        Array.from(document.querySelectorAll('img'))
             .map(i => (i.src||'').substring(0,200))
             .filter(Boolean)
    );
    const _check = () => {
        for (const img of document.querySelectorAll('img')) {
            const s = img.src || '';
            if (window.__gt_pre.has(s.substring(0,200))) continue;
            // data: -- imagen inline en base64 (formato historico de GenTube).
            // blob: -- patron comun en apps React que renderizan el resultado con
            // URL.createObjectURL(blob); no trae longitud en la URL, asi que
            // cualquier blob: nuevo (no pre-existente) cuenta como candidato.
            if (s.startsWith('data:image') && s.length > 5000) {
                window.__gt_img = s; return;
            }
            if (s.startsWith('blob:')) {
                window.__gt_img = s; return;
            }
        }
    };
    const obs = new MutationObserver(_check);
    obs.observe(document.body, {subtree:true, childList:true,
                                 attributes:true, attributeFilter:['src']});
    // Poll interval como backup (React puede reemplazar nodos)
    window.__gt_poll = setInterval(_check, 150);
    window.__gt_obs = obs;

    // 3. Click boton generar (flecha)
    const r = ta.getBoundingClientRect();
    const candidates = Array.from(document.querySelectorAll('button'))
        .filter(b => {
            const br = b.getBoundingClientRect();
            const cls = b.className || '';
            return b.offsetParent !== null && !b.disabled &&
                   b.textContent.trim() === '' &&
                   br.y >= r.top - 20 && br.y <= r.bottom + 60 &&
                   br.x >= r.right - 60 && !cls.includes('absolute');
        });
    candidates.sort((a,b) => {
        const ar=a.getBoundingClientRect(), br=b.getBoundingClientRect();
        return Math.hypot(ar.x-r.right,ar.y-r.top)
              -Math.hypot(br.x-r.right,br.y-r.top);
    });
    if (candidates.length > 0) { candidates[0].click(); return 'ok'; }
    return 'no_btn';
}
"""

# Los bytes de un blob: URL solo existen dentro del contexto de la pagina que lo
# creo -- hay que leerlos ahi (fetch + FileReader) y devolverlos como data URL
# para poder reusar el mismo parsing (`header, _, b64data = ...partition(",")`)
# que ya existe para el caso "data:image" clasico.
_BLOB_TO_DATA_URL_JS = """
(u) => fetch(u).then(r => r.blob()).then(b => new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = reject;
    fr.readAsDataURL(b);
}))
"""


_TRACKER_DOMAINS = (
    "google-analytics",
    "googleads",
    "doubleclick",
    "pinterest",
    "axiom.co",
    "posthog",
    "ph.gentube",
)


def should_block_request(url: str, resource_type: str) -> bool:
    """Que bloquear en el contexto headless de generacion. Bloquea fuentes/media
    (no afectan la captura de la imagen resultado, ahorran ancho de banda) y
    dominios de tracking conocidos -- NUNCA por resource_type "image" con un
    allowlist de un solo dominio de CDN: eso fue justamente lo que dejo a
    Playwright ciego cuando GenTube cambio de CDN (la imagen final se
    bloqueaba antes de cargar, asi que ni el DOM-observer ni el sniffer de
    red podian verla)."""
    if resource_type in ("font", "media"):
        return True
    return any(d in url for d in _TRACKER_DOMAINS)


def _block_route(route):
    if should_block_request(route.request.url, route.request.resource_type):
        route.abort()
    else:
        route.continue_()


_JUNK_IMAGE_MARKERS = ("profile_", "avatar", "favicon", "/icons/", "logo")


def is_capturable_image_response(url: str, content_type: str, status: int) -> bool:
    """Si una respuesta de red es candidata a "la imagen generada". Antes exigia
    "cloudfront.net" en la URL -- un allowlist de un solo CDN que se rompe con
    cualquier cambio de proveedor de imagenes en GenTube. Ahora es agnostica al
    dominio: cualquier respuesta de tipo imagen con 200 OK cuenta, salvo los
    patrones conocidos de assets decorativos (avatares, iconos, logos)."""
    if status != 200 or "image" not in (content_type or ""):
        return False
    low = url.lower()
    return not any(marker in low for marker in _JUNK_IMAGE_MARKERS)


def _slot_worker(
    slot_idx,
    acc_id,
    cookie_str,
    task_q,
    total,
    saved_count,
    done_count,
    lock,
    state_lock,
    state,
    stop_event,
    log,
    exe,
):
    """Un slot mantiene su propio browser headless y procesa tareas de la cola
    compartida, reutilizando la pagina entre imagenes para evitar recargar
    gentube.app en cada prompt."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            executable_path=exe,
            args=[
                "--no-first-run",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        for ck_part in cookie_str.split(";"):
            ck_part = ck_part.strip()
            if "=" not in ck_part:
                continue
            name, _, val = ck_part.partition("=")
            for domain in (".gentube.app", "gentube.app", "www.gentube.app"):
                try:
                    ctx.add_cookies(
                        [{"name": name.strip(), "value": val.strip(), "domain": domain, "path": "/"}]
                    )
                    break
                except Exception:
                    pass

        page = ctx.new_page()
        page.route("**/*", _block_route)
        page_loaded = False
        pre_urls: set[str] = set()
        captured_imgs: list[str] = []

        def _on_resp(r):
            if is_capturable_image_response(r.url, r.headers.get("content-type", ""), r.status):
                captured_imgs.append(r.url)

        page.on("response", _on_resp)

        def _mark_done():
            with lock:
                done_count[0] += 1
                with state_lock:
                    state["progress"] = min(done_count[0], total)
            task_q.task_done()

        try:
            while not stop_event.is_set():
                try:
                    task_idx, prompt, retries = task_q.get_nowait()
                except queue.Empty:
                    break

                try:
                    if not page_loaded:
                        page.goto(GENTUBE_URL, timeout=60000, wait_until="domcontentloaded")
                        try:
                            page.wait_for_selector("textarea", timeout=15000)
                        except Exception:
                            pass
                        time.sleep(0.2)
                        for img in page.query_selector_all("img"):
                            s = img.get_attribute("src") or ""
                            if s:
                                pre_urls.add(s[:200])
                        page_loaded = True
                        log(f"  [S{slot_idx}/C{acc_id}] Pagina cargada")

                    log(f"  [S{slot_idx}|{task_idx + 1}/{total}] {prompt[:55]}...")

                    del captured_imgs[:]
                    result = page.evaluate(_GENERATE_JS % {"prompt": json.dumps(prompt)})

                    if result != "ok":
                        log(f"  [S{slot_idx}] {result}, recargando...")
                        page_loaded = False
                        pre_urls.clear()
                        try:
                            cur_url = page.url
                            if "sign-in" in cur_url or "login" in cur_url or "clerk" in cur_url:
                                log(f"  [S{slot_idx}] Sesion expirada C{acc_id} - usa Login")
                                try:
                                    cookie_path(acc_id).unlink()
                                except Exception:
                                    pass
                                if retries < 3:
                                    task_q.put((task_idx, prompt, retries + 1))
                                _mark_done()
                                break
                        except Exception:
                            pass
                        if retries < 3:
                            task_q.put((task_idx, prompt, retries + 1))
                        _mark_done()
                        continue

                    result_img = None
                    for _tick in range(90):
                        time.sleep(0.2)
                        try:
                            ds = page.evaluate("() => window.__gt_img || null")
                            if ds and ds[:200] not in pre_urls:
                                try:
                                    page.evaluate(
                                        "() => { if(window.__gt_obs) window.__gt_obs.disconnect(); "
                                        "if(window.__gt_poll) clearInterval(window.__gt_poll); }"
                                    )
                                except Exception:
                                    pass
                                if ds.startswith("blob:"):
                                    # blob: no trae los bytes en la URL -- hay que
                                    # leerlo desde el contexto de la pagina (donde
                                    # el objeto Blob vive) y convertirlo a data URL.
                                    try:
                                        ds = page.evaluate(_BLOB_TO_DATA_URL_JS, ds)
                                    except Exception:
                                        ds = None
                                if ds:
                                    result_img = ("b64", ds)
                                    break
                            new_imgs = [u for u in captured_imgs if u not in pre_urls]
                            if new_imgs:
                                result_img = ("url", new_imgs[-1])
                                break
                        except Exception:
                            pass

                    if not result_img:
                        log(f"  [S{slot_idx}|{task_idx + 1}] Sin imagen, reintentando...")
                        page_loaded = False
                        pre_urls.clear()
                        if retries < 3:
                            task_q.put((task_idx, prompt, retries + 1))
                        _mark_done()
                        continue

                    ts = int(time.time() * 1000)
                    output_dir = state["output_dir"]
                    if result_img[0] == "b64":
                        header, _, b64data = result_img[1].partition(",")
                        ext = "webp" if "webp" in header else "png"
                        fname = f"gt_{task_idx + 1:04d}_{ts}.{ext}"
                        fpath = os.path.join(output_dir, fname)
                        with open(fpath, "wb") as fh:
                            fh.write(base64.b64decode(b64data))
                        pre_urls.add(result_img[1][:200])
                    else:
                        opener = urllib.request.build_opener()
                        opener.addheaders = [("User-Agent", "Mozilla/5.0")]
                        img_data = opener.open(result_img[1], timeout=30).read()
                        ext = "webp" if result_img[1].endswith(".webp") else "png"
                        fname = f"gt_{task_idx + 1:04d}_{ts}.{ext}"
                        fpath = os.path.join(output_dir, fname)
                        with open(fpath, "wb") as fh:
                            fh.write(img_data)

                    with lock:
                        saved_count[0] += 1
                        with state_lock:
                            state["images_saved"] = saved_count[0]
                    log(f"  [OK] [S{slot_idx}|{task_idx + 1}] {fname}")

                except Exception as exc:
                    log(f"  [S{slot_idx}|{task_idx + 1}] [ERROR] {str(exc)[:80]}")
                    page_loaded = False
                    pre_urls.clear()
                    if retries < 3:
                        task_q.put((task_idx, prompt, retries + 1))
                finally:
                    _mark_done()
        finally:
            try:
                browser.close()
            except Exception:
                pass


def run_batch(prompts, slots, repeat, output_dir, state, state_lock, stop_event, log) -> None:
    """Genera imagenes usando N slots (browsers headless) en paralelo, round-robin
    entre las cuentas con cookie guardada. Bloqueante -- correr en un hilo."""
    os.makedirs(output_dir, exist_ok=True)

    cookies_list = [(i, ck) for i in range(NUM_ACCOUNTS) if (ck := read_cookie(i))]
    if not cookies_list:
        log("[ERROR] No hay cuentas configuradas. Usa Login primero.")
        with state_lock:
            state.update(running=False, step="idle")
        return

    if not playwright_available():
        log("[ERROR] Playwright no instalado.")
        with state_lock:
            state.update(running=False, step="idle")
        return

    all_tasks = prompts * repeat
    total = len(all_tasks)
    effective_slots = min(slots, total)

    with state_lock:
        state.update(
            running=True, step="running", progress=0, total=total, images_saved=0, output_dir=output_dir
        )
    log(f"GenTube: {total} imagenes - {effective_slots} slots - {len(cookies_list)} cuentas")

    exe = find_chromium_exe()
    task_q: queue.Queue = queue.Queue()
    for i, p in enumerate(all_tasks):
        task_q.put((i, p, 0))

    saved_count = [0]
    done_count = [0]
    lock = threading.Lock()

    threads = []
    for slot_idx in range(effective_slots):
        acc_id, cookie_str = cookies_list[slot_idx % len(cookies_list)]
        t = threading.Thread(
            target=_slot_worker,
            args=(
                slot_idx,
                acc_id,
                cookie_str,
                task_q,
                total,
                saved_count,
                done_count,
                lock,
                state_lock,
                state,
                stop_event,
                log,
                exe,
            ),
            daemon=True,
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    log(f"Finalizado. {saved_count[0]}/{total} imagenes.")
    with state_lock:
        state.update(running=False, step="done", progress=done_count[0], images_saved=saved_count[0])
