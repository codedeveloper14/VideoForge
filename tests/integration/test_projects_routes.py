import pytest

from src.infrastructure.storage import project_repository


@pytest.fixture(autouse=True)
def _isolated_jobs_dir(tmp_path, monkeypatch):
    # get_jobs_dir se importa con "from x import y" en project_repository -- hay que
    # parchearlo ahi donde se usa, no en src.utils.paths.
    monkeypatch.setattr(project_repository, "get_jobs_dir", lambda: tmp_path)
    return tmp_path


def test_crear_proyecto(client, login_as):
    login_as()
    resp = client.post("/api/proyectos/crear", json={"nombre": "Mi Proyecto de Prueba"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["nombre"] == "Mi_Proyecto_de_Prueba"


def test_crear_proyecto_nombre_vacio_da_400(client, login_as):
    login_as()
    resp = client.post("/api/proyectos/crear", json={"nombre": "   "})
    assert resp.status_code == 400


def test_listar_proyectos_vacio(client, login_as):
    login_as()
    resp = client.get("/api/proyectos/listar")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_crear_y_listar_proyecto(client, login_as):
    login_as()
    client.post("/api/proyectos/crear", json={"nombre": "proyecto_uno"})
    resp = client.get("/api/proyectos/listar")
    nombres = [p["nombre"] for p in resp.get_json()]
    assert "proyecto_uno" in nombres


def test_borrar_proyecto(client, login_as):
    login_as()
    client.post("/api/proyectos/crear", json={"nombre": "para_borrar"})
    resp = client.post("/api/proyectos/borrar", json={"nombre": "para_borrar"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    resp = client.get("/api/proyectos/listar")
    assert "para_borrar" not in [p["nombre"] for p in resp.get_json()]


def test_imagen_file_bloquea_traversal(client, login_as):
    login_as()
    client.post("/api/proyectos/crear", json={"nombre": "seguridad_test"})
    resp = client.get("/api/proyectos/imagen_file",
                       query_string={"project": "seguridad_test", "file": "../../../etc/passwd"})
    assert resp.status_code == 404


def test_video_final_bloquea_traversal(client, login_as):
    login_as()
    client.post("/api/proyectos/crear", json={"nombre": "seguridad_test2"})
    resp = client.get("/api/proyectos/video_final",
                       query_string={"project": "seguridad_test2", "file": "../../../etc/passwd", "dl": "0"})
    assert resp.status_code == 404


def test_rutas_de_proyectos_requieren_auth(client):
    assert client.get("/api/proyectos/listar").status_code == 401
    assert client.post("/api/proyectos/crear", json={"nombre": "x"}).status_code == 401
