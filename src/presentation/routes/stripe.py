from apiflask import APIBlueprint
from flask import jsonify, request

from src.domain.models.plan import PLANS, normalize_plan_key
from src.infrastructure.payments import stripe_service
from src.infrastructure.storage import user_repository
from src.presentation.auth_middleware import get_current_user
from src.presentation.schemas.stripe import StripeCheckoutInSchema

stripe_bp = APIBlueprint("stripe", __name__, url_prefix="/api/stripe")
stripe_pages_bp = APIBlueprint("stripe_pages", __name__)


@stripe_bp.route("/checkout", methods=["GET", "POST"])
@stripe_bp.input(StripeCheckoutInSchema, location="query", arg_name="query_data")
def checkout(query_data):
    """Crea una Stripe Checkout Session y retorna la URL. El success_url incluye session_id para verificacion."""
    username = get_current_user()
    if not username:
        return jsonify({"error": "No autenticado"}), 401

    plan_param = query_data.get("plan") or (request.get_json(silent=True) or {}).get("plan") or ""
    plan_key = normalize_plan_key(plan_param.lower().strip()) if plan_param else None
    if not plan_key or plan_key not in PLANS:
        return jsonify({"error": "Plan inválido"}), 400

    user_info = user_repository.get_user_full(username) or {}
    result = stripe_service.create_checkout_session(username, plan_key, user_info.get("email"))
    return jsonify(result)


@stripe_bp.get("/poll-session")
def poll_session():
    """El frontend llama esto cada N segundos con el session_id para saber si el pago completo."""
    session_id = request.args.get("session_id", "").strip()
    username = get_current_user()
    if not session_id:
        return jsonify({"paid": False, "error": "Sin session_id"}), 400
    if not username:
        return jsonify({"paid": False, "error": "No autenticado"}), 401

    result = stripe_service.verify_stripe_session(session_id)
    if not result or not result.get("paid"):
        return jsonify({"paid": False})

    plan_meta = result.get("plan")
    plan_url = request.args.get("plan", "").lower().strip()
    plan_key = normalize_plan_key(plan_meta or plan_url) if (plan_meta or plan_url) else None

    if plan_key and plan_key in PLANS:
        stripe_service.apply_plan_upgrade(username, plan_key, session_id)
        return jsonify({"paid": True, "plan": plan_key})
    return jsonify({"paid": True, "plan": None})


@stripe_pages_bp.get("/stripe-success")
def stripe_success():
    """Stripe redirige aqui tras completar el pago. Verifica la sesion y activa el plan."""
    session_id = request.args.get("session_id", "").strip()
    plan_param = request.args.get("plan", "").lower().strip()
    username = get_current_user()

    verified = False
    plan_key = None
    error_msg = None

    if session_id:
        result = stripe_service.verify_stripe_session(session_id)
        if result and result["paid"]:
            verified = True
            meta_plan = result.get("plan")
            plan_key = normalize_plan_key(meta_plan or plan_param) if (meta_plan or plan_param) else None

            if not username and result.get("customer_email"):
                username = user_repository.find_username_by_email(result["customer_email"])

            if username and plan_key:
                stripe_service.apply_plan_upgrade(username, plan_key, session_id)
            else:
                error_msg = "No se pudo identificar el usuario. El plan se activará manualmente."
        else:
            error_msg = "El pago no fue confirmado por Stripe."
    else:
        error_msg = "Sesión inválida."

    plan_name = PLANS[plan_key]["name"] if plan_key and plan_key in PLANS else "nuevo"
    is_success = verified and not error_msg

    title = f"¡Plan {plan_name} activado!" if is_success else "Pago recibido"
    message = (
        f"Tu cuenta ya tiene acceso a todas las funciones del plan {plan_name}."
        if is_success
        else (error_msg or "Contacta soporte si el plan no se activa.")
    )
    return (
        (
            f"<!DOCTYPE html><html lang='es'><meta charset='utf-8'>"
            f"<title>Pago completado — Studio IVR</title>"
            f"<body><h1>{title}</h1><p>{message}</p></body></html>"
        ),
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )
