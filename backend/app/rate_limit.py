from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.utils.security import hash_api_token

limiter = Limiter(key_func=get_remote_address)


def mgmt_key_func(request: Request) -> str:
    """Per-key bucket for the management API.

    Prefers the SHA-256 hash of the X-API-Key header so a single noisy
    consumer is throttled by *its key*, not by the (likely shared)
    client IP. Falls back to the remote address for unauthenticated
    requests so they still get rate-limited.
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"mgmt:{hash_api_token(api_key)}"
    return f"ip:{get_remote_address(request)}"
