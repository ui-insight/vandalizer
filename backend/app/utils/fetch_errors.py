"""Human-readable descriptions of outbound URL fetch failures.

Many sites — especially .gov/.edu sites behind Akamai, Cloudflare, or
similar WAFs — refuse or silently stall automated clients. The raw
exceptions those failures produce are useless to end users: httpx timeout
exceptions often stringify to an empty string (so the UI showed a bare
"error" with no reason), and `str(HTTPStatusError)` is developer-speak.

``describe_fetch_error`` maps every failure mode of
:mod:`app.services.web_fetcher` to a plain-English reason, calling out
"the site is blocking automated access" where that is the likely cause,
so KB sources, workflow nodes, and chat attachments can show users why a
URL failed instead of just that it failed.
"""

from __future__ import annotations

from typing import Optional

import httpx

# Appended to failure modes where fetching a copy manually is the practical
# workaround.
_UPLOAD_HINT = (
    "Try downloading the page or file in your browser and uploading it "
    "directly instead."
)

_BLOCKED_HINT = (
    "This usually means the site blocks automated tools like Vandalizer. "
    + _UPLOAD_HINT
)


def describe_fetch_error(e: Exception) -> str:
    """Return a user-facing reason for a failed URL fetch.

    Always returns a non-empty string, even for exceptions whose ``str()``
    is empty (httpx timeouts, bare ConnectError).
    """
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        try:
            reason = (e.response.reason_phrase or "").strip()
        except Exception:
            reason = ""
        if not isinstance(reason, str):
            reason = ""
        label = f"HTTP {code} {reason}".strip()
        if code in (401, 403, 406, 451):
            return f"The website refused automated access ({label}). {_BLOCKED_HINT}"
        if code == 429:
            return (
                f"The website rate-limited the request ({label}). It may "
                f"throttle automated tools — try again later, or upload the "
                f"file directly."
            )
        if code in (404, 410):
            return (
                f"The page was not found ({label}). Check that the URL is "
                f"correct and still live."
            )
        if 400 <= code < 500:
            return f"The website rejected the request ({label}). {_BLOCKED_HINT}"
        if code >= 500:
            return (
                f"The website returned a server error ({label}). The site may "
                f"be down or refusing automated requests — try again later."
            )
        return f"Unexpected response from the website ({label})."

    if isinstance(e, httpx.TimeoutException):
        return (
            "The website did not respond before the request timed out. Some "
            "sites (including many .gov sites) silently stall automated tools "
            "as a form of bot protection. " + _UPLOAD_HINT
        )

    if isinstance(e, httpx.TooManyRedirects):
        return "The website kept redirecting the request without ever serving the page."

    if isinstance(e, httpx.ConnectError):
        detail = str(e).strip()
        if "certificate" in detail.lower() or "ssl" in detail.lower():
            return f"Could not establish a secure connection to the website ({detail[:300]})."
        return (
            "Could not connect to the website — the connection was refused or "
            "reset. The site may be down or blocking automated access."
        )

    if isinstance(e, httpx.RemoteProtocolError):
        return (
            "The website closed the connection before sending the page. This "
            "often means it is blocking automated access."
        )

    if isinstance(e, httpx.RequestError):
        detail = str(e).strip()
        suffix = f": {detail}" if detail else ""
        return f"Could not fetch the URL ({type(e).__name__}{suffix})."

    # ValueError from SSRF validation carries its own explanation; anything
    # else falls back to the exception text, never to an empty string.
    detail = str(e).strip()
    return detail or f"Failed to fetch the URL ({type(e).__name__})."


def describe_empty_fetch(status_code: Optional[int] = None) -> str:
    """Reason shown when a fetch "succeeded" but yielded no extractable text."""
    status = f" (HTTP {status_code})" if status_code else ""
    return (
        f"The website responded{status} but no text could be extracted. The "
        f"page may be image-only, rendered entirely in JavaScript, or serving "
        f"a block page to automated tools. " + _UPLOAD_HINT
    )
