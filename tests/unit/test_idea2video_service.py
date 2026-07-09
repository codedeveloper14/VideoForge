import pytest

from src.domain.services import idea2video_service as i2v


def test_parse_scenes_divide_por_lineas_en_blanco():
    script = "Escena uno con texto suficiente.\n\nEscena dos con mas texto aca.\n\ncorta"
    scenes = i2v._parse_scenes(script)
    # "corta" (5 chars) queda filtrada por el umbral de >15 caracteres.
    assert scenes == ["Escena uno con texto suficiente.", "Escena dos con mas texto aca."]


def test_extract_prompts_usa_tag_visual_si_existe():
    scenes = ["[ESCENA 1]\n[Visual: un gato en la playa al atardecer]\n[Audio: musica]\n\nHola"]
    prompts = i2v._extract_prompts(scenes)
    assert prompts == ["un gato en la playa al atardecer"]


def test_extract_prompts_cae_a_primera_oracion_sin_tag():
    scenes = ["Un texto sin ningun tag de visual que sea suficientemente largo. Segunda oracion."]
    prompts = i2v._extract_prompts(scenes)
    assert prompts == ["Un texto sin ningun tag de visual que sea suficientemente largo"]


def test_extract_prompts_maximo_20():
    scenes = [f"[Visual: escena numero {i} con suficiente longitud aca]" for i in range(30)]
    prompts = i2v._extract_prompts(scenes)
    assert len(prompts) == 20


def test_extract_narration_quita_tags_de_escena_y_visual():
    script = "[ESCENA 1 - GANCHO | ~7 seg]\n[Visual: algo]\n[Audio: musica]\n\nHola mundo, esto es narracion."
    narration = i2v._extract_narration(script)
    assert "[ESCENA" not in narration
    assert "[Visual" not in narration
    assert "Hola mundo, esto es narracion." in narration


def test_extract_narration_trunca_a_8000_caracteres():
    script = "palabra " * 2000  # muy largo
    narration = i2v._extract_narration(script)
    assert len(narration) <= 8000


def test_template_script_genera_estructura_esperada():
    result = i2v._template_script("el cambio climatico", dur_sec=60, style="tutorial",
                                    tone="profesional", audience="general")
    assert result["scenes"] >= 4
    assert "[ESCENA 1" in result["script"]
    assert "el cambio climatico" in result["script"]
    assert result["dur"] == "1m00s"
    assert result["words"] > 0


def test_template_script_estilo_desconocido_usa_default():
    result = i2v._template_script("tema x", dur_sec=30, style="no_existe",
                                    tone="no_existe", audience="general")
    assert result["scenes"] >= 4  # no explota, usa fallback cinematic/inspirador


def test_generate_script_rechaza_idea_vacia():
    with pytest.raises(ValueError):
        i2v.generate_script("", dur_sec=60, style="cinematic", tone="inspirador", audience="general")


def test_generate_script_clampa_duracion(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)

    result = i2v.generate_script("una idea", dur_sec=99999, style="cinematic",
                                  tone="inspirador", audience="general")
    # dur_sec se clampa a 1200 antes de generar -> dur_label debe reflejar 20 minutos.
    assert result["dur"] == "20m00s"


def test_generate_script_sin_api_key_usa_template(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)

    result = i2v.generate_script("una idea cualquiera", dur_sec=45, style="viral",
                                  tone="urgente", audience="jovenes")
    assert "[ESCENA 1" in result["script"]
    assert result["dur"] == "45s"


def test_scan_images_arma_urls_relativas(tmp_path):
    img_dir = tmp_path / "imagenes"
    img_dir.mkdir()
    (img_dir / "b.png").write_bytes(b"x")
    (img_dir / "a.jpg").write_bytes(b"x")

    job = {}
    i2v._scan_images(job, "mi_proyecto", img_dir)

    assert len(job["images"]) == 2
    assert all(url.startswith("/api/idea2video/ap_imagen?project=mi_proyecto&file=") for url in job["images"])
