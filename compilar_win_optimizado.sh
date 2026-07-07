#!/bin/bash

echo "========================================="
echo "  COMPILANDO IVR 2.5 PARA WINDOWS"
echo "========================================="

# Configurar PATH para PyArmor
export PATH="/c/Users/igaby/AppData/Roaming/Python/Python314/Scripts:$PATH"

echo "[PACKAGE] Instalando dependencias..."
pip install bcrypt replicate pywebview playwright pyinstaller websockets flask flask_cors pythonnet

# Limpiar
rm -rf dist dist_final build IVR_2.5.spec dist_ofuscado

echo "[SECURE] Ofuscando modulos..."
mkdir -p dist_ofuscado

PYARMOR_CMD="pyarmor"
if ! command -v pyarmor &> /dev/null; then
    PYARMOR_CMD="/c/Users/igaby/AppData/Roaming/Python/Python314/Scripts/pyarmor"
fi

for mod in launcher.py auth_module.py ui_embedded.py grok_multi.py vf_db_connection.py vf_db_interact.py vf_db_sync.py; do
    if [ -f "$mod" ]; then
        echo "   Ofuscando: $mod"
        $PYARMOR_CMD gen --obf-code 2 -O dist_ofuscado "$mod" 2>/dev/null || cp "$mod" dist_ofuscado/
    fi
done

# Copiar flow_extension y assets
cp -r flow_extension dist_ofuscado/ 2>/dev/null
cp -r assets dist_ofuscado/ 2>/dev/null

# Crear entry.py SIN EMOJIS
cat > dist_ofuscado/entry.py << 'ENTRY_EOF'
import sys
import os
import runpy

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("=" * 60)
print("  IVR 2.5 - Iniciando aplicacion")
print("=" * 60)

try:
    import launcher
    print("[OK] launcher.py importado correctamente")
    runpy.run_module('launcher', run_name='__main__')
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    input("Presiona Enter para salir...")
    sys.exit(1)
ENTRY_EOF

echo "[OK] entry.py creado"

# Compilar
echo "[START] Compilando con PyInstaller..."
python -m PyInstaller \
  --onefile \
  --windowed \
  --name IVR_2.5 \
  --icon assets/icon.ico \
  --strip \
  --hidden-import bcrypt \
  --hidden-import replicate \
  --hidden-import webview \
  --hidden-import pywebview \
  --hidden-import tkinter \
  --hidden-import tkinter.ttk \
  --hidden-import tkinter.messagebox \
  --hidden-import dotenv \
  --hidden-import flask \
  --hidden-import flask_cors \
  --hidden-import werkzeug \
  --hidden-import jinja2 \
  --hidden-import itsdangerous \
  --hidden-import click \
  --hidden-import markupsafe \
  --hidden-import requests \
  --hidden-import pymysql \
  --hidden-import cryptography \
  --hidden-import playwright \
  --hidden-import playwright.sync_api \
  --hidden-import PIL \
  --hidden-import PIL.Image \
  --hidden-import PIL.ImageTk \
  --hidden-import websockets \
  --hidden-import websockets.sync \
  --hidden-import websockets.asyncio \
  --hidden-import waitress \
  --hidden-import clr \
  --hidden-import pythonnet \
  --collect-all webview \
  --collect-all flask \
  --collect-all bcrypt \
  --collect-all replicate \
  --collect-all websockets \
  --add-data "cookies;cookies" \
  --add-data "jobs;jobs" \
  --add-data "meta_accounts;meta_accounts" \
  --add-data "gentube_cookies;gentube_cookies" \
  --add-data "grok-animator2.0;grok-animator2.0" \
  --add-data "whisk_downloads;whisk_downloads" \
  --add-data "Build and Instructions;Build and Instructions" \
  --add-data "dist_ofuscado/flow_extension;flow_extension" \
  --add-data "dist_ofuscado/assets;assets" \
  --add-data "dist_ofuscado/launcher.py;." \
  --add-data "dist_ofuscado/auth_module.py;." \
  --add-data "dist_ofuscado/ui_embedded.py;." \
  --add-data "dist_ofuscado/grok_multi.py;." \
  --add-data "dist_ofuscado/vf_db_connection.py;." \
  --add-data "dist_ofuscado/vf_db_interact.py;." \
  --add-data "dist_ofuscado/vf_db_sync.py;." \
  --add-data "dist_ofuscado/pyarmor_runtime_012301;pyarmor_runtime_012301" \
  --distpath dist_final \
  dist_ofuscado/entry.py

echo ""
echo "========================================="
if [ -f "dist_final/IVR_2.5.exe" ]; then
    echo "[OK] COMPILACION COMPLETADA"
    ls -lh dist_final/IVR_2.5.exe
else
    echo "[ERROR] Error en compilacion"
    exit 1
fi