import sys

if getattr(sys, "frozen", False) and len(sys.argv) >= 2 and sys.argv[1] == "--vf-grok-worker":
    # El .exe/.app compilado no tiene un Python suelto para invocar scripts/grok_worker.py,
    # asi que se relanza a si mismo con esta bandera para correr el worker en vez de la app.
    import runpy

    _worker_script = sys.argv[2]
    sys.argv = [_worker_script] + sys.argv[3:]
    runpy.run_path(_worker_script, run_name="__main__")
    raise SystemExit(0)

from src.core.config import config
from src.presentation.app import create_app
from src.utils.logger import get_logger, setup_logging


def main() -> None:
    setup_logging()
    logger = get_logger(__name__)
    logger.info("Iniciando %s backend en puerto %s", config.app_name, config.flask_port)

    app = create_app()
    app.run(host=config.flask_host, port=config.flask_port, debug=config.debug, use_reloader=False)


if __name__ == "__main__":
    main()
