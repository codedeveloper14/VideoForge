import glob
import os
import sys
from pathlib import Path

from src.utils.platform_utils import is_frozen


def _app_base_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[3]


def get_extension_dir() -> Path:
    """Directorio de extensions/flow_extension empaquetado con la app.

    A diferencia del original (que buscaba manifest.json/meta_bridge.js en
    varias ubicaciones posibles por como copiaba el build), aqui la ubicacion
    es fija y conocida porque el nuevo empaquetado la controla directamente.
    """
    base = _app_base_dir()
    candidate = base / "extensions" / "flow_extension"
    if candidate.is_dir():
        return candidate
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        frozen_candidate = Path(meipass) / "extensions" / "flow_extension"
        if frozen_candidate.is_dir():
            return frozen_candidate
    return candidate


def find_chromium_exe() -> str | None:
    """Busca Chromium/Chrome priorizando Playwright (unico que acepta
    --load-extension sin restricciones). Cross-platform: Windows y macOS."""
    local_appdata = os.environ.get("LOCALAPPDATA", "") or str(Path.home() / "AppData" / "Local")
    home = str(Path.home())
    appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    program_dir = os.path.join(appdata, "VideoForge")
    exe_dir = str(_app_base_dir())

    # 1. Playwright Chromium (Windows)
    for pat in [
        os.path.join(local_appdata, "ms-playwright", "chromium-*", "chrome-win", "chrome.exe"),
        os.path.join(local_appdata, "ms-playwright", "chromium-*", "chrome-win64", "chrome.exe"),
        os.path.join(local_appdata, "ms-playwright", "chromium-*", "chrome-win32", "chrome.exe"),
        os.path.join(home, "AppData", "Local", "ms-playwright", "chromium-*", "chrome-win*", "chrome.exe"),
    ]:
        found = sorted(glob.glob(pat))
        if found:
            return found[-1]

    # 2. Chromium portable junto al ejecutable
    for rel in [
        os.path.join(exe_dir, "chromium", "chrome.exe"),
        os.path.join(exe_dir, "chrome", "chrome.exe"),
        os.path.join(exe_dir, "chromium-win", "chrome.exe"),
    ]:
        if os.path.isfile(rel):
            return rel

    # 3. Chromium del sistema (Windows)
    for candidate in [
        os.path.join(program_dir, "Chromium", "Application", "chrome.exe"),
        os.path.join(local_appdata, "Chromium", "Application", "chrome.exe"),
        os.path.join(local_appdata, "Chromium", "chrome.exe"),
    ]:
        if os.path.isfile(candidate):
            return candidate

    # 4. Google Chrome del sistema (Windows) — ultimo recurso, puede no soportar --load-extension
    for candidate in [
        os.path.join(program_dir, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(local_appdata, "Google", "Chrome", "Application", "chrome.exe"),
    ]:
        if os.path.isfile(candidate):
            return candidate

    # 5. Playwright Chromium (macOS)
    for cache_base in (
        os.path.expanduser("~/Library/Caches/ms-playwright"),
        os.path.expanduser("~/.cache/ms-playwright"),
    ):
        for pat in [
            os.path.join(
                cache_base, "chromium-*", "chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium"
            ),
            os.path.join(
                cache_base, "chromium-*", "chrome-mac-arm", "Chromium.app", "Contents", "MacOS", "Chromium"
            ),
        ]:
            hits = sorted(glob.glob(pat))
            if hits:
                return hits[-1]

    # 6. Chrome/Chromium del sistema (macOS)
    for candidate in [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
        os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        os.path.expanduser("~/Applications/Chromium.app/Contents/MacOS/Chromium"),
    ]:
        if os.path.isfile(candidate):
            return candidate

    return None
