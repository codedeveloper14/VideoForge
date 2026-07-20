"""Multi-proyecto de Vibes (Modulo 04) -- mismo patron que test_video_multiacount.py
(Qwen) y test_flow_multiacount.py (Flow).

Antes, vibes_animation_service.py usaba un unico dict de modulo (_state) para
TODOS los proyectos: lanzar un lote para el proyecto B pisaba _state["project_dir"]/
["total"]/["done"] del proyecto A mientras el hilo de A seguia corriendo y
escribiendo en la MISMA lista de log_lines -- logs y progreso de dos proyectos
distintos quedaban entrelazados en lo que fuera que la UI estuviera polleando, y
stop() paraba lo que fuera que estuviera corriendo sin importar el proyecto.
Ahora el estado esta indexado por proyecto (_batches), igual que ya se hizo en
Qwen/Grok.

Todo se simula con dobles de prueba (vibes_client mockeado) para no depender de
sesion real ni del bridge de la extension de Chrome."""

import threading
import time
from pathlib import Path

import pytest


def _video_params(batch_variation: bool = False) -> dict:
    return {
        "aspect_ratio": "9:16",
        "resolution": "480p",
        "prompt_model": "gemini-2.5-flash",
        "image_model": "midjen-base",
        "video_model": "midjen-short",
        "batch_variation": batch_variation,
    }


@pytest.fixture(autouse=True)
def _clean_vibes_batches(tmp_path, monkeypatch):
    from src.domain.services import vibes_animation_service as vas
    from src.infrastructure.storage import project_repository

    vas._batches.clear()
    vas._last_project = None
    monkeypatch.setattr(project_repository, "get_jobs_dir", lambda: tmp_path / "jobs")
    yield
    vas._batches.clear()
    vas._last_project = None


def _mock_session(monkeypatch):
    from src.infrastructure.ai_providers import vibes_client

    monkeypatch.setattr(vibes_client, "load_cookies", lambda idx: [{"name": "meta_session", "value": "fake"}])
    monkeypatch.setattr(vibes_client, "check_session", lambda cookies: True)
    monkeypatch.setattr(vibes_client, "ensure_project", lambda cookies, idx, log=None: "vibes-proj-fake")


def test_dos_proyectos_vibes_simultaneos_no_mezclan_logs_ni_progreso(monkeypatch):
    """Dos start_batch() para proyectos distintos, corriendo de verdad en
    paralelo (hilos reales) -- ninguno debe ver logs, out_dir ni contador
    'done' del otro."""
    from src.domain.services import vibes_animation_service as vas
    from src.infrastructure.ai_providers import vibes_client

    _mock_session(monkeypatch)

    calls: list[tuple[str, str]] = []
    calls_lock = threading.Lock()

    def _fake_generate(prompt, project_id, out_dir, cookie_list, timeout_sec, slot_id, ref_image, log, **kw):
        with calls_lock:
            calls.append((prompt, out_dir))
        log(f"generando slot {slot_id}")
        # Superposicion real entre los dos batches en paralelo.
        time.sleep(0.3)
        fname = f"vibes_{slot_id}.mp4"
        Path(out_dir, fname).write_bytes(b"fake-video-bytes")
        return {"videos": [fname], "error": None}

    monkeypatch.setattr(vibes_client, "generate_video_via_bridge", _fake_generate)

    result_a = vas.start_batch("proyecto_a", "prompt de A", 2, _video_params(), 60)
    result_b = vas.start_batch("proyecto_b", "prompt de B", 2, _video_params(), 60)

    deadline = time.time() + 10
    finished_a = finished_b = False
    while time.time() < deadline and not (finished_a and finished_b):
        finished_a = vas.get_log_state(0, "proyecto_a")["finished"]
        finished_b = vas.get_log_state(0, "proyecto_b")["finished"]
        time.sleep(0.05)
    assert finished_a and finished_b, "los dos lotes debieron terminar dentro del timeout"

    log_a = vas.get_log_state(0, "proyecto_a")["lines"]
    log_b = vas.get_log_state(0, "proyecto_b")["lines"]

    assert result_a["project_dir"] != result_b["project_dir"]

    # Ningun log de un proyecto debe mencionar la carpeta/salida del otro.
    dir_a, dir_b = result_a["project_dir"], result_b["project_dir"]
    assert not any(dir_b in line for line in log_a), (
        f"CRUCE DETECTADO: el log de proyecto_a menciona la carpeta de proyecto_b: {log_a}"
    )
    assert not any(dir_a in line for line in log_b), (
        f"CRUCE DETECTADO: el log de proyecto_b menciona la carpeta de proyecto_a: {log_b}"
    )

    # Cada generate_video_via_bridge debio escribir SOLO en el out_dir de su
    # propio proyecto -- nunca cruzado.
    assert len(calls) == 4, f"se esperaban 4 llamadas (2 slots x 2 proyectos): {calls}"
    for prompt, out_dir in calls:
        if prompt == "prompt de A":
            assert dir_a in out_dir and dir_b not in out_dir
        elif prompt == "prompt de B":
            assert dir_b in out_dir and dir_a not in out_dir
        else:
            pytest.fail(f"prompt inesperado: {prompt}")

    # Progreso (done/total) via list_videos() -- cada proyecto cuenta SOLO sus
    # propios videos, nunca los del otro.
    videos_a = vas.list_videos("proyecto_a")
    videos_b = vas.list_videos("proyecto_b")
    assert videos_a["total"] == 2 and videos_a["done"] == 2
    assert videos_b["total"] == 2 and videos_b["done"] == 2


def test_vibes_stop_de_un_proyecto_no_detiene_al_otro(monkeypatch):
    """stop(project_name) debe apagar solo el cancel_event de ESE proyecto --
    nunca el de otro batch corriendo en paralelo."""
    from src.domain.services import vibes_animation_service as vas
    from src.infrastructure.ai_providers import vibes_client

    _mock_session(monkeypatch)

    release = threading.Event()

    def _fake_generate(prompt, project_id, out_dir, cookie_list, timeout_sec, slot_id, ref_image, log, **kw):
        release.wait(timeout=5)
        return {"videos": [], "error": None}

    monkeypatch.setattr(vibes_client, "generate_video_via_bridge", _fake_generate)

    vas.start_batch("proyecto_x", "prompt x", 1, _video_params(), 60)
    vas.start_batch("proyecto_y", "prompt y", 1, _video_params(), 60)

    # Esperar a que ambos hilos hayan registrado su batch (arrancan casi
    # instantaneo, antes de bloquearse en _fake_generate).
    deadline = time.time() + 5
    while time.time() < deadline and ("proyecto_x" not in vas._batches or "proyecto_y" not in vas._batches):
        time.sleep(0.02)

    vas.stop("proyecto_x")

    batch_x = vas._batches["proyecto_x"]
    batch_y = vas._batches["proyecto_y"]
    assert batch_x["cancel_event"].is_set(), "stop() debio marcar el cancel_event de proyecto_x"
    assert not batch_y["cancel_event"].is_set(), "stop('proyecto_x') NUNCA debe cancelar proyecto_y"

    release.set()


def test_vibes_segundo_batch_mismo_proyecto_no_afecta_a_otro_proyecto(monkeypatch):
    """Reiniciar un batch para el MISMO proyecto puede cancelar su propio lote
    anterior (reinicio legitimo), pero jamas el de un proyecto distinto que
    siga corriendo en paralelo."""
    from src.domain.services import vibes_animation_service as vas
    from src.infrastructure.ai_providers import vibes_client

    _mock_session(monkeypatch)

    release = threading.Event()

    def _fake_generate(prompt, project_id, out_dir, cookie_list, timeout_sec, slot_id, ref_image, log, **kw):
        release.wait(timeout=5)
        return {"videos": [], "error": None}

    monkeypatch.setattr(vibes_client, "generate_video_via_bridge", _fake_generate)

    vas.start_batch("proyecto_ajeno", "prompt ajeno", 1, _video_params(), 60)
    deadline = time.time() + 5
    while time.time() < deadline and "proyecto_ajeno" not in vas._batches:
        time.sleep(0.02)
    ajeno_cancel = vas._batches["proyecto_ajeno"]["cancel_event"]

    # Dos arranques seguidos del MISMO proyecto ("mio") -- el segundo cancela
    # el cancel_event del primer intento de "mio", pero no debe tocar "ajeno".
    vas.start_batch("mio", "prompt 1", 1, _video_params(), 60)
    first_cancel = vas._batches["mio"]["cancel_event"]
    vas.start_batch("mio", "prompt 2", 1, _video_params(), 60)

    assert first_cancel.is_set(), "reiniciar el propio proyecto debe cancelar su batch anterior"
    assert not ajeno_cancel.is_set(), "reiniciar 'mio' NUNCA debe cancelar 'proyecto_ajeno'"

    release.set()
