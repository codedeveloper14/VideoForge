import hashlib
import hmac
from typing import Any
from vf_db_connection import (load_db_config_from_vf)
from vf_db_sync import (validate_license_and_hwid, _get_db_connection)

def _hash_password(password):
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        salt = "videoforge_salt_2024_"
        return "sha256:" + hashlib.sha256((salt + password).encode()).hexdigest()

def verify_password(plain, hashed):
    try:
        if hashed.startswith("sha256:"):
            salt = "videoforge_salt_2024_"
            return hmac.compare_digest(
                hashed,
                "sha256:" + hashlib.sha256((salt + plain).encode()).hexdigest()
            )
        import bcrypt
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def authenticate_user(username, password):
    """
    Autentica al usuario y valida la licencia/HWID si existe vf.cfg.
    
    Retorna (user_dict, error_message)
    """
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash, role, active, must_change_password "
                "FROM vf_users WHERE username = %s LIMIT 1",
                (username,)
            )
            row = cur.fetchone()
        conn.close()
    except Exception as e:
        return None, str(e)

    if not row:
        return None, "Usuario no existente"

    user_id, uname, pw_hash, role, active, must_change = row

    if not active:
        return None, "Cuenta desactivada. Contacta al administrador."

    if not verify_password(password, pw_hash):
        return None, "Credenciales incorrectas"

    # ── NUEVO: Validar licencia y HWID si existe vf.cfg ──────────────
    is_licensed, license_msg = validate_license_and_hwid(uname)
    if not is_licensed:
        return None, license_msg
    # ────────────────────────────────────────────────────────────────

    return {
        "id": user_id,
        "username": uname,
        "role": role,
        "must_change_password": bool(must_change)
    }, None
