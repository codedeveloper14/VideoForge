import logging
import os
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "VideoForge"


def get_app_data_dir(app_name: str = APP_NAME) -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ["APPDATA"])
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"

    app_dir = base / app_name
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def open_folder(path: str | Path) -> None:
    """Abre la carpeta indicada en el explorador de archivos del SO (cross-platform)."""
    path = str(path)
    try:
        folder = os.path.dirname(path) if os.path.isfile(path) else path
        if not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)
        system = platform.system()
        if system == "Windows":
            subprocess.Popen(["explorer", os.path.normpath(folder)],
                              creationflags=subprocess.CREATE_NO_WINDOW)
        elif system == "Darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
    except Exception as exc:
        logger.error("open_folder error: %s", exc)
