import random
import time

import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

N8N_HOST_CANON = "n8n-n8n.y9c1cn.easypanel.host"
VOCES_URL = f"https://{N8N_HOST_CANON}/webhook/voces-videoforge"
GENERAR_URL = f"https://{N8N_HOST_CANON}/webhook/541b2f00-1fbb-443f-8225-25dd5969da01"
FUSIONAR_URL = f"https://{N8N_HOST_CANON}/webhook/merge-audio"
CLONAR_URL = f"https://{N8N_HOST_CANON}/webhook/clonar-voz-studio-ivr"

_RETRYABLE = (
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.Timeout,
)


def _fix_url(url: str) -> str:
    """Normaliza el host n8n por un typo comun y sus alias."""
    if not url:
        return url
    return str(url).replace("y9clcn", "y9c1cn").replace("y9C1cn", "y9c1cn")


def n8n_request(method: str, url: str, *, json_payload=None, timeout=120, attempts=3):
    """Request con reintentos robustos para n8n.

    Usa una sesion nueva en cada intento para evitar reutilizar sockets keep-alive
    ya cerrados por el servidor (ConnectionResetError 10054 en Windows /
    BrokenPipeError en Linux). El header Connection:close evita esa fuente de
    reset en solicitudes largas como merge-audio.
    """
    url = _fix_url(url)
    last: Exception | None = None
    for i in range(max(1, int(attempts))):
        session = requests.Session()
        session.headers.update({"Connection": "close"})
        try:
            return session.request(method.upper(), url, json=json_payload, timeout=timeout)
        except _RETRYABLE as exc:
            last = exc
            if i < attempts - 1:
                time.sleep((2 ** i) + random.uniform(0.2, 0.8))
        except Exception as exc:
            last = exc
            if i < attempts - 1:
                time.sleep(1.2 * (i + 1))
        finally:
            try:
                session.close()
            except Exception:
                pass
    logger.error("n8n_request agotó reintentos hacia %s: %s", url, last)
    raise RuntimeError(
        "No se pudo conectar con el servidor de voces. Verifica Internet o n8n y vuelve a intentar."
    ) from last
