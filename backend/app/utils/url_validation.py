"""Validate URLs before making server-side requests (SSRF protection)."""

import ipaddress
import socket
from urllib.parse import urlparse

BLOCKED_HOSTS = frozenset({
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
})


def validate_outbound_url(url: str) -> str:
    """Validate that *url* is safe for server-side HTTP requests.

    Blocks private/loopback/link-local IPs, non-HTTP(S) schemes, and
    cloud metadata endpoints.  Raises ``ValueError`` on rejection.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Blocked URL scheme: {parsed.scheme!r}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    if hostname in BLOCKED_HOSTS:
        raise ValueError(f"Blocked hostname: {hostname}")

    # Resolve DNS and reject private / reserved addresses
    try:
        infos = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError(f"URL resolves to blocked IP range: {ip}")

    return url


async def safe_get(client, url: str, *, max_redirects: int = 5):
    """GET *url*, re-validating every redirect hop against the SSRF policy.

    ``httpx``'s built-in ``follow_redirects`` validates nothing, so a public
    URL that we cleared with :func:`validate_outbound_url` can still ``302`` to
    ``http://169.254.169.254/`` or another internal host. We validate the
    initial URL and every ``Location`` before connecting, so the link-local /
    private / reserved block applies to the *final* address actually fetched —
    not just the first hop.

    The caller must pass an ``httpx.AsyncClient`` created with
    ``follow_redirects=False``. Raises ``ValueError`` (the same type
    :func:`validate_outbound_url` raises) when a hop is blocked or the redirect
    chain is too long, so existing ``except ValueError`` handlers catch it.
    Returns the final non-redirect ``httpx.Response``.
    """
    current = validate_outbound_url(url)
    for _ in range(max_redirects + 1):
        resp = await client.get(current)
        if resp.is_redirect:
            location = resp.headers.get("location")
            if not location:
                return resp
            # Resolve relative redirects against the URL we just requested,
            # then re-run the full SSRF policy on the absolute target.
            current = validate_outbound_url(str(resp.url.join(location)))
            continue
        return resp
    raise ValueError("Too many redirects")
