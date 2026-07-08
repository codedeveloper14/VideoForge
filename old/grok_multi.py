#!/usr/bin/env python3
"""
grok_multi.py — Multi-cuenta Grok Animator
Las imágenes se procesan ordenadas por FECHA DE CREACIÓN (más antigua primero).
El video de salida usa el mismo stem que la imagen: img_00001.jpg --> img_00001.mp4

Uso:
  python3 grok_multi.py /fotos --slots 3 --prompt "Cinematic slow zoom"
  python3 grok_multi.py /fotos --slots 3 --login   ← primer uso
"""
import sys, json, time, uuid, base64, logging, argparse, mimetypes, requests, random, threading
from pathlib import Path
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR      = Path(__file__).parent.resolve()
ACCOUNTS_DIR  = BASE_DIR / "accounts"
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
SLOTS_MAX = 12

def _make_log_handlers():
    fh = logging.FileHandler(str(BASE_DIR / "grok_multi.log"), encoding="utf-8")
    if sys.platform == "win32":
        import io
        stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        sh = logging.StreamHandler(stream)
    else:
        sh = logging.StreamHandler()
    return [sh, fh]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_make_log_handlers(),
    force=True,
)
log = logging.getLogger(__name__)

GROK_BASE     = "https://grok.com"
UPLOAD_URL    = f"{GROK_BASE}/rest/app-chat/upload-file"
CONV_URL      = f"{GROK_BASE}/rest/app-chat/conversations/new"
ASSET_BASE    = "https://assets.grok.com"

# Misma familia Chrome 124 que el script original; el UA y sec-ch-ua-platform deben
# coincidir con el SO real. En Windows con firma "macOS" Grok suele responder anti-bot.
def _http_browser_fingerprint():
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
    # Linux u otros: Chrome desktop genérico (coherente con TLS cliente)
    return {
        "user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua_platform": '"Linux"',
    }

# ── Ordenar por fecha de creación ──────────────────────────────────────────────

def _creation_time(path: Path) -> float:
    """Fecha de creación real (macOS: st_birthtime; Linux/Win: st_mtime)."""
    st = path.stat()
    return getattr(st, "st_birthtime", None) or st.st_mtime

def get_images(source: str):
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    p = Path(source)
    if p.is_dir():
        imgs = [f for f in p.iterdir() if f.suffix.lower() in exts]
    elif p.is_file():
        imgs = [p]
    else:
        imgs = []
    if not imgs:
        log.error("No se encontraron imágenes."); sys.exit(1)

    imgs.sort(key=_creation_time)

    log.info(f"  {len(imgs)} imagen(es) — orden por fecha de creación:")
    for i, img in enumerate(imgs, 1):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_creation_time(img)))
        log.info(f"    {i:03d}. [{ts}] {img.name}")
    return imgs

# ── Utilidades HTTP (idénticas al funcional) ──────────────────────────────────

def _rid(): return str(uuid.uuid4())

def _hdrs(ref=f"{GROK_BASE}/imagine", session_meta=None):
    meta        = session_meta or {}
    trace_id    = uuid.uuid4().hex
    span_id     = uuid.uuid4().hex[:16]
    sample_rand = round(random.uniform(0.1, 0.99), 17)
    sentry_rel  = meta.get("sentry_release", "78c3d15bba7fcf5626222ce6e26baf5c0705b262")
    statsig_id  = meta.get("statsig_id", "")
    fp          = _http_browser_fingerprint()
    h = {
        "accept"            : "*/*",
        "accept-language"   : "es-CO,es;q=0.9,ko;q=0.8,de;q=0.7,ru;q=0.6",
        "origin"            : GROK_BASE,
        "referer"           : ref,
        "priority"          : "u=1, i",
        "sec-ch-ua"         : '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile"  : "?0",
        "sec-ch-ua-platform": fp["sec_ch_ua_platform"],
        "sec-fetch-dest"    : "empty",
        "sec-fetch-mode"    : "cors",
        "sec-fetch-site"    : "same-origin",
        "user-agent"        : fp["user_agent"],
        "sentry-trace"      : f"{trace_id}-{span_id}-0",
        "baggage"           : (
            f"sentry-environment=production,"
            f"sentry-release={sentry_rel},"
            f"sentry-public_key=b311e0f2690c81f25e2c4cf6d4f7ce1c,"
            f"sentry-trace_id={trace_id},"
            f"sentry-org_id=4508179396558848,"
            f"sentry-sampled=false,"
            f"sentry-sample_rand={sample_rand},"
            f"sentry-sample_rate=0"
        ),
        "traceparent"       : f"00-{uuid.uuid4().hex}-{uuid.uuid4().hex[:16]}-00",
        "x-xai-request-id"  : _rid(),
    }
    if statsig_id:
        h["x-statsig-id"] = statsig_id
    return h

def _resolve(raw):
    return raw if raw.startswith("http") else f"{ASSET_BASE}/{raw.lstrip('/')}"

def _deep(obj, d=0):
    if d > 6: return None
    if isinstance(obj, str) and obj.startswith("http") and \
       any(x in obj for x in [".mp4", ".webm", "vidgen", "video"]):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            f = _deep(v, d+1)
            if f: return f
    if isinstance(obj, list):
        for i in obj:
            f = _deep(i, d+1)
            if f: return f
    return None

# ── Cliente: una instancia = una session independiente por slot ────────────────

class GrokAccountClient:
    """Cada slot usa su propia instancia (requests.Session no es thread-safe)."""

    def __init__(self, account_name, slot_id, cookies_dict, session_meta,
                 prompt, aspect_ratio, video_length, resolution):
        self.label        = f"{account_name}-s{slot_id}"
        self.prompt       = prompt
        self.aspect_ratio = aspect_ratio
        self.video_length = video_length
        self.resolution   = resolution
        self.session_meta = session_meta or {}
        self.cookies_dict = dict(cookies_dict)
        self.session      = requests.Session()
        for n, v in self.cookies_dict.items():
            self.session.cookies.set(n, v, domain=".grok.com")

    def _upload(self, image_path):
        mime, _ = mimetypes.guess_type(str(image_path)); mime = mime or "image/jpeg"
        with open(image_path, "rb") as f: b64 = base64.b64encode(f.read()).decode()
        payload = {"fileName": image_path.name, "fileMimeType": mime,
                   "content": b64, "fileSource": "IMAGINE_SELF_UPLOAD_FILE_SOURCE"}
        log.info(f"[{self.label}] [1/3] Subiendo {image_path.name}...")
        for attempt in range(2):
            try:
                hdrs = {**_hdrs(session_meta=self.session_meta), "content-type": "application/json"}
                r = self.session.post(UPLOAD_URL, json=payload, headers=hdrs, timeout=60)
                if r.status_code in (401, 403) and attempt == 0:
                    log.warning(f"[{self.label}] {r.status_code} upload"); continue
                if not r.ok:
                    log.error(f"[{self.label}] Upload {r.status_code}: {r.text[:200]}")
                    return None, None
                data = r.json()
                fid  = (data.get("fileMetadataId") or data.get("fileId") or
                        data.get("id") or data.get("attachmentId"))
                furi = data.get("fileUri", "")
                uid  = self.session.cookies.get("x-userid", "x")
                aurl = (f"{ASSET_BASE}/{furi}" if furi else
                        data.get("url") or data.get("assetUrl") or
                        f"{ASSET_BASE}/users/{uid}/{fid}/content")
                log.info(f"[{self.label}] fileId={fid}")
                return fid, aurl
            except Exception as e:
                log.error(f"[{self.label}] Upload err: {e}"); return None, None
        return None, None

    def _build_payload(self, fid, aurl):
        return {
            "temporary": True, "modelName": "grok-3",
            "message": f"{aurl} {self.prompt} --mode=custom",
            "fileAttachments": [fid], "toolOverrides": {"videoGen": True},
            "enableSideBySide": False,
            "responseMetadata": {"experiments": [], "modelConfigOverride": {"modelMap": {}}}
        }

    def _parse_sse(self, response):
        video_url = None; conv_id = None; video_id = None; lines = []
        uid = self.session.cookies.get("x-userid", "")
        for raw in response.iter_lines(decode_unicode=True):
            lines.append(raw or "")
            if not raw: continue
            payload = raw[5:].strip() if raw.startswith("data:") else raw.strip()
            if not payload or payload == "[DONE]": continue
            try: data = json.loads(payload)
            except: continue
            result = data.get("result", {})
            if not conv_id:
                conv    = result.get("conversation", {})
                conv_id = (conv.get("conversationId") or result.get("conversationId")
                           or result.get("id"))
            resp = result.get("response", {})
            svgr = resp.get("streamingVideoGenerationResponse")
            if svgr:
                prog = svgr.get("progress", 0); rv = svgr.get("videoUrl", "")
                log.info(f"[{self.label}] {prog}%")
                vid = svgr.get("videoId") or svgr.get("videoPostId") or svgr.get("postId")
                if vid and not video_id:
                    video_id = vid; log.info(f"[{self.label}] videoId={video_id}")
                if rv: video_url = _resolve(rv)
                if prog == 100 and rv:
                    log.info(f"[{self.label}] [OK] 100% url={video_url}"); break
            for media in (resp.get("generatedMedia") or result.get("generatedMedia") or []):
                ru = media.get("url") or media.get("videoUrl") or media.get("mediaUrl") or ""
                mt = (media.get("mediaType") or "").lower()
                if ru:
                    u = _resolve(ru)
                    if "video" in mt or ru.endswith((".mp4", ".webm")):
                        video_url = u; break
        (BASE_DIR / f"sse_dump_{self.label}.txt").write_text("\n".join(lines))
        log.info(f"[{self.label}] SSE fin — conv={conv_id} vid={video_id} url={video_url}")
        if video_url: return video_url
        if video_id and uid:
            url = f"{ASSET_BASE}/users/{uid}/generated/{video_id}/generated_video.mp4?cache=1"
            log.info(f"[{self.label}] URL construida: {url}"); return url
        if conv_id:
            log.info(f"[{self.label}] Polleando {conv_id}..."); return self._poll(conv_id)
        return None

    def _poll(self, conv_id):
        url = f"{GROK_BASE}/rest/app-chat/conversations/{conv_id}/responses"
        deadline = time.time() + 600
        while time.time() < deadline:
            try:
                r = self.session.get(url, headers=_hdrs(session_meta=self.session_meta), timeout=30)
                if r.ok:
                    found = _deep(r.json())
                    if found: return found
            except Exception as e:
                log.warning(f"[{self.label}] Poll: {e}")
            time.sleep(6)
        log.error(f"[{self.label}] Poll timeout."); return None

    def animate(self, image_path):
        fid, aurl = self._upload(image_path)
        if not fid: return None
        payload = self._build_payload(fid, aurl)
        log.info(f"[{self.label}] [2/3] Generando video...")
        for attempt in range(2):
            try:
                hdrs = {**_hdrs(session_meta=self.session_meta), "content-type": "application/json"}
                r = self.session.post(CONV_URL, json=payload, headers=hdrs,
                                      timeout=30, stream=True)
                if r.status_code in (401, 403) and attempt == 0:
                    log.warning(f"[{self.label}] {r.status_code}"); continue
                if not r.ok:
                    log.error(f"[{self.label}] Conv {r.status_code}: {r.text[:200]}"); return None
                log.info(f"[{self.label}] [3/3] Esperando SSE...")
                return self._parse_sse(r)
            except Exception as e:
                log.error(f"[{self.label}] Animate: {e}"); return None
        return None

    def download(self, url, dest):
        """Usa self.session. Espera 15s (CDN) + retry cada 20s hasta 10 min."""
        hdrs = _hdrs(session_meta=self.session_meta)
        hdrs["referer"] = "https://grok.com/"
        log.info(f"[{self.label}] Descargando --> {dest.name} (15s CDN...)")
        time.sleep(15)
        deadline = time.time() + 600
        attempt  = 0
        while time.time() < deadline:
            attempt += 1
            try:
                with self.session.get(url, stream=True, timeout=180, headers=hdrs) as r:
                    if r.status_code == 404:
                        log.info(f"[{self.label}] CDN 404 intento {attempt} — 20s...")
                        time.sleep(20); continue
                    r.raise_for_status()
                    with open(dest, "wb") as f:
                        for chunk in r.iter_content(65536): f.write(chunk)
                    log.info(f"[{self.label}] [OK] {dest.name} ({dest.stat().st_size//1024} KB) intento {attempt}")
                    return True
            except requests.exceptions.HTTPError as e:
                code = e.response.status_code if e.response else "?"
                log.warning(f"[{self.label}] HTTP {code} intento {attempt}"); time.sleep(20)
            except Exception as e:
                log.warning(f"[{self.label}] DL err {attempt}: {e}"); time.sleep(20)
        log.error(f"[{self.label}] [ERROR] Timeout descarga: {url}")
        (BASE_DIR / "pending_downloads.txt").open("a").write(url + "\n")
        return False

# ── Login vía Playwright ───────────────────────────────────────────────────────

def _login_account(folder):
    from playwright.sync_api import sync_playwright
    profile_dir = folder / "chromium_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    captured = {}
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(profile_dir), headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-features=IsolateOrigins,site-per-process"],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 800},
            locale="es-CO", timezone_id="America/Bogota",
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
            Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
            window.chrome={runtime:{},loadTimes:function(){},csi:function(){},app:{}};
        """)
        def on_req(req):
            h   = req.headers
            sid = h.get("x-statsig-id", "")
            if sid and not captured.get("statsig_id"):
                captured["statsig_id"] = sid; log.info(f"[{folder.name}] statsig_id [OK]")
            bag = h.get("baggage", "")
            if "sentry-release=" in bag and not captured.get("sentry_release"):
                for part in bag.split(","):
                    if part.strip().startswith("sentry-release="):
                        captured["sentry_release"] = part.split("=", 1)[1].strip()
        page.on("request", on_req)
        page.goto(f"{GROK_BASE}/imagine", timeout=60000)
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        log.info(f"[{folder.name}] *** Inicia sesión en el browser *** (máx 3 min)")
        for _ in range(180):
            ck = {c["name"]: c["value"] for c in ctx.cookies("https://grok.com")}
            if ck.get("sso"): log.info(f"[{folder.name}] [OK] Login OK"); break
            time.sleep(1)
        else:
            log.error(f"[{folder.name}] Timeout login"); ctx.close(); return False
        time.sleep(3)
        try: page.reload(); page.wait_for_load_state("networkidle", timeout=15000)
        except: pass
        time.sleep(2)
        raw = ctx.cookies("https://grok.com"); ctx.close()
    clist = [{"name": c["name"], "value": c["value"], "domain": ".grok.com",
              "path": "/", "httpOnly": False, "secure": True} for c in raw]
    (folder / "cookies_auto.json").write_text(json.dumps(clist, indent=2))
    (folder / "session_meta.json").write_text(json.dumps(captured, indent=2))
    log.info(f"[{folder.name}] Cookies y meta guardados [OK]")
    return True

# ── Crear clientes por cuenta ──────────────────────────────────────────────────

def _make_clients(folder, slots, prompt, aspect_ratio, video_length, resolution):
    """Devuelve `slots` instancias independientes (una session cada una)."""
    cookies_file = folder / "cookies_auto.json"
    meta_file    = folder / "session_meta.json"
    if not cookies_file.exists():
        log.warning(f"[{folder.name}] Sin cookies_auto.json — omitiendo"); return []
    cookies = {c["name"]: c["value"] for c in json.loads(cookies_file.read_text()) if "name" in c}
    meta    = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    clients = [GrokAccountClient(folder.name, i, cookies, meta,
                                 prompt, aspect_ratio, video_length, resolution)
               for i in range(1, slots + 1)]
    log.info(f"  [{folder.name}] {slots} slot(s) — statsig={'[OK]' if meta.get('statsig_id') else '[ERROR]'}")
    return clients

# ── Worker loop ────────────────────────────────────────────────────────────────

def _worker(client, queue, total, success_count, lock, output_dir):
    while True:
        try: idx, img = queue.get_nowait()
        except Empty: break
        dest = output_dir / f"{img.stem}.mp4"
        if dest.exists() and dest.stat().st_size > 10_000:
            log.info(f"[{client.label}] [{idx:03d}] Ya existe ({dest.stat().st_size//1024}KB) — skip")
            with lock: success_count[0] += 1
            queue.task_done(); continue
        log.info(f"[{client.label}] [{idx:03d}/{total}] {img.name}")
        try:
            url = client.animate(img)
            if url:
                if client.download(url, dest):
                    with lock: success_count[0] += 1
            else:
                log.warning(f"[{client.label}] [{idx:03d}] Sin URL de video")
        except Exception as e:
            log.error(f"[{client.label}] [{idx:03d}]: {e}")
        finally:
            queue.task_done()

# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Grok Multi-Account Animator — orden por fecha de creación",
        formatter_class=argparse.RawTextHelpFormatter
    )
    p.add_argument("images",         help="Carpeta con imágenes (se ordenan por fecha de creación)")
    p.add_argument("--prompt",       default="Animate this image with smooth natural motion",
                   help="Prompt de animación")
    p.add_argument("--aspect-ratio", default="2:3",
                   choices=["1:1","16:9","9:16","4:3","3:4","2:3","3:2"],
                   help="Aspect ratio del video (default: 2:3)")
    p.add_argument("--video-length", type=int, default=6,
                   help="Duración en segundos (default: 6)")
    p.add_argument("--resolution",   default="480p", choices=["480p","720p","1080p"],
                   help="Resolución (default: 480p)")
    p.add_argument("--login",        action="store_true",
                   help="Re-login de todas las cuentas (abre browser por cuenta)")
    p.add_argument("--output-dir",   default="",
                   help="Carpeta destino para los .mp4 (default: ./downloads). "
                        "Usar ruta absoluta a jobs/PROYECTO/video/")
    p.add_argument("--slots",        type=int, default=1, metavar="N",
                   help=(
                       "Videos en paralelo POR cuenta [1-12, default: 1]\n"
                       "  --slots 1  --> 1 video/cuenta (más estable)\n"
                       "  --slots 3  --> 3 videos/cuenta (recomendado)\n"
                       "  --slots 12 --> máximo permitido\n"
                       "Total = cuentas × slots (ej: 3 cuentas × 3 = 9 en paralelo)"
                   ))
    p.add_argument("--filter-file",  default="",
                   help="JSON con lista de nombres de archivos a procesar")
    args = p.parse_args()

    if not 1 <= args.slots <= SLOTS_MAX:
        p.error(f"--slots debe estar entre 1 y {SLOTS_MAX} (ingresaste: {args.slots})")

    output_dir = Path(args.output_dir).resolve() if args.output_dir else DOWNLOADS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    if not ACCOUNTS_DIR.exists():
        ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
        for i in range(1, 4):
            (ACCOUNTS_DIR / f"account_{i}").mkdir(parents=True, exist_ok=True)
        log.warning(f"Se creó {ACCOUNTS_DIR} con cuentas base: account_1..account_3")

    account_folders = sorted([d for d in ACCOUNTS_DIR.iterdir() if d.is_dir()])
    if not account_folders:
        for i in range(1, 4):
            (ACCOUNTS_DIR / f"account_{i}").mkdir(parents=True, exist_ok=True)
        account_folders = sorted([d for d in ACCOUNTS_DIR.iterdir() if d.is_dir()])

    if args.login:
        for folder in account_folders:
            _login_account(folder)

    all_clients = []
    for folder in account_folders:
        all_clients.extend(_make_clients(folder, args.slots, args.prompt,
                                         args.aspect_ratio, args.video_length, args.resolution))
    if not all_clients:
        log.error("Sin clientes disponibles. Ejecuta con --login primero."); sys.exit(1)

    images = get_images(args.images)

    # Aplicar --filter-file si se proveyó
    if args.filter_file:
        try:
            names = json.loads(Path(args.filter_file).read_text())
            allowed = {Path(n).stem for n in names} | {Path(n).name for n in names}
            filtered = [img for img in images if img.stem in allowed or img.name in allowed]
            log.info(f"  Filtrando: {len(filtered)}/{len(images)} imágenes")
            if filtered:
                images = filtered
        except Exception as e:
            log.warning(f"--filter-file ignorado: {e}")

    total = len(images)

    log.info(f"\n{'='*65}")
    _fp = _http_browser_fingerprint()
    log.info(
        "  Cliente HTTP: Chrome 124 / sec-ch-ua-platform %s (alineado al SO como el flujo original)",
        _fp["sec_ch_ua_platform"],
    )
    log.info(f"  Imágenes  : {total} (ordenadas por fecha de creación)")
    log.info(f"  Cuentas   : {len(account_folders)} × {args.slots} slot(s) "
             f"= {len(all_clients)} en paralelo")
    log.info(f"  Slots     : {[c.label for c in all_clients]}")
    log.info(f"  Prompt    : {args.prompt[:60]}")
    log.info(f"  Aspect    : {args.aspect_ratio} | {args.video_length}s | {args.resolution}")
    log.info(f"  Salida    : {output_dir}")
    log.info(f"{'='*65}\n")

    queue = Queue()
    for idx, img in enumerate(images, 1):
        queue.put((idx, img))

    success_count = [0]
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=len(all_clients)) as ex:
        futures = [ex.submit(_worker, c, queue, total, success_count, lock, output_dir)
                   for c in all_clients]
        for f in as_completed(futures):
            try: f.result()
            except Exception as e: log.error(f"Worker crash: {e}")
    queue.join()

    log.info(f"\n{'='*65}")
    log.info(f"  [OK] Completado: {success_count[0]}/{total} videos en {output_dir}")
    log.info(f"{'='*65}")

if __name__ == "__main__":
    main()
