#!/bin/bash
# Compila Studio IVR (VideoForge) para macOS -- un solo comando, corrido
# localmente en un Mac real (no CI). Arquitectura nativa: toma la del Mac
# donde se ejecuta (arm64 en Apple Silicon, x86_64 en Intel) via `uname -m`,
# no compila universal2 -- ver [[project-deployment-architecture]] para el
# motivo (no todas las dependencias nativas garantizan wheels universal2).
#
# Requisito previo, UNA SOLA VEZ en esta maquina, antes de correr este script:
#   pyarmor reg <archivo-de-activacion>
# Sin esto el paso de ofuscacion falla y el script se detiene (a proposito --
# no genera un build sin ofuscar por error). Si "pyarmor reg" (sin argumentos)
# ya muestra "License Type: pyarmor-basic" en vez de "(trial)", ya esta listo.
#
# Uso:
#   ./build-mac.sh
#
# Salida: dist/Studio IVR.app y "dist/Studio IVR (<arch>).dmg"

set -euo pipefail
cd "$(dirname "$0")"

ARCH=$(uname -m)
echo "========================================="
echo "  Compilando Studio IVR para macOS ($ARCH)"
echo "========================================="

# --- 1. Herramientas base ---
command -v python3 >/dev/null || { echo "Falta python3. Instalalo (brew install python) y volve a correr."; exit 1; }
command -v node >/dev/null || { echo "Falta node. Instalalo (brew install node) y volve a correr."; exit 1; }
command -v brew >/dev/null || { echo "Falta Homebrew (necesario para create-dmg). Instalalo desde https://brew.sh y volve a correr."; exit 1; }

# --- 2. Entorno virtual + dependencias Python ---
if [ ! -d "venv" ]; then
    echo "-> Creando entorno virtual..."
    python3 -m venv venv
fi
source venv/bin/activate
echo "-> Instalando dependencias Python (puede tardar la primera vez, incluye torch/whisper)..."
pip install --upgrade pip wheel setuptools >/dev/null
pip install -r requirements.txt

echo "-> Instalando Chromium de Playwright..."
python -m playwright install chromium

# --- 3. Frontend ---
echo "-> Compilando frontend..."
( cd frontend && npm ci && npm run build )

# --- 4. Ofuscacion con PyArmor ---
echo "-> Ofuscando con PyArmor..."
rm -rf build/pyarmor_dist
if ! pyarmor gen -O build/pyarmor_dist -r main.py src desktop scripts; then
    echo ""
    echo "ERROR: PyArmor no pudo ofuscar (probablemente la licencia no esta"
    echo "registrada en esta maquina todavia). Corre primero:"
    echo "  pyarmor reg <archivo-de-activacion>"
    echo "y volve a ejecutar este script. No se genero ningun build."
    exit 1
fi

# --- 5. PyInstaller (.app) ---
echo "-> Empaquetando con PyInstaller..."
rm -rf "dist/Studio IVR.app" dist/StudioIVR
python -m PyInstaller studioivr-mac.spec --noconfirm

# --- 6. .dmg ---
echo "-> Creando .dmg..."
brew list create-dmg >/dev/null 2>&1 || brew install create-dmg
DMG_PATH="dist/Studio IVR ($ARCH).dmg"
rm -f "$DMG_PATH"
create-dmg \
    --volname "Studio IVR" \
    --window-pos 200 120 \
    --window-size 800 400 \
    --icon-size 100 \
    --icon "Studio IVR.app" 200 190 \
    --app-drop-link 600 185 \
    "$DMG_PATH" \
    "dist/Studio IVR.app"

# --- 7. Script de desbloqueo (sin firma todavia, Gatekeeper bloquea por defecto) ---
# Ver [[project-code-signing]]: hasta que exista el certificado Developer ID
# Application y se firme+notarice de verdad, cualquiera que abra el .app
# descargado/copiado necesita este paso (o clic-derecho > Abrir) una vez.
UNLOCK_SCRIPT="dist/Desbloquear y abrir Studio IVR.command"
cat > "$UNLOCK_SCRIPT" << 'EOF'
#!/bin/bash
# Studio IVR todavia no esta firmado (falta el certificado Developer ID
# Application de Apple) -- Gatekeeper bloquea la app por default. Este script
# saca la cuarentena y la abre. Una vez que exista firma+notarizacion real,
# este paso deja de hacer falta.
cd "$(dirname "$0")"
xattr -rd com.apple.quarantine "Studio IVR.app" 2>/dev/null
open "Studio IVR.app"
EOF
chmod +x "$UNLOCK_SCRIPT"

echo ""
echo "========================================="
echo "  Listo"
echo "========================================="
echo "  dist/Studio IVR.app"
echo "  $DMG_PATH"
echo "  $UNLOCK_SCRIPT   (corre esto para abrir la app sin firma)"
echo ""
echo "  Sin firmar/notarizar todavia -- ver [[project-code-signing]]."
echo "  Build no ofuscado NO se genera por este script: si PyArmor falla,"
echo "  el script se detiene arriba en vez de producir algo a medias."
