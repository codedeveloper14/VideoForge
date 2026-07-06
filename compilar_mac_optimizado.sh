#!/bin/bash

echo "========================================="
echo "  COMPILANDO IVR 2.5 PARA MACOS (OPTIMIZADO)"
echo "========================================="

source venv/bin/activate

# Instalar dependencias
echo "Instalando dependencias..."
pip install bcrypt replicate

# Verificar
python -c "import bcrypt; print('bcrypt OK')"
python -c "import replicate; print('replicate OK')"

# Limpiar
rm -rf dist dist_final build IVR_2.5.app IVR_2.5.dmg IVR_2.5.spec dist_ofuscado

# Ofuscar módulos
echo "Ofuscando módulos..."
mkdir -p dist_ofuscado
for mod in launcher.py auth_module.py ui_embedded.py grok_multi.py vf_db_connection.py vf_db_interact.py vf_db_sync.py; do
    if [ -f "$mod" ]; then
        pyarmor gen --obf-code 2 -O dist_ofuscado "$mod"
    fi
done

# Copiar flow_extension a dist_ofuscado
if [ -d "flow_extension" ]; then
    echo "Copiando flow_extension..."
    cp -r flow_extension dist_ofuscado/
fi

# Compilar con PyInstaller optimizado
echo "Compilando con PyInstaller (optimizado)..."
pyinstaller \
  --onefile \
  --windowed \
  --name IVR_2.5 \
  --icon assets/icon.icns \
  --strip \
  --hidden-import bcrypt \
  --hidden-import replicate \
  --hidden-import webview \
  --hidden-import webview.platforms \
  --hidden-import webview.platforms.winforms \
  --hidden-import webview.platforms.winforms.webview \
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
  --add-data "cookies:cookies" \
  --add-data "jobs:jobs" \
  --add-data "meta_accounts:meta_accounts" \
  --add-data "gentube_cookies:gentube_cookies" \
  --add-data "grok-animator2.0:grok-animator2.0" \
  --add-data "whisk_downloads:whisk_downloads" \
  --add-data "Build and Instructions:Build and Instructions" \
  --add-data "dist_ofuscado/flow_extension:flow_extension" \
  --add-data "dist_ofuscado/auth_module.py:." \
  --add-data "dist_ofuscado/ui_embedded.py:." \
  --add-data "dist_ofuscado/grok_multi.py:." \
  --add-data "dist_ofuscado/vf_db_connection.py:." \
  --add-data "dist_ofuscado/vf_db_interact.py:." \
  --add-data "dist_ofuscado/vf_db_sync.py:." \
  --distpath dist_final \
  dist_ofuscado/launcher.py

# Crear .app
echo "Creando .app..."
APP_NAME="IVR_2.5.app"
APP_DIR="$APP_NAME/Contents"
mkdir -p "$APP_DIR/MacOS" "$APP_DIR/Resources"

cp dist_final/IVR_2.5 "$APP_DIR/MacOS/"
chmod +x "$APP_DIR/MacOS/IVR_2.5"
cp assets/icon.icns "$APP_DIR/Resources/"

cat > "$APP_DIR/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>IVR 2.5</string>
    <key>CFBundleDisplayName</key>
    <string>IVR 2.5</string>
    <key>CFBundleIdentifier</key>
    <string>com.videoforge.ivr25</string>
    <key>CFBundleVersion</key>
    <string>2.5.0</string>
    <key>CFBundleShortVersionString</key>
    <string>2.5.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleExecutable</key>
    <string>IVR_2.5</string>
    <key>CFBundleIconFile</key>
    <string>icon.icns</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
</dict>
</plist>
EOF

echo "APPL????" > "$APP_DIR/PkgInfo"

# Crear .dmg optimizado
echo "Creando .dmg optimizado..."
rm -f IVR_2.5.dmg
hdiutil create -volname "IVR 2.5" \
  -srcfolder IVR_2.5.app \
  -ov -format UDZO \
  -imagekey zlib-level=9 \
  IVR_2.5.dmg

echo ""
echo "========================================="
echo "COMPILACIÓN OPTIMIZADA COMPLETADA"
echo "========================================="
ls -lh IVR_2.5.dmg

echo ""
echo "Tamaño del .dmg:"
du -sh IVR_2.5.dmg

echo ""
echo "Probando la app..."
./IVR_2.5.app/Contents/MacOS/IVR_2.5 &
sleep 3

echo ""
echo "Instalando en ~/Applications/..."
cp -R IVR_2.5.app ~/Applications/
open ~/Applications/IVR_2.5.app
