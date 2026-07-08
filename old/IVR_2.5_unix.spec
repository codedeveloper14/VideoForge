# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [
    ('cookies', 'cookies'),
    ('jobs', 'jobs'),
    ('meta_accounts', 'meta_accounts'),
    ('gentube_cookies', 'gentube_cookies'),
    ('grok-animator2.0', 'grok-animator2.0'),
    ('whisk_downloads', 'whisk_downloads'),
    ('Build and Instructions', 'Build and Instructions'),
    ('dist_ofuscado/flow_extension', 'flow_extension'),
    ('dist_ofuscado/auth_module.py', '.'),
    ('dist_ofuscado/ui_embedded.py', '.'),
    ('dist_ofuscado/grok_multi.py', '.'),
    ('dist_ofuscado/vf_db_connection.py', '.'),
    ('dist_ofuscado/vf_db_interact.py', '.'),
    ('dist_ofuscado/vf_db_sync.py', '.'),
]

binaries = []
hiddenimports = [
    'bcrypt', 'replicate', 'webview', 'pywebview',
    'tkinter', 'tkinter.ttk', 'tkinter.messagebox',
    'dotenv', 'flask', 'flask_cors', 'werkzeug',
    'jinja2', 'itsdangerous', 'click', 'markupsafe',
    'requests', 'pymysql', 'cryptography',
    'playwright', 'playwright.sync_api',
    'PIL', 'PIL.Image', 'PIL.ImageTk',
    'websockets', 'waitress'
]

# Collect all dependencies
for package in ['webview', 'flask', 'bcrypt', 'replicate']:
    tmp_ret = collect_all(package)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    ['dist_ofuscado/entry.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='IVR_2.5',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'],
)
