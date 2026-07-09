import base64
import io
import random
import time

import requests

from src.infrastructure.ai_providers.whisk_client import mk_https_session

MODAL_URL = "https://davidestebanbermudez14--motor-video-cpa-renderizar.modal.run"


class ModalRequestError(Exception):
    def __init__(self, message: str, body: str = ""):
        super().__init__(message)
        self.body = body


def new_session(pool_size: int = 16) -> requests.Session:
    try:
        return mk_https_session(pool_size)
    except Exception:
        return requests.Session()


def encode_image_b64(img_path: str, max_size: int = 960, quality: int = 78) -> str:
    """JPEG re-encode + resize (960px) para reducir el payload enviado a Modal."""
    try:
        from PIL import Image

        with Image.open(img_path) as im:
            if im.mode != "RGB":
                im = im.convert("RGB")
            if max(im.width, im.height) > max_size:
                ratio = max_size / max(im.width, im.height)
                im = im.resize((int(im.width * ratio), int(im.height * ratio)), Image.BILINEAR)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=quality, optimize=True)
            return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        with open(img_path, "rb") as f:
            return base64.b64encode(f.read()).decode()


def post_batch(
    session: requests.Session,
    payload: dict,
    connect_timeout: float,
    read_timeout: float,
    max_retries: int,
    on_retry=None,
    on_reset_session=None,
) -> dict:
    """POST a Modal con reintentos (SSL/conexion/timeout/5xx). Lanza ModalRequestError
    si se agotan los reintentos o el error no es transitorio - el llamador decide si
    hace fallback local con ese error."""
    last_err: Exception | None = None
    last_resp = None
    for attempt in range(max_retries):
        try:
            r = session.post(MODAL_URL, json=payload, timeout=(connect_timeout, read_timeout))
            r.raise_for_status()
            return r.json()
        except requests.exceptions.SSLError as exc:
            last_err = exc
            time.sleep(2.0 + attempt * 2.0 + random.random() * 0.4)
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as exc:
            last_err = exc
            if on_reset_session:
                on_reset_session()
            if on_retry:
                on_retry(f"conexion Modal inestable, reintentando... ({str(exc)[:120]})")
            time.sleep(1.5 + attempt * 2.0 + random.random() * 0.35)
        except requests.exceptions.ReadTimeout as exc:
            last_err = exc
            if on_retry:
                on_retry(f"timeout de Modal ({read_timeout}s), reintentando...")
            time.sleep(1.0 + attempt * 1.5 + random.random() * 0.3)
        except requests.exceptions.HTTPError as exc:
            last_err = exc
            last_resp = exc.response
            status = getattr(exc.response, "status_code", None)
            if status in (408, 409, 425, 429, 500, 502, 503, 504):
                if on_retry:
                    on_retry(f"Modal HTTP {status}, reintentando...")
                time.sleep(1.5 + attempt * 2.0 + random.random() * 0.3)
                continue
            break
        except Exception as exc:
            last_err = exc
            break

    body = ""
    try:
        body = (last_resp.text or "")[:600] if last_resp is not None else ""
    except Exception:
        pass
    raise ModalRequestError(str(last_err), body)
