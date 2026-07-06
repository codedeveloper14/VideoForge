#!/bin/bash

echo "========================================="
echo "  COMPILANDO IVR 2.5 PARA WINDOWS (OPTIMIZADO)"
echo "========================================="

# Activar entorno virtual
source venv/Scripts/activate

# Instalar dependencias
echo " Instalando dependencias..."
pip install bcrypt replicate

# Verificar
python -c "import bcrypt; print(' bcrypt OK')"
python -c "import replicate; print(' replicate OK')"

# Limpiar
rm -rf dist dist_final build IVR_2.5.spec dist_ofuscado

# Ofuscar módulos
echo " Ofuscando módulos..."
mkdir -p dist_ofuscado
for mod in launcher.py auth_module.py ui_embedded.py grok_multi.py vf_db_connection.py vf_db_interact.py vf_db_sync.py; do
    if [ -f "$mod" ]; then
        pyarmor gen --obf-code 2 -O dist_ofuscado "$mod"
    fi
done

# Copiar flow_extension a dist_ofuscado
if [ -d "flow_extension" ]; then
    echo " Copiando flow_extension..."
    cp -r flow_extension dist_ofuscado/
else
    echo " No se encontró flow_extension. Saltando..."
fi

# Compilar con PyInstaller optimizado
echo " Compilando con PyInstaller (optimizado)..."
./venv/Scripts/pyinstaller \
  --onefile \
  --windowed \
  --name IVR_2.5 \
  --icon assets/icon.ico \
  --strip \
  --hidden-import bcrypt \
  --hidden-import replicate \
  --hidden-import webview \
  --hidden-import tkinter \
  --hidden-import tkinter.ttk \
  --hidden-import tkinter.messagebox \
  --hidden-import dotenv \
  --hidden-import flask \
  --hidden-import werkzeug \
  --hidden-import jinja2 \
  --hidden-import itsdangerous \
  --hidden-import click \
  --hidden-import markupsafe \
  --hidden-import requests \
  --hidden-import pymysql \
  --hidden-import cryptography \
  --hidden-import playwright \
  --hidden-import PIL \
  --collect-all webview \
  --collect-all flask \
  --collect-all bcrypt \
  --collect-all replicate \
  --add-data "cookies;cookies" \
  --add-data "jobs;jobs" \
  --add-data "meta_accounts;meta_accounts" \
  --add-data "gentube_cookies;gentube_cookies" \
  --add-data "grok-animator2.0;grok-animator2.0" \
  --add-data "whisk_downloads;whisk_downloads" \
  --add-data "Build and Instructions;Build and Instructions" \
  --add-data "dist_ofuscado/flow_extension;flow_extension" \
  --add-data "dist_ofuscado/auth_module.py;." \
  --add-data "dist_ofuscado/ui_embedded.py;." \
  --add-data "dist_ofuscado/grok_multi.py;." \
  --add-data "dist_ofuscado/vf_db_connection.py;." \
  --add-data "dist_ofuscado/vf_db_interact.py;." \
  --add-data "dist_ofuscado/vf_db_sync.py;." \
  --distpath dist_final \
  dist_ofuscado/launcher.py

# Verificar que se creó
echo ""
echo "========================================="
echo " COMPILACIÓN OPTIMIZADA COMPLETADA"
echo "========================================="
ls -lh dist_final/IVR_2.5.exe

echo ""
echo "📌 Tamaño del ejecutable:"
du -sh dist_final/IVR_2.5.exe

echo ""
echo "📌 Ejecutando la app..."
./dist_final/IVR_2.5.exe
