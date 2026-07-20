from src.domain.services.project_service import sanitize_name
from src.infrastructure.storage import project_repository


def save_script(project_name: str, texto: str, prompts: str = "") -> dict:
    name = sanitize_name(project_name)
    texto = (texto or "").strip()
    if not name or not texto:
        raise ValueError("Faltan datos")
    project_repository.write_guion(name, texto, (prompts or "").strip())
    return {"ok": True}


def load_script(project_name: str) -> dict:
    name = sanitize_name(project_name)
    if not name:
        return {"texto": "", "prompts": "", "existe": False}
    texto, prompts, existe = project_repository.read_guion(name)
    return {"texto": texto, "prompts": prompts, "existe": existe}


def list_audio(project_name: str) -> dict:
    name = sanitize_name(project_name)
    if not name:
        return {"existe": False, "archivos": []}
    files = project_repository.list_audio_files(name)
    if not files:
        return {"existe": False, "archivos": []}
    archivos = [f.name for f in files]
    return {"existe": True, "archivos": archivos, "principal": archivos[0]}


def delete_audio(project_name: str, filename: str) -> dict:
    name = sanitize_name(project_name)
    if not name or not filename:
        raise ValueError("Faltan datos")
    path = project_repository.resolve_safe_file(name, "audio", filename)
    if not path:
        raise ValueError("Ruta invalida")
    if not path.is_file():
        raise ValueError("Archivo no encontrado")
    path.unlink()
    return {"ok": True}
