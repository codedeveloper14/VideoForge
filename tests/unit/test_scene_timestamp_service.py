from src.domain.services import scene_timestamp_service as sts


def test_proporcional_divide_duracion_en_partes_iguales():
    escenas = ["uno", "dos", "tres", "cuatro"]
    resultado = sts.proporcional(escenas, 40.0)

    assert len(resultado) == 4
    for i, ts in enumerate(resultado):
        assert ts["duracion"] == 10.0
        assert ts["inicio"] == i * 10.0
        assert ts["fin"] == (i + 1) * 10.0
        assert ts["score"] == 0


def test_asignar_timestamps_sin_segmentos_cae_a_proporcional():
    escenas = ["a", "b"]
    resultado = sts.asignar_timestamps(escenas, [], 20.0)
    assert resultado == sts.proporcional(escenas, 20.0)


def test_contar_palabras_comunes_ignora_mayusculas_y_puntuacion():
    score = sts.contar_palabras_comunes("Hola, Mundo!", "hola mundo bonito")
    assert score == 1.0  # las 2 palabras de "a" estan en "b"


def test_contar_palabras_comunes_sin_texto_devuelve_cero():
    assert sts.contar_palabras_comunes("", "algo") == 0


def test_asignar_timestamps_words_sin_words_cae_a_proporcional():
    escenas = ["hola mundo", "chau mundo"]
    resultado = sts.asignar_timestamps_words(escenas, [], 10.0)
    assert resultado == sts.proporcional(escenas, 10.0)


def _make_words(texto: str, start: float, step: float = 0.3):
    """Genera una lista de dicts {word,start,end} espaciados uniformemente,
    imitando la salida de un transcriptor word-level."""
    words = []
    t = start
    for w in texto.split():
        words.append({"word": w, "start": round(t, 3), "end": round(t + step - 0.02, 3)})
        t += step
    return words


def test_asignar_timestamps_words_encuentra_ngrams_en_orden():
    escenas = ["el gato duerme", "el perro corre rapido"]
    all_words = _make_words("el gato duerme en la casa", 0.0) + _make_words("el perro corre rapido", 3.0)

    resultado = sts.asignar_timestamps_words(escenas, all_words, duracion_total=6.0)

    assert len(resultado) == 2
    # La escena 1 matchea al principio del stream, la 2 mas adelante.
    assert resultado[0]["inicio"] < resultado[1]["inicio"]
    assert resultado[0]["score"] > 0
    assert resultado[1]["score"] > 0
    # Los timestamps deben quedar dentro del rango total.
    assert resultado[-1]["fin"] <= 6.0 + 0.01


def test_assign_timestamps_auto_sin_nada_cae_a_proporcional():
    escenas = ["uno", "dos"]
    resultado = sts.assign_timestamps_auto(escenas, [], None, 10.0)
    assert resultado == sts.proporcional(escenas, 10.0)


def test_assign_timestamps_auto_sin_words_usa_segment_level():
    escenas = ["hola mundo"]
    segmentos = [{"text": "hola mundo", "start": 0.0, "end": 2.0, "words": []}]
    resultado = sts.assign_timestamps_auto(escenas, segmentos, None, 2.0)
    assert resultado == sts.asignar_timestamps(escenas, segmentos, 2.0)


def test_assign_timestamps_auto_usa_word_level_cuando_matchea_bien():
    escenas = ["el gato duerme"]
    all_words = _make_words("el gato duerme tranquilo", 0.0)
    fallback_calls = []

    resultado = sts.assign_timestamps_auto(
        escenas, [], all_words, duracion_total=2.0, on_fallback=lambda *a: fallback_calls.append(a))

    assert resultado[0]["score"] > 0
    assert not fallback_calls  # no debio caer al fallback, matcheo bien


def test_assign_timestamps_auto_cae_a_segment_level_si_word_level_falla_al_final():
    # La mayoria de las escenas no tienen ninguna palabra en comun con el audio real
    # (simula voz TTS que lee numeros/siglas distinto al guion) y la unica que si
    # matchea cae muy tarde en el audio (>85% de la duracion) -- dispara la heuristica
    # de fallback a segment-level (>40% sin match Y ultimo match tardio).
    escenas = [
        "palabra faltante uno", "palabra faltante dos",
        "palabra faltante tres", "palabra faltante cuatro",
        "frase objetivo especial",
    ]
    duracion_total = 20.0
    all_words = _make_words("frase objetivo especial", start=18.0)
    segmentos = [{"text": "frase objetivo especial", "start": 18.0, "end": 20.0, "words": []}]
    fallback_calls = []

    resultado = sts.assign_timestamps_auto(
        escenas, segmentos, all_words, duracion_total,
        on_fallback=lambda *a: fallback_calls.append(a))

    assert fallback_calls, "deberia haber invocado on_fallback"
    assert resultado == sts.asignar_timestamps(escenas, segmentos, duracion_total)
