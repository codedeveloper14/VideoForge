import os
import sys
import hashlib
import json
import platform
import subprocess
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet, InvalidToken

HAS_CRYPTO=True

PLANS = {
    "starter": {
        "name": "Starter",
        "emoji": "🌱",
        "videos_per_day": 7,
        "tts_chars_per_day": 27_000,   # ≈ 30 min TTS
        "max_video_minutes": 15,
        "price_usd": 9,
        "color": "#22d3a0",
        "highlight": False,
    },
    "pro": {
        "name": "Pro",
        "emoji": "⚡",
        "videos_per_day": 20,
        "tts_chars_per_day": 54_000,   # ≈ 1 hora TTS
        "max_video_minutes": 30,
        "price_usd": 29,
        "color": "#7c6aff",
        "highlight": True,
    },
    "ultra": {
        "name": "Ultra",
        "emoji": "🔥",
        "videos_per_day": 50,
        "tts_chars_per_day": 135_000,  # ≈ 2.5 horas TTS
        "max_video_minutes": None,      # ilimitado
        "price_usd": 79,
        "color": "#fbbf24",
        "highlight": False,
    },
}

# Alias de nombres de plan alternativos en la BD → clave canónica
PLAN_ALIASES = {
    "standard": "pro",       # nombre alternativo común para Pro
    "basic":    "starter",
    "free":     "starter",
    "premium":  "pro",
    "advanced": "pro",
    "enterprise": "ultra",
    "business": "ultra",
}

def _get_install_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def normalize_plan_key(raw: str) -> str:
    """Convierte cualquier nombre de plan de la BD al key canónico (starter/pro/ultra)."""
    key = str(raw or "starter").lower().strip()
    key = PLAN_ALIASES.get(key, key)          # resolver alias
    return key if key in PLANS else "starter" # validar contra PLANS

def _get_raw_hwid() -> str:
    """Obtiene el HWID sin hash para compatibilidad con variantes de cifrado antiguas."""
    try:
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            return guid.strip()
        elif platform.system() == "Darwin":
            out = subprocess.check_output(
                ["system_profiler", "SPHardwareDataType"], timeout=5
            ).decode()
            for line in out.splitlines():
                if "Hardware UUID" in line:
                    return line.split(":")[1].strip()
        else:
            with open("/etc/machine-id") as f:
                return f.read().strip()
    except Exception as exc:
        pass
    return platform.node()


def get_hwid() -> str:
    """Obtiene el identificador unico del hardware en formato hash."""
    raw = _get_raw_hwid()
    return hashlib.sha256(raw.encode()).hexdigest()


def get_license_key():
    """Lee la clave de licencia del almacenamiento persistente."""
    
    try:
        if platform.system() == "Windows":
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\VideoForge")
                license_key, _ = winreg.QueryValueEx(key, "LicenseKey")
                winreg.CloseKey(key)
                if license_key:
                    return license_key.strip()
            except FileNotFoundError:
                pass
            except OSError as exc:
                pass
        path = os.path.join(_get_install_dir(), ".vflk")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                value = f.read().strip()
                if value:
                    return value
    except Exception as exc:
        pass

    env_value = os.environ.get("VF_LICENSE_KEY")
    if env_value:
        return env_value.strip()

    return None


def load_vf_config() -> dict | None:
    if not HAS_CRYPTO:
        return None

    try:
        license_key = (get_license_key() or "").strip()
        
        if not license_key:
            return None

        raw_hwid = (_get_raw_hwid() or "").strip()
        hashed_hwid = (get_hwid() or "").strip().lower()

        candidates = []
        if hashed_hwid:
            candidates.append(f"{license_key}:{hashed_hwid}")
        if raw_hwid and raw_hwid != hashed_hwid:
            candidates.append(f"{license_key}:{raw_hwid}")
        candidates.append(license_key)

        cfg_path = os.path.join(_get_install_dir(), "vf.cfg")
        if not os.path.exists(cfg_path):
            return None

        with open(cfg_path, "r", encoding="utf-8-sig") as f:
            encrypted_text = f.read().strip()

        if not encrypted_text:
            return None

        last_exception = None

        for idx, material in enumerate(candidates):
            try:
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=b"videoforge-vf-cfg-v1",
                    iterations=390000,
                )
                fernet_key = base64.urlsafe_b64encode(kdf.derive(material.encode("utf-8")))
                fernet = Fernet(fernet_key)

                decrypted_data = fernet.decrypt(encrypted_text.encode("utf-8"))
                config = json.loads(decrypted_data.decode("utf-8"))

                return config

            except InvalidToken as exc:
                last_exception = exc
                continue
            except Exception as exc:
                last_exception = exc
                continue

        if isinstance(last_exception, InvalidToken):
            pass
        elif last_exception is not None:
            pass
        else:
            pass

        return None

    except Exception as exc:
        pass
        return None


def load_db_config_from_vf() -> dict | None:
    vf_config = load_vf_config()
    if vf_config:
        return {
            "host": vf_config.get("dbhost", "127.0.0.1"),
            "user": vf_config.get("dbuser", ""),
            "password": vf_config.get("dbpass", ""),
            "database": vf_config.get("dbname", ""),
            "port": int(vf_config.get("dbport", 3306)),
            "connect_timeout": 10,
            "charset": "utf8mb4",
        }
    return None


def load_user_config_from_vf() -> dict | None:
    vf_config = load_vf_config()
    if vf_config:
        return {
            "username": vf_config.get("username", "VideoForge User"),
            "email": vf_config.get("email", ""),
            "plan": normalize_plan_key(vf_config.get("plan", "starter")),
            "expires_at": vf_config.get("expires_at"),
            "license_key": vf_config.get("license_key"),
            "activated_on": vf_config.get("activated_on"),
            "hwid": get_hwid(),
        }
    return None