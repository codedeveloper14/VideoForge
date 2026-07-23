import base64
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from src.domain.services import scene_timestamp_service
from src.infrastructure.ai_providers import image_search_client, whisper_client
from src.infrastructure.jobs import job_registry
from src.infrastructure.media import ffmpeg_utils
from src.infrastructure.storage import project_repository
from src.utils.logger import get_logger
from src.utils.platform_utils import no_window_kwargs, open_folder

logger = get_logger(__name__)

_REF_TIPOS = {
    "broll",
    "split_screen",
    "ref_persona",
    "ref_lugar",
    "ref_doble",
    "nombre_persona",
    "texto_lateral",
    "google_fullscreen",
}
_SYNC_TIPOS = {"lower_third", "texto_enfasis", "ref_lugar", "ref_persona", "google_fullscreen", "broll"}
_YA_APLICO_OVERLAY = {
    "nombre_persona",
    "texto_lateral",
    "ref_doble",
    "titulo_capitulo",
    "quote_animado",
    "lower_third",
}
_MAX_LOG = 800
_FONT_BOLD_CANDIDATES = [
    "/Windows/Fonts/Impact.ttf",
    "/Windows/Fonts/ariblk.ttf",
    "/Windows/Fonts/arialbd.ttf",
    "/Windows/Fonts/calibrib.ttf",
    "/Windows/Fonts/verdanab.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_FONT_REGULAR_CANDIDATES = [
    "/Windows/Fonts/arialbd.ttf",
    "/Windows/Fonts/arial.ttf",
    "/Windows/Fonts/calibri.ttf",
    "/Windows/Fonts/verdana.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def get_job(job_id: str) -> dict | None:
    return job_registry.get_job(job_id)


def get_job_video_path(job_id: str) -> str | None:
    job = job_registry.get_job(job_id)
    if not job:
        return None
    path = job.get("video_path")
    return path if path and os.path.exists(path) else None


def _save_ref(b64_or_url: str, dest_path: Path) -> bool:
    """Guarda una imagen de referencia base64 O descarga una URL a disco. Rechaza
    SVG y valida magic bytes (JPEG/PNG/WEBP) para no romper el pipeline de FFmpeg."""
    if not b64_or_url:
        return False
    try:
        if b64_or_url.startswith("http://") or b64_or_url.startswith("https://"):
            r = requests.get(b64_or_url, timeout=12, stream=True, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            ct = r.headers.get("content-type", "").split(";")[0].strip().lower()
            if "svg" in ct or "xml" in ct or "html" in ct or "text" in ct:
                return False
            data = r.content
            if len(data) < 500:
                return False
            ext_map = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
            real_dest = dest_path.with_suffix(ext_map.get(ct, ".jpg"))
            real_dest.write_bytes(data)
            if real_dest != dest_path:
                shutil.copy2(real_dest, dest_path)
            return True

        header = ""
        if "," in b64_or_url:
            header, b64data = b64_or_url.split(",", 1)
        else:
            b64data = b64_or_url
        if "svg" in header.lower():
            return False
        decoded = base64.b64decode(b64data)
        if len(decoded) < 12:
            return False
        magic = decoded[:4]
        if not (magic[:2] == b"\xff\xd8" or magic == b"\x89PNG" or magic == b"RIFF"):
            return False
        dest_path.write_bytes(decoded)
        return dest_path.exists() and dest_path.stat().st_size > 500
    except Exception as exc:
        logger.info("enriched_render: ref error: %s", exc)
        return False


def _resolve_ref_images(escenas: list[dict], tmp_ref_dir: Path, pexels_key: str, unsplash_key: str) -> dict:
    """Resuelve (en paralelo, 4 threads) la imagen de referencia de cada escena que la
    necesita: usa la que trajo el frontend (base64/URL) o busca por google_query."""
    ref_images: dict = {}

    def _resolve_one(esc):
        idx = esc.get("indice", -1)
        tipo = esc.get("tipo", "normal")
        results = []
        if idx < 0:
            return results

        b64 = esc.get("ref_image_b64") or esc.get("ref_image_url")
        if b64:
            rp = tmp_ref_dir / f"ref_{idx}.jpg"
            if _save_ref(b64, rp):
                results.append((idx, str(rp)))
        elif tipo in _REF_TIPOS and esc.get("google_query"):
            data = image_search_client.fetch_image_bytes(
                esc["google_query"], n=6, pexels_key=pexels_key, unsplash_key=unsplash_key
            )
            if data:
                rp = tmp_ref_dir / f"ref_{idx}.jpg"
                rp.write_bytes(data)
                results.append((idx, str(rp)))

        b64_2 = esc.get("ref_image_b64_2") or esc.get("ref_image_url_2")
        if b64_2:
            rp2 = tmp_ref_dir / f"ref_{idx}_2.jpg"
            if _save_ref(b64_2, rp2):
                results.append((f"{idx}_2", str(rp2)))
        elif tipo == "ref_doble" and esc.get("google_query_2"):
            data2 = image_search_client.fetch_image_bytes(
                esc["google_query_2"], n=6, pexels_key=pexels_key, unsplash_key=unsplash_key
            )
            if data2:
                rp2 = tmp_ref_dir / f"ref_{idx}_2.jpg"
                rp2.write_bytes(data2)
                results.append((f"{idx}_2", str(rp2)))
        return results

    esc_with_refs = [
        e
        for e in escenas
        if e.get("ref_image_b64")
        or e.get("ref_image_url")
        or (e.get("tipo", "normal") in _REF_TIPOS and e.get("google_query"))
    ]
    if esc_with_refs:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_resolve_one, e): e for e in esc_with_refs}
            for fut in as_completed(futures):
                try:
                    for key, path in fut.result() or []:
                        ref_images[key] = path
                except Exception as exc:
                    logger.info("enriched_render: ref thread error: %s", exc)
    return ref_images


def start_render(
    *,
    project_name: str,
    escenas: list[dict],
    resolucion: str = "1920x1080",
    transicion: str = "xfade",
    trans_dur: float = 0.6,
    pexels_key: str = "",
    unsplash_key: str = "",
) -> dict:
    """Lanza el render con efectos del editor (Ken Burns, overlays de texto, refs,
    split-screen) en un hilo de fondo. Lanza ValueError en validaciones (--> 400)."""
    project_name = (project_name or "").strip()
    if not project_name:
        raise ValueError("Falta project_name")

    proj_dir = project_repository.project_dir(project_name)
    audio_dir = proj_dir / "audio"
    out_dir = proj_dir / "video_final"
    out_dir.mkdir(parents=True, exist_ok=True)

    audios = (
        sorted(audio_dir.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True)
        if audio_dir.exists()
        else []
    )
    audio_path = str(audios[0]) if audios else None
    if not audio_path:
        raise ValueError("No hay audio en el proyecto")

    tmp_ref_dir = Path(tempfile.mkdtemp())
    ref_images = _resolve_ref_images(escenas, tmp_ref_dir, pexels_key, unsplash_key)
    logger.info("enriched_render: %d/%d refs resueltas", len(ref_images), len(escenas))

    job_id = str(uuid.uuid4())[:8]
    job_registry.create_job(
        job_id,
        {
            "id": job_id,
            "estado": "procesando",
            "progreso": 0,
            "mensaje": "Iniciando render enriquecido...",
            "logs": [],
            "video_url": None,
            "inicio": time.time(),
        },
    )

    threading.Thread(
        target=_procesar_render_enriquecido,
        args=(
            job_id,
            project_name,
            escenas,
            ref_images,
            audio_path,
            resolucion,
            transicion,
            trans_dur,
            str(out_dir),
            str(tmp_ref_dir),
            pexels_key,
            unsplash_key,
        ),
        daemon=True,
    ).start()

    return {"job_id": job_id}


def _find_font(candidates: list[str]) -> str:
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


def _procesar_render_enriquecido(
    job_id,
    proj_name,
    escenas,
    ref_images,
    audio_path,
    resolucion,
    transicion,
    trans_dur,
    out_dir,
    tmp_ref_dir,
    pexels_key,
    unsplash_key,
):
    """Worker con timestamps reales (WhisperX), Ken Burns dinamico, texto cinematografico
    y efectos split/broll. Un pipeline de FFmpeg independiente del Render normal (no usa
    Modal): cada tipo de escena clasificado por analizar_escenas tiene su propia rama de
    renderizado."""

    def log(msg, pct=None):
        job = job_registry.get_job(job_id)
        logs = job["logs"]
        logs.append(msg)
        if len(logs) > _MAX_LOG:
            del logs[: len(logs) - _MAX_LOG]
        job["mensaje"] = msg
        if pct is not None:
            job["progreso"] = pct
        logger.info("[editor:%s] %s", job_id, msg)

    def run(cmd, ctx, timeout=180):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **no_window_kwargs())
        except subprocess.TimeoutExpired:
            raise Exception(f"{ctx}: timeout {timeout}s")
        if res.returncode != 0:
            lines = (res.stderr or "").splitlines()
            raise Exception(f"{ctx}:\n" + "\n".join(lines[-12:]))
        return res

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        w_res, h_res = (int(x) for x in resolucion.split("x"))
        proj_dir = project_repository.project_dir(proj_name)
        img_dir = proj_dir / "imagen"
        out_dir_p = Path(out_dir)
        out_dir_p.mkdir(parents=True, exist_ok=True)

        # ── 1. Duracion total del audio ──────────────────────────────
        log("Analizando audio...", 3)
        dur_audio = ffmpeg_utils.ffprobe_duration(audio_path)
        if dur_audio <= 0:
            raise Exception("No se pudo leer la duracion del audio")
        log(f"Audio: {dur_audio:.1f}s", 5)

        # ── 2. Transcripcion --> timestamps reales ───────────────────
        log("Transcribiendo con WhisperX Replicate (word-level)...", 6)
        # Leer guion del proyecto -- IDENTICO a render normal (linea = escena). Los
        # textos del JSON del editor son parrafos largos que no coinciden bien con
        # los segmentos de WhisperX; las lineas del guion si coinciden.
        escenas_hab = [e for e in escenas if e.get("habilitado", True)]
        guion_lines = project_repository.read_guion_lines(proj_name)
        if guion_lines:
            log(f"Guion leido: {len(guion_lines)} lineas", 8)
            escenas_texto = guion_lines
        else:
            escenas_texto = [e.get("texto", "") for e in escenas_hab]
            log("[WARNING] guion no encontrado - usando textos del editor", 9)

        all_words: list[dict] = []
        timestamps = None

        def _on_fallback(unmatched, total, last_ok, dur):
            log(
                f"[WARNING] Word-level anomalo ({unmatched}/{total} sin match) "
                f"--> segment-level fallback",
                10,
            )

        try:
            segmentos, all_words = whisper_client.transcribe_whisperx_replicate(audio_path, language=None)
            if all_words or segmentos:
                timestamps = scene_timestamp_service.assign_timestamps_auto(
                    escenas_texto, segmentos, all_words, dur_audio, on_fallback=_on_fallback
                )
                log(f"{len(timestamps)} timestamps ({'word-level' if all_words else 'segment-level'})", 12)
        except Exception as exc:
            all_words = []
            log(f"[WARNING] WhisperX: {exc} - proporcional", 10)

        if not timestamps:
            timestamps = scene_timestamp_service.proporcional(escenas_texto, dur_audio)
            log(f"{len(timestamps)} timestamps proporcionales", 12)

        # Garantizar N timestamps = N escenas del guion (no imagenes totales en la
        # carpeta); usar siempre len(escenas_texto) para no generar timestamps huerfanos.
        n_guion = len(escenas_texto)
        while len(timestamps) < n_guion:
            pf = timestamps[-1]["fin"] if timestamps else 0.0
            dd = max(0.5, (dur_audio - pf) / max(1, n_guion - len(timestamps)))
            timestamps.append({"inicio": pf, "fin": pf + dd, "duracion": dd})

        # Sanity check: t_fin[i] = max(t_fin[i], t_inicio[i+1]) -- normalmente ya es
        # asi (asignar_timestamps_words lo hace en su segunda pasada), no-op salvo
        # cuando hubo interpolacion.
        for ti in range(len(timestamps) - 1):
            if timestamps[ti]["fin"] < timestamps[ti + 1]["inicio"]:
                timestamps[ti]["fin"] = timestamps[ti + 1]["inicio"]
                timestamps[ti]["duracion"] = round(timestamps[ti]["fin"] - timestamps[ti]["inicio"], 3)

        # Mapa indice_absoluto --> timestamp (solo las primeras N escenas habilitadas,
        # N = len(escenas_texto)). Escenas extra que excedan el guion no se incluyen.
        ts_map = {}
        ai = 0
        for ei, e in enumerate(escenas):
            if e.get("habilitado", True):
                if ai >= len(timestamps):
                    break
                ts_map[ei] = timestamps[ai]
                ai += 1

        # Detectar timestamps con duracion minima (0.30s): WhisperX no pudo alinear
        # algunas lineas del guion (silencio, musica de fondo, lineas finales sin
        # palabras detectables). Redistribuir el tiempo restante proporcional al
        # largo del texto de cada escena huerfana.
        min_valid_dur = 1.0
        last_real_idx, last_real_fin = -1, 0.0
        for ei in sorted(ts_map.keys()):
            if ts_map[ei]["duracion"] >= min_valid_dur:
                last_real_idx, last_real_fin = ei, ts_map[ei]["fin"]

        if last_real_idx >= 0 and last_real_fin < dur_audio - 1.0:
            tiempo_restante = dur_audio - last_real_fin
            huerfanas = [
                ei
                for ei in sorted(ts_map.keys())
                if ei > last_real_idx and ts_map[ei]["duracion"] < min_valid_dur
            ]
            if huerfanas and tiempo_restante > len(huerfanas) * 0.5:
                textos_h = [len(str(escenas[ei].get("texto", "") or "").strip()) or 1 for ei in huerfanas]
                total_chars = sum(textos_h)
                log(f"Redistribuyendo {tiempo_restante:.1f}s entre {len(huerfanas)} escenas sin timestamp")
                t_cursor = last_real_fin
                for k, ei in enumerate(huerfanas):
                    frac = textos_h[k] / total_chars
                    new_dur = round(max(1.0, tiempo_restante * frac), 3)
                    t_cursor = round(t_cursor, 3)
                    ts_map[ei] = {
                        "inicio": t_cursor,
                        "fin": round(t_cursor + new_dur, 3),
                        "duracion": new_dur,
                    }
                    t_cursor += new_dur

        log(f"{len(timestamps)} timestamps:")
        for i, ts in enumerate(timestamps):
            log(f"  E{i + 1:02d}: {ts['inicio']:.2f}s --> {ts['fin']:.2f}s  ({ts['duracion']:.2f}s)")

        # ── 3. Fuentes disponibles ────────────────────────────────────
        font_bold = _find_font(_FONT_BOLD_CANDIDATES)
        font_reg = _find_font(_FONT_REGULAR_CANDIDATES) or font_bold

        # ── helpers de texto ────────────────────────────────────────
        def _ct(s, mx=None):
            """Limpia texto para drawtext. mx limita caracteres totales."""
            o = "".join(c for c in (s or "") if ord(c) < 256)
            o = (
                o.replace("\\", "")
                .replace("'", "")
                .replace('"', "")
                .replace("[", "")
                .replace("]", "")
                .replace("%", "pct")
                .strip()
            )
            o = " ".join(o.split()).replace(":", "\\:")
            return o[:mx] if mx else o

        def _ct_short(s, max_words=5, max_chars=35):
            o = _ct(s)
            if not o:
                return ""
            words = o.split()
            if len(words) > max_words:
                o = " ".join(words[:max_words])
            if len(o) > max_chars:
                o = o[:max_chars].rsplit(" ", 1)[0] if " " in o[:max_chars] else o[:max_chars]
            return o.strip()

        def _wr(txt, mc):
            """Word-wrap a max mc chars/linea, max 2 lineas."""
            words = txt.split()
            out, cur = [], ""
            for w in words:
                if cur and len(cur) + 1 + len(w) > mc:
                    out.append(cur)
                    cur = w
                else:
                    cur = (cur + " " + w).strip()
            if cur:
                out.append(cur)
            return out[:2]

        def _sf(lines):
            return "\\n".join(lines)

        def _kb(wr, hr, dur, v):
            """Ken Burns clamped sin temblor. Siempre hay movimiento visible (min 1.0s)."""
            sc = 1.12
            su = int(wr * sc)
            su += su % 2
            sh = int(hr * sc)
            sh += sh % 2
            dx, dy = su - wr, sh - hr
            dd = f"{max(dur, 1.0):.4f}"
            t = f"min(max(t/{dd},0),1)"
            variants = [
                f"scale={su}:{sh}:force_original_aspect_ratio=increase,crop={wr}:{hr}:x='({dx})*(1-{t})':y='({dy})*(1-{t})',setsar=1,fps=24,setpts=PTS-STARTPTS",
                f"scale={su}:{sh}:force_original_aspect_ratio=increase,crop={wr}:{hr}:x='({dx})*{t}':y='({dy})*{t}',setsar=1,fps=24,setpts=PTS-STARTPTS",
                f"scale={su}:{sh}:force_original_aspect_ratio=increase,crop={wr}:{hr}:x='({dx})*{t}':y='({dy})/2',setsar=1,fps=24,setpts=PTS-STARTPTS",
                f"scale={su}:{sh}:force_original_aspect_ratio=increase,crop={wr}:{hr}:x='({dx})*(1-{t})':y='({dy})/2',setsar=1,fps=24,setpts=PTS-STARTPTS",
            ]
            return variants[v % 4]

        def _bsb(wr, hr, col="black"):
            return (
                f"scale={wr}:{hr}:force_original_aspect_ratio=decrease,"
                f"pad={wr}:{hr}:(ow-iw)/2:(oh-ih)/2:color={col},"
                f"setsar=1,fps=24,setpts=PTS-STARTPTS"
            )

        def _fallback_caption_vf(base_vf, wr, hr, otxt, fontfile):
            """Reaplica el texto de la escena sobre el filtro de respaldo (fondo solido)
            cuando el render "completo" de la escena (Ken Burns + overlays especificos
            del tipo) fallo -- sin esto, el fallback quedaba SIN caption: el video seguia
            armandose bien, pero esa escena aparecia muda de texto, con solo una linea
            de log para explicarlo (facil de pasar por alto entre cientos de lineas)."""
            fp = (fontfile or "").replace("\\", "/")
            if not otxt or not fp:
                return base_vf
            fs = int(wr / 22)
            text = _sf(_wr(otxt, 28))
            y = f"h-text_h-{int(hr * 0.08)}"
            return (
                base_vf + ","
                f"drawtext=fontfile='{fp}':text='{text}':"
                f"fontcolor=black@0.6:fontsize={fs}:line_spacing={int(fs * 0.2)}:"
                f"x=(w-text_w)/2+3:y={y}+3,"
                f"drawtext=fontfile='{fp}':text='{text}':"
                f"fontcolor=white@1.0:fontsize={fs}:line_spacing={int(fs * 0.2)}:"
                f"x=(w-text_w)/2:y={y}"
            )

        def _enc(so, vf, dur, src, preset="ultrafast", crf=23, fc=None, mv="[v]", tout=120):
            cmd = [ffmpeg_utils.ffmpeg_exe(), "-y"]
            if isinstance(src, str):
                cmd += ["-loop", "1", "-t", str(dur), "-i", src]
            else:
                cmd += src
            if fc:
                cmd += ["-filter_complex", fc, "-map", mv]
            elif vf:
                cmd += ["-vf", vf]
            cmd += [
                "-c:v",
                "libx264",
                "-preset",
                preset,
                "-crf",
                str(crf),
                "-pix_fmt",
                "yuv420p",
                "-r",
                "24",
                "-an",
                so,
            ]
            return run(cmd, f"enc {os.path.basename(so)}", timeout=tout)

        def _add_txt(si, so, dt, tout=90):
            run(
                [
                    ffmpeg_utils.ffmpeg_exe(),
                    "-y",
                    "-i",
                    si,
                    "-vf",
                    dt,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "22",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "24",
                    "-an",
                    so,
                ],
                f"txt {os.path.basename(so)}",
                timeout=tout,
            )

        def _make_lavfi_vid(path, color, wr, hr, dur, tout=30):
            run(
                [
                    ffmpeg_utils.ffmpeg_exe(),
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c={color}:size={wr}x{hr}:rate=24:duration={dur}",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "26",
                    "-pix_fmt",
                    "yuv420p",
                    "-an",
                    path,
                ],
                f"lavfi {color}",
                timeout=tout,
            )

        def _apply_timed_overlay(seg_out, vf_str, t_start, t_end, dur_clip, tag, tout=90):
            """Aplica vf_str sobre seg_out SOLO en [t_start, t_end] via trim+concat, para
            que el overlay no aparezca antes del momento exacto. Modifica seg_out in-place."""
            tmp = str(tmp_dir / f"{tag}_ov.mp4")
            if t_start >= dur_clip - 0.05:
                t_start, t_end = 0.0, dur_clip

            if t_start <= 0.05:
                _add_txt(seg_out, tmp, vf_str, tout=tout)
                if os.path.exists(tmp):
                    os.replace(tmp, seg_out)
                    return True
                return False

            sa = str(tmp_dir / f"{tag}_A.mp4")
            ebs = str(tmp_dir / f"{tag}_Bs.mp4")
            sb = str(tmp_dir / f"{tag}_B.mp4")
            sc = str(tmp_dir / f"{tag}_C.mp4")
            lf = str(tmp_dir / f"{tag}_list.txt")
            parts = []

            run(
                [
                    ffmpeg_utils.ffmpeg_exe(),
                    "-y",
                    "-i",
                    seg_out,
                    "-ss",
                    "0",
                    "-t",
                    f"{t_start:.3f}",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "22",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "24",
                    "-an",
                    sa,
                ],
                f"{tag}-A",
                timeout=60,
            )
            if os.path.exists(sa):
                parts.append(sa)

            dur_b = max(0.1, t_end - t_start)
            run(
                [
                    ffmpeg_utils.ffmpeg_exe(),
                    "-y",
                    "-i",
                    seg_out,
                    "-ss",
                    f"{t_start:.3f}",
                    "-t",
                    f"{dur_b:.3f}",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "22",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "24",
                    "-an",
                    ebs,
                ],
                f"{tag}-Bsrc",
                timeout=60,
            )
            if os.path.exists(ebs):
                _add_txt(ebs, sb, vf_str, tout=tout)
                parts.append(sb if os.path.exists(sb) else ebs)

            dur_c = dur_clip - t_end
            if dur_c > 0.15:
                run(
                    [
                        ffmpeg_utils.ffmpeg_exe(),
                        "-y",
                        "-i",
                        seg_out,
                        "-ss",
                        f"{t_end:.3f}",
                        "-t",
                        f"{dur_c:.3f}",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "fast",
                        "-crf",
                        "22",
                        "-pix_fmt",
                        "yuv420p",
                        "-r",
                        "24",
                        "-an",
                        sc,
                    ],
                    f"{tag}-C",
                    timeout=60,
                )
                if os.path.exists(sc):
                    parts.append(sc)

            if len(parts) >= 2:
                with open(lf, "w") as lfh:
                    for p in parts:
                        lfh.write(f"file '{p}'\n")
                run(
                    [
                        ffmpeg_utils.ffmpeg_exe(),
                        "-y",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        lf,
                        "-c:v",
                        "libx264",
                        "-preset",
                        "fast",
                        "-crf",
                        "22",
                        "-pix_fmt",
                        "yuv420p",
                        "-r",
                        "24",
                        "-an",
                        tmp,
                    ],
                    f"{tag}-concat",
                    timeout=tout,
                )
                if os.path.exists(tmp):
                    os.replace(tmp, seg_out)
                    return True
            elif len(parts) == 1:
                shutil.copy2(parts[0], seg_out)
                return True
            return False

        def _norm_word(s):
            s = s.lower().strip()
            s = unicodedata.normalize("NFD", s)
            s = "".join(c for c in s if unicodedata.category(c) != "Mn")
            return "".join(c for c in s if c.isalnum() or c in ".,%-")

        def _find_word_offset(keywords, t_scene_start, t_scene_end, show_dur=None):
            """Busca keywords en all_words dentro de [t_scene_start, t_scene_end].
            Retorna (offset_start, offset_end) relativo al inicio de la escena, o None."""
            if not all_words or not keywords:
                return None
            kws_norm = [_norm_word(k) for k in keywords if k and len(k.strip()) >= 2]
            if not kws_norm:
                return None
            scene_words = [
                w for w in all_words if t_scene_start - 0.05 <= float(w.get("start", 0)) <= t_scene_end + 0.05
            ]
            if not scene_words:
                return None

            best_start = None
            for w in scene_words:
                wn = _norm_word(w.get("word", ""))
                for kw in kws_norm:
                    if wn == kw or wn.startswith(kw) or kw in wn:
                        ws = float(w.get("start", t_scene_start))
                        if best_start is None or ws < best_start:
                            best_start = ws
                        break
            if best_start is None:
                return None

            rel_start = max(0.0, round(best_start - t_scene_start, 3))
            clip_dur = t_scene_end - t_scene_start
            if show_dur is None:
                show_dur = max(1.5, clip_dur - rel_start)
            rel_end = min(clip_dur, rel_start + show_dur)
            return (rel_start, rel_end)

        _WORD_WINDOW_GENERIC = {
            "actualidad",
            "siglo",
            "epoca",
            "periodo",
            "vista",
            "foto",
            "imagen",
            "norte",
            "sur",
            "este",
            "oeste",
            "circa",
            "aprox",
        }
        _WORD_WINDOW_STOP = {
            "para",
            "este",
            "esta",
            "como",
            "pero",
            "cada",
            "solo",
            "todo",
            "que",
            "con",
            "sin",
            "por",
            "entre",
            "sobre",
            "desde",
            "hasta",
            "hay",
            "fue",
            "era",
            "son",
            "sus",
            "muy",
            "bien",
            "nada",
            "algo",
            "cuando",
            "donde",
            "aunque",
            "siempre",
            "nunca",
            "año",
            "años",
            "vez",
            "veces",
            "parte",
            "lugar",
            "tiempo",
            "vida",
            "de",
            "la",
            "el",
            "en",
            "al",
            "se",
            "su",
            "un",
            "es",
            "no",
            "lo",
            "una",
            "les",
            "han",
            "sido",
            "bajo",
            "toldos",
            "nocturno",
            "convoy",
            "pantalla",
            "imagen",
        }

        def _word_window(overlay_text, scene_texto, t_start_abs, t_end_abs, dur_clip, search_last=False):
            """Retorna (t_rel_start, t_rel_end) para mostrar el overlay en el momento exacto
            en que se pronuncia el contenido. search_last=True busca la ULTIMA keyword
            (para ref_lugar/persona, donde el lugar suele mencionarse al final)."""
            if not all_words:
                return (0.0, dur_clip)

            kws_ov = [
                p.strip().lower() for p in re.split(r"[,\s%\.]+", overlay_text or "") if len(p.strip()) >= 2
            ]
            kws_ov = [k for k in kws_ov if k not in _WORD_WINDOW_GENERIC]

            kws_txt = [
                w.lower()
                for w in re.findall(r"[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]{4,}", scene_texto or "")
                if w.lower() not in _WORD_WINDOW_STOP
            ]
            all_kws = kws_ov + [k for k in kws_txt if k not in kws_ov]
            if not all_kws:
                return (0.0, dur_clip)

            kws_norm = [_norm_word(k) for k in all_kws if k]
            scene_words = [
                w for w in all_words if t_start_abs - 0.05 <= float(w.get("start", 0)) <= t_end_abs + 0.05
            ]
            if not scene_words:
                return (0.0, dur_clip)

            matches = []
            for w in scene_words:
                wn = _norm_word(w.get("word", ""))
                for kw in kws_norm:
                    if len(kw) >= 3 and (wn == kw or wn.startswith(kw) or kw in wn):
                        ws = float(w.get("start", t_start_abs))
                        we = float(w.get("end", ws + 0.4))
                        matches.append((ws, we))
                        break
            if not matches:
                return (0.0, dur_clip)

            best_start, best_end = matches[-1] if search_last else matches[0]
            rel_start = max(0.0, round(best_start - t_start_abs, 3))
            clip_dur = t_end_abs - t_start_abs
            if rel_start >= dur_clip - 0.05:
                return (0.0, dur_clip)
            show_dur = max(1.5, clip_dur - rel_start)
            rel_end = min(clip_dur, rel_start + show_dur)
            return (rel_start, rel_end)

        # ── 4. Procesar escenas ───────────────────────────────────────
        log(f"Procesando {len(escenas)} escenas...", 14)
        seg_paths = []

        for i, esc in enumerate(escenas):
            if not esc.get("habilitado", True):
                continue

            idx = esc.get("indice", i)
            tipo = esc.get("tipo", "normal")
            ofile = esc.get("imagen_file", "")
            otxt_raw = esc.get("texto_overlay") or ""
            otxt = (
                _ct(otxt_raw, 150)
                if tipo == "quote_animado"
                else _ct_short(otxt_raw, max_words=5, max_chars=35)
            )
            opos = esc.get("texto_overlay_pos") or "bottom_center"
            tsec = _ct(esc.get("texto_secundario") or "", 55)
            cacc = (esc.get("color_accent") or "ffffff").lstrip("#")
            sl1 = _ct(esc.get("split_label_1") or "", 22)
            sl2 = _ct(esc.get("split_label_2") or "", 22)
            rp = ref_images.get(idx)
            rp2 = ref_images.get(f"{idx}_2")
            rlbl = _ct(esc.get("ref_label") or "", 60)
            ncap = esc.get("numero_capitulo")

            ts = ts_map.get(i, {"inicio": 0, "fin": dur_audio, "duracion": dur_audio / max(1, len(escenas))})
            dur_clip = max(0.5, round(float(ts["duracion"]), 3))
            t_scene_start = float(ts.get("inicio", 0))
            t_scene_end = float(ts.get("fin", t_scene_start + dur_clip))
            seg_out = str(tmp_dir / f"seg_{i:04d}.mp4")
            ref_show_from = 0.0

            img_path = None
            if ofile and (img_dir / ofile).exists():
                img_path = str(img_dir / ofile)
            else:
                imgs = (
                    sorted(img_dir.glob("*.png"))
                    + sorted(img_dir.glob("*.jpg"))
                    + sorted(img_dir.glob("*.webp"))
                )
                if imgs:
                    img_path = str(imgs[min(idx, len(imgs) - 1)])

            # Autocompletar con imagen buscada si no hay imagen local
            if not img_path:
                texto_esc = str(esc.get("texto") or otxt or "").strip()
                if texto_esc:
                    q_auto = " ".join(texto_esc.split()[:7])
                    log(f"  E{i + 1}: sin imagen local --> buscando '{q_auto[:45]}...'")
                    try:
                        img_data = image_search_client.fetch_image_bytes(
                            q_auto, n=4, pexels_key=pexels_key, unsplash_key=unsplash_key
                        )
                        if img_data:
                            auto_img = tmp_dir / f"auto_{i:04d}.jpg"
                            auto_img.write_bytes(img_data)
                            img_path = str(auto_img)
                            log(f"  E{i + 1}: imagen autocomplete OK")
                    except Exception as exc:
                        log(f"  [WARNING] E{i + 1}: autocomplete fallo ({exc})")

            # Fallback dinamico: fondo negro cuando tampoco hay imagen buscada
            if not img_path:
                bg_img = str(tmp_dir / f"bg_{i:04d}.png")
                try:
                    run(
                        [
                            ffmpeg_utils.ffmpeg_exe(),
                            "-y",
                            "-f",
                            "lavfi",
                            "-i",
                            f"color=c=black:size={w_res}x{h_res}:rate=1",
                            "-frames:v",
                            "1",
                            bg_img,
                        ],
                        f"bg_dyn_{i}",
                        timeout=15,
                    )
                    if os.path.exists(bg_img) and os.path.getsize(bg_img) > 100:
                        img_path = bg_img
                        log(f"  E{i + 1}: escena dinamica (fondo negro, sin imagen)")
                except Exception:
                    pass

            if not img_path:
                log(f"  [WARNING] Escena {i + 1}: sin imagen - omitida")
                continue

            pct = 14 + int((i / max(1, len(escenas))) * 68)
            log(f"  [{tipo}] Escena {i + 1}/{len(escenas)} ({dur_clip:.1f}s)...", pct)

            try:
                fp_b = (font_bold or "").replace("\\", "/")
                fp_r = (font_reg or "").replace("\\", "/")
                kb = _kb(w_res, h_res, dur_clip, i)

                # ══════════════ BASE RENDER (segun tipo de escena) ══════════════
                if tipo == "intro_dinamica":
                    su2 = int(w_res * 1.18)
                    su2 += su2 % 2
                    sh2 = int(h_res * 1.18)
                    sh2 += sh2 % 2
                    dx2, dy2 = su2 - w_res, sh2 - h_res
                    d2 = f"{dur_clip:.4f}"
                    vfi = (
                        f"scale={su2}:{sh2}:force_original_aspect_ratio=increase,"
                        f"crop={w_res}:{h_res}:"
                        f"x='({dx2})/2*(1-min(max(t/{d2},0),1))':"
                        f"y='({dy2})/2*(1-min(max(t/{d2},0),1))',"
                        f"setsar=1,fps=24,setpts=PTS-STARTPTS"
                    )
                    _enc(seg_out, vfi, dur_clip, img_path, crf=22)

                elif tipo == "titulo_capitulo":
                    tsd = min(0.50, dur_clip * 0.35)
                    _enc(
                        seg_out,
                        (
                            f"scale={w_res}:{h_res}:force_original_aspect_ratio=decrease,"
                            f"pad={w_res}:{h_res}:(ow-iw)/2:(oh-ih)/2:color=black,"
                            f"setsar=1,fps=24,"
                            f"fade=t=in:st=0:d={tsd:.3f},setpts=PTS-STARTPTS"
                        ),
                        dur_clip,
                        img_path,
                        crf=26,
                    )
                    if fp_b:
                        nt = _ct(f"Capitulo {ncap}" if ncap else "")
                        mt = otxt[:40] if otxt else ""
                        ln = _wr(mt, 28)
                        sm = _sf(ln)
                        fn, fm = int(w_res / 10), int(w_res / 18)
                        yn = int(h_res * 0.30)
                        ym = yn + fn + int(h_res * 0.04)
                        dt = (
                            f"colorchannelmixer=rr=0.15:gg=0.15:bb=0.15,"
                            f"drawtext=fontfile='{fp_b}':text='{nt}':"
                            f"fontcolor=0x{cacc}@0.9:fontsize={fn}:"
                            f"x=(w-text_w)/2:y={yn}:"
                            f"shadowcolor=black@0.8:shadowx=3:shadowy=3,"
                            f"drawtext=fontfile='{fp_b}':text='{sm}':"
                            f"fontcolor=white@0.95:fontsize={fm}:"
                            f"line_spacing={int(fm * 0.2)}:x=(w-text_w)/2:y={ym}:"
                            f"shadowcolor=black@0.9:shadowx=2:shadowy=2"
                        )
                        tmp_seg = str(tmp_dir / f"seg_{i:04d}_t.mp4")
                        _add_txt(seg_out, tmp_seg, dt)
                        if os.path.exists(tmp_seg):
                            os.replace(tmp_seg, seg_out)

                elif tipo == "nombre_persona":
                    # Mitad izq: foto ref (o IA) con slide-in; mitad der: panel blanco + nombre/cargo
                    hw = w_res // 2
                    isrc = rp if rp else img_path
                    wr_vid = str(tmp_dir / f"white_{i:04d}.mp4")
                    _make_lavfi_vid(wr_vid, "white", hw, h_res, dur_clip)
                    left_vid = str(tmp_dir / f"left_{i:04d}.mp4")
                    sd = min(0.40, dur_clip * 0.35)
                    slide_vf = (
                        f"scale={hw}:{h_res}:force_original_aspect_ratio=decrease,"
                        f"pad={hw}:{h_res}:(ow-iw)/2:(oh-ih)/2:color=black,"
                        f"setsar=1,fps=24,"
                        f"fade=t=in:st=0:d={sd:.3f},setpts=PTS-STARTPTS"
                    )
                    _enc(left_vid, slide_vf, dur_clip, isrc, crf=22, tout=60)
                    fc_n = (
                        "[0:v]setpts=PTS-STARTPTS[L];"
                        "[1:v]setpts=PTS-STARTPTS[R];"
                        "[L][R]hstack=inputs=2[v]"
                    )
                    _enc(
                        seg_out,
                        None,
                        dur_clip,
                        ["-i", left_vid, "-i", wr_vid],
                        fc=fc_n,
                        mv="[v]",
                        crf=22,
                        tout=60,
                    )
                    if fp_b and otxt:
                        nl = _wr(otxt[:35], 16)
                        sn = _sf(nl)
                        fn = int(w_res / 13)
                        xr = hw + int(hw * 0.08)
                        ym = int(h_res * 0.28)
                        dt_nom = (
                            f"drawtext=fontfile='{fp_b}':text='{sn}':"
                            f"fontcolor=black@0.92:fontsize={fn}:"
                            f"line_spacing={int(fn * 0.12)}:x={xr}:y={ym}:"
                            f"shadowcolor=white@0.3:shadowx=2:shadowy=2"
                        )
                        if tsec and fp_r:
                            fs2 = int(w_res / 26)
                            ys = ym + int(fn * len(nl) * 1.3) + int(h_res * 0.02)
                            dt_nom += (
                                f",drawtext=fontfile='{fp_r}':text='{tsec}':"
                                f"fontcolor=black@0.52:fontsize={fs2}:x={xr}:y={ys}"
                            )
                        ws_nom, we_nom = _word_window(
                            otxt, esc.get("texto", ""), t_scene_start, t_scene_end, dur_clip
                        )
                        _apply_timed_overlay(seg_out, dt_nom, ws_nom, we_nom, dur_clip, f"seg_{i:04d}_nom")

                elif tipo == "texto_lateral":
                    # Fondo blanco + imagen centrada al 58% con entrada desde abajo + titulo arriba
                    isrc = rp if rp else img_path
                    iw = int(w_res * 0.58)
                    iw += iw % 2
                    ih = int(h_res * 0.72)
                    ih += ih % 2
                    ix = (w_res - iw) // 2
                    iy = int(h_res * 0.16)
                    bg_vid = str(tmp_dir / f"bg_w_{i:04d}.mp4")
                    _make_lavfi_vid(bg_vid, "white", w_res, h_res, dur_clip)
                    sd = min(0.45, dur_clip * 0.35)
                    offset_y = int(h_res * 0.04)
                    d_s = f"{max(sd, 0.1):.4f}"
                    t_ease = f"min(max(t/{d_s},0),1)"
                    fc_t = (
                        f"[0:v]setpts=PTS-STARTPTS[bg];"
                        f"[1:v]scale={iw}:{ih}:force_original_aspect_ratio=decrease,"
                        f"pad={iw}:{ih}:(ow-iw)/2:(oh-ih)/2:color=white,"
                        f"setsar=1,fps=24,"
                        f"fade=t=in:st=0:d={sd:.3f}[fg];"
                        f"[bg][fg]overlay={ix}:y='{iy}+{offset_y}*(1-{t_ease})'[v]"
                    )
                    _enc(
                        seg_out,
                        None,
                        dur_clip,
                        ["-i", bg_vid, "-loop", "1", "-t", str(dur_clip), "-i", isrc],
                        fc=fc_t,
                        mv="[v]",
                        crf=24,
                        tout=90,
                    )
                    if fp_r and otxt:
                        fs_t = int(w_res / 10)
                        ln = _wr(otxt[:30], 20)
                        st = _sf(ln)
                        dt_lat = (
                            f"drawtext=fontfile='{fp_r}':text='{st}':"
                            f"fontcolor=black@0.88:fontsize={fs_t}:"
                            f"line_spacing={int(fs_t * 0.1)}:"
                            f"x=(w-text_w)/2:y={int(h_res * 0.02)}:"
                            f"shadowcolor=white@0.4:shadowx=1:shadowy=1"
                        )
                        ws_lat, we_lat = _word_window(
                            otxt, esc.get("texto", ""), t_scene_start, t_scene_end, dur_clip
                        )
                        _apply_timed_overlay(seg_out, dt_lat, ws_lat, we_lat, dur_clip, f"seg_{i:04d}_lt")

                elif tipo == "ref_doble":
                    # Fondo blanco + 2 imagenes entrando desde los costados + etiquetas
                    i1 = rp or img_path
                    i2 = rp2 or img_path
                    hw = w_res // 2
                    iw2 = int(hw * 0.72)
                    iw2 += iw2 % 2
                    ih2 = int(h_res * 0.68)
                    ih2 += ih2 % 2
                    x1 = int(hw * 0.14)
                    x2 = hw + int(hw * 0.14)
                    yim = int(h_res * 0.18)
                    bg_vid = str(tmp_dir / f"bg_w_{i:04d}.mp4")
                    _make_lavfi_vid(bg_vid, "white", w_res, h_res, dur_clip)
                    sd = min(0.45, dur_clip * 0.35)
                    d_s = f"{max(sd, 0.1):.4f}"
                    t_ease = f"min(max(t/{d_s},0),1)"
                    slide_px = int(w_res * 0.06)
                    fc_d = (
                        f"[0:v]setpts=PTS-STARTPTS[bg];"
                        f"[1:v]scale={iw2}:{ih2}:force_original_aspect_ratio=decrease,"
                        f"pad={iw2}:{ih2}:(ow-iw)/2:(oh-ih)/2:color=white,"
                        f"setsar=1,fps=24,"
                        f"fade=t=in:st=0:d={sd:.3f}[m1];"
                        f"[2:v]scale={iw2}:{ih2}:force_original_aspect_ratio=decrease,"
                        f"pad={iw2}:{ih2}:(ow-iw)/2:(oh-ih)/2:color=white,"
                        f"setsar=1,fps=24,"
                        f"fade=t=in:st=0:d={sd:.3f}[m2];"
                        f"[bg][m1]overlay=x='{x1}-{slide_px}*(1-{t_ease})':y={yim}[t1];"
                        f"[t1][m2]overlay=x='{x2}+{slide_px}*(1-{t_ease})':y={yim}[v]"
                    )
                    _enc(
                        seg_out,
                        None,
                        dur_clip,
                        [
                            "-i",
                            bg_vid,
                            "-loop",
                            "1",
                            "-t",
                            str(dur_clip),
                            "-i",
                            i1,
                            "-loop",
                            "1",
                            "-t",
                            str(dur_clip),
                            "-i",
                            i2,
                        ],
                        fc=fc_d,
                        mv="[v]",
                        crf=24,
                        tout=120,
                    )
                    if fp_b:
                        fs_l = int(w_res / 22)
                        yl = int(h_res * 0.06)
                        dt = ""
                        if sl1:
                            dt += (
                                f"drawtext=fontfile='{fp_b}':text='{sl1}':"
                                f"fontcolor=red@0.95:fontsize={fs_l}:x={x1}:y={yl}:"
                                f"shadowcolor=white@0.5:shadowx=1:shadowy=1,"
                            )
                        if sl2:
                            dt += (
                                f"drawtext=fontfile='{fp_b}':text='{sl2}':"
                                f"fontcolor=red@0.95:fontsize={fs_l}:x={x2}:y={yl}:"
                                f"shadowcolor=white@0.5:shadowx=1:shadowy=1,"
                            )
                        if dt:
                            tmp_seg = str(tmp_dir / f"seg_{i:04d}_t.mp4")
                            _add_txt(seg_out, tmp_seg, dt.rstrip(","))
                            if os.path.exists(tmp_seg):
                                os.replace(tmp_seg, seg_out)

                elif tipo in ("ref_persona", "ref_lugar", "google_fullscreen") and rp:
                    # La imagen de referencia aparece cuando se TERMINA de mencionar el
                    # nombre/lugar (search_last=True); antes de eso, KB de la imagen IA.
                    ref_ov_txt = esc.get("texto_overlay") or esc.get("ref_label") or ""
                    rw_s, rw_e = _word_window(
                        ref_ov_txt,
                        esc.get("texto", ""),
                        t_scene_start,
                        t_scene_end,
                        dur_clip,
                        search_last=True,
                    )
                    ref_show_from = rw_s
                    min_ref_dur = 2.0
                    if dur_clip - rw_s < min_ref_dur:
                        rw_s = max(0.0, dur_clip - min_ref_dur)
                        ref_show_from = rw_s

                    if rw_s <= 0.10:
                        _enc(seg_out, kb, dur_clip, rp, crf=23, tout=90)
                    else:
                        kb_part = str(tmp_dir / f"seg_{i:04d}_kb.mp4")
                        ref_part = str(tmp_dir / f"seg_{i:04d}_rp.mp4")
                        ref_list = str(tmp_dir / f"seg_{i:04d}_rl.txt")
                        _enc(kb_part, kb, rw_s, img_path, crf=23, tout=60)
                        dur_ref = dur_clip - rw_s
                        ref_fade_vf = (
                            f"scale={w_res}:{h_res}:force_original_aspect_ratio=decrease,"
                            f"pad={w_res}:{h_res}:(ow-iw)/2:(oh-ih)/2:color=black,"
                            f"setsar=1,fps=24,"
                            f"fade=t=in:st=0:d=0.25,setpts=PTS-STARTPTS"
                        )
                        _enc(ref_part, ref_fade_vf, dur_ref, rp, crf=23, tout=90)
                        if os.path.exists(kb_part) and os.path.exists(ref_part):
                            with open(ref_list, "w") as rlf:
                                rlf.write(f"file '{kb_part}'\n")
                                rlf.write(f"file '{ref_part}'\n")
                            run(
                                [
                                    ffmpeg_utils.ffmpeg_exe(),
                                    "-y",
                                    "-f",
                                    "concat",
                                    "-safe",
                                    "0",
                                    "-i",
                                    ref_list,
                                    "-c:v",
                                    "libx264",
                                    "-preset",
                                    "fast",
                                    "-crf",
                                    "22",
                                    "-pix_fmt",
                                    "yuv420p",
                                    "-r",
                                    "24",
                                    "-an",
                                    seg_out,
                                ],
                                "ref-concat",
                                timeout=120,
                            )
                        elif os.path.exists(ref_part):
                            shutil.copy2(ref_part, seg_out)
                        else:
                            _enc(seg_out, kb, dur_clip, rp, crf=23, tout=90)

                elif tipo == "quote_animado":
                    qsd = min(0.45, dur_clip * 0.35)
                    qbg = (
                        f"scale={w_res}:{h_res}:force_original_aspect_ratio=decrease,"
                        f"pad={w_res}:{h_res}:(ow-iw)/2:(oh-ih)/2:color=black,"
                        f"colorchannelmixer=rr=0.4:gg=0.4:bb=0.4,"
                        f"setsar=1,fps=24,"
                        f"fade=t=in:st=0:d={qsd:.3f},setpts=PTS-STARTPTS"
                    )
                    _enc(seg_out, qbg, dur_clip, img_path, crf=23)
                    if fp_r and otxt:
                        ql = _wr(otxt[:120], 38)
                        sq = _sf(ql)
                        fq = int(w_res / 22)
                        bh = int(fq * len(ql) * 1.5 + h_res * 0.12)
                        by = (h_res - bh) // 2
                        ax = int(w_res * 0.08)
                        pq = int(h_res * 0.025)
                        ay = by + int(h_res * 0.02)
                        ahl = bh - int(h_res * 0.04)
                        dt = (
                            f"drawbox=x=0:y={by}:w=iw:h={bh}:color=black@0.70:t=fill,"
                            f"drawbox=x={ax - 6}:y={ay}:w=5:h={ahl}:color=0x{cacc}@0.9:t=fill,"
                            f"drawtext=fontfile='{fp_r}':text='{sq}':"
                            f"fontcolor=white@0.95:fontsize={fq}:"
                            f"line_spacing={int(fq * 0.28)}:"
                            f"x={ax + int(w_res * 0.03)}:y={by + pq}:"
                            f"shadowcolor=black@0.8:shadowx=2:shadowy=2"
                        )
                        tmp_seg = str(tmp_dir / f"seg_{i:04d}_t.mp4")
                        _add_txt(seg_out, tmp_seg, dt)
                        if os.path.exists(tmp_seg):
                            os.replace(tmp_seg, seg_out)

                elif tipo == "lower_third":
                    _enc(seg_out, kb, dur_clip, img_path, crf=24)
                    if fp_b and otxt:
                        ll = _wr(otxt[:50], 30)
                        sl = _sf(ll)
                        fl = int(w_res / 34)
                        bh = int(fl * len(ll) * 1.6 + h_res * 0.04)
                        by = h_res - bh - int(h_res * 0.06)
                        bx = int(w_res * 0.05)
                        bw = int(w_res * 0.45)
                        pt = int(h_res * 0.012)
                        dt_l3 = (
                            f"drawbox=x={bx}:y={by}:w={bw}:h={bh}:color=black@0.78:t=fill,"
                            f"drawbox=x={bx}:y={by}:w={bw}:h=4:color=0x{cacc}@0.95:t=fill,"
                            f"drawtext=fontfile='{fp_b}':text='{sl}':"
                            f"fontcolor=white@0.97:fontsize={fl}:"
                            f"line_spacing={int(fl * 0.22)}:"
                            f"x={bx + int(w_res * 0.012)}:y={by + pt}:"
                            f"shadowcolor=black@0.9:shadowx=2:shadowy=2"
                        )
                        if tsec and fp_r:
                            fsu = int(fl * 0.78)
                            ysu = by + pt + int(fl * len(ll) * 1.3)
                            dt_l3 += (
                                f",drawtext=fontfile='{fp_r}':text='{tsec}':"
                                f"fontcolor=0x{cacc}@0.85:fontsize={fsu}:"
                                f"x={bx + int(w_res * 0.012)}:y={ysu}"
                            )
                        ws_l3, we_l3 = _word_window(
                            otxt, esc.get("texto", ""), t_scene_start, t_scene_end, dur_clip
                        )
                        log(f"    L3 '{otxt[:20]}' @ {ws_l3:.2f}s-{we_l3:.2f}s")
                        _apply_timed_overlay(seg_out, dt_l3, ws_l3, we_l3, dur_clip, f"seg_{i:04d}_l3")

                elif tipo == "broll" and rp:
                    # KB base + PiP overlay en esquina (pre-renderizado en 2 pasos, evita
                    # comillas anidadas en filter_complex sobre Windows)
                    kb_base = str(tmp_dir / f"kb_{i:04d}.mp4")
                    try:
                        _enc(kb_base, kb, dur_clip, img_path, crf=25, tout=90)
                    except Exception as exc:
                        log(f"  [WARNING] broll KB fallback normal: {exc}")
                        _enc(kb_base, _bsb(w_res, h_res), dur_clip, img_path, crf=25, tout=60)
                    pw = int(w_res * 0.26)
                    pw += pw % 2
                    ph = int(h_res * 0.26)
                    ph += ph % 2
                    px, py = w_res - pw - 24, 24
                    fc_b = (
                        f"[0:v]setpts=PTS-STARTPTS[bg];"
                        f"[1:v]scale={pw}:{ph}:force_original_aspect_ratio=decrease,"
                        f"pad={pw}:{ph}:(ow-iw)/2:(oh-ih)/2:color=black,"
                        f"setsar=1,fps=24[pip];"
                        f"[bg][pip]overlay={px}:{py}[v]"
                    )
                    _enc(
                        seg_out,
                        None,
                        dur_clip,
                        ["-i", kb_base, "-loop", "1", "-t", str(dur_clip), "-i", rp],
                        fc=fc_b,
                        mv="[v]",
                        crf=24,
                        tout=90,
                    )

                elif tipo == "texto_enfasis":
                    _enc(seg_out, kb, dur_clip, img_path, crf=23)

                else:
                    _enc(seg_out, kb, dur_clip, img_path, crf=25)

                # ══════════════ POST-PROCESO 1: overlay de texto generico ══════════════
                if otxt and fp_b and tipo not in _YA_APLICO_OVERLAY and os.path.exists(seg_out):
                    sto = str(tmp_dir / f"seg_{i:04d}_txt.mp4")
                    ov_enable = ""
                    if tipo in _SYNC_TIPOS and all_words:
                        ov_kws = [p.strip() for p in re.split(r"[,\s%]+", otxt) if p.strip()]
                        woff = _find_word_offset(ov_kws, t_scene_start, t_scene_end)
                        if woff:
                            ws, we = woff
                            ov_enable = f":enable='between(t,{ws:.3f},{we:.3f})'"
                            log(f"    overlay '{otxt[:20]}' @ {ws:.2f}s-{we:.2f}s")

                    dt = None
                    if tipo == "texto_enfasis":
                        e = _ct_short(otxt, max_words=4, max_chars=30) or otxt[:30]
                        ln = _wr(e, 18)
                        sf = _sf(ln)
                        fs = int(w_res / 11)
                        bh = int(fs * len(ln) * 1.25 + h_res * 0.08)
                        by = (h_res - bh) // 2
                        dt_enf = (
                            f"drawbox=x=0:y={by}:w=iw:h={bh}:color=black@0.85:t=fill,"
                            f"drawbox=x=0:y={by}:w=iw:h=5:color=0x{cacc}@0.95:t=fill,"
                            f"drawbox=x=0:y={by + bh - 5}:w=iw:h=5:color=0x{cacc}@0.95:t=fill,"
                            f"drawtext=fontfile='{fp_b}':text='{sf}':"
                            f"fontcolor=black@0.50:fontsize={fs}:"
                            f"line_spacing={int(fs * 0.15)}:"
                            f"x=(w-text_w)/2+4:y=(h-text_h)/2+4,"
                            f"drawtext=fontfile='{fp_b}':text='{sf}':"
                            f"fontcolor=white@1.0:fontsize={fs}:"
                            f"line_spacing={int(fs * 0.15)}:"
                            f"x=(w-text_w)/2:y=(h-text_h)/2"
                        )
                        enf_s, enf_e = _word_window(
                            otxt, esc.get("texto", ""), t_scene_start, t_scene_end, dur_clip
                        )
                        log(f"    ENF '{otxt[:15]}' @ {enf_s:.2f}s-{enf_e:.2f}s")
                        _apply_timed_overlay(seg_out, dt_enf, enf_s, enf_e, dur_clip, f"seg_{i:04d}_enf")

                    elif tipo == "intro_dinamica":
                        e = _ct_short(otxt, max_words=5, max_chars=40) or otxt[:40]
                        ln = _wr(e, 20)
                        ft = int(w_res / 15)
                        ph2 = int(ft * len(ln) * 1.35 + h_res * 0.12)
                        py2 = h_res - ph2 - int(h_res * 0.03)
                        py3 = py2 + int(ph2 * 0.20)
                        lh = int(ft * 1.35)
                        dt_p = [
                            f"drawbox=x=0:y={py2}:w=iw:h={ph2}:color=black@0.72:t=fill",
                            f"drawbox=x=0:y={py2}:w=iw:h=6:color=0x{cacc}@0.95:t=fill",
                        ]
                        for li, lt in enumerate(ln):
                            ly = py3 + li * lh
                            dt_p += [
                                f"drawtext=fontfile='{fp_b}':text='{lt}':fontcolor=black@0.50:fontsize={ft}:x=(w-text_w)/2+3:y={ly + 3}",
                                f"drawtext=fontfile='{fp_b}':text='{lt}':fontcolor=white@1.0:fontsize={ft}:x=(w-text_w)/2:y={ly}",
                            ]
                        dt = ",".join(dt_p)

                    elif tipo in ("ref_persona", "ref_lugar", "google_fullscreen"):
                        ln = _wr(otxt[:80], 30)
                        sf = _sf(ln)
                        fs = int(w_res / 24)
                        pv = int(h_res * 0.020)
                        dt_ref = (
                            f"drawtext=fontfile='{fp_b}':text='{sf}':"
                            f"fontcolor=white@1.0:fontsize={fs}:"
                            f"line_spacing={int(fs * 0.22)}:"
                            f"x=(w-text_w)/2:y=h-text_h-{int(h_res * 0.06)}:"
                            f"shadowcolor=black@1.0:shadowx=3:shadowy=3:"
                            f"box=1:boxcolor=black@0.72:boxborderw={pv}"
                        )
                        ws_ref, we_ref = _word_window(
                            otxt, esc.get("texto", ""), t_scene_start, t_scene_end, dur_clip
                        )
                        _apply_timed_overlay(seg_out, dt_ref, ws_ref, we_ref, dur_clip, f"seg_{i:04d}_ref")

                    else:
                        ln = _wr(otxt, 28)
                        sf = _sf(ln)
                        fs = int(w_res / 30)
                        pv = int(h_res * 0.016)
                        ppos = {
                            "bottom_center": f"x=(w-text_w)/2:y=h-text_h-{int(h_res * 0.06)}",
                            "top_center": f"x=(w-text_w)/2:y={int(h_res * 0.05)}",
                            "center": "x=(w-text_w)/2:y=(h-text_h)/2",
                            "bottom_left": f"x={int(w_res * 0.05)}:y=h-text_h-{int(h_res * 0.06)}",
                            "top_left": f"x={int(w_res * 0.05)}:y={int(h_res * 0.05)}",
                            "right_center": f"x={int(w_res * 0.55)}:y=(h-text_h)/2",
                        }
                        auto_pos = [
                            "bottom_center",
                            "bottom_left",
                            "bottom_center",
                            "top_center",
                            "bottom_center",
                            "bottom_left",
                        ]
                        xy = ppos.get(
                            opos,
                            ppos.get(
                                auto_pos[i % len(auto_pos)], f"x=(w-text_w)/2:y=h-text_h-{int(h_res * 0.06)}"
                            ),
                        )
                        dt = (
                            f"drawtext=fontfile='{fp_r}':text='{sf}':"
                            f"fontcolor=0x{cacc}@1.0:fontsize={fs}:"
                            f"line_spacing={int(fs * 0.20)}:{xy}:"
                            f"shadowcolor=black@1.0:shadowx=3:shadowy=3:"
                            f"box=1:boxcolor=black@0.72:boxborderw={pv}{ov_enable}"
                        )

                    try:
                        if dt is not None:
                            _add_txt(seg_out, sto, dt)
                            if os.path.exists(sto):
                                os.replace(sto, seg_out)
                    except Exception as exc:
                        log(f"  [WARNING] overlay txt seg {i + 1}: {exc}")

                # ══════════════ POST-PROCESO FINAL: ref_label, siempre encima ══════════════
                if rlbl and fp_r and os.path.exists(seg_out):
                    rfs = int(w_res / 48)
                    rpd = int(h_res * 0.010)
                    dark_bg = tipo in ("nombre_persona", "texto_lateral", "ref_doble")
                    rl_col = "black@0.85" if dark_bg else "white@0.92"
                    rl_box = "white@0.0" if dark_bg else "black@0.55"
                    rl_shcol = "white@0.5" if dark_bg else "black@0.95"
                    rdt = (
                        f"drawtext=fontfile='{fp_r}':text='{rlbl}':"
                        f"fontcolor={rl_col}:fontsize={rfs}:"
                        f"x={int(w_res * 0.025)}:y=h-text_h-{int(h_res * 0.035)}:"
                        f"shadowcolor={rl_shcol}:shadowx=2:shadowy=2:"
                        f"box=1:boxcolor={rl_box}:boxborderw={rpd}"
                    )
                    _apply_timed_overlay(seg_out, rdt, ref_show_from, dur_clip, dur_clip, f"seg_{i:04d}_rlbl")

                seg_paths.append(seg_out)

            except Exception as seg_e:
                log(f"  [ERROR] Error escena {i + 1}: {seg_e}")
                try:
                    fb_vf = _fallback_caption_vf(
                        _bsb(w_res, h_res), w_res, h_res, otxt, font_bold or font_reg
                    )
                    _enc(seg_out, fb_vf, dur_clip, img_path, preset="ultrafast", crf=28, tout=60)
                    seg_paths.append(seg_out)
                except Exception:
                    pass

        if not seg_paths:
            raise Exception("No se genero ningun segmento")

        # ── 5. Concatenar por lotes ────────────────────────────────────
        log("Concatenando segmentos...", 83)
        concat_out = str(tmp_dir / "concat_editor.mp4")

        def _write_clist(paths, list_path):
            with open(list_path, "w", encoding="utf-8") as lf:
                for p in paths:
                    lf.write("file '" + p.replace("\\", "/") + "'\n")

        def _do_concat(paths, out_p, timeout=300):
            lst = out_p + ".txt"
            _write_clist(paths, lst)
            run(
                [
                    ffmpeg_utils.ffmpeg_exe(),
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    lst,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "26",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "24",
                    "-an",
                    "-movflags",
                    "+faststart",
                    out_p,
                ],
                "concat_list",
                timeout=timeout,
            )
            if not os.path.exists(out_p):
                raise Exception("concat no genero: " + out_p)
            try:
                os.remove(lst)
            except Exception:
                pass

        batch = 8
        if len(seg_paths) <= batch:
            _do_concat(seg_paths, concat_out)
        else:
            bouts = []
            nb = (len(seg_paths) + batch - 1) // batch
            for bi, st in enumerate(range(0, len(seg_paths), batch)):
                chunk = seg_paths[st : st + batch]
                bo = str(tmp_dir / f"batch_{bi:04d}.mp4")
                log(f"   lote {bi + 1}/{nb}...", 84 + bi)
                _do_concat(chunk, bo)
                bouts.append(bo)
            log("Uniendo lotes...", 90)
            _do_concat(bouts, concat_out)

        if not os.path.exists(concat_out):
            raise Exception("concat_out no existe tras concatenacion")

        # ── 6. Mezclar audio -- alineado exacto (igual que Render normal) ──────
        log("Mezclando audio final (alineado)...", 92)
        video_final = str(out_dir_p / f"editor_{job_id}.mp4")
        try:
            ffmpeg_utils.final_mux_aligned(concat_out, audio_path, video_final, dur_audio, log=log)
        except Exception as mux_e:
            log(f"  [WARNING] mux_aligned: {mux_e} - usando -shortest")
            run(
                [
                    ffmpeg_utils.ffmpeg_exe(),
                    "-y",
                    "-i",
                    concat_out,
                    "-i",
                    audio_path,
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                    "-movflags",
                    "+faststart",
                    video_final,
                ],
                "mezcla audio fallback",
                timeout=180,
            )

        if not os.path.exists(video_final):
            raise Exception("FFmpeg no genero el video final")

        size_mb = os.path.getsize(video_final) / (1024 * 1024)
        log(f"Video listo - {size_mb:.1f} MB", 100)
        job_registry.update_job(
            job_id,
            estado="completado",
            video_url=f"/api/descargar_render/{job_id}",
            video_path=video_final,
            size_mb=round(size_mb, 1),
        )
        open_folder(video_final)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.rmtree(tmp_ref_dir, ignore_errors=True)

    except Exception as exc:
        logger.exception("[editor:%s] render enriquecido fallo", job_id)
        err_msg = str(exc)
        log(f"Error: {err_msg}")
        log(f"Carpeta temporal conservada para diagnostico: {tmp_dir}")
        job_registry.update_job(job_id, estado="error", error=err_msg, tmp_dir=str(tmp_dir))
        shutil.rmtree(tmp_ref_dir, ignore_errors=True)
