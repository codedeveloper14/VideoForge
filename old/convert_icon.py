import os
from PIL import Image
import subprocess
import shutil

# Verificar que el icono existe
icon_path = 'assets/icon.ico'
if not os.path.exists(icon_path):
    print(f"No se encontró {icon_path}")
    exit(1)

# Crear carpeta para el iconset
iconset_dir = 'assets/icon.iconset'
os.makedirs(iconset_dir, exist_ok=True)

# Tamaños necesarios para macOS
sizes = [
    (16, 16),
    (32, 32),
    (64, 64),
    (128, 128),
    (256, 256),
    (512, 512)
]

try:
    # Cargar el icono .ico
    img = Image.open(icon_path)
    print(f"Icono cargado: {img.size} {img.mode}")
    
    # Guardar cada tamaño
    for w, h in sizes:
        resized = img.resize((w, h), Image.Resampling.LANCZOS)
        png_path = os.path.join(iconset_dir, f'icon_{w}x{h}.png')
        resized.save(png_path, 'PNG')
        print(f"Creado: {png_path}")

    # Crear el archivo .icns
    icns_path = 'assets/icon.icns'
    if shutil.which('iconutil'):
        cmd = ['iconutil', '-c', 'icns', iconset_dir, '-o', icns_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and os.path.exists(icns_path):
            print(f"Icono convertido a: {icns_path}")
        else:
            print(f" Error al convertir: {result.stderr}")
            exit(1)
    else:
        print(" iconutil no encontrado")
        exit(1)
except Exception as e:
    print(f" Error: {e}")
    exit(1)
