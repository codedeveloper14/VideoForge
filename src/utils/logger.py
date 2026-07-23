import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

from src.core.config import config
from src.utils.paths import get_logs_dir

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5

_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return

    formatter = logging.Formatter(_LOG_FORMAT)

    file_handler = RotatingFileHandler(
        get_logs_dir() / "videoforge.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if config.debug else logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # En desarrollo, ademas del log en %APPDATA%/.../logs, escribe a ./logs/backend.log
    # (raiz del repo) para poder hacer tail sin navegar al directorio de datos de la
    # app -- ver [[project-dead-code-audit]]/auditoria de logging. Solo con config.debug
    # activo: en un build empaquetado no existe una "raiz del repo" junto al ejecutable.
    if config.debug:
        dev_log_dir = Path(__file__).resolve().parents[2] / "logs"
        dev_log_dir.mkdir(parents=True, exist_ok=True)
        dev_file_handler = RotatingFileHandler(
            dev_log_dir / "backend.log",
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        dev_file_handler.setFormatter(formatter)
        root_logger.addHandler(dev_file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
