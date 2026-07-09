"""Ventana nativa de escritorio (pywebview) que envuelve el backend Flask local.

Carpeta llamada 'desktop/' y no 'webview/' a proposito: pywebview se importa como
`import webview`, y si esta carpeta tuviera ese mismo nombre, Python resolveria el
paquete local en vez de la libreria real (confirmado de forma empirica) -- rompe el
import silenciosamente. Ver [[project-refactor-plan]] en la memoria del proyecto.

A diferencia del launcher.py original, NO se fuerza WEBVIEW_GUI=mshtml: MSHTML es el
motor de Internet Explorer y no corre JavaScript moderno, lo cual rompe cualquier app
React. Se deja que pywebview auto-detecte el mejor motor disponible (EdgeChromium en
Windows 10/11, que trae el runtime WebView2 instalado por defecto).
"""

import os
import sys
import threading
import time
import urllib.request
import webbrowser
from typing import Callable

from src.core.config import config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _wait_for_backend(health_url: str, max_wait: float = 20.0, interval: float = 0.25) -> bool:
    """Espera (polling) a que el backend Flask responda antes de abrir la ventana."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            urllib.request.urlopen(health_url, timeout=1)
            return True
        except Exception:
            time.sleep(interval)
    return False


def _screen_size() -> tuple[int, int]:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        return w, h
    except Exception:
        return 1920, 1080


def run(start_backend: Callable[[], None], url: str | None = None, title: str | None = None) -> None:
    """Arranca `start_backend` (una funcion sin argumentos que corre app.run(), debe
    bloquear) en un hilo de fondo, y abre la ventana nativa apuntando a `url` en el
    hilo principal (pywebview lo requiere ahi). Si pywebview no esta instalado, falla,
    o se pasa --browser / la variable VF_NO_WEBVIEW, cae a abrir el navegador por
    defecto del sistema en su lugar."""
    url = url or f"http://127.0.0.1:{config.flask_port}/"
    health_url = f"http://127.0.0.1:{config.flask_port}/api/health"
    title = title or config.app_name

    backend_thread = threading.Thread(target=start_backend, daemon=True, name="VF-Backend")
    backend_thread.start()

    logger.info("Esperando a que el backend responda...")
    if _wait_for_backend(health_url):
        logger.info("Backend listo.")
    else:
        logger.warning("Timeout esperando al backend -- se abre la ventana/navegador igual.")

    use_native = "--browser" not in sys.argv and not os.environ.get("VF_NO_WEBVIEW")
    if use_native:
        try:
            import webview
        except ImportError:
            use_native = False
            logger.warning("pywebview no instalado -- abre en el navegador. Ventana nativa: pip install pywebview")

    if not use_native:
        webbrowser.open(url)
        backend_thread.join()
        return

    from desktop import events

    screen_w, screen_h = _screen_size()
    window_kwargs = dict(
        title=title, url=url, width=screen_w, height=screen_h,
        resizable=True, min_size=(960, 640), text_select=True, maximized=True,
    )
    if sys.platform == "darwin":
        window_kwargs["fullscreen"] = False

    try:
        try:
            window = webview.create_window(**window_kwargs)
        except TypeError:
            # Versiones viejas de pywebview no aceptan 'maximized' en create_window --
            # se maximiza manualmente despues via events.on_shown.
            window_kwargs.pop("maximized", None)
            window = webview.create_window(**window_kwargs)

        window.events.closed += events.on_closed
        try:
            webview.start(debug=config.debug, http_server=False, func=lambda: events.on_shown(window))
        except TypeError:
            webview.start(debug=config.debug, http_server=False)
    except Exception as exc:
        logger.error("Error iniciando pywebview (%s) -- cae a navegador.", exc)
        webbrowser.open(url)
        backend_thread.join()
