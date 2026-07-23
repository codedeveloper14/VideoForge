import os

from src.infrastructure.storage import project_repository as repo


def test_sanitize_name_reemplaza_caracteres_especiales():
    assert repo.sanitize_name("mi proyecto #1!") == "mi_proyecto__1_"


def test_sanitize_name_trunca_a_60_caracteres():
    assert len(repo.sanitize_name("a" * 200)) == 60


def test_sanitize_name_con_vacio_o_none():
    assert repo.sanitize_name("") == ""
    assert repo.sanitize_name(None) == ""


def test_project_dir_sanitiza_intento_de_escape():
    jobs_dir = repo.get_jobs_dir().resolve()
    proj = repo.project_dir("../../../../etc/passwd")
    # Pase lo que pase con el nombre, el resultado siempre debe quedar DENTRO de jobs/.
    assert jobs_dir in proj.resolve().parents or proj.resolve() == jobs_dir
    assert ".." not in proj.name


def test_project_dir_mismo_nombre_da_mismo_path():
    assert repo.project_dir("mi_proyecto") == repo.project_dir("mi_proyecto")


def test_resolve_safe_file_normal_dentro_del_proyecto():
    path = repo.resolve_safe_file("proyecto_test", "imagen", "foto.png")
    assert path is not None
    expected_base = (repo.project_dir("proyecto_test") / "imagen").resolve()
    assert path.parent == expected_base


def test_resolve_safe_file_bloquea_traversal_con_puntos():
    path = repo.resolve_safe_file("proyecto_test", "imagen", "../../../../windows/system32/config")
    assert path is None


def test_resolve_safe_file_bloquea_traversal_absoluto():
    # "C:\Windows\..." solo se interpreta como ruta absoluta en Windows -- en POSIX
    # (Mac/Linux) esa cadena con backslashes es un simple nombre de archivo raro
    # (pathlib POSIX no separa por "\"), y el ataque real ahi es "/etc/passwd".
    attack = "C:\\Windows\\System32\\config" if os.name == "nt" else "/etc/passwd"
    path = repo.resolve_safe_file("proyecto_test", "imagen", attack)
    assert path is None
