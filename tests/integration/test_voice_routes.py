import json

from src.domain.services import usage_service
from src.infrastructure.ai_providers import n8n_client
from src.infrastructure.storage import user_repository


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text if text is not None else json.dumps(json_data)

    def json(self):
        return self._json_data


def test_generar_sin_data_da_error_de_schema(client, login_as):
    login_as()
    resp = client.post("/api/voz/generar", json={"voice_id": "v1"})
    assert resp.status_code in (400, 422)


def test_generar_exitoso(client, login_as, monkeypatch):
    login_as()
    monkeypatch.setattr(usage_service, "check_limit", lambda *a, **kw: (True, "", {}))
    monkeypatch.setattr(usage_service, "record_usage", lambda *a, **kw: True)
    monkeypatch.setattr(user_repository, "get_user_full", lambda u: {"id": 1, "username": u})
    monkeypatch.setattr(
        n8n_client, "n8n_request",
        lambda method, url, **kw: _FakeResponse(200, {"fragments": [{"audio": "abc"}]}))

    resp = client.post("/api/voz/generar", json={"voice_id": "v1", "data": "hola mundo"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["fragments"]) == 1


def test_generar_limite_alcanzado_da_429(client, login_as, monkeypatch):
    login_as()
    monkeypatch.setattr(
        usage_service, "check_limit",
        lambda *a, **kw: (False, "Limite mensual de voz alcanzado", {"used": 100, "limit": 100}))

    resp = client.post("/api/voz/generar", json={"voice_id": "v1", "data": "hola mundo"})
    assert resp.status_code == 429
    assert resp.get_json()["limit_reached"] is True


def test_generar_requiere_auth(client):
    resp = client.post("/api/voz/generar", json={"voice_id": "v1", "data": "hola"})
    assert resp.status_code == 401


def test_voces_proxea_n8n(client, login_as, monkeypatch):
    login_as()
    monkeypatch.setattr(
        n8n_client, "n8n_request",
        lambda method, url, **kw: _FakeResponse(200, [{"ID Voz": "v1", "Nombre Voz": "Voz Uno"}]))

    resp = client.get("/api/voz/voces")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body[0]["ID Voz"] == "v1"


def test_fusionar_sin_proyecto_no_guarda_pero_responde(client, login_as, monkeypatch):
    login_as()
    monkeypatch.setattr(
        n8n_client, "n8n_request",
        lambda method, url, **kw: _FakeResponse(200, {"finalAudio": ""}))

    resp = client.post("/api/voz/fusionar", json={"fragments": [{"audio": "abc"}]})
    assert resp.status_code == 200
