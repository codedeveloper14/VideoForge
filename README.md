# Studio IVR

VideoForge es una aplicación de escritorio desarrollada con PyWebView y Flask para automatizar tareas relacionadas con la generación de contenido multimedia.

## Características

- Interfaz nativa con PyWebView.
- Backend desarrollado con Flask.
- Código protegido con PyArmor.
- Instalador para Windows.
- Compilación para macOS (Universal2: Intel + Apple Silicon).
- Actualizaciones desde GitHub Releases.

## Requisitos

- Python 3.14+
- Git
- Windows 10/11
- Inno Setup 6 (solo para Windows)
- macOS 11+ (Big Sur)
- Xcode Command Line Tools (solo para macOS)

## Instalación

```bash
git clone https://github.com/codedeveloper14/VideoForge.git
cd VideoForge

python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

Cada persona que vaya a programar en el repo necesita además copiar `.env.example` a `.env` y completarlo con credenciales reales (no se suben al repo), y correr `pre-commit install` una vez para activar el formateo/lint automático en cada commit.

## Requisitos de hardware recomendados

Cada usuario inicia sesión con sus **propias** cuentas de Grok/Qwen/Meta/Whisk/Gentube/Flow — todo corre localmente en su máquina, sin servidor compartido. Quien quiera usar varias cuentas en paralelo (hasta 20-25 perfiles de Chrome/Chromium simultáneos entre los distintos proveedores) necesita una máquina con memoria suficiente para sostenerlos.

Medido de forma real en esta máquina de desarrollo (perfiles Chromium persistentes en blanco, sin generar contenido todavía): **~250 MB de RAM por perfil en reposo**. Bajo uso real (páginas cargadas, generando imágenes/video) el consumo por perfil sube — hay que contar con margen.

| Escenario | RAM recomendada | CPU recomendada |
|---|---|---|
| Uso liviano (1-5 cuentas) | 8 GB | 4 núcleos |
| Uso medio (10-15 cuentas) | 16 GB | 6 núcleos / 12 hilos |
| Uso completo (20-25 cuentas en paralelo) | 16-32 GB | 6+ núcleos / 12+ hilos (o Apple M1 o superior) |

Almacenamiento: se recomienda SSD (los perfiles de Chrome y las imágenes/videos generados se acumulan en disco). Conexión a internet estable, ya que cada cuenta activa mantiene su propia sesión/petición en curso.

## Autores

- **David Bermudez** — Python Developer
- **Gabriela Montilla** — Fullstack Developer 
