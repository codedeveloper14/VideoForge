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

import json
import os
import sys
import tempfile
import threading
import webbrowser
from collections.abc import Callable
from pathlib import Path

from src.core.config import config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# create_app() corre ensure_tables/ensure_stripe_table/docs.ensure_tables contra el
# MySQL remoto de Contabo antes de que Flask abra el puerto -- en un arranque en frio
# con la red lenta esto se observo tardando ~90-100s. 200s deja margen de sobra.
_LOADING_TIMEOUT_MS = 200_000
_LOADING_POLL_MS = 700


def _loading_html(target_url: str, health_url: str, title: str) -> str:
    """Pagina de espera autocontenida (sin depender del backend, que todavia no
    escucha) que hace polling a `health_url` en JS y recien navega a `target_url`
    cuando el backend contesta.

    Usa `fetch(..., {mode: 'no-cors'})`: no necesitamos leer la respuesta, solo
    saber si la conexion se pudo establecer -- eso evita depender de que el backend
    mande headers CORS, y funciona igual desde el origen null/file:// de la ventana
    nativa que desde el file:// del navegador de respaldo.

    Reemplaza el reintento anterior (`_reload_when_ready`), que vivia en Python y
    solo aplicaba a la ventana nativa de pywebview -- el navegador de respaldo
    (cuando WebView2 no esta disponible en la maquina) abria la URL una sola vez
    sin reintento alguno, y si el backend todavia no escuchaba quedaba con
    ERR_CONNECTION_REFUSED para siempre. Un mismo mecanismo para los dos caminos.
    """
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  html, body {{ height: 100%; margin: 0; }}
  body {{
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: #0f1115; color: #e6e6e6; font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
  }}
  .spinner {{
    width: 40px; height: 40px; border-radius: 50%;
    border: 3px solid #2a2d34; border-top-color: #6c8cff;
    animation: spin 0.8s linear infinite; margin-bottom: 20px;
  }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  #error {{ display: none; margin-top: 16px; text-align: center; }}
  button {{
    background: #6c8cff; color: #0f1115; border: none; padding: 10px 20px;
    border-radius: 6px; font-size: 14px; cursor: pointer; margin-top: 12px;
  }}
</style>
</head>
<body>
  <div class="spinner"></div>
  <div>Iniciando {title}...</div>
  <div id="error">
    <div>Esta tardando mas de lo normal.</div>
    <button onclick="location.reload()">Reintentar</button>
  </div>
  <script>
    var deadline = Date.now() + {_LOADING_TIMEOUT_MS};
    var healthUrl = {json.dumps(health_url)};
    var targetUrl = {json.dumps(target_url)};
    function poll() {{
      fetch(healthUrl, {{ mode: 'no-cors', cache: 'no-store' }})
        .then(function () {{ location.replace(targetUrl); }})
        .catch(function () {{
          if (Date.now() > deadline) {{
            document.getElementById('error').style.display = 'block';
            return;
          }}
          setTimeout(poll, {_LOADING_POLL_MS});
        }});
    }}
    poll();
  </script>
</body>
</html>"""


def _write_loading_page(html: str) -> Path:
    """Escribe la pagina de espera a un archivo temporal (webbrowser.open no acepta
    HTML inline como si permite pywebview via create_window(html=...))."""
    fd, path = tempfile.mkstemp(prefix="videoforge_loading_", suffix=".html")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(html)
    return Path(path)


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
    bloquear) en un hilo de fondo, y abre la ventana nativa en el hilo principal
    (pywebview lo requiere ahi) mostrando una pagina de espera que navega sola a
    `url` apenas el backend contesta. Si pywebview no esta instalado, falla, o se
    pasa --browser / la variable VF_NO_WEBVIEW, cae a abrir el navegador por
    defecto del sistema en su lugar (misma pagina de espera)."""
    url = url or f"http://127.0.0.1:{config.flask_port}/"
    health_url = f"http://127.0.0.1:{config.flask_port}/api/health"
    title = title or config.app_name

    backend_thread = threading.Thread(target=start_backend, daemon=True, name="VF-Backend")
    backend_thread.start()

    loading_html = _loading_html(url, health_url, title)

    use_native = "--browser" not in sys.argv and not os.environ.get("VF_NO_WEBVIEW")
    if use_native:
        try:
            import webview
        except ImportError:
            use_native = False
            logger.warning(
                "pywebview no instalado -- abre en el navegador. Ventana nativa: pip install pywebview"
            )

    if not use_native:
        webbrowser.open(_write_loading_page(loading_html).as_uri())
        backend_thread.join()
        return

    from desktop import events

    screen_w, screen_h = _screen_size()
    window_kwargs = dict(
        title=title,
        html=loading_html,
        width=screen_w,
        height=screen_h,
        resizable=True,
        min_size=(960, 640),
        text_select=True,
        maximized=True,
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
        webbrowser.open(_write_loading_page(loading_html).as_uri())
        backend_thread.join()
