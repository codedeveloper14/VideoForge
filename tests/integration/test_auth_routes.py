import pytest

from src.core.config import config
from src.domain.services import auth_service
from src.infrastructure.storage import user_repository


def _user_row(username="usuario_test", password="clave-correcta-123", role="user",
              active=1, must_change=0):
    return (1, username, auth_service.hash_password(password), role, active, must_change)


@pytest.fixture(autouse=True)
def _clean_lockout_state():
    # _failed_attempts es un dict a nivel de modulo en auth_service -- se comparte
    # entre tests si no se limpia, y podria dejar un test bloqueado por otro anterior.
    yield
    for ip in ("203.0.113.10", "203.0.113.11", "203.0.113.12"):
        auth_service.clear_fails(ip)


def test_login_exitoso_devuelve_cookie(client, monkeypatch):
    monkeypatch.setattr(user_repository, "get_user_for_auth",
                         lambda u: _user_row(username=u, password="clave-correcta-123"))

    resp = client.post("/api/login", json={"username": "usuario_test", "password": "clave-correcta-123"},
                        environ_overrides={"REMOTE_ADDR": "203.0.113.10"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["user"] == "usuario_test"
    assert "vf_session=" in resp.headers.get("Set-Cookie", "")


def test_login_password_incorrecta_da_401(client, monkeypatch):
    monkeypatch.setattr(user_repository, "get_user_for_auth",
                         lambda u: _user_row(username=u, password="clave-correcta-123"))

    resp = client.post("/api/login", json={"username": "usuario_test", "password": "clave-mala"},
                        environ_overrides={"REMOTE_ADDR": "203.0.113.11"})

    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False


def test_login_usuario_inexistente_da_401(client, monkeypatch):
    monkeypatch.setattr(user_repository, "get_user_for_auth", lambda u: None)

    resp = client.post("/api/login", json={"username": "fantasma", "password": "cualquiera123"},
                        environ_overrides={"REMOTE_ADDR": "203.0.113.12"})

    assert resp.status_code == 401


def test_login_must_change_password_no_setea_cookie(client, monkeypatch):
    monkeypatch.setattr(user_repository, "get_user_for_auth",
                         lambda u: _user_row(username=u, password="clave-correcta-123", must_change=1))

    resp = client.post("/api/login", json={"username": "usuario_test", "password": "clave-correcta-123"},
                        environ_overrides={"REMOTE_ADDR": "203.0.113.10"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["must_change_password"] is True
    assert "Set-Cookie" not in resp.headers


def test_login_bloquea_ip_tras_intentos_fallidos(client, monkeypatch):
    monkeypatch.setattr(user_repository, "get_user_for_auth",
                         lambda u: _user_row(username=u, password="clave-correcta-123"))
    ip = "203.0.113.10"

    for _ in range(config.max_failed_login_attempts):
        resp = client.post("/api/login", json={"username": "usuario_test", "password": "mala"},
                            environ_overrides={"REMOTE_ADDR": ip})

    # El intento que completa el umbral ya viene bloqueado (429), y cualquiera despues tambien.
    resp = client.post("/api/login", json={"username": "usuario_test", "password": "clave-correcta-123"},
                        environ_overrides={"REMOTE_ADDR": ip})
    assert resp.status_code == 429
    assert resp.get_json()["lockout"] is True


def test_me_sin_auth_da_401(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_autenticado_devuelve_username(client, monkeypatch):
    monkeypatch.setattr(user_repository, "get_user_for_auth",
                         lambda u: _user_row(username=u, password="clave-correcta-123"))
    client.post("/api/login", json={"username": "usuario_test", "password": "clave-correcta-123"},
                environ_overrides={"REMOTE_ADDR": "203.0.113.10"})

    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["authenticated"] is True
    assert body["username"] == "usuario_test"


def test_ruta_protegida_sin_auth_da_401(client):
    resp = client.get("/api/proyectos/listar")
    assert resp.status_code == 401


def test_ruta_publica_no_requiere_auth(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_options_preflight_no_requiere_auth(client):
    # Regresion: el bug real encontrado durante esta migracion -- OPTIONS
    # devolvia 401 y rompia CORS en cualquier ruta cross-origin.
    resp = client.options("/api/proyectos/listar")
    assert resp.status_code != 401
