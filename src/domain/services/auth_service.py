import base64
import hashlib
import hmac
import json
import tempfile
import threading
import time
from pathlib import Path

from src.core.config import config
from src.infrastructure.storage import user_repository
from src.utils.logger import get_logger

logger = get_logger(__name__)

SESSION_COOKIE = "vf_session"

# ─────────────────────────────────────────────────────────────────
# BOOT EPOCH — invalida todas las sesiones previas al reiniciar,
# salvo que el reinicio ocurra dentro de la misma ventana de sesion.
# ─────────────────────────────────────────────────────────────────
_BOOT_FILE = Path(tempfile.gettempdir()) / "vf_server_boot.epoch"


def _load_or_create_server_boot() -> int:
    try:
        stored = _BOOT_FILE.read_text().strip().split(":")
        epoch_val = int(stored[0])
        epoch_ts = float(stored[1]) if len(stored) > 1 else 0
        if time.time() - epoch_ts < config.session_minutes * 60:
            return epoch_val
        raise ValueError("epoch expirado")
    except Exception:
        boot = int(time.time())
        try:
            _BOOT_FILE.write_text(f"{boot}:{time.time()}")
        except Exception:
            pass
        return boot


_SERVER_BOOT = _load_or_create_server_boot()

# ─────────────────────────────────────────────────────────────────
# Lockout por intentos fallidos de login
# ─────────────────────────────────────────────────────────────────
_failed_attempts: dict[str, dict] = {}
_lock = threading.Lock()


def is_locked_out(ip: str) -> tuple[bool, int]:
    with _lock:
        data = _failed_attempts.get(ip)
        if not data:
            return False, 0
        if time.time() < data.get("until", 0):
            return True, int(data["until"] - time.time())
        _failed_attempts.pop(ip, None)
        return False, 0


def register_fail(ip: str) -> None:
    with _lock:
        data = _failed_attempts.setdefault(ip, {"count": 0, "until": 0})
        data["count"] += 1
        if data["count"] >= config.max_failed_login_attempts:
            data["until"] = time.time() + config.lockout_seconds
            data["count"] = 0


def clear_fails(ip: str) -> None:
    with _lock:
        _failed_attempts.pop(ip, None)


# ─────────────────────────────────────────────────────────────────
# Password hashing
# ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        salt = "videoforge_salt_2024_"
        return "sha256:" + hashlib.sha256((salt + password).encode()).hexdigest()


def verify_password(plain: str, hashed: str | None) -> bool:
    try:
        if not hashed:
            return False
        if hashed.startswith("sha256:"):
            salt = "videoforge_salt_2024_"
            expected = "sha256:" + hashlib.sha256((salt + plain).encode("utf-8")).hexdigest()
            return hmac.compare_digest(hashed, expected)
        try:
            import bcrypt
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except ImportError:
            logger.warning("bcrypt no disponible - usando sha256 fallback")
            salt = "videoforge_salt_2024_"
            expected = "sha256:" + hashlib.sha256((salt + plain).encode("utf-8")).hexdigest()
            return hmac.compare_digest(hashed, expected)
    except Exception as exc:
        logger.error("verify_password error: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────
# Sesiones — token deslizante firmado con HMAC-SHA256
# ─────────────────────────────────────────────────────────────────

def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(username: str) -> str:
    """Token firmado que incluye 'boot' para invalidar tokens de arranques anteriores."""
    expires = int(time.time() + config.session_minutes * 60)
    payload = json.dumps({"u": username, "exp": expires, "boot": _SERVER_BOOT})
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"{encoded}.{_sign(encoded, config.app_secret_key)}"


def verify_token(token: str) -> str | None:
    try:
        encoded, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(sig, _sign(encoded, config.app_secret_key)):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded).decode())
        if payload.get("boot") != _SERVER_BOOT:
            return None
        if payload.get("exp", 0) < time.time():
            return None
        return payload.get("u")
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────
# Autenticacion / registro
# ─────────────────────────────────────────────────────────────────

def authenticate_user(username: str, password: str) -> tuple[dict | None, str | None]:
    try:
        row = user_repository.get_user_for_auth(username)
    except Exception as exc:
        logger.error("DB error en authenticate_user: %s", exc)
        return None, str(exc)

    if not row:
        return None, "Usuario no encontrado"

    user_id, uname, pw_hash, role, active, must_change = row

    if not active:
        return None, "Cuenta desactivada. Contacta al administrador."
    if not verify_password(password, pw_hash):
        return None, "Contraseña incorrecta"

    return {
        "id": user_id,
        "username": uname,
        "role": role,
        "must_change_password": bool(must_change),
    }, None


def register_user(username: str, email: str, password: str, plan: str) -> tuple[bool, str | None]:
    if user_repository.username_exists(username):
        return False, "Este nombre de usuario ya está en uso"
    if user_repository.email_exists(email):
        return False, "Este correo ya está registrado"
    try:
        user_repository.create_user(username, hash_password(password), email, plan)
        logger.info("Nuevo usuario registrado: %s, plan=%s, email=%s", username, plan, email)
        return True, None
    except Exception as exc:
        logger.error("register error: %s", exc)
        return False, "Error interno al registrar. Intenta de nuevo."


def change_password(username: str, new_password: str) -> tuple[bool, str | None]:
    try:
        updated = user_repository.update_password(username, hash_password(new_password))
    except Exception as exc:
        logger.error("change-password error: %s", exc)
        return False, "Error interno al actualizar"
    if not updated:
        return False, "Usuario no encontrado o ya completó el cambio"
    return True, None
