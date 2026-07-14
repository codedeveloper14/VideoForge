# -*- mode: python ; coding: utf-8 -*-
"""Empaqueta VideoForge (Studio IVR) para Windows.

Dos pasos, en orden:
1. PyArmor ofusca main.py + src/ + desktop/ + scripts/ hacia build/pyarmor_dist/
   (correr antes de esto: `pyarmor gen -O build/pyarmor_dist -r main.py src desktop scripts`).
2. Este spec empaqueta ESE codigo ofuscado con PyInstaller -- nunca el fuente real.

Por que no alcanza con el analisis automatico de PyInstaller para nuestro propio
codigo: PyArmor reescribe cada modulo para que sus imports no sean `import x`
literales en el AST (asi es como protege el codigo), y el analizador estatico de
PyInstaller solo entiende imports literales. Sin ayuda extra, arranca el .exe y
explota con "ModuleNotFoundError: No module named 'src'" (o, si se usa
collect_submodules -- que necesita poder IMPORTAR cada modulo para enumerarlo --
falla parcial y silenciosamente en cuanto un submodulo dispara una excepcion al
importarse, dejando afuera paquetes enteros como 'src.domain'). La solucion real:
enumerar los modulos propios caminando el sistema de archivos (nombres de archivo,
nunca hace falta importar nada), y pasarlos como hiddenimports explicitos.
"""
import os

from PyInstaller.utils.hooks import collect_all

OBF_DIR = "build/pyarmor_dist"


def own_package_modules(package_dir: str) -> list[str]:
    """Convierte cada .py bajo package_dir/<package> en su nombre de modulo punteado
    (p.ej. src/domain/services/grok_animation_service.py -> algo asi con prefijo
    package). Camina el disco, nunca importa nada -- inmune a que PyArmor haya
    reescrito los imports o a que un submodulo falle al importarse."""
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
    # grok_worker.py NUNCA se importa -- main.py lo relanza con runpy.run_path()
    # sobre una ruta real de disco (ver el dispatch de --vf-grok-worker), asi que
    # tiene que existir como archivo suelto, no compilado dentro del PYZ.
    (f"{OBF_DIR}/scripts/grok_worker.py", "scripts"),
]
binaries = []
hiddenimports = [
    # apiflask carga esta config por string (werkzeug.utils.import_string) -- el
    # analisis estatico de PyInstaller no lo detecta solo, ni siquiera sin PyArmor
    # de por medio (confirmado en vivo, mismo bug que aparecio compilando con Nuitka).
    "apiflask.settings",
    # Submodulos de la libreria estandar/terceros importados con `from X.Y import Z`
    # dentro de nuestro codigo ofuscado -- mismo motivo que apiflask.settings arriba:
    # PyArmor oculta el import literal, PyInstaller no lo puede ver por analisis
    # estatico. Lista construida grep-eando TODO el arbol (src/desktop/scripts/
    # main.py) por imports con punto, en vez de esperar a que cada uno rompa el
    # build uno por uno.
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
    # torch/whisper/faster_whisper/replicate: backends opcionales de transcripcion,
    # ninguno instalado en este venv -- ni siquiera hace falta excluirlos, pero
    # explicito por las dudas si alguna vez se instalan localmente sin querer
    # empaquetarlos. mypy/pytest/black/ruff/pre-commit: herramientas de desarrollo,
    # jamas se usan en tiempo de ejecucion (mismo criterio ya aplicado con Nuitka).
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
