#!/usr/bin/env python3
"""
grok_multi.py — Multi-cuenta Grok Animator (v4 — anti rate-limit)
Las imágenes se procesan ordenadas por FECHA DE CREACIÓN (más antigua primero).
El nombre del video de salida incluye el índice de orden: 001_imagen.mp4, 002_...

Uso:
python3 grok_multi.py /fotos --slots 3 --prompt "Cinematic slow zoom"
python3 grok_multi.py /fotos --slots 3 --login ← primer uso
"""
import sys, json, time, uuid, base64, logging, argparse, mimetypes, requests, random, threading
from pathlib import Path
from queue import Queue, Empty
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("grok_multi.log")]
)

log = logging.getLogger(__name__)

GROK_BASE  = "https://grok.com"
UPLOAD_URL = f"{GROK_BASE}/rest/app-chat/upload-file"
CONV_URL   = f"{GROK_BASE}/rest/app-chat/conversations/new"
ASSET_BASE = "https://assets.grok.com"
BASE_DIR   = Path(__file__).parent.resolve()
ACCOUNTS_DIR  = BASE_DIR / "accounts"
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
SLOTS_MAX = 12

# ── OPTIMIZACIÓN: máximo de reintentos de generación por imagen ───────────────
MAX_GEN_ATTEMPTS = 3

# ── Excepciones propias ────────────────────────────────────────────────────────

class GrokRateLimit(Exception):
    """El servidor devolvio 429 / 503 o un error de cuota en el SSE."""
    def __init__(self, msg="", retry_after: float = 65.0):
        super().__init__(msg)
        self.retry_after = retry_after

class GrokAuthError(Exception):
    """Cookie expirada o cuenta sin acceso."""

# ── Ordenar por fecha de creacion ─────────────────────────────────────────────

def _creation_time(path: Path) -> float:
    st = path.stat()
    return getattr(st, "st_birthtime", None) or st.st_mtime

def get_images(source: str, filter_file: str = ""):
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    p = Path(source)
    if p.is_dir():
        imgs = [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in exts]
    elif p.is_file():
        imgs = [p]
    else:
        imgs = []
    if not imgs:
        log.error("No se encontraron imagenes."); sys.exit(1)

    if filter_file and Path(filter_file).exists():
        import json as _json
        allowed = set(_json.loads(Path(filter_file).read_text()))
        imgs_filtered = [f for f in imgs if f.name in allowed]
        log.info(f"  Filtrando: {len(imgs_filtered)}/{len(imgs)} imagenes de esta sesion")
        if imgs_filtered:
            imgs = imgs_filtered

    imgs.sort(key=_creation_time)
    log.info(f"  {len(imgs)} imagen(es) — orden por fecha de creacion:")
    for i, img in enumerate(imgs, 1):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_creation_time(img)))
        log.info(f"    {i:03d}. [{ts}] {img.name}")
    return imgs

# ── Utilidades HTTP ───────────────────────────────────────────────────────────

def _rid(): return str(uuid.uuid4())

def _hdrs(ref=f"{GROK_BASE}/imagine", session_meta=None):
    meta        = session_meta or {}
    trace_id    = uuid.uuid4().hex
    span_id     = uuid.uuid4().hex[:16]
    sample_rand = round(random.uniform(0.1, 0.99), 17)
    sentry_rel  = meta.get("sentry_release", "78c3d15bba7fcf5626222ce6e26baf5c0705b262")
    statsig_id  = meta.get("statsig_id", "")
    h = {
        "accept"            : "*/*",
        "accept-language"   : "es-CO,es;q=0.9,ko;q=0.8,de;q=0.7,ru;q=0.6",
        "origin"            : GROK_BASE,
        "referer"           : ref,
        "priority"          : "u=1, i",
        "sec-ch-ua"         : '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile"  : "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest"    : "empty",
        "sec-fetch-mode"    : "cors",
        "sec-fetch-site"    : "same-origin",
        "user-agent"        : UA,
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

# ── GrokPool — rotacion inteligente de cuentas ────────────────────────────────

class GrokPool:
    """
    Gestiona N clientes Grok.

    - Rate-limit (429/503/cuota SSE) -> cooldown por slot, rota a otro.
    - Auth expirada -> cooldown temporal (re-evaluacion automatica).
      Si la cookie fue renovada externamente vuelve a funcionar sola.
      Cada fallo consecutivo duplica el cooldown (5min->10->20->30 max).
    - Todos en cooldown -> espera silenciosa (log cada 10 s con countdown).
    - _in_use rastrea slots individuales: mismo slot nunca se asigna dos veces.
    """
    DEAD_COOLDOWN = 5 * 60  # 5 min base antes de re-intentar cuenta muerta

    def __init__(self, clients: list):
        self._clients      = list(clients)
        self._lock         = threading.Lock()
        self._cond         = threading.Condition(self._lock)
        self._cooldown     = {c.label: 0.0 for c in clients}
        self._in_use       = set()
        self._dead_until   = {}   # label -> timestamp (temporal, no permanente)
        self._fail_count   = {}   # account_name -> fallos auth consecutivos
        self._last_sat_log = 0.0

    def _is_dead(self, c) -> bool:
        return time.time() < self._dead_until.get(c.label, 0.0)

    def _free_now(self) -> list:
        now = time.time()
        result = []
        for c in self._clients:
            if c.label in self._in_use: continue
            if now < self._dead_until.get(c.label, 0.0): continue
            if self._cooldown.get(c.label, 0.0) > now: continue
            result.append(c)
        return result

    def _next_free_ts(self) -> float:
        now = time.time()
        candidates = []
        for c in self._clients:
            if c.label in self._in_use: continue
            t = max(self._cooldown.get(c.label, 0.0),
                    self._dead_until.get(c.label, 0.0))
            if t > now: candidates.append(t)
        return min(candidates) if candidates else now + 1.0

    def get_client(self, cancel_ev):
        with self._cond:
            while True:
                if cancel_ev.is_set(): return None
                free = self._free_now()
                if free:
                    free.sort(key=lambda c: sum(
                        1 for l in self._in_use if l.startswith(c.account_name)
                    ))
                    chosen = free[0]
                    self._in_use.add(chosen.label)
                    # Si este slot estaba en periodo de re-evaluacion (dead_until expirado),
                    # reactivar TODOS los slots de la misma cuenta inmediatamente
                    if self._dead_until.get(chosen.label, 0.0) > 0:
                        acc = chosen.account_name
                        reactivated = 0
                        for c in self._clients:
                            if c.account_name == acc and self._dead_until.get(c.label, 0.0) > 0:
                                self._dead_until[c.label] = 0.0
                                reactivated += 1
                        self._fail_count[acc] = 0
                        if reactivated > 1:
                            log.info(f"  [{acc}] Re-evaluando — {reactivated} slots reactivados")
                    return chosen
                now  = time.time()
                wait = max(0.3, self._next_free_ts() - now)
                if now - self._last_sat_log >= 10:
                    n_busy = len(self._in_use)
                    n_cd   = sum(1 for c in self._clients
                                 if self._cooldown.get(c.label, 0.0) > now)
                    n_dead = sum(1 for c in self._clients if self._is_dead(c))
                    revivals, seen = [], set()
                    for c in self._clients:
                        if self._is_dead(c) and c.account_name not in seen:
                            secs = self._dead_until.get(c.label, 0.0) - now
                            revivals.append(f"{c.account_name}({secs:.0f}s)")
                            seen.add(c.account_name)
                    rev = (" re-eval:" + ",".join(revivals)) if revivals else ""
                    log.info(f"  Esperando slot "
                             f"(ocupados={n_busy} cooldown={n_cd} pausadas={n_dead}{rev})...")
                    self._last_sat_log = now
                self._cond.wait(timeout=min(wait, 3.0))

    def release(self, client):
        """Libera el slot con micro-cooldown para evitar martillar la misma cuenta."""
        with self._cond:
            self._in_use.discard(client.label)
            # OPTIMIZACIÓN: micro-pausa de 1.5 s entre generaciones del mismo slot
            self._cooldown[client.label] = max(
                self._cooldown.get(client.label, 0.0),
                time.time() + 1.5
            )
            # Si habia estado "muerto" y ahora funciono, resetear completamente
            if self._dead_until.get(client.label, 0.0) > 0:
                self._dead_until[client.label] = 0.0
                self._fail_count[client.account_name] = 0
                log.info(f"  [{client.label}] Reactivado tras re-evaluacion exitosa")
            self._cond.notify_all()

    def mark_ok(self, client):
        with self._cond:
            self._in_use.discard(client.label)
            self._cooldown[client.label]          = 0.0
            self._dead_until[client.label]        = 0.0
            self._fail_count[client.account_name] = 0
            self._cond.notify_all()

    def mark_ratelimited(self, client, cooldown: float = 65.0):
        with self._cond:
            self._in_use.discard(client.label)
            self._cooldown[client.label] = time.time() + cooldown
            log.warning(f"  [{client.label}] Rate-limit — pausa {cooldown:.0f}s")
            self._cond.notify_all()

    def mark_dead(self, client):
        """Cookie expirada: cooldown temporal con backoff exponencial."""
        with self._cond:
            acc   = client.account_name
            fails = self._fail_count.get(acc, 0) + 1
            self._fail_count[acc] = fails
            cd    = min(self.DEAD_COOLDOWN * (2 ** (fails - 1)), 30 * 60)
            until = time.time() + cd
            count = 0
            for c in self._clients:
                if c.account_name == acc:
                    self._dead_until[c.label] = until
                    self._in_use.discard(c.label)
                    count += 1
            log.warning(f"  [{acc}] Auth fallida #{fails} — "
                        f"{count} slots pausados {cd/60:.0f} min "
                        f"(re-evaluacion automatica)")
            self._cond.notify_all()

    def any_alive(self) -> bool:
        """Siempre True mientras exista algun slot con re-evaluacion pendiente."""
        with self._lock:
            # Con dead_until temporal siempre hay esperanza
            return len(self._clients) > 0

# ── Cliente ───────────────────────────────────────────────────────────────────

class GrokAccountClient:
    def __init__(self, account_name, slot_id, cookies_dict, session_meta,
                 prompt, aspect_ratio, video_length, resolution):
        self.account_name = account_name
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

    def _upload(self, image_path: Path):
        mime, _ = mimetypes.guess_type(str(image_path)); mime = mime or "image/jpeg"
        with open(image_path, "rb") as f: b64 = base64.b64encode(f.read()).decode()
        payload = {"fileName": image_path.name, "fileMimeType": mime,
                   "content": b64, "fileSource": "IMAGINE_SELF_UPLOAD_FILE_SOURCE"}
        log.info(f"[{self.label}] [1/3] Subiendo {image_path.name}...")
        for attempt in range(4):
            try:
                hdrs = {**_hdrs(session_meta=self.session_meta), "content-type": "application/json"}
                r = self.session.post(UPLOAD_URL, json=payload, headers=hdrs, timeout=60)
                if r.status_code in (401, 403): raise GrokAuthError(f"Upload auth {r.status_code}")
                if r.status_code == 429:
                    retry = int(r.headers.get("Retry-After", 65))
                    raise GrokRateLimit("Upload 429", retry_after=float(retry))
                if r.status_code in (500, 502, 503):
                    wait = 5 * (attempt + 1)
                    log.warning(f"[{self.label}] Upload {r.status_code} intento {attempt+1} — {wait}s...")
                    time.sleep(wait); continue
                if not r.ok:
                    log.error(f"[{self.label}] Upload {r.status_code}: {r.text[:200]}")
                    return None, None
                data = r.json()
                fid  = (data.get("fileMetadataId") or data.get("fileId") or
                        data.get("id")             or data.get("attachmentId"))
                furi = data.get("fileUri", "")
                uid  = self.session.cookies.get("x-userid", "x")
                aurl = (f"{ASSET_BASE}/{furi}" if furi else
                        data.get("url") or data.get("assetUrl") or
                        f"{ASSET_BASE}/users/{uid}/{fid}/content")
                log.info(f"[{self.label}] fileId={fid}")
                return fid, aurl
            except (GrokRateLimit, GrokAuthError): raise
            except Exception as e:
                if attempt < 3: time.sleep(5 * (attempt + 1)); continue
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
        try:
            for raw in response.iter_lines(decode_unicode=True):
                lines.append(raw or "")
                if not raw: continue
                payload = raw[5:].strip() if raw.startswith("data:") else raw.strip()
                if not payload or payload == "[DONE]": continue
                try: data = json.loads(payload)
                except: continue
                err = data.get("error") or data.get("message") or ""
                if isinstance(err, str):
                    err_l = err.lower()
                    if any(k in err_l for k in ("rate limit", "too many", "quota", "ratelimit")):
                        raise GrokRateLimit(f"SSE error: {err[:120]}", retry_after=65.0)
                    if any(k in err_l for k in ("unauthorized", "auth", "login", "forbidden")):
                        raise GrokAuthError(f"SSE auth: {err[:120]}")
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
                        log.info(f"[{self.label}] 100% url={video_url}"); break
                for media in (resp.get("generatedMedia") or result.get("generatedMedia") or []):
                    ru = media.get("url") or media.get("videoUrl") or media.get("mediaUrl") or ""
                    mt = (media.get("mediaType") or "").lower()
                    if ru:
                        u = _resolve(ru)
                        if "video" in mt or ru.endswith((".mp4", ".webm")):
                            video_url = u; break
        except requests.exceptions.ReadTimeout:
            # Stream se corto a mitad — usar lo que tengamos hasta ahora
            log.warning(f"[{self.label}] SSE ReadTimeout — usando datos parciales "
                        f"(vid={video_id} url={video_url})")
        except (GrokRateLimit, GrokAuthError):
            raise
        except Exception as e:
            log.warning(f"[{self.label}] SSE parse error: {e}")

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
        url      = f"{GROK_BASE}/rest/app-chat/conversations/{conv_id}/responses"
        deadline = time.time() + 600
        while time.time() < deadline:
            try:
                r = self.session.get(url, headers=_hdrs(session_meta=self.session_meta), timeout=30)
                if r.status_code == 429: raise GrokRateLimit("Poll 429", retry_after=65.0)
                if r.ok:
                    found = _deep(r.json())
                    if found: return found
            except GrokRateLimit: raise
            except Exception as e: log.warning(f"[{self.label}] Poll: {e}")
            time.sleep(6)
        log.error(f"[{self.label}] Poll timeout."); return None

    def animate(self, image_path: Path):
        # Verificacion rapida: si ya estamos marcados como muertos no intentar nada
        # (el pool no deberia asignarnos, pero por seguridad)
        fid, aurl = self._upload(image_path)
        if not fid: return None
        payload = self._build_payload(fid, aurl)
        log.info(f"[{self.label}] [2/3] Generando video...")

        # La imagen ya esta subida — reintentar solo el SSE si hay timeout,
        # sin volver a subir. timeout=(connect_s, read_s): 15s para conectar,
        # 300s entre chunks del stream (suficiente para pausas del modelo).
        for attempt in range(4):
            try:
                hdrs = {**_hdrs(session_meta=self.session_meta), "content-type": "application/json"}
                r = self.session.post(CONV_URL, json=payload, headers=hdrs,
                                      timeout=(15, 300), stream=True)
                if r.status_code in (401, 403): raise GrokAuthError(f"Conv auth {r.status_code}")
                if r.status_code == 429:
                    retry = int(r.headers.get("Retry-After", 65))
                    raise GrokRateLimit("Conv 429", retry_after=float(retry))
                if r.status_code in (500, 502, 503):
                    wait = 5 * (attempt + 1)
                    log.warning(f"[{self.label}] Conv {r.status_code} intento {attempt+1} — {wait}s...")
                    time.sleep(wait); continue
                if not r.ok:
                    log.error(f"[{self.label}] Conv {r.status_code}: {r.text[:200]}"); return None
                log.info(f"[{self.label}] [3/3] Leyendo SSE...")
                return self._parse_sse(r)

            except (GrokRateLimit, GrokAuthError): raise
            except requests.exceptions.ReadTimeout:
                wait = 10 * (attempt + 1)
                log.warning(f"[{self.label}] SSE timeout intento {attempt+1} — reintentando SSE en {wait}s "
                            f"(imagen ya subida, no se re-sube)...")
                time.sleep(wait)
            except Exception as e:
                wait = 5 * (attempt + 1)
                log.warning(f"[{self.label}] Animate intento {attempt+1}: {str(e)[:120]} — {wait}s...")
                time.sleep(wait)

        log.error(f"[{self.label}] Animate: 4 intentos SSE fallidos — imagen: {payload.get('message','')[:60]}")
        return None

    def download(self, url: str, dest: Path, max_404: int = 4) -> bool:
        """
        Backoff adaptativo para 404 de CDN.
        Si supera max_404 intentos consecutivos de 404, la URL se considera
        muerta (cuota agotada / video no renderizado) y retorna False para
        que el worker regenere la imagen con otra cuenta.
        """
        hdrs = _hdrs(session_meta=self.session_meta)
        hdrs["referer"] = "https://grok.com/"
        log.info(f"[{self.label}] Descargando -> {dest.name}")
        backoff_404 = [3, 5, 8, 12, 15, 20]
        deadline    = time.time() + 300   # OPTIMIZACIÓN: 300 s en vez de 600
        attempt     = 0
        consec_404  = 0
        while time.time() < deadline:
            attempt += 1
            try:
                with self.session.get(url, stream=True, timeout=180, headers=hdrs) as r:
                    if r.status_code == 404:
                        consec_404 += 1
                        # Despues de max_404 intentos la URL es definitivamente muerta
                        if consec_404 >= max_404:
                            log.warning(f"[{self.label}] URL muerta tras {consec_404} "
                                        f"404s consecutivos — se regenerara la imagen")
                            return False
                        wait = backoff_404[min(consec_404 - 1, len(backoff_404) - 1)]
                        log.info(f"[{self.label}] CDN 404 intento {attempt} ({consec_404}/{max_404}) — {wait}s...")
                        time.sleep(wait); continue
                    if r.status_code == 429: raise GrokRateLimit("Download 429", retry_after=65.0)
                    if r.status_code in (401, 403): raise GrokAuthError(f"Download auth {r.status_code}")
                    r.raise_for_status()
                    consec_404 = 0
                    with open(dest, "wb") as f:
                        for chunk in r.iter_content(65536): f.write(chunk)
                    size = dest.stat().st_size
                    if size < 10_000:
                        dest.unlink(missing_ok=True)
                        log.warning(f"[{self.label}] Archivo muy pequeño ({size}B) — reintentando...")
                        time.sleep(10); continue
                    log.info(f"[{self.label}] {dest.name} ({size//1024} KB) intento {attempt}")
                    return True
            except (GrokRateLimit, GrokAuthError): raise
            except requests.exceptions.HTTPError as e:
                code = e.response.status_code if e.response else "?"
                log.warning(f"[{self.label}] HTTP {code} intento {attempt}")
                time.sleep(20)
            except Exception as e:
                log.warning(f"[{self.label}] DL err {attempt}: {e}")
                time.sleep(15)
        log.error(f"[{self.label}] Timeout descarga: {url}")
        (BASE_DIR / "pending_downloads.txt").open("a").write(url + "\n")
        return False

# ── Login via Playwright ──────────────────────────────────────────────────────

def _login_account(folder):
    """
    Login manual con perfil temporal limpio.
    Sin flags anti-bot — browser completamente normal.
    El usuario inicia sesion y presiona ENTER para capturar las cookies.
    """
    import shutil
    from playwright.sync_api import sync_playwright

    temp_profile = Path(f"/tmp/grok_login_{folder.name}")
    if temp_profile.exists():
        shutil.rmtree(temp_profile)
    temp_profile.mkdir(parents=True)

    captured = {}
    result   = False

    print(f"\n{'='*52}")
    print(f"  Cuenta: {folder.name}")
    print(f"{'='*52}")

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(temp_profile),
            headless=False,
            args=["--no-sandbox"],
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_req(req):
            h   = req.headers
            sid = h.get("x-statsig-id", "")
            if sid and not captured.get("statsig_id"):
                captured["statsig_id"] = sid
            bag = h.get("baggage", "")
            if "sentry-release=" in bag and not captured.get("sentry_release"):
                for part in bag.split(","):
                    if part.strip().startswith("sentry-release="):
                        captured["sentry_release"] = part.split("=", 1)[1].strip()
        page.on("request", on_req)

        try:
            page.goto("https://grok.com/imagine", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass

        print(f"\n  *** Inicia sesion con [{folder.name}] en el browser ***")
        print(f"  Cuando estes dentro de grok.com/imagine presiona ENTER...\n")
        input()

        ck_dict = {c["name"]: c["value"] for c in ctx.cookies("https://grok.com")}
        if not ck_dict.get("sso"):
            print(f"  Sin cookie sso — navega a grok.com y presiona ENTER de nuevo")
            try: page.goto("https://grok.com/imagine", timeout=30000)
            except Exception: pass
            input()
            ck_dict = {c["name"]: c["value"] for c in ctx.cookies("https://grok.com")}

        if not ck_dict.get("sso"):
            print(f"  No se detecto sesion en [{folder.name}] — saltando")
            ctx.close()
            shutil.rmtree(temp_profile, ignore_errors=True)
            return False

        raw   = ctx.cookies("https://grok.com")
        clist = [{"name": c["name"], "value": c["value"], "domain": ".grok.com",
                  "path": "/", "httpOnly": False, "secure": True}
                 for c in raw]
        (folder / "cookies_auto.json").write_text(json.dumps(clist, indent=2))
        (folder / "session_meta.json").write_text(json.dumps(captured, indent=2))
        print(f"  Cookies guardadas: {[c['name'] for c in raw]}")
        ctx.close()
        result = True

    shutil.rmtree(temp_profile, ignore_errors=True)
    return result

def _login_all(account_folders):
    print(f"\n{'='*52}")
    print(f"  LOGIN — {len(account_folders)} cuenta(s)")
    print(f"  Se abrira un browser por cada cuenta.")
    print(f"  Inicia sesion y presiona ENTER en cada uno.")
    print(f"{'='*52}\n")
    ok = 0
    for folder in account_folders:
        if _login_account(folder):
            ok += 1
    print(f"\n  Login completado: {ok}/{len(account_folders)} cuentas OK")

# ── Crear clientes por cuenta ─────────────────────────────────────────────────

def _make_clients(folder, slots, prompt, aspect_ratio, video_length, resolution):
    cookies_file = folder / "cookies_auto.json"
    meta_file    = folder / "session_meta.json"
    if not cookies_file.exists():
        log.warning(f"[{folder.name}] Sin cookies_auto.json — omitiendo"); return []
    cookies = {c["name"]: c["value"]
               for c in json.loads(cookies_file.read_text()) if "name" in c}
    meta    = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    clients = [GrokAccountClient(folder.name, i, cookies, meta,
                                 prompt, aspect_ratio, video_length, resolution)
               for i in range(1, slots + 1)]
    log.info(f"  [{folder.name}] {slots} slot(s) — statsig={'OK' if meta.get('statsig_id') else 'NO'}")
    return clients

# ── Helper ────────────────────────────────────────────────────────────────────

def _sleep(secs: float, cancel_ev: threading.Event):
    deadline = time.time() + secs
    while time.time() < deadline:
        if cancel_ev.is_set(): return
        time.sleep(min(1.0, deadline - time.time()))

# ── Pipeline 1: Generación (upload + SSE) ────────────────────────────────────
# Cada slot se libera en cuanto obtiene la URL, SIN esperar la descarga.
# Las descargas van a una cola separada para no bloquear la generación.

def _worker(idx: int, img: Path, total: int,
            pool: GrokPool, output_dir: Path,
            success_count: list, lock: threading.Lock,
            cancel_ev: threading.Event):
    """
    Un hilo por imagen. Dos fases separadas:
    Fase 1 — GENERACIÓN: pide slot al pool, upload + SSE, libera slot
              INMEDIATAMENTE al obtener la URL.
    Fase 2 — DESCARGA: sin slot, corre en el mismo hilo mientras otros
              hilos ya están generando sus propias imágenes.
    Así los slots siempre están libres para generar y las descargas nunca
    bloquean la generación.
    """
    dest    = output_dir / f"{img.stem}.mp4"
    attempt = 0

    if dest.exists() and dest.stat().st_size > 10_000:
        log.info(f"  [{idx:03d}/{total}] Ya existe — skip")
        with lock: success_count[0] += 1
        return

    while not cancel_ev.is_set():
        attempt += 1

        # OPTIMIZACIÓN: cortar si se superan MAX_GEN_ATTEMPTS
        if attempt > MAX_GEN_ATTEMPTS:
            log.error(f"  [{idx:03d}/{total}] Fallo definitivo tras {MAX_GEN_ATTEMPTS} intentos — {img.name}")
            return

        # ── Fase 1: GENERACIÓN (necesita slot) ───────────────────────────────
        client = pool.get_client(cancel_ev)
        if client is None:
            return  # cancelado

        log.info(f"[{client.label}] [{idx:03d}/{total}] intento {attempt}: {img.name}")
        url = None
        try:
            url = client.animate(img)
            # Liberar slot ANTES de descargar — el slot ya no es necesario
            pool.release(client)

        except GrokRateLimit as e:
            pool.mark_ratelimited(client, e.retry_after)
            attempt -= 1  # no contar el rate-limit como intento fallido
            continue
        except GrokAuthError:
            pool.mark_dead(client)
            if not pool.any_alive():
                log.error("  Sin slots disponibles. Verifica --login.")
                cancel_ev.set()
            continue
        except Exception as e:
            pool.release(client)
            wait = min(10 * attempt, 40)
            log.error(f"[{client.label}] [{idx:03d}] Gen error: {str(e)[:120]} — {wait}s")
            _sleep(wait, cancel_ev)
            continue

        if not url:
            wait = min(10 * attempt, 40)
            log.warning(f"[{client.label}] [{idx:03d}] Sin URL — {wait}s")
            _sleep(wait, cancel_ev)
            continue

        # Capturar cookies ANTES de liberar el slot — las necesita la descarga
        dl_session = requests.Session()
        for name, value in client.cookies_dict.items():
            dl_session.cookies.set(name, value, domain=".grok.com")
        dl_session.cookies.set("_ga", "GA1.1.1", domain=".grok.com")  # evita redirect

        # ── Fase 2: DESCARGA (sin slot, otros hilos generan en paralelo) ─────
        ok = _download_url(url, dest, label=f"{client.label}", session=dl_session)
        if ok:
            with lock:
                success_count[0] += 1
            log.info(f"  [{idx:03d}] OK — {success_count[0]}/{total} completados")
            return
        # URL muerta → volver a generar (con cualquier cuenta disponible)
        log.warning(f"  [{idx:03d}] URL muerta — regenerando")

def _download_url(url: str, dest: Path, label: str,
                  session: requests.Session = None,
                  max_404: int = 4) -> bool:       # OPTIMIZACIÓN: max_404 = 4
    """Descarga standalone con session autenticada."""
    hdrs = _hdrs()
    hdrs["referer"] = "https://grok.com/"
    backoff_404 = [3, 5, 8, 12, 15, 20]
    deadline    = time.time() + 300              # OPTIMIZACIÓN: 300 s en vez de 600
    consec_404  = 0
    local_att   = 0
    sess        = session or requests.Session()

    while time.time() < deadline:
        local_att += 1
        try:
            with sess.get(url, stream=True, timeout=180, headers=hdrs) as r:
                if r.status_code == 404:
                    consec_404 += 1
                    if consec_404 >= max_404:
                        log.warning(f"  [{label}] URL muerta ({consec_404} 404s)")
                        return False
                    wait = backoff_404[min(consec_404 - 1, len(backoff_404) - 1)]
                    log.info(f"  [{label}] CDN 404 ({consec_404}/{max_404}) — {wait}s")
                    time.sleep(wait); continue
                if r.status_code == 429:
                    raise GrokRateLimit("Download 429", retry_after=65.0)
                r.raise_for_status()
                consec_404 = 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(65536): f.write(chunk)
                size = dest.stat().st_size
                if size < 10_000:
                    dest.unlink(missing_ok=True)
                    time.sleep(10); continue
                log.info(f"  [{label}] {dest.name} ({size//1024} KB) intento {local_att}")
                return True
        except GrokRateLimit: raise
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response else "?"
            log.warning(f"  [{label}] HTTP {code}")
            time.sleep(20)
        except Exception as e:
            log.warning(f"  [{label}] DL err: {e}")
            time.sleep(15)

    log.error(f"  [{label}] Timeout descarga: {url}")
    (BASE_DIR / "pending_downloads.txt").open("a").write(url + "\n")
    return False

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Grok Multi-Account Animator v4",
        formatter_class=argparse.RawTextHelpFormatter
    )
    p.add_argument("images",        help="Carpeta con imagenes")
    p.add_argument("--prompt",      default="Animate this image with smooth natural motion")
    p.add_argument("--aspect-ratio",default="2:3",
                   choices=["1:1","16:9","9:16","4:3","3:4","2:3","3:2"])
    p.add_argument("--video-length",type=int, default=6)
    p.add_argument("--resolution",  default="480p", choices=["480p","720p","1080p"])
    p.add_argument("--login", action="store_true",
                   help=(
                       "Abre Chrome para iniciar sesion en cada cuenta.\n"
                       "Crea las carpetas primero:\n"
                       "  mkdir -p accounts/cuenta1 accounts/cuenta2 accounts/cuenta3\n"
                       "  mkdir -p accounts/cuenta4 accounts/cuenta5\n"
                       "Luego ejecuta: python3 grok_multi.py /fotos --login\n"
                       "Se abrira un browser por cuenta — inicia sesion en cada uno."
                   ))
    p.add_argument("--output-dir",  default="")
    p.add_argument("--filter-file", default="")
    p.add_argument("--slots", type=int, default=1, metavar="N",
                   help=(
                       "Videos en paralelo POR cuenta [1-12, default: 1]\n"
                       "  --slots 3 -> 3 videos/cuenta (recomendado)\n"
                       "Total = cuentas x slots (ej: 5 cuentas x 3 = 15 en paralelo)"
                   ))
    args = p.parse_args()

    if not 1 <= args.slots <= SLOTS_MAX:
        p.error(f"--slots debe estar entre 1 y {SLOTS_MAX}")

    output_dir = Path(args.output_dir).resolve() if args.output_dir else DOWNLOADS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    if not ACCOUNTS_DIR.exists():
        log.error(f"No existe {ACCOUNTS_DIR} -> crea: accounts/cuenta1/ ... accounts/cuenta5/")
        sys.exit(1)

    account_folders = sorted([d for d in ACCOUNTS_DIR.iterdir() if d.is_dir()])
    if not account_folders:
        log.error(f"Sin carpetas en {ACCOUNTS_DIR}")
        log.error("Crea las carpetas de cuentas primero:")
        log.error("  mkdir -p accounts/cuenta1 accounts/cuenta2 accounts/cuenta3")
        log.error("  mkdir -p accounts/cuenta4 accounts/cuenta5")
        sys.exit(1)

    if args.login:
        _login_all(account_folders)
        sys.exit(0)

    all_clients = []
    for folder in account_folders:
        all_clients.extend(_make_clients(folder, args.slots, args.prompt,
                                         args.aspect_ratio, args.video_length,
                                         args.resolution))
    if not all_clients:
        log.error("Sin clientes disponibles. Ejecuta con --login primero."); sys.exit(1)

    images = get_images(args.images, filter_file=args.filter_file)
    total  = len(images)

    log.info(f"\n{'='*65}")
    log.info(f"  Imagenes : {total} (ordenadas por fecha de creacion)")
    log.info(f"  Cuentas  : {len(account_folders)} x {args.slots} slot(s) "
             f"= {len(all_clients)} videos en paralelo")
    log.info(f"  Slots    : {[c.label for c in all_clients]}")
    log.info(f"  Prompt   : {args.prompt[:60]}")
    log.info(f"  Aspect   : {args.aspect_ratio} | {args.video_length}s | {args.resolution}")
    log.info(f"  Salida   : {output_dir}")
    log.info(f"{'='*65}\n")

    pool          = GrokPool(all_clients)
    cancel_ev     = threading.Event()
    success_count = [0]
    lock          = threading.Lock()

    # OPTIMIZACIÓN: workers = min(imagenes, slots*2) — evita saturar el servidor
    n_workers = min(total, len(all_clients) * 2)
    log.info(f"  Thread pool: {n_workers} workers ({len(all_clients)} slots x 2, cap={total})")

    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futures = [
            ex.submit(_worker, idx, img, total, pool, output_dir,
                      success_count, lock, cancel_ev)
            for idx, img in enumerate(images, 1)
        ]
        try:
            for f in as_completed(futures):
                try: f.result()
                except Exception as e: log.error(f"Worker crash: {e}")
        except KeyboardInterrupt:
            log.info("  Interrumpido por usuario")
            cancel_ev.set()

    log.info(f"\n{'='*65}")
    log.info(f"  Completado: {success_count[0]}/{total} videos en {output_dir}")
    log.info(f"{'='*65}")

if __name__ == "__main__":
    main()
