import subprocess
import sys
from pathlib import Path

from src.utils.platform_utils import is_frozen, no_window_kwargs


def _project_root() -> Path:
    if is_frozen():
        # PyInstaller extrae los datos empaquetados (incl. scripts/) bajo sys._MEIPASS.
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[3]


WORKER_SCRIPT = _project_root() / "scripts" / "grok_worker.py"


def build_worker_argv(args: list[str]) -> list[str]:
    """Arma el argv para lanzar scripts/grok_worker.py, compatible con .exe/.app compilados.

    En un ejecutable compilado (PyInstaller) no existe un Python suelto: hay que
    relanzar el mismo binario con --vf-grok-worker para que se comporte como el worker
    en vez de arrancar la app completa (ver main.py).
    """
    if is_frozen():
        return [sys.executable, "--vf-grok-worker", str(WORKER_SCRIPT), *args]
    return [sys.executable, str(WORKER_SCRIPT), *args]


def spawn_worker(args: list[str], cwd: Path) -> subprocess.Popen:
    argv = build_worker_argv(args)
    return subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(cwd),
        env=_child_env(),
        **no_window_kwargs(),
    )


def _child_env() -> dict:
    import os

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env
