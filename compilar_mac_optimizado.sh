#!/bin/bash

echo "========================================="
echo "  COMPILANDO IVR 2.5 PARA MACOS (OPTIMIZADO)"
echo "========================================="

# ============================================
# 1. ACTIVAR ENTORNO VIRTUAL
# ============================================
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo " No se encontró el entorno virtual. Ejecuta: python -m venv venv"
    exit 1
fi

# ============================================
# 2. INSTALAR DEPENDENCIAS
# ============================================
echo " Instalando dependencias..."
pip install --upgrade pip
pip install bcrypt replicate

# Verificar
python -c "import bcrypt; print(' bcrypt OK')"
python -c "import replicate; print(' replicate OK')"

# ============================================
# 3. LIMPIAR COMPILACIONES ANTERIORES
# ============================================
echo " Limpiando compilaciones anteriores..."
rm -rf dist dist_final build IVR_2.5.app IVR_2.5.dmg IVR_2.5.spec dist_ofuscado

# ============================================
# 4. OFUSCAR MÓDULOS
# ============================================
echo " Ofuscando módulos..."
mkdir -p dist_ofuscado
for mod in launcher.py auth_module.py ui_embedded.py grok_multi.py vf_db_connection.py vf_db_interact.py vf_db_sync.py; do
    if [ -f "$mod" ]; then
        echo "  → Ofuscando $mod..."
        pyarmor gen --obf-code 2 -O dist_ofuscado "$mod"
    else
        echo "    $mod no encontrado, saltando..."
    fi
done

# ============================================
# 5. COPIAR FLOW_EXTENSION AL OFUSCADO
# ============================================
if [ -d "flow_extension" ]; then
    echo " Copiando flow_extension..."
    cp -r flow_extension dist_ofuscado/
else
    echo "  No se encontró flow_extension. Saltando..."
fi

# ============================================
# 6. VERIFICAR RECURSOS (PARA QUE FUNCIONE EN CUALQUIER MAC)
# ============================================
echo " Verificando recursos..."
for folder in cookies jobs meta_accounts gentube_cookies grok-animator2.0 whisk_downloads "Build and Instructions"; do
    if [ ! -d "$folder" ]; then
        echo "    Creando carpeta: $folder"
        mkdir -p "$folder"
        touch "$folder/placeholder.txt"
    fi
done

# ============================================
# 7. COMPILAR CON PYINSTALLER (TODOS LOS RECURSOS INCLUIDOS)
# ============================================
echo " Compilando con PyInstaller (optimizado)..."
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

if [ $? -ne 0 ] || [ ! -f "dist_final/IVR_2.5" ]; then
    echo " Error en la compilación con PyInstaller"
    exit 1
fi

# ============================================
# 8. CREAR EL .APP (CON TODOS LOS RECURSOS)
# ============================================
echo " Creando .app..."
APP_NAME="IVR_2.5.app"
APP_DIR="$APP_NAME/Contents"
mkdir -p "$APP_DIR/MacOS" "$APP_DIR/Resources"

# Copiar ejecutable
cp dist_final/IVR_2.5 "$APP_DIR/MacOS/"
chmod +x "$APP_DIR/MacOS/IVR_2.5"

# Copiar icono
cp assets/icon.icns "$APP_DIR/Resources/"

# Crear Info.plist
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

# ============================================
# 9. VERIFICAR QUE EL .APP CONTIENE TODOS LOS RECURSOS
# ============================================
echo " Verificando recursos dentro del .app..."
ls -la "$APP_DIR/Resources/"

# ============================================
# 10. CREAR EL .DMG
# ============================================
echo " Creando .dmg optimizado..."
rm -f IVR_2.5.dmg
hdiutil create -volname "IVR 2.5" \
  -srcfolder IVR_2.5.app \
  -ov -format UDZO \
  -imagekey zlib-level=9 \
  IVR_2.5.dmg

if [ $? -ne 0 ] || [ ! -f "IVR_2.5.dmg" ]; then
    echo " Error al crear el .dmg"
    exit 1
fi

# ============================================
# 11. CREAR EL SCRIPT .COMMAND PARA DESBLOQUEAR LA APP
# ============================================
echo " Creando script de desbloqueo..."

cat > "Abrir_IVR_2.5.command" << 'EOF'
#!/bin/bash

echo " Desbloqueando IVR 2.5..."
xattr -rd com.apple.quarantine /Applications/IVR_2.5.app
echo " Abriendo IVR 2.5..."
open /Applications/IVR_2.5.app
echo " Listo. Puedes cerrar esta ventana."
EOF

chmod +x "Abrir_IVR_2.5.command"

# ============================================
# 12. CREAR EL INSTALADOR .ZIP (APP + SCRIPT)
# ============================================
echo " Creando instalador ZIP..."

# Verificar que el .app existe
if [ -d "IVR_2.5.app" ] && [ -f "Abrir_IVR_2.5.command" ]; then
    # Crear el ZIP con la app y el script
    zip -r "IVR_2.5_Instalador.zip" "IVR_2.5.app" "Abrir_IVR_2.5.command"
    echo " ZIP creado: IVR_2.5_Instalador.zip"
    ls -lh IVR_2.5_Instalador.zip
else
    echo "  No se pudo crear el ZIP: faltan archivos"
    echo "   Verifica que IVR_2.5.app y Abrir_IVR_2.5.command existan"
fi

# ============================================
# 13. RESULTADO FINAL
# ============================================
echo ""
echo "========================================="
echo "COMPILACIÓN OPTIMIZADA COMPLETADA"
echo "========================================="
echo ""
echo " Archivos generados:"
echo "   IVR_2.5.dmg                  → Instalador para macOS"
echo "   IVR_2.5_Instalador.zip       → ZIP con app + script de desbloqueo"
echo "   IVR_2.5.app                  → Aplicación (dentro del DMG y ZIP)"
echo "   Abrir_IVR_2.5.command        → Script para desbloquear la app"
echo ""
echo " Tamaño del .dmg:"
du -sh IVR_2.5.dmg
echo ""
echo " Probando la app..."
./IVR_2.5.app/Contents/MacOS/IVR_2.5 &
sleep 3

echo ""
echo " Instalando en ~/Applications/..."
cp -R IVR_2.5.app ~/Applications/
open ~/Applications/IVR_2.5.app

echo ""
echo "========================================="
echo " ¡LISTO! El .dmg y el ZIP están listos"
echo "   para compartir con los usuarios."
echo "========================================="