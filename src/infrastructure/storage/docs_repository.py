from src.infrastructure.storage.mysql_client import get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)


def ensure_tables() -> None:
    """Crea vf_docs / vf_help_reports si no existen. Se llama al arrancar la app."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vf_docs (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    type          ENUM('video','text') NOT NULL DEFAULT 'video',
                    category      VARCHAR(100) NOT NULL DEFAULT 'General',
                    title         VARCHAR(255) NOT NULL DEFAULT '',
                    description   TEXT,
                    url           VARCHAR(1000) DEFAULT '',
                    content       LONGTEXT,
                    thumbnail_url VARCHAR(500)  DEFAULT '',
                    duration_label VARCHAR(20)  DEFAULT '',
                    tags          VARCHAR(500)  DEFAULT '',
                    sort_order    INT           DEFAULT 0,
                    is_published  TINYINT(1)    DEFAULT 1,
                    created_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
                    updated_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    created_by    VARCHAR(100)  DEFAULT ''
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vf_help_reports (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    username    VARCHAR(255),
                    email       VARCHAR(255),
                    type        VARCHAR(50),
                    category    VARCHAR(100),
                    title       VARCHAR(500),
                    description TEXT,
                    status      VARCHAR(50) DEFAULT 'pending',
                    priority    VARCHAR(20) DEFAULT 'normal',
                    admin_notes TEXT,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_type (type), INDEX idx_status (status),
                    INDEX idx_user (username), INDEX idx_created (created_at)
                ) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)
        conn.commit()
        conn.close()
        logger.info("Tablas vf_docs / vf_help_reports OK.")
    except Exception as exc:
        logger.error("docs_repository.ensure_tables error: %s", exc)


def list_published() -> list[tuple]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id,type,category,title,description,url,content,"
            "thumbnail_url,duration_label,tags,sort_order "
            "FROM vf_docs WHERE is_published=1 ORDER BY category,sort_order,id"
        )
        rows = cur.fetchall()
    conn.close()
    return rows


def list_all() -> list[tuple]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id,type,category,title,description,url,content,thumbnail_url,"
            "duration_label,tags,sort_order,is_published,"
            "DATE_FORMAT(created_at,'%Y-%m-%d'),created_by "
            "FROM vf_docs ORDER BY category,sort_order,id"
        )
        rows = cur.fetchall()
    conn.close()
    return rows


def create_doc(fields: dict, created_by: str) -> int:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO vf_docs(type,category,title,description,url,content,"
            "thumbnail_url,duration_label,tags,sort_order,is_published,created_by) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (fields["type"], fields["category"], fields["title"], fields["description"],
             fields["url"], fields["content"], fields["thumbnail_url"], fields["duration_label"],
             fields["tags"], fields["sort_order"], 1 if fields["is_published"] else 0, created_by),
        )
        new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_doc(doc_id: int, fields: dict) -> None:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE vf_docs SET type=%s,category=%s,title=%s,description=%s,url=%s,"
            "content=%s,thumbnail_url=%s,duration_label=%s,tags=%s,"
            "sort_order=%s,is_published=%s WHERE id=%s",
            (fields["type"], fields["category"], fields["title"], fields["description"],
             fields["url"], fields["content"], fields["thumbnail_url"], fields["duration_label"],
             fields["tags"], fields["sort_order"], 1 if fields["is_published"] else 0, doc_id),
        )
    conn.commit()
    conn.close()


def delete_doc(doc_id: int) -> None:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM vf_docs WHERE id=%s", (doc_id,))
    conn.commit()
    conn.close()


def insert_help_report(username: str, email: str, report_type: str, category: str,
                        title: str, description: str) -> None:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO vf_help_reports "
            "(username, email, type, category, title, description) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (username, email, report_type, category, title, description),
        )
    conn.commit()
    conn.close()


def get_user_email(username: str) -> str:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT user_mail FROM vf_users WHERE username=%s LIMIT 1", (username,))
        row = cur.fetchone()
    conn.close()
    return (row[0] or "") if row else ""
