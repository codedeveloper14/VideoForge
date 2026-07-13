from src.domain.models.plan import PLAN_ALIASES, PLANS
from src.infrastructure.storage.mysql_client import get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)

_KNOWN_PLAN_VALUES = set(PLANS.keys()) | set(PLAN_ALIASES.keys())


def get_user_full(username: str) -> dict | None:
    """Devuelve {id, username, plan, email, plan_expires_at, created_at} o None.

    Usa SELECT * para ser robusto ante distintos nombres de columna en la BD
    (el esquema de vf_users ha variado entre despliegues).
    """
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM vf_users WHERE username=%s LIMIT 1",
                (username,),
            )
            cols = [d[0].lower() for d in (cur.description or [])]
            row = cur.fetchone()
        conn.close()
        if not row:
            logger.info("Usuario '%s' no encontrado en BD", username)
            return None
        r = dict(zip(cols, row))

        plan_raw = (
            r.get("plan")
            or r.get("plan_type")
            or r.get("subscription")
            or r.get("membership")
            or r.get("tier")
            or r.get("user_plan")
            or r.get("user_tier")
            or r.get("account_type")
            or r.get("level")
            or r.get("package")
            or r.get("user_type")
            or r.get("service")
        )
        if not plan_raw or str(plan_raw).lower().strip() not in _KNOWN_PLAN_VALUES:
            for col_name, col_val in r.items():
                if (
                    isinstance(col_val, str)
                    and col_val.lower().strip() in _KNOWN_PLAN_VALUES
                    and col_name not in ("role", "status", "username", "user_mail", "email")
                ):
                    plan_raw = col_val
                    break

        email_val = r.get("user_mail") or r.get("email") or r.get("user_email") or r.get("correo") or ""
        if not email_val:
            for col_val in r.values():
                if isinstance(col_val, str) and "@" in col_val:
                    email_val = col_val
                    break

        expires = (
            r.get("plan_expires_at")
            or r.get("expires_at")
            or r.get("plan_expiry")
            or r.get("subscription_end")
        )
        created = r.get("created_at") or r.get("registered_at") or r.get("reg_date") or r.get("date_created")
        subscription_date = r.get("subscription_date")
        theme = r.get("theme") or "dark"
        if theme not in ("light", "dark"):
            theme = "dark"

        return {
            "id": r.get("id") or 0,
            "username": r.get("username") or username,
            "plan": str(plan_raw) if plan_raw else "basico",
            "email": str(email_val) if email_val else "",
            "plan_expires_at": str(expires) if expires else None,
            "created_at": str(created) if created else None,
            "subscription_date": subscription_date,
            "theme": theme,
        }
    except Exception as exc:
        logger.error("get_user_full error: %s", exc)
        return None


def get_user_for_auth(username: str) -> tuple | None:
    """Devuelve (id, username, password_hash, role, active, must_change_password) o None."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash, role, active, must_change_password "
                "FROM vf_users WHERE username = %s LIMIT 1",
                (username,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def username_exists(username: str) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM vf_users WHERE username=%s LIMIT 1", (username,))
            return cur.fetchone() is not None
    finally:
        conn.close()


def email_exists(email: str) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM vf_users WHERE user_mail=%s LIMIT 1", (email,))
            return cur.fetchone() is not None
    finally:
        conn.close()


def create_user(username: str, password_hash: str, email: str, plan: str) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO vf_users "
                "(username, password_hash, role, active, must_change_password, user_mail, plan, user_type) "
                "VALUES (%s, %s, 'user', 1, 0, %s, %s, 'standard')",
                (username, password_hash, email, plan),
            )
        conn.commit()
    finally:
        conn.close()


def update_password(username: str, new_hash: str) -> bool:
    """Actualiza la contrasena solo si el usuario tenia must_change_password=1."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE vf_users SET password_hash=%s, must_change_password=0 "
                "WHERE username=%s AND must_change_password=1",
                (new_hash, username),
            )
            affected = cur.rowcount
        conn.commit()
        return affected > 0
    finally:
        conn.close()


def update_user_plan(username: str, new_plan: str) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE vf_users SET plan=%s, subscription_date=CURDATE() WHERE username=%s",
                (new_plan, username),
            )
            updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def update_user_theme(username: str, theme: str) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE vf_users SET theme=%s WHERE username=%s",
                (theme, username),
            )
            updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def find_username_by_email(email: str) -> str | None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username FROM vf_users WHERE user_mail=%s OR email=%s LIMIT 1",
                (email, email),
            )
            row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()
