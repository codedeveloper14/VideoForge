#!/usr/bin/env python3
"""
fetch_chromium_windows.py — Prepara un Chromium (Windows x64) para bundlear en el
instalador, en vez de depender de que el cliente final tenga Chrome instalado y de
que su Chrome acepte --load-extension (ver auditoria de empaquetado -- Qwen, Vibes,
Flow y GenTube dependen todos de chrome_launcher.find_chromium_exe()).

Reusa el Chromium que Playwright ya gestiona (misma version que se prueba en dev):
si no esta descargado, corre "playwright install chromium" primero. Copia SOLO
chrome-win64/ (416MB) -- descarta chromium_headless_shell (no lo usamos, headless=True
lanza el chrome.exe normal con un flag), el ffmpeg interno de Playwright (no es el
que usa la app) y winldd (solo hace falta durante el install). Poda ademas los
locales de Chromium a es-ES/en-US (43MB -> ~2MB) -- Chromium cae a en-US si falta
un locale, no rompe nada.

Corre esto ANTES de studioivr.spec / PyInstaller. Genera vendor/chromium/win64/
(gitignored, build-time).

Uso:
  python scripts/fetch_chromium_windows.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST_DIR = ROOT / "vendor" / "chromium" / "win64"
KEEP_LOCALES = {"es-ES.pak", "es-419.pak", "en-US.pak"}


def _ms_playwright_cache() -> Path:
    import os

    local_appdata = os.environ.get("LOCALAPPDATA", "") or str(Path.home() / "AppData" / "Local")
    return Path(local_appdata) / "ms-playwright"


def _find_chrome_win64() -> Path | None:
    cache = _ms_playwright_cache()
    if not cache.is_dir():
        return None
    candidates = sorted(cache.glob("chromium-*/chrome-win64/chrome.exe"))
    return candidates[-1].parent if candidates else None


def _ensure_playwright_chromium_installed() -> None:
    print("[fetch_chromium] Chromium de Playwright no encontrado -- corriendo 'playwright install chromium'...")
    res = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    if res.returncode != 0:
        raise RuntimeError(f"'playwright install chromium' fallo (exit {res.returncode})")


def _prune_locales(chrome_win64_dest: Path) -> None:
    locales_dir = chrome_win64_dest / "locales"
    if not locales_dir.is_dir():
        return
    removed, kept = 0, 0
    for pak in locales_dir.glob("*.pak"):
        if pak.name in KEEP_LOCALES:
            kept += 1
            continue
        pak.unlink()
        removed += 1
    print(f"[fetch_chromium] Locales podados: {removed} eliminados, {kept} conservados ({sorted(KEEP_LOCALES)}).")


def main() -> int:
    if (DEST_DIR / "chrome.exe").is_file():
        print(f"[fetch_chromium] Ya existe en {DEST_DIR} -- nada que hacer (borra la carpeta para forzar re-copia).")
        return 0

    src_dir = _find_chrome_win64()
    if src_dir is None:
        try:
            _ensure_playwright_chromium_installed()
        except Exception as exc:
            print(f"[fetch_chromium] [ERROR] {exc}", file=sys.stderr)
            return 1
        src_dir = _find_chrome_win64()
        if src_dir is None:
            print(
                "[fetch_chromium] [ERROR] Chromium sigue sin aparecer en la cache de Playwright tras el install.",
                file=sys.stderr,
            )
            return 1

    print(f"[fetch_chromium] Copiando {src_dir} -> {DEST_DIR} ...")
    DEST_DIR.parent.mkdir(parents=True, exist_ok=True)
    if DEST_DIR.exists():
        shutil.rmtree(DEST_DIR)
    shutil.copytree(src_dir, DEST_DIR)

    _prune_locales(DEST_DIR)

    total_mb = sum(f.stat().st_size for f in DEST_DIR.rglob("*") if f.is_file()) / (1024 * 1024)
    print(f"[fetch_chromium] OK -- {DEST_DIR} ({total_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
