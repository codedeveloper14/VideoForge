import base64
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.domain.services import scene_timestamp_service, usage_service
from src.domain.services.project_service import scene_sort_key
from src.infrastructure.ai_providers import modal_render_client, whisper_client
from src.infrastructure.ai_providers.modal_render_client import ModalRequestError
from src.infrastructure.media import ffmpeg_utils
from src.infrastructure.storage import project_repository, user_repository
from src.utils.logger import get_logger
from src.utils.platform_utils import no_window_kwargs, open_folder

logger = get_logger(__name__)

_jobs: dict[str, dict] = {}
_AUDIO_UPLOAD_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
_SCENE_NUM_RE = re.compile(r"^(?:img|flow)_(\d+)$", re.IGNORECASE)


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def get_job_video_path(job_id: str) -> str | None:
    job = _jobs.get(job_id)
    if not job:
        return None
    path = job.get("video_path")
    return path if path and os.path.exists(path) else None


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        val = int((os.environ.get(name) or str(default)).strip())
    except ValueError:
        val = default
    return max(lo, min(hi, val))


def start_render(*, project_name: str, render_mode: str, guion: str, resolucion: str, modelo: str,
                  whisper_backend: str, transicion: str, trans_dur: float, movimiento: str,
                  shake: bool, audio_upload, username: str | None) -> dict:
    """Prepara el proyecto (audio, imagenes/videos ordenados, guion) y lanza el pipeline en
    un hilo de fondo. Lanza ValueError en validaciones (--> 400 en la ruta)."""
    if not project_name:
        raise ValueError("Proyecto requerido")

    proj_dir = project_repository.project_dir(project_name)
    img_dir = proj_dir / "imagen"
    vid_dir = proj_dir / "video"
    audio_dir = proj_dir / "audio"
    out_dir = proj_dir / "video_final"
    out_dir.mkdir(parents=True, exist_ok=True)

    if audio_upload and audio_upload.filename:
        aext = os.path.splitext(audio_upload.filename)[-1].lower() or ".mp3"
        aext = aext if aext in _AUDIO_UPLOAD_EXTS else ".mp3"
        audio_path = str(audio_dir / f"render_audio{aext}")
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_upload.save(audio_path)
    else:
        audios = list(audio_dir.glob("*")) if audio_dir.exists() else []
        audio_path = str(audios[0]) if audios else None

    if not audio_path or not os.path.exists(audio_path):
        raise ValueError("No se encontro audio")

    images = []
    if img_dir.exists():
        for f in img_dir.iterdir():
            if f.is_file() and f.suffix.lower().lstrip(".") in project_repository.IMAGE_EXTS:
                images.append(f)
        images.sort(key=scene_sort_key)
    if not images and render_mode == "images":
        raise ValueError("No hay imagenes en el proyecto")

    videos = sorted(vid_dir.glob("*.mp4"), key=scene_sort_key) if vid_dir.exists() else []

    if not images and not videos:
        raise ValueError("El proyecto no tiene imagenes ni videos para renderizar")

    vid_index = {v.stem: v for v in videos}

    guion_path = None
    if guion:
        guion_dir = proj_dir / "guion"
        guion_dir.mkdir(parents=True, exist_ok=True)
        guion_path = str(guion_dir / "guion_render.txt")
        Path(guion_path).write_text(guion, encoding="utf-8")

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"id": job_id, "estado": "procesando", "progreso": 0,
                      "mensaje": "Iniciando...", "logs": [], "video_url": None, "inicio": time.time()}

    threading.Thread(
        target=_procesar_render_inteligente,
        args=(job_id, images, vid_index, audio_path, guion, resolucion, modelo,
              transicion, trans_dur, movimiento, shake, render_mode, str(out_dir),
              whisper_backend, guion_path, username),
        daemon=True,
    ).start()

    if username:
        try:
            user = user_repository.get_user_full(username)
            if user:
                usage_service.record_usage(user["id"], videos=1)
        except Exception:
            logger.exception("No se pudo registrar el uso de video para %s", username)

    return {"job_id": job_id}


def _procesar_render_inteligente(job_id, images, vid_index, audio_path, guion,
                                  resolucion, modelo, transicion, trans_dur,
                                  movimiento, shake, render_mode, out_dir,
                                  whisper_backend="local", guion_path=None,
                                  ri_user=None):
    """Pipeline hibrido: imagenes --> Modal GPU | videos --> FFmpeg local (paralelo)."""
    BATCH_SIZE = _int_env("VF_MODAL_BATCH_SIZE", 28, 8, 40)
    seg_par = _int_env("VF_RENDER_SEG_PARALLEL", 2, 1, 6)
    vid_clip_par = _int_env("VF_RENDER_VID_CLIP_PARALLEL", 2, 1, 4)
    modal_read_timeout = _int_env("VF_MODAL_READ_TIMEOUT_SEC", 240, 60, 1200)
    modal_connect_timeout = _int_env("VF_MODAL_CONNECT_TIMEOUT_SEC", 35, 8, 120)
    ff_threads = (os.environ.get("VF_FFMPEG_THREADS") or "0").strip() or "0"
    x264_thr = (os.environ.get("VF_FFMPEG_X264_THREADS") or "0").strip() or "0"
    modal_max_retries = _int_env("VF_MODAL_MAX_RETRIES", 4, 1, 8)
    MAX_LOG_LINES = 800
    FPS = 24
    modal_local = threading.local()

    def _modal_session():
        s = getattr(modal_local, "s", None)
        if s is None:
            s = modal_render_client.new_session(16)
            modal_local.s = s
        return s

    def log(msg, pct=None):
        logs = _jobs[job_id]["logs"]
        logs.append(msg)
        if len(logs) > MAX_LOG_LINES:
            del logs[: len(logs) - MAX_LOG_LINES]
        _jobs[job_id]["mensaje"] = msg
        if pct is not None:
            _jobs[job_id]["progreso"] = pct
        logger.info("[%s] %s", job_id, msg)

    tmp_dir = tempfile.mkdtemp()
    try:
        # ── Audio duration ──────────────────────────────────────────────
        log("Analizando audio...", 3)
        res = ffmpeg_utils.run_cmd(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", audio_path],
            "ffprobe no pudo leer audio",
        )
        try:
            parsed = json.loads(res.stdout)
            dur = (parsed.get("format") or {}).get("duration")
            if dur is None:
                r2 = ffmpeg_utils.run_cmd(
                    ["ffprobe", "-v", "error", "-show_entries", "stream=duration", "-of", "json", audio_path],
                    "ffprobe fallback fallo",
                )
                dur = next((s["duration"] for s in json.loads(r2.stdout).get("streams", [])
                            if s.get("duration")), None)
            duracion_total = float(dur)
        except Exception as de:
            raise Exception(f"No se pudo leer la duracion del audio: {de}")
        log(f"Audio: {duracion_total:.1f}s", 7)

        # ── Verificar duracion maxima segun plan (server-side) ──────────
        if ri_user:
            dur_ok, dur_msg = usage_service.check_video_duration(ri_user, duracion_total)
            if not dur_ok:
                log(dur_msg)
                _jobs[job_id].update({"estado": "error", "error": dur_msg,
                                       "limit_reached": True, "limit_type": "video_duration"})
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return

        # ── Whisper timestamps ───────────────────────────────────────────
        if guion_path and os.path.exists(guion_path):
            with open(guion_path, "r", encoding="utf-8") as gf:
                escenas_texto = [e.strip() for e in gf.read().split("\n") if e.strip()]
        elif guion:
            escenas_texto = [e.strip() for e in guion.split("\n") if e.strip()]
        else:
            n_items = len(images) if images else len(vid_index)
            escenas_texto = [f"Escena {i + 1}" for i in range(n_items)]

        if guion and guion.strip():
            all_words = None
            if whisper_backend == "api":
                log("Transcribiendo con Whisper API...", 10)
                try:
                    segmentos, all_words = whisper_client.transcribe_api(audio_path, language="es")
                except Exception as exc:
                    raise Exception(f"Whisper API error: {exc}")
                log(f"  (API: {len(all_words)} words --> {len(segmentos)} sub-segmentos)")
            elif whisper_backend == "faster":
                log(f"Transcribiendo con faster-whisper ({modelo})...", 10)
                try:
                    segmentos = whisper_client.transcribe_faster(audio_path, modelo)
                except Exception as exc:
                    raise Exception(f"faster-whisper error: {exc}")
            elif whisper_backend == "whisperx_local":
                log(f"Transcribiendo con WhisperX local ({modelo})...", 10)
                try:
                    segmentos, all_words = whisper_client.transcribe_whisperx_local(audio_path, modelo)
                except Exception as exc:
                    raise Exception(f"WhisperX local error: {exc}")
            elif whisper_backend == "whisperx":
                log("Transcribiendo con WhisperX Replicate (alineacion forzada)...", 10)
                try:
                    segmentos, all_words = whisper_client.transcribe_whisperx_replicate(audio_path, language=None)
                except Exception as exc:
                    raise Exception(f"WhisperX Replicate error: {exc}")
            else:
                log(f"Transcribiendo con Whisper ({modelo})...", 10)
                segmentos = whisper_client.transcribe_local(audio_path, modelo)
            log(f"{len(segmentos)} segmentos", 20)

            if all_words:
                timestamps = scene_timestamp_service.asignar_timestamps_words(escenas_texto, all_words, duracion_total)

                # ── Deteccion de fallo en word-level ─────────────────────
                # Con ciertas voces TTS el narrador lee numeros y abreviaciones
                # de forma distinta al texto del guion ("Kepler-70" --> "kepler setenta").
                # El n-gram matching exacto falla silenciosamente: encuentra coincidencias
                # en posiciones incorrectas del stream, produciendo escenas de 200-300s
                # que "absorben" decenas de escenas siguientes. Sintoma: >40% de escenas
                # sin match Y el ultimo match esta en los ultimos 15% del audio.
                # En ese caso, segment-level (bag-of-words overlap) es mas robusto
                # porque tolera variaciones de pronunciacion en los numeros.
                wl_unmatched = sum(1 for ts in timestamps if ts.get("score", 0) == 0)
                wl_last_ok = max((ts["fin"] for ts in timestamps if ts.get("score", 0) > 0), default=0.0)
                wl_ratio = wl_unmatched / max(1, len(timestamps))
                wl_late = wl_last_ok > duracion_total * 0.85
                wl_failed = wl_ratio > 0.40 and wl_late

                if wl_failed:
                    log(f"[WARNING] Word-level anomalo: {wl_unmatched}/{len(timestamps)} escenas sin "
                        f"coincidencia, ultimo match al {wl_last_ok / duracion_total * 100:.0f}% del audio.", 33)
                    log("   Causa probable: voz TTS lee numeros/abreviaciones distinto al guion.", 33)
                    log("   Usando segment-level (mas tolerante a variaciones de pronunciacion)...", 33)
                    timestamps = scene_timestamp_service.asignar_timestamps(escenas_texto, segmentos, duracion_total)
                    log(f"{len(timestamps)} timestamps (segment-level fallback)", 22)
                else:
                    log(f"{len(timestamps)} timestamps (word-level / precision maxima)", 22)
            else:
                timestamps = scene_timestamp_service.asignar_timestamps(escenas_texto, segmentos, duracion_total)
                log(f"{len(timestamps)} timestamps (segment-level)", 22)
        else:
            dur_eq = duracion_total / max(1, len(escenas_texto))
            timestamps = [{"inicio": i * dur_eq, "fin": (i + 1) * dur_eq, "duracion": dur_eq}
                          for i in range(len(escenas_texto))]
            log(f"{len(timestamps)} timestamps", 22)

        log("Timestamps por escena:")
        for i, ts in enumerate(timestamps):
            log(f"  E{i + 1:02d}: {ts['inicio']:.2f}s --> {ts['fin']:.2f}s  dur={ts['duracion']:.3f}s  "
                f"score={ts.get('score', 0):.2f}  seg={ts.get('seg_idx', '?')}")

        # ── Build scene list ──────────────────────────────────────────────
        # Un timestamp por linea de guion: si hay mas timestamps que imagenes (p. ej. Whisk
        # genero menos clips), reutilizar la ultima imagen - evita videos cortos con -shortest
        # en el mux final.
        scenes = []
        if not images and render_mode in ("smart", "videos") and vid_index:
            vids_sorted = sorted(vid_index.values(), key=lambda p: p.name)
            n_ts, n_vids = len(timestamps), len(vids_sorted)
            n_total = max(n_ts, n_vids)
            if n_ts > n_vids:
                log(f"[WARNING] {n_ts} timestamps pero solo {n_vids} videos - se reutiliza el ultimo.", 25)
            for i in range(n_total):
                vid = vids_sorted[min(i, n_vids - 1)]
                ts = timestamps[min(i, n_ts - 1)] if timestamps else {
                    "inicio": 0, "fin": duracion_total / max(1, n_vids), "duracion": duracion_total / max(1, n_vids)}
                vid_path = str(vid) if vid.exists() else None
                scenes.append({
                    "type": "video" if vid_path else "image",
                    "img_path": str(vid), "vid_path": vid_path,
                    "duracion": max(0.5, float(ts["duracion"])),
                    "inicio": float(ts.get("inicio", 0)),
                    "fin": float(ts.get("fin", ts.get("inicio", 0) + ts["duracion"])),
                    "escena_idx": i,
                })
        else:
            n_ts, n_img = len(timestamps), len(images)
            if n_ts > n_img:
                log(f"[WARNING] {n_ts} timestamps (guion) pero {n_img} imagenes - "
                    f"se reutiliza la ultima imagen en las {n_ts - n_img} escenas finales.", 25)
            # Mapa escena-->imagen por nombre de archivo (img_00001-->escena 0, etc.)
            # Robusto ante fallos de Whisk: si falta img_00003.png, la escena 2 usa el
            # fallback pero las escenas 3,4,... siguen viendo su imagen correcta.
            img_by_scene = {}
            for img in images:
                mm = _SCENE_NUM_RE.match(img.stem)
                if mm:
                    img_by_scene[int(mm.group(1)) - 1] = img
            if n_ts >= n_img:
                for i in range(n_ts):
                    ts = timestamps[i]
                    sidx = ts.get("scene_idx", i)
                    img = img_by_scene.get(sidx) or images[min(sidx, n_img - 1)]
                    vid = vid_index.get(img.stem) if render_mode in ("smart", "videos") else None
                    vid_path = str(vid) if vid and os.path.exists(str(vid)) else None
                    scenes.append({
                        "type": "video" if vid_path else "image",
                        "img_path": str(img), "vid_path": vid_path,
                        "duracion": max(0.5, float(ts["duracion"])),
                        "inicio": float(ts.get("inicio", 0)),
                        "fin": float(ts.get("fin", ts.get("inicio", 0) + ts["duracion"])),
                        "escena_idx": i,
                    })
            else:
                ts_by_scene = {t.get("scene_idx", j): t for j, t in enumerate(timestamps)}
                for i, img in enumerate(images):
                    mm2 = _SCENE_NUM_RE.match(img.stem)
                    sidx2 = int(mm2.group(1)) - 1 if mm2 else i
                    ts = ts_by_scene.get(sidx2, timestamps[min(i, n_ts - 1)])
                    vid = vid_index.get(img.stem) if render_mode in ("smart", "videos") else None
                    vid_path = str(vid) if vid and os.path.exists(str(vid)) else None
                    scenes.append({
                        "type": "video" if vid_path else "image",
                        "img_path": str(img), "vid_path": vid_path,
                        "duracion": max(0.5, float(ts["duracion"])),
                        "escena_idx": i,
                    })
        total_vid = sum(float(s["duracion"]) for s in scenes)
        gap = float(duracion_total) - total_vid
        if gap > 0.08 and scenes:
            scenes[-1]["duracion"] = round(max(0.5, float(scenes[-1]["duracion"]) + gap), 3)
            log(f"Ajuste fin de linea: +{gap:.2f}s en ultima escena "
                f"(suma escenas {total_vid:.1f}s --> audio {duracion_total:.1f}s).", 26)
        n_vid = sum(1 for s in scenes if s["type"] == "video")
        log(f"{len(scenes)} escenas - {n_vid} video / {len(scenes) - n_vid} imagen", 25)

        # ── Resolution ────────────────────────────────────────────────────
        try:
            w_res, h_res = [int(x) for x in resolucion.split("x")]
        except Exception:
            w_res, h_res = 1920, 1080

        # ── Silent audio (Modal necesita audio_b64 valido por batch) ────────
        silent = os.path.join(tmp_dir, "silent.mp3")
        ffmpeg_utils.run_cmd(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", str(duracion_total), "-b:a", "32k", silent],
            "No se pudo crear audio silencioso",
        )
        silent_b64 = base64.b64encode(open(silent, "rb").read() if os.path.exists(silent) else b"").decode()

        # ── Compressed audio para mezcla final ───────────────────────────
        asm = os.path.join(tmp_dir, "audio_s.mp3")
        ra = subprocess.run(["ffmpeg", "-y", "-i", audio_path, "-ar", "44100", "-ac", "1",
                              "-b:a", "64k", "-movflags", "+faststart", asm],
                             capture_output=True, text=True, **no_window_kwargs())
        audio_path_mix = (asm if ra.returncode == 0 and os.path.exists(asm)
                          and os.path.getsize(asm) > 1000 else audio_path)

        # ── _encode_img: JPEG 960px para enviar a Modal ──────────────────
        def _encode_img(sc):
            ib = modal_render_client.encode_image_b64(sc["img_path"])
            return {"imagen_b64": ib, "duracion": sc["duracion"], "movimiento": movimiento, "is_video": False}

        # ── _render_vid_clip: escala + letterbox un clip de video con FFmpeg ─
        def _render_vid_clip(sc):
            out = os.path.join(tmp_dir, f"vc_{sc['escena_idx']:05d}.mp4")
            dur = sc["duracion"]
            try:
                src_d = float(ffmpeg_utils.ffprobe_duration(sc["vid_path"]))
            except Exception:
                src_d = 0.0

            # Generar clip con duracion 100% EXACTA: paso 1 ralentiza con setpts
            # (se ve bien visualmente); paso 2 recorta a int(dur*24) frames exactos
            # para eliminar drift acumulativo sin sacrificar la ralentizacion.
            n_frames_exact = int(round(dur * FPS))
            dur_exact = n_frames_exact / FPS
            out_tmp = out.replace(".mp4", "_slow.mp4")

            if src_d > 0.05 and src_d < dur_exact * 0.98:
                ratio = dur_exact / src_d
                if ratio <= 1.60:
                    pts_expr = f"{ratio:.8f}*PTS"
                    log(f"  clip E{sc['escena_idx'] + 1}: {src_d:.2f}s --> {dur_exact:.3f}s (x{ratio:.3f})")
                else:
                    pts_expr = "PTS"
                    log(f"  clip E{sc['escena_idx'] + 1}: {src_d:.2f}s < {dur_exact:.3f}s --> freeze")
                vf_s = f"{ffmpeg_utils.scale_pad_filter(w_res, h_res, FPS)},setpts={pts_expr}"
                if ratio > 1.60:
                    vf_s += f",tpad=stop_mode=clone:stop_duration={(dur_exact - src_d):.6f}"
            else:
                vf_s = f"{ffmpeg_utils.scale_pad_filter(w_res, h_res, FPS)},setpts=PTS-STARTPTS"

            r = subprocess.run([
                "ffmpeg", "-y", "-threads", ff_threads, "-i", sc["vid_path"],
                "-map", "0:v:0", "-vf", vf_s,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-x264-params", f"threads={x264_thr}",
                "-an", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_tmp,
            ], capture_output=True, text=True, **no_window_kwargs())

            if os.path.exists(out_tmp) and os.path.getsize(out_tmp) > 500:
                subprocess.run([
                    "ffmpeg", "-y", "-threads", ff_threads, "-i", out_tmp,
                    "-frames:v", str(n_frames_exact),
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                    "-x264-params", f"threads={x264_thr}",
                    "-an", "-pix_fmt", "yuv420p", "-r", str(FPS), "-vsync", "cfr",
                    "-movflags", "+faststart", out,
                ], capture_output=True, text=True, **no_window_kwargs())
                try:
                    os.remove(out_tmp)
                except Exception:
                    pass
            elif os.path.exists(out_tmp):
                os.replace(out_tmp, out)

            if not (os.path.exists(out) and os.path.getsize(out) > 500):
                err = (r.stderr or "")[-400:].strip()
                log(f"  [WARNING] _render_vid_clip E{sc['escena_idx'] + 1} fallback: {err[-200:]}")
                vf_fb = f"{ffmpeg_utils.scale_pad_filter(w_res, h_res, FPS)},setpts=PTS-STARTPTS"
                subprocess.run([
                    "ffmpeg", "-y", "-threads", ff_threads, "-i", sc["vid_path"],
                    "-map", "0:v:0", "-vf", vf_fb,
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                    "-x264-params", f"threads={x264_thr}",
                    "-an", "-r", str(FPS), "-vsync", "cfr", "-pix_fmt", "yuv420p",
                    "-frames:v", str(n_frames_exact),
                    "-movflags", "+faststart", out,
                ], capture_output=True, text=True, **no_window_kwargs())
            return out if (os.path.exists(out) and os.path.getsize(out) > 500) else None

        # ── _render_img_segment: llama a Modal con un segmento de imagenes ──
        def _render_img_segment(args):
            seg_idx, img_scenes = args
            n_b = max(1, math.ceil(len(img_scenes) / BATCH_SIZE))
            batches = [img_scenes[i * BATCH_SIZE:(i + 1) * BATCH_SIZE] for i in range(n_b)]
            clips = []
            for bi, batch in enumerate(batches):
                log(f"  seg{seg_idx} batch {bi + 1}/{n_b}: preparando {len(batch)} escenas")
                is_last_batch = (bi == n_b - 1)
                batch_mod = []
                for j, sc in enumerate(batch):
                    sc_m = _encode_img(sc)
                    is_last_of_segment = is_last_batch and (j == len(batch) - 1)
                    if transicion != "none" and not is_last_of_segment:
                        sc_m["duracion"] = round(sc["duracion"] + trans_dur, 3)
                    batch_mod.append(sc_m)
                # Duracion objetivo del clip que devuelve Modal para este batch. Se
                # recorta/normaliza a este valor para evitar drift de PTS que
                # terminaria desincronizando cortes con el audio.
                try:
                    expected_dur = float(sum(float(x.get("duracion", 0.0)) for x in batch_mod))
                except Exception:
                    expected_dur = 0.0
                payload = {
                    "audio_b64": silent_b64,
                    "escenas": batch_mod,
                    "resolucion": resolucion.replace("x", ":"),
                    "transicion": transicion,
                    "trans_dur": trans_dur,
                    "fade": 0,
                    "shake": "true" if shake else "false",
                }

                def _on_retry(msg, _seg=seg_idx, _bi=bi, _nb=n_b):
                    log(f"  [WARNING] seg{_seg} batch {_bi + 1}/{_nb}: {msg}")

                def _on_reset_session():
                    modal_local.s = modal_render_client.new_session(16)

                try:
                    log(f"  seg{seg_idx} batch {bi + 1}/{n_b}: enviando a Modal")
                    d = modal_render_client.post_batch(
                        _modal_session(), payload, modal_connect_timeout, modal_read_timeout,
                        modal_max_retries, on_retry=_on_retry, on_reset_session=_on_reset_session,
                    )
                    log(f"  seg{seg_idx} batch {bi + 1}/{n_b}: respuesta Modal OK")
                except ModalRequestError as merr:
                    log(f"  [WARNING] seg{seg_idx} batch {bi + 1}/{n_b}: Modal no respondio, "
                        f"fallback local estatico. {str(merr)[:140]}")
                    batch_clips = []
                    for j, sc in enumerate(batch):
                        fb = os.path.join(tmp_dir, f"seg_{seg_idx:03d}_b{bi:02d}_fb_{j:02d}.mp4")
                        img_path = sc.get("img_path", "")
                        if img_path and os.path.exists(img_path):
                            subprocess.run([
                                "ffmpeg", "-y", "-threads", ff_threads, "-loop", "1", "-i", img_path,
                                "-t", str(max(0.1, float(sc.get("duracion", 1.0)))),
                                "-vf", f"{ffmpeg_utils.scale_pad_filter(w_res, h_res)},setpts=PTS-STARTPTS",
                                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                                "-x264-params", f"threads={x264_thr}",
                                "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", fb,
                            ], capture_output=True, text=True, **no_window_kwargs())
                        if os.path.exists(fb) and os.path.getsize(fb) > 500:
                            batch_clips.append(fb)
                    if not batch_clips:
                        raise Exception(f"Modal seg {seg_idx} batch {bi}: request error {merr}. {merr.body}")
                    if len(batch_clips) == 1:
                        bp = batch_clips[0]
                    else:
                        bp = os.path.join(tmp_dir, f"seg_{seg_idx:03d}_b{bi:02d}.mp4")
                        cl = os.path.join(tmp_dir, f"seg_{seg_idx:03d}_b{bi:02d}_fb.txt")
                        ffmpeg_utils.write_concat_list(cl, batch_clips)
                        ffmpeg_utils.run_cmd([
                            "ffmpeg", "-y", "-threads", ff_threads, "-f", "concat", "-safe", "0", "-i", cl,
                            "-vf", "setpts=PTS-STARTPTS",
                            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                            "-x264-params", f"threads={x264_thr}",
                            "-pix_fmt", "yuv420p", "-r", "24", "-an", "-movflags", "+faststart", bp,
                        ], f"Fallback local batch seg {seg_idx} fallo")
                    clips.append(bp)
                    continue

                if not d.get("success"):
                    raise Exception(f"Modal seg {seg_idx} batch {bi}: {d.get('error', 'error')}")
                video_b64 = d.get("video_b64") or d.get("video_base64")
                if not isinstance(video_b64, str) or not video_b64.strip():
                    raise Exception(f"Modal seg {seg_idx} batch {bi}: respuesta sin video_b64 valido. "
                                     f"Claves: {list(d.keys())[:20]}")
                bp = os.path.join(tmp_dir, f"seg_{seg_idx:03d}_b{bi:02d}.mp4")
                try:
                    decoded_video = base64.b64decode(video_b64)
                except Exception as b64_err:
                    raise Exception(f"Modal seg {seg_idx} batch {bi}: base64 invalido ({b64_err})")
                with open(bp, "wb") as f:
                    f.write(decoded_video)
                if not os.path.exists(bp) or os.path.getsize(bp) <= 500:
                    raise Exception(f"Modal seg {seg_idx} batch {bi}: clip vacio o invalido")
                # Normalizar codec Modal --> libx264 ultrafast para compatibilidad con clips locales
                bp_n = bp.replace(".mp4", "_n.mp4")
                cmd = ["ffmpeg", "-y", "-threads", ff_threads, "-i", bp]
                if expected_dur:
                    cmd += ["-t", str(max(0.1, expected_dur))]
                cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                        "-x264-params", f"threads={x264_thr}",
                        "-pix_fmt", "yuv420p", "-r", "24", "-an",
                        "-movflags", "+faststart", bp_n]
                subprocess.run(cmd, capture_output=True, text=True, **no_window_kwargs())
                if os.path.exists(bp_n) and os.path.getsize(bp_n) > 500:
                    os.replace(bp_n, bp)
                clips.append(bp)

            if len(clips) == 1:
                return seg_idx, clips[0]

            # Descartar clips con dimensiones invalidas (ej. 0x1) antes del concat -
            # un clip asi hace fallar todo el filter_complex.
            clips_ok = []
            for bi_v, bp_v in enumerate(clips):
                try:
                    pr_v = subprocess.run(
                        ["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=width,height", "-of", "json", bp_v],
                        capture_output=True, text=True, **no_window_kwargs())
                    st_v = json.loads(pr_v.stdout).get("streams", [{}])
                    bw_v = int((st_v[0] if st_v else {}).get("width", 0) or 0)
                    bh_v = int((st_v[0] if st_v else {}).get("height", 0) or 0)
                    if bw_v < 2 or bh_v < 2:
                        log(f"  [WARNING] seg{seg_idx} batch{bi_v} descartado: dim invalida "
                            f"{bw_v}x{bh_v} --> {os.path.basename(bp_v)}")
                        continue
                except Exception:
                    pass
                clips_ok.append(bp_v)
            if not clips_ok:
                raise Exception(f"seg {seg_idx}: todos los batches tienen dimensiones invalidas - abortando")
            clips = clips_ok
            if len(clips) == 1:
                return seg_idx, clips[0]

            co = os.path.join(tmp_dir, f"seg_{seg_idx:03d}.mp4")
            n_c = len(clips)
            for bi, bp in enumerate(clips):
                try:
                    pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "json", bp], capture_output=True, text=True, **no_window_kwargs())
                    bd = float(json.loads(pr.stdout).get("format", {}).get("duration", 0))
                    log(f"  batch{bi}: {os.path.basename(bp)} dur={bd:.3f}s")
                except Exception:
                    pass
            # Normalizar resolucion de cada batch antes de concatenar - sin esto, si
            # Modal devuelve clips con dimensiones distintas, FFmpeg falla el concat.
            fc_inputs = []
            for cp in clips:
                fc_inputs += ["-i", cp]
            fp = "".join(
                f"[{k}:v]{ffmpeg_utils.scale_pad_filter(w_res, h_res)},setpts=PTS-STARTPTS[v{k}];"
                for k in range(n_c)
            )
            fp += "".join(f"[v{k}]" for k in range(n_c))
            fp += f"concat=n={n_c}:v=1:a=0[vout]"
            ffmpeg_utils.run_cmd(["ffmpeg", "-y", "-threads", ff_threads] + fc_inputs + [
                "-filter_complex", fp, "-map", "[vout]",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-x264-params", f"threads={x264_thr}",
                "-pix_fmt", "yuv420p", "-r", "24", "-an",
                "-movflags", "+faststart", co,
            ], f"No se pudo concatenar batches de imagen seg {seg_idx}")
            try:
                pr2 = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                       "-of", "json", co], capture_output=True, text=True, **no_window_kwargs())
                sd = float(json.loads(pr2.stdout).get("format", {}).get("duration", 0))
                esp = sum(sc["duracion"] for sc in img_scenes)
                log(f"  seg{seg_idx} concat: dur={sd:.3f}s esperado={esp:.3f}s delta={sd - esp:+.3f}s")
            except Exception:
                pass
            return seg_idx, co

        # ── _render_vid_segment: procesa clips de video en paralelo con FFmpeg ─
        def _render_vid_segment(args):
            seg_idx, vid_scenes = args

            def _render_one(sc):
                return sc["escena_idx"], _render_vid_clip(sc)

            with ThreadPoolExecutor(max_workers=min(len(vid_scenes), vid_clip_par)) as ex:
                res_vid = list(ex.map(_render_one, vid_scenes))
            res_vid.sort(key=lambda x: x[0])
            sc_map = {sc["escena_idx"]: sc for sc in vid_scenes}
            clip_paths = []
            for eidx, path in res_vid:
                if path and os.path.exists(path) and os.path.getsize(path) > 500:
                    clip_paths.append(path)
                    continue
                sc = sc_map[eidx]
                fb = os.path.join(tmp_dir, f"vc_{eidx:05d}_fb.mp4")
                log(f"  [WARNING] clip E{eidx + 1} fallo - usando imagen estatica como fallback")
                img_path = sc.get("img_path", "")
                img_ok = img_path and os.path.exists(img_path)
                if img_ok:
                    subprocess.run([
                        "ffmpeg", "-y", "-threads", ff_threads, "-loop", "1", "-i", img_path,
                        "-t", str(sc["duracion"]),
                        "-vf", f"{ffmpeg_utils.scale_pad_filter(w_res, h_res)},setpts=PTS-STARTPTS",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                        "-x264-params", f"threads={x264_thr}",
                        "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", fb,
                    ], capture_output=True, **no_window_kwargs())
                if not img_ok or not (os.path.exists(fb) and os.path.getsize(fb) > 500):
                    subprocess.run([
                        "ffmpeg", "-y", "-threads", ff_threads, "-f", "lavfi",
                        "-i", f"color=c=black:s={w_res}x{h_res}:r=24:d={sc['duracion']}",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                        "-x264-params", f"threads={x264_thr}",
                        "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", fb,
                    ], capture_output=True, **no_window_kwargs())
                if os.path.exists(fb) and os.path.getsize(fb) > 500:
                    clip_paths.append(fb)
            if not clip_paths:
                raise Exception(f"Segmento video {seg_idx}: ningun clip generado")
            if len(clip_paths) == 1:
                return seg_idx, clip_paths[0]
            cl = os.path.join(tmp_dir, f"seg_{seg_idx:03d}_cl.txt")
            ffmpeg_utils.write_concat_list(cl, clip_paths)
            co = os.path.join(tmp_dir, f"seg_{seg_idx:03d}.mp4")
            seg_dur_exact = sum(sc["duracion"] for sc in vid_scenes)
            seg_frames_exact = int(round(seg_dur_exact * 24))
            ffmpeg_utils.run_cmd([
                "ffmpeg", "-y", "-threads", ff_threads, "-f", "concat", "-safe", "0", "-i", cl,
                "-vf", "setpts=PTS-STARTPTS", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-x264-params", f"threads={x264_thr}",
                "-pix_fmt", "yuv420p", "-r", "24", "-vsync", "cfr", "-an",
                "-frames:v", str(seg_frames_exact),
                "-movflags", "+faststart", co,
            ], f"No se pudo concatenar clips de video seg {seg_idx}")
            try:
                prv = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                       "-of", "json", co], capture_output=True, text=True, **no_window_kwargs())
                vd = float(json.loads(prv.stdout).get("format", {}).get("duration", 0))
                drift = vd - seg_dur_exact
                log(f"  seg{seg_idx} video concat: {len(vid_scenes)} clips, dur={vd:.3f}s "
                    f"esperado={seg_dur_exact:.3f}s delta={drift:+.3f}s")
                if abs(drift) > 0.042 and vd > 0.1:
                    corr_ratio = seg_dur_exact / vd
                    co_corr = co.replace(".mp4", "_corr.mp4")
                    subprocess.run([
                        "ffmpeg", "-y", "-threads", ff_threads, "-i", co,
                        "-vf", f"setpts={corr_ratio:.8f}*PTS-STARTPTS",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                        "-x264-params", f"threads={x264_thr}",
                        "-pix_fmt", "yuv420p", "-r", "24", "-vsync", "cfr", "-an",
                        "-frames:v", str(seg_frames_exact),
                        "-movflags", "+faststart", co_corr,
                    ], capture_output=True, **no_window_kwargs())
                    if os.path.exists(co_corr) and os.path.getsize(co_corr) > 500:
                        os.replace(co_corr, co)
                        log(f"  [OK] seg{seg_idx} drift corregido: {drift:+.3f}s --> 0.000s")
            except Exception:
                pass
            return seg_idx, co

        # ── Agrupar escenas en segmentos consecutivos por tipo ───────────
        segments = []
        cur_type, cur_batch = None, []
        for sc in scenes:
            if sc["type"] != cur_type:
                if cur_batch:
                    segments.append((cur_type, cur_batch))
                cur_type, cur_batch = sc["type"], [sc]
            else:
                cur_batch.append(sc)
        if cur_batch:
            segments.append((cur_type, cur_batch))

        n_img_segs = sum(1 for t, _ in segments if t == "image")
        n_vid_segs = sum(1 for t, _ in segments if t == "video")
        log(f"{len(segments)} segmentos - {n_img_segs} imagen->Modal / {n_vid_segs} video->FFmpeg", 30)

        log("Procesando segmentos en paralelo...", 35)

        def _process_segment(args):
            seg_idx, (seg_type, seg_scenes) = args
            if seg_type == "image":
                return _render_img_segment((seg_idx, seg_scenes))
            return _render_vid_segment((seg_idx, seg_scenes))

        with ThreadPoolExecutor(max_workers=min(seg_par, len(segments))) as ex:
            results = list(ex.map(_process_segment, enumerate(segments)))
        results.sort(key=lambda x: x[0])
        log(f"{len(results)} segmentos listos", 82)

        seg_paths_raw = [(idx, p) for idx, p in results if p and os.path.exists(p)]
        log(f"Segmentos para stitch: {len(seg_paths_raw)}/{len(results)}")
        for idx, p in seg_paths_raw:
            try:
                pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                      "format=duration,stream=codec_name,width,height,r_frame_rate",
                                      "-of", "json", p], capture_output=True, text=True, **no_window_kwargs())
                log(f"  seg{idx}: {os.path.basename(p)} - {pr.stdout[:200].strip()}")
            except Exception:
                log(f"  seg{idx}: {os.path.basename(p)}")
        if not seg_paths_raw:
            raise Exception("No se generaron clips de segmentos")

        log("Liberando espacio temporal...", 84)
        seg_finals = set(p for _, p in seg_paths_raw)
        for f in os.listdir(tmp_dir):
            fp = os.path.join(tmp_dir, f)
            if fp not in seg_finals and f not in ("silent.mp3", "audio_s.mp3"):
                try:
                    os.remove(fp)
                except Exception:
                    pass

        # Unir segmentos con filter_complex: normaliza specs en un solo paso.
        # CRF 28 para reducir uso de disco (~4x menos que CRF 18, calidad suficiente).
        log("Uniendo y normalizando segmentos con filter_complex...", 85)
        concat_out = os.path.join(tmp_dir, "concat_final.mp4")
        n_segs = len(seg_paths_raw)
        inputs = []
        for _, p in seg_paths_raw:
            inputs += ["-i", p]
        vf = f"{ffmpeg_utils.scale_pad_filter(w_res, h_res)},setpts=PTS-STARTPTS"
        total_frames_exact = int(round(duracion_total * 24))
        filter_parts = "".join(f"[{i}:v]{vf}[v{i}];" for i in range(n_segs))
        concat_inputs = "".join(f"[v{i}]" for i in range(n_segs))
        filter_str = f"{filter_parts}{concat_inputs}concat=n={n_segs}:v=1:a=0[vout]"
        ffmpeg_utils.run_cmd(
            ["ffmpeg", "-y", "-threads", ff_threads] + inputs + [
                "-filter_complex", filter_str, "-map", "[vout]",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-x264-params", f"threads={x264_thr}",
                "-pix_fmt", "yuv420p", "-r", "24", "-vsync", "cfr", "-an",
                "-frames:v", str(total_frames_exact),
                "-movflags", "+faststart", concat_out,
            ], "No se pudo unir segmentos finales",
        )

        # ── Mezcla de audio final (alineado a duracion del audio maestro; sin -shortest) ─
        log("Mezclando audio...", 90)
        video_final = os.path.join(out_dir, f"render_{job_id}.mp4")
        try:
            ffmpeg_utils.final_mux_aligned(concat_out, audio_path_mix, video_final, duracion_total, log=log)
        except Exception as mux_e:
            raise Exception(f"No se pudo mezclar audio final: {mux_e}") from mux_e

        if not os.path.exists(video_final):
            raise Exception("FFmpeg no genero el video final")

        size_mb = os.path.getsize(video_final) / (1024 * 1024)
        log(f"Video listo - {size_mb:.1f} MB", 100)
        _jobs[job_id].update({
            "estado": "completado",
            "video_url": f"/api/descargar_render/{job_id}",
            "video_path": video_final,
            "size_mb": round(size_mb, 1),
            "duracion": round(duracion_total, 1),
            "escenas": len(scenes),
        })
        open_folder(video_final)
        shutil.rmtree(tmp_dir, ignore_errors=True)

    except Exception as exc:
        logger.exception("[%s] render fallo", job_id)
        err_msg = str(exc)
        log(f"Error: {err_msg}")
        log(f"Carpeta temporal conservada para diagnostico: {tmp_dir}")
        _jobs[job_id].update({"estado": "error", "error": err_msg, "tmp_dir": tmp_dir})
