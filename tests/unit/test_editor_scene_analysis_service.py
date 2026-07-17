import types

from src.domain.services import editor_scene_analysis_service as sas


class _FakeResponse:
    def __init__(self, status_code, content):
        self.status_code = status_code
        self.text = content or ""

    def json(self):
        return {"choices": [{"message": {"content": self.text}, "finish_reason": "stop"}]}


def test_call_openrouter_batch_prueba_siguiente_modelo_si_el_primero_no_parsea(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        model = json["model"]
        if model == sas._MODELS[0]:
            return _FakeResponse(200, "esto no es json en absoluto")
        return _FakeResponse(200, '[{"tipo": "quote_animado"}]')

    monkeypatch.setattr(sas.requests, "post", fake_post)

    lote = sas._call_openrouter_batch("sys", "user", "fake-key")

    assert calls["n"] == 2
    assert lote == [{"tipo": "quote_animado"}]


def test_analizar_escenas_usa_fallback_normal_solo_si_todos_los_modelos_fallan(monkeypatch):
    monkeypatch.setattr(sas, "config", types.SimpleNamespace(openrouter_api_key="fake-key"))

    def fake_post(url, headers=None, json=None, timeout=None):
        return _FakeResponse(200, "esto no es json en absoluto")

    monkeypatch.setattr(sas.requests, "post", fake_post)

    resultado = sas.analizar_escenas([{"texto": "hola mundo"}], "mi-video")

    assert len(resultado) == 1
    assert resultado[0]["tipo"] == "normal"


def test_analizar_escenas_no_cae_a_normal_si_algun_modelo_parsea_bien(monkeypatch):
    monkeypatch.setattr(sas, "config", types.SimpleNamespace(openrouter_api_key="fake-key"))

    def fake_post(url, headers=None, json=None, timeout=None):
        model = json["model"]
        if model == sas._MODELS[0]:
            return _FakeResponse(200, "esto no es json en absoluto")
        return _FakeResponse(200, '[{"tipo": "quote_animado"}]')

    monkeypatch.setattr(sas.requests, "post", fake_post)

    resultado = sas.analizar_escenas([{"texto": "una cita textual importante"}], "mi-video")

    assert resultado[0]["tipo"] == "quote_animado"
