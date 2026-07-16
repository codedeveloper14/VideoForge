import sys
from pathlib import Path

from src.core.config import config


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_frontend_dist_dir() -> Path:
    """Carpeta con el build de Vite (frontend/dist). En un .exe/.app compilado, los
    archivos no viven junto a este .py -- hay que resolverlos segun la herramienta de
    build: PyInstaller los extrae bajo sys._MEIPASS (--add-data); Nuitka standalone
    los deja junto al ejecutable (--include-data-dir), sin sys._MEIPASS. Ambos deben
    empaquetar la carpeta bajo el nombre "frontend_dist"."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "frontend_dist"
    if "__compiled__" in globals():
        return Path(sys.executable).resolve().parent / "frontend_dist"
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def get_logs_dir() -> Path:
    return _ensure(config.app_data_dir / "logs")


def get_jobs_dir() -> Path:
    return _ensure(config.app_data_dir / "jobs")


def get_grok_accounts_dir() -> Path:
    return _ensure(config.app_data_dir / "grok_accounts")


def get_grok_downloads_dir() -> Path:
    return _ensure(config.app_data_dir / "grok_downloads")


def get_qwen_accounts_dir() -> Path:
    return _ensure(config.app_data_dir / "qwen_accounts")


def get_meta_accounts_dir() -> Path:
    return _ensure(config.app_data_dir / "meta_accounts")


def get_gentube_cookies_dir() -> Path:
    return _ensure(config.app_data_dir / "gentube_cookies")


def get_gentube_profiles_dir() -> Path:
    return _ensure(config.app_data_dir / "gentube_profiles")


def get_flow_cookies_dir() -> Path:
    return _ensure(config.app_data_dir / "flow_cookies")


def get_flow_profiles_dir() -> Path:
    return _ensure(config.app_data_dir / "flow_profiles")


def get_vibes_cookies_dir() -> Path:
    return _ensure(config.app_data_dir / "vibes_cookies")


def get_vibes_profiles_dir() -> Path:
    return _ensure(config.app_data_dir / "vibes_profiles")
