from src.domain.services import auth_service
from src.infrastructure.storage import docs_repository, user_repository


def _login_as(client, monkeypatch, username="usuario_test", role="user"):
    monkeypatch.setattr(
        user_repository, "get_user_for_auth",
        lambda u: (1, u, auth_service.hash_password("clave-correcta-123"), role, 1, 0))
    resp = client.post("/api/login", json={"username": username, "password": "clave-correcta-123"},
                        environ_overrides={"REMOTE_ADDR": "203.0.113.20"})
    assert resp.status_code == 200
    auth_service.clear_fails("203.0.113.20")


def test_docs_publicos_no_requiere_auth(client, monkeypatch):
    monkeypatch.setattr(
        docs_repository, "list_published",
        lambda: [(1, "video", "Primeros pasos", "Titulo", "desc", "https://youtu.be/abc12345678",
                   "", "", "", "", 0)])

    resp = client.get("/api/docs")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "Primeros pasos" in body["categories"]


def test_help_submit_funciona_sin_auth(client, monkeypatch):
    calls = []
    monkeypatch.setattr(docs_repository, "insert_help_report",
                         lambda *a: calls.append(a))

    resp = client.post("/api/help", json={"title": "algo no funciona", "description": "detalle"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert calls[0][0] == "anonymous"


def test_help_submit_sin_titulo_da_400(client):
    resp = client.post("/api/help", json={"description": "sin titulo"})
    assert resp.status_code in (400, 422)  # 422 si lo rechaza el schema (required=True)


def test_admin_docs_rechaza_usuario_no_admin(client, monkeypatch):
    _login_as(client, monkeypatch, username="usuario_normal", role="user")
    monkeypatch.setattr(user_repository, "get_user_full",
                         lambda u: {"role": "user", "username": u})

    resp = client.get("/api/admin/docs")
    assert resp.status_code == 403


def test_admin_docs_permite_admin(client, monkeypatch):
    _login_as(client, monkeypatch, username="admin_test", role="admin")
    monkeypatch.setattr(user_repository, "get_user_full",
                         lambda u: {"role": "admin", "username": u})
    monkeypatch.setattr(docs_repository, "list_all", lambda: [])

    resp = client.get("/api/admin/docs")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_admin_docs_post_rechaza_usuario_no_admin(client, monkeypatch):
    _login_as(client, monkeypatch, username="usuario_normal", role="user")
    monkeypatch.setattr(user_repository, "get_user_full",
                         lambda u: {"role": "user", "username": u})

    resp = client.post("/api/admin/docs", json={"title": "intento de crear"})
    assert resp.status_code == 403


def test_admin_docs_delete_rechaza_usuario_no_admin(client, monkeypatch):
    _login_as(client, monkeypatch, username="usuario_normal", role="user")
    monkeypatch.setattr(user_repository, "get_user_full",
                         lambda u: {"role": "user", "username": u})

    resp = client.delete("/api/admin/docs/1")
    assert resp.status_code == 403


def test_admin_docs_sin_auth_da_401_no_403(client):
    # Sin login siquiera -- el auth_middleware debe cortar antes de llegar a _require_admin.
    resp = client.get("/api/admin/docs")
    assert resp.status_code == 401
