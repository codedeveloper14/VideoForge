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

Todo se simula con dobles de prueba (vibes_bridge mockeado, la cola en memoria que
consulta vibes_bridge.js) para no depender de sesion real ni de una pestaña de
Chrome de verdad."""

import threading
import time
from pathlib import Path

import pytest


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
    from src.infrastructure.ai_providers import vibes_bridge, vibes_client

    monkeypatch.setattr(vibes_client, "load_cookies", lambda idx: [{"name": "meta_session", "value": "fake"}])
    monkeypatch.setattr(vibes_client, "check_session", lambda cookies: True)
    monkeypatch.setattr(vibes_bridge, "connected_accounts", lambda: ["vibes:default"])


def _autoresolve_bridge_jobs(monkeypatch, make_result):
    """Simula vibes_bridge.js: cada enqueue_request() dispara make_result(job) y
    lo entrega via post_result() casi al instante, en un hilo aparte (como haria
    la extension real respondiendo al poll)."""
    from src.infrastructure.ai_providers import vibes_bridge

    def _fake_enqueue(job):
        def _resolve():
            time.sleep(0.05)
            vibes_bridge.post_result(job["requestId"], make_result(job))

        threading.Thread(target=_resolve, daemon=True).start()

    monkeypatch.setattr(vibes_bridge, "enqueue_request", _fake_enqueue)


def test_dos_proyectos_vibes_simultaneos_no_mezclan_logs_ni_progreso(monkeypatch):
    """Dos start_batch() para proyectos distintos, corriendo de verdad en
    paralelo (hilos reales) -- ninguno debe ver logs, out_dir ni contador
    'done' del otro."""
    from src.domain.services import vibes_animation_service as vas

    _mock_session(monkeypatch)

    calls: list[str] = []
    calls_lock = threading.Lock()

    def _make_result(job):
        with calls_lock:
            calls.append(job["prompt"])
        return {"status": 200, "videos": [f"http://fake/{job['requestId']}_0.mp4"] * job["slots"]}

    _autoresolve_bridge_jobs(monkeypatch, _make_result)
    monkeypatch.setattr(
        "src.domain.services.vibes_animation_service.requests.Session.get",
        lambda self, url, timeout=120: type(
            "R", (), {"content": b"fake-video-bytes", "raise_for_status": lambda self: None}
        )(),
    )

    result_a = vas.start_batch("proyecto_a", "prompt de A", 2, 60)
    result_b = vas.start_batch("proyecto_b", "prompt de B", 2, 60)

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

    assert sorted(calls) == ["prompt de A", "prompt de B"]

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
    from src.infrastructure.ai_providers import vibes_bridge

    _mock_session(monkeypatch)

    release = threading.Event()
    monkeypatch.setattr(vibes_bridge, "enqueue_request", lambda job: release.wait(timeout=5))

    vas.start_batch("proyecto_x", "prompt x", 1, 60)
    vas.start_batch("proyecto_y", "prompt y", 1, 60)

    # Esperar a que ambos hilos hayan registrado su batch (arrancan casi
    # instantaneo, antes de bloquearse en enqueue_request).
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
    from src.infrastructure.ai_providers import vibes_bridge

    _mock_session(monkeypatch)

    release = threading.Event()
    monkeypatch.setattr(vibes_bridge, "enqueue_request", lambda job: release.wait(timeout=5))

    vas.start_batch("proyecto_ajeno", "prompt ajeno", 1, 60)
    deadline = time.time() + 5
    while time.time() < deadline and "proyecto_ajeno" not in vas._batches:
        time.sleep(0.02)
    ajeno_cancel = vas._batches["proyecto_ajeno"]["cancel_event"]

    # Dos arranques seguidos del MISMO proyecto ("mio") -- el segundo cancela
    # el cancel_event del primer intento de "mio", pero no debe tocar "ajeno".
    vas.start_batch("mio", "prompt 1", 1, 60)
    first_cancel = vas._batches["mio"]["cancel_event"]
    vas.start_batch("mio", "prompt 2", 1, 60)

    assert first_cancel.is_set(), "reiniciar el propio proyecto debe cancelar su batch anterior"
    assert not ajeno_cancel.is_set(), "reiniciar 'mio' NUNCA debe cancelar 'proyecto_ajeno'"

    release.set()
