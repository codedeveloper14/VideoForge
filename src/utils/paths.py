from pathlib import Path

from src.core.config import config


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


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
