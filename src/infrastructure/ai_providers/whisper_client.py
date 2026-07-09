import os
import threading

from src.core.config import config
from src.utils.logger import get_logger

logger = get_logger(__name__)

_WHISPERX_REPLICATE_MODEL = (
    "victor-upmeet/whisperx:84d2ad2d6194fe98a17d2b60bef1c7f910c46b2f6fd38996ca457afd9c8abfcb"
)


def _split_api_segmentos(all_words: list[dict], tr_segments) -> list[dict]:
    """Divide segmentos largos de Whisper API en sub-segmentos por oracion/pausa."""
    if not all_words:
        return [
            {"start": float(s.start), "end": float(s.end), "text": s.text, "words": []}
            for s in (tr_segments or [])
        ]
    segmentos = []
    for s in tr_segments or []:
        seg_words = [w for w in all_words if float(s.start) - 0.05 <= w["start"] <= float(s.end) + 0.05]
        if not seg_words:
            segmentos.append({"start": float(s.start), "end": float(s.end), "text": s.text, "words": []})
            continue
        cur = []
        for k, w in enumerate(seg_words):
            cur.append(w)
            is_last = k == len(seg_words) - 1
            ends_s = w.get("word", "").strip().rstrip(",").endswith((".", "?", "!", ";"))
            has_pause = False
            if not is_last:
                we = float(w.get("end", w.get("start", 0)))
                ns = float(seg_words[k + 1].get("start", we))
                has_pause = (ns - we) >= 0.15
            if (ends_s or has_pause or is_last) and cur:
                segmentos.append(
                    {
                        "start": float(cur[0].get("start", float(s.start))),
                        "end": float(cur[-1].get("end", cur[-1].get("start", float(s.end)))),
                        "text": " ".join(ww.get("word", "").strip() for ww in cur),
                        "words": list(cur),
                    }
                )
                cur = []
    return segmentos or [
        {"start": float(s.start), "end": float(s.end), "text": s.text, "words": []}
        for s in (tr_segments or [])
    ]


def transcribe_api(audio_path: str, language: str = "es") -> tuple[list[dict], list[dict]]:
    """Whisper API (OpenAI whisper-1). Devuelve (segmentos, all_words)."""
    from openai import OpenAI

    client = OpenAI(api_key=config.openai_whisper_key)
    with open(audio_path, "rb") as f:
        tr = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language=language,
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
        )
    all_words = [
        {"word": w.word, "start": float(w.start), "end": float(w.end)}
        for w in (getattr(tr, "words", None) or [])
    ]
    if not all_words:
        for s in tr.segments or []:
            for w in getattr(s, "words", None) or []:
                all_words.append({"word": w.word, "start": float(w.start), "end": float(w.end)})
    segmentos = _split_api_segmentos(all_words, tr.segments)
    return segmentos, all_words


def transcribe_faster(audio_path: str, model: str) -> list[dict]:
    """faster-whisper local (CPU, int8)."""
    from faster_whisper import WhisperModel

    fwm = WhisperModel(model, device="cpu", compute_type="int8")
    segs_raw, _ = fwm.transcribe(audio_path, language=None, word_timestamps=True, beam_size=2)
    segmentos = []
    for s in segs_raw:
        segmentos.append(
            {
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "words": [{"word": w.word, "start": w.start, "end": w.end} for w in (s.words or [])],
            }
        )
    return segmentos


def transcribe_whisperx_local(audio_path: str, model: str) -> tuple[list[dict], list[dict]]:
    """WhisperX local (CPU) con alineacion forzada. Devuelve (segmentos, all_words)."""
    import whisperx

    device = "cpu"
    wx_model = whisperx.load_model(model, device, compute_type="int8", language="es")
    audio = whisperx.load_audio(audio_path)
    result = wx_model.transcribe(audio, batch_size=8, language="es")
    del wx_model
    align_model, align_meta = whisperx.load_align_model(language_code="es", device=device)
    aligned = whisperx.align(
        result["segments"], align_model, align_meta, audio, device, return_char_alignments=False
    )
    del align_model
    all_words = []
    for s in aligned["segments"]:
        for w in s.get("words") or []:
            if w.get("start") is not None:
                all_words.append(
                    {
                        "word": w.get("word", ""),
                        "start": float(w["start"]),
                        "end": float(w.get("end", w["start"])),
                    }
                )
    segmentos = [
        {
            "start": float(s["start"]),
            "end": float(s["end"]),
            "text": s.get("text", ""),
            "words": [
                {
                    "word": w.get("word", ""),
                    "start": float(w["start"]),
                    "end": float(w.get("end", w["start"])),
                }
                for w in (s.get("words") or [])
                if w.get("start") is not None
            ],
        }
        for s in aligned["segments"]
    ]
    return segmentos, all_words


def transcribe_whisperx_replicate(
    audio_path: str, language: str | None = "es"
) -> tuple[list[dict], list[dict]]:
    """WhisperX via Replicate (alineacion forzada), subiendo el audio directamente
    con el cliente oficial de replicate.run(). Devuelve (segmentos, all_words)."""
    if not config.replicate_api_key:
        raise Exception("Falta REPLICATE_API_KEY en la configuracion (.env).")
    try:
        import replicate as replicate_client
    except ImportError:
        raise Exception("Falta el paquete 'replicate'. Instalalo con: pip install replicate")

    os.environ["REPLICATE_API_TOKEN"] = config.replicate_api_key

    input_payload = {
        "audio_file": open(audio_path, "rb"),
        "align_output": True,
        "only_text": False,
        "batch_size": 4,
    }
    if language:
        input_payload["language"] = language

    result_box: list = [None]
    error_box: list = [None]
    timeout_secs = 120

    def _run():
        try:
            result_box[0] = replicate_client.run(_WHISPERX_REPLICATE_MODEL, input=input_payload)
        except Exception as exc:
            error_box[0] = exc

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout_secs)
    if t.is_alive():
        raise Exception(f"WhisperX Replicate: timeout tras {timeout_secs}s - usando fallback local.")
    if error_box[0]:
        raise Exception(f"WhisperX Replicate error: {error_box[0]}")
    output = result_box[0]
    if not output:
        raise Exception("WhisperX Replicate: la prediccion no devolvio output.")

    segs_raw = output.get("segments") or (output.get("results") or {}).get("segments") or []
    all_words = []
    segmentos = []
    for s in segs_raw:
        words_s = []
        for w in s.get("words") or []:
            if w.get("start") is not None:
                wd = {
                    "word": w.get("word", ""),
                    "start": float(w["start"]),
                    "end": float(w.get("end", w["start"])),
                }
                all_words.append(wd)
                words_s.append(wd)
        segmentos.append(
            {
                "start": float(s.get("start", 0)),
                "end": float(s.get("end", 0)),
                "text": s.get("text", ""),
                "words": words_s,
            }
        )
    return segmentos, all_words


def transcribe_local(audio_path: str, model: str) -> list[dict]:
    """Whisper local (paquete 'openai-whisper')."""
    import whisper

    wm = whisper.load_model(model)
    resultado = wm.transcribe(audio_path, language=None, word_timestamps=True)
    return resultado.get("segments", [])


def transcribe_with_fallback(audio_path: str) -> tuple[list[dict], list[dict], str]:
    """Cascada automatica whisperx (Replicate) -> faster-whisper -> whisper local ->
    sin transcripcion, usando cada paso solo si el anterior fallo. A diferencia de
    render_service (que usa el backend elegido explicitamente por el usuario, sin
    cascada), esto es para flujos donde no se pide un backend concreto (editor visual)."""
    try:
        segmentos, all_words = transcribe_whisperx_replicate(audio_path, language=None)
        return segmentos, all_words, "whisperx_replicate"
    except Exception as exc:
        logger.info("transcribe_with_fallback: whisperx fallo (%s), probando faster-whisper...", exc)

    try:
        segmentos = transcribe_faster(audio_path, "medium")
        all_words = [w for s in segmentos for w in s.get("words", [])]
        return segmentos, all_words, "faster_whisper"
    except ImportError:
        pass

    try:
        segmentos = transcribe_local(audio_path, "medium")
        all_words = [w for s in segmentos for w in s.get("words", [])]
        return segmentos, all_words, "openai_whisper"
    except ImportError:
        pass

    return [], [], "guion_estimate"
