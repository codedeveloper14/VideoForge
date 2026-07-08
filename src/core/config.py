import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from src.utils.platform_utils import get_app_data_dir

load_dotenv()


@dataclass(frozen=True)
class Config:
    app_name: str = "VideoForge"
    flask_host: str = "0.0.0.0"
    flask_port: int = 8080
    websocket_port: int = 5557
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    app_data_dir: Path = get_app_data_dir()

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY_INLINE")
    openai_whisper_key: str | None = os.getenv("OPENAI_WHISPER_KEY")
    replicate_api_key: str | None = os.getenv("REPLICATE_API_KEY")
    replicate_whisperx_model: str | None = os.getenv("REPLICATE_WHISPERX_MODEL")
    stripe_api_key: str | None = os.getenv("STRIPE_API_KEY")


config = Config()
