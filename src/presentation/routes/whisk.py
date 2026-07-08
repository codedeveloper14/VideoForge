from apiflask import APIBlueprint
from flask import jsonify, request, send_file

from src.domain.services import whisk_service
from src.presentation.schemas.whisk import (
    PollinationGenerateInSchema,
    WhiskLoginInSchema,
    WhiskRunPromptsInSchema,
    WhiskSetSubjectInSchema,
)

whisk_bp = APIBlueprint("whisk", __name__, url_prefix="/api/whisk")
pollination_bp = APIBlueprint("pollination", __name__, url_prefix="/api/pollination")

_IMAGE_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _parse_prompts(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(p).strip() for p in raw if str(p).strip()]
    return [p.strip() for p in str(raw or "").splitlines() if p.strip()]


@whisk_bp.get("/status")
def status():
    try:
        return jsonify(whisk_service.get_status())
    except Exception as exc:
        return jsonify({"error": str(exc), "running": False, "step": "idle",
                         "playwright_ok": whisk_service.playwright_installed()})


@whisk_bp.post("/abrir_carpeta")
def abrir_carpeta():
    try:
        path = whisk_service.open_output_folder()
        return jsonify(ok=True, path=path)
    except FileNotFoundError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 500


@whisk_bp.post("/stop")
def stop():
    whisk_service.stop()
    return jsonify(ok=True)


@whisk_bp.get("/images")
def images():
    return jsonify(whisk_service.list_images())


@whisk_bp.get("/image/<name>")
def image(name):
    path = whisk_service.get_image_path(name)
    if not path or not path.exists():
        return "", 404
    resp = send_file(str(path), mimetype=_IMAGE_MIME.get(path.suffix.lower(), "image/png"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@whisk_bp.post("/clear-images")
def clear_images():
    whisk_service.clear_images()
    return jsonify(ok=True)


@whisk_bp.get("/check-login")
def check_login():
    return jsonify(profiles=whisk_service.check_login())


@whisk_bp.post("/login")
@whisk_bp.input(WhiskLoginInSchema)
def login(json_data):
    profile_id = json_data["profile"] or json_data["account_id"]
    profile_id = max(0, min(profile_id, whisk_service.NUM_ACCOUNTS - 1))

    cookie = json_data["cookie"].strip()
    if cookie:
        try:
            result = whisk_service.login_with_cookie(profile_id, cookie)
            return jsonify(ok=True, user=result.get("user", ""))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400

    whisk_service.start_browser_login(profile_id)
    return jsonify(ok=True)


@whisk_bp.route("/set-subject", methods=["POST", "DELETE"])
def set_subject():
    if request.method == "DELETE":
        whisk_service.clear_subject()
        return jsonify(ok=True, cleared=True)

    data = request.get_json(force=True, silent=True) or {}
    b64 = (data.get("image") or "").strip()
    if b64:
        try:
            path = whisk_service.set_subject_b64(b64, data.get("ext", "jpg"))
            return jsonify(ok=True, path=path)
        except Exception as exc:
            return jsonify(error=f"No se pudo decodificar la imagen: {exc}"), 400

    img = request.files.get("image")
    if img:
        path = whisk_service.set_subject_file(img, img.filename)
        return jsonify(ok=True, path=path)

    whisk_service.clear_subject()
    return jsonify(ok=True, cleared=True)


@whisk_bp.post("/run-prompts")
@whisk_bp.input(WhiskRunPromptsInSchema)
def run_prompts(json_data):
    prompts = _parse_prompts(json_data["prompts"])
    try:
        result = whisk_service.run_prompts(prompts, json_data["slots"], json_data["repeat"], json_data["output_dir"])
        return jsonify(ok=True, **result)
    except (ValueError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 400


@pollination_bp.post("/generate")
@pollination_bp.input(PollinationGenerateInSchema)
def pollination_generate(json_data):
    prompts = _parse_prompts(json_data["prompts"])
    try:
        result = whisk_service.pollination_generate(
            prompts, json_data["ratio"], json_data["width"], json_data["height"], json_data["output_dir"],
        )
        return jsonify(ok=True, **result)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 502
    except Exception as exc:
        return jsonify(error=f"Pollination proxy error: {exc}"), 500
