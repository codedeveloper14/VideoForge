from flask import Blueprint, send_from_directory

from src.utils.paths import get_frontend_dist_dir

frontend_bp = Blueprint("frontend", __name__)


@frontend_bp.get("/")
@frontend_bp.get("/<path:path>")
def serve_frontend(path: str = ""):
    """Sirve el build de React (frontend/dist). Cualquier ruta que no matchee un
    archivo real (rutas de React Router como /app/proyectos) cae a index.html --
    el enrutado real ocurre del lado del cliente."""
    dist_dir = get_frontend_dist_dir()
    index_file = dist_dir / "index.html"
    if not index_file.exists():
        return (
            "Frontend no compilado. Corre `npm run build` en frontend/, o usa "
            "`npm run dev` (puerto 5173) durante el desarrollo.",
            501,
        )

    target = dist_dir / path
    if path and target.is_file():
        return send_from_directory(dist_dir, path)
    return send_from_directory(dist_dir, "index.html")
