import re

from apiflask import APIBlueprint
from flask import jsonify, make_response, request

from src.core.config import config
from src.domain.models.plan import normalize_plan_key
from src.domain.services import auth_service
from src.presentation.auth_middleware import get_current_user
from src.presentation.schemas.auth import (
    ChangePasswordInSchema,
    LoginInSchema,
    MeOutSchema,
    RegisterInSchema,
)

auth_bp = APIBlueprint("auth", __name__, url_prefix="/api")


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _session_response(payload: dict, username: str):
    resp = make_response(jsonify(payload))
    resp.set_cookie(
        auth_service.SESSION_COOKIE,
        auth_service.make_token(username),
        httponly=True, samesite="Lax", secure=config.session_cookie_secure,
        max_age=config.session_minutes * 60,
    )
    return resp


@auth_bp.post("/login")
@auth_bp.input(LoginInSchema)
def login(json_data):
    ip = _client_ip()
    locked, secs = auth_service.is_locked_out(ip)
    if locked:
        mins = secs // 60
        return jsonify({"ok": False, "lockout": True,
                         "error": f"Demasiados intentos. Espera {mins}m {secs % 60}s."}), 429

    username = json_data["username"].strip()
    password = json_data["password"]

    user, err = auth_service.authenticate_user(username, password)
    if not user:
        auth_service.register_fail(ip)
        locked2, secs2 = auth_service.is_locked_out(ip)
        if locked2:
            mins2 = secs2 // 60
            return jsonify({"ok": False, "lockout": True,
                             "error": f"Cuenta bloqueada por {mins2}m {secs2 % 60}s."}), 429
        return jsonify({"ok": False, "error": err or "Credenciales incorrectas"}), 401

    auth_service.clear_fails(ip)

    if user["must_change_password"]:
        return jsonify({"ok": True, "must_change_password": True, "user": user["username"]})

    return _session_response({"ok": True, "user": user["username"]}, user["username"])


@auth_bp.post("/change-password")
@auth_bp.input(ChangePasswordInSchema)
def change_password_route(json_data):
    username = json_data["username"].strip()
    new_password = json_data["new_password"]

    if new_password == "1234":
        return jsonify({"ok": False, "error": "No puedes usar la contraseña temporal"}), 400

    ok, err = auth_service.change_password(username, new_password)
    if not ok:
        status = 404 if err and "no encontrado" in err else 500
        return jsonify({"ok": False, "error": err}), status

    return _session_response({"ok": True}, username)


@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(auth_service.SESSION_COOKIE)
    return resp


@auth_bp.post("/register")
@auth_bp.input(RegisterInSchema)
def register(json_data):
    username = json_data["username"].strip()
    email = json_data["email"].strip().lower()
    password = json_data["password"]
    plan = normalize_plan_key(json_data.get("plan") or "basico")

    if not re.match(r"^[a-zA-Z0-9_]{3,20}$", username):
        return jsonify({"ok": False, "error": "Usuario: 3-20 caracteres (letras, números y _)"}), 400
    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"ok": False, "error": "Correo electrónico inválido"}), 400

    ok, err = auth_service.register_user(username, email, password, plan)
    if not ok:
        status = 409 if err and ("en uso" in err or "registrado" in err) else 500
        return jsonify({"ok": False, "error": err}), status

    return _session_response({"ok": True, "user": username}, username)


@auth_bp.get("/auth/me")
@auth_bp.output(MeOutSchema)
def me():
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False}), 401
    return {"authenticated": True, "username": user}
