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
