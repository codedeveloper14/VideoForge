import time
import datetime
from typing import Any
from vf_db_connection import (load_user_config_from_vf,load_vf_config,get_hwid,_get_raw_hwid,normalize_plan_key, load_db_config_from_vf)
# Caché en memoria de vf.cfg para evitar descifrar múltiples veces
_VF_CONFIG_CACHE = None
_VF_CONFIG_CACHE_TIME = 0
_VF_CONFIG_CACHE_TTL = 300  # 5 minutos

def get_vf_config_cached() -> dict | None:
    
    """
    Retorna vf.cfg descifrado (caché con TTL de 5 min).
    Evita descifraciones repetidas y reduce carga de CPU.
    """

    global _VF_CONFIG_CACHE, _VF_CONFIG_CACHE_TIME
    current_time = time.time()
    
    if _VF_CONFIG_CACHE is not None and (current_time - _VF_CONFIG_CACHE_TIME) < _VF_CONFIG_CACHE_TTL:
        return _VF_CONFIG_CACHE
    
    _VF_CONFIG_CACHE = load_vf_config()
    _VF_CONFIG_CACHE_TIME = current_time
    return _VF_CONFIG_CACHE


def validate_license_and_hwid(username: str) -> tuple[bool, str]:
    """
    Valida que la licencia en vf.cfg sea válida y coincida con el HWID.
    Retorna (is_valid: bool, message: str)
    
    ✓ Válido: licencia activa, HWID coincide, no expirada
    ✗ Inválido: licencia no encontrada, HWID mismatch, expirada
    """
    try:
        vf_cfg = get_vf_config_cached()
        if not vf_cfg:
            print(f"[AUTH]  {username}: vf.cfg no encontrado (usuario BD puro)", flush=True)
            return False, ""  # Permitir login en BD pura
        
        # Validar HWID
        current_hwid = get_hwid()
        raw_hwid = _get_raw_hwid()
        stored_hwid = vf_cfg.get("hwid")
        if stored_hwid and stored_hwid not in (current_hwid, raw_hwid):
            msg = f"HWID mismatch: hardware cambió. Contacta a soporte."
            print(f"[AUTH]  {username}: {msg}", flush=True)
            return False, msg
        
        # Validar expiración
        expires_at = vf_cfg.get("expires_at")
        if expires_at:
            try:
                exp_date = datetime.datetime.fromisoformat(expires_at)
                if datetime.datetime.utcnow() > exp_date:
                    msg = f"Licencia expirada el {expires_at}. Renuévala para continuar."
                    print(f"[AUTH] {username}: {msg}", flush=True)
                    return False, msg
            except Exception as e:
                print(f"[AUTH]  Error parsing expiry date: {e}", flush=True)
        
        # Validar que el usuario en vf.cfg coincida (si existe)
        vf_username = vf_cfg.get("username")
        if vf_username and vf_username.lower() != username.lower():
            msg = f"El usuario ({username}) no coincide con vf.cfg ({vf_username})"
            print(f"[AUTH] {msg}", flush=True)
            return False, msg
        
        print(f"[AUTH] {username}: Licencia y HWID válidos", flush=True)
        return True, ""
    
    except Exception as e:
        print(f"[AUTH] validate_license_and_hwid ERROR: {e}", flush=True)
        return True, ""  # En caso de error, permitir (fallback seguro)

def _get_db_connection():
    try:
        import pymysql
        raw = load_db_config_from_vf() or {}
        DB_CONFIG: dict[str, Any] = raw
        return pymysql.connect(**DB_CONFIG)
    except ImportError:
        raise RuntimeError("pymysql no instalado. Ejecuta: pip install pymysql")
    except Exception as e:
        raise RuntimeError(f"Error conectando a la base de datos: {e}")

def sync_vf_config_with_db() -> dict | None:
    """
    Sincroniza la configuración de vf.cfg con el registro del usuario en la base de datos.

    - Si no hay vf.cfg, devuelve None.
    - Si el usuario existe en la BD, actualiza email, plan y expiración.
    - Si el usuario no existe, devuelve los datos de vf.cfg sin insertar.
    """
    vf_user = load_user_config_from_vf()
    if not vf_user:
        return None

    username = (vf_user.get("username") or "").strip()
    if not username:
        print("[AUTH] vf.cfg no contiene username válido.", flush=True)
        return None

    plan = normalize_plan_key(vf_user.get("plan", "starter"))
    email = (vf_user.get("email") or "").strip().lower()
    expires_at = vf_user.get("expires_at")
    hwid = vf_user.get("hwid")
    license_key = vf_user.get("license_key")

    conn = None
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM vf_users WHERE username=%s LIMIT 1", (username,))
            row = cur.fetchone()
            cols = [d[0].lower() for d in (cur.description or [])]

            alt_user = None
            if not row and email:
                if "user_mail" in cols:
                    cur.execute("SELECT * FROM vf_users WHERE user_mail=%s LIMIT 1", (email,))
                    alt_user = cur.fetchone()
                elif "email" in cols:
                    cur.execute("SELECT * FROM vf_users WHERE email=%s LIMIT 1", (email,))
                    alt_user = cur.fetchone()
                if alt_user:
                    row = alt_user
                    cols = [d[0].lower() for d in (cur.description or [])]

            if row:
                current = dict(zip(cols, row))
                updates = {}

                if email:
                    if "user_mail" in cols:
                        current_email = (current.get("user_mail") or "").strip().lower()
                        if current_email != email:
                            updates["user_mail"] = email
                    elif "email" in cols:
                        current_email = (current.get("email") or "").strip().lower()
                        if current_email != email:
                            updates["email"] = email

                if "plan" in cols and normalize_plan_key(str(current.get("plan") or "")) != plan:
                    updates["plan"] = plan

                if expires_at:
                    if "plan_expires_at" in cols and current.get("plan_expires_at") != expires_at:
                        updates["plan_expires_at"] = expires_at
                    elif "expires_at" in cols and current.get("expires_at") != expires_at:
                        updates["expires_at"] = expires_at

                if "active" in cols and current.get("active") in (0, "0", False):
                    updates["active"] = 1

                if "hwid" in cols and hwid and current.get("hwid") != hwid:
                    updates["hwid"] = hwid

                if "license_key" in cols and license_key and current.get("license_key") != license_key:
                    updates["license_key"] = license_key

                if updates:
                    setters = ", ".join(f"{k}=%s" for k in updates)
                    values = list(updates.values()) + [username]
                    cur.execute(f"UPDATE vf_users SET {setters} WHERE username=%s", tuple(values))
                    conn.commit()
                    print(f"[AUTH] vf.cfg sincronizado para {username}: {list(updates.keys())}", flush=True)

                return {
                    "username": username,
                    "plan": plan,
                    "email": email or current.get("user_mail") or current.get("email") or "",
                    "expires_at": expires_at,
                    "license_key": license_key,
                }

            print(f"[AUTH]   Usuario '{username}' no existe en BD; no se insertará automáticamente.", flush=True)
            return {
                "username": username,
                "plan": plan,
                "email": email,
                "expires_at": expires_at,
                "license_key": license_key,
            }
    except Exception as exc:
        print(f"[AUTH] sync_vf_config_with_db error: {exc}", flush=True)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            
def get_app_secret() -> str | None:
    vf_config = get_vf_config_cached()
    if vf_config:
        return str(vf_config.get("appsecret", ""))
    return None

