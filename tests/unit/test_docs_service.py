from src.domain.services import docs_service
from src.infrastructure.storage import user_repository


def test_yt_embed_convierte_url_watch():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s"
    embed = docs_service._yt_embed(url)
    assert embed == "https://www.youtube.com/embed/dQw4w9WgXcQ?rel=0&modestbranding=1"


def test_yt_embed_convierte_url_corta():
    url = "https://youtu.be/dQw4w9WgXcQ"
    embed = docs_service._yt_embed(url)
    assert embed == "https://www.youtube.com/embed/dQw4w9WgXcQ?rel=0&modestbranding=1"


def test_yt_embed_url_no_youtube_queda_igual():
    url = "https://example.com/video.mp4"
    assert docs_service._yt_embed(url) == url


def test_yt_embed_vacio():
    assert docs_service._yt_embed("") == ""
    assert docs_service._yt_embed(None) == ""


def test_normalize_fields_aplica_defaults():
    fields = docs_service._normalize_fields({})
    assert fields["type"] == "video"
    assert fields["category"] == "General"
    assert fields["title"] == "Sin título"
    assert fields["is_published"] is True
    assert fields["sort_order"] == 0


def test_normalize_fields_convierte_youtube_solo_si_es_video():
    yt_url = "https://youtu.be/dQw4w9WgXcQ"
    as_video = docs_service._normalize_fields({"type": "video", "url": yt_url})
    assert as_video["url"] == "https://www.youtube.com/embed/dQw4w9WgXcQ?rel=0&modestbranding=1"

    as_link = docs_service._normalize_fields({"type": "link", "url": yt_url})
    assert as_link["url"] == yt_url  # no se toca si no es tipo "video"


def test_is_admin_sin_username():
    assert docs_service.is_admin(None) is False
    assert docs_service.is_admin("") is False


def test_is_admin_true_para_rol_admin(monkeypatch):
    monkeypatch.setattr(
        user_repository, "get_user_full", lambda username: {"role": "admin", "username": username}
    )
    assert docs_service.is_admin("cualquiera") is True


def test_is_admin_false_para_rol_normal(monkeypatch):
    monkeypatch.setattr(
        user_repository, "get_user_full", lambda username: {"role": "user", "username": username}
    )
    assert docs_service.is_admin("cualquiera") is False


def test_is_admin_false_si_usuario_no_existe(monkeypatch):
    monkeypatch.setattr(user_repository, "get_user_full", lambda username: None)
    assert docs_service.is_admin("fantasma") is False


def test_is_admin_false_si_repo_falla(monkeypatch):
    def _boom(username):
        raise RuntimeError("DB caida")

    monkeypatch.setattr(user_repository, "get_user_full", _boom)
    assert docs_service.is_admin("cualquiera") is False
