class AppError(Exception):
    """Base exception for all application-level errors."""


class ConfigError(AppError):
    """Raised when required configuration is missing or invalid."""


class DatabaseError(AppError):
    """Raised when a database operation fails."""


class AuthError(AppError):
    """Base exception for authentication/authorization failures."""


class InvalidCredentialsError(AuthError):
    """Raised when a login attempt fails validation or credential check."""


class AccountLockedError(AuthError):
    """Raised when an IP is locked out after too many failed login attempts."""
