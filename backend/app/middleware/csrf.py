"""Double-submit cookie CSRF protection middleware."""

import http.cookies
import secrets

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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


class CSRFMiddleware:
    """Validate a double-submit CSRF token on state-changing requests.

    On every response the middleware ensures a non-httpOnly ``csrf_token``
    cookie exists.  The SPA reads this cookie and sends it back as the
    ``X-CSRF-Token`` header on POST/PUT/PATCH/DELETE requests.  The
    middleware rejects the request if the header is missing or does not
    match the cookie.

    Implemented as pure ASGI middleware (not BaseHTTPMiddleware) so that
    client disconnects mid-response don't leak pending asyncio tasks from
    Starlette's internal task group.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method: str = scope["method"]
        path: str = scope["path"]
        headers = Headers(scope=scope)
        cookies = _parse_cookie_header(headers.get("cookie", ""))
        csrf_cookie = cookies.get("csrf_token")

        is_safe = method in SAFE_METHODS
        is_exempt_path = any(path.startswith(prefix) for prefix in CSRF_EXEMPT_PREFIXES)
        has_api_key = bool(headers.get("x-api-key"))

        # Validate double-submit token on state-changing, non-exempt, cookie-auth
        # requests.
        if not is_safe and not is_exempt_path and not has_api_key:
            csrf_header = headers.get("x-csrf-token")
            if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                response = JSONResponse(
                    {"detail": "CSRF validation failed"}, status_code=403
                )
                await response(scope, receive, send)
                return

        # API-key authenticated requests are not cookie-based — pass through
        # without setting the CSRF cookie, matching the prior behavior.
        if has_api_key and not is_safe and not is_exempt_path:
            await self.app(scope, receive, send)
            return

        # If the client already has a csrf_token cookie there's nothing to set.
        if csrf_cookie:
            await self.app(scope, receive, send)
            return

        # Otherwise append a Set-Cookie header onto the outgoing response.
        from app.dependencies import get_settings

        set_cookie_value = _build_csrf_cookie_header(
            secure=get_settings().is_production
        )

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers_list = list(message.get("headers", []))
                headers_list.append(
                    (b"set-cookie", set_cookie_value.encode("latin-1"))
                )
                message["headers"] = headers_list
            await send(message)

        await self.app(scope, receive, send_with_cookie)


def _parse_cookie_header(cookie_header: str) -> dict[str, str]:
    """Parse a Cookie request header into a {name: value} dict."""
    cookies: dict[str, str] = {}
    if not cookie_header:
        return cookies
    parsed: http.cookies.SimpleCookie = http.cookies.SimpleCookie()
    try:
        parsed.load(cookie_header)
    except http.cookies.CookieError:
        return cookies
    for key, morsel in parsed.items():
        cookies[key] = morsel.value
    return cookies


def _build_csrf_cookie_header(*, secure: bool) -> str:
    """Build a Set-Cookie value matching the original middleware's settings."""
    cookie: http.cookies.SimpleCookie = http.cookies.SimpleCookie()
    cookie["csrf_token"] = secrets.token_urlsafe(32)
    morsel = cookie["csrf_token"]
    morsel["path"] = "/"
    morsel["samesite"] = "strict"
    morsel["max-age"] = 86400 * 30
    if secure:
        morsel["secure"] = True
    # httpOnly intentionally unset — JS must be able to read this cookie.
    return cookie.output(header="").strip()
