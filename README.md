# 🎬 VideoForge

**VideoForge** es una aplicación de escritorio moderna desarrollada con **PyWebView** y **Flask**, diseñada para automatizar la creación de contenido multimedia, la gestión de cuentas y procesos de scraping mediante una interfaz nativa rápida, segura y fácil de usar.

---

## ✨ Características

- 🖥️ **Interfaz nativa** utilizando PyWebView con HTML, CSS y JavaScript.
- ⚡ **Backend en Flask** para manejar toda la lógica de la aplicación.
- 🔒 **Protección del código** mediante PyArmor.
- 📦 **Instalador profesional para Windows** generado con Inno Setup.
- 🍎 **Compilación automática para macOS** mediante GitHub Actions.
- 🔄 **Actualizaciones automáticas** usando GitHub Releases.
- 🛡️ **Módulos protegidos**, incluyendo:
  - `auth_module`
  - `ui_embedded`
  - `grok_multi`
  - `vf_db_*`

---

# 📦 Instalación

## Windows

1. Descarga la última versión desde **Releases**.
2. Ejecuta `IVR_2.5_Setup.exe`.
3. Sigue el asistente de instalación.
4. Abre VideoForge desde el acceso directo del escritorio o desde el menú Inicio.

---

## macOS

1. Descarga el ejecutable `IVR_2.5` desde **Releases**.
2. Haz clic derecho sobre el archivo.
3. Selecciona **Abrir**.
4. Confirma nuevamente en **Abrir** cuando macOS lo solicite.

> **Importante:** Como la aplicación no está notarizada por Apple, macOS mostrará una advertencia de seguridad la primera vez que se ejecute.

---

# 🖥️ Requisitos del sistema

| Sistema | Versión mínima |
|---------|----------------|
| Windows | Windows 10 / 11 (64 bits) |
| macOS | macOS 10.15 Catalina o superior |

---

# 🛠️ Compilar desde el código fuente

## Requisitos

- Python **3.14** o superior
- Git
- Windows:
  - Inno Setup 6
- macOS:
  - Xcode Command Line Tools

---

## Clonar el proyecto

```bash
git clone https://github.com/codedeveloper14/VideoForge.git
cd VideoForge
```

---

## Crear un entorno virtual

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## Instalar dependencias

```bash
pip install -r requirements.txt
```

---

## Ejecutar la aplicación

```bash
python main.py
```

---

# 📁 Estructura del proyecto

```
VideoForge/
│
├── app.py
├── main.py
├── requirements.txt
├── README.md
│
├── auth_module/
├── ui_embedded/
├── grok_multi/
├── vf_db/
│
├── static/
├── templates/
│
└── build/
```

---

# 🔐 Protección del código

VideoForge utiliza **PyArmor** para proteger los módulos críticos frente a ingeniería inversa.

Los siguientes módulos se distribuyen ofuscados:

- auth_module
- ui_embedded
- grok_multi
- vf_db_*

---

# 🚀 Actualizaciones

La aplicación puede comprobar automáticamente nuevas versiones publicadas en **GitHub Releases**.

Cuando exista una actualización disponible, VideoForge notificará al usuario para descargar e instalar la versión más reciente.

---

# 📦 Distribución

### Windows

- Ejecutable `.exe`
- Instalador con Inno Setup

### macOS

- Ejecutable nativo
- Compilado automáticamente mediante GitHub Actions

---

# 🤝 Contribuciones

Las contribuciones son bienvenidas.

1. Haz un Fork.
2. Crea una rama.

```bash
git checkout -b feature/nueva-funcionalidad
```

3. Realiza tus cambios.

4. Haz commit.

```bash
git commit -m "Agregar nueva funcionalidad"
```

5. Sube la rama.

```bash
git push origin feature/nueva-funcionalidad
```

6. Abre un Pull Request.

---

# 📄 Licencia

Este proyecto se distribuye bajo la licencia **MIT**.

Consulta el archivo **LICENSE** para más información.

---

# 👨‍💻 Autor

**David Bermudez y Gabriela Montilla**

GitHub:
https://github.com/codedeveloper14

---

⭐ Si este proyecto te resulta útil, no olvides darle una estrella al repositorio.
