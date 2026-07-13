from src.core.config import config
from src.domain.models.plan import PLANS
from src.infrastructure.storage.mysql_client import get_connection
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Precios en centavos por plan (para crear Checkout Sessions).
STRIPE_PRICES = {
    "basico": {"amount": 7500, "name": "Studio IVR Básico", "product_id": None},
    "pro": {"amount": 10500, "name": "Studio IVR Pro", "product_id": None},
    "ultra": {"amount": 14500, "name": "Studio IVR Ultra", "product_id": None},
    "unlimited": {"amount": 35000, "name": "Studio IVR Ilimitado", "product_id": None},
}

# Payment Links de respaldo (se usan si falla la creacion de sesion o no hay Stripe key).
STRIPE_PAYMENT_LINKS = {
    "basico": "https://buy.stripe.com/6oU3cx2S10sr24c4v93cc0b",
    "pro": "https://buy.stripe.com/9B614p78h0sr7ow1iX3cc0c",
    "ultra": "https://buy.stripe.com/8x2eVf3W51wvaAIf9N3cc0d",
    "unlimited": "https://buy.stripe.com/fZufZj3W50sr9wEf9N3cc0e",
}


def ensure_stripe_table() -> None:
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS vf_stripe_payments (
                    id                INT AUTO_INCREMENT PRIMARY KEY,
                    username          VARCHAR(120) NOT NULL,
                    plan              VARCHAR(40)  NOT NULL,
                    amount_usd        DECIMAL(10,2) DEFAULT 0,
                    stripe_session_id VARCHAR(255),
                    paid_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_session (stripe_session_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
            )
            for col, ddl in [
                ("amount_usd", "DECIMAL(10,2) DEFAULT 0"),
                ("paid_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
                ("stripe_session_id", "VARCHAR(255)"),
                ("plan", "VARCHAR(40) NOT NULL DEFAULT 'unknown'"),
            ]:
                try:
                    cur.execute(f"ALTER TABLE vf_stripe_payments ADD COLUMN {col} {ddl}")
                except Exception:
                    pass  # ya existe
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error("ensure_stripe_table error: %s", exc)


def apply_plan_upgrade(username: str, new_plan: str, stripe_session_id: str | None = None) -> bool:
    """Actualiza el plan del usuario y registra el pago. Devuelve True si se actualizo."""
    try:
        conn = get_connection()
        plan_obj = PLANS.get(new_plan, {})
        amount = plan_obj.get("price_usd", 0)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE vf_users SET plan=%s, subscription_date=CURDATE() WHERE username=%s",
                (new_plan, username),
            )
            updated = cur.rowcount > 0
        conn.commit()
        if updated and stripe_session_id:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT IGNORE INTO vf_stripe_payments "
                        "(username, plan, amount_usd, stripe_session_id) "
                        "VALUES (%s, %s, %s, %s)",
                        (username, new_plan, amount, stripe_session_id),
                    )
                conn.commit()
            except Exception:
                pass
        conn.close()
        if updated:
            logger.info("Plan actualizado: %s --> %s", username, new_plan)
        return updated
    except Exception as exc:
        logger.error("apply_plan_upgrade error: %s", exc)
        return False


def get_payment_history(username: str, limit: int = 20) -> list[dict]:
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT plan, amount_usd, paid_at, stripe_session_id "
                "FROM vf_stripe_payments WHERE username=%s ORDER BY paid_at DESC LIMIT %s",
                (username, limit),
            )
            rows = cur.fetchall()
        conn.close()
        payments = []
        for plan, amount_usd, paid_at, session_id in rows:
            if hasattr(paid_at, "strftime"):
                paid_at = paid_at.strftime("%Y-%m-%d %H:%M")
            payments.append(
                {
                    "plan": plan,
                    "amount_usd": float(amount_usd) if amount_usd else 0,
                    "paid_at": str(paid_at),
                    "session_id": session_id,
                }
            )
        return payments
    except Exception as exc:
        logger.error("get_payment_history error: %s", exc)
        return []


def create_checkout_session(username: str, plan_key: str, user_email: str | None) -> dict:
    """Crea una Stripe Checkout Session. Si falla o no hay API key, retorna el Payment Link de respaldo."""
    if not config.stripe_secret_key:
        return {"url": STRIPE_PAYMENT_LINKS.get(plan_key, ""), "fallback": True}

    try:
        import stripe as _stripe

        _stripe.api_key = config.stripe_secret_key
        price_info = STRIPE_PRICES[plan_key]

        price_id = None
        product_id = price_info.get("product_id")
        if product_id:
            try:
                prices = _stripe.Price.list(
                    product=product_id,
                    active=True,
                    recurring={"interval": "month"},
                    limit=1,
                )
                if prices.data:
                    price_id = prices.data[0].id
            except Exception as exc:
                logger.warning("No se pudo obtener precio del producto %s: %s", product_id, exc)

        line_item = (
            {"price": price_id, "quantity": 1}
            if price_id
            else {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": price_info["name"]},
                    "unit_amount": price_info["amount"],
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }
        )

        session = _stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[line_item],
            mode="subscription",
            success_url=(
                f"{config.public_base_url}/app/planes" "?session_id={CHECKOUT_SESSION_ID}&plan=" + plan_key
            ),
            cancel_url=f"{config.public_base_url}/app/planes",
            customer_email=user_email or None,
            metadata={"username": username, "plan": plan_key},
        )
        return {"url": session.url, "session_id": session.id}
    except Exception as exc:
        logger.error("checkout error: %s", exc)
        return {"url": STRIPE_PAYMENT_LINKS.get(plan_key, ""), "fallback": True, "error": str(exc)}


def verify_stripe_session(session_id: str) -> dict | None:
    """Verifica una sesion de Stripe. Devuelve {paid, plan, customer_email, session_id} o None si hay error."""
    try:
        import stripe as _stripe

        _stripe.api_key = config.stripe_secret_key
        session = _stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
        paid = session.payment_status in ("paid", "no_payment_required") or session.status == "complete"
        meta_plan = None
        if session.metadata:
            meta_plan = session.metadata.get("plan") or session.metadata.get("plan_key")
        return {
            "paid": paid,
            "plan": meta_plan,
            "customer_email": session.customer_details.email if session.customer_details else None,
            "session_id": session_id,
        }
    except Exception as exc:
        logger.error("verify_stripe_session error: %s", exc)
        return None
