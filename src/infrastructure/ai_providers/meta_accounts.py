import json
import re
from pathlib import Path

ACCOUNT_PREFIX = "meta_cuenta_"


def account_dir(accounts_dir: Path, name: str) -> Path:
    safe = re.sub(r"[^\w\-]", "_", (name or "").strip())
    return accounts_dir / safe


def ensure_accounts(accounts_dir: Path, count: int = 5) -> None:
    accounts_dir.mkdir(parents=True, exist_ok=True)
    existing_nums = set()
    for fd in accounts_dir.iterdir():
        if fd.is_dir():
            m = re.match(rf"{ACCOUNT_PREFIX}(\d+)$", fd.name)
            if m:
                existing_nums.add(int(m.group(1)))
    for i in range(1, count + 1):
        if i not in existing_nums:
            (accounts_dir / f"{ACCOUNT_PREFIX}{i}").mkdir(parents=True, exist_ok=True)
    readme = accounts_dir / "README.txt"
    if not readme.exists():
        readme.write_text(
            "Carpetas de cuentas Meta AI.\n"
            "1) Abre 'Cuentas' en la app.\n"
            "2) Haz clic en 'Login' de cada cuenta.\n"
            "3) Inicia sesion en meta.ai (requiere cuenta Meta/Facebook).\n"
            "4) Cierra la ventana del navegador.\n"
            "Las cookies se guardan en cada carpeta meta_cuenta_X/cookies_auto.json.\n",
            encoding="utf-8",
        )


def load_cookies_list(folder: Path) -> list[dict]:
    ck_file = folder / "cookies_auto.json"
    if not ck_file.exists():
        return []
    try:
        return json.loads(ck_file.read_text())
    except Exception:
        return []


def load_cookies_dict(folder: Path) -> dict:
    items = load_cookies_list(folder)
    return {c["name"]: c["value"] for c in items if isinstance(c, dict)}


def is_authenticated(folder: Path) -> bool:
    """La cookie de sesion es 'ecto_1_s...' - nombre dinamico, siempre empieza con 'ecto'."""
    return any(c.get("name", "").startswith("ecto") for c in load_cookies_list(folder) if isinstance(c, dict))


def delete_session(accounts_dir: Path, account_name: str) -> None:
    ck_file = account_dir(accounts_dir, account_name) / "cookies_auto.json"
    if ck_file.exists():
        ck_file.unlink()


def tokens_for_run(accounts_dir: Path) -> list[tuple[str, list]]:
    result = []
    for folder in sorted(accounts_dir.iterdir()):
        if folder.is_dir() and is_authenticated(folder):
            result.append((folder.name, load_cookies_list(folder)))
    return result


# ─────────────────────────────────────────────────────────────────
# api_state.json (por cuenta) - tokens para el modo HTTP directo
# ─────────────────────────────────────────────────────────────────


def api_state_path(acct_folder: Path) -> Path:
    return acct_folder / "api_state.json"


def load_api_state(acct_folder: Path) -> dict:
    p = api_state_path(acct_folder)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def save_api_state(acct_folder: Path, state: dict) -> None:
    try:
        api_state_path(acct_folder).write_text(json.dumps(state, indent=2))
    except Exception:
        pass


def http_state_complete(api_state: dict) -> bool:
    """True cuando api_state tiene todo lo necesario para generacion HTTP pura."""
    return bool(
        api_state.get("oauth_token")
        and api_state.get("gen_doc_id")
        and api_state.get("gen_variables_template") is not None
    )


# ─────────────────────────────────────────────────────────────────
# Estado global aprendido por la extension (compartido entre cuentas/tabs)
# ─────────────────────────────────────────────────────────────────


class GlobalState:
    """Estado en memoria + persistido de lo que la extension aprendio de la red.

    gen_doc_id/gen_vars_tpl/send_msg_* NUNCA se restauran desde disco al
    arrancar -- deben re-capturarse cada sesion (un doc_id viejo podria ya no
    ser valido). oauth_token/upload_tenant/lax_endpoint si se persisten.
    """

    _PERSISTED_FIELDS = ("oauth_token", "upload_tenant", "lax_endpoint")

    def __init__(self, accounts_dir: Path):
        self._path = accounts_dir / "ext_learned_state.json"
        self._state: dict = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            saved = json.loads(self._path.read_text())
            self._state = {k: saved[k] for k in self._PERSISTED_FIELDS if saved.get(k)}
        except Exception:
            pass

    def _save(self) -> None:
        try:
            self._path.write_text(json.dumps(self._state, indent=2))
        except Exception:
            pass

    def get(self, key, default=None):
        return self._state.get(key, default)

    def learn(self, state: dict) -> None:
        changed = False
        for field in self._PERSISTED_FIELDS:
            value = state.get(field)
            if value and self._state.get(field) != value:
                self._state[field] = value
                changed = True
        if changed:
            self._save()
        if state.get("gen_doc_id"):
            self._state["gen_doc_id"] = state["gen_doc_id"]
            self._state["gen_vars_tpl"] = state.get("gen_vars_tpl", "")
        if state.get("send_msg_did") and state.get("send_msg_tpl"):
            self._state["send_msg_did"] = state["send_msg_did"]
            self._state["send_msg_tpl"] = state["send_msg_tpl"]

    def safe_dict(self) -> dict:
        return {
            k: self._state[k]
            for k in ("oauth_token", "upload_tenant", "gen_doc_id", "gen_vars_tpl")
            if self._state.get(k)
        }
