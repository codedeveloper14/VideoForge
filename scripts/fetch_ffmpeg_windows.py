#!/usr/bin/env python3
"""
fetch_ffmpeg_windows.py — Descarga ffmpeg/ffprobe (Windows x64) para bundlear en el
instalador, en vez de depender del PATH del sistema del cliente final (que no tiene
ffmpeg instalado por defecto -- ver auditoria de empaquetado).

Usa el build "essentials" de gyan.dev (GPL, incluye libx264 -- el build LGPL no lo
trae, y ffmpeg_utils.h264_encode_args() lo necesita). NO usar el build "full"
(~700MB con ffplay incluido, que no usamos) -- "essentials" (~200MB) alcanza.

Corre esto ANTES de studioivr.spec / PyInstaller. Genera vendor/ffmpeg/win64/
(gitignored, build-time) con ffmpeg.exe, ffprobe.exe y LICENSE.

Uso:
  python scripts/fetch_ffmpeg_windows.py
"""
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
ROOT = Path(__file__).resolve().parent.parent
DEST_DIR = ROOT / "vendor" / "ffmpeg" / "win64"


def main() -> int:
    if (DEST_DIR / "ffmpeg.exe").is_file() and (DEST_DIR / "ffprobe.exe").is_file():
        print(f"[fetch_ffmpeg] Ya existe en {DEST_DIR} -- nada que hacer (borra la carpeta para forzar re-descarga).")
        return 0

    with tempfile.TemporaryDirectory(prefix="vf_ffmpeg_fetch_") as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "ffmpeg.zip"

        print(f"[fetch_ffmpeg] Descargando {FFMPEG_URL} ...")
        try:
            urllib.request.urlretrieve(FFMPEG_URL, zip_path)
        except Exception as exc:
            print(f"[fetch_ffmpeg] [ERROR] Descarga fallo: {exc}", file=sys.stderr)
            return 1

        size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"[fetch_ffmpeg] Descargado ({size_mb:.1f} MB). Extrayendo...")

        extract_dir = tmp_path / "extracted"
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

        # El zip trae una unica carpeta raiz tipo "ffmpeg-7.1-essentials_build".
        candidates = [d for d in extract_dir.iterdir() if d.is_dir()]
        if len(candidates) != 1:
            print(
                f"[fetch_ffmpeg] [ERROR] Se esperaba 1 carpeta raiz en el zip, se encontraron {len(candidates)}.",
                file=sys.stderr,
            )
            return 1
        build_dir = candidates[0]

        ffmpeg_exe = build_dir / "bin" / "ffmpeg.exe"
        ffprobe_exe = build_dir / "bin" / "ffprobe.exe"
        license_file = build_dir / "LICENSE"
        for f in (ffmpeg_exe, ffprobe_exe):
            if not f.is_file():
                print(f"[fetch_ffmpeg] [ERROR] No encontrado en el build: {f}", file=sys.stderr)
                return 1

        DEST_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ffmpeg_exe, DEST_DIR / "ffmpeg.exe")
        shutil.copy2(ffprobe_exe, DEST_DIR / "ffprobe.exe")
        if license_file.is_file():
            shutil.copy2(license_file, DEST_DIR / "LICENSE")

    final_size_mb = sum(f.stat().st_size for f in DEST_DIR.iterdir()) / (1024 * 1024)
    print(f"[fetch_ffmpeg] OK -- {DEST_DIR} ({final_size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
