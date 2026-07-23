import sys

if getattr(sys, "frozen", False) and len(sys.argv) >= 2 and sys.argv[1] == "--vf-grok-worker":
    # El .exe/.app compilado no tiene un Python suelto para invocar scripts/grok_worker.py,
    # asi que se relanza a si mismo con esta bandera para correr el worker en vez de la app.
    import runpy

    _worker_script = sys.argv[2]
    sys.argv = [_worker_script] + sys.argv[3:]
    runpy.run_path(_worker_script, run_name="__main__")
    raise SystemExit(0)

import threading

from src.core.config import config
from src.presentation.app import create_app
from src.utils.logger import get_logger, setup_logging


def _run_backend() -> None:
    """Bloqueante -- corre en un hilo de fondo (ver desktop.window.run), nunca en el
    hilo principal: pywebview necesita el hilo principal para la ventana nativa.

    La misma app se sirve en dos puertos: flask_port (8080, la API real que
    consume el frontend) y docs_port (8081, dedicado a Swagger/OpenAPI -- ver
    `_register_docs_port_gate` en src/presentation/app.py). Una sola instancia
    de `create_app()` -- evita duplicar el servidor WS de Flow, los hilos de
    sync, etc. -- corriendo en dos sockets via werkzeug."""
    app = create_app()

    docs_thread = threading.Thread(
        target=lambda: app.run(
            host=config.flask_host, port=config.docs_port, debug=False, use_reloader=False, threaded=True
        ),
        daemon=True,
        name="VF-Docs",
    )
    docs_thread.start()

    app.run(
        host=config.flask_host, port=config.flask_port, debug=config.debug, use_reloader=False, threaded=True
    )


def main() -> None:
    setup_logging()
    logger = get_logger(__name__)
    logger.info("Iniciando %s backend en puerto %s", config.app_name, config.flask_port)

    from desktop.window import run as run_window

    run_window(_run_backend)


if __name__ == "__main__":
    main()
