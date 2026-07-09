from src.core.config import config
from src.core.exceptions import DatabaseError
from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_connection():
    try:
        import pymysql
    except ImportError as exc:
        raise DatabaseError("pymysql no instalado. Ejecuta: pip install pymysql") from exc

    base_kwargs = {
        "user": config.db_user,
        "password": config.db_password,
        "database": config.db_name,
        "port": config.db_port,
        "connect_timeout": 10,
        "charset": "utf8mb4",
    }

    last_err: Exception | None = None
    try:
        return pymysql.connect(host=config.db_host, **base_kwargs)
    except Exception as exc:
        last_err = exc

    if config.db_host_fallback and config.db_host_fallback != config.db_host:
        try:
            conn = pymysql.connect(host=config.db_host_fallback, **base_kwargs)
            logger.warning(
                "Conectado via fallback host '%s' (principal fallo: %s)",
                config.db_host_fallback,
                last_err,
            )
            return conn
        except Exception:
            pass

    raise DatabaseError(f"Error conectando a la base de datos: {last_err}")
