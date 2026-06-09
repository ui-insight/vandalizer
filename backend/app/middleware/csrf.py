"""Double-submit cookie CSRF protection middleware."""

import http.cookies
import logging
import secrets

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Paths that are expected to receive cross-origin requests (webhooks, OAuth
# callbacks) or are themselves login endpoints that issue the CSRF cookie.
CSRF_EXEMPT_PREFIXES = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/logout",
    "/api/auth/refresh",
    "/api/auth/oauth/",
    # SAML SSO: the IdP returns a self-submitting form that POSTs to
    # /api/auth/saml/acs cross-site. It can't carry a CSRF header and Lax
    # cookies don't ride along on cross-site POSTs — only an exemption
    # works here. The endpoint validates the signed SAML assertion itself.
    "/api/auth/saml/",
    "/api/auth/config",
    # Team invite / public join-link acceptance. The POST fires immediately
    # after a cross-site SSO redirect (Azure/SAML), the exact window where the
    # freshly-set CSRF cookie can be briefly unreadable by document.cookie — so
    # the double-submit header is unreliable here and produces spurious 403s.
    # Exemption is safe: the unguessable URL token is the actual authorization
    # (accept_invite/accept_join_link authorize on the token, not the session),
    # so a forged cross-site POST gains nothing an attacker holding the token
    # couldn't already do directly. Same reasoning as the SAML ACS exemption.
    # Scoped to the accept sub-routes only, not all of /api/teams.
    "/api/teams/invite/accept/",
    "/api/teams/join-link/accept/",
    "/api/webhooks/",
    "/api/demo/apply",
    "/api/demo/request-contact",
    "/api/demo/status/",
    "/api/demo/feedback/",
    "/api/health",
    "/api/certification/levels",
)

# The modern cookie carries the ``__Host-`` prefix, which the browser enforces
# to be ``Secure``, ``Path=/``, and ``Domain``-less.  That guarantees only one
# cookie of this name can live in the jar — immune to collisions from sibling
# apps on a shared parent domain, prior deploys that set different attributes,
# or proxies.  HTTP (development) cannot satisfy the prefix's ``Secure``
# requirement, so we fall back to the legacy name there.
MODERN_COOKIE_NAME = "__Host-csrf_token"
LEGACY_COOKIE_NAME = "csrf_token"


def _primary_cookie_name(*, secure: bool) -> str:
    return MODERN_COOKIE_NAME if secure else LEGACY_COOKIE_NAME


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

        from app.dependencies import get_settings

        settings = get_settings()
        primary_name = _primary_cookie_name(secure=settings.is_production)

        method: str = scope["method"]
        path: str = scope["path"]
        headers = Headers(scope=scope)
        cookie_header = headers.get("cookie", "")
        cookies = _parse_cookie_header(cookie_header)
        # Accept the header if it matches *any* cookie value the browser is
        # sending.  A stale old-SPA tab will only read the legacy name (its
        # regex doesn't match the ``__Host-`` prefix), while a fresh SPA reads
        # the modern one.  When duplicate ``csrf_token`` cookies exist in the
        # jar (sibling app on a parent domain, prior deploy with a different
        # Path), the old SPA's regex picks the *first* value while SimpleCookie
        # picks the *last* — so we must enumerate every legacy value, not just
        # the deduped one, or the old-SPA header value won't be in the set.
        csrf_modern = cookies.get(primary_name)
        legacy_values = _all_cookie_values(cookie_header, LEGACY_COOKIE_NAME)

        is_safe = method in SAFE_METHODS
        is_exempt_path = any(path.startswith(prefix) for prefix in CSRF_EXEMPT_PREFIXES)
        has_api_key = bool(headers.get("x-api-key"))

        # Validate double-submit token on state-changing, non-exempt, cookie-auth
        # requests.
        if not is_safe and not is_exempt_path and not has_api_key:
            csrf_header = headers.get("x-csrf-token")
            valid_values = {v for v in (csrf_modern, *legacy_values) if v}
            if not csrf_header or csrf_header not in valid_values:
                # Log enough to diagnose: which side is missing/mismatched,
                # which cookie name the browser sent, and where the user was.
                # Values are never logged — only their presence/length.
                logger.warning(
                    "CSRF validation failed",
                    extra={
                        "path": path,
                        "method": method,
                        "has_modern_cookie": bool(csrf_modern),
                        "legacy_cookie_count": len(legacy_values),
                        "has_csrf_header": bool(csrf_header),
                        "header_len": len(csrf_header) if csrf_header else 0,
                        "modern_len": len(csrf_modern) if csrf_modern else 0,
                        "any_cookie_present": bool(valid_values),
                        "origin": headers.get("origin", ""),
                        "referer": headers.get("referer", ""),
                        "user_agent": headers.get("user-agent", "")[:200],
                    },
                )
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

        # Only skip setting if the *primary* cookie is already present.  A user
        # holding only the legacy cookie should still receive the modern one so
        # subsequent requests can ignore stale duplicates of the old name.
        if cookies.get(primary_name):
            await self.app(scope, receive, send)
            return

        set_cookie_value = _build_csrf_cookie_header(
            name=primary_name, secure=settings.is_production
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


def _all_cookie_values(cookie_header: str, name: str) -> list[str]:
    """Return every value the header carries for ``name``, including duplicates.

    SimpleCookie collapses duplicate names to a single value (last-write-wins),
    which loses any earlier value a stale old-SPA regex would have grabbed.
    For double-submit validation we need the full multiset.
    """
    if not cookie_header:
        return []
    values: list[str] = []
    for chunk in cookie_header.split(";"):
        key, sep, value = chunk.strip().partition("=")
        if sep and key == name:
            values.append(value)
    return values


def _build_csrf_cookie_header(*, name: str, secure: bool) -> str:
    """Build a Set-Cookie value for the CSRF cookie.

    Assembled by hand rather than via ``SimpleCookie`` so the ``__Host-``
    prefix in the name passes through verbatim without any quoting.
    httpOnly is intentionally omitted — JS must be able to read this cookie.

    ``SameSite=Lax`` (not Strict) because Strict has a documented browser
    quirk: after an OAuth/SAML callback (a cross-site request that sets a
    fresh Strict cookie), Chrome puts the just-set cookie in a transitional
    "lax-allow-unsafe" mode on the next navigation, so ``document.cookie``
    can briefly return empty for it. The SPA then can't echo the value into
    the ``X-CSRF-Token`` header and the next POST 403s. Lax has none of
    that quirk and provides equivalent CSRF protection: the double-submit
    pattern's security comes from the Same-Origin Policy preventing
    cross-origin *reads* of the cookie, not from SameSite. Lax already
    blocks cross-site POSTs (the actual attack vector). This matches what
    Django/Laravel/OWASP recommend for CSRF token cookies and aligns with
    the ``access_token`` cookie which is also Lax.
    """
    value = secrets.token_urlsafe(32)
    parts = [
        f"{name}={value}",
        "Path=/",
        "SameSite=Lax",
        f"Max-Age={86400 * 30}",
    ]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)
