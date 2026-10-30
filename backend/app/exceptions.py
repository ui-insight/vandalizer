"""Centralized exception hierarchy for the Vandalizer backend.

Routers catch these and return appropriate HTTP responses.
Services raise these instead of bare ValueError / HTTPException.
"""


class AppError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str = "An error occurred", status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    """Resource not found."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404)


class AuthorizationError(AppError):
    """User lacks permission for this action."""

    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message, status_code=403)


class ValidationError(AppError):
    """Input validation failed."""

    def __init__(self, message: str = "Validation failed") -> None:
        super().__init__(message, status_code=400)


class ConflictError(AppError):
    """Resource already exists or state conflict."""

    def __init__(self, message: str = "Resource conflict") -> None:
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
    """A trial account has used up its included LLM token budget.

    ``code`` separates the two remedies this class carries: "budget_exhausted"
    (the account's own allowance — a top-up fixes it) and "fleet_paused" (the
    deployment's monthly ceiling — nothing the user can do).
    """

    def __init__(self, message: str = "Trial AI usage limit reached", code: str = "budget_exhausted") -> None:
        super().__init__(message, status_code=402)
        self.code = code


class TrialUnverifiedError(TrialSpendBlockedError):
    """A trial account must confirm its email address before spending tokens."""

    def __init__(self, message: str = "Confirm your email to use AI features") -> None:
        super().__init__(message, status_code=403)
