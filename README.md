# Studio IVR (VideoForge)

Aplicación de escritorio para automatización de generación de contenido multimedia con IA.

---

##  Características

- **Interfaz nativa** con PyWebView
- **Backend Flask** para API y lógica de negocio
- **Código protegido** con PyArmor (ofuscación)
- **Instalador para Windows** con Inno Setup
- **Compilación para macOS** (Universal2: Intel + Apple Silicon M1/M2/M3)
- **WebSocket Bridge** para comunicación con extensión de Chrome
- **Generación de imágenes** con Google Flow / Whisk
- **Actualizaciones** desde GitHub Releases

---

##  Requisitos

| Requisito | Versión |
|-----------|---------|
| Python | 3.14+ |
| Git | Cualquiera |
| Windows | 10/11 |
| macOS | 11+ (Big Sur) |
| Inno Setup | 6 (solo para Windows) |
| Xcode CLI | (solo para macOS) |

---

##  Instalación para Desarrollo

```bash
# 1. Clonar el repositorio
git clone https://github.com/codedeveloper14/VideoForge.git
cd VideoForge

# 2. Crear entorno virtual
python -m venv venv

# 3. Activar entorno virtual
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# 4. Instalar dependencias
pip install -r requirements.txt
```

## Autores

- **David Bermudez** — Python Developer
- **Gabriela Montilla** — Fullstack Developer
