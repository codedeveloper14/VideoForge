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

# Mensaje amigable para CUALQUIER fallo de conexion (timeout, host inalcanzable,
# pool agotado) -- nunca el texto crudo del driver (p. ej. pymysql renderiza
# "(2003, "Can't connect to MySQL server on '...' (timed out)")"), que sin este
# wrapping se colaba tal cual hasta pantallas como Login ("⚠ (2003, ...)").
_DB_LOADING_MSG = "Cargando la base de datos, esperá unos segundos e intentá de nuevo."


def _build_pool(host: str):
    import pymysql
    from dbutils.pooled_db import PooledDB

    return PooledDB(
        creator=pymysql,
        mincached=1,
        maxcached=5,
        maxconnections=10,
        blocking=True,
        # ping=1 pingueaba el server remoto (Contabo) en cada get_connection(),
        # duplicando el round-trip de TODA query de la app (ping + la query real).
        # failures= (su default: OperationalError/InterfaceError/InternalError) ya
        # hace que SteadyDB reconecte solo cuando una conexion realmente esta muerta
        # -- ping=0 deja de pagar el chequeo proactivo en el camino feliz y solo paga
        # el costo de reconectar en el caso raro (conexion cortada por wait_timeout).
        ping=0,
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

    logger.error("Error conectando a la base de datos: %s", last_err)
    raise DatabaseError(_DB_LOADING_MSG) from last_err


def get_connection():
    """Conexion del pool -- si el pool ya existe pero la conexion en si falla recien
    ahora (blip de red al MySQL remoto, las conexiones cacheadas quedaron muertas),
    DBUtils/pymysql propagan el error CRUDO del driver sin pasar por el wrapping de
    _get_pool() de arriba. Se envuelve tambien aca para que ningun llamador (auth,
    docs, usage, stripe) vea nunca ese texto crudo -- el detalle real queda en el
    log, no en pantalla."""
    try:
        return _get_pool().connection()
    except DatabaseError:
        raise
    except Exception as exc:
        logger.error("Error obteniendo conexion del pool: %s", exc)
        raise DatabaseError(_DB_LOADING_MSG) from exc
