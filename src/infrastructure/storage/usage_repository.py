from datetime import datetime, timedelta

from src.infrastructure.storage.mysql_client import get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)


def ensure_tables() -> None:
    """Crea/actualiza las tablas de uso si no existen. Se llama al arrancar la app."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vf_usage (
                    id               INT AUTO_INCREMENT PRIMARY KEY,
                    user_id          INT  NOT NULL,
                    usage_date       DATE NOT NULL,
                    videos_generated INT DEFAULT 0,
                    tts_chars_used   INT DEFAULT 0,
                    shorts_generated INT DEFAULT 0,
                    UNIQUE KEY uq_user_date (user_id, usage_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            try:
                cur.execute("ALTER TABLE vf_usage ADD COLUMN shorts_generated INT DEFAULT 0 NOT NULL")
            except Exception:
                pass  # ya existe
            try:
                cur.execute("ALTER TABLE vf_users ADD COLUMN subscription_date DATE DEFAULT NULL")
            except Exception:
                pass  # ya existe
        conn.commit()
        conn.close()
        logger.info("Tabla vf_usage OK.")
    except Exception as exc:
        logger.error("ensure_tables error: %s", exc)


def get_today_usage(user_id: int) -> dict:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT videos_generated, tts_chars_used, COALESCE(shorts_generated,0) "
                "FROM vf_usage WHERE user_id=%s AND usage_date=%s LIMIT 1",
                (user_id, today),
            )
            row = cur.fetchone()
        conn.close()
        if row:
            return {"videos": int(row[0]), "tts_chars": int(row[1]), "shorts": int(row[2])}
    except Exception as exc:
        logger.error("get_today_usage error: %s", exc)
    return {"videos": 0, "tts_chars": 0, "shorts": 0}


def get_month_usage(user_id: int) -> dict:
    now = datetime.utcnow()
    month_start = now.strftime("%Y-%m-01")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(videos_generated),0), "
                "       COALESCE(SUM(tts_chars_used),0), "
                "       COALESCE(SUM(COALESCE(shorts_generated,0)),0) "
                "FROM vf_usage "
                "WHERE user_id=%s AND usage_date >= %s AND usage_date < %s",
                (user_id, month_start, tomorrow),
            )
            row = cur.fetchone()
        conn.close()
        if row:
            return {"videos": int(row[0]), "tts_chars": int(row[1]), "shorts": int(row[2])}
    except Exception as exc:
        logger.error("get_month_usage error: %s", exc)
    return {"videos": 0, "tts_chars": 0, "shorts": 0}


def record_usage(user_id: int, videos: int = 0, tts_chars: int = 0, shorts: int = 0) -> bool:
    if videos == 0 and tts_chars == 0 and shorts == 0:
        return True
    today = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO vf_usage "
                "(user_id, usage_date, videos_generated, tts_chars_used, shorts_generated) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE "
                "videos_generated = videos_generated + VALUES(videos_generated), "
                "tts_chars_used   = tts_chars_used   + VALUES(tts_chars_used), "
                "shorts_generated = COALESCE(shorts_generated,0) + VALUES(shorts_generated)",
                (user_id, today, videos, tts_chars, shorts),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        logger.error("record_usage error: %s", exc)
        return False
