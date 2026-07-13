from src.core.config import config
from src.core.exceptions import DatabaseError
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Cada llamada a get_connection() abria una conexion TCP+TLS nueva al MySQL
# remoto (Contabo) -- sin pool, cada request pagaba el handshake completo,
# lo que se sentia como "la DB esta lenta" en Planes/Ajustes/Documentacion
# (requests de 12-23s solo por el connect, no por la query en si). Un pool
# reutiliza conexiones ya abiertas: conn.close() las devuelve al pool en vez
# de cerrarlas de verdad, asi que los repositorios no necesitan cambiar nada.
_pool = None


def _build_pool(host: str):
    import pymysql
    from dbutils.pooled_db import PooledDB

    return PooledDB(
        creator=pymysql,
        mincached=1,
        maxcached=5,
        maxconnections=10,
        blocking=True,
        ping=1,  # revalida la conexion antes de entregarla; reconecta si se cayo
        host=host,
        user=config.db_user,
        password=config.db_password,
        database=config.db_name,
        port=config.db_port,
        connect_timeout=10,
        charset="utf8mb4",
    )


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool

    try:
        import pymysql  # noqa: F401
    except ImportError as exc:
        raise DatabaseError("pymysql no instalado. Ejecuta: pip install pymysql") from exc

    last_err: Exception | None = None
    try:
        _pool = _build_pool(config.db_host)
        return _pool
    except Exception as exc:
        last_err = exc

    if config.db_host_fallback and config.db_host_fallback != config.db_host:
        try:
            _pool = _build_pool(config.db_host_fallback)
            logger.warning(
                "Pool de DB conectado via fallback host '%s' (principal fallo: %s)",
                config.db_host_fallback,
                last_err,
            )
            return _pool
        except Exception:
            pass

    raise DatabaseError(f"Error conectando a la base de datos: {last_err}")


def get_connection():
    return _get_pool().connection()
