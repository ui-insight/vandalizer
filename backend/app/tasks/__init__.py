"""Shared Celery task utilities."""

# Transient exceptions that are safe to retry with backoff.
# Permanent errors (ValueError, KeyError, TypeError, etc.) should NOT be retried.
TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)
