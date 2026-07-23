"""Integracion del bridge de deteccion de sesion de GenTube (gentube_bridge.py +
gentube_animation_service._on_bridge_session). Todo el estado se aisla en tmp_path --
nunca debe tocar la carpeta real de datos del usuario (get_gentube_cookies_dir())."""

import base64
import json

import pytest

from src.domain.services import gentube_animation_service as gas
from src.infrastructure.ai_providers import gentube_bridge, gentube_service


def _fake_jwt(email: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"header.{payload}.sig"


def _cookie_for(email: str) -> str:
    return f"__session={_fake_jwt(email)}; other=1"


def _reset_presence_state():
    # Limpia SOLO el estado (_seen/_sessions/_queue) de la instancia _presence ya
    # existente -- NUNCA reemplazarla por una instancia nueva, porque
    # gentube_animation_service._on_bridge_session se registro como listener de
    # la instancia original al importar el modulo (gentube_bridge.add_session_
    # listener(_on_bridge_session), a nivel de modulo); una instancia nueva
    # tendria _listeners vacio y _on_bridge_session dejaria de dispararse.
    p = gentube_bridge._presence
    p._seen.clear()
    p._sessions.clear()
    p._queue.clear()


@pytest.fixture(autouse=True)
def _isolate_gentube_state(tmp_path, monkeypatch):
    monkeypatch.setattr(gentube_service, "get_gentube_cookies_dir", lambda: tmp_path)
    monkeypatch.setattr(gas, "get_gentube_cookies_dir", lambda: tmp_path)
    # El slot assigner SI se puede resetear reemplazandolo -- no tiene listeners
    # externos registrados sobre el, solo lo usa _on_bridge_session internamente.
    gas._slot_assigner = None
    _reset_presence_state()
    for acc in gas._state["accounts"]:
        acc.update({"logged_in": False, "user": "", "has_cookie": False})
    yield


def test_sesion_detectada_se_escribe_en_el_primer_slot_libre():
    probe = gentube_bridge.set_session_from_cookie(_cookie_for("a@example.com"))
    assert probe["ok"] is True

    assert gentube_service.read_cookie(0) != ""
    assert "a@example.com" not in gentube_service.read_cookie(0)  # el cookie guardado es el header crudo
    status = gas.get_status()
    assert status["accounts"][0]["logged_in"] is True
    assert status["accounts"][0]["user"] == "a@example.com"
    assert status["ext_connected"] == 1


def test_dos_sesiones_distintas_nunca_comparten_slot():
    gentube_bridge.set_session_from_cookie(_cookie_for("a@example.com"))
    gentube_bridge.set_session_from_cookie(_cookie_for("b@example.com"))

    status = gas.get_status()
    assert status["accounts"][0]["user"] == "a@example.com"
    assert status["accounts"][1]["user"] == "b@example.com"


def test_sesion_repetida_no_pisa_un_slot_ya_ocupado_por_otra_cuenta():
    gentube_bridge.set_session_from_cookie(_cookie_for("a@example.com"))
    # Slot 0 ya ocupado a mano (cookie guardada por fuera del bridge, ej. pegada
    # por el usuario) -- una sesion nueva detectada nunca debe pisarlo.
    gentube_service.cookie_path(1).write_text("manual=1", encoding="utf-8")

    gentube_bridge.set_session_from_cookie(_cookie_for("c@example.com"))
    status = gas.get_status()
    assert status["accounts"][0]["user"] == "a@example.com"
    assert status["accounts"][2]["user"] == "c@example.com"  # salta el slot 1 (ocupado a mano)


def test_cookie_invalida_no_registra_nada():
    probe = gentube_bridge.set_session_from_cookie("sin_sesion=1")
    assert probe["ok"] is False
    assert gentube_bridge.connected_accounts() == []
    status = gas.get_status()
    assert all(not a["logged_in"] for a in status["accounts"])


def test_restart_del_backend_reasigna_el_mismo_slot_via_sidecar():
    gentube_bridge.set_session_from_cookie(_cookie_for("a@example.com"))
    idx_before = next(i for i, a in enumerate(gas.get_status()["accounts"]) if a["user"] == "a@example.com")

    # Simula un reinicio del backend: el estado en memoria (presencia + cache
    # hash->slot del assigner) se pierde, pero el sidecar en disco (escrito por
    # write_sidecar) sigue ahi.
    _reset_presence_state()
    gas._slot_assigner = None

    gentube_bridge.set_session_from_cookie(_cookie_for("a@example.com"))
    idx_after = next(i for i, a in enumerate(gas.get_status()["accounts"]) if a["user"] == "a@example.com")
    assert idx_after == idx_before
