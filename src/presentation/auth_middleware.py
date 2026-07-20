from flask import g, jsonify, request

from src.core.config import config
from src.domain.services import auth_service

PUBLIC_ROUTES = {
    "/api/login",
    "/api/register",
    "/api/change-password",
    "/api/logout",
    "/api/health",
    "/api/updates/check",
    "/stripe-success",
    "/favicon.ico",
    # Contenido del centro de ayuda: publico en el original (sin auth), igual aqui.
    "/api/docs",
    "/api/help",
    # La extension de Chrome llama estas rutas desde la pagina de meta.ai/labs.google,
    # sin cookie de sesion de VideoForge -- deben quedar publicas.
    "/api/meta/ext-register",
    "/api/meta/ext-poll",
    "/api/meta/ext-result",
    "/api/meta/ext-learn",
    "/api/meta/ext-captured",
    "/api/meta/ext-state",
    # La extension de vibes.ai (vibes_bridge.js) hace polling desde la pagina de
    # vibes.ai, sin cookie de sesion de VideoForge -- misma razon que ext-* arriba.
    "/api/meta/vibes-poll",
    "/api/meta/vibes-result",
    # La extension de Flow envia la cookie desde su propio popup, misma razon
    # que las rutas ext-* de Meta arriba: no hay cookie de sesion de VideoForge.
    "/api/flow/save-cookie",
}
PUBLIC_PREFIXES = ("/docs", "/openapi.json", "/redoc")


def _is_public(path: str) -> bool:
    # Todo lo que no sea /api/* es el frontend (React) servido estatico, o Swagger --
    # ninguno de los dos expone datos sensibles del lado del servidor. El SPA hace su
    # propio chequeo de sesion via /api/auth/me y redirige a /login si hace falta;
    # bloquear aqui la carga del index.html rompe la app entera antes de que React
    # pueda siquiera mostrar la pantalla de login.
    if not path.startswith("/api"):
        return True
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
        # Un preflight CORS nunca lleva cookies de sesion (el browser lo envia sin
        # credenciales por diseno) -- bloquearlo con 401 rompe el CORS real para
        # cualquier ruta que necesite responder a peticiones cross-origin.
        if request.method == "OPTIONS":
            return None
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
                secure=config.session_cookie_secure,
                max_age=config.session_minutes * 60,
            )
        return response
