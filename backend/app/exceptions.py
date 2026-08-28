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


class TrialSpendBlockedError(AppError):
    """Base for every reason a trial account may not spend LLM tokens.

    All of these raise from the same place — metering-scope entry — so callers
    that degrade gracefully (skip the step, tell the user, keep the job
    moving) must catch *this*, not one specific subclass. Catching a subclass
    is how a new gate silently turns a handled degradation back into an
    unhandled failure.
    """


class TrialBudgetExceededError(TrialSpendBlockedError):
    """A trial account has used up its included LLM token budget."""

    def __init__(self, message: str = "Trial AI usage limit reached"):
        super().__init__(message, status_code=402)


class TrialUnverifiedError(TrialSpendBlockedError):
    """A trial account must confirm its email address before spending tokens."""

    def __init__(self, message: str = "Confirm your email to use AI features"):
        super().__init__(message, status_code=403)
