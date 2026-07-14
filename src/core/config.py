import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from src.utils.platform_utils import get_app_data_dir

load_dotenv()


@dataclass(frozen=True)
class Config:
    app_name: str = "Studio IVR"
    # Version del paquete instalable (instalador/actualizaciones), NO del refactor en
    # si -- reinicia en 1.0.0 porque este relanzamiento es el primer release real de
    # produccion de la app (ver decision de versionado). Bump manual antes de cada
    # release nueva; el chequeo de actualizaciones compara esto contra el ultimo tag
    # de GitHub Releases.
    app_version: str = "1.0.0"
    flask_host: str = "0.0.0.0"
    flask_port: int = 8080
    docs_port: int = 8081
    websocket_port: int = 5557
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8080")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    app_data_dir: Path = get_app_data_dir()

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY_INLINE")
    openai_whisper_key: str | None = os.getenv("OPENAI_WHISPER_KEY")
    replicate_api_key: str | None = os.getenv("REPLICATE_API_KEY")
    replicate_whisperx_model: str | None = os.getenv("REPLICATE_WHISPERX_MODEL")
    stripe_api_key: str | None = os.getenv("STRIPE_API_KEY")
    stripe_secret_key: str | None = os.getenv("STRIPE_SECRET_KEY")
    openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY")
    openrouter_whisk_sanitize_model: str = os.getenv("OPENROUTER_WHISK_SANITIZE_MODEL", "openai/gpt-4o-mini")

    db_host: str | None = os.getenv("DB_HOST")
    db_host_fallback: str | None = os.getenv("DB_HOST_FALLBACK")
    db_user: str | None = os.getenv("DB_USER")
    db_password: str | None = os.getenv("DB_PASSWORD")
    db_name: str | None = os.getenv("DB_NAME")
    db_port: int = int(os.getenv("DB_PORT", "3306"))

    app_secret_key: str | None = os.getenv("APP_SECRET_KEY")
    session_minutes: int = 40
    max_failed_login_attempts: int = 5
    lockout_seconds: int = 300

    @property
    def session_cookie_secure(self) -> bool:
        """La cookie de sesion solo debe llevar Secure cuando realmente se sirve por
        HTTPS -- si no, el navegador nunca la reenvia y rompe el login. En local
        (PUBLIC_BASE_URL=http://localhost:...) da False; en el servidor real, con
        PUBLIC_BASE_URL=https://..., da True automaticamente."""
        return self.public_base_url.startswith("https://")


config = Config()
