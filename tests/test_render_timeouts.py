"""Timeouts y cancelacion del Modulo 05 (render_service.py / ffmpeg_utils.py).

Antes, ni ffmpeg_utils.run_cmd()/final_mux_aligned() ni la mayoria de los
subprocess.run() propios de render_service.py tenian timeout: un audio/video de
entrada corrupto que dejara a ffmpeg colgado bloqueaba el hilo del render para
siempre, con el job atascado en "estado": "procesando" y sin forma de
cancelarlo salvo reiniciar el backend entero (matando de paso cualquier OTRO
render en curso). Estos tests prueban las dos mitades del fix:

1. Un TimeoutExpired real/simulado se convierte en una Exception legible y
   rapida, nunca en un cuelgue -- tanto en ffmpeg_utils.run_cmd() como en el
   pipeline completo de render_service (el job termina en "error", no se
   queda pegado en "procesando").
2. stop_render(job_id) cancela un job individual sin tocar a otros."""

import subprocess
import time
from pathlib import Path

import pytest

from src.infrastructure.media import ffmpeg_utils


# ── 1a. ffmpeg_utils.run_cmd(): timeout real -> Exception rapida, nunca cuelgue ──


def test_run_cmd_timeout_real_no_se_cuelga():
    """Comando real que duerme mas que el timeout -- debe fallar en ~1s, no
    esperar los 5s completos del sleep."""
    start = time.time()
    with pytest.raises(Exception, match="timeout"):
        ffmpeg_utils.run_cmd(
            ["python", "-c", "import time; time.sleep(5)"],
            "comando de prueba colgado",
            timeout=1,
        )
    elapsed = time.time() - start
    assert elapsed < 3.0, f"run_cmd tardo {elapsed:.1f}s -- debio cortar en ~1s por el timeout"


def test_run_cmd_default_timeout_existe_y_es_razonable():
    """El default ya no es 'sin timeout' -- es un valor acotado (60-300s)."""
    assert 60 <= ffmpeg_utils.DEFAULT_FFMPEG_TIMEOUT <= 300


# ── 1b. ffmpeg_utils.final_mux_aligned(): TimeoutExpired simulado -> error controlado ──


def test_final_mux_aligned_timeout_simulado_da_error_controlado(tmp_path, monkeypatch):
    """Simula un ffmpeg colgado en el paso de mux final (TimeoutExpired
    inmediato, sin esperar de verdad) -- debe propagar una Exception legible,
    no un cuelgue ni un traceback crudo."""
    concat_out = tmp_path / "concat.mp4"
    audio_mix = tmp_path / "audio.mp3"
    concat_out.write_bytes(b"fake")
    audio_mix.write_bytes(b"fake")

    # Duraciones validas simuladas (sin depender de ffprobe real) y forzar la
    # rama "video~audio" (copy) para llegar directo al subprocess.run que
    # nos interesa forzar en timeout.
    monkeypatch.setattr(ffmpeg_utils, "ffprobe_duration", lambda p: 10.0)

    def _fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(subprocess, "run", _fake_run)

    start = time.time()
    with pytest.raises(Exception, match="timeout"):
        ffmpeg_utils.final_mux_aligned(str(concat_out), str(audio_mix), str(tmp_path / "out.mp4"), 10.0)
    elapsed = time.time() - start
    assert elapsed < 2.0, "el TimeoutExpired simulado no debe tardar nada en propagarse"


# ── 2. Pipeline completo: un timeout simulado libera el job (no lo cuelga) ──


@pytest.fixture
def _fake_project(tmp_path, monkeypatch):
    """Proyecto minimo (audio + 1 imagen) apuntando a tmp_path, para no tocar
    AppData/jobs real. El contenido de los archivos no importa: subprocess.run
    se mockea antes de que ffmpeg/ffprobe lean nada de verdad."""
    from src.infrastructure.storage import project_repository

    monkeypatch.setattr(project_repository, "get_jobs_dir", lambda: tmp_path / "jobs")
    proj_dir = project_repository.project_dir("proyecto_timeout")
    (proj_dir / "audio").mkdir(parents=True, exist_ok=True)
    (proj_dir / "imagen").mkdir(parents=True, exist_ok=True)
    (proj_dir / "audio" / "audio.mp3").write_bytes(b"fake-audio")
    (proj_dir / "imagen" / "img_00001.jpg").write_bytes(b"fake-image")
    return "proyecto_timeout"


def test_timeout_simulado_en_el_pipeline_libera_el_job_en_vez_de_colgarlo(_fake_project, monkeypatch):
    """subprocess.run mockeado para simular SIEMPRE un ffmpeg/ffprobe colgado
    (TimeoutExpired instantaneo, sin dormir de verdad) desde el primerisimo
    paso del pipeline (leer duracion del audio). El job debe terminar en
    "error" -- nunca quedarse pegado en "procesando" -- y debe hacerlo rapido,
    sin esperar ningun timeout real."""
    from src.domain.services import render_service

    def _fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = render_service.start_render(
        project_name=_fake_project,
        render_mode="images",
        guion="",
        resolucion="640x360",
        modelo="base",
        whisper_backend="local",
        transicion="none",
        trans_dur=0.0,
        movimiento="none",
        shake=False,
        audio_upload=None,
        username=None,
    )
    job_id = result["job_id"]

    deadline = time.time() + 5.0
    job = render_service.get_job(job_id)
    while time.time() < deadline and job.get("estado") == "procesando":
        time.sleep(0.05)
        job = render_service.get_job(job_id)

    assert job.get("estado") == "error", (
        f"el job debio liberarse con estado='error' tras el timeout simulado, quedo: {job}"
    )
    assert "timeout" in (job.get("error") or "").lower()

    # El cancel_event del job no debe quedar huerfano en el registro interno
    # una vez que el pipeline termino (exito, error o cancelacion).
    assert job_id not in render_service._cancel_events


def test_stop_render_cancela_solo_el_job_indicado():
    """stop_render(job_id) debe marcar SOLO ese job como cancelado -- otro job
    "en curso" en paralelo (mismo mecanismo, sin levantar un pipeline real) no
    debe verse afectado."""
    from src.infrastructure.jobs import job_registry
    from src.domain.services import render_service

    job_a, job_b = "job_a_test", "job_b_ajeno_test"
    for jid in (job_a, job_b):
        job_registry.create_job(jid, {"id": jid, "estado": "procesando", "logs": []})
        render_service._register_cancel_event(jid)

    try:
        assert render_service.stop_render(job_a) is True
        assert job_registry.get_job(job_a)["estado"] == "cancelado"

        with render_service._cancel_events_lock:
            ev_b = render_service._cancel_events.get(job_b)
        assert ev_b is not None and not ev_b.is_set(), "stop_render(job_a) NUNCA debe cancelar job_b"
        assert job_registry.get_job(job_b)["estado"] == "procesando"

        assert render_service.stop_render("job-que-no-existe") is False
    finally:
        render_service._forget_cancel_event(job_a)
        render_service._forget_cancel_event(job_b)
