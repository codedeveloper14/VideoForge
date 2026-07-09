"""Orquestacion de Flow: estado compartido + cuentas/cookies (Etapa A). El bridge
WS/HTTP y el motor de generacion por lotes se agregan en etapas posteriores y
extienden el mismo `_state`."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor

from src.infrastructure.ai_providers import flow_service
from src.utils.logger import get_logger
from src.utils.paths import get_flow_profiles_dir

logger = get_logger(__name__)

state = {
    "running": False, "step": "idle", "progress": 0, "total": 0,
    "images_saved": 0, "log": [], "last_error": None, "output_dir": None,
    "accounts": [{"index": i, "ok": False, "email": None, "jobs": 0}
                 for i in range(flow_service.NUM_ACCOUNTS)],
}
lock = threading.Lock()


def log(msg: str) -> None:
    with lock:
        state["log"].append(msg)
        if len(state["log"]) > 600:
            state["log"] = state["log"][-600:]
    logger.info("[flow] %s", msg)


def save_account_cookie(idx: int, cookie: str) -> dict:
    idx = max(0, min(idx, flow_service.NUM_ACCOUNTS - 1))
    cookie = (cookie or "").strip()
    if not cookie:
        raise ValueError("cookie vacio")

    flow_service.save_cookie(idx, cookie)
    sess = flow_service.get_session(cookie)
    email = sess.get("email", "")
    ok = bool(sess.get("bearer", ""))
    if ok:
        acc_hash = flow_service.account_hash(email)
        with lock:
            state["accounts"][idx].update({"ok": True, "email": email})
        return {"ok": True, "email": email, "hash": acc_hash}
    return {"ok": False, "error": "Cookie invalida o sesion expirada"}


def check_accounts() -> list[dict]:
    def _check_one(i):
        ck = flow_service.load_cookie(i)
        acc = {"index": i, "ok": False, "email": None, "cookie": bool(ck)}
        if not ck:
            return i, acc
        sess = flow_service.get_session(ck)
        bearer = sess.get("bearer", "")
        email = sess.get("email", "") or f"Cuenta {i + 1}"
        if bearer:
            acc["ok"] = True
            acc["email"] = f"{email} ok"
            with lock:
                state["accounts"][i].update({"ok": True, "email": acc["email"]})
        else:
            acc["ok"] = False
            acc["email"] = f"Cuenta {i + 1} - sesion expirada"
            with lock:
                state["accounts"][i].update({"ok": False})
        return i, acc

    result: list[dict | None] = [None] * flow_service.NUM_ACCOUNTS
    with ThreadPoolExecutor(max_workers=flow_service.NUM_ACCOUNTS) as ex:
        for i, acc in ex.map(_check_one, range(flow_service.NUM_ACCOUNTS)):
            result[i] = acc
    return result


def profile_dump(idx: int) -> dict:
    """Diagnostico: lista los archivos del perfil de Chromium de una cuenta."""
    profile_dir = str(get_flow_profiles_dir() / f"flow_profile_{idx}")
    result: dict = {"profile_dir": profile_dir, "files": [], "local_state_keys": []}

    for root, dirs, files in os.walk(profile_dir):
        depth = root.replace(profile_dir, "").count(os.sep)
        if depth > 2:
            dirs.clear()
            continue
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), profile_dir)
            try:
                size = os.path.getsize(os.path.join(root, f))
            except Exception:
                size = 0
            result["files"].append({"path": rel, "size": size})

    ls_path = os.path.join(profile_dir, "Local State")
    if os.path.isfile(ls_path):
        try:
            import json
            with open(ls_path, "r", encoding="utf-8") as f:
                ls = json.load(f)
            result["local_state_keys"] = list(ls.keys())
        except Exception:
            pass

    return result
