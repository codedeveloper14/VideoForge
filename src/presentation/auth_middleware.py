from flask import g, jsonify, request

from src.core.config import config
from src.domain.services import auth_service

PUBLIC_ROUTES = {
    "/api/login",
    "/api/register",
    "/api/change-password",
    "/api/logout",
    "/api/health",
    "/stripe-success",
    "/favicon.ico",
    # La extension de Chrome llama estas rutas desde la pagina de meta.ai/labs.google,
    # sin cookie de sesion de VideoForge -- deben quedar publicas.
    "/api/meta/ext-register",
    "/api/meta/ext-poll",
    "/api/meta/ext-result",
    "/api/meta/ext-learn",
    "/api/meta/ext-captured",
    "/api/meta/ext-state",
}
PUBLIC_PREFIXES = ("/docs", "/openapi.json", "/redoc")


def _is_public(path: str) -> bool:
    if path in PUBLIC_ROUTES:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def get_current_user() -> str | None:
    token = request.cookies.get(auth_service.SESSION_COOKIE)
    if not token:
        return None
    return auth_service.verify_token(token)


def register_auth_middleware(app) -> None:
    @app.before_request
    def check_auth():
        if _is_public(request.path):
            return None
        user = get_current_user()
        if not user:
            return jsonify({"error": "No autenticado"}), 401
        g._vf_user = user
        return None

    @app.after_request
    def renew_session(response):
        user = getattr(g, "_vf_user", None)
        if user:
            response.set_cookie(
                auth_service.SESSION_COOKIE,
                auth_service.make_token(user),
                httponly=True,
                samesite="Lax",
                secure=False,
                max_age=config.session_minutes * 60,
            )
        return response
