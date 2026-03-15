"""Double-submit cookie CSRF protection middleware."""

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Paths that are expected to receive cross-origin requests (webhooks, OAuth
# callbacks) or are themselves login endpoints that issue the CSRF cookie.
CSRF_EXEMPT_PREFIXES = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/logout",
    "/api/auth/refresh",
    "/api/auth/oauth/",
    "/api/auth/config",
    "/api/webhooks/",
    "/api/demo/apply",
    "/api/demo/status/",
    "/api/demo/feedback/",
    "/api/health",
    "/api/certification/levels",
)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Validate a double-submit CSRF token on state-changing requests.

    On every response the middleware ensures a non-httpOnly ``csrf_token``
    cookie exists.  The SPA reads this cookie and sends it back as the
    ``X-CSRF-Token`` header on POST/PUT/PATCH/DELETE requests.  The
    middleware rejects the request if the header is missing or does not
    match the cookie.
    """

    async def dispatch(self, request: Request, call_next):
        # Let safe (read-only) methods through
        if request.method in SAFE_METHODS:
            response = await call_next(request)
            _ensure_csrf_cookie(response, request)
            return response

        # Exempt specific paths
        path = request.url.path
        if any(path.startswith(prefix) for prefix in CSRF_EXEMPT_PREFIXES):
            response = await call_next(request)
            _ensure_csrf_cookie(response, request)
            return response

        # API-key authenticated requests are not cookie-based → skip CSRF
        if request.headers.get("x-api-key"):
            return await call_next(request)

        # Validate double-submit token
        csrf_cookie = request.cookies.get("csrf_token")
        csrf_header = request.headers.get("x-csrf-token")

        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            return Response("CSRF validation failed", status_code=403)

        response = await call_next(request)
        _ensure_csrf_cookie(response, request)
        return response


def _ensure_csrf_cookie(response: Response, request: Request) -> None:
    """Set the csrf_token cookie if the client doesn't already have one."""
    if not request.cookies.get("csrf_token"):
        from app.dependencies import get_settings

        settings = get_settings()
        response.set_cookie(
            "csrf_token",
            secrets.token_urlsafe(32),
            httponly=False,  # JS must be able to read this
            secure=settings.is_production,
            samesite="lax",
            path="/",
            max_age=86400 * 30,
        )
