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
        import importlib.util

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
async () => {
    // 1. Limpiar y escribir prompt en textarea. Preferir la caja principal por
    // su placeholder actual ("Type to Create..."), con fallback al primer
    // <textarea> de la pagina si el placeholder cambia de nuevo.
    const ta = document.querySelector('textarea[placeholder*="Type to Create" i]')
        || document.querySelector('textarea');
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

    // 3. Click boton generar. Preferir el boton real por su aria-label estable
    // ("Create") en vez de la heuristica geometrica: el input sintetico de
    // arriba dispara un re-render de React que puede no haber terminado en
    // este mismo tick sincrono, asi que el boton real todavia puede figurar
    // como disabled cuando lo buscamos -- eso llevaba a descartarlo y
    // clickear un boton decoy cercano (ej. "Hide blocks panel"). Por eso se
    // espera activamente (hasta 3s) a que se habilite antes de clickear.
    let btn = document.querySelector('button[aria-label="Create" i]');
    if (btn) {
        for (let i = 0; i < 30 && btn.disabled; i++) {
            await new Promise(res => setTimeout(res, 100));
        }
        if (btn.disabled) return 'create_btn_disabled';
        window.__gt_clicked_btn = btn;
        btn.click();
        return 'ok';
    }

    // Fallback: heuristica geometrica original, por si el aria-label cambia
    // de nuevo en un futuro rediseño.
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
    if (candidates.length > 0) {
        window.__gt_clicked_btn = candidates[0];
        candidates[0].click();
        return 'ok';
    }
    return 'no_btn';
}
"""

# _GENERATE_JS de arriba queda como fallback legado autocontenido (y como sujeto
# de los tests de test_gentube_selectors.py) -- confirmado en vivo que su truco
# de dispatchEvent('input') para escribir el prompt NO registra en el estado de
# React de gentube.app (el boton "Create" queda disabled sin importar cuanto se
# espere). El flujo real en produccion usa page.locator(...).fill() +
# page.locator(...).click() de Playwright (dispara eventos de teclado/input
# reales via CDP, que React si reconoce) con estas dos piezas separadas:

# Solo instala el detector de imagen -- se llama DESPUES de fill() y ANTES del
# click, igual que el paso 2 original de _GENERATE_JS.
_INSTALL_OBSERVER_JS = """
() => {
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
    window.__gt_poll = setInterval(_check, 150);
    window.__gt_obs = obs;
}
"""

# Fallback de click puro (el texto ya se escribio via Playwright fill()) --
# misma heuristica geometrica que el paso 3 de _GENERATE_JS, usada solo si
# page.locator('button[aria-label="Create" i]').click() de Playwright no
# encuentra/habilita el boton (ej. un futuro rediseño cambia el aria-label).
_FALLBACK_CLICK_JS = """
() => {
    const ta = document.querySelector('textarea[placeholder*="Type to Create" i]')
        || document.querySelector('textarea');
    if (!ta) return 'no_textarea';
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
    if (candidates.length > 0) {
        window.__gt_clicked_btn = candidates[0];
        candidates[0].click();
        return 'ok';
    }
    return 'no_btn';
}
"""

# Diagnostico post-click: confirma si el valor realmente quedo cargado en el
# textarea (React puede ignorar el input sintetico) y que boton se termino
# clickeando -- para descartar que estemos clickeando un control decorativo en
# vez del boton real de generar.
_POST_CLICK_DIAG_JS = """
() => {
    const ta = document.querySelector('textarea[placeholder*="Type to Create" i]')
        || document.querySelector('textarea');
    const btn = window.__gt_clicked_btn;
    return JSON.stringify({
        ta_value: ta ? ta.value.substring(0, 80) : null,
        btn_disabled: btn ? btn.disabled : null,
        btn_html: btn ? btn.outerHTML.substring(0, 300) : null,
    });
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
    "ga-audiences",
    "pinterest",
)
# NO agregar "ph.gentube", "posthog" ni "axiom.co" a esta lista sin verificar
# primero via el log [reqfail] (ver page.on("requestfailed") en _slot_worker)
# que el fetch() interno de generacion de gentube.app sigue completando.
#
# Los tres son servicios propios de GenTube (proxy de PostHog en ph.gentube.app
# -- config/flags/eventos/session-recording -- y su pipeline de logging en
# api.axiom.co/.../ingest), no trackers de terceros de verdad. Bloquearlos
# rompe un fetch() interno de la app (TypeError: Failed to fetch, capturado
# via consola) y la generacion real nunca llega a dispararse -- probablemente
# la causa original del bug de imagenes vacias/avatar. "posthog" generico
# tambien hay que dejarlo afuera: varias rutas de ph.gentube.app (ej.
# /static/posthog-recorder.js) contienen ese substring en el path, asi que
# alcanza con dejar el dominio "ph.gentube" bloqueado para que ese substring
# generico ya no haga falta.


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


_MIN_VALID_IMAGE_BYTES = 2000  # un pixel de tracking pesa decenas de bytes; el arte real de GenTube, no.


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
    """Un slot mantiene su propio browser Chromium (aislado, sesion inyectada via
    add_cookies()) y procesa tareas de la cola compartida, reutilizando la pagina
    entre imagenes para evitar recargar gentube.app en cada prompt.

    headless=True (100% en segundo plano). El bug de "no genera nada" no era
    headless vs headed -- se probaron ambos con resultado identico -- era que
    should_block_request() bloqueaba ph.gentube.app (proxy propio de GenTube
    para PostHog: config/feature-flags/eventos), lo que rompia un fetch()
    interno de la app antes de que la generacion real llegara a dispararse.
    Ver comentario junto a _TRACKER_DOMAINS."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        log(f"  [S{slot_idx}/C{acc_id}] Lanzando Chromium (headless) - exe={exe}")
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
        page.on(
            "console",
            lambda msg: log(f"  [S{slot_idx}] [console:{msg.type}] {msg.text[:200]}")
            if msg.type in ("error", "warning")
            else None,
        )
        page_loaded = False
        pre_urls: set[str] = set()
        captured_imgs: list[str] = []

        def _on_resp(r):
            if is_capturable_image_response(r.url, r.headers.get("content-type", ""), r.status):
                log(f"  [S{slot_idx}] [net-img] {r.status} {r.headers.get('content-type', '')} {r.url[:120]}")
                captured_imgs.append(r.url)

        page.on("response", _on_resp)

        def _on_reqfailed(req):
            # Diagnostico: cual URL exacta fallo y por que -- distingue si fuimos
            # nosotros los que la abortamos (should_block_request) de un fallo de
            # red externo real (el segundo es el sospechoso de romper la generacion).
            blocked_by_us = should_block_request(req.url, req.resource_type)
            reason = req.failure or ""
            log(
                f"  [S{slot_idx}] [reqfail] blocked_por_nosotros={blocked_by_us} "
                f"type={req.resource_type} reason={reason} url={req.url[:150]}"
            )

        page.on("requestfailed", _on_reqfailed)

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
                        log(f"  [S{slot_idx}/C{acc_id}] [debug] goto -> url={page.url} title={page.title()!r}")
                        try:
                            page.wait_for_selector("textarea", timeout=15000)
                            log(f"  [S{slot_idx}/C{acc_id}] [debug] textarea encontrado")
                        except Exception as exc:
                            log(f"  [S{slot_idx}/C{acc_id}] [debug] [WARN] textarea NO encontrado: {exc}")
                        time.sleep(0.2)
                        pre_srcs = []
                        for img in page.query_selector_all("img"):
                            # .src (propiedad JS resuelta) en vez de get_attribute("src") (atributo
                            # crudo, puede venir relativo tipo "/images/x.png") -- si no coinciden en
                            # formato con las URLs absolutas que reporta la red, una imagen preexistente
                            # (ej. el logo del sitio) parece "nueva" en cada reload y se cuela como
                            # resultado falso.
                            s = img.evaluate("el => el.src") or ""
                            if s:
                                pre_urls.add(s[:200])
                                pre_srcs.append(s[:80])
                        log(f"  [S{slot_idx}/C{acc_id}] [debug] {len(pre_srcs)} <img> preexistentes: {pre_srcs}")
                        page_loaded = True
                        log(f"  [S{slot_idx}/C{acc_id}] Pagina cargada")

                    log(f"  [S{slot_idx}|{task_idx + 1}/{total}] {prompt[:55]}...")

                    del captured_imgs[:]

                    ta_locator = page.locator('textarea[placeholder*="Type to Create" i]')
                    if ta_locator.count() == 0:
                        ta_locator = page.locator("textarea").first
                    if ta_locator.count() == 0:
                        result = "no_textarea"
                    else:
                        # fill() de Playwright (via CDP) dispara los eventos reales que
                        # React necesita para registrar el cambio -- el truco JS de
                        # dispatchEvent('input') NUNCA habilitaba el boton "Create"
                        # (confirmado en vivo: quedaba disabled sin importar cuanto se
                        # esperara), asi que ya no se usa como camino principal.
                        ta_locator.click()
                        ta_locator.fill(prompt)
                        page.evaluate(_INSTALL_OBSERVER_JS)
                        try:
                            page.locator('button[aria-label="Create" i]').click(timeout=10000)
                            result = "ok"
                        except Exception:
                            log(f"  [S{slot_idx}|{task_idx + 1}] [debug] boton Create no disponible via aria-label, fallback geometrico")
                            result = page.evaluate(_FALLBACK_CLICK_JS)
                    log(f"  [S{slot_idx}|{task_idx + 1}] [debug] click result={result!r}")
                    if result == "ok":
                        try:
                            diag = page.evaluate(_POST_CLICK_DIAG_JS)
                            log(f"  [S{slot_idx}|{task_idx + 1}] [debug] post-click: {diag}")
                        except Exception as exc:
                            log(f"  [S{slot_idx}|{task_idx + 1}] [debug] post-click diag fallo: {exc}")

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
                                break
                        except Exception:
                            pass
                        if retries < 3:
                            task_q.put((task_idx, prompt, retries + 1))
                        continue

                    result_img = None
                    for _tick in range(90):
                        time.sleep(0.2)
                        if _tick > 0 and _tick % 25 == 0:
                            log(
                                f"  [S{slot_idx}|{task_idx + 1}] [debug] tick={_tick} "
                                f"captured_imgs={len(captured_imgs)} esperando window.__gt_img..."
                            )
                        try:
                            ds = page.evaluate("() => window.__gt_img || null")
                            if ds and ds[:200] not in pre_urls:
                                log(
                                    f"  [S{slot_idx}|{task_idx + 1}] [debug] __gt_img detectado: "
                                    f"{ds[:80]}... (len={len(ds)})"
                                )
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
                                log(f"  [S{slot_idx}|{task_idx + 1}] [debug] imagen via red: {new_imgs[-1][:120]}")
                                result_img = ("url", new_imgs[-1])
                                break
                        except Exception:
                            pass

                    if not result_img:
                        cur_imgs = [
                            (img.evaluate("el => el.src") or "")[:80] for img in page.query_selector_all("img")
                        ]
                        log(
                            f"  [S{slot_idx}|{task_idx + 1}] Sin imagen, reintentando... "
                            f"[debug] <img> en DOM ahora: {cur_imgs}"
                        )
                        page_loaded = False
                        pre_urls.clear()
                        if retries < 3:
                            task_q.put((task_idx, prompt, retries + 1))
                        continue

                    ts = int(time.time() * 1000)
                    output_dir = state["output_dir"]
                    if result_img[0] == "b64":
                        header, _, b64data = result_img[1].partition(",")
                        ext = "webp" if "webp" in header else "png"
                        img_bytes = base64.b64decode(b64data)
                    else:
                        opener = urllib.request.build_opener()
                        opener.addheaders = [("User-Agent", "Mozilla/5.0")]
                        img_bytes = opener.open(result_img[1], timeout=30).read()
                        ext = "webp" if result_img[1].endswith(".webp") else "png"

                    if len(img_bytes) < _MIN_VALID_IMAGE_BYTES:
                        log(
                            f"  [S{slot_idx}|{task_idx + 1}] [WARN] captura descartada por tamano "
                            f"sospechoso ({len(img_bytes)} bytes, source={result_img[0]}, "
                            f"url={result_img[1][:120]}), reintentando..."
                        )
                        page_loaded = False
                        pre_urls.clear()
                        if retries < 3:
                            task_q.put((task_idx, prompt, retries + 1))
                        continue

                    if result_img[0] == "b64":
                        pre_urls.add(result_img[1][:200])

                    fname = f"gt_{task_idx + 1:04d}_{ts}.{ext}"
                    fpath = os.path.join(output_dir, fname)
                    with open(fpath, "wb") as fh:
                        fh.write(img_bytes)

                    with lock:
                        saved_count[0] += 1
                        with state_lock:
                            state["images_saved"] = saved_count[0]
                    log(f"  [OK] [S{slot_idx}|{task_idx + 1}] {fname} [debug] {len(img_bytes)} bytes (source={result_img[0]})")

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


def run_batch(
    prompts, slots, repeat, output_dir, state, state_lock, stop_event, log, browser_mode: str = "chromium"
) -> None:
    """Genera imagenes con GenTube. Bloqueante -- correr en un hilo.

    Chromium exclusivamente: N slots en paralelo, round-robin entre las cuentas
    con cookie guardada -- multi-cuenta. `browser_mode` se acepta solo por
    compatibilidad con el llamador (gentube_animation_service.start_run) y se
    ignora -- ya no existe modo "Chrome real"/ventana persistente."""
    os.makedirs(output_dir, exist_ok=True)

    if browser_mode != "chromium":
        log(f"[gentube] browser_mode={browser_mode!r} ignorado - GenTube corre siempre sobre Chromium")

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
    exe = find_chromium_exe()
    log(f"GenTube: {total} imagenes - {effective_slots} slots - {len(cookies_list)} cuentas")

    with state_lock:
        state.update(
            running=True, step="running", progress=0, total=total, images_saved=0, output_dir=output_dir
        )

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
