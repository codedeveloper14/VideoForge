import base64
import os
import random
import time
from datetime import UTC, datetime

import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

_W_SESSION = "https://labs.google/fx/api/auth/session"
_W_WORKFLOW = "https://labs.google/fx/api/trpc/media.createOrUpdateWorkflow"
_W_CAPTION = "https://labs.google/fx/api/trpc/backbone.captionImage"
_W_UPLOAD = "https://labs.google/fx/api/trpc/backbone.uploadImage"
_W_GENERATE = "https://aisandbox-pa.googleapis.com/v1/whisk:runImageRecipe"
_W_MAX_BYTES = 4 * 1024 * 1024

# Conexiones TLS simultaneas a labs.google. 50+ suele colgar la red/Windows.
LABS_TLS_POOL = max(1, min(48, int(os.environ.get("WHISK_LABS_PARALLEL", "12"))))

_LABS_HEADERS_BASE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Origin": "https://labs.google",
    "Referer": "https://labs.google/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def mk_https_session(pool_maxsize: int) -> requests.Session:
    """Session con keep-alive + pool de conexiones. Reduce SSLEOF/EOF en Windows
    al evitar crear miles de handshakes en paralelo."""
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
    except Exception:
        return requests.Session()

    s = requests.Session()
    retry = Retry(
        total=0,
        connect=0,
        read=0,
        redirect=0,
        status=0,
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        pool_connections=max(1, pool_maxsize),
        pool_maxsize=max(1, pool_maxsize),
        max_retries=retry,
        pool_block=True,
    )
    s.mount("https://", adapter)
    return s


_LABS_SESSION = mk_https_session(LABS_TLS_POOL)
_AIS_SESSION = mk_https_session(max(4, min(24, LABS_TLS_POOL)))


def tls_workers(n: int) -> int:
    return max(1, min(int(n), LABS_TLS_POOL))


def _labs_headers(cookie: str) -> dict:
    h = dict(_LABS_HEADERS_BASE)
    h["cookie"] = cookie
    return h


def labs_request(method: str, url: str, **kwargs):
    """Reintentos ante SSLEOF / EOF en TLS (muy frecuentes con muchas conexiones paralelas)."""
    timeout = kwargs.pop("timeout", (12, 45))
    last_err = None
    for attempt in range(6):
        try:
            return _LABS_SESSION.request(method.upper(), url, timeout=timeout, **kwargs)
        except (
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.Timeout,
        ) as exc:
            last_err = exc
            time.sleep(min(6.0, 0.5 * (2**attempt)) + random.random() * 0.25)
    raise last_err


def ais_request(url: str, **kwargs):
    """POST a aisandbox con keep-alive y backoff corto ante fallos de red."""
    timeout = kwargs.pop("timeout", 65)
    last_err = None
    for attempt in range(4):
        try:
            return _AIS_SESSION.post(url, timeout=timeout, **kwargs)
        except (
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.Timeout,
        ) as exc:
            last_err = exc
            time.sleep(min(4.0, 0.45 * (2**attempt)) + random.random() * 0.20)
    raise last_err


def clean_cookie(raw: str) -> str:
    attrs = {"path", "expires", "domain", "max-age", "httponly", "secure", "samesite", "partitioned"}
    parts = [p.strip() for p in (raw or "").split(";") if p.strip()]
    return "; ".join(
        p
        for p in parts
        if not (("=" in p and p.split("=", 1)[0].strip().lower() in attrs) or p.strip().lower() in attrs)
    )


def probe_session(cookie: str) -> dict:
    """Valida cookie contra labs.google con timeout corto."""
    ck = clean_cookie((cookie or "").strip())
    if not ck:
        return {"ok": False, "user": "", "error": "empty"}
    try:
        r = labs_request("GET", _W_SESSION, headers=_labs_headers(ck), timeout=(4, 14))
        if r.status_code != 200:
            return {"ok": False, "user": "", "error": f"HTTP {r.status_code}"}
        d = r.json()
        if d.get("error") == "ACCESS_TOKEN_REFRESH_NEEDED":
            return {"ok": False, "user": "", "error": "expired"}
        uobj = d.get("user") or {}
        user = uobj.get("name") or uobj.get("email") or uobj.get("displayName") or ""
        return {"ok": bool(d.get("access_token")), "user": user or "", "error": ""}
    except requests.exceptions.Timeout:
        return {"ok": False, "user": "", "error": "timeout"}
    except Exception as exc:
        return {"ok": False, "user": "", "error": str(exc)[:120]}


def resize_if_needed(raw: bytes) -> bytes:
    if len(raw) <= _W_MAX_BYTES:
        return raw
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        if img.mode == "RGBA":
            img = img.convert("RGB")
        for q in range(90, 15, -15):
            buf = io.BytesIO()
            w, h = img.size
            if q < 70:
                img = img.resize((int(w * 0.7), int(h * 0.7)), Image.LANCZOS)
            img.save(buf, format="JPEG", quality=q)
            if len(buf.getvalue()) <= _W_MAX_BYTES:
                return buf.getvalue()
    except ImportError:
        pass
    return raw


def to_b64(src) -> str:
    if isinstance(src, str) and src.startswith("data:"):
        return src
    if isinstance(src, str):
        with open(src, "rb") as f:
            raw = f.read()
    else:
        raw = bytes(src)
    raw = resize_if_needed(raw)
    mime = "image/jpeg" if raw[:3] == b"\xff\xd8\xff" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


class WhiskExpired(RuntimeError):
    pass


class WhiskClient:
    """Una cuenta Whisk (cookie). Cada slot es una instancia separada."""

    def __init__(self, cookie: str, label: str = "?"):
        self.cookie = clean_cookie(cookie)
        self.label = label
        self._token = None
        self._expiry = None
        self._auth_lock_time = None
        self.workflow_id = None
        self.subject_refs: list[dict] = []

    def _log(self, msg: str) -> None:
        logger.info("[%s] %s", self.label, msg)

    def _refresh_token(self) -> str:
        self._log("Autenticando...")
        r = labs_request("GET", _W_SESSION, headers={"cookie": self.cookie}, timeout=(10, 30))
        if r.status_code != 200:
            raise RuntimeError(f"Auth HTTP {r.status_code}")
        d = r.json()
        if d.get("error") == "ACCESS_TOKEN_REFRESH_NEEDED":
            raise RuntimeError("Cookie expirada - renueva la cookie de Whisk.")
        self._token = d.get("access_token")
        exp = d.get("expires")
        if exp:
            self._expiry = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        user = d.get("user", {}).get("name", "?")
        self._log(f"[OK] Auth OK - {user}")
        return self._token

    def _get_token(self) -> str:
        if self._token and self._expiry:
            exp = self._expiry if self._expiry.tzinfo else self._expiry.replace(tzinfo=UTC)
            if datetime.now(UTC) < exp:
                return self._token
        return self._refresh_token()

    def test_auth(self) -> dict:
        try:
            t = self._get_token()
            return {"ok": True, "user": (t[:20] + "...") if t else ""}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _cookie_headers(self) -> dict:
        return {"cookie": self.cookie, "Content-Type": "application/json"}

    def _bearer_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
            "Referer": "https://labs.google/",
        }

    def create_project(self) -> str:
        name = "Batch-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        r = labs_request(
            "POST",
            _W_WORKFLOW,
            headers=self._cookie_headers(),
            json={"json": {"workflowMetadata": {"workflowName": name}}},
            timeout=(15, 60),
        )
        if r.status_code != 200:
            raise RuntimeError(f"create_project HTTP {r.status_code}: {r.text[:120]}")
        d = r.json()
        wid = None
        for path in (
            ["result", "data", "json", "result", "workflowId"],
            ["result", "data", "json", "workflowId"],
        ):
            try:
                v = d
                for k in path:
                    v = v[k]
                wid = v
                break
            except Exception:
                pass
        if not wid:
            raise RuntimeError(f"No workflowId en: {str(d)[:200]}")
        self._log(f"Proyecto: {wid[:24]}...")
        return wid

    def _caption(self, b64: str, wid: str) -> str:
        body = {
            "json": {
                "captionInput": {
                    "candidatesCount": 1,
                    "mediaInput": {"mediaCategory": "MEDIA_CATEGORY_SUBJECT", "rawBytes": b64},
                },
                "clientContext": {"workflowId": wid},
            }
        }
        r = labs_request("POST", _W_CAPTION, headers=self._cookie_headers(), json=body, timeout=(12, 60))
        if r.status_code != 200:
            raise RuntimeError(f"caption HTTP {r.status_code}")
        d = r.json()
        try:
            return d["result"]["data"]["json"]["result"]["candidates"][0]["output"]
        except Exception:
            return "A character"

    def _upload_img(self, b64: str, caption: str, wid: str) -> str:
        body = {
            "json": {
                "clientContext": {"workflowId": wid},
                "uploadMediaInput": {
                    "mediaCategory": "MEDIA_CATEGORY_SUBJECT",
                    "rawBytes": b64,
                    "caption": caption,
                },
            }
        }
        last_err = None
        r = None
        for attempt in range(4):
            try:
                r = labs_request(
                    "POST", _W_UPLOAD, headers=self._cookie_headers(), json=body, timeout=(12, 60)
                )
                if r.status_code == 200:
                    break
                if r.status_code in (500, 502, 503) and attempt < 3:
                    wait = 3 * (attempt + 1)
                    self._log(f"[WARNING] upload HTTP {r.status_code} - reintentando en {wait}s...")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"upload HTTP {r.status_code}: {r.text[:120]}")
            except RuntimeError:
                raise
            except Exception as exc:
                last_err = exc
                if attempt < 3:
                    time.sleep(3 * (attempt + 1))
                    continue
                raise RuntimeError(f"upload error: {exc}") from exc
        else:
            raise RuntimeError(f"upload fallo tras 4 intentos: {last_err}")
        d = r.json()
        mid = None
        for path in (
            ["result", "data", "json", "result", "uploadMediaGenerationId"],
            ["result", "data", "json", "uploadMediaGenerationId"],
        ):
            try:
                v = d
                for k in path:
                    v = v[k]
                mid = v
                break
            except Exception:
                pass
        if not mid:
            raise RuntimeError(f"No media_id: {str(d)[:200]}")
        return mid

    def upload_subject(self, src, wid: str) -> dict:
        b64 = to_b64(src)
        cap = self._caption(b64, wid)
        mid = self._upload_img(b64, cap, wid)
        self._log(f"Sujeto OK - {cap[:50]}")
        return {"caption": cap, "mediaGenerationId": mid}

    def generate(self, prompt: str, seed: int = 0) -> bytes:
        """Genera imagen y devuelve los bytes PNG/JPEG directamente."""
        if not self.subject_refs:
            raise RuntimeError("recipeMediaInputs vacio - sube una imagen de referencia antes de generar.")
        recipe = [
            {
                "caption": r["caption"],
                "mediaInput": {
                    "mediaCategory": "MEDIA_CATEGORY_SUBJECT",
                    "mediaGenerationId": r["mediaGenerationId"],
                },
            }
            for r in self.subject_refs
        ]
        self._log(f"Generando con {len(recipe)} ref(s) - wf={self.workflow_id[:8]}...")
        body = {
            "clientContext": {"workflowId": self.workflow_id, "tool": "BACKBONE"},
            "seed": seed,
            "imageModelSettings": {"imageModel": "GEM_PIX", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"},
            "userInstruction": prompt,
            "recipeMediaInputs": recipe,
        }
        r = ais_request(_W_GENERATE, headers=self._bearer_headers(), json=body, timeout=65)
        if r.status_code == 429:
            self._token = None
            raise RuntimeError("Rate limit (429) - demasiadas solicitudes")
        if r.status_code in (401, 403):
            self._token = None
            raise RuntimeError("Cookie invalida o expirada")
        if r.status_code == 400:
            txt = r.text.lower()
            self._log(f"Whisk 400: {r.text[:300]}")
            if any(
                k in txt
                for k in (
                    "public_error_unsafe",
                    "unsafe_generation",
                    "public_error_sensitive",
                    "blocked_reason",
                    "image_safety",
                )
            ):
                raise RuntimeError("WHISK_BLOCKED_CONTENT")
            if any(
                k in txt
                for k in ("unauthenticated", "auth", "token", "session", "credential", "login", "permission")
            ):
                self._token = None
                raise RuntimeError("Cookie invalida o expirada")
            if any(
                k in txt
                for k in ("safety", "policy", "blocked", "harmful", "inappropriate", "sensitive", "violat")
            ):
                raise RuntimeError(f"Bloqueado por politica de contenido: {r.text[:120]}")
            raise WhiskExpired(f"IDs expirados: {r.text[:150]}")
        if r.status_code != 200:
            raise RuntimeError(f"generate HTTP {r.status_code}: {r.text[:200]}")
        d = r.json()
        try:
            enc = d["imagePanels"][0]["generatedImages"][0]["encodedImage"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Respuesta inesperada: {str(d)[:200]}") from exc
        if "," in enc:
            enc = enc.split(",", 1)[1]
        return base64.b64decode(enc)

    def reset_session(self, subj_src=None) -> None:
        """Crea proyecto nuevo y re-sube el sujeto. Preserva subject_refs si falla a medias."""
        old_refs = list(self.subject_refs)
        try:
            self.workflow_id = self.create_project()
            self.subject_refs = []
            if subj_src and os.path.isfile(str(subj_src)):
                self.subject_refs = [self.upload_subject(subj_src, self.workflow_id)]
            else:
                self._log("[WARNING] reset_session sin sujeto - recipeMediaInputs quedara vacio")
        except Exception as exc:
            if not self.subject_refs and old_refs:
                self._log(
                    f"[WARNING] reset_session fallo ({exc}) - restaurando refs anteriores temporalmente"
                )
                self.subject_refs = old_refs
            raise
