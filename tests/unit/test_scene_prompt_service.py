from src.domain.services import scene_prompt_service as sps
from src.domain.services import scene_prompt_templates as tpl


class _FakeResponse:
    def __init__(self, status_code, content=None):
        self.status_code = status_code
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeSession:
    """Devuelve una respuesta distinta por llamada, en orden."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def post(self, *a, **kw):
        idx = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[idx]


def test_segment_script_guion_corto_da_una_sola_escena():
    bloques, _ = sps.segment_script("hablemos de futbol argentina vs espana")
    assert len(bloques) == 1


def test_parse_batch_output_contenido_corto_no_produce_prompt():
    batch = [{"bloque_global_id": 1, "texto_original": "hablemos de futbol"}]
    # Menos de 4 palabras -> _clean_prompt lo descarta -> parseo vacio real.
    parsed = sps._parse_batch_output("Sin contexto.", batch)
    assert parsed == {}


def test_gen_batch_safe_reintenta_una_vez_para_escena_unica(monkeypatch):
    bloques = [{"bloque_global_id": 1, "texto_original": "hablemos de futbol argentina vs espana"}]
    fake = _FakeSession(
        [
            _FakeResponse(200, "Sin contexto suficiente."),  # no parsea -> mapping vacio
            _FakeResponse(200, "1. A crowded stadium with fans waving flags under bright lights."),
        ]
    )
    monkeypatch.setattr(sps, "_or_session", lambda pool_size: fake)

    mapping = sps._gen_batch_safe(
        bloques, "hablemos de futbol argentina vs espana", tpl.DEFAULT_ESTILO,
        "normal", tpl.SYS_N8N_AGENT, ["fake-model"], 0.38,
    )

    assert fake.calls == 2
    assert mapping[1].startswith("A crowded stadium")


def test_generate_prompts_guion_corto_no_cae_al_fallback_generico(monkeypatch):
    fake = _FakeSession(
        [
            _FakeResponse(200, "Sin contexto suficiente."),
            _FakeResponse(200, "1. A crowded stadium with fans waving flags under bright lights."),
        ]
    )
    monkeypatch.setattr(sps, "_or_session", lambda pool_size: fake)
    monkeypatch.setattr(sps, "_openrouter_models", lambda: ["fake-model"])

    resultado = sps.generate_prompts(
        "hablemos de futbol argentina vs espana", "prompts", "normal", "default", ""
    )

    prompt = resultado["escenas"][0]["prompt_imagen"]
    assert "Literal visual representation of" not in prompt
    assert prompt.startswith("A crowded stadium")


def test_generate_prompts_agota_reintentos_si_todo_falla_y_usa_fallback(monkeypatch):
    fake = _FakeSession([_FakeResponse(200, "Sin contexto.")])
    monkeypatch.setattr(sps, "_or_session", lambda pool_size: fake)
    monkeypatch.setattr(sps, "_openrouter_models", lambda: ["fake-model"])

    resultado = sps.generate_prompts(
        "hablemos de futbol argentina vs espana", "prompts", "normal", "default", ""
    )

    prompt = resultado["escenas"][0]["prompt_imagen"]
    assert prompt.startswith("Literal visual representation of:")
    assert "Ilustración conceptual para miniatura YouTube" in prompt
