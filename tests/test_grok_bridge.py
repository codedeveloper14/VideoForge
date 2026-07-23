"""Integracion del bridge de deteccion de sesion de Grok (grok_session_bridge.py +
grok_animation_service._on_bridge_session). Todo el estado se aisla en tmp_path --
nunca debe tocar la carpeta real de datos del usuario (get_grok_accounts_dir())."""

import json
import threading

import pytest

from src.domain.services import grok_animation_service as gas
from src.infrastructure.ai_providers import grok_service, grok_session_bridge


def _cookies(sso_value: str) -> list[dict]:
    return [
        {"name": "sso", "value": sso_value, "httpOnly": True, "secure": True},
        {"name": "sso-rw", "value": sso_value, "httpOnly": True, "secure": True},
        {"name": "cf_clearance", "value": "cf123", "httpOnly": False, "secure": True},
    ]


def _reset_presence_state():
    # Igual que en test_gentube_bridge.py: limpiar el estado de la instancia
    # existente, nunca reemplazarla -- _on_bridge_session ya esta registrado como
    # listener de ESA instancia desde el import del modulo.
    p = grok_session_bridge._presence
    p._seen.clear()
    p._sessions.clear()
    p._queue.clear()


@pytest.fixture(autouse=True)
def _isolate_grok_state(tmp_path, monkeypatch):
    monkeypatch.setattr(gas, "get_grok_accounts_dir", lambda: tmp_path)
    gas._slot_assigner = None
    _reset_presence_state()
    yield


def test_sesion_detectada_se_escribe_en_cookies_auto_json_formato_correcto():
    result = grok_session_bridge.set_session_from_cookies(_cookies("SSO_A"))
    assert result["ok"] is True

    accounts_dir = gas.get_grok_accounts_dir()
    ck_file = accounts_dir / "account_1" / "cookies_auto.json"
    assert ck_file.is_file()
    saved = json.loads(ck_file.read_text())
    names = {c["name"] for c in saved}
    assert {"sso", "sso-rw", "cf_clearance"} <= names
    assert all(c["domain"] == ".grok.com" and c["path"] == "/" for c in saved)

    sessions = grok_service.list_account_sessions(accounts_dir)
    row = next(s for s in sessions if s["name"] == "account_1")
    assert row["active"] is True


def test_dos_sesiones_distintas_nunca_comparten_slot():
    grok_session_bridge.set_session_from_cookies(_cookies("SSO_A"))
    grok_session_bridge.set_session_from_cookies(_cookies("SSO_B"))

    accounts_dir = gas.get_grok_accounts_dir()
    assert (accounts_dir / "account_1" / "cookies_auto.json").is_file()
    assert (accounts_dir / "account_2" / "cookies_auto.json").is_file()
    ck1 = json.loads((accounts_dir / "account_1" / "cookies_auto.json").read_text())
    ck2 = json.loads((accounts_dir / "account_2" / "cookies_auto.json").read_text())
    assert {c["value"] for c in ck1 if c["name"] == "sso"} == {"SSO_A"}
    assert {c["value"] for c in ck2 if c["name"] == "sso"} == {"SSO_B"}


def test_slot_ya_ocupado_en_disco_nunca_se_pisa():
    accounts_dir = gas.get_grok_accounts_dir()
    grok_service.ensure_accounts_setup(accounts_dir)
    manual = accounts_dir / "account_1" / "cookies_auto.json"
    manual.write_text(json.dumps([{"name": "sso", "value": "MANUAL"}]), encoding="utf-8")

    grok_session_bridge.set_session_from_cookies(_cookies("SSO_NUEVA"))

    assert json.loads(manual.read_text())[0]["value"] == "MANUAL"
    ck2 = json.loads((accounts_dir / "account_2" / "cookies_auto.json").read_text())
    assert {c["value"] for c in ck2 if c["name"] == "sso"} == {"SSO_NUEVA"}


def test_cookies_sin_sso_no_registran_nada():
    result = grok_session_bridge.set_session_from_cookies([{"name": "cf_clearance", "value": "x"}])
    assert result["ok"] is False
    assert grok_session_bridge.connected_accounts() == []
    accounts_dir = gas.get_grok_accounts_dir()
    grok_service.ensure_accounts_setup(accounts_dir)
    assert not (accounts_dir / "account_1" / "cookies_auto.json").exists()


def test_cuenta_preexistente_sin_sidecar_no_se_duplica_al_detectarse_por_bridge():
    # Simula cookies_auto.json guardado ANTES de que existiera el bridge (login
    # manual viejo, login_account_managed), SIN sidecar hash->slot -- mismo sso
    # que la sesion recien detectada. Es el escenario real reportado en
    # produccion: una sola sesion de Chrome terminaba mostrando 2 cuentas.
    accounts_dir = gas.get_grok_accounts_dir()
    grok_service.ensure_accounts_setup(accounts_dir)
    (accounts_dir / "account_1" / "cookies_auto.json").write_text(
        json.dumps(_cookies("SSO_A")), encoding="utf-8"
    )

    grok_session_bridge.set_session_from_cookies(_cookies("SSO_A"))

    assert not (accounts_dir / "account_2" / "cookies_auto.json").exists()
    ck1 = json.loads((accounts_dir / "account_1" / "cookies_auto.json").read_text())
    assert {c["value"] for c in ck1 if c["name"] == "sso"} == {"SSO_A"}


def test_cuenta_preexistente_con_sso_distinto_si_crea_cuenta_nueva():
    # Contraste con el test anterior: si el sso de la cookie preexistente es
    # REALMENTE distinto (otra cuenta, o una sesion vieja/expirada), no hay que
    # fusionarlas -- deben quedar en slots separados.
    accounts_dir = gas.get_grok_accounts_dir()
    grok_service.ensure_accounts_setup(accounts_dir)
    (accounts_dir / "account_1" / "cookies_auto.json").write_text(
        json.dumps(_cookies("SSO_VIEJA")), encoding="utf-8"
    )

    grok_session_bridge.set_session_from_cookies(_cookies("SSO_A"))

    ck2 = json.loads((accounts_dir / "account_2" / "cookies_auto.json").read_text())
    assert {c["value"] for c in ck2 if c["name"] == "sso"} == {"SSO_A"}


def test_detecciones_concurrentes_de_la_misma_cuenta_nunca_duplican_carpeta():
    """Reproduce el bug real de produccion (2026-07-23): una cuenta ya logueada
    ANTES de que existiera el bridge (sin sidecar), detectada muchas veces casi
    en simultaneo, nunca debe terminar ocupando mas de una carpeta."""
    accounts_dir = gas.get_grok_accounts_dir()
    grok_service.ensure_accounts_setup(accounts_dir)
    (accounts_dir / "account_1" / "cookies_auto.json").write_text(
        json.dumps(_cookies("SSO_A")), encoding="utf-8"
    )

    def _fire():
        grok_session_bridge.set_session_from_cookies(_cookies("SSO_A"))

    threads = [threading.Thread(target=_fire) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    active = [
        s for s in grok_service.list_account_sessions(accounts_dir) if s["active"]
    ]
    assert len(active) == 1
    assert active[0]["name"] == "account_1"


def test_restart_del_backend_reasigna_el_mismo_slot_via_sidecar():
    grok_session_bridge.set_session_from_cookies(_cookies("SSO_A"))
    accounts_dir = gas.get_grok_accounts_dir()
    before = json.loads((accounts_dir / "account_1" / "cookies_auto.json").read_text())

    _reset_presence_state()
    gas._slot_assigner = None

    grok_session_bridge.set_session_from_cookies(_cookies("SSO_A"))
    # Sigue en account_1 (mismo hash -> mismo slot via sidecar), no crea account_2.
    assert not (accounts_dir / "account_2" / "cookies_auto.json").exists()
    after = json.loads((accounts_dir / "account_1" / "cookies_auto.json").read_text())
    assert before == after
