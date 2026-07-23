import base64
import json

from src.core.config import config
from src.domain.services import auth_service


def test_hash_and_verify_password_roundtrip():
    hashed = auth_service.hash_password("mi-clave-super-secreta")
    assert auth_service.verify_password("mi-clave-super-secreta", hashed)


def test_verify_password_rechaza_clave_incorrecta():
    hashed = auth_service.hash_password("clave-correcta")
    assert not auth_service.verify_password("clave-incorrecta", hashed)


def test_verify_password_con_hash_none_es_falso():
    assert not auth_service.verify_password("cualquiera", None)


def test_verify_password_compatibilidad_sha256_legacy():
    # Formato heredado (fallback cuando bcrypt no estaba disponible).
    salt = "videoforge_salt_2024_"
    import hashlib

    legacy_hash = "sha256:" + hashlib.sha256((salt + "clave123").encode()).hexdigest()
    assert auth_service.verify_password("clave123", legacy_hash)
    assert not auth_service.verify_password("otra-clave", legacy_hash)


def test_make_and_verify_token_roundtrip():
    token = auth_service.make_token("usuario_de_prueba")
    assert auth_service.verify_token(token) == "usuario_de_prueba"


def test_verify_token_rechaza_firma_alterada():
    token = auth_service.make_token("usuario_de_prueba")
    encoded, sig = token.rsplit(".", 1)
    tampered = f"{encoded}.{'0' * len(sig)}"
    assert auth_service.verify_token(tampered) is None


def test_verify_token_rechaza_payload_expirado():
    payload = json.dumps({"u": "usuario_x", "exp": 0, "boot": auth_service._SERVER_BOOT})
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = auth_service._sign(encoded, config.app_secret_key)
    expired_token = f"{encoded}.{sig}"
    assert auth_service.verify_token(expired_token) is None


def test_verify_token_basura_no_rompe():
    assert auth_service.verify_token("esto-no-es-un-token-valido") is None
    assert auth_service.verify_token("") is None


def test_is_locked_out_y_register_fail():
    ip = "203.0.113.1-test-auth-service"
    auth_service.clear_fails(ip)
    try:
        locked, _ = auth_service.is_locked_out(ip)
        assert not locked

        for _ in range(config.max_failed_login_attempts):
            auth_service.register_fail(ip)

        locked, remaining = auth_service.is_locked_out(ip)
        assert locked
        assert remaining > 0
    finally:
        auth_service.clear_fails(ip)
