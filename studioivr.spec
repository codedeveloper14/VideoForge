# -*- mode: python ; coding: utf-8 -*-
# Empaqueta Studio IVR (VideoForge) para Windows -- SOLO Windows, no sirve para Mac
# (eso necesita build-mac.yml corriendo en macOS real, con universal2 aparte).
#
# Antes de correr este spec: ofuscar con PyArmor.
#   pyarmor gen -O build/pyarmor_dist -r main.py src desktop scripts
#
# own_package_modules() existe porque PyArmor reescribe los imports de nuestro
# propio codigo para que no sean literales en el AST -- PyInstaller no los ve por
# analisis estatico, y collect_submodules() falla parcial y en silencio en cuanto
# un submodulo tira una excepcion al importarse (paso con 'src.domain'). Caminar el
# arbol de archivos evita ambos problemas.
import os
import sys

from PyInstaller.utils.hooks import collect_all

OBF_DIR = "build/pyarmor_dist"

# ffmpeg/chromium bundleados -- ver scripts/fetch_ffmpeg_windows.py y
# scripts/fetch_chromium_windows.py (correr AMBOS antes de este spec). Sin esto el
# instalador queda dependiendo del PATH del cliente final (ffmpeg) o de que tenga
# Chrome instalado y acepte --load-extension (Qwen/Vibes/Flow/GenTube) -- ver
# auditoria de empaquetado. Aborta el build en vez de producir un .exe silenciosamente
# roto para cualquier usuario que instale desde cero.
VENDOR_FFMPEG_DIR = "vendor/ffmpeg/win64"
VENDOR_CHROMIUM_DIR = "vendor/chromium/win64"
if not os.path.isfile(os.path.join(VENDOR_FFMPEG_DIR, "ffmpeg.exe")):
    print(
        f"[studioivr.spec] ERROR: falta {VENDOR_FFMPEG_DIR}/ffmpeg.exe -- "
        "corre 'python scripts/fetch_ffmpeg_windows.py' antes de compilar.",
        file=sys.stderr,
    )
    sys.exit(1)
if not os.path.isfile(os.path.join(VENDOR_CHROMIUM_DIR, "chrome.exe")):
    print(
        f"[studioivr.spec] ERROR: falta {VENDOR_CHROMIUM_DIR}/chrome.exe -- "
        "corre 'python scripts/fetch_chromium_windows.py' antes de compilar.",
        file=sys.stderr,
    )
    sys.exit(1)


def own_package_modules(package_dir: str) -> list[str]:
    package_name = os.path.basename(package_dir.rstrip("/\\"))
    root = os.path.join(OBF_DIR, package_name)
    modules = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fname), OBF_DIR)
            dotted = rel[: -len(".py")].replace(os.sep, ".")
            if dotted.endswith(".__init__"):
                dotted = dotted[: -len(".__init__")]
            modules.append(dotted)
    return modules


own_hidden = own_package_modules("src") + own_package_modules("desktop")

datas = [
    ("frontend/dist", "frontend_dist"),
    ("assets", "assets"),
    ("extensions/flow_extension", "extensions/flow_extension"),
    (f"{OBF_DIR}/pyarmor_runtime_012301", "pyarmor_runtime_012301"),
    # Nunca se importa -- main.py lo relanza con runpy.run_path() sobre una ruta
    # real de disco, tiene que existir suelto, no compilado dentro del PYZ.
    (f"{OBF_DIR}/scripts/grok_worker.py", "scripts"),
    # ffmpeg.exe/ffprobe.exe reales -- ver get_bundled_ffmpeg_dir()/ffmpeg_exe() en
    # src/utils/paths.py y src/infrastructure/media/ffmpeg_utils.py.
    (VENDOR_FFMPEG_DIR, "ffmpeg_bin"),
    # Chromium real (con extension-loading) -- ver get_bundled_chromium_exe() en
    # src/utils/paths.py y chrome_launcher.find_chromium_exe().
    (VENDOR_CHROMIUM_DIR, "chromium_bin"),
]
binaries = []
hiddenimports = [
    # Import dinamico por string (werkzeug.utils.import_string), invisible para
    # el analisis estatico de PyInstaller.
    "apiflask.settings",
    # Submodulos con el mismo problema que arriba, ocultos por PyArmor dentro de
    # nuestro propio codigo -- lista armada grep-eando todo el arbol por imports
    # con punto en vez de esperar a que cada uno rompa el build por separado.
    "collections.abc",
    "concurrent.futures",
    "dbutils.pooled_db",
    "http.server",
    "logging.handlers",
    "requests.adapters",
    "urllib.parse",
    "urllib.request",
    "urllib3.util.retry",
    "websockets.sync.server",
    "bcrypt",
    "webview",
    "pywebview",
    "tkinter",
    "dotenv",
    "flask",
    "flask_marshmallow",
    "werkzeug",
    "jinja2",
    "itsdangerous",
    "click",
    "markupsafe",
    "requests",
    "pymysql",
    "dbutils",
    "cryptography",
    "playwright",
    "playwright.sync_api",
    "PIL",
    "PIL.Image",
    "websockets",
    "websockets.sync",
    "websockets.asyncio",
    "curl_cffi",
    "oss2",
    "psutil",
    "stripe",
    # Import perezoso dentro de editor_scene_analysis_service.py -- invisible para
    # el analisis estatico de PyInstaller (mas todavia con el codigo ofuscado por
    # PyArmor, ver comentario de own_package_modules() arriba).
    "json_repair",
] + own_hidden

for pkg in ("webview", "flask", "apiflask", "bcrypt", "playwright", "websockets", "curl_cffi", "oss2", "stripe"):
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    [f"{OBF_DIR}/main.py"],
    pathex=[OBF_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # torch/whisper/faster_whisper/replicate: backends opcionales, ninguno
    # instalado aca. mypy/pytest/black/ruff/pre-commit: solo de desarrollo.
    excludes=["torch", "whisper", "faster_whisper", "replicate", "mypy", "pytest", "black", "ruff", "pre_commit"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StudioIVR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["assets/icon.ico"],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="StudioIVR",
)
