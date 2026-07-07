#!/bin/bash

echo "========================================="
echo "  COMPILANDO IVR 2.5 PARA MACOS (UNIVERSAL2)"
echo "  Compatible con Intel y Apple Silicon (M1/M2/M3)"
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
pip install bcrypt replicate pyarmor pyinstaller websockets flask flask_cors

python -c "import bcrypt; print(' bcrypt OK')"
python -c "import replicate; print(' replicate OK')"
python -c "import websockets; print(' websockets OK')"

# ============================================
# 3. LIMPIAR COMPILACIONES ANTERIORES
# ============================================
echo " Limpiando compilaciones anteriores..."
rm -rf dist dist_final build IVR_2.5.app IVR_2.5.dmg IVR_2.5.spec dist_ofuscado IVR_2.5_Instalador.zip

# ============================================
# 4. OFUSCAR MÓDULOS
# ============================================
echo " Ofuscando módulos..."
mkdir -p dist_ofuscado
for mod in launcher.py auth_module.py ui_embedded.py grok_multi.py vf_db_connection.py vf_db_interact.py vf_db_sync.py; do
    if [ -f "$mod" ]; then
        echo "  → Ofuscando $mod..."
        pyarmor gen --obf-code 2 -O dist_ofuscado "$mod" 2>/dev/null || cp "$mod" dist_ofuscado/
    else
        echo "     $mod no encontrado, saltando..."
    fi
done

# ============================================
# 5. COPIAR FLOW_EXTENSION Y ASSETS
# ============================================
echo " Copiando recursos..."
if [ -d "flow_extension" ]; then
    cp -r flow_extension dist_ofuscado/
    echo "   flow_extension copiado"
fi

if [ -d "assets" ]; then
    cp -r assets dist_ofuscado/
    echo "   assets copiados"
fi

# ============================================
# 6. CREAR ENTRY.PY CON CAPTURA DE ERRORES PARA MAC
# ============================================
echo " Creando entry.py con captura de errores para macOS..."

cat > dist_ofuscado/entry.py << 'ENTRY_EOF'
import sys
import os
import runpy
import traceback
import platform
from datetime import datetime

# ============================================
# CARPETAS DE DATOS (AppData/Application Support)
# ============================================

def get_app_data_folder():
    if platform.system() == "Windows":
        appdata = os.environ.get('APPDATA', os.path.expanduser('~\\AppData\\Roaming'))
        return os.path.join(appdata, 'VideoForge')
    else:
        home = os.path.expanduser('~')
        return os.path.join(home, 'Library', 'Application Support', 'VideoForge')

APP_DATA = get_app_data_folder()
JOBS_FOLDER = os.path.join(APP_DATA, 'jobs')
COOKIES_FOLDER = os.path.join(APP_DATA, 'cookies')
WHISK_DOWNLOADS = os.path.join(APP_DATA, 'whisk_downloads')
FLOW_EXTENSION_FOLDER = os.path.join(APP_DATA, 'flow_extension')

for folder in [JOBS_FOLDER, COOKIES_FOLDER, WHISK_DOWNLOADS, FLOW_EXTENSION_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# ============================================
# CAPTURA DE ERRORES PARA MACOS
# ============================================

def guardar_error(error_texto):
    """Guarda el error en el escritorio del usuario"""
    try:
        desktop = os.path.expanduser("~/Desktop")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_path = os.path.join(desktop, f"IVR_Error_{timestamp}.txt")
        
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write("  IVR 2.5 - REPORTE DE ERROR\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Usuario: {os.getlogin()}\n")
            f.write(f"Maquina: {platform.node()}\n")
            f.write(f"Arquitectura: {platform.machine()}\n")
            f.write(f"Sistema: {platform.system()} {platform.release()}\n\n")
            f.write("=" * 60 + "\n")
            f.write("  ERROR DETALLADO\n")
            f.write("=" * 60 + "\n\n")
            f.write(error_texto)
            f.write("\n\n" + "=" * 60 + "\n")
            f.write("  FIN DEL REPORTE\n")
            f.write("=" * 60 + "\n")
        
        return log_path
    except Exception as e:
        return None

# ============================================
# MAIN CON CAPTURA DE ERRORES
# ============================================

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("=" * 60)
print("  IVR 2.5 - Iniciando aplicacion")
print("=" * 60)
print(f" Directorio: {current_dir}")
print(f" Arquitectura: {platform.machine()}")
print(f" AppData: {APP_DATA}")
print("=" * 60)

try:
    import launcher
    print("[OK] launcher.py importado correctamente")
    runpy.run_module('launcher', run_name='__main__')
except Exception as e:
    error_texto = traceback.format_exc()
    print(f"[ERROR] {e}")
    log_path = guardar_error(error_texto)
    if log_path:
        print(f"[OK] Error guardado en: {log_path}")
        print(f"[MSG] Envia este archivo al desarrollador: {log_path}")
    input("Presiona Enter para salir...")
    sys.exit(1)
ENTRY_EOF

echo " entry.py con captura de errores creado"

# ============================================
# 7. COMPILAR CON PYINSTALLER (UNIVERSAL2)
# ============================================
echo " Compilando con PyInstaller (Universal2)..."
echo "   Esto puede tomar varios minutos..."

pyinstaller \
  --onefile \
  --windowed \
  --target-architecture universal2 \
  --name IVR_2.5 \
  --icon assets/icon.icns \
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
  --collect-all webview \
  --collect-all flask \
  --collect-all bcrypt \
  --collect-all replicate \
  --collect-all websockets \
  --add-data "cookies:cookies" \
  --add-data "jobs:jobs" \
  --add-data "meta_accounts:meta_accounts" \
  --add-data "gentube_cookies:gentube_cookies" \
  --add-data "grok-animator2.0:grok-animator2.0" \
  --add-data "whisk_downloads:whisk_downloads" \
  --add-data "Build and Instructions:Build and Instructions" \
  --add-data "dist_ofuscado/flow_extension:flow_extension" \
  --add-data "dist_ofuscado/assets:assets" \
  --add-data "dist_ofuscado/launcher.py:." \
  --add-data "dist_ofuscado/auth_module.py:." \
  --add-data "dist_ofuscado/ui_embedded.py:." \
  --add-data "dist_ofuscado/grok_multi.py:." \
  --add-data "dist_ofuscado/vf_db_connection.py:." \
  --add-data "dist_ofuscado/vf_db_interact.py:." \
  --add-data "dist_ofuscado/vf_db_sync.py:." \
  --add-data "dist_ofuscado/pyarmor_runtime_012301:pyarmor_runtime_012301" \
  --distpath dist_final \
  dist_ofuscado/entry.py

if [ $? -ne 0 ] || [ ! -f "dist_final/IVR_2.5" ]; then
    echo " Error en la compilación con PyInstaller"
    exit 1
fi

echo " Compilación completada"

# ============================================
# 8. CREAR EL .APP
# ============================================
echo " Creando .app..."
APP_NAME="IVR_2.5.app"
APP_DIR="$APP_NAME/Contents"
mkdir -p "$APP_DIR/MacOS" "$APP_DIR/Resources"

cp dist_final/IVR_2.5 "$APP_DIR/MacOS/"
chmod +x "$APP_DIR/MacOS/IVR_2.5"

if [ -f "assets/icon.icns" ]; then
    cp assets/icon.icns "$APP_DIR/Resources/"
else
    echo " No se encontró icon.icns"
fi

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
# 9. CREAR EL .DMG
# ============================================
echo " Creando .dmg..."
rm -f IVR_2.5.dmg
hdiutil create -volname "IVR 2.5" \
  -srcfolder IVR_2.5.app \
  -ov -format UDZO \
  -imagekey zlib-level=9 \
  IVR_2.5.dmg

if [ $? -ne 0 ] || [ ! -f "IVR_2.5.dmg" ]; then
    echo " Error al crear el .dmg, pero la app está lista"
fi

# ============================================
# 10. CREAR SCRIPT .COMMAND CON ROSETTA
# ============================================
echo " Creando script de desbloqueo con Rosetta..."

cat > "Abrir_IVR_2.5.command" << 'EOF'
#!/bin/bash

echo "========================================="
echo "  IVR 2.5 - Desbloqueo para macOS"
echo "========================================="

if [[ "$(uname -m)" == "arm64" ]]; then
    echo " Verificando Rosetta 2..."
    if ! /usr/bin/pgrep -q oahd; then
        echo " Rosetta 2 no esta instalado."
        echo " Instalando Rosetta 2..."
        softwareupdate --install-rosetta --agree-to-license
        echo " Rosetta 2 instalado correctamente"
    else
        echo " Rosetta 2 ya esta instalado"
    fi
fi

echo ""
echo " Desbloqueando IVR 2.5..."
xattr -rd com.apple.quarantine "/Applications/IVR_2.5.app" 2>/dev/null || echo "⚠️ La app no esta en /Applications"

echo ""
echo " Abriendo IVR_2.5..."
open "/Applications/IVR_2.5.app"

echo ""
echo "========================================="
echo "   IVR 2.5 iniciado"
echo "========================================="
echo ""
echo " Si la app no abre:"
echo "   1. Ve a Preferencias del Sistema -> Privacidad y Seguridad"
echo "   2. Busca el mensaje de bloqueo y haz clic en 'Abrir de todos modos'"
echo "   3. Si ves un error, busca el archivo IVR_Error_*.txt en el Escritorio"
echo ""
read -p "Presiona Enter para cerrar..."
EOF

chmod +x "Abrir_IVR_2.5.command"

# ============================================
# 11. CREAR INSTALADOR .ZIP
# ============================================
echo " Creando instalador ZIP..."

if [ -d "IVR_2.5.app" ] && [ -f "Abrir_IVR_2.5.command" ]; then
    zip -r "IVR_2.5_Instalador.zip" "IVR_2.5.app" "Abrir_IVR_2.5.command"
    echo " ZIP creado: IVR_2.5_Instalador.zip"
    ls -lh IVR_2.5_Instalador.zip
fi

# ============================================
# 12. RESULTADO FINAL
# ============================================
echo ""
echo "========================================="
echo " COMPILACION COMPLETADA"
echo "========================================="
echo ""
echo " Archivos generados:"
echo "   IVR_2.5.dmg                  -> Instalador para macOS"
echo "   IVR_2.5_Instalador.zip       -> ZIP con app + script de desbloqueo"
echo "   IVR_2.5.app                  -> Aplicacion"
echo "   Abrir_IVR_2.5.command        -> Script para desbloquear la app"
echo ""
echo " Tamaño del .dmg:"
du -sh IVR_2.5.dmg 2>/dev/null || echo "   No se pudo calcular"
echo ""
echo " Probando la app..."
./IVR_2.5.app/Contents/MacOS/IVR_2.5 &
sleep 3

echo ""
echo "========================================="
echo "  ¡LISTO! Los instaladores estan listos"
echo "  para compartir con los usuarios."
echo "========================================="