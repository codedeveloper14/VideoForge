import json
import os
import platform
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable

from src.utils.logger import get_logger

logger = get_logger(__name__)


def _NoOpLog(msg: str) -> None:
    pass


# ─────────────────────────────────────────────────────────────────
# Foco automatico de la ventana de Chrome (Windows only)
# ─────────────────────────────────────────────────────────────────
# Ninguna extension de Chrome puede forzar que el SO le devuelva el foco si
# el usuario esta trabajando en otra ventana -- Windows bloquea ese tipo de
# robo de foco desde apps en 2do plano. Un proceso nativo SI puede, usando
# el truco de simular una tecla (ALT) justo antes de SetForegroundWindow.
# No aplica en macOS -- todas las funciones de esta seccion son no-op ahi.

_chrome_pids: set[int] = set()
_chrome_pids_lock = threading.Lock()
FOCUS_EVERY_N_JOBS = 14


def register_chrome_pid(pid: int) -> None:
    with _chrome_pids_lock:
        _chrome_pids.add(pid)


def unregister_chrome_pid(pid: int) -> None:
    with _chrome_pids_lock:
        _chrome_pids.discard(pid)


def _collect_descendant_pids(pid: int) -> set[int]:
    pids = {pid}
    try:
        import psutil

        try:
            proc = psutil.Process(pid)
            for child in proc.children(recursive=True):
                pids.add(child.pid)
        except psutil.NoSuchProcess:
            pass
    except Exception:
        try:
            out = subprocess.run(
                ["wmic", "process", "where", f"(ParentProcessId={pid})", "get", "ProcessId"],
                capture_output=True,
                text=True,
                timeout=3,
            ).stdout
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.add(int(line))
        except Exception:
            pass
    return pids


def bring_pid_to_front(pid: int, log: Callable[[str], None] = _NoOpLog) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        target_pids = _collect_descendant_pids(pid)
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def enum_cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            win_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(win_pid))
            if win_pid.value in target_pids and user32.GetWindowTextLengthW(hwnd) > 0:
                found.append(hwnd)
            return True

        user32.EnumWindows(enum_cb, 0)
        if not found:
            log(
                f"[WARNING] [focus] ninguna ventana visible coincide con PID {pid} "
                f"ni sus {len(target_pids) - 1} hijo(s)"
            )
            return False
        hwnd = found[0]

        SW_RESTORE = 9
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)

        VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        ok = bool(user32.SetForegroundWindow(hwnd))
        log(
            f"[focus] ventana de Chrome (PID {pid}) puesta en primer plano"
            if ok
            else f"[WARNING] [focus] SetForegroundWindow devolvio False para PID {pid}"
        )
        return ok
    except Exception as exc:
        log(f"[WARNING] [focus] excepcion robando el foco (PID {pid}): {exc}")
        return False


def focus_loop(
    get_running: Callable[[], bool], get_downloaded: Callable[[], int], log: Callable[[str], None] = _NoOpLog
) -> None:
    """Corre en un hilo daemon; roba el foco 1 vez cada FOCUS_EVERY_N_JOBS videos
    descargados (no cada N segundos -- confirmado molesto e inefectivo)."""
    if sys.platform != "win32":
        return
    import time

    state = {"last_done": 0, "was_running": False}
    while True:
        try:
            running_now = get_running()
            if running_now and not state["was_running"]:
                state["last_done"] = 0
            state["was_running"] = running_now
            if running_now:
                done = get_downloaded()
                if done - state["last_done"] >= FOCUS_EVERY_N_JOBS:
                    state["last_done"] = done
                    with _chrome_pids_lock:
                        pids = list(_chrome_pids)
                    log(f"[focus] {done} video(s) listos - robando foco una vez")
                    for pid in pids:
                        if bring_pid_to_front(pid, log):
                            break
        except Exception as exc:
            try:
                log(f"[WARNING] [focus] excepcion en focus_loop: {exc}")
            except Exception:
                pass
        time.sleep(3)


# ─────────────────────────────────────────────────────────────────
# Deteccion de procesos Chrome/Chromium (Windows: wmic, macOS: ps)
# ─────────────────────────────────────────────────────────────────


def wmic_lines() -> list[str]:
    """CommandLine de procesos chrome/chromium. Solo Windows; vacio en macOS/Linux."""
    if platform.system() != "Windows":
        return []
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='chrome.exe' or name='chromium.exe'", "get", "CommandLine"],
            capture_output=True,
            text=True,
            timeout=6,
            creationflags=0x08000000,
        )
        return [line.replace("\\", "/").lower() for line in r.stdout.splitlines()]
    except Exception:
        return []


def ps_mac_lines() -> list[str]:
    """Argumentos de procesos Chrome/Chromium via 'ps'. Solo macOS."""
    if platform.system() != "Darwin":
        return []
    try:
        r = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=6)
        return [
            line for line in r.stdout.splitlines() if "chrome" in line.lower() or "chromium" in line.lower()
        ]
    except Exception:
        return []


def chrome_type_for_profile(profile_dir: str, launched_procs: dict) -> str:
    """'batch' (lanzado por nosotros o detectado corriendo), 'playwright'
    (detectado por --remote-debugging-pipe, usado durante login), o 'none'."""
    proc = launched_procs.get(profile_dir)
    if proc and proc.poll() is None:
        return "batch"
    pd = profile_dir.replace("\\", "/").lower()
    for line in wmic_lines():
        if pd in line:
            return "playwright" if "--remote-debugging-pipe" in line else "batch"
    for line in ps_mac_lines():
        if pd in line:
            return "playwright" if "--remote-debugging-pipe" in line else "batch"
    return "none"


def clean_profile_for_fresh_start(profile_dir: str, log: Callable[[str], None] = _NoOpLog) -> None:
    """Borra archivos de sesion previa y fuerza inicio con una sola pestana limpia."""
    default_dir = os.path.join(profile_dir, "Default")
    os.makedirs(default_dir, exist_ok=True)
    removed = []
    for sf in ("Last Session", "Last Tabs", "Current Session", "Current Tabs", "Sessions"):
        sp = os.path.join(default_dir, sf)
        try:
            if os.path.isfile(sp):
                os.remove(sp)
                removed.append(sf)
            elif os.path.isdir(sp):
                shutil.rmtree(sp, ignore_errors=True)
                removed.append(sf + "/")
        except Exception:
            pass
    prefs_path = os.path.join(default_dir, "Preferences")
    try:
        prefs = {}
        if os.path.exists(prefs_path):
            with open(prefs_path, encoding="utf-8", errors="ignore") as pf:
                prefs = json.load(pf)
        prefs.setdefault("profile", {})["exit_type"] = "Normal"
        prefs.setdefault("session", {})["restore_on_startup"] = 5
        with open(prefs_path, "w", encoding="utf-8") as pf:
            json.dump(prefs, pf, indent=2)
    except Exception:
        pass
    log("Sesion limpiada" + (f" (borrados: {', '.join(removed)})" if removed else " (sin archivos previos)"))


def launch_chrome_with_extension(
    exe: str,
    profile_dir: str,
    extension_dirs: list[str],
    urls: list[str],
    extra_args: list[str] | None = None,
) -> subprocess.Popen:
    ext_list = ",".join(extension_dirs)
    args = [
        exe,
        f"--user-data-dir={profile_dir}",
        f"--disable-extensions-except={ext_list}",
        f"--load-extension={ext_list}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        *(extra_args or []),
        *urls,
    ]
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
