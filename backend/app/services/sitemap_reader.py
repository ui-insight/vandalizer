"""Read a site's sitemap: the pages it says it has, for the user to pick from.

Adding a site to a knowledge base meant pasting its pages one by one, or
crawling — which follows whatever links the first page happens to have and
stops at a page count, so it misses sections and picks up navigation. A
sitemap is the site's own list of its pages (feature request). This reads it;
the user picks pages, and the picked ones go through the ordinary add-URLs path.

Given a sitemap URL it reads that file. Given anything else on a site it asks
the site where its sitemap is (``Sitemap:`` lines in robots.txt), then tries
``/sitemap.xml`` and ``/sitemap_index.xml``. A sitemap index is followed into
its child sitemaps, up to ``MAX_SITEMAP_FILES`` files and ``MAX_PAGES`` pages.

Every request — each redirect hop included — passes the outbound URL check,
the XML is parsed with defusedxml (no entity expansion, no external DTDs),
and a file is cut off at ``MAX_FILE_BYTES``, gzipped or not.
"""

from __future__ import annotations

import logging
import zlib
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx

logger = logging.getLogger(__name__)

MAX_SITEMAP_FILES = 25
MAX_PAGES = 5000
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT_SECONDS = 20.0

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Vandalizer/1.0; +knowledge-base sitemap reader)",
    "Accept": "application/xml,text/xml,application/x-gzip,text/plain;q=0.8,*/*;q=0.5",
}


class SitemapError(Exception):
    """The sitemap could not be found or read; the message is for the user."""


@dataclass
class SitemapPage:
    url: str
    lastmod: str | None = None


@dataclass
class SitemapResult:
    sitemap_url: str
    pages: list[SitemapPage] = field(default_factory=list)
    sitemaps_read: int = 0
    truncated: bool = False
    errors: list[str] = field(default_factory=list)


def looks_like_sitemap(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return path.endswith((".xml", ".xml.gz")) or "sitemap" in path


def _gunzip(data: bytes) -> bytes:
    # Bounded: a few KB of gzip can expand to gigabytes.
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = inflater.decompress(data, MAX_FILE_BYTES + 1)
    if len(out) > MAX_FILE_BYTES:
        raise SitemapError(f"The sitemap is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB once unzipped.")
    return out


async def _get(client: httpx.AsyncClient, url: str, allowed_hosts: frozenset[str]) -> tuple[str, bytes]:
    """GET with every hop checked; returns (final_url, body). Raises SitemapError."""
    from app.utils.url_validation import validate_outbound_url

    current = url
    for _ in range(MAX_REDIRECTS + 1):
        try:
            validate_outbound_url(current, allowed_hosts=allowed_hosts)
        except ValueError as e:
            raise SitemapError(f"{current} can't be fetched: {e}") from e
        try:
            async with client.stream("GET", current) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    current = urljoin(current, resp.headers["location"])
                    continue
                if resp.status_code >= 400:
                    raise SitemapError(f"{current} returned HTTP {resp.status_code}.")
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_FILE_BYTES:
                        raise SitemapError(f"{current} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
                return current, bytes(body)
        except httpx.TimeoutException as e:
            raise SitemapError(f"{current} took longer than {int(TIMEOUT_SECONDS)} seconds to answer.") from e
        except httpx.HTTPError as e:
            raise SitemapError(f"{current} could not be reached ({type(e).__name__}).") from e
    raise SitemapError(f"{url} redirected more than {MAX_REDIRECTS} times.")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_sitemap(data: bytes) -> tuple[str, list[SitemapPage], list[str]]:
    """Parse one sitemap file: ``(kind, pages, child_sitemaps)``, kind being
    ``"urlset"`` or ``"sitemapindex"``. Raises SitemapError if it isn't one."""
    import defusedxml.ElementTree as ET
    from defusedxml import DefusedXmlException

    if data[:2] == b"\x1f\x8b":
        data = _gunzip(data)
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, DefusedXmlException) as e:
        raise SitemapError("That address isn't a sitemap: it isn't valid sitemap XML.") from e

    kind = _local(root.tag)
    if kind not in ("urlset", "sitemapindex"):
        raise SitemapError("That address isn't a sitemap: its XML is not a <urlset> or <sitemapindex>.")
    pages: list[SitemapPage] = []
    children: list[str] = []
    for entry in root:
        values = {_local(child.tag): (child.text or "").strip() for child in entry}
        loc = values.get("loc", "")
        if not loc.startswith(("http://", "https://")):
            continue
        if kind == "urlset":
            pages.append(SitemapPage(url=loc, lastmod=values.get("lastmod") or None))
        else:
            children.append(loc)
    return kind, pages, children


async def _discover(client: httpx.AsyncClient, url: str, allowed_hosts: frozenset[str]) -> list[str]:
    """Sitemap candidates for a site address: robots.txt's, then the usual names."""
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    found: list[str] = []
    try:
        _, robots = await _get(client, f"{origin}/robots.txt", allowed_hosts)
        for line in robots.decode("utf-8", "replace").splitlines():
            key, _, value = line.partition(":")
            if key.strip().lower() == "sitemap" and value.strip().startswith(("http://", "https://")):
                found.append(value.strip())
    except SitemapError:
        pass  # no robots.txt is common; fall through to the usual names
    found += [f"{origin}/sitemap.xml", f"{origin}/sitemap_index.xml"]
    return list(dict.fromkeys(found))


async def read_sitemap(url: str) -> SitemapResult:
    """Pages listed by the sitemap at, or for the site of, ``url``. Raises
    SitemapError when no sitemap is found or the given one can't be read."""
    from app.utils.url_validation import load_allowed_hosts

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    allowed_hosts = await load_allowed_hosts()

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False, headers=_HEADERS) as client:
        if looks_like_sitemap(url):
            candidates = [url]
        else:
            candidates = await _discover(client, url, allowed_hosts)

        # The first candidate that parses is the sitemap; the rest were guesses.
        start: tuple[str, bytes] | None = None
        first_error: SitemapError | None = None
        for candidate in candidates:
            try:
                final_url, body = await _get(client, candidate, allowed_hosts)
                parse_sitemap(body)
                start = (final_url, body)
                break
            except SitemapError as e:
                first_error = first_error or e
        if start is None:
            if len(candidates) == 1:
                raise first_error or SitemapError("No sitemap was found.")
            host = urlsplit(url).netloc
            raise SitemapError(
                f"No sitemap was found for {host} (checked robots.txt, /sitemap.xml and /sitemap_index.xml). "
                "Enter the sitemap's address if the site has one elsewhere."
            )

        result = SitemapResult(sitemap_url=start[0])
        queue: list[tuple[str, bytes | None]] = [start]
        visited: set[str] = set()
        seen_pages: set[str] = set()
        while queue and result.sitemaps_read < MAX_SITEMAP_FILES:
            sitemap_url, queued_body = queue.pop(0)
            if sitemap_url in visited:
                continue
            visited.add(sitemap_url)
            try:
                if queued_body is None:
                    sitemap_url, queued_body = await _get(client, sitemap_url, allowed_hosts)
                _, pages, children = parse_sitemap(queued_body)
            except SitemapError as e:
                # One unreadable child sitemap leaves the rest worth showing.
                result.errors.append(str(e))
                continue
            result.sitemaps_read += 1
            for page in pages:
                if page.url in seen_pages:
                    continue
                if len(result.pages) >= MAX_PAGES:
                    result.truncated = True
                    break
                seen_pages.add(page.url)
                result.pages.append(page)
            queue.extend((child, None) for child in children if child not in visited)
            if result.truncated:
                break
        if queue and not result.truncated and result.sitemaps_read >= MAX_SITEMAP_FILES:
            result.truncated = True
    return result
