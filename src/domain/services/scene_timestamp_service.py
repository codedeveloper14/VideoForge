import re

_TRIVIALES = {
    "el",
    "la",
    "los",
    "las",
    "un",
    "una",
    "de",
    "en",
    "a",
    "y",
    "o",
    "que",
    "se",
    "es",
    "su",
    "me",
    "te",
    "con",
    "por",
    "para",
    "si",
    "no",
    "ya",
}
_COMUNES_NGRAM = {
    "the",
    "a",
    "an",
    "in",
    "on",
    "at",
    "to",
    "of",
    "and",
    "or",
    "is",
    "it",
    "its",
    "be",
    "was",
    "are",
    "for",
    "as",
    "with",
    "but",
    "not",
    "this",
    "that",
    "they",
    "you",
    "your",
    "we",
    "i",
    "my",
    "me",
    "he",
    "she",
    "his",
    "her",
    "their",
    "our",
}


def limpiar(texto: str) -> str:
    texto = texto.lower().strip()
    texto = re.sub(r'[¿¡.,;:!?\-–—""\'()\[\]]', "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto


def contar_palabras_comunes(a: str, b: str) -> float:
    pa = set(limpiar(a).split())
    pb = set(limpiar(b).split())
    if not pa:
        return 0
    return len(pa & pb) / len(pa)


def proporcional(escenas: list[str], duracion_total: float) -> list[dict]:
    dur = duracion_total / len(escenas)
    return [
        {
            "inicio": round(i * dur, 3),
            "fin": round((i + 1) * dur, 3),
            "duracion": round(dur, 3),
            "seg_idx": i,
            "score": 0,
        }
        for i in range(len(escenas))
    ]


def _refinar_inicio(escena: str, seg: dict) -> float:
    """
    Devuelve el punto de corte para el inicio de la escena dentro del segmento.
    Encuentra la primera palabra clave, luego verifica si hay una pausa natural
    (>= 0.15s) en las 2 words INMEDIATAMENTE anteriores a esa palabra.
    Si la hay, corta en esa pausa (silencio entre parrafos).
    Si no, usa el start de la palabra clave.
    Esto evita que la imagen aparezca antes de que el audio diga la palabra.
    """
    words = seg.get("words", [])
    if not words:
        return seg["start"]

    claves = [w for w in limpiar(escena).split() if w not in _TRIVIALES and len(w) > 2]
    if not claves:
        claves = [w for w in limpiar(escena).split() if w]
    if not claves:
        return seg["start"]

    words_limpias = [limpiar(w.get("word", "")) for w in words]

    palabra_idx = None
    for clave in claves[:3]:
        for i, wl in enumerate(words_limpias):
            if wl == clave:
                palabra_idx = i
                break
        if palabra_idx is None:
            for i, wl in enumerate(words_limpias):
                if wl and (clave in wl or wl in clave) and len(wl) > 2:
                    palabra_idx = i
                    break
        if palabra_idx is not None:
            break

    if palabra_idx is None:
        return seg["start"]

    t_palabra = float(words[palabra_idx].get("start", seg["start"]))

    for k in range(max(0, palabra_idx - 2), palabra_idx):
        w_end = float(words[k].get("end", words[k].get("start", 0)))
        w_next = float(words[k + 1].get("start", w_end))
        if (w_next - w_end) >= 0.15:
            return round(w_end, 3)

    return round(t_palabra, 3)


def asignar_timestamps(escenas: list[str], segmentos: list[dict], duracion_total: float) -> list[dict]:
    n = len(escenas)
    if not segmentos:
        return proporcional(escenas, duracion_total)

    asignaciones = []
    ultimo = 0
    for i, escena in enumerate(escenas):
        mejor_score, mejor_idx = -1, ultimo
        limite = min(len(segmentos), ultimo + max(5, len(segmentos) // n * 3))
        for j in range(ultimo, limite):
            st = segmentos[j].get("text", "")
            score = contar_palabras_comunes(escena, st)
            if j + 1 < len(segmentos):
                t2 = st + " " + segmentos[j + 1].get("text", "")
                score = max(score, contar_palabras_comunes(escena, t2) * 0.9)
            if score > mejor_score:
                mejor_score, mejor_idx = score, j
        asignaciones.append((mejor_idx, mejor_score))
        ultimo = mejor_idx

    resultado = []
    prev_fin = 0.0
    i = 0
    while i < n:
        idx, score = asignaciones[i]
        seg = segmentos[idx]

        j = i + 1
        while j < n and asignaciones[j][0] == idx:
            j += 1
        grupo = list(range(i, j))

        if len(grupo) == 1:
            inicio = _refinar_inicio(escenas[i], seg)
            inicio = max(inicio, prev_fin)
            if i < n - 1:
                idx_sig = asignaciones[i + 1][0]
                fin = _refinar_inicio(escenas[i + 1], segmentos[idx_sig])
                if fin <= inicio:
                    fin = seg["end"]
            else:
                fin = duracion_total
            if fin <= inicio:
                fin = round(inicio + 0.5, 3)
            dur = max(0.5, round(fin - inicio, 3))
            fin = round(inicio + dur, 3)
            resultado.append(
                {
                    "inicio": round(inicio, 3),
                    "fin": fin,
                    "duracion": dur,
                    "seg_idx": idx,
                    "score": round(score, 3),
                }
            )
            prev_fin = fin
            i = j
        else:
            t_inicio_grupo = max(prev_fin, _refinar_inicio(escenas[grupo[0]], seg))
            if j < n:
                idx_sig = asignaciones[j][0]
                t_fin_grupo = _refinar_inicio(escenas[j], segmentos[idx_sig])
                if t_fin_grupo <= t_inicio_grupo:
                    t_fin_grupo = seg["end"]
            else:
                t_fin_grupo = duracion_total
            if t_fin_grupo <= t_inicio_grupo:
                t_fin_grupo = t_inicio_grupo + len(grupo) * 1.0

            pesos = [max(1, len(limpiar(escenas[k]).split())) for k in grupo]
            total_p = sum(pesos)
            rango = t_fin_grupo - t_inicio_grupo
            t = t_inicio_grupo
            for ki, gi in enumerate(grupo):
                _, sc = asignaciones[gi]
                t_ini = round(t, 3)
                t_fin = round(t + rango * pesos[ki] / total_p, 3)
                if t_fin <= t_ini:
                    t_fin = round(t_ini + 0.5, 3)
                dur = max(0.5, round(t_fin - t_ini, 3))
                t_fin = round(t_ini + dur, 3)
                resultado.append(
                    {"inicio": t_ini, "fin": t_fin, "duracion": dur, "seg_idx": idx, "score": round(sc, 3)}
                )
                t = t_fin
                prev_fin = t_fin
            i = j

    return resultado


def asignar_timestamps_words(escenas: list[str], all_words: list[dict], duracion_total: float) -> list[dict]:
    """
    Asignacion word-level usando n-gram matching para evitar falsos positivos
    con palabras comunes. Busca secuencias de 2-3 palabras consecutivas del guion
    en el stream de words, avanzando secuencialmente.
    """
    if not all_words or not escenas:
        return proporcional(escenas, duracion_total)

    words_limpias = [limpiar(w.get("word", "")) for w in all_words]
    n_words = len(all_words)
    n_escenas = len(escenas)

    def _palabras_escena(texto):
        return [w for w in limpiar(texto).split() if len(w) > 0]

    def _buscar_ngram(palabras_guion, desde, max_ventana=600):
        hasta = min(n_words, desde + max_ventana)
        palabras = palabras_guion

        for ngram_size in [3, 2, 1]:
            if len(palabras) < ngram_size:
                continue
            ngrams_guion = []
            for j in range(min(len(palabras) - ngram_size + 1, 6)):
                ng = tuple(palabras[j : j + ngram_size])
                if ngram_size == 1 and ng[0] in _COMUNES_NGRAM:
                    continue
                ngrams_guion.append((j, ng))

            best_pos = None
            best_guion_j = len(palabras)
            for guion_j, ng in ngrams_guion:
                for k in range(desde, hasta - ngram_size + 1):
                    if tuple(words_limpias[k : k + ngram_size]) == ng:
                        if guion_j < best_guion_j:
                            best_pos = max(desde, k - guion_j)
                            best_guion_j = guion_j
                        break
            if best_pos is not None:
                return best_pos

        return None

    resultado = []
    ultimo_idx = 0

    for i, escena in enumerate(escenas):
        palabras = _palabras_escena(escena)
        if not palabras:
            t_prev = resultado[-1]["fin"] if resultado else 0
            resultado.append(
                {
                    "inicio": t_prev,
                    "fin": round(t_prev + 1.0, 3),
                    "duracion": 1.0,
                    "seg_idx": ultimo_idx,
                    "score": 0,
                    "scene_idx": i,
                }
            )
            continue

        first_idx = _buscar_ngram(palabras, ultimo_idx, max_ventana=800)

        if first_idx is None:
            t_prev = resultado[-1]["inicio"] if resultado else 0
            t_interp = round(t_prev + (duracion_total - t_prev) / max(1, n_escenas - i), 3)
            resultado.append(
                {
                    "inicio": t_interp,
                    "fin": t_interp,
                    "duracion": 0,
                    "seg_idx": ultimo_idx,
                    "score": 0,
                    "scene_idx": i,
                }
            )
            continue

        t_inicio = round(float(all_words[first_idx].get("start", 0)), 3)
        if first_idx > 0:
            prev_end = float(
                all_words[first_idx - 1].get("end", all_words[first_idx - 1].get("start", t_inicio))
            )
            pausa_prev = t_inicio - prev_end
            if pausa_prev >= 0.08:
                t_inicio = round(prev_end + 0.03, 3)

        resultado.append(
            {
                "inicio": t_inicio,
                "fin": t_inicio,
                "duracion": 0,
                "seg_idx": first_idx,
                "score": 1.0,
                "scene_idx": i,
            }
        )
        ultimo_idx = first_idx + 1

    resultado.sort(key=lambda x: x["inicio"])
    for i in range(len(resultado)):
        if i + 1 < len(resultado):
            t_fin = resultado[i + 1]["inicio"]
        else:
            t_fin = duracion_total
        t_inicio = resultado[i]["inicio"]
        if t_fin <= t_inicio:
            t_fin = round(t_inicio + 0.5, 3)
        dur = max(0.3, round(t_fin - t_inicio, 3))
        resultado[i]["fin"] = round(t_fin, 3)
        resultado[i]["duracion"] = dur

    # Redistribuir bloque final de escenas mal asignadas: con ciertas voces
    # WhisperX agota el stream de palabras antes de cubrir todas las escenas.
    tail_start = len(resultado)
    for k in range(len(resultado) - 1, -1, -1):
        if resultado[k]["score"] > 0 and resultado[k]["duracion"] >= 1.0:
            tail_start = k + 1
            break

    tail_indices = list(range(tail_start, len(resultado)))
    n_tail = len(tail_indices)
    tail_has_unmatched = any(resultado[i].get("score", 0) == 0 for i in tail_indices)
    if n_tail >= 5 and tail_has_unmatched:
        t0 = resultado[tail_start - 1]["fin"] if tail_start > 0 else 0.0
        t_disponible = max(0.0, duracion_total - t0)

        pesos = [
            max(1, len(_palabras_escena(escenas[resultado[i].get("scene_idx", i)]))) for i in tail_indices
        ]
        total_p = sum(pesos) or 1

        dur_min = 0.5
        t_rango = max(t_disponible, dur_min * n_tail)

        t = t0
        for ki, idx in enumerate(tail_indices):
            t_ini = round(t, 3)
            dur = max(dur_min, round(t_rango * pesos[ki] / total_p, 3))
            resultado[idx]["inicio"] = t_ini
            resultado[idx]["fin"] = round(t_ini + dur, 3)
            resultado[idx]["duracion"] = dur
            t = resultado[idx]["fin"]

    return resultado


def assign_timestamps_auto(
    escenas: list[str],
    segmentos: list[dict],
    all_words: list[dict] | None,
    duracion_total: float,
    on_fallback=None,
) -> list[dict]:
    """Asigna timestamps con word-level (n-gram) si hay palabras, y cae a segment-level
    si el resultado de word-level parece fallido: heuristica >40% de escenas sin match
    Y el ultimo match cae en el ultimo 15% del audio (voz TTS que lee numeros/siglas
    distinto al guion, el n-gram matching falla silenciosamente en esos casos).
    on_fallback(unmatched, total, last_ok, duracion_total), si se pasa, se invoca justo
    antes de recalcular con segment-level (para que el llamador pueda loguear el motivo)."""
    if not segmentos and not all_words:
        return proporcional(escenas, duracion_total)
    if not all_words:
        return asignar_timestamps(escenas, segmentos, duracion_total)

    timestamps = asignar_timestamps_words(escenas, all_words, duracion_total)
    unmatched = sum(1 for ts in timestamps if ts.get("score", 0) == 0)
    last_ok = max((ts["fin"] for ts in timestamps if ts.get("score", 0) > 0), default=0.0)
    ratio = unmatched / max(1, len(timestamps))
    late = last_ok > duracion_total * 0.85
    if ratio > 0.40 and late:
        if on_fallback:
            on_fallback(unmatched, len(timestamps), last_ok, duracion_total)
        return asignar_timestamps(escenas, segmentos, duracion_total)
    return timestamps
