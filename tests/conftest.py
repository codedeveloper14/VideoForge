"""Fixtures compartidas.

Las pruebas unitarias (tests/unit) son puras -- sin DB, sin red, sin Flask app.

Las de integracion (tests/integration) usan la fixture `client` de aca abajo: crea
la app Flask REAL (con todas las rutas/blueprints reales, para probar la integracion
de verdad) pero evita tocar la base de datos de produccion o levantar servidores de
fondo (WS de Flow, sync de Gentube) -- esos efectos secundarios de create_app() se
neutralizan antes de construir la app. Cada test que necesita datos "de base de datos"
mockea la funcion puntual del repositorio con `monkeypatch`, no la conexion completa."""

import pytest


@pytest.fixture
def app(monkeypatch):
    # create_app() en produccion hace DDL real y arranca hilos/servidores de fondo --
    # ninguno de los dos es deseable en un test que corre repetidamente. Los nombres
    # importados con "from x import y" hay que parchearlos donde se USAN (el modulo
    # que hizo el import), no en su modulo de origen -- si no, el parche no aplica.
    monkeypatch.setattr("src.presentation.app.ensure_tables", lambda: None)
    monkeypatch.setattr("src.presentation.app.ensure_stripe_table", lambda: None)
    monkeypatch.setattr("src.infrastructure.storage.docs_repository.ensure_tables", lambda: None)
    monkeypatch.setattr("src.domain.services.gentube_animation_service.sync_profiles_async", lambda: None)
    monkeypatch.setattr("src.infrastructure.ai_providers.flow_bridge.start_ws_server", lambda *a, **kw: None)

    from src.presentation.app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login_as(client, monkeypatch):
    """Factory fixture: login_as() -> "usuario_test" logueado (cookie de sesion real
    en el jar del test client). Mockea solo la consulta de credenciales -- el resto
    del flujo (hash/verify, token firmado, cookie) corre real."""

    def _do(username="usuario_test", password="clave-correcta-123", role="user", ip="203.0.113.99"):
        from src.domain.services import auth_service
        from src.infrastructure.storage import user_repository

        monkeypatch.setattr(
            user_repository,
            "get_user_for_auth",
            lambda u: (1, u, auth_service.hash_password(password), role, 1, 0),
        )
        resp = client.post(
            "/api/login",
            json={"username": username, "password": password},
            environ_overrides={"REMOTE_ADDR": ip},
        )
        assert resp.status_code == 200, resp.get_json()
        auth_service.clear_fails(ip)
        return username

    return _do
