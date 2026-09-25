"""Validate URLs before making server-side requests (SSRF protection)."""

import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BLOCKED_HOSTS = frozenset({
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
})


class InvalidAllowedHost(ValueError):
    """An allowlist entry that is not a bare hostname."""


_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$")


def normalize_allowed_host(entry: str) -> str:
    """Canonicalise one allowlist entry, or raise ``InvalidAllowedHost``.

    Accepts a bare hostname only -- lower-cased, trailing dot dropped. A
    scheme, path, port, wildcard or IP-literal-with-brackets is rejected
    rather than silently trimmed, because "https://router.example.edu/v1"
    saved as an exemption would never match and the admin would not know
    why. The cloud metadata hostnames are rejected outright: no
    configuration may exempt them.
    """
    host = (entry or "").strip().lower().rstrip(".")
    if not host:
        raise InvalidAllowedHost("empty entry")
    if "://" in host or "/" in host or "*" in host or ":" in host or any(c.isspace() for c in host):
        raise InvalidAllowedHost(
            f"{entry.strip()!r} is not a bare hostname -- enter the host only, "
            "without scheme, port, path or wildcard"
        )
    if host in BLOCKED_HOSTS:
        raise InvalidAllowedHost(f"{host!r} is a cloud metadata endpoint and can never be allowed")
    if not _HOSTNAME_RE.match(host):
        raise InvalidAllowedHost(f"{entry.strip()!r} is not a valid hostname")
    return host


def env_allowed_hosts() -> frozenset[str]:
    """Hostnames the operator exempted via ``OUTBOUND_URL_ALLOWED_HOSTS``.

    Comma-separated, exact hostnames. Settings are rebuilt on each call
    rather than cached here (the list is a handful of names) but in the
    Dockerized deploy the value arrives through the container environment,
    so changing it still means restarting the api and celery containers.
    Entries that are not bare hostnames -- or that name a metadata host --
    are skipped rather than failing every outbound request.
    """
    from app.config import Settings

    settings = Settings()
    raw = settings.outbound_url_allowed_hosts or ""
    # SSRF_ALLOWED_HOSTS is the v5 branch's name for the same list (its web
    # search reaches an on-campus search proxy); honour both.
    legacy = getattr(settings, "ssrf_allowed_hosts", "")
    if isinstance(legacy, str) and legacy:
        raw = f"{raw},{legacy}"
    out = set()
    for h in raw.split(","):
        try:
            out.add(normalize_allowed_host(h))
        except InvalidAllowedHost:
            continue
    return frozenset(out)


def allowed_private_hosts(config: object = None) -> frozenset[str]:
    """The effective allowlist: the operator's env list plus the admin's.

    ``config`` is the ``SystemConfig`` document (Beanie model or the raw
    pymongo dict) whose ``outbound_url_allowed_hosts`` the admin edits in
    System Config; ``None`` means env only. Callers pass the config they
    already hold rather than this module reading the database: the
    validator runs inside Celery threads, async routers and plain unit
    tests alike, and a hidden Mongo read from a validator would stall any
    process without a live database.
    """
    hosts = set(env_allowed_hosts())
    if config is not None:
        if isinstance(config, dict):
            raw = config.get("outbound_url_allowed_hosts") or []
        else:
            raw = getattr(config, "outbound_url_allowed_hosts", None) or []
        for h in raw:
            try:
                hosts.add(normalize_allowed_host(str(h)))
            except InvalidAllowedHost:
                continue
    return frozenset(hosts)


def normalize_crawl_url(url: str) -> str:
    """Normalize a URL for crawl deduplication: strip fragments, trailing slashes.

    ``example.com``, ``example.com/`` and ``example.com#section`` all serve the
    same page; normalizing them to one form keeps crawlers from fetching (and
    counting) the same page once per spelling.
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    clean = f"{parsed.scheme}://{parsed.netloc}{path}"
    if parsed.query:
        clean += f"?{parsed.query}"
    return clean


async def load_allowed_hosts() -> frozenset[str]:
    """The effective allowlist for an async request handler.

    Reads the System Config document and merges it with the env list. If
    the document cannot be read (database not initialised, transient
    outage) the admin list simply does not apply and the env list stands:
    a config-read failure must narrow what the server will fetch, never
    widen it, and must not turn a credential save into a 500.
    """
    try:
        from app.models.system_config import SystemConfig

        config = await SystemConfig.get_config()
    except Exception:  # noqa: BLE001 - fail closed on any read failure
        logger.warning("Could not read System Config for the outbound allowlist; using env list only", exc_info=True)
        config = None
    return allowed_private_hosts(config)


def validate_outbound_url(url: str, allowed_hosts: frozenset[str] | None = None) -> str:
    """Validate that *url* is safe for server-side HTTP requests.

    Blocks private/loopback/link-local IPs, non-HTTP(S) schemes, and
    cloud metadata endpoints.  Raises ``ValueError`` on rejection.

    A hostname in *allowed_hosts* (default: the operator's
    ``OUTBOUND_URL_ALLOWED_HOSTS`` alone; pass ``allowed_private_hosts(cfg)``
    to include the admin's System Config list) may resolve to a private
    (RFC 1918) address. Loopback, link-local and reserved ranges stay blocked
    even for a listed host, the scheme must still be HTTP(S), the metadata
    hostnames stay blocked, and the name must still resolve. The match is on the exact hostname, so an
    exemption for ``router.example.edu`` says nothing about any other name
    that happens to share its address.
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

    if allowed_hosts is None:
        allowed_hosts = allowed_private_hosts()
    private_ok = hostname.lower().rstrip(".") in allowed_hosts

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # Never exempt: an allowlisted name that resolves to loopback,
        # link-local (cloud metadata) or reserved space is a rebinding or
        # misconfiguration, not the campus service it was listed for.
        if ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError(f"URL resolves to blocked IP range: {ip}")
        if ip.is_private and not private_ok:
            raise ValueError(
                f"URL resolves to blocked IP range: {ip}. If {hostname} is a "
                "service this deployment should reach, an admin can allow it "
                "under Admin > System Config > Endpoints > Allowed private "
                "hosts (or an operator via OUTBOUND_URL_ALLOWED_HOSTS)."
            )

    return url


async def safe_get(client, url: str, *, max_redirects: int = 5, validate=None):
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

    ``validate`` lets callers pass their own module-level reference to
    :func:`validate_outbound_url` so tests that patch it at the call site
    also cover the per-hop checks here.
    """
    validate = validate or validate_outbound_url
    current = validate(url)
    for _ in range(max_redirects + 1):
        resp = await client.get(current)
        if resp.is_redirect:
            location = resp.headers.get("location")
            if not location:
                return resp
            # Resolve relative redirects against the URL we just requested,
            # then re-run the full SSRF policy on the absolute target.
            current = validate(str(resp.url.join(location)))
            continue
        return resp
    raise ValueError("Too many redirects")
