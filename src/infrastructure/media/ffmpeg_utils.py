import json
import os
import subprocess

from src.utils.platform_utils import no_window_kwargs

_h264_encode_cache: list[str] | None = None


def run_cmd(cmd: list[str], err_ctx: str) -> subprocess.CompletedProcess:
    """Corre un subprocess y lanza un error legible si falla (ultimas 20 lineas de stderr)."""
    res = subprocess.run(cmd, capture_output=True, text=True, **no_window_kwargs())
    if res.returncode != 0:
        stderr = (res.stderr or "").strip()
        lines = stderr.splitlines()
        detail = "\n".join(lines[-20:]) if lines else "sin salida"
        raise Exception(f"{err_ctx}:\n{detail}")
    return res


def write_concat_list(path: str, clip_paths: list[str]) -> None:
    """Escribe una lista de concat de ffmpeg segura para rutas de Windows."""
    with open(path, "w", encoding="utf-8") as f:
        for p in clip_paths:
            pp = str(p).replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{pp}'\n")


def ffprobe_duration(path: str) -> float:
    """Duracion en segundos (format.duration; si falta, stream de audio)."""
    try:
        if not path or not os.path.exists(path):
            return 0.0
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=duration,codec_type", "-of", "json", path],
            capture_output=True, text=True, timeout=60, **no_window_kwargs(),
        )
        if r.returncode != 0:
            return 0.0
        d = json.loads(r.stdout or "{}")
        fmt = (d.get("format") or {}).get("duration")
        if fmt is not None and float(fmt) > 0.01:
            return float(fmt)
        for s in d.get("streams") or []:
            if s.get("codec_type") == "audio" and s.get("duration"):
                return float(s["duration"])
        return 0.0
    except Exception:
        return 0.0


def scale_pad_filter(w: int, h: int, fps: int = 24) -> str:
    """Fragmento de filtro compartido: escala manteniendo aspecto + letterbox + fps.
    El llamador agrega el resto (setpts, tpad, etc.) segun el caso."""
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps}"
    )


def libx264_encode_args_only() -> list[str]:
    """libx264 siempre (sin cache global) - fallback fiable si la GPU falla."""
    xthreads = (os.environ.get("VF_FFMPEG_X264_THREADS") or "0").strip() or "0"
    return [
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-pix_fmt", "yuv420p", "-r", "24",
        "-x264-params", f"threads={xthreads}",
    ]


def h264_encode_args() -> list[str]:
    """Codificacion H.264 para pasos que requieren re-encode (p. ej. tpad).
    VF_FFMPEG_VIDEO_ENCODER=auto|libx264|h264_nvenc|h264_qsv|h264_amf

    Modo auto: solo libx264 (CPU). FFmpeg suele listar nvenc/qsv/amf aunque el encoder
    falle en runtime (drivers, sandbox, GPU no disponible) - no se elige GPU por lista.
    """
    global _h264_encode_cache
    if _h264_encode_cache is not None:
        return list(_h264_encode_cache)
    pref = (os.environ.get("VF_FFMPEG_VIDEO_ENCODER") or "auto").strip().lower()

    if pref in ("auto", "", "libx264", "x264", "cpu"):
        _h264_encode_cache = libx264_encode_args_only()
        return list(_h264_encode_cache)
    if pref == "h264_nvenc":
        _h264_encode_cache = [
            "-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "28",
            "-pix_fmt", "yuv420p", "-r", "24",
        ]
    elif pref == "h264_qsv":
        _h264_encode_cache = [
            "-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "28",
            "-pix_fmt", "yuv420p", "-r", "24",
        ]
    elif pref == "h264_amf":
        _h264_encode_cache = [
            "-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp",
            "-qp_i", "28", "-qp_p", "28", "-pix_fmt", "yuv420p", "-r", "24",
        ]
    else:
        _h264_encode_cache = libx264_encode_args_only()
    return list(_h264_encode_cache)


def final_mux_aligned(concat_out: str, audio_path_mix: str, video_final: str,
                       duracion_total: float, log=None) -> None:
    """
    Une video + audio a duracion_total (audio maestro). Sin -shortest: no recorta al stream
    mas corto. Rellena video (tpad) o audio (apad) y recorta (trim/atrim) si hace falta.
    """
    dt = float(duracion_total)
    v_dur = ffprobe_duration(concat_out)
    a_dur = ffprobe_duration(audio_path_mix)
    eps = 0.08
    if v_dur <= 0.05:
        raise Exception(f"Video concatenado sin duracion valida ({v_dur:.3f}s)")
    if a_dur <= 0.05:
        raise Exception(f"Audio final sin duracion valida ({a_dur:.3f}s) - revisa audio_path_mix")

    def _lg(msg):
        if log:
            log(msg)

    a_parts = ["asetpts=PTS-STARTPTS"]
    if a_dur > dt + eps:
        a_parts.append(f"atrim=0:{dt:.6f}")
        a_parts.append("asetpts=PTS-STARTPTS")
    elif a_dur < dt - eps:
        a_parts.append(f"apad=pad_dur={dt - a_dur:.6f}")
    if dt > 3.0:
        st = max(0.0, dt - 1.5)
        a_parts.append(f"afade=t=out:st={st}:d=1.5")
    af = ",".join(a_parts)

    if abs(v_dur - dt) <= eps:
        _lg(f"Mux final: video~audio ({v_dur:.2f}s~{dt:.2f}s), copiando video sin re-encode")
        cmd = [
            "ffmpeg", "-y", "-i", concat_out, "-i", audio_path_mix,
            "-filter_complex", f"[1:a]{af}[aout]",
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", "-t", f"{dt:.6f}", video_final,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, **no_window_kwargs())
        copy_ok = (
            res.returncode == 0
            or (os.path.exists(video_final) and os.path.getsize(video_final) > 10240)
        )
        if not copy_ok:
            raise Exception(f"FFmpeg mux final (copy) fallo:\n{(res.stderr or res.stdout or '')[-1200:]}")
        return

    v_parts = ["setpts=PTS-STARTPTS"]
    if v_dur + eps < dt:
        gap = dt - v_dur
        v_parts.append(f"tpad=stop_mode=clone:stop_duration={gap:.6f}")
        _lg(f"Mux final: video {v_dur:.2f}s < objetivo {dt:.2f}s -> tpad +{gap:.2f}s")
    elif v_dur - eps > dt:
        v_parts.append(f"trim=duration={dt:.6f}")
        v_parts.append("setpts=PTS-STARTPTS")
        _lg(f"Mux final: video {v_dur:.2f}s > objetivo {dt:.2f}s -> trim")
    vf = ",".join(v_parts)
    fc = f"[0:v]{vf}[vout];[1:a]{af}[aout]"
    _lg("Mux final: re-encode de video para alinear duracion (libx264 ultrafast por defecto)")
    base_cmd = ["ffmpeg", "-y", "-i", concat_out, "-i", audio_path_mix, "-filter_complex", fc] + [
        "-map", "[vout]", "-map", "[aout]",
    ]
    tail = ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{dt:.6f}", video_final]

    def _run_mux(enc_list):
        return subprocess.run(base_cmd + enc_list + tail, capture_output=True, text=True, **no_window_kwargs())

    res = _run_mux(h264_encode_args())
    if res.returncode != 0:
        err = (res.stderr or res.stdout or "")[-1400:]
        _lg("Mux final: fallo el encoder elegido (p. ej. NVENC sin GPU/driver); reintentando con libx264 (CPU)...")
        res = _run_mux(libx264_encode_args_only())
        if res.returncode != 0:
            raise Exception(
                f"FFmpeg mux final (re-encode) fallo tambien con libx264:\n"
                f"primer intento:\n{err}\n---\nultimo:\n{(res.stderr or res.stdout or '')[-1200:]}"
            )
