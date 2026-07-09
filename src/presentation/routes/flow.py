from apiflask import APIBlueprint
from flask import Response, jsonify, request

from src.domain.services import flow_animation_service
from src.presentation.schemas.flow import FlowProfileDumpQuerySchema
from src.utils.logger import get_logger

logger = get_logger(__name__)

flow_bp = APIBlueprint("flow", __name__, url_prefix="/api/flow")


def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@flow_bp.route("/save-cookie", methods=["POST", "OPTIONS"])
def save_cookie():
    if request.method == "OPTIONS":
        return _cors(Response("", 204))
    data = request.get_json(force=True, silent=True) or {}
    idx = int(data.get("account", data.get("account_id", 0)))
    cookie = (data.get("cookie") or data.get("cookie_str") or "").strip()
    try:
        result = flow_animation_service.save_account_cookie(idx, cookie)
        return _cors(jsonify(result))
    except ValueError as exc:
        return _cors(jsonify({"error": str(exc)})), 400
    except Exception as exc:
        logger.exception("flow save_cookie error")
        return _cors(jsonify({"error": str(exc)})), 500


@flow_bp.get("/profile-dump")
@flow_bp.input(FlowProfileDumpQuerySchema, location="query")
def profile_dump(query_data):
    return _cors(jsonify(flow_animation_service.profile_dump(query_data["idx"])))


@flow_bp.get("/accounts")
def accounts():
    return jsonify({"accounts": flow_animation_service.check_accounts()})
