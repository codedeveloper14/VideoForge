from src.domain.services import auth_service
from src.infrastructure.storage import user_repository


def _login(client, monkeypatch):
    monkeypatch.setattr(
        user_repository,
        "get_user_for_auth",
        lambda u: (1, u, auth_service.hash_password("clave-correcta-123"), "user", 1, 0),
    )
    resp = client.post(
        "/api/login",
        json={"username": "usuario_test", "password": "clave-correcta-123"},
        environ_overrides={"REMOTE_ADDR": "203.0.113.30"},
    )
    assert resp.status_code == 200
    auth_service.clear_fails("203.0.113.30")


def test_script_requiere_auth(client):
    resp = client.post("/api/idea2video/script", json={"idea": "algo"})
    assert resp.status_code == 401


def test_script_sin_idea_da_400(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.post("/api/idea2video/script", json={"idea": ""})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_script_con_idea_valida_usa_template(client, monkeypatch):
    _login(client, monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)

    resp = client.post(
        "/api/idea2video/script", json={"idea": "el impacto de la IA", "dur": 30, "style": "tutorial"}
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert "[ESCENA 1" in body["script"]


def test_autopilot_status_job_inexistente_da_404(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.get("/api/idea2video/autopilot/no-existe-este-job")
    assert resp.status_code == 404


def test_autopilot_sin_script_da_400(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.post("/api/idea2video/autopilot", json={"script": ""})
    assert resp.status_code == 400


def test_ap_imagen_bloquea_traversal(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.get(
        "/api/idea2video/ap_imagen",
        query_string={"project": "cualquiera", "file": "../../../guion/guion.txt"},
    )
    assert resp.status_code == 404


def test_ap_imagen_sin_archivo_da_404(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.get(
        "/api/idea2video/ap_imagen", query_string={"project": "proyecto_que_no_existe", "file": "a.png"}
    )
    assert resp.status_code == 404
