import re

from src.infrastructure.storage import docs_repository, user_repository

_YT_RE = re.compile(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})")

_PUBLIC_COLUMNS = ("id", "type", "category", "title", "description", "url", "content",
                   "thumbnail_url", "duration_label", "tags", "sort_order")
_ADMIN_COLUMNS = _PUBLIC_COLUMNS + ("is_published", "created_at", "created_by")


def is_admin(username: str | None) -> bool:
    if not username:
        return False
    try:
        user = user_repository.get_user_full(username)
        return bool(user and user.get("role") == "admin")
    except Exception:
        return False


def _yt_embed(url: str) -> str:
    m = _YT_RE.search(url or "")
    return f"https://www.youtube.com/embed/{m.group(1)}?rel=0&modestbranding=1" if m else (url or "")


def list_public_docs() -> dict:
    """Docs publicados, agrupados por categoria (ordenadas alfabeticamente)."""
    rows = docs_repository.list_published()
    categories: dict[str, list[dict]] = {}
    for row in rows:
        doc = dict(zip(_PUBLIC_COLUMNS, row))
        categories.setdefault(doc["category"] or "General", []).append(doc)
    return {"categories": dict(sorted(categories.items()))}


def submit_help_report(username: str | None, data: dict) -> None:
    title = (data.get("title") or "")[:500]
    if not title:
        raise ValueError("title required")

    report_type = (data.get("type") or "")[:50]
    category = (data.get("category") or "")[:100]
    description = (data.get("description") or "")[:5000]
    email = (data.get("email") or "")[:255]

    if not email and username:
        email = docs_repository.get_user_email(username)

    docs_repository.insert_help_report(username or "anonymous", email, report_type,
                                        category, title, description)


def list_admin_docs() -> list[dict]:
    rows = docs_repository.list_all()
    out = []
    for row in rows:
        doc = dict(zip(_ADMIN_COLUMNS, row))
        doc["is_published"] = bool(doc["is_published"])
        doc["created_at"] = doc["created_at"] or ""
        doc["created_by"] = doc["created_by"] or ""
        out.append(doc)
    return out


def _normalize_fields(data: dict) -> dict:
    doc_type = data.get("type", "video")
    url = data.get("url", "")
    return {
        "type": doc_type,
        "category": data.get("category", "General"),
        "title": data.get("title", "Sin título"),
        "description": data.get("description", ""),
        "url": _yt_embed(url) if doc_type == "video" else url,
        "content": data.get("content", ""),
        "thumbnail_url": data.get("thumbnail_url", ""),
        "duration_label": data.get("duration_label", ""),
        "tags": data.get("tags", ""),
        "sort_order": int(data.get("sort_order", 0)),
        "is_published": bool(data.get("is_published", True)),
    }


def create_doc(data: dict, created_by: str) -> int:
    return docs_repository.create_doc(_normalize_fields(data), created_by)


def update_doc(doc_id: int, data: dict) -> None:
    docs_repository.update_doc(doc_id, _normalize_fields(data))


def delete_doc(doc_id: int) -> None:
    docs_repository.delete_doc(doc_id)
