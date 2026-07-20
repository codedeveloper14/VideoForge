"""Cliente para Vibes (vibes.ai) -- reemplaza a Meta AI como backend de generacion de
video (Meta migro la feature ahi). Todo lo de abajo esta verificado contra trafico
real, sin sesion, con curl -- no inventado:

  GET https://vibes.ai/api/meta-oidc/start
    -> 307 Location: https://auth.meta.com/oidc?app_id=1301537925115840&
       scope=openid+linking&response_type=code&redirect_uri=https://auth.meta.ai/ecto&
       state=<csrf+redirect_to=vibes.ai/api/meta-oidc/callback>
       Set-Cookie: oauth_csrf_token=...; HttpOnly; Secure; SameSite=lax
    Confirma: login via OIDC contra auth.meta.com, NO se reusa una cookie de
    meta.ai/facebook.com directamente (a diferencia del viejo flujo de Meta AI).

  GET https://vibes.ai/api/auth/me           (sin cookie) -> 401
    {"error":"No cookie value provided","errorType":"NoToken"}
  GET https://vibes.ai/api/system-status     (sin cookie) -> 401
    Set-Cookie: meta_session=; Max-Age=0        <- nombre real de la cookie de sesion
    {"success":false,"error":{"code":"SESSION_EXPIRED",...},"errorType":"NoToken"}

  Endpoints reales (grep sobre los bundles JS servidos por vibes.ai, no adivinados):
    /api/generation-batches/   REST -- crear/consultar un batch de generacion
    /api/playables             REST -- resultado generado (401 sin sesion)
    /api/projects              REST -- 401 sin sesion
    /api/upload-asset          POST (405 en GET)
    /api/upload-video-direct   POST (405 en GET)
    /api/meta-graphql          POST (405 en GET) -- proxy same-origin a GraphQL de
                                Meta; el browser real NUNCA llama a meta.ai/api/graphql
                                directo como hacia el viejo meta_gql_client.py.

  Capturado por el usuario via "Copy as cURL" de un POST real que SI funciono
  (2026-07-16) -- este es el body completo real, no la version simplificada de un
  intento anterior que daba 500 "Failed to create generation batch" por faltarle
  campos:

    POST https://www.vibes.ai/api/generation-batches
      Origin/Referer: https://www.vibes.ai (mismo origen)
      body real completo:
        {
          "id": "batch-019f6922-4439-7713-b335-f2e4dd7180b5",   <- generado CLIENTE, UUIDv7
          "type": "videos",
          "prompt": "...",
          "timestamp": "2026-07-16T04:14:41.210Z",
          "content": [
            {"id": "batch-<id>-content-0", "type": "videos", "isLoading": true},
            {"id": "batch-<id>-content-1", "type": "videos", "isLoading": true},
            {"id": "batch-<id>-content-2", "type": "videos", "isLoading": true},
            {"id": "batch-<id>-content-3", "type": "videos", "isLoading": true}
          ],
          "isComplete": false,
          "config": {
            "directGeneration": true, "promptModel": "gemini-2.5-flash",
            "aspectRatio": "9:16", "imageModel": "midjen-base",
            "videoModel": "midjen-short", "resolution": "480p", "batchVariation": true
          },
          "promptModel": "gemini-2.5-flash",   <- SI, duplicado tambien a nivel raiz
          "imageModel": "midjen-base",
          "videoModel": "midjen-short",
          "generationStartTime": "2026-07-16T04:14:41.210Z",
          "isDirectGeneration": true,
          "projectId": "..."
        }
    GET  /api/generation-batches/{batchId}/stream   Accept: text/event-stream (SSE)
      -> evento final: {"isComplete": true, "content": [...]}
         cada item de "content" trae content[i]["videoUrl"] y content[i]["imageUrl"].

  El batch_id NO lo devuelve el server -- lo genera el cliente (UUIDv7, "batch-"
  + uuid.uuid7()) ANTES del POST, junto con 4 placeholders en "content" (uno por
  batchVariation), y el POST es basicamente "guardame este objeto en progreso".
  projectId es obligatorio (confirmado: sin el, 500; con ensure_project(), OK) --
  este cURL real confirma que faltaban id/content/timestamps, no projectId.

  El body real no manda ninguna imagen de referencia (nada de assetId/upload-asset)
  -- "imageModel"/"videoModel" generan la imagen y el video en el mismo batch, no
  animan una imagen subida. Por eso generate_video() no usa UPLOAD_ASSET_URL."""

import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from src.utils.logger import get_logger
from src.utils.paths import get_vibes_cookies_dir, get_vibes_profiles_dir

logger = get_logger(__name__)

# www.vibes.ai, NO vibes.ai a secas -- BUG REAL encontrado en vivo: arrancar el
# login en el dominio sin www deja el cookie meta_session con domain=vibes.ai
# (host-only, confirmado inspeccionando el cookie guardado). Chromium (estricto)
# nunca manda esa cookie a www.vibes.ai -> 401 SESSION_EXPIRED inmediato al generar,
# incluso con sesion recien logueada. requests, mas laxo con el dominio, SI la
# mandaba -> por eso el POST de creacion daba 200 pero la generacion en si fallaba
# ("Generation failed to start") -- probablemente el mismo problema de fondo,
# el server no reconoce del todo una sesion cross-domain. www.vibes.ai/api/meta-oidc/start
# devuelve el mismo 307, pero con redirect_to=https://www.vibes.ai/api/meta-oidc/callback
# (confirmado con curl) -- todo el round-trip queda en www, cookie scoped correcto.
BASE_URL = "https://www.vibes.ai"
OIDC_START_URL = f"{BASE_URL}/api/meta-oidc/start"
SESSION_COOKIE_NAME = "meta_session"  # cookie de VIBES, pese al nombre -- no es la de meta.ai

ME_URL = f"{BASE_URL}/api/auth/me"
UPLOAD_ASSET_URL = f"{BASE_URL}/api/upload-asset"
# Endpoint real de subida de imagen de referencia ("Ingredientes" -> "Upload media"
# en la UI), confirmado en vivo (2026-07-17) via DevTools -- NO es UPLOAD_ASSET_URL
# (esa nunca se vio usada en trafico real). multipart/form-data con campos "file"
# (binario) + "filename". Devuelve {"mediaEntId","cdnUrl","dimensions",
# "aspectRatio","uploadToken"} -- mediaEntId/cdnUrl son los mismos valores que
# manda el batch de generacion como setting_image_ent_ids/setting_image_url.
UPLOAD_MEDIA_URL = f"{BASE_URL}/api/upload-media"
PROJECTS_URL = f"{BASE_URL}/api/projects"
GENERATION_BATCHES_URL = f"{BASE_URL}/api/generation-batches"

# Debe coincidir EXACTO con VIBES_ACCOUNT_HASH en extensions/flow_extension/vibes_content.js.
# Un solo hash fijo -- a diferencia de Flow (10 cuentas rotando), Vibes hoy es una
# sola sesion por cliente, no hace falta resolver identidad dinamicamente.
# Prefijo "vibes:" -- namespacea el hash frente al de Flow (que usa "flow:", ver
# flow_service.account_hash) en el bridge compartido, para que background.js pueda
# verificar que un hash "vibes:*" solo se registre desde una pestaña de vibes.ai.
VIBES_ACCOUNT_HASH = "vibes:default"


def _stream_url(batch_id: str) -> str:
    return f"{GENERATION_BATCHES_URL}/{batch_id}/stream"


def _NoOpLog(msg: str) -> None:
    pass


def _iso_now_ms() -> str:
    """ "2026-07-16T04:14:41.210Z" -- mismo formato que "timestamp"/
    "generationStartTime" en el body real capturado."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _new_batch_id() -> str:
    """batch_id NO lo devuelve el server -- lo genera el cliente antes del POST.
    Formato real: "batch-" + UUIDv7 (confirmado via cURL real, no un UUID
    cualquiera: el tercer grupo empieza en "7", version UUIDv7)."""
    return f"batch-{uuid.uuid7()}"


# Igual al cURL real capturado (2026-07-16) -- el UA/sec-ch-ua viejo (Chrome/124,
# sin client hints) es un fingerprint inconsistente que un sistema anti-abuso puede
# usar para degradar/rechazar el request; "Generation failed to start" en el primer
# intento con el body completo coincidio con este UA desactualizado.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)
_SEC_CH_UA = '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"'


def cookie_path(account_idx: int) -> Path:
    return get_vibes_cookies_dir() / f"account_{account_idx}.json"


def profile_dir(account_idx: int) -> Path:
    return get_vibes_profiles_dir() / f"vibes_profile_{account_idx}"


def load_cookies(account_idx: int) -> list[dict] | None:
    path = cookie_path(account_idx)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_cookies(account_idx: int, cookie_list: list[dict]) -> None:
    cookie_path(account_idx).write_text(json.dumps(cookie_list, indent=2), encoding="utf-8")


def _requests_session_from_cookies(cookie_list: list[dict]) -> requests.Session:
    sess = requests.Session()
    sess.headers.update(
        {
            "user-agent": _UA,
            "sec-ch-ua": _SEC_CH_UA,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
    )
    for c in cookie_list:
        sess.cookies.set(c["name"], c["value"], domain=c.get("domain", "www.vibes.ai"))
    return sess


def check_session(cookie_list: list[dict]) -> bool:
    """True si la cookie guardada todavia autentica contra vibes.ai. Verificado: sin
    cookie /api/auth/me da 401 {"errorType":"NoToken"} -- cualquier otra cosa (200,
    o un 401 con otro errorType) se toma como sesion valida/indeterminada en vez de
    asumir inválida, ya que no se pudo capturar la forma exacta del 200 real."""
    try:
        r = _requests_session_from_cookies(cookie_list).get(ME_URL, timeout=15)
        if r.status_code == 200:
            return True
        if r.status_code == 401:
            try:
                return r.json().get("errorType") != "NoToken"
            except Exception:
                return False
        return False
    except Exception as exc:
        logger.info("vibes_client.check_session error: %s", exc)
        return False


def _project_id_path(account_idx: int) -> Path:
    return get_vibes_cookies_dir() / f"account_{account_idx}_project.txt"


def list_projects(cookie_list: list[dict]) -> list[dict]:
    """GET /api/projects -- confirmado en vivo: {"success":true,"projects":[...],
    "page":{...}}, cada proyecto con "id"/"name"/"createdAt"/etc."""
    r = _requests_session_from_cookies(cookie_list).get(PROJECTS_URL, timeout=15)
    r.raise_for_status()
    return r.json().get("projects", [])


def create_project(cookie_list: list[dict], log: Callable[[str], None] = _NoOpLog) -> str | None:
    """POST /api/projects -- el body real todavia NO esta confirmado (no capturado
    en DevTools); se manda un POST vacio, patron comun para "crear proyecto
    default" en APIs REST. Se loguea la respuesta cruda completa para detectar de
    inmediato si Vibes exige campos que no se estan mandando."""
    sess = _requests_session_from_cookies(cookie_list)
    try:
        r = sess.post(PROJECTS_URL, json={}, timeout=30)
        log(f"create_project HTTP {r.status_code}: {r.text[:500]}")
        if not r.ok:
            return None
        data = r.json()
    except Exception as exc:
        log(f"create_project fallo: {exc}")
        return None
    proj = data.get("project") if isinstance(data.get("project"), dict) else data
    return proj.get("id")


def ensure_project(
    cookie_list: list[dict], account_idx: int, log: Callable[[str], None] = _NoOpLog
) -> str | None:
    """Devuelve un projectId reutilizable para esta cuenta: (1) cache en disco si ya
    se resolvio antes (persiste entre corridas, no solo en memoria del proceso),
    (2) si no, el primero de GET /api/projects si ya existe alguno, (3) si no hay
    ninguno, lo crea via POST /api/projects. Necesario porque POST
    /api/generation-batches sin projectId da HTTP 500 "Failed to create generation
    batch" -- confirmado en vivo, projectId es obligatorio."""
    cache_path = _project_id_path(account_idx)
    if cache_path.is_file():
        cached = cache_path.read_text(encoding="utf-8").strip()
        if cached:
            return cached

    try:
        projects = list_projects(cookie_list)
    except Exception as exc:
        log(f"ensure_project: list_projects fallo: {exc}")
        projects = []

    if projects:
        project_id = projects[0].get("id")
        log(f"ensure_project: reutilizando proyecto existente {project_id}")
    else:
        project_id = create_project(cookie_list, log=log)
        log(f"ensure_project: proyecto nuevo creado {project_id}")

    if project_id:
        cache_path.write_text(project_id, encoding="utf-8")
    return project_id


def login_account_managed(account_idx: int, log=lambda m: None) -> None:
    """Login interactivo (perfil Playwright persistente): navega directo al arranque
    del OIDC real (OIDC_START_URL), el usuario completa el login de Meta en la
    ventana real, y se espera a que aparezca la cookie SESSION_COOKIE_NAME
    ("meta_session") en el contexto de vibes.ai -- confirma que el callback OIDC
    termino y Vibes emitio su propia sesion. Mismo patron que
    meta_browser.login_account_managed(), adaptado a un solo dominio de destino
    (vibes.ai) en vez de la lista de dominios meta.ai/facebook.com."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("[ERROR] Playwright no instalado.")
        return

    from src.infrastructure.ai_providers.chrome_launcher import find_chromium_exe

    prof_dir = str(profile_dir(account_idx))
    Path(prof_dir).mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as pw:
            exe = find_chromium_exe()
            ctx = pw.chromium.launch_persistent_context(
                prof_dir,
                headless=False,
                executable_path=exe,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--no-first-run"],
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            log(f"[Vibes Acc{account_idx + 1}] Abriendo login (OIDC contra auth.meta.com)...")
            try:
                page.goto(OIDC_START_URL, timeout=30000)
            except Exception:
                pass

            deadline = time.time() + 300
            last_log = 0.0
            while time.time() < deadline:
                time.sleep(2)
                try:
                    cookies = ctx.cookies(BASE_URL)
                except Exception:
                    cookies = []
                session_c = next((c for c in cookies if c["name"] == SESSION_COOKIE_NAME), None)
                if session_c and session_c.get("value"):
                    save_cookies(
                        account_idx,
                        [
                            {
                                "name": c["name"],
                                "value": c["value"],
                                "domain": c.get("domain", urlparse(BASE_URL).hostname),
                                "path": c.get("path", "/"),
                            }
                            for c in cookies
                        ],
                    )
                    log(f"[OK] [Vibes Acc{account_idx + 1}] Sesion guardada ({len(cookies)} cookies).")
                    break
                now = time.time()
                if now - last_log > 15:
                    last_log = now
                    log(f"[Vibes Acc{account_idx + 1}] Esperando login... ({[c['name'] for c in cookies]})")

            ctx.close()
    except Exception as exc:
        logger.exception("vibes_client.login_account_managed excepcion")
        log(f"[Vibes Acc{account_idx + 1}] EXCEPCION: {exc}")


def _handle_complete_event(evt: dict, log: Callable[[str], None] = _NoOpLog) -> list[dict] | None:
    """Observado en vivo (2026-07-16), evento real de completado:
    {"success": true, "isComplete": true, "items": [{"id":..., "isLoading": false,
    "videoUrl":..., "videoHandle":..., "imageUrl":..., "imageHandle":..., "data":...,
    "error":...}, ...]} -- la clave real es "items", NO "content" (la descripcion
    original decia "content"; se prueban ambas por si el nombre cambia segun el tipo
    de batch, pero "items" es lo que de verdad llego). Los items fallidos traen
    "error" en vez de "videoUrl" -- se loguean para que un fallo real (cuota, cuenta,
    modelo) se vea explicito en vez de perderse como "sin video"."""
    if evt.get("isComplete") is not True:
        return None
    items = evt.get("items")
    if not isinstance(items, list):
        items = evt.get("content")
    if not isinstance(items, list):
        return []
    videos = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("videoUrl"):
            videos.append({"video_url": item.get("videoUrl"), "image_url": item.get("imageUrl")})
        elif item.get("error"):
            log(f"item {item.get('id')} fallo: {item.get('error')}")
    return videos


def _build_create_body(
    prompt: str,
    project_id: str,
    aspect_ratio: str = "9:16",
    resolution: str = "480p",
    prompt_model: str = "gemini-2.5-flash",
    image_model: str = "midjen-base",
    video_model: str = "midjen-short",
    batch_variation: bool = True,
    ref_image: dict | None = None,
) -> dict:
    """Body real completo capturado via cURL 2026-07-16. batch_id/content NO los
    devuelve el server -- se generan aca y se mandan ya armados; el POST guarda este
    objeto "en progreso" (isComplete=false). Compartido entre generate_video()
    (requests puro -- confirmado que NO alcanza para que la generacion arranque de
    verdad, solo crea el batch) y generate_video_via_bridge() (via la extension en
    un browser real, el camino que si funciona).

    ref_image (opcional): {"media_ent_id": str, "cdn_url": str} devuelto por
    upload_reference_image_via_bridge(). Confirmado en vivo (2026-07-17, cURL real
    capturado con "Add from projects" en la UI de Vibes): con imagen de referencia
    el body agrega "setting_image_ent_ids"/"setting_image_url" (los mismos
    mediaEntId/cdnUrl que devuelve /api/upload-media) y "promptSegments"
    ([{"segmentType":"raw_text","text":prompt}]) ademas del "prompt" normal -- sin
    imagen ninguno de estos 3 campos aparece."""
    batch_id = _new_batch_id()
    now = _iso_now_ms()
    n_variations = 4 if batch_variation else 1
    content_placeholders = [
        {"id": f"{batch_id}-content-{i}", "type": "videos", "isLoading": True} for i in range(n_variations)
    ]
    body = {
        "id": batch_id,
        "type": "videos",
        "prompt": prompt,
        "timestamp": now,
        "content": content_placeholders,
        "isComplete": False,
        "config": {
            "directGeneration": True,
            "promptModel": prompt_model,
            "aspectRatio": aspect_ratio,
            "imageModel": image_model,
            "videoModel": video_model,
            "resolution": resolution,
            "batchVariation": batch_variation,
        },
        # Si, duplicados a nivel raiz tambien -- asi viene en el body real.
        "promptModel": prompt_model,
        "imageModel": image_model,
        "videoModel": video_model,
        "generationStartTime": now,
        "isDirectGeneration": True,
        "projectId": project_id,
    }
    if ref_image and ref_image.get("media_ent_id") and ref_image.get("cdn_url"):
        body["setting_image_ent_ids"] = ref_image["media_ent_id"]
        body["setting_image_url"] = ref_image["cdn_url"]
        body["promptSegments"] = [{"segmentType": "raw_text", "text": prompt}]
    return body


def generate_video(
    cookie_list: list[dict],
    prompt: str,
    project_id: str | None = None,
    aspect_ratio: str = "9:16",
    resolution: str = "480p",
    prompt_model: str = "gemini-2.5-flash",
    image_model: str = "midjen-base",
    video_model: str = "midjen-short",
    batch_variation: bool = True,
    out_dir: str | None = None,
    timeout_sec: int = 300,
    slot_id: int = 0,
    log: Callable[[str], None] = _NoOpLog,
) -> dict:
    """Genera video(s) via Vibes usando requests puro (sin browser).

    CONFIRMADO EN VIVO (2026-07-16): esta funcion crea el batch bien (HTTP 200,
    id real), pero la generacion en si SIEMPRE falla con "Generation failed to
    start. Please try again." en los 4 items, con la misma cookie que funciona
    perfecto generando a mano en Chrome normal. No es la cuenta (el usuario genero
    3 videos de prueba a mano con la misma sesion), no es projectId, no es el
    dominio de la cookie, no es el User-Agent -- se probaron los 4 y ninguno lo
    explica. Conclusion: Vibes detecta que el request no viene de un browser real
    (fingerprint/automatizacion) y bloquea el arranque de la generacion aunque la
    sesion sea 100% valida. Usar generate_video_via_bridge() en su lugar, que hace
    el fetch() desde dentro de una pestaña real de Chrome via la extension -- esta
    funcion queda solo para diagnostico (confirmar creacion de batch, inspeccionar
    create_response) o por si Vibes cambia su deteccion en el futuro."""
    if not project_id:
        result_no_proj = {
            "videos": [],
            "batch_id": None,
            "error": "project_id requerido -- usar vibes_client.ensure_project() primero",
            "create_response": None,
            "final_event": None,
        }
        return result_no_proj

    create_body = _build_create_body(
        prompt, project_id, aspect_ratio, resolution, prompt_model, image_model, video_model, batch_variation
    )
    batch_id = create_body["id"]
    n_variations = len(create_body["content"])

    result: dict = {
        "videos": [],
        "batch_id": batch_id,
        "error": None,
        "create_response": None,
        "final_event": None,
    }
    sess = _requests_session_from_cookies(cookie_list)

    try:
        r = sess.post(
            GENERATION_BATCHES_URL,
            json=create_body,
            headers={
                "Origin": "https://www.vibes.ai",
                "Referer": f"https://www.vibes.ai/projects/{project_id}",
            },
            timeout=30,
        )
        log(f"[S{slot_id}] POST generation-batches id={batch_id} HTTP {r.status_code}")
        log(f"[S{slot_id}] respuesta: {r.text[:800]}")
        if not r.ok:
            result["error"] = f"Creacion de batch fallo: HTTP {r.status_code}: {r.text[:300]}"
            return result
        if r.text:
            try:
                result["create_response"] = r.json()
            except Exception:
                pass
    except Exception as exc:
        result["error"] = f"Creacion de batch fallo: {exc}"
        return result

    log(
        f"[S{slot_id}] batch creado id={batch_id} projectId={project_id} content={n_variations} placeholder(s)"
    )

    # ── 2-4. Consumir SSE hasta {"isComplete": true, "content": [...]} ──────
    try:
        r = sess.get(
            _stream_url(batch_id),
            headers={"Accept": "text/event-stream"},
            stream=True,
            timeout=(15, timeout_sec),
        )
        if not r.ok:
            result["error"] = f"Stream SSE HTTP {r.status_code}: {r.text[:300]}"
            return result

        videos: list[dict] | None = None
        data_lines: list[str] = []
        deadline = time.time() + timeout_sec

        def _handle_line_group(raw_data: str) -> list[dict] | None:
            if not raw_data:
                return None
            try:
                evt = json.loads(raw_data)
            except Exception:
                log(f"[S{slot_id}] evento SSE no-JSON: {raw_data[:200]}")
                return None
            log(f"[S{slot_id}] evento SSE: {json.dumps(evt)[:300]}")
            found = _handle_complete_event(evt, log=log)
            if found is not None:
                result["final_event"] = evt
            return found

        for line in r.iter_lines(decode_unicode=True):
            if time.time() > deadline:
                result["error"] = f"Timeout ({timeout_sec}s) esperando isComplete=true"
                return result
            if line is None:
                continue
            if line == "":
                # linea en blanco = fin de un evento SSE
                if data_lines:
                    found = _handle_line_group("\n".join(data_lines))
                    data_lines = []
                    if found is not None:
                        videos = found
                        break
                continue
            if line.startswith("data:"):
                data_lines.append(line[len("data:") :].lstrip())
        else:
            if data_lines and videos is None:
                videos = _handle_line_group("\n".join(data_lines))

        try:
            r.close()
        except Exception:
            pass

        if videos is None:
            result["error"] = "Stream SSE termino sin isComplete=true"
            return result
        if not videos:
            result["error"] = "isComplete=true pero 'content' vino vacio o sin videoUrl"
            return result

    except Exception as exc:
        result["error"] = f"Stream SSE fallo: {exc}"
        return result

    log(f"[S{slot_id}] [OK] {len(videos)} video(s) generado(s)")

    if out_dir:
        _download_videos(sess, videos, out_dir, batch_id, slot_id, log)

    result["videos"] = videos
    return result


def _download_videos(
    sess: requests.Session,
    videos: list[dict],
    out_dir: str,
    batch_id: str,
    slot_id: int,
    log: Callable[[str], None],
) -> None:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    for i, v in enumerate(videos):
        dest = Path(out_dir) / f"vibes_{batch_id}_{i}.mp4"
        try:
            r_dl = sess.get(v["video_url"], timeout=120, stream=True)
            r_dl.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r_dl.iter_content(65536):
                    f.write(chunk)
            v["saved_path"] = str(dest)
            log(f"[S{slot_id}] [OK] video {i} descargado a {dest}")
        except Exception as exc:
            log(f"[S{slot_id}] [WARNING] descarga video {i} fallo: {exc}")


def upload_reference_image_via_bridge(
    image_bytes: bytes,
    filename: str = "reference.jpg",
    timeout_sec: int = 60,
    log: Callable[[str], None] = _NoOpLog,
) -> dict:
    """Sube una imagen de referencia a traves de la pestaña real de Chrome (mismo
    motivo que generate_video_via_bridge: un POST automatizado sin browser real
    puede ser rechazado). Devuelve {"media_ent_id","cdn_url","error"} -- media_ent_id/
    cdn_url son mediaEntId/cdnUrl de la respuesta real de POST /api/upload-media
    (confirmado en vivo 2026-07-17), listos para pasar como ref_image a
    generate_video_via_bridge()."""
    from base64 import b64encode

    from src.infrastructure.ai_providers import flow_bridge

    result: dict = {"media_ent_id": None, "cdn_url": None, "error": None}

    connected = set(flow_bridge.get_connected_accounts()) | set(flow_bridge.get_ws_clients().keys())
    if VIBES_ACCOUNT_HASH not in connected:
        result["error"] = (
            "No hay ninguna pestaña de vibes.ai conectada al bridge. Abri vibes.ai en "
            "Chrome con extensions/flow_extension cargada y logueado, y esperá unos "
            "segundos a que se registre."
        )
        return result

    request_id = str(uuid.uuid4())
    event = flow_bridge.register_result_waiter(request_id)
    req = {
        "requestId": request_id,
        "url": UPLOAD_MEDIA_URL,
        "bearer": "",
        "kind": "upload_media",
        "body": json.dumps({"filename": filename, "dataB64": b64encode(image_bytes).decode("ascii")}),
        "account_hash": VIBES_ACCOUNT_HASH,
    }

    log(f"encolando subida de imagen de referencia ({filename}, {len(image_bytes)} bytes)...")
    pushed = flow_bridge.ws_push(VIBES_ACCOUNT_HASH, req)
    if not pushed:
        flow_bridge.enqueue_request(req)
        log("sin WS -- encolado para HTTP poll")

    ok = event.wait(timeout=timeout_sec)
    msg = flow_bridge.try_pop_result(request_id)
    flow_bridge.cleanup_waiter(request_id)

    if not ok or msg is None:
        result["error"] = f"Timeout ({timeout_sec}s) esperando resultado de la subida"
        return result
    if msg.get("status") != 200 or msg.get("error"):
        result["error"] = f"Subida fallo: {msg.get('error')} (status={msg.get('status')}) body={str(msg.get('body'))[:300]}"
        return result

    try:
        data = json.loads(msg.get("body") or "{}")
    except Exception as exc:
        result["error"] = f"Respuesta de subida no es JSON valido: {exc}"
        return result

    media_ent_id = data.get("mediaEntId")
    cdn_url = data.get("cdnUrl")
    if not media_ent_id or not cdn_url:
        result["error"] = f"Respuesta de subida sin mediaEntId/cdnUrl: {str(data)[:300]}"
        return result

    log(f"[OK] imagen de referencia subida -- mediaEntId={media_ent_id}")
    result["media_ent_id"] = media_ent_id
    result["cdn_url"] = cdn_url
    return result


def generate_video_via_bridge(
    prompt: str,
    project_id: str | None = None,
    aspect_ratio: str = "9:16",
    resolution: str = "480p",
    prompt_model: str = "gemini-2.5-flash",
    image_model: str = "midjen-base",
    video_model: str = "midjen-short",
    batch_variation: bool = True,
    out_dir: str | None = None,
    timeout_sec: int = 300,
    slot_id: int = 0,
    cookie_list: list[dict] | None = None,
    ref_image: dict | None = None,
    log: Callable[[str], None] = _NoOpLog,
) -> dict:
    """Genera video(s) via Vibes usando una pestaña REAL de Chrome (con
    extensions/flow_extension cargada, logueada en vibes.ai) en vez de requests
    puro -- generate_video() confirmo que requests siempre falla ("Generation
    failed to start") aunque la sesion sea valida; a mano en Chrome normal funciona.
    Reusa el mismo bridge de Flow (background.js/flow_bridge.py, puertos 5556/5557),
    que ya es generico: no distingue Flow de Vibes, solo enruta por account_hash.
    vibes_content.js (en la pestaña real) hace el fetch() de creacion + consume el
    SSE el mismo, y devuelve el evento final completo por el bridge.

    No necesita cookie_list para el fetch en si (el browser real ya tiene su propia
    sesion) -- cookie_list solo se usa, si se pasa, para descargar los mp4 al
    terminar (out_dir), reusando la cookie exportada via requests.Session."""
    from src.infrastructure.ai_providers import flow_bridge

    result: dict = {"videos": [], "batch_id": None, "error": None, "final_event": None}

    if not project_id:
        result["error"] = "project_id requerido -- usar vibes_client.ensure_project() primero"
        return result

    connected = set(flow_bridge.get_connected_accounts()) | set(flow_bridge.get_ws_clients().keys())
    if VIBES_ACCOUNT_HASH not in connected:
        result["error"] = (
            "No hay ninguna pestaña de vibes.ai conectada al bridge. Abri vibes.ai en "
            "Chrome con extensions/flow_extension cargada y logueado, y esperá unos "
            "segundos a que se registre."
        )
        return result

    create_body = _build_create_body(
        prompt,
        project_id,
        aspect_ratio,
        resolution,
        prompt_model,
        image_model,
        video_model,
        batch_variation,
        ref_image=ref_image,
    )
    batch_id = create_body["id"]
    result["batch_id"] = batch_id

    request_id = str(uuid.uuid4())
    event = flow_bridge.register_result_waiter(request_id)
    req = {
        "requestId": request_id,
        "url": GENERATION_BATCHES_URL,
        "bearer": "",
        "body": json.dumps(create_body),
        "account_hash": VIBES_ACCOUNT_HASH,
    }

    log(f"[S{slot_id}] encolando batch {batch_id} al bridge (cuenta {VIBES_ACCOUNT_HASH})...")
    pushed = flow_bridge.ws_push(VIBES_ACCOUNT_HASH, req)
    if not pushed:
        flow_bridge.enqueue_request(req)
        log(f"[S{slot_id}] sin WS -- encolado para HTTP poll")

    # +30s de margen sobre el timeout interno de vibes_content.js (que corta a los
    # 300s el propio SSE), para no cortar antes que el content script.
    ok = event.wait(timeout=timeout_sec + 30)
    msg = flow_bridge.try_pop_result(request_id)
    flow_bridge.cleanup_waiter(request_id)

    if not ok or msg is None:
        result["error"] = (
            f"Timeout ({timeout_sec}s) esperando resultado del bridge (¿la pestaña sigue abierta?)"
        )
        return result

    if msg.get("status") != 200 or msg.get("error"):
        result["error"] = (
            f"vibes_content.js reporto error: {msg.get('error')} (status={msg.get('status')}) body={str(msg.get('body'))[:300]}"
        )
        return result

    try:
        evt = json.loads(msg.get("body") or "{}")
    except Exception as exc:
        result["error"] = f"Resultado del bridge no es JSON valido: {exc}"
        return result

    result["final_event"] = evt
    videos = _handle_complete_event(evt, log=log) or []
    if not videos:
        result["error"] = (
            "isComplete=true pero sin videoUrl en ningun item (ver log de items fallidos arriba)"
        )
        return result

    log(f"[S{slot_id}] [OK] {len(videos)} video(s) generado(s) via bridge")

    if out_dir and cookie_list:
        _download_videos(_requests_session_from_cookies(cookie_list), videos, out_dir, batch_id, slot_id, log)
    elif out_dir:
        log(f"[S{slot_id}] [WARNING] out_dir pedido pero sin cookie_list -- no se puede descargar, solo URLs")

    result["videos"] = videos
    return result
