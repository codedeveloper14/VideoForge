# -*- mode: python ; coding: utf-8 -*-
# Empaqueta Studio IVR (VideoForge) para macOS -- SOLO Mac, no sirve para Windows
# (eso usa studioivr.spec). Genera un .app onedir vía BUNDLE(), no --onefile
# (ver [[project-production-requirements]]: un solo binario onefile se
# autoextrae a /tmp en cada arranque, un retraso evitable).
#
# No produce un binario universal2: se corre una vez por arquitectura nativa
# (arm64 en un runner Apple Silicon, x86_64 en uno Intel) -- ver
# .github/workflows/build-mac.yml. target_arch se deja en None a propósito
# para que PyInstaller tome la arquitectura nativa del Python que lo ejecuta,
# en vez de forzar un target que requeriría wheels universal2 para cada
# dependencia nativa (playwright, curl_cffi, oss2, psutil, pyobjc, etc.),
# que no está garantizado.
#
# Antes de correr este spec: ofuscar con PyArmor (mismo paso que Windows).
#   pyarmor gen -O build/pyarmor_dist -r main.py src desktop scripts
import os

from PyInstaller.utils.hooks import collect_all

OBF_DIR = "build/pyarmor_dist"


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
]
binaries = []
hiddenimports = [
    "apiflask.settings",
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
    # Backend nativo Cocoa/WebKit de pywebview en Mac (pywebview elige este
    # modulo en runtime segun sys.platform, invisible para el analisis
    # estatico -- sin esto pywebview cae en silencio al fallback de navegador
    # en vez de abrir una ventana nativa real). pyobjc (requirements.txt,
    # sys_platform=="darwin") instala el paquete completo de frameworks.
    "webview.platforms.cocoa",
    "objc",
    "Foundation",
    "AppKit",
    "WebKit",
    "Quartz",
    "PyObjCTools",
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
    # Sin firma todavia -- ver [[project-code-signing]] (Apple Developer
    # Program comprado, credenciales/certificado Developer ID Application
    # todavia no generados). Cuando existan: codesign_identity="Developer ID
    # Application: NOMBRE (TEAMID)" aca, y notarizar el .dmg aparte
    # (xcrun notarytool) despues de este build -- no lo hace PyInstaller.
    codesign_identity=None,
    entitlements_file=None,
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

app = BUNDLE(
    coll,
    name="Studio IVR.app",
    icon="assets/icon.icns",
    bundle_identifier="com.studioivr.app",
    version="1.0.0",
    info_plist={
        "CFBundleName": "Studio IVR",
        "CFBundleDisplayName": "Studio IVR",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "10.15",
        # Deja que la app siga el tema claro/oscuro del sistema en vez de
        # forzar apariencia clara.
        "NSRequiresAquaSystemAppearance": False,
    },
)
