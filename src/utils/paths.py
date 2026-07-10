import sys
from pathlib import Path

from src.core.config import config


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_frontend_dist_dir() -> Path:
    """Carpeta con el build de Vite (frontend/dist). En un .exe/.app compilado con
    PyInstaller, los archivos se extraen bajo sys._MEIPASS en vez de vivir junto a
    este .py -- ahi es donde debe apuntar el spec de build (--add-data)."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "frontend_dist"
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def get_logs_dir() -> Path:
    return _ensure(config.app_data_dir / "logs")


def get_jobs_dir() -> Path:
    return _ensure(config.app_data_dir / "jobs")


def get_cookies_dir() -> Path:
    return _ensure(config.app_data_dir / "cookies")


def get_whisk_downloads_dir() -> Path:
    return _ensure(config.app_data_dir / "whisk_downloads")


def get_grok_accounts_dir() -> Path:
    return _ensure(config.app_data_dir / "grok_accounts")


def get_grok_downloads_dir() -> Path:
    return _ensure(config.app_data_dir / "grok_downloads")


def get_qwen_accounts_dir() -> Path:
    return _ensure(config.app_data_dir / "qwen_accounts")


def get_meta_accounts_dir() -> Path:
    return _ensure(config.app_data_dir / "meta_accounts")


def get_whisk_profiles_dir() -> Path:
    return _ensure(config.app_data_dir / "whisk_profiles")


def get_gentube_cookies_dir() -> Path:
    return _ensure(config.app_data_dir / "gentube_cookies")


def get_gentube_profiles_dir() -> Path:
    return _ensure(config.app_data_dir / "gentube_profiles")


def get_flow_cookies_dir() -> Path:
    # Carpeta propia -- el original compartia "cookies/account_N.txt" con Whisk
    # (mismo directorio, mismo patron de nombre), un choque real de datos entre
    # dos features independientes. get_cookies_dir() ya es de Whisk.
    return _ensure(config.app_data_dir / "flow_cookies")


def get_flow_profiles_dir() -> Path:
    return _ensure(config.app_data_dir / "flow_profiles")
