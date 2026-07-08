class AppError(Exception):
    """Base exception for all application-level errors."""


class ConfigError(AppError):
    """Raised when required configuration is missing or invalid."""
