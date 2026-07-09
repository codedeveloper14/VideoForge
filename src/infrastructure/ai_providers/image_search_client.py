import base64
import os

import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

_TIMEOUT = 10
_INVALID_EXTS = (".svg", ".gif", "svg+xml")


def _valid_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    low = url.lower()
    return not any(x in low for x in _INVALID_EXTS)


def _search_serper(query: str, n: int, api_key: str) -> list[str]:
    try:
        resp = requests.post(
            "https://google.serper.dev/images",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 20}, timeout=12,
        )
        if resp.status_code != 200:
            return []
        images = resp.json().get("images") or []
        min_w, min_h = 400, 300
        urls = [
            img.get("imageUrl", "") for img in images
            if img.get("imageWidth", 0) >= min_w and img.get("imageHeight", 0) >= min_h
            and _valid_url(img.get("imageUrl", ""))
        ]
        return urls[:n]
    except Exception as exc:
        logger.info("image_search serper error: %s", exc)
        return []


def _search_pexels(query: str, n: int, api_key: str) -> list[str]:
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params={"query": query, "per_page": n, "orientation": "landscape", "size": "large"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        photos = resp.json().get("photos") or []
        urls = []
        for p in photos:
            src = p.get("src", {})
            url = src.get("large2x") or src.get("large") or src.get("original")
            if url and _valid_url(url):
                urls.append(url)
        return urls[:n]
    except Exception as exc:
        logger.info("image_search pexels error: %s", exc)
        return []


def _search_unsplash(query: str, n: int, api_key: str) -> list[str]:
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            headers={"Authorization": f"Client-ID {api_key}"},
            params={"query": query, "per_page": n, "orientation": "landscape"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        results = resp.json().get("results") or []
        urls = [item["urls"]["regular"] for item in results if item.get("urls")]
        return [u for u in urls if _valid_url(u)][:n]
    except Exception as exc:
        logger.info("image_search unsplash error: %s", exc)
        return []


def _search_pixabay(query: str, n: int, api_key: str) -> list[str]:
    try:
        resp = requests.get(
            "https://pixabay.com/api/",
            params={"key": api_key, "q": query, "image_type": "photo",
                    "per_page": n, "safesearch": "true", "order": "popular"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        hits = resp.json().get("hits") or []
        urls = [h["webformatURL"] for h in hits]
        return [u for u in urls if _valid_url(u)][:n]
    except Exception as exc:
        logger.info("image_search pixabay error: %s", exc)
        return []


def search_images(query: str, n: int = 4, serper_key: str = "", pexels_key: str = "",
                   unsplash_key: str = "") -> list[str]:
    """Cascada Serper (Google Images) -> Pexels -> Unsplash -> Pixabay, primer resultado
    no vacio gana. Las claves pasadas por parametro (p. ej. suministradas por el frontend)
    tienen prioridad sobre las variables de entorno; Pixabay solo usa variable de entorno."""
    n = min(int(n or 4), 8)
    query = (query or "").strip()
    if not query:
        return []

    urls: list[str] = []
    serper_key = (serper_key or "").strip() or os.environ.get("SERPER_API_KEY", "").strip()
    pexels_key = (pexels_key or "").strip() or os.environ.get("PEXELS_API_KEY", "").strip()
    unsplash_key = (unsplash_key or "").strip() or os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    pixabay_key = os.environ.get("PIXABAY_API_KEY", "").strip()

    if serper_key and not urls:
        urls = _search_serper(query, n, serper_key)
    if pexels_key and not urls:
        urls = _search_pexels(query, n, pexels_key)
    if unsplash_key and not urls:
        urls = _search_unsplash(query, n, unsplash_key)
    if pixabay_key and not urls:
        urls = _search_pixabay(query, n, pixabay_key)

    if not urls:
        logger.info("image_search sin resultados para %r (configura SERPER_API_KEY o PEXELS_API_KEY)", query)
    return urls[:n]


def fetch_image_bytes(query: str, n: int = 6, serper_key: str = "", pexels_key: str = "",
                       unsplash_key: str = "") -> bytes | None:
    """Busca `query` en la misma cascada de proveedores y descarga la primera imagen
    valida (no SVG/GIF, magic bytes JPEG/PNG/WEBP). Usado server-side cuando una escena
    necesita una referencia y no trajo una propia; acepta claves puntuales del frontend
    igual que search_images."""
    urls = search_images(query, n=n, serper_key=serper_key, pexels_key=pexels_key, unsplash_key=unsplash_key)
    for url in urls:
        try:
            resp = requests.get(url, timeout=_TIMEOUT, stream=True, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if "svg" in ct or "xml" in ct or "html" in ct:
                continue
            data = resp.content
            if len(data) <= 1000:
                continue
            magic = data[:4]
            if magic[:2] == b"\xff\xd8" or magic == b"\x89PNG" or magic == b"RIFF":
                return data
        except Exception as exc:
            logger.info("image_search download failed %s: %s", url[:80], exc)
    return None


def proxy_image_b64(url: str) -> dict:
    """Descarga una imagen externa y la devuelve como data-URI base64, para que el
    frontend evite problemas de CORS al mostrarla directamente."""
    url = (url or "").strip()
    if not url or not url.startswith("http"):
        return {"error": "URL invalida"}
    try:
        resp = requests.get(url, timeout=_TIMEOUT, stream=True, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        content = resp.content
        if len(content) < 500:
            return {"error": "Imagen demasiado pequena"}
        ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if ct in ("image/jpeg", "image/jpg"):
            ct = "image/jpeg"
        elif ct == "image/png":
            ct = "image/png"
        elif ct == "image/webp":
            ct = "image/webp"
        else:
            ct = "image/jpeg"
        b64 = base64.b64encode(content).decode("ascii")
        return {"b64": f"data:{ct};base64,{b64}", "size": len(content)}
    except Exception as exc:
        return {"error": str(exc)}
