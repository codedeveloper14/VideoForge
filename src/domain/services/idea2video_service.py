"""Idea -> guion -> video: genera un guion (Claude si hay API key, si no plantilla) y
opcionalmente corre un pipeline "autopilot" completo (escenas -> prompts -> voz -> imagenes
via Flow -> ensamblado FFmpeg) en un job de fondo. La sintesis de voz reutiliza voice_service
en vez de reimplementar el chunking/saneo/llamadas a n8n (el original las duplicaba inline)."""

import glob
import json
import os
import re
import ssl
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from src.domain.services import flow_animation_service, scene_timestamp_service, voice_service
from src.infrastructure.ai_providers import whisper_client
from src.infrastructure.media import ffmpeg_utils
from src.infrastructure.storage import project_repository
from src.utils.logger import get_logger
from src.utils.platform_utils import no_window_kwargs, open_folder

logger = get_logger(__name__)

_jobs: dict[str, dict] = {}

_STYLES = {
    "cinematic": [
        ("Gran angular, luz dramatica de amanecer", "Orquesta epica, arranca en el primer frame"),
        ("Primer plano, bokeh profundo, camara lenta", "Tema orquestal tenso"),
        ("Travelling lateral fluido", "Cuerdas en crescendo"),
        ("Plano cenital, perspectiva aerea", "Climax instrumental"),
    ],
    "tutorial": [
        ("Pantalla con UI, anotaciones visuales animadas", "Musica ligera, discreta"),
        ("Demostracion paso a paso, zoom en detalles", "Ambiente neutro, clean"),
        ("Comparativa side-by-side", "Transicion suave"),
        ("Infografia animada", "Tono claro e informativo"),
    ],
    "documental": [
        ("Plano medio, entrevista, iluminacion natural", "Narracion sobria en off"),
        ("Archivo historico / material de epoca", "Sonido ambiente autentico"),
        ("Exterior, camara en mano", "Sonido directo, sin musica"),
        ("Datos y graficos animados", "Fondo documental, discreto"),
    ],
    "viral": [
        ("Corte rapido, angulo dinamico", "Beat electronico, crescendo"),
        ("Split screen, ritmo acelerado", "Drop de impacto"),
        ("POV camara, inmersivo", "Efecto sonoro de golpe"),
        ("Texto animado sobre imagen", "Beat viral trending"),
    ],
    "corporativo": [
        ("Oficina moderna, equipo colaborando", "Musica corporativa positiva"),
        ("Presentacion limpia, minimalista", "Fondo profesional"),
        ("Reunion de equipo, diversidad", "Motivador corporativo"),
        ("Producto en uso, contexto real", "Musica positiva de fondo"),
    ],
}

_TONE_DATA = {
    "inspirador": {
        "hook": "Hay momentos que lo cambian todo. Este es uno de ellos.",
        "bridge": "Lo que viene a continuacion no es teoria. Es la realidad.",
        "climax": "Juntos, lo imposible se vuelve posible.",
        "cta": "Comparte. Inspira. Transforma.",
    },
    "profesional": {
        "hook": "Los datos son contundentes. El analisis no deja lugar a dudas.",
        "bridge": "La evidencia respalda una sola conclusion.",
        "climax": "La eficiencia y el conocimiento son la ventaja decisiva.",
        "cta": "Actua con informacion. Decide con claridad.",
    },
    "casual": {
        "hook": "¿Y si te dijera que hay algo que la mayoria no sabe sobre esto?",
        "bridge": "Sere directo contigo, sin rodeos.",
        "climax": "Es mas simple de lo que parece. Solo hay que verlo.",
        "cta": "Dale like si esto te hizo pensar. Comenta que opinas.",
    },
    "tecnico": {
        "hook": "El sistema opera bajo parametros especificos. Vamos a analizarlos.",
        "bridge": "Cada variable tiene un impacto medible en el resultado.",
        "climax": "Los patrones revelan una direccion inequivoca.",
        "cta": "Implementa. Mide. Itera.",
    },
    "urgente": {
        "hook": "No hay tiempo que perder. Cada segundo de inaccion tiene un costo.",
        "bridge": "La ventana de oportunidad no estara abierta para siempre.",
        "climax": "El que actua hoy define las reglas del manana.",
        "cta": "Actua ahora. No manana. Ahora.",
    },
}

_ANGLE_TEMPLATE = [
    (
        "CONTEXTO",
        "Para entender {topic}, hay que ver el panorama completo.\n"
        "No basta con la superficie: cada capa que se descubre\n"
        "revela dimensiones que cambian por completo la perspectiva.",
    ),
    (
        "PROFUNDIDAD",
        "¿Que hay realmente detras de {topic}?\n"
        "Los detalles que la mayoria pasa por alto\n"
        "son precisamente los que marcan la diferencia definitiva.",
    ),
    (
        "IMPACTO REAL",
        "{topic} tiene consecuencias concretas, no abstractas.\n"
        "No en un futuro lejano: ahora mismo, hoy.\n"
        "Quienes lo entienden ya llevan una ventaja decisiva.",
    ),
    (
        "PERSPECTIVA",
        "Visto desde otro angulo, {topic} revela patrones\n"
        "que no son evidentes a primera vista.\n"
        "La informacion mas valiosa raramente esta en la superficie.",
    ),
    (
        "LO QUE NADIE DICE",
        "Hay aspectos de {topic} que pocas veces se mencionan.\n"
        "No porque no sean importantes,\n"
        "sino porque requieren un nivel mas profundo de analisis.",
    ),
    (
        "MOMENTO ACTUAL",
        "{topic} es mas relevante hoy que en cualquier otro momento.\n"
        "Las circunstancias actuales crean una convergencia unica.\n"
        "Este tipo de alineacion no se repite con frecuencia.",
    ),
    (
        "EL FACTOR DECISIVO",
        "De todos los elementos que rodean a {topic},\n"
        "hay uno que lo determina todo.\n"
        "Identificarlo es la diferencia entre el acierto y el error.",
    ),
    (
        "EVIDENCIA",
        "Los hechos sobre {topic} son elocuentes.\n"
        "No se trata de opiniones ni interpretaciones subjetivas.\n"
        "Las tendencias apuntan de forma inequivoca en una direccion.",
    ),
]


def _template_script(idea: str, dur_sec: int, style: str, tone: str, audience: str) -> dict:
    n_scenes = max(4, min(40, round(dur_sec / 7)))
    dur_label = f"{dur_sec // 60}m{dur_sec % 60:02d}s" if dur_sec >= 60 else f"{dur_sec}s"

    sv_list = _STYLES.get(style, _STYLES["cinematic"])
    td = _TONE_DATA.get(tone, _TONE_DATA["inspirador"])
    topic = idea.strip()
    title = topic[:60] + ("..." if len(topic) > 60 else "")

    def sv(i):
        return sv_list[i % len(sv_list)]

    sections = []
    visual0, audio0 = sv(0)
    sections.append(
        f"[ESCENA 1 — GANCHO | ~7 seg]\n"
        f"[Visual: {visual0}. Impacto inmediato, sin texto en pantalla.]\n"
        f"[Audio: {audio0}]\n\n"
        f"{td['hook']}\n"
        f"{topic}.\n"
        f"Esto es lo que necesitas saber."
    )

    dev_n = n_scenes - 3
    for i in range(dev_n):
        sc = i + 2
        angle_name, angle_body = _ANGLE_TEMPLATE[i % len(_ANGLE_TEMPLATE)]
        visual_i, audio_i = sv(i + 1)
        sections.append(
            f"[ESCENA {sc} — {angle_name} | ~7 seg]\n"
            f"[Visual: {visual_i}. Mantiene tension, ritmo sostenido.]\n"
            f"[Audio: {audio_i}]\n\n"
            f"{angle_body.format(topic=topic)}"
        )

    cl = n_scenes - 1
    visual_cl, audio_cl = sv(cl)
    sections.append(
        f"[ESCENA {cl} — PUNTO DE INFLEXION | ~10 seg]\n"
        f"[Visual: {visual_cl}. Maxima intensidad. El momento mas memorable.]\n"
        f"[Audio: Pico musical. Climax emocional.]\n\n"
        f"{td['bridge']}\n"
        f"{topic} define un antes y un despues.\n"
        f"Las decisiones de hoy construyen el manana.\n"
        f"{td['climax']}"
    )

    sections.append(
        f"[ESCENA {n_scenes} — CIERRE Y LLAMADA A LA ACCION | ~8 seg]\n"
        f"[Visual: Logo y tagline. Fade out elegante.]\n"
        f"[Audio: Resolucion musical. Remate definitivo.]\n\n"
        f"El momento es ahora. No manana.\n"
        f"{td['cta']}\n\n"
        f"[{title}]"
    )

    script = "\n\n".join(sections)
    return {
        "title": title,
        "script": script,
        "scenes": n_scenes,
        "words": len(script.split()),
        "dur": dur_label,
    }


def _call_claude(idea: str, dur_sec: int, style: str, tone: str, audience: str, api_key: str) -> dict | None:
    try:
        n_sc = max(4, round(dur_sec / 7))
        dur_s = f"{dur_sec // 60}:{dur_sec % 60:02d}" if dur_sec >= 60 else f"{dur_sec}s"
        prompt = (
            f"Genera un guion profesional para video de {dur_s} en espanol.\n"
            f"IDEA: {idea}\nESTILO: {style}\nTONO: {tone}\nAUDIENCIA: {audience}\n"
            f"ESCENAS: ~{n_sc}\n\n"
            f"Usa este formato para cada escena:\n"
            f"[ESCENA N - NOMBRE | ~X seg]\n"
            f"[Visual: descripcion]\n[Audio: indicacion]\n\nNarracion aqui...\n\n"
            f"Incluye: gancho impactante, desarrollo, climax, CTA al cierre. "
            f"Solo el guion, sin explicaciones."
        )
        payload = json.dumps(
            {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode()
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            rdata = json.loads(resp.read().decode())
        script = rdata["content"][0]["text"].strip()
        n_found = max(1, script.count("[ESCENA"))
        return {
            "title": idea[:60].rstrip(),
            "script": script,
            "scenes": n_found,
            "words": len(script.split()),
            "dur": dur_s,
        }
    except Exception as exc:
        logger.warning("idea2video: _call_claude fallo, uso template: %s", exc)
        return None


def generate_script(idea: str, dur_sec: int, style: str, tone: str, audience: str) -> dict:
    idea = (idea or "").strip()[:3000]
    if not idea:
        raise ValueError("idea requerida")
    dur_sec = max(15, min(1200, int(dur_sec or 60)))
    style = (style or "cinematic").strip()
    tone = (tone or "inspirador").strip()
    audience = (audience or "general").strip()

    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
    if api_key:
        result = _call_claude(idea, dur_sec, style, tone, audience, api_key)
        if result:
            return result
    return _template_script(idea, dur_sec, style, tone, audience)


def _parse_scenes(script: str) -> list[str]:
    parts = re.split(r"\n\s*\n", script.strip())
    return [p.strip() for p in parts if p.strip() and len(p.strip()) > 15]


def _extract_prompts(scenes: list[str]) -> list[str]:
    out = []
    for s in scenes:
        m = re.search(r"\[Visual:\s*([^\]]{5,})\]", s, re.I)
        if m:
            out.append(m.group(1).strip())
        else:
            txt = re.sub(r"\[[^\]]*\]", "", s).strip()
            first = txt.split(".")[0].strip()[:120]
            if len(first) > 10:
                out.append(first)
    return [p for p in out if p][:20]


def _extract_narration(script: str) -> str:
    t = re.sub(r"\[ESCENA[^\]]*\]", "", script, flags=re.I)
    t = re.sub(r"\[\w+:[^\]]*\]", "", t)
    t = re.sub(r"\n{2,}", "\n", t.strip())
    return " ".join(t.split())[:8000]


def _scan_images(job: dict, proj_name: str, img_dir: Path) -> None:
    imgs = []
    for pat in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        imgs.extend(glob.glob(str(img_dir / pat)))
    imgs = sorted(set(imgs))
    job["images"] = [
        f"/api/idea2video/ap_imagen?project={proj_name}&file={os.path.basename(p)}" for p in imgs
    ]


def start_autopilot(script: str, title: str, voice_id: str, ref_image: str | None, mode: str) -> dict:
    script = (script or "").strip()
    if not script:
        raise ValueError("Sin guion")
    if mode not in ("rapido", "profesional"):
        mode = "rapido"

    job_id = str(uuid.uuid4())[:8]
    safe_title = re.sub(r"[^\w\-]", "_", (title or "video_autopilot")[:40])
    proj_name = project_repository.sanitize_name(f"{safe_title}_{job_id}")
    _jobs[job_id] = {
        "status": "running",
        "phase": "",
        "phases": {
            k: "pending" for k in ("recursos", "fragmentar", "prompts", "voz", "imagenes", "ensamblar")
        },
        "images": [],
        "log": [],
        "title": title or "video_autopilot",
        "project_name": proj_name,
        "current_detail": "",
        "scenes": 0,
        "char_count": 0,
        "started": time.time(),
        "ref_image": ref_image,
        "mode": mode,
    }
    threading.Thread(target=_worker, args=(job_id, script, voice_id), daemon=True).start()
    return {"ok": True, "job_id": job_id}


def get_autopilot_status(job_id: str) -> dict | None:
    job = _jobs.get(job_id)
    if not job:
        return None
    result = dict(job)
    result["elapsed"] = int(time.time() - job["started"])
    return result


def open_autopilot_folder(job_id: str) -> None:
    job = _jobs.get(job_id)
    if not job:
        raise ValueError("Job no encontrado")
    proj = job.get("project_name", "")
    if not proj:
        raise ValueError("Sin proyecto")
    open_folder(str(project_repository.project_dir(proj)))


def get_autopilot_image(proj_name: str, filename: str) -> Path | None:
    path = project_repository.resolve_safe_file(proj_name, "imagenes", filename)
    if not path or not path.exists():
        return None
    return path


def _worker(job_id: str, script: str, voice_id: str) -> None:
    job = _jobs[job_id]
    ref_image = job.get("ref_image")
    mode = job.get("mode", "rapido")
    proj_name = job["project_name"]

    def upd(phase: str, status: str, detail: str = "") -> None:
        job["phase"] = phase
        job["phases"][phase] = status
        if detail:
            job["current_detail"] = detail
            job["log"].append(detail)

    try:
        # ── 1. Preparar recursos ────────────────────────────────────
        upd("recursos", "active", "Creando estructura del proyecto...")
        proj_dir = project_repository.project_dir(proj_name)
        for sub in ("guion", "imagenes", "audio"):
            (proj_dir / sub).mkdir(parents=True, exist_ok=True)
        (proj_dir / "guion" / "guion.txt").write_text(script, encoding="utf-8")
        time.sleep(0.4)
        upd("recursos", "done", f'Proyecto "{proj_name}" listo')

        # ── 2. Fragmentar guion ──────────────────────────────────────
        upd("fragmentar", "active", "Dividiendo guion en escenas...")
        scenes = _parse_scenes(script)
        prompts = _extract_prompts(scenes)
        job["scenes"] = len(scenes)
        job["prompts"] = prompts
        job["_scenes_list"] = scenes
        time.sleep(0.6)
        upd("fragmentar", "done", f"{len(scenes)} escenas · {len(prompts)} prompts extraidos")

        # ── 3. Generar prompts ────────────────────────────────────────
        upd("prompts", "active", "Guardando prompts...")
        prompts_dir = proj_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)
        (prompts_dir / "prompts.txt").write_text(
            "\n".join(f"{i + 1}. {p}" for i, p in enumerate(prompts)), encoding="utf-8"
        )
        time.sleep(0.6)
        upd("prompts", "done", f"{len(prompts)} prompts guardados")

        # ── 4. Voz (reutiliza voice_service en vez de re-implementar) ─
        upd("voz", "active", "Iniciando sintesis de voz...")
        narration = _extract_narration(script)
        char_count = len(narration)
        job["char_count"] = char_count
        upd("voz", "active", f"Procesando {char_count} caracteres de narracion...")

        voz_ok = False
        if voice_id and narration:
            try:
                gen = voice_service.generate_voice(None, voice_id, narration)
                if gen.get("status_code") == 200 and gen.get("fragments"):
                    upd("voz", "active", f"Fusionando {len(gen['fragments'])} fragmentos de audio...")
                    body, status = voice_service.merge_audio(
                        proj_name, {"fragments": gen["fragments"], "voice_id": voice_id}
                    )
                    if status < 400:
                        parsed = json.loads(body)
                        raw = parsed[0] if isinstance(parsed, list) else parsed
                        voz_ok = bool(isinstance(raw, dict) and raw.get("finalAudio"))
                    if not voz_ok:
                        job["log"].append(f"Voz: fusion respondio {status}")
                else:
                    job["log"].append(f"Voz: {str(gen.get('error', 'sin fragmentos'))[:120]}")
            except Exception as exc:
                job["log"].append(f"Voz: {str(exc)[:120]}")

        if voz_ok:
            upd("voz", "done", "Voz sintetizada · audio guardado")
        elif voice_id:
            upd("voz", "partial", "Voz en proceso (revisar n8n/ElevenLabs)")
        else:
            upd("voz", "skip", "Sin voz seleccionada (omitido)")

        # ── 5. Imagenes (Flow) ─────────────────────────────────────────
        img_dir = proj_dir / "imagenes"
        if prompts:
            upd("imagenes", "active", f"Iniciando generacion de {len(prompts)} imagenes...")
            ap_model = "IMAGE_GENERATION_001_IMAGEN4" if ref_image else "NANO_BANANA_2"
            already_flow = False
            try:
                flow_animation_service.start_run(
                    prompts=prompts,
                    out_dir=str(img_dir),
                    slots=5,
                    aspect="IMAGE_ASPECT_RATIO_LANDSCAPE",
                    model=ap_model,
                    max_retries=2,
                    ref_image=ref_image,
                    auto_open=True,
                )
            except RuntimeError:
                already_flow = True

            if not already_flow:
                deadline = time.time() + 600
                while time.time() < deadline:
                    st = flow_animation_service.get_status(0)
                    saved = st.get("images_saved", 0)
                    total = st.get("total", len(prompts))
                    running = st.get("running", False)
                    job["current_detail"] = f"Flow: {saved}/{total} imagenes generadas"
                    _scan_images(job, proj_name, img_dir)
                    if not running:
                        break
                    time.sleep(2)
            else:
                time.sleep(2)
                job["log"].append("[Flow] Generacion en curso en otro proceso — esperando")

            _scan_images(job, proj_name, img_dir)
            n_img = len(job["images"])
            if n_img > 0:
                upd("imagenes", "done", f"{n_img} imagenes generadas con Flow")
            else:
                upd(
                    "imagenes",
                    "partial",
                    "Sin imagenes — verifica cuentas Flow y que los browsers esten conectados",
                )
        else:
            upd("imagenes", "skip", "Sin prompts de imagen")

        # ── 6. Ensamblar ─────────────────────────────────────────────
        upd("ensamblar", "active", "Ensamblando video final...")
        try:
            imgs = sorted(
                glob.glob(str(proj_dir / "imagenes" / "*.png"))
                + glob.glob(str(proj_dir / "imagenes" / "*.jpg"))
                + glob.glob(str(proj_dir / "imagenes" / "*.webp")),
                key=lambda p: os.path.basename(p),
            )
            if not imgs:
                raise Exception("Sin imagenes para ensamblar")

            aud_files = sorted(
                glob.glob(str(proj_dir / "audio" / "*.wav")) + glob.glob(str(proj_dir / "audio" / "*.mp3"))
            )
            audio = aud_files[0] if aud_files else None
            vf_dir = proj_dir / "video_final"
            vf_dir.mkdir(exist_ok=True)
            final_mp4 = str(vf_dir / "video_autopilot.mp4")

            if mode == "profesional":
                upd("ensamblar", "active", "Analizando audio con WhisperX...")
                scenes_txt = job.get("_scenes_list") or [p for p in script.split("\n\n") if p.strip()]
                aud_dur = ffmpeg_utils.ffprobe_duration(audio) if audio else 0.0
                segmentos: list[dict] = []
                all_words: list[dict] | None = None
                if audio:
                    try:
                        job["current_detail"] = "WhisperX: alineando palabras..."
                        segmentos, all_words, backend = whisper_client.transcribe_with_fallback(audio)
                        job["current_detail"] = f"WhisperX ({backend}): {len(all_words)} palabras alineadas"
                    except Exception as wex:
                        job["log"].append(f"WhisperX fallo ({wex}), usando duracion igual por escena")
                else:
                    job["log"].append("Sin audio -- timing proporcional en vez de WhisperX")

                def _on_fallback(unmatched, total, last_ok, dur):
                    job["log"].append(f"Word-level anomalo ({unmatched}/{total}) → segment-level fallback")

                if scenes_txt and aud_dur > 0:
                    ts_list = scene_timestamp_service.assign_timestamps_auto(
                        scenes_txt, segmentos, all_words, aud_dur, on_fallback=_on_fallback
                    )
                else:
                    n_s = max(1, len(scenes_txt) or len(imgs))
                    d_s = aud_dur / n_s if aud_dur > 0 else 3.0
                    ts_list = [
                        {"inicio": i * d_s, "fin": (i + 1) * d_s, "duracion": d_s, "scene_idx": i}
                        for i in range(n_s)
                    ]

                upd("ensamblar", "active", f"Renderizando {len(ts_list)} escenas con FFmpeg...")
                n_imgs = len(imgs)
                concat_path = str(vf_dir / "_concat_pro.txt")
                tmp_vid = str(vf_dir / "_pro_tmp.mp4")
                with open(concat_path, "w", encoding="utf-8") as clf:
                    for i, ts in enumerate(ts_list):
                        sidx = min(ts.get("scene_idx", i), n_imgs - 1)
                        dur = max(0.1, ts.get("duracion", 1.0))
                        pp = imgs[sidx].replace("\\", "/").replace("'", "'\\''")
                        clf.write(f"file '{pp}'\nduration {dur:.3f}\n")
                    last_sidx = min(
                        (ts_list[-1].get("scene_idx", n_imgs - 1) if ts_list else n_imgs - 1), n_imgs - 1
                    )
                    pp_last = imgs[last_sidx].replace("\\", "/").replace("'", "'\\''")
                    clf.write(f"file '{pp_last}'\n")

                r1 = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        concat_path,
                        "-vf",
                        (
                            "scale=1920:1080:force_original_aspect_ratio=decrease,"
                            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p"
                        ),
                        "-c:v",
                        "libx264",
                        "-preset",
                        "fast",
                        "-crf",
                        "18",
                        "-r",
                        "24",
                        "-an",
                        "-movflags",
                        "+faststart",
                        tmp_vid,
                    ],
                    capture_output=True,
                    text=True,
                    **no_window_kwargs(),
                )
                if r1.returncode != 0:
                    raise Exception(f"FFmpeg profesional fallo: {r1.stderr[-300:]}")
                if audio:
                    r2 = subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            tmp_vid,
                            "-i",
                            audio,
                            "-c:v",
                            "copy",
                            "-c:a",
                            "aac",
                            "-b:a",
                            "192k",
                            "-shortest",
                            "-movflags",
                            "+faststart",
                            final_mp4,
                        ],
                        capture_output=True,
                        text=True,
                        **no_window_kwargs(),
                    )
                    if r2.returncode != 0:
                        raise Exception(f"FFmpeg mux profesional fallo: {r2.stderr[-300:]}")
                else:
                    os.rename(tmp_vid, final_mp4)
                wx_label = f"WhisperX · {len(all_words)} palabras" if all_words else "timing proporcional"
                upd("ensamblar", "done", f"Video profesional listo · {len(ts_list)} escenas · {wx_label}")

            else:
                aud_dur = ffmpeg_utils.ffprobe_duration(audio) if audio else 0.0
                n_imgs = len(imgs)
                dur_per = max(1.5, aud_dur / n_imgs) if aud_dur > 1.0 else 3.0

                upd("ensamblar", "active", f"Creando slideshow: {n_imgs} imagenes × {dur_per:.1f}s...")

                concat_path = str(vf_dir / "_concat.txt")
                tmp_vid = str(vf_dir / "_slideshow_tmp.mp4")
                with open(concat_path, "w", encoding="utf-8") as clf:
                    for img in imgs:
                        pp = img.replace("\\", "/").replace("'", "'\\''")
                        clf.write(f"file '{pp}'\nduration {dur_per:.3f}\n")
                    pp = imgs[-1].replace("\\", "/").replace("'", "'\\''")
                    clf.write(f"file '{pp}'\n")

                r1 = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        concat_path,
                        "-vf",
                        (
                            "scale=1280:720:force_original_aspect_ratio=decrease,"
                            "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=24,setpts=PTS-STARTPTS"
                        ),
                        "-c:v",
                        "libx264",
                        "-preset",
                        "ultrafast",
                        "-crf",
                        "26",
                        "-pix_fmt",
                        "yuv420p",
                        "-an",
                        "-movflags",
                        "+faststart",
                        tmp_vid,
                    ],
                    capture_output=True,
                    text=True,
                    **no_window_kwargs(),
                )
                if r1.returncode != 0 or not os.path.exists(tmp_vid):
                    raise Exception(f"FFmpeg slideshow: {(r1.stderr or '')[-300:]}")

                if audio and os.path.exists(audio):
                    upd("ensamblar", "active", "Mezclando video con audio...")
                    r2 = subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            tmp_vid,
                            "-i",
                            audio,
                            "-c:v",
                            "copy",
                            "-c:a",
                            "aac",
                            "-b:a",
                            "192k",
                            "-shortest",
                            "-movflags",
                            "+faststart",
                            final_mp4,
                        ],
                        capture_output=True,
                        text=True,
                        **no_window_kwargs(),
                    )
                    if r2.returncode == 0 and os.path.exists(final_mp4):
                        try:
                            os.remove(tmp_vid)
                        except OSError:
                            pass
                    else:
                        os.rename(tmp_vid, final_mp4)
                        job["log"].append(f"Audio mux fallo: {(r2.stderr or '')[-150:]}")
                else:
                    os.rename(tmp_vid, final_mp4)

                try:
                    os.remove(concat_path)
                except OSError:
                    pass

                total_s = int(aud_dur or n_imgs * dur_per)
                upd("ensamblar", "done", f"Video listo · {n_imgs} imagenes · {total_s}s")

            job["video_url"] = f"/api/proyectos/video_final?project={proj_name}&file=video_autopilot.mp4"
            job["video_dl"] = f"/api/proyectos/video_final?project={proj_name}&file=video_autopilot.mp4&dl=1"

        except Exception as ev:
            job["log"].append(f"Ensamblar: {str(ev)[:200]}")
            upd("ensamblar", "partial", f"Error ensamblando: {str(ev)[:80]}")

        job["status"] = "done"

    except Exception as ex:
        job["status"] = "error"
        job["error"] = str(ex)[:300]
        if job.get("phase"):
            job["phases"][job["phase"]] = "error"
        job["log"].append(f"ERROR: {str(ex)[:200]}")
