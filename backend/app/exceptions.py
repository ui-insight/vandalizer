"""Centralized exception hierarchy for the Vandalizer backend.

Routers catch these and return appropriate HTTP responses.
Services raise these instead of bare ValueError / HTTPException.
"""


class AppError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str = "An error occurred", status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    """Resource not found."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


class AuthorizationError(AppError):
    """User lacks permission for this action."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, status_code=403)


class ValidationError(AppError):
    """Input validation failed."""

    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, status_code=400)


class ConflictError(AppError):
    """Resource already exists or state conflict."""

    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message, status_code=409)
