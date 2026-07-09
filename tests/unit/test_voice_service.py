from src.domain.services import voice_service


def test_sanitize_tts_text_colapsa_saltos_de_linea_y_espacios():
    text = "Hola\r\nmundo\ncomo   estas\r  hoy"
    assert voice_service._sanitize_tts_text(text) == "Hola mundo como estas hoy"


def test_sanitize_tts_text_reemplaza_comillas_y_backslash():
    text = 'dijo "hola" y luego \\ algo'
    result = voice_service._sanitize_tts_text(text)
    assert '"' not in result
    assert "\\" not in result
    assert "'hola'" in result


def test_split_text_no_parte_si_es_corto():
    text = "Un texto corto que no necesita dividirse."
    assert voice_service._split_text(text, 900) == [text]


def test_split_text_corta_en_limite_de_oracion():
    frase1 = "Primera oracion completa aqui."
    frase2 = "Segunda oracion completa aqui tambien."
    text = frase1 + " " + frase2
    chunks = voice_service._split_text(text, max_chars=45)
    assert chunks == [frase1, frase2]


def test_split_text_cae_a_espacio_si_no_hay_punto():
    text = "palabra " * 50  # sin puntuacion
    chunks = voice_service._split_text(text.strip(), max_chars=100)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 100
        assert not chunk.startswith(" ") and not chunk.endswith(" ")


def test_split_text_reconstituye_todo_el_contenido():
    text = ("Esta es una oracion larga de prueba. " * 10).strip()
    chunks = voice_service._split_text(text, max_chars=80)
    # Ningun caracter del texto original se pierde en la union (salvo espacios de corte).
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")
