"""Multi-cuenta / multi-proyecto de Grok y Qwen (Paso 4 - Generacion de video).

Tres frentes, todos sobre el fix aplicado tras la auditoria de "Network Error"
en las pantallas de Grok/Qwen:

1. qwen_service.list_account_sessions() ya NO hace verificacion de red en vivo
   (test_token) de forma secuencial dentro del endpoint -- responde con el
   estado local (igual que Grok) y dispara la verificacion real en un
   ThreadPoolExecutor de fondo. GET /api/qwen/sesiones debe responder casi
   instantaneo sin importar cuantas cuentas haya en disco ni cuan lenta este
   la red.
2. qwen_animation_service ya no usa un unico dict global (_state) para TODOS
   los proyectos -- el estado esta indexado por proyecto (_batches). Lanzar
   dos lotes de proyectos distintos en paralelo no debe mezclar sus
   log_lines ni sus rutas de imagen/video.
3. grok_animation_service tampoco usa un dict global -- iniciar un batch para
   un proyecto NUEVO no debe matar (.terminate()) el proceso de otro
   proyecto que sigue corriendo.

Todo se simula con dobles de prueba (fake file storage, fake Popen, fake
generate_one) para no depender de Playwright/Chromium ni de red real hacia
grok.com / chat.qwen.ai."""

import threading
import time
from pathlib import Path

import pytest

ACCOUNTS_COUNT = 10


class _FakeFileStorage:
    """Sustituto de un werkzeug FileStorage: solo necesita .save(path)."""

    def __init__(self, content: bytes = b"fake-image-bytes"):
        self._content = content

    def save(self, path: str) -> None:
        Path(path).write_bytes(self._content)


def _images(prefix: str, n: int) -> list[tuple[str, _FakeFileStorage]]:
    return [(f"{prefix}_{i}.jpg", _FakeFileStorage()) for i in range(n)]


# ── 1. GET /api/qwen/sesiones debe responder rapido, sin importar la red ────


@pytest.fixture
def _many_qwen_accounts(tmp_path):
    accounts_dir = tmp_path / "qwen_accounts"
    accounts_dir.mkdir()
    for i in range(ACCOUNTS_COUNT):
        acc = accounts_dir / f"cuenta_{i}"
        acc.mkdir()
        (acc / "token.txt").write_text("token-de-prueba", encoding="utf-8")
    return accounts_dir


def test_qwen_sesiones_responde_rapido_sin_importar_cuentas_en_disco(
    client, login_as, monkeypatch, _many_qwen_accounts
):
    """Antes, list_account_sessions() llamaba test_token() (HTTP real a
    chat.qwen.ai, timeout=15s) de forma SECUENCIAL por cada cuenta con token
    -- con 10 cuentas y la red lenta/inalcanzable, el propio GET /sesiones
    podia tardar hasta 150s, tiempo mas que suficiente para que algo aguas
    abajo cortara la conexion y el frontend viera "Network Error". Ahora la
    verificacion corre en background: el endpoint debe responder casi al
    instante aunque test_token() sea deliberadamente lento."""
    login_as()

    from src.infrastructure.ai_providers import qwen_service

    monkeypatch.setattr(
        "src.domain.services.qwen_animation_service.get_qwen_accounts_dir",
        lambda: _many_qwen_accounts,
    )

    def _slow_test_token(token, cookie_header="", session_meta=None):
        time.sleep(5)
        return True, "ok"

    monkeypatch.setattr(qwen_service, "test_token", _slow_test_token)
    with qwen_service._verify_lock:
        qwen_service._verify_cache.clear()
        qwen_service._verify_inflight = False

    start = time.time()
    resp = client.get("/api/qwen/sesiones")
    elapsed = time.time() - start

    assert resp.status_code == 200
    assert elapsed < 1.0, (
        f"/api/qwen/sesiones tardo {elapsed:.2f}s con {ACCOUNTS_COUNT} cuentas -- "
        "la verificacion de red debe correr en background, nunca bloquear el request"
    )

    body = resp.get_json()
    names_with_token = {f"cuenta_{i}" for i in range(ACCOUNTS_COUNT)}
    returned = {a["name"]: a for a in body["accounts"] if a["name"] in names_with_token}
    assert len(returned) == ACCOUNTS_COUNT
    # Sin verificacion todavia: se muestran optimistamente activas (estado
    # local, como Grok) mientras el ThreadPoolExecutor confirma de fondo.
    assert all(a["active"] for a in returned.values())


# ── 2. Dos proyectos Qwen en paralelo no mezclan logs ni rutas ──────────────


@pytest.fixture(autouse=True)
def _clean_qwen_batches(tmp_path, monkeypatch):
    from src.domain.services import qwen_animation_service as qas
    from src.infrastructure.storage import project_repository

    qas._batches.clear()
    qas._last_project = None
    monkeypatch.setattr(qas, "get_qwen_accounts_dir", lambda: tmp_path / "qwen_accounts")
    monkeypatch.setattr(project_repository, "get_jobs_dir", lambda: tmp_path / "jobs")
    yield
    qas._batches.clear()
    qas._last_project = None


def test_dos_proyectos_qwen_simultaneos_no_mezclan_logs_ni_rutas(monkeypatch):
    """Antes, _state era un unico dict de modulo: lanzar el proyecto B pisaba
    _state["project_dir"]/["images"] del proyecto A mientras el hilo del
    proyecto A seguia corriendo y escribiendo en la MISMA lista de
    log_lines -- el poll de cualquiera de los dos proyectos podia terminar
    leyendo lineas o rutas del otro. Ahora cada proyecto tiene su propio
    _batches[name]."""
    from src.domain.services import qwen_animation_service as qas
    from src.infrastructure.ai_providers import qwen_service

    calls: list[tuple[str, str]] = []
    calls_lock = threading.Lock()

    def _fake_tokens_for_run(accounts_dir):
        return [("cuenta_unica", "TOKEN123", "", {})]

    def _fake_generate_one(
        token, image_path, prompt, size, output_path, timeout_sec=600, cookie_header="", session_meta=None
    ):
        with calls_lock:
            calls.append((str(image_path), str(output_path)))
        # Dormir un poco para maximizar la superposicion real entre los dos
        # batches en paralelo (sin esto, uno podria terminar antes de que el
        # otro arranque y el test dejaria de probar el caso concurrente).
        time.sleep(0.3)
        Path(output_path).write_bytes(b"fake-video-bytes")

    monkeypatch.setattr(qwen_service, "tokens_for_run", _fake_tokens_for_run)
    monkeypatch.setattr(qwen_service, "generate_one", _fake_generate_one)

    result_a = qas.start_batch("proyecto_a", _images("imgA", 2), "prompt A", 2, "1280x720", 30, "16:9")
    result_b = qas.start_batch("proyecto_b", _images("imgB", 2), "prompt B", 2, "1280x720", 30, "16:9")

    deadline = time.time() + 10
    finished_a = finished_b = False
    while time.time() < deadline and not (finished_a and finished_b):
        finished_a = qas.get_log_state(0, "proyecto_a")["finished"]
        finished_b = qas.get_log_state(0, "proyecto_b")["finished"]
        time.sleep(0.05)
    assert finished_a and finished_b, "los dos lotes debieron terminar dentro del timeout"

    log_a = qas.get_log_state(0, "proyecto_a")["lines"]
    log_b = qas.get_log_state(0, "proyecto_b")["lines"]

    assert result_a["project_dir"] != result_b["project_dir"]
    assert any("imgA" in line for line in log_a)
    assert any("imgB" in line for line in log_b)
    assert not any("imgB" in line for line in log_a), (
        f"CRUCE DETECTADO: el log de proyecto_a menciona archivos de proyecto_b: {log_a}"
    )
    assert not any("imgA" in line for line in log_b), (
        f"CRUCE DETECTADO: el log de proyecto_b menciona archivos de proyecto_a: {log_b}"
    )

    dir_a = result_a["project_dir"]
    dir_b = result_b["project_dir"]
    assert len(calls) == 4, f"se esperaban 4 llamadas a generate_one (2 imagenes x 2 proyectos): {calls}"
    for image_path, output_path in calls:
        if "imgA" in image_path:
            assert dir_a in output_path and dir_b not in output_path, (
                f"CRUCE DETECTADO: una imagen de proyecto_a se escribio fuera de su carpeta: {output_path}"
            )
        elif "imgB" in image_path:
            assert dir_b in output_path and dir_a not in output_path, (
                f"CRUCE DETECTADO: una imagen de proyecto_b se escribio fuera de su carpeta: {output_path}"
            )
        else:
            pytest.fail(f"imagen inesperada en generate_one: {image_path}")


def test_qwen_stop_de_un_proyecto_no_detiene_al_otro(monkeypatch):
    """stop(project_name) debe apagar solo el cancel_event de ESE proyecto --
    nunca el de otro batch corriendo en paralelo."""
    from src.domain.services import qwen_animation_service as qas
    from src.infrastructure.ai_providers import qwen_service

    release = threading.Event()

    def _fake_tokens_for_run(accounts_dir):
        return [("cuenta_unica", "TOKEN123", "", {})]

    def _fake_generate_one(
        token, image_path, prompt, size, output_path, timeout_sec=600, cookie_header="", session_meta=None
    ):
        release.wait(timeout=5)
        Path(output_path).write_bytes(b"fake-video-bytes")

    monkeypatch.setattr(qwen_service, "tokens_for_run", _fake_tokens_for_run)
    monkeypatch.setattr(qwen_service, "generate_one", _fake_generate_one)

    qas.start_batch("proyecto_x", _images("imgX", 1), "prompt", 1, "1280x720", 30, "16:9")
    qas.start_batch("proyecto_y", _images("imgY", 1), "prompt", 1, "1280x720", 30, "16:9")

    qas.stop("proyecto_x")

    batch_x = qas._batches["proyecto_x"]
    batch_y = qas._batches["proyecto_y"]
    assert batch_x["cancel_event"].is_set(), "stop() debio marcar el cancel_event de proyecto_x"
    assert not batch_y["cancel_event"].is_set(), "stop('proyecto_x') NUNCA debe cancelar proyecto_y"

    release.set()


# ── 3. Un segundo proyecto de Grok no mata el proceso del primero ──────────


class _FakeStdout:
    def readline(self, *_a, **_kw) -> bytes:
        return b""


class _FakeProc:
    def __init__(self):
        self.pid = id(self)
        self.terminated = False
        self.stdout = _FakeStdout()

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self):
        self.terminated = True


def test_grok_segundo_proyecto_no_mata_proceso_del_primero(tmp_path, monkeypatch):
    """Antes, start_batch() hacia `if _state["proc"]...: _state["proc"].terminate()`
    sin importar de que proyecto era: lanzar animacion para el proyecto B
    mataba el subproceso del proyecto A aunque siguiera corriendo. Ahora solo
    se mata un batch previo DEL MISMO proyecto (reinicio), nunca el de otro."""
    from src.domain.services import grok_animation_service as gas
    from src.infrastructure.ai_providers import grok_process, grok_service
    from src.infrastructure.storage import project_repository

    gas._batches.clear()
    gas._last_project = None
    monkeypatch.setattr(gas, "get_grok_accounts_dir", lambda: tmp_path / "grok_accounts")
    monkeypatch.setattr(project_repository, "get_jobs_dir", lambda: tmp_path / "jobs")
    monkeypatch.setattr(grok_service, "ensure_accounts_setup", lambda accounts_dir, count=10: None)

    procs: list[_FakeProc] = []

    def _fake_spawn_worker(args, cwd):
        p = _FakeProc()
        procs.append(p)
        return p

    monkeypatch.setattr(grok_process, "spawn_worker", _fake_spawn_worker)

    gas.start_batch("proyecto_1", _images("img1", 1), "prompt", 1, "2:3", 6, "480p")
    time.sleep(0.05)
    gas.start_batch("proyecto_2", _images("img2", 1), "prompt", 1, "2:3", 6, "480p")

    assert len(procs) == 2
    assert not procs[0].terminated, "iniciar proyecto_2 NUNCA debe matar el proceso de proyecto_1"
    assert not procs[1].terminated

    assert gas._batches["proyecto_1"]["proc"] is procs[0]
    assert gas._batches["proyecto_2"]["proc"] is procs[1]

    gas._batches.clear()
    gas._last_project = None
