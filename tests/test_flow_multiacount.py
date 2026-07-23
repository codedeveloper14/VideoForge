"""Integracion multi-cuenta de Flow.

Dos frentes:

1. _bridge_generate() nunca cruza el trabajo de una cuenta con el canal/bearer de
   otra, ni siquiera cuando el WS de la cuenta asignada esta muerto y hay otra cuenta
   sana conectada al mismo bridge.
2. _assign_slot_for_hash() nunca deja que dos account_hash distintos terminen
   compartiendo el mismo indice de slot (0-9) -- ni por una condicion de carrera al
   registrar dos cuentas nuevas casi al mismo tiempo (p. ej. al reiniciar la app con
   varias extensiones reconectando a la vez), ni por sobrecupo cuando ya hay
   NUM_ACCOUNTS sesiones en disco.

Todo se simula registrando "perfiles Playwright" falsos directamente en el estado de
flow_bridge/flow_animation_service (sin Chromium ni sockets reales), tal como lo
haria el handler real de start_ws_server al recibir un "register" de la extension."""

import json
import threading
import time

import pytest

from src.domain.services import flow_animation_service as fas
from src.infrastructure.ai_providers import flow_bridge, flow_service

ACC0 = "flow:cuenta0"
ACC1 = "flow:cuenta1"


class FakeWSClient:
    """Sustituto de un socket de extension real. send() imita lo que hace el
    Chromium de esa cuenta: recibe el "generate", y responde de inmediato con un
    resultado que declara CON QUE cuenta y CON QUE bearer se proceso -- eso es lo
    que el test verifica que nunca sea otra cuenta distinta a la asignada."""

    def __init__(self, account_hash: str, bearer: str, fail_send: bool = False):
        self.account_hash = account_hash
        self.bearer = bearer
        self.fail_send = fail_send
        self.received: list[dict] = []

    def send(self, raw: str) -> None:
        if self.fail_send:
            raise ConnectionError("socket muerto (simulado)")
        msg = json.loads(raw)
        self.received.append(msg)
        for req in msg.get("requests", []):
            self._respond(req)

    def _respond(self, req: dict) -> None:
        result = {
            "requestId": req["requestId"],
            "status": 200,
            "body": json.dumps({"media": [{"image": {"generatedImage": {"fifeUrl": "http://fake/img.png"}}}]}),
            "processed_by": self.account_hash,
            "bearer_seen": req.get("bearer"),
        }
        flow_bridge._presence.post_result(req["requestId"], result)


@pytest.fixture(autouse=True)
def _clean_bridge_state(monkeypatch):
    # start_bridge() intenta bindear sockets reales (5556/5557) -- no lo queremos en
    # un test que solo ejercita el ruteo interno del bridge.
    monkeypatch.setattr(flow_bridge, "start_bridge", lambda log: None)
    with flow_bridge._ws_clients_lock:
        flow_bridge._ws_clients.clear()
    flow_bridge._presence.clear_queue()
    with flow_bridge._presence._r_lock:
        flow_bridge._presence._results.clear()
        flow_bridge._presence._r_events.clear()
    with flow_bridge._bearer_cache_lock:
        flow_bridge._bearer_cache.clear()
    with flow_bridge._presence._seen_lock:
        flow_bridge._presence._seen.clear()
    yield
    with flow_bridge._ws_clients_lock:
        flow_bridge._ws_clients.clear()
    flow_bridge._presence.clear_queue()


def test_generaciones_paralelas_nunca_se_cruzan_entre_cuentas():
    """Cuenta 0 y Cuenta 1 conectadas y sanas a la vez -- cada request debe resolverse
    con el WS y el bearer de su propia cuenta, nunca con los de la otra."""
    ws0 = FakeWSClient(ACC0, "BEARER_0")
    ws1 = FakeWSClient(ACC1, "BEARER_1")
    with flow_bridge._ws_clients_lock:
        flow_bridge._ws_clients[ACC0] = ws0
        flow_bridge._ws_clients[ACC1] = ws1

    results: dict[int, dict] = {}

    def _run(idx: int, account_hash: str, bearer: str):
        results[idx] = fas._bridge_generate(
            json.dumps({"prompt": f"prompt-{idx}"}),
            bearer,
            "https://fake/url",
            account_hash=account_hash,
            timeout=10,
        )

    t0 = threading.Thread(target=_run, args=(0, ACC0, "BEARER_0"))
    t1 = threading.Thread(target=_run, args=(1, ACC1, "BEARER_1"))
    t0.start()
    t1.start()
    t0.join(timeout=15)
    t1.join(timeout=15)

    assert results[0]["processed_by"] == ACC0
    assert results[0]["bearer_seen"] == "BEARER_0"
    assert results[1]["processed_by"] == ACC1
    assert results[1]["bearer_seen"] == "BEARER_1"

    assert len(ws0.received) == 1, "la Cuenta 0 debio recibir exactamente 1 request"
    assert len(ws1.received) == 1, "la Cuenta 1 debio recibir exactamente 1 request"
    for msg in ws0.received:
        for r in msg["requests"]:
            assert r["bearer"] == "BEARER_0"
            assert r.get("account_hash", ACC0) == ACC0
    for msg in ws1.received:
        for r in msg["requests"]:
            assert r["bearer"] == "BEARER_1"
            assert r.get("account_hash", ACC1) == ACC1


def test_websocket_muerto_no_delega_a_otra_cuenta_conectada():
    """El caso que rompia el aislamiento: la Cuenta 0 tiene el WS muerto justo cuando
    llega su generacion, y la Cuenta 1 esta sana y conectada al mismo bridge. La
    request de la Cuenta 0 NUNCA debe llegar al socket/bearer de la Cuenta 1 -- debe
    quedarse encolada para polling HTTP bajo su propio account_hash y, si nadie la
    atiende, expirar en timeout limpio (RuntimeError), sin resultado falso."""
    ws0_dead = FakeWSClient(ACC0, "BEARER_0", fail_send=True)
    ws1_alive = FakeWSClient(ACC1, "BEARER_1")
    with flow_bridge._ws_clients_lock:
        flow_bridge._ws_clients[ACC0] = ws0_dead
        flow_bridge._ws_clients[ACC1] = ws1_alive

    outcome: dict = {}

    def _run():
        try:
            fas._bridge_generate(
                json.dumps({"prompt": "no-debe-cruzarse"}),
                "BEARER_0",
                "https://fake/url",
                account_hash=ACC0,
                timeout=3,
            )
        except RuntimeError as exc:
            outcome["error"] = str(exc)

    t = threading.Thread(target=_run)
    t.start()

    # Mientras la request de la Cuenta 0 sigue "en vuelo" (WS muerto -> debio caer al
    # polling HTTP de SU PROPIA cuenta), la Cuenta 1 no debe haber visto nada.
    time.sleep(1.0)
    assert ws1_alive.received == [], "CRUCE DETECTADO: la Cuenta 1 proceso una request asignada a la Cuenta 0"

    with flow_bridge._presence._q_lock:
        queued = list(flow_bridge._presence._queue)
    assert len(queued) == 1
    assert queued[0]["account_hash"] == ACC0
    assert queued[0]["bearer"] == "BEARER_0"

    with flow_bridge._ws_clients_lock:
        assert ACC0 not in flow_bridge._ws_clients, "ws_push debe limpiar el socket muerto"

    t.join(timeout=6)
    assert outcome.get("error"), "debio expirar en timeout limpio, sin delegar a otra cuenta"
    assert ws1_alive.received == [], "la Cuenta 1 no debio recibir nada durante todo el ciclo"


# ── _assign_slot_for_hash(): el mapeo hash -> indice de slot fisico ──────────────


@pytest.fixture(autouse=True)
def _clean_slot_assignment_state(tmp_path, monkeypatch):
    """Aisla _hash_to_idx (memoria) y los sidecars account_N.bridge.json (disco) de
    cada test -- si dos tests comparten estado, uno podria "heredar" el indice que
    otro ya reservo y el test dejaria de probar lo que dice probar."""
    fas._hash_to_idx.clear()
    monkeypatch.setattr(flow_service, "load_cookie", lambda idx: "")
    # fas importo get_flow_cookies_dir con "from ... import" -- hay que parchear el
    # nombre donde se USA (fas.get_flow_cookies_dir), no en su modulo de origen.
    monkeypatch.setattr(fas, "get_flow_cookies_dir", lambda: tmp_path)
    yield
    fas._hash_to_idx.clear()


def test_dos_cuentas_nuevas_simultaneas_nunca_comparten_indice():
    """Condicion de carrera real: dos account_hash JAMAS vistos antes (sin sidecar en
    disco todavia) se registran practicamente al mismo tiempo -- exactamente lo que
    pasa al reiniciar la app con varias extensiones reconectando a la vez. Ninguna
    combinacion de threads debe terminar con las dos cuentas apuntando al mismo idx."""
    hashes = [f"flow:concurrente{i}" for i in range(8)]
    assigned: dict[str, int] = {}
    assigned_lock = threading.Lock()
    start_gate = threading.Barrier(len(hashes))

    def _register(h: str):
        start_gate.wait(timeout=5)  # maximizar la superposicion real entre threads
        idx = fas._assign_slot_for_hash(h)
        with assigned_lock:
            assigned[h] = idx

    threads = [threading.Thread(target=_register, args=(h,)) for h in hashes]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(assigned) == len(hashes)
    assert None not in assigned.values(), "hay cupo de sobra (10 slots, 8 cuentas) - ninguna debio quedar sin slot"

    idx_values = list(assigned.values())
    assert len(idx_values) == len(set(idx_values)), (
        f"CRUCE DETECTADO: dos hashes distintos comparten el mismo indice de slot: {assigned}"
    )

    # Cada hash debe seguir resolviendo al MISMO indice en llamadas posteriores
    # (estabilidad entre "reinicios" simulados por llamadas repetidas).
    for h, idx in assigned.items():
        assert fas._assign_slot_for_hash(h) == idx


def test_sobrecupo_nunca_alias_una_cuenta_nueva_sobre_un_slot_ocupado():
    """Con los NUM_ACCOUNTS slots ya ocupados por cuentas distintas, una cuenta 11
    (nunca vista) no debe recibir por modulo el indice de otra cuenta ya asignada --
    debe rechazarse (None) en vez de pisar el sidecar de la cuenta que ya esta ahi."""
    for i in range(flow_service.NUM_ACCOUNTS):
        h = f"flow:llena{i}"
        idx = fas._assign_slot_for_hash(h)
        assert idx == i

    overflow_idx = fas._assign_slot_for_hash("flow:cuenta_de_mas")
    assert overflow_idx is None, "sin slots libres debe rechazar la cuenta, nunca reusar un indice ocupado"

    # Las 10 cuentas originales deben seguir intactas, cada una en su propio indice.
    for i in range(flow_service.NUM_ACCOUNTS):
        assert fas._assign_slot_for_hash(f"flow:llena{i}") == i


def test_on_bridge_session_no_pisa_sidecar_ajeno_en_sobrecupo():
    """Extremo a extremo: _on_bridge_session() con NUM_ACCOUNTS cuentas ya
    persistidas en disco no debe escribir la sesion de una cuenta 11 en el sidecar
    de ninguna de las 10 existentes."""
    for i in range(flow_service.NUM_ACCOUNTS):
        fas._on_bridge_session(f"flow:persistida{i}", f"user{i}@test.com", f"BEARER_{i}")

    saved_before = {i: fas._load_bridge_session(i) for i in range(flow_service.NUM_ACCOUNTS)}
    for i, data in saved_before.items():
        assert data["account_hash"] == f"flow:persistida{i}"

    fas._on_bridge_session("flow:cuenta_de_mas", "extra@test.com", "BEARER_EXTRA")

    for i in range(flow_service.NUM_ACCOUNTS):
        data_after = fas._load_bridge_session(i)
        assert data_after == saved_before[i], (
            f"sidecar del slot {i} fue sobreescrito por la cuenta de sobrecupo"
        )


def test_sidecar_huerfano_pre_migracion_se_autolimpia_y_libera_el_slot():
    """Reproduce el caso real encontrado en produccion: un sidecar de ANTES del fix
    que agrego el prefijo "flow:" al hash (mismo djb2, sin prefijo) queda huerfano en
    disco -- la extension y flow_service.account_hash() ya solo emiten el formato con
    prefijo, asi que ese hash nunca vuelve a conectarse. Sin autolimpieza, ese slot
    queda "ocupado" para siempre y la misma cuenta real aparece duplicada en la UI
    (una vez con el sidecar viejo huerfano, otra con el nuevo correcto)."""
    idx = 2
    stale_path = fas._bridge_session_path(idx)
    stale_path.write_text(
        json.dumps({"account_hash": "c6538308", "email": "igabymontilla@gmail.com", "bearer": "OLD", "ts": 1.0}),
        encoding="utf-8",
    )

    # Leer el sidecar huerfano debe descartarlo (formato sin prefijo == pre-migracion)
    # y autolimpiarlo del disco -- check_accounts() no debe seguir reportandolo como
    # cuenta conectada.
    assert fas._load_bridge_session(idx) is None
    assert not stale_path.is_file(), "el sidecar huerfano debio borrarse solo al leerlo"

    # El slot debe quedar realmente libre: NUM_ACCOUNTS cuentas nuevas (formato
    # correcto, prefijo "flow:") deben poder ocupar los 10 slots sin que ninguna se
    # quede sin indice -- si el huerfano siguiera "ocupando" el slot 2, solo habria
    # 9 libres para 10 cuentas nuevas y la ultima recibiria None.
    assigned = [fas._assign_slot_for_hash(f"flow:nueva{i}") for i in range(flow_service.NUM_ACCOUNTS)]
    assert None not in assigned, "el slot huerfano sigue bloqueado -- solo aparecen 9 libres, no 10"
    assert len(set(assigned)) == flow_service.NUM_ACCOUNTS
    assert idx in assigned, "el slot 2 (liberado del huerfano) debio quedar disponible de nuevo"


def test_check_accounts_no_muestra_la_misma_cuenta_duplicada_por_sidecar_viejo():
    """Extremo a extremo con el escenario real: slot 2 = sidecar huerfano
    pre-migracion (mismo email, hash sin prefijo), slot 3 = sesion actual correcta
    (mismo email, hash con prefijo). check_accounts() no debe mostrar la cuenta 2
    como conectada -- solo debe quedar UNA entrada real para igabymontilla@gmail.com."""
    fas._bridge_session_path(2).write_text(
        json.dumps({"account_hash": "c6538308", "email": "igabymontilla@gmail.com", "bearer": "OLD", "ts": 1.0}),
        encoding="utf-8",
    )
    fas._bridge_session_path(3).write_text(
        json.dumps(
            {"account_hash": "flow:c6538308", "email": "igabymontilla@gmail.com", "bearer": "NEW", "ts": 2.0}
        ),
        encoding="utf-8",
    )
    # El slot 3 esta realmente conectado ahora mismo (bearer fresco en cache) --
    # sin esto, ninguna de las dos entradas mostraria "ok" desde el fix de
    # liveness, y el test dejaria de probar la duplicacion que le da nombre.
    flow_bridge.set_cached_bearer("flow:c6538308", "NEW", "igabymontilla@gmail.com")

    accounts = fas.check_accounts()

    connected_emails = [a["email"] for a in accounts if a["ok"]]
    assert connected_emails.count("igabymontilla@gmail.com") == 1, (
        f"la cuenta aparece duplicada como conectada: {connected_emails}"
    )
    assert accounts[2]["ok"] is False, "el slot con el sidecar huerfano ya no debe reportarse como conectado"
    assert accounts[3]["ok"] is True
    assert accounts[3]["email"] == "igabymontilla@gmail.com"


def test_check_accounts_sidecar_valido_pero_sin_conexion_viva_no_se_muestra_conectada():
    """Caso real reportado en produccion: la sesion se guardo en el sidecar hace
    rato (el navegador estuvo conectado en algun momento), pero AHORA MISMO no hay
    WS activo, ni HTTP reciente, ni bearer fresco -- el navegador ya no esta. La
    tarjeta de la cuenta no debe decir "conectado": tiene que coincidir con lo que
    ve flow_bridge (el aviso "sin cuentas conectadas" de arriba del panel y el
    motor de generacion), o el usuario ve "conectado" arriba y "sin cuentas" abajo
    a la vez, y el boton de generar no hace nada aunque la tarjeta diga que si."""
    fas._bridge_session_path(4).write_text(
        json.dumps({"account_hash": "flow:desconectada", "email": "vieja@test.com", "bearer": "OLD", "ts": 1.0}),
        encoding="utf-8",
    )

    accounts = fas.check_accounts()

    assert accounts[4]["ok"] is False, "sidecar sin conexion viva no debe reportarse como conectado"
    assert "flow:desconectada" not in flow_bridge.get_connected_accounts()
