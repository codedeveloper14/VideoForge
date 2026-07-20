"""El 409 de /api/flow/run-prompts ("Ya hay una generacion en curso") NO es una
colision entre la extension del navegador (que solo llama a /api/flow/save-cookie,
una ruta sin lock) y Playwright -- es el guard intencional de un unico batch a la
vez sobre state["running"] (ver flow_animation_service.start_run). Estos tests
cubren que ese guard responda de forma ordenada (409 claro, nunca un cuelgue
silencioso) ante peticiones simultaneas, que el candado se libere solo por
inactividad real sin penalizar un batch que sigue progresando, y que el endpoint
de reset manual (/api/flow/reset-lock) lo libere sin esperar el auto-release."""

import threading
import time

import pytest

from src.domain.services import flow_animation_service as fas
from src.infrastructure.ai_providers import flow_service


@pytest.fixture(autouse=True)
def _clean_flow_state(monkeypatch):
    """Aisla el estado global de flow_animation_service entre tests -- start_run()
    dispara un hilo de batch real (_run_batch) si no se lo evita, asi que se
    reemplaza por un stub que no hace nada salvo lo que cada test necesite."""
    with fas.lock:
        fas.state.update(
            running=False,
            step="idle",
            progress=0,
            total=0,
            images_saved=0,
            log=[],
            last_error=None,
            output_dir=None,
            started_at=0.0,
            last_activity=0.0,
        )
    fas._stop_event.clear()
    monkeypatch.setattr(fas, "auto_open_browsers", lambda force=False: None)
    yield
    with fas.lock:
        fas.state.update(running=False, step="idle")
    fas._stop_event.set()


def _start_run_no_thread(monkeypatch, **kwargs):
    """start_run() real, pero con _run_batch (lo que corre DENTRO del hilo que
    lanza start_run) convertido en no-op -- no hay bridge/Playwright en el
    entorno de test. El hilo real de threading.Thread se sigue creando y
    arrancando (no se toca threading.Thread global), solo su target no hace
    nada, asi se puede controlar exactamente cuando "running" se libera."""
    monkeypatch.setattr(fas, "_run_batch", lambda *a, **kw: None)
    return fas.start_run(
        prompts=kwargs.pop("prompts", ["un prompt"]),
        out_dir=kwargs.pop("out_dir", "C:/tmp/flow_test_out"),
        slots=kwargs.pop("slots", 1),
        aspect="IMAGE_ASPECT_RATIO_LANDSCAPE",
        model="NANO_BANANA_2",
        max_retries=1,
        **kwargs,
    )


def test_segunda_llamada_mientras_corre_devuelve_409_ordenado(monkeypatch):
    """Con un batch ya "corriendo" (running=True), una segunda start_run() debe
    fallar con RuntimeError (-> 409 en la ruta) en vez de arrancar un segundo
    batch en paralelo o quedarse esperando en silencio."""
    _start_run_no_thread(monkeypatch)
    assert fas.state["running"] is True

    with pytest.raises(RuntimeError, match="Ya hay una generacion en curso"):
        _start_run_no_thread(monkeypatch, out_dir="C:/tmp/flow_test_out_2")


def test_peticiones_simultaneas_solo_una_gana_el_lock(monkeypatch):
    """Simula el escenario real del reporte: N threads llamando a start_run() al
    mismo tiempo (como si varias pestañas o un doble click dispararan
    /run-prompts a la vez). Exactamente una debe obtener el lock (running=True,
    sin excepcion); el resto debe recibir RuntimeError de forma limpia -- nunca
    dos batches corriendo, nunca una que se quede colgada sin resolver."""
    N = 8
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()
    start_gate = threading.Barrier(N)

    def _attempt(i: int):
        start_gate.wait(timeout=5)
        try:
            _start_run_no_thread(monkeypatch, out_dir=f"C:/tmp/flow_test_out_{i}")
            with outcomes_lock:
                outcomes.append("ok")
        except RuntimeError:
            with outcomes_lock:
                outcomes.append("409")

    threads = [threading.Thread(target=_attempt, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(outcomes) == N, "todas las peticiones debieron resolverse (ninguna quedo colgada)"
    assert outcomes.count("ok") == 1, f"exactamente una peticion debio ganar el lock, gano: {outcomes.count('ok')}"
    assert outcomes.count("409") == N - 1


def test_extension_save_cookie_no_colisiona_con_el_lock_de_run_prompts(monkeypatch, tmp_path):
    """El hallazgo central de la auditoria: la extension solo llama a
    save_account_cookie() (ruta /save-cookie), que NO toca el lock de
    "running" -- debe poder llamarse libremente mientras run-prompts esta
    "corriendo", sin lanzar RuntimeError ni bloquearse."""
    monkeypatch.setattr(flow_service, "get_flow_cookies_dir", lambda: tmp_path)
    monkeypatch.setattr(
        fas.flow_service, "get_session", lambda cookie: {"bearer": "FAKE_BEARER", "email": "test@example.com"}
    )
    _start_run_no_thread(monkeypatch)
    assert fas.state["running"] is True

    result = fas.save_account_cookie(0, "SIDCC=fake-cookie-value-larga-1234567890")
    assert result.get("ok") is not False
    assert fas.state["running"] is True, "save_account_cookie no debe tocar el lock de generacion"


def test_lock_se_libera_solo_por_inactividad_real_no_por_tiempo_transcurrido(monkeypatch):
    """Un batch que sigue logueando actividad (progreso real) no debe liberarse
    solo porque paso mucho tiempo desde que arranco -- el techo antiguo de 30
    minutos fijos mataba tandas largas que seguian trabajando. Solo la falta de
    actividad reciente (batch realmente colgado) debe liberar el lock antes del
    techo absoluto de seguridad."""
    _start_run_no_thread(monkeypatch)
    with fas.lock:
        # "started" hace rato (mucho mas que INACTIVITY_TIMEOUT_SECONDS, bastante
        # menos que MAX_RUN_SECONDS) pero con actividad reciente -- debe seguir vivo.
        fas.state["started_at"] = time.time() - (fas.INACTIVITY_TIMEOUT_SECONDS * 10)
        fas.state["last_activity"] = time.time()  # actividad reciente == sigue vivo

    fas._release_if_stale()
    assert fas.state["running"] is True, "no debe liberarse mientras sigue habiendo actividad reciente"


def test_lock_colgado_sin_actividad_se_libera_automaticamente(monkeypatch):
    """El caso real que causaba el "se queda en esperando": un batch que dejo de
    loguear (colgado de verdad) debe liberar el lock tras INACTIVITY_TIMEOUT_SECONDS
    sin esperar el techo absoluto de 30-60 minutos."""
    _start_run_no_thread(monkeypatch)
    with fas.lock:
        fas.state["started_at"] = time.time() - (fas.INACTIVITY_TIMEOUT_SECONDS + 5)
        fas.state["last_activity"] = time.time() - (fas.INACTIVITY_TIMEOUT_SECONDS + 5)

    fas._release_if_stale()
    assert fas.state["running"] is False
    assert fas.state["last_error"]


def test_reset_lock_endpoint_libera_el_candado_manualmente(monkeypatch):
    """POST /api/flow/reset-lock debe liberar "running" de inmediato, sin esperar
    ningun timeout -- la opcion de "forzar reinicio" que ve el usuario en la UI
    cuando el 409 viene de una sesion anterior colgada."""
    _start_run_no_thread(monkeypatch)
    assert fas.state["running"] is True

    result = fas.reset_lock()
    assert result == {"ok": True, "was_running": True}
    assert fas.state["running"] is False
    assert fas.state["step"] == "idle"

    # Tras el reset, una nueva peticion debe poder arrancar sin 409.
    result2 = _start_run_no_thread(monkeypatch, out_dir="C:/tmp/flow_test_out_after_reset")
    assert result2["ok"] is True


def test_reset_lock_sobre_estado_ya_libre_es_no_op_seguro():
    """Llamar reset-lock cuando no hay nada corriendo no debe romper nada ni
    reportar falsamente que libero un batch activo."""
    assert fas.state["running"] is False
    result = fas.reset_lock()
    assert result == {"ok": True, "was_running": False}
    assert fas.state["running"] is False


def test_run_prompts_route_devuelve_409_no_500_ni_cuelgue(client, login_as, monkeypatch, tmp_path):
    """Prueba de integracion HTTP real: dos POST a /api/flow/run-prompts, el
    segundo mientras el primero "sigue corriendo" -- el segundo debe responder
    409 con un mensaje claro en el body, nunca un 500 ni quedarse sin responder."""
    login_as()
    monkeypatch.setattr(fas, "auto_open_browsers", lambda force=False: None)
    monkeypatch.setattr(fas, "_run_batch", lambda *a, **kw: None)

    payload = {
        "prompts": ["un prompt de prueba"],
        "output_dir": str(tmp_path),
        "slots": 1,
        "browser_mode": "auto",
    }
    resp1 = client.post("/api/flow/run-prompts", json=payload)
    assert resp1.status_code == 200, resp1.get_json()

    resp2 = client.post("/api/flow/run-prompts", json=payload)
    assert resp2.status_code == 409
    body = resp2.get_json()
    assert "en curso" in body.get("error", "")

    resp3 = client.post("/api/flow/reset-lock", json={})
    assert resp3.status_code == 200
    assert resp3.get_json()["was_running"] is True

    resp4 = client.post("/api/flow/run-prompts", json=payload)
    assert resp4.status_code == 200, resp4.get_json()


def test_browser_mode_chrome_no_abre_chromium(monkeypatch):
    """Modo "chrome" (Chrome real, mono-cuenta): no debe forzar la apertura de
    perfiles Chromium -- el usuario conecta su propio Chrome via la extension."""
    calls = []
    monkeypatch.setattr(fas, "auto_open_browsers", lambda force=False: calls.append(force))
    _start_run_no_thread(monkeypatch, auto_open=True, browser_mode="chrome")
    assert calls == [], "modo chrome no debe llamar a auto_open_browsers"


def test_browser_mode_chromium_fuerza_apertura(monkeypatch):
    """Modo "chromium" explicito: debe forzar la apertura de Chromium (force=True)
    aunque ya haya una sesion de Chrome real conectada, para multi-cuenta real."""
    calls = []
    monkeypatch.setattr(fas, "auto_open_browsers", lambda force=False: calls.append(force))
    _start_run_no_thread(monkeypatch, auto_open=True, browser_mode="chromium")
    assert calls == [True]


def test_browser_mode_auto_preserva_comportamiento_previo(monkeypatch):
    """Modo por defecto ("auto"): comportamiento identico al de antes de este
    cambio -- abre Chromium sin forzar (respeta sesiones de Chrome real ya
    conectadas)."""
    calls = []
    monkeypatch.setattr(fas, "auto_open_browsers", lambda force=False: calls.append(force))
    _start_run_no_thread(monkeypatch, auto_open=True, browser_mode="auto")
    assert calls == [False]
