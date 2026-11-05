"""Domain and security exception hierarchy."""


class AppError(Exception):
    """Base application exception."""

    def __init__(self, message: str, code: str = "APP_ERROR", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class AuthenticationError(AppError):
    def __init__(self, message: str = "Invalid credentials or expired session"):
        super().__init__(message=message, code="AUTH_ERROR", status_code=401)


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "Insufficient user permissions"):
        super().__init__(message=message, code="FORBIDDEN", status_code=403)


class ResourceNotFoundError(AppError):
    def __init__(self, message: str = "Requested resource was not found"):
        super().__init__(message=message, code="NOT_FOUND", status_code=404)


class ConflictError(AppError):
    def __init__(self, message: str = "Resource conflict or duplicate entry"):
        super().__init__(message=message, code="CONFLICT", status_code=409)


class SecurityConfigurationError(AppError):
    def __init__(self, message: str = "Encrypted credential could not be verified"):
        super().__init__(message=message, code="SECURITY_CONFIG_ERROR", status_code=500)


class TelegramOperationError(AppError):
    def __init__(self, message: str, code: str = "TELEGRAM_ERROR", status_code: int = 400):
        super().__init__(message=message, code=code, status_code=status_code)


class AmbiguousPublishError(Exception):
    """Raised when network/client fails AFTER dispatching publish call so delivery is uncertain (UNKNOWN)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class TransientPublishError(Exception):
    """Raised for recoverable errors (e.g., FloodWait, temporary disconnect before send)."""

    def __init__(self, message: str, retry_after_seconds: int | None = None, code: str = "TRANSIENT_ERROR"):
        super().__init__(message)
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        self.code = code


class PermanentPublishError(Exception):
    """Raised for non-recoverable target errors (e.g., ChatWriteForbidden, ChannelPrivate)."""

    def __init__(self, message: str, code: str = "PERMANENT_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code
