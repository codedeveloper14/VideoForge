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


def _bundled_dir(packaged_name: str, dev_relative: tuple[str, ...]) -> Path:
    """Resuelve una carpeta vendorizada (ffmpeg, chromium) al lado del ejecutable
    compilado -- mismo patron dual-mode que get_frontend_dist_dir(): PyInstaller
    extrae bajo sys._MEIPASS, Nuitka standalone la deja junto al ejecutable, y en
    dev vive bajo vendor/ en la raiz del repo (poblada por
    scripts/fetch_*_windows.py antes de compilar)."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / packaged_name
    if "__compiled__" in globals():
        return Path(sys.executable).resolve().parent / packaged_name
    return Path(__file__).resolve().parents[2].joinpath(*dev_relative)


def get_bundled_ffmpeg_dir() -> Path:
    """Carpeta con ffmpeg.exe/ffprobe.exe bundleados (Windows) -- ver
    scripts/fetch_ffmpeg_windows.py y ffmpeg_utils.ffmpeg_exe()/ffprobe_exe()."""
    return _bundled_dir("ffmpeg_bin", ("vendor", "ffmpeg", "win64"))


def get_bundled_chromium_exe() -> Path | None:
    """chrome.exe bundleado (Windows), o None si la carpeta no existe (dev sin
    correr scripts/fetch_chromium_windows.py todavia, o plataforma no-Windows) --
    ver chrome_launcher.find_chromium_exe()."""
    candidate = _bundled_dir("chromium_bin", ("vendor", "chromium", "win64")) / "chrome.exe"
    return candidate if candidate.is_file() else None


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


def get_vibes_profile_dir() -> Path:
    return _ensure(config.app_data_dir / "vibes_profile")


def get_vibes_cookies_dir() -> Path:
    return _ensure(config.app_data_dir / "vibes_cookies")


def get_vibes_profiles_dir() -> Path:
    return _ensure(config.app_data_dir / "vibes_profiles")
