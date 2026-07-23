"""Manejadores de eventos de la ventana nativa (pywebview)."""

import os

from src.utils.logger import get_logger

logger = get_logger(__name__)


def on_closed() -> None:
    """Al cerrar la ventana, termina todo el proceso de inmediato (incluye el hilo
    daemon de Flask) -- salida limpia e instantanea, sin esperar cleanup de pywebview."""
    logger.info("Ventana cerrada. Saliendo.")
    os._exit(0)


def on_shown(window) -> None:
    """Fallback para versiones de pywebview que no aceptan 'maximized' en
    create_window: maximiza manualmente una vez que la ventana ya se muestra."""
    try:
        window.maximize()
    except Exception:
        pass
