"""El pipeline de generacion mas antiguo de la app (/api/generar): sube guion + audio +
imagenes directo, sin necesidad de un proyecto -- distinto del Render normal
(render_service, basado en proyectos) y del render enriquecido del editor. Cada job vive
en su propia carpeta AppData/jobs/<job_id>/ (audio.mp3, guion.txt, imagenes/, video_final.mp4),
no bajo un nombre de proyecto."""

import base64
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from src.domain.services import scene_timestamp_service
from src.infrastructure.ai_providers import modal_render_client, whisper_client
from src.infrastructure.ai_providers.modal_render_client import ModalRequestError
from src.infrastructure.jobs import job_registry
from src.infrastructure.media import ffmpeg_utils
from src.utils.logger import get_logger
from src.utils.paths import get_jobs_dir
from src.utils.platform_utils import no_window_kwargs, open_folder

logger = get_logger(__name__)

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
_IMAGE_CT_EXT = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAX_CHUNK_SECONDS = 8.0
_BATCH_SIZE = 30
_MODAL_MAX_RETRIES = 4
_MODAL_CONNECT_TIMEOUT = 30
_MODAL_READ_TIMEOUT = 900


def get_job(job_id: str) -> dict | None:
    return job_registry.get_job(job_id)


def get_job_video_path(job_id: str) -> str | None:
    job = job_registry.get_job(job_id)
    if not job:
        return None
    path = job.get("video_path")
    return path if path and os.path.exists(path) else None


def start_render(
    *,
    audio_upload,
    guion: str,
    image_uploads: list,
    resolucion: str = "1920x1080",
    fade: float = 0.0,
    modelo: str = "base",
    whisper_backend: str = "whisperx",
    transicion: str = "none",
    movimiento: str = "none",
    trans_dur: float = 0.8,
    shake: str = "false",
) -> dict:
    """Valida y guarda audio/guion/imagenes en una carpeta de job nueva, y lanza el
    worker en un hilo de fondo. Lanza ValueError en validaciones (--> 400 en la ruta)."""
    job_id = str(uuid.uuid4())[:8]
    job_dir = get_jobs_dir() / job_id
    imgs_dir = job_dir / "imagenes"
    imgs_dir.mkdir(parents=True, exist_ok=True)

    if not audio_upload or not audio_upload.filename:
        raise ValueError("Falta el archivo de audio")
    audio_path = job_dir / "audio.mp3"
    audio_upload.save(str(audio_path))

    guion = (guion or "").strip()
    if not guion:
        raise ValueError("El guion esta vacio")
    guion_path = job_dir / "guion.txt"
    guion_path.write_text(guion, encoding="utf-8")

    if not image_uploads:
        raise ValueError("No se subieron imagenes")
    for i, img_file in enumerate(image_uploads):
        ext = _IMAGE_CT_EXT.get(img_file.content_type or "image/png", ".jpg")
        img_file.save(str(imgs_dir / f"img_{i:03d}{ext}"))

    job_registry.create_job(
        job_id,
        {
            "id": job_id,
            "estado": "procesando",
            "progreso": 0,
            "mensaje": "Iniciando...",
            "logs": [],
            "video_url": None,
            "inicio": time.time(),
        },
    )

    threading.Thread(
        target=_procesar_video,
        args=(
            job_id,
            str(job_dir),
            str(audio_path),
            str(guion_path),
            str(imgs_dir),
            resolucion,
            fade,
            modelo,
            transicion,
            movimiento,
            trans_dur,
            shake,
            whisper_backend,
        ),
        daemon=True,
    ).start()

    return {"job_id": job_id}


def _procesar_video(
    job_id,
    job_dir,
    audio_path,
    guion_path,
    imgs_dir,
    resolucion,
    fade,
    modelo,
    transicion,
    movimiento,
    trans_dur,
    shake,
    whisper_backend="local",
):
    def log(msg, pct=None):
        job = job_registry.get_job(job_id)
        job["logs"].append(msg)
        job["mensaje"] = msg
        if pct is not None:
            job["progreso"] = pct
        logger.info("[%s] %s", job_id, msg)

    tmp_dir = tempfile.mkdtemp()
    try:
        log("Leyendo guion...", 5)
        escenas = [e.strip() for e in Path(guion_path).read_text(encoding="utf-8").split("\n") if e.strip()]
        log(f"{len(escenas)} escenas", 10)

        log("Cargando imagenes...", 12)
        imagenes = sorted(
            (str(p) for p in Path(imgs_dir).iterdir() if p.suffix.lower() in _IMAGE_EXTS),
            key=lambda p: os.path.basename(p),
        )
        if not imagenes:
            raise Exception("No se encontraron imagenes")
        log(f"{len(imagenes)} imagenes | {len(escenas)} escenas", 15)

        log("Analizando audio...", 18)
        duracion_total = ffmpeg_utils.ffprobe_duration(audio_path)
        if duracion_total <= 0:
            raise Exception("No se pudo leer la duracion del audio")
        log(f"Audio: {duracion_total:.1f}s", 20)

        all_words: list[dict] = []
        if whisper_backend == "api":
            log("Transcribiendo con Whisper API...", 22)
            segmentos, all_words = whisper_client.transcribe_api(audio_path, language="es")
            log(f"{len(all_words)} words --> {len(segmentos)} sub-segmentos (API)", 30)
        elif whisper_backend == "faster":
            log(f"Transcribiendo con faster-whisper ({modelo})...", 22)
            segmentos = whisper_client.transcribe_faster(audio_path, modelo)
            log(f"{len(segmentos)} segmentos (faster-whisper)", 30)
        elif whisper_backend == "whisperx_local":
            log(f"Transcribiendo con WhisperX local ({modelo})...", 22)
            segmentos, all_words = whisper_client.transcribe_whisperx_local(audio_path, modelo)
            log(f"{len(all_words)} words alineadas --> {len(segmentos)} segmentos (WhisperX local)", 30)
        elif whisper_backend == "whisperx":
            log("Transcribiendo con WhisperX Replicate (alineacion forzada)...", 22)
            segmentos, all_words = whisper_client.transcribe_whisperx_replicate(audio_path, language=None)
            log(f"{len(all_words)} words alineadas --> {len(segmentos)} segmentos (WhisperX Replicate)", 30)
        else:
            log(f"Transcribiendo con Whisper ({modelo})...", 22)
            segmentos = whisper_client.transcribe_local(audio_path, modelo)
            log(f"{len(segmentos)} segmentos transcritos", 30)

        log("Asignando timestamps...", 32)

        def _on_fallback(unmatched, total, last_ok, dur):
            log(
                f"[WARNING] Word-level anomalo ({unmatched}/{total} sin match) --> segment-level fallback", 33
            )

        timestamps = scene_timestamp_service.assign_timestamps_auto(
            escenas, segmentos, all_words, duracion_total, on_fallback=_on_fallback
        )
        log(f"{len(timestamps)} timestamps listos", 35)
        log("Timestamps por escena:")
        for i, ts in enumerate(timestamps):
            log(
                f"  E{i + 1:02d}: {ts['inicio']:.2f}s --> {ts['fin']:.2f}s  dur={ts['duracion']:.3f}s  "
                f"score={ts.get('score', 0):.2f}  seg={ts.get('seg_idx', '?')}"
            )

        log("Codificando archivos para Modal...", 40)
        # Batch mode: audio silencioso en la nube, se mezcla el audio real al final --
        # evita reinicios de audio entre batches al concatenar.
        silent_audio = os.path.join(tmp_dir, "silent.mp3")
        sil = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=mono",
                "-t",
                str(max(1.0, duracion_total)),
                "-b:a",
                "32k",
                silent_audio,
            ],
            capture_output=True,
            text=True,
            **no_window_kwargs(),
        )
        if sil.returncode == 0 and os.path.exists(silent_audio):
            with open(silent_audio, "rb") as f:
                batch_audio_b64 = base64.b64encode(f.read()).decode("utf-8")
        else:
            with open(audio_path, "rb") as f:
                batch_audio_b64 = base64.b64encode(f.read()).decode("utf-8")

        # Mapa escena-->imagen por nombre de archivo -- evita desplazamiento si falta
        # una imagen intermedia (img_00003 faltante no corre las demas).
        img_by_scene = {}
        for ip in imagenes:
            m = re.match(r"^img_(\d+)$", os.path.splitext(os.path.basename(ip))[0], re.IGNORECASE)
            if m:
                img_by_scene[int(m.group(1)) - 1] = ip

        escenas_modal = []
        for i, ts in enumerate(timestamps):
            sidx = ts.get("scene_idx", i)
            img_path = img_by_scene.get(sidx) or imagenes[min(sidx, len(imagenes) - 1)]
            with open(img_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
            base_dur = ts["duracion"]
            if base_dur <= _MAX_CHUNK_SECONDS:
                escenas_modal.append({"imagen_b64": img_b64, "duracion": base_dur, "movimiento": movimiento})
            else:
                remaining = base_dur
                while remaining > 0:
                    d = min(_MAX_CHUNK_SECONDS, remaining)
                    escenas_modal.append({"imagen_b64": img_b64, "duracion": d, "movimiento": movimiento})
                    remaining -= d

        resolucion_modal = resolucion.replace("x", ":")
        total_escenas = len(escenas_modal)
        n_batches = (total_escenas + _BATCH_SIZE - 1) // _BATCH_SIZE
        log(f"Procesando en la nube ({total_escenas} escenas en batches de {_BATCH_SIZE})...", 60)

        session = modal_render_client.new_session()
        part_files = []
        batch_dur_esperada = []
        for b_idx in range(n_batches):
            batch = escenas_modal[b_idx * _BATCH_SIZE : (b_idx + 1) * _BATCH_SIZE]
            batch_dur_esperada.append(sum(sc["duracion"] for sc in batch))
            batch_payload = {
                "audio_b64": batch_audio_b64,
                "escenas": batch,
                "resolucion": resolucion_modal,
                "transicion": transicion,
                "trans_dur": trans_dur,
                "fade": fade,
                "shake": shake,
                "batch_mode": True,
                "batch_index": b_idx,
                "batch_total": n_batches,
            }
            prog = 60 + int(30 * (b_idx + 1) / n_batches)
            log(f"  Batch {b_idx + 1}/{n_batches} ({len(batch)} escenas)...", prog)

            def _on_retry(msg, _b=b_idx, _nb=n_batches):
                log(f"  [WARNING] Batch {_b + 1}/{_nb}: {msg}")

            try:
                d = modal_render_client.post_batch(
                    session,
                    batch_payload,
                    _MODAL_CONNECT_TIMEOUT,
                    _MODAL_READ_TIMEOUT,
                    _MODAL_MAX_RETRIES,
                    on_retry=_on_retry,
                    on_reset_session=lambda: None,
                )
            except ModalRequestError as merr:
                raise Exception(f"Batch {b_idx + 1} fallo: {merr}. {merr.body}") from merr

            video_b64 = d.get("video_b64") or d.get("video_base64")
            if not isinstance(video_b64, str) or not video_b64.strip():
                raise Exception(
                    f"Respuesta invalida en batch {b_idx + 1}: falta video_b64 valido. "
                    f"Claves: {list(d.keys())[:20]}"
                )

            part = os.path.join(tmp_dir, f"part_{b_idx:04d}.mp4")
            with open(part, "wb") as f:
                f.write(base64.b64decode(video_b64))
            try:
                real = ffmpeg_utils.ffprobe_duration(part)
            except Exception:
                real = 0.0
            esperado = batch_dur_esperada[b_idx]
            log(
                f"  Batch {b_idx + 1}: esperado={esperado:.3f}s real={real:.3f}s delta={real - esperado:+.3f}s"
            )
            part_files.append(part)

        log("Descargando video final...", 90)
        video_concat = os.path.join(job_dir, "video_concat.mp4")
        video_final = os.path.join(job_dir, "video_final.mp4")

        if len(part_files) == 1:
            ffmpeg_utils.run_cmd(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    part_files[0],
                    "-vf",
                    "setpts=PTS-STARTPTS",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "24",
                    "-an",
                    "-movflags",
                    "+faststart",
                    video_concat,
                ],
                "No se pudo normalizar el video",
            )
        else:
            n_parts = len(part_files)
            inputs = []
            for p in part_files:
                inputs += ["-i", p]
            filter_parts = "".join(f"[{i}:v]setpts=PTS-STARTPTS[v{i}];" for i in range(n_parts))
            concat_inputs = "".join(f"[v{i}]" for i in range(n_parts))
            filter_str = f"{filter_parts}{concat_inputs}concat=n={n_parts}:v=1:a=0[vout]"
            ffmpeg_utils.run_cmd(
                ["ffmpeg", "-y"]
                + inputs
                + [
                    "-filter_complex",
                    filter_str,
                    "-map",
                    "[vout]",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "24",
                    "-an",
                    "-movflags",
                    "+faststart",
                    video_concat,
                ],
                "No se pudo unir los batches",
            )

        # Mezcla de audio alineada a duracion_total (sin -shortest: no recorta el final)
        ffmpeg_utils.final_mux_aligned(video_concat, audio_path, video_final, duracion_total, log=log)

        size_mb = os.path.getsize(video_final) / (1024 * 1024)
        log(f"Video listo - {size_mb:.1f} MB", 100)
        job_registry.update_job(
            job_id,
            estado="completado",
            video_url=f"/api/descargar/{job_id}",
            video_path=video_final,
            size_mb=round(size_mb, 1),
            duracion=round(duracion_total, 1),
            escenas=len(escenas),
        )
        open_folder(video_final)
        shutil.rmtree(tmp_dir, ignore_errors=True)

    except Exception as exc:
        logger.exception("[%s] generar_video fallo", job_id)
        err_msg = str(exc)
        log(f"Error: {err_msg}")
        log(f"Carpeta temporal conservada para diagnostico: {tmp_dir}")
        job_registry.update_job(job_id, estado="error", error=err_msg, tmp_dir=tmp_dir)
