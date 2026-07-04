# Studio IVR

VideoForge es una aplicación de escritorio desarrollada con PyWebView y Flask para automatizar tareas relacionadas con la generación de contenido multimedia.

## Características

- Interfaz nativa con PyWebView.
- Backend desarrollado con Flask.
- Código protegido con PyArmor.
- Instalador para Windows.
- Compilación para macOS mediante GitHub Actions.
- Actualizaciones desde GitHub Releases.

## Requisitos

- Python 3.14+
- Git

### Windows

- Inno Setup 6

### macOS

- Xcode Command Line Tools

## Instalación

```bash
git clone https://github.com/codedeveloper14/VideoForge.git
cd VideoForge

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Ejecutar

```bash
python main.py
```

## Compilar

### Windows

```bash
python build_windows.py
```

### macOS

La compilación se realiza mediante GitHub Actions.

## Estructura

```
VideoForge/
├── main.py
├── app.py
├── requirements.txt
├── auth_module/
├── ui_embedded/
├── grok_multi/
├── static/
├── templates/
└── vf_db/
```

## Autores

David Bermudez Python developer
Gabriela Montilla Fullstack Developer
