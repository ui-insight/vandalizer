"""Unified outbound web fetcher.

Two-stage pipeline:
  1. Plain httpx GET → trafilatura main-content extraction.
  2. If the extracted text is shorter than ``web_fetcher_min_chars`` (a sign of
     a JS-rendered shell like Next.js), fall back to headless Chromium via
     Playwright and re-extract from the post-JS DOM.

All callers (chat URL attachments, workflow ``AddWebsite`` nodes, knowledge-
base URL sources) should route through this module rather than calling httpx
themselves so SPA pages produce usable content everywhere.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from app.config import Settings
from app.utils.url_validation import validate_outbound_url

logger = logging.getLogger(__name__)

# Trafilatura logs at ERROR whenever it's handed input it can't parse —
# "empty HTML tree", "parsed tree length: 1, wrong data type...", and similar.
# We already fall back to BeautifulSoup on parse failure, so none of these
# are actionable, but Sentry's logging integration captures every ERROR as a
# production event. Silence the whole trafilatura namespace below CRITICAL.
logging.getLogger("trafilatura").setLevel(logging.CRITICAL)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; VandalizerBot/1.0; +https://vandalizer.uidaho.edu)"
)

# Browser-like headers. Many .gov/.edu sites sit behind a CDN/WAF (Akamai,
# Cloudfront) that stalls or resets connections from clients that don't send a
# full browser header set — the request hangs until our read timeout fires and
# the source is recorded as an error. Sending Accept/Accept-Language alongside
# the UA clears the most common of these heuristics.
_DEFAULT_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Cap on the raw PDF payload we'll pull from a URL before extracting text.
_MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB


@dataclass
class WebFetchResult:
    url: str
    title: str
    text: str
    raw_html: Optional[str]
    used_browser: bool
    status_code: Optional[int]


def _extract_title(html: str, fallback_url: str) -> str:
    try:
        meta = trafilatura.extract_metadata(html)
        if meta and meta.title:
            return meta.title.strip()[:300]
    except Exception:
        pass
    try:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            return soup.title.string.strip()[:300]
    except Exception:
        pass
    return urlparse(fallback_url).netloc


def _extract_main_text(html: str) -> str:
    text = trafilatura.extract(
        html,
        include_links=False,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    if text:
        return _normalize_whitespace(text)
    # Trafilatura returned nothing — fall back to a permissive BeautifulSoup
    # strip so we always return *something* rather than silently dropping the
    # page (matches the older behavior of workflow_engine._extract_text_from_html).
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()
    return _normalize_whitespace(soup.get_text(separator="\n"))


def _looks_like_pdf(url: str, content_type: str) -> bool:
    """True when a response is a PDF, by content-type or URL extension."""
    if "application/pdf" in (content_type or "").lower():
        return True
    path = urlparse(url).path.lower()
    return path.endswith(".pdf")


def _extract_pdf_response(content: bytes, url: str) -> tuple[str, str]:
    """Extract text + a title from PDF bytes fetched over HTTP.

    Uses PyMuPDF (no OCR) to stay fast and dependency-light in the fetch path;
    image-only PDFs will yield little text, which the caller treats as an empty
    result. Title prefers the PDF's metadata, falling back to the URL filename.
    """
    if not content:
        return "", urlparse(url).path.rsplit("/", 1)[-1] or urlparse(url).netloc
    if len(content) > _MAX_PDF_BYTES:
        logger.warning(
            "PDF at %s is %d bytes (> %d cap) — skipping extraction",
            url, len(content), _MAX_PDF_BYTES,
        )
        return "", urlparse(url).path.rsplit("/", 1)[-1] or urlparse(url).netloc

    import os
    import tempfile

    from app.services.document_readers import extract_text_from_pdf

    filename = urlparse(url).path.rsplit("/", 1)[-1] or urlparse(url).netloc
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        text = extract_text_from_pdf(tmp_path)
        title = _pdf_title(tmp_path) or filename
        return _normalize_whitespace(text or ""), title
    except Exception as e:
        logger.warning("Failed to extract PDF from %s: %s", url, e)
        return "", filename
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _pdf_title(pdf_path: str) -> Optional[str]:
    """Best-effort title from PDF metadata; None if unavailable."""
    try:
        import pymupdf

        with pymupdf.open(pdf_path) as doc:
            title = (doc.metadata or {}).get("title") or ""
        title = title.strip()
        return title[:300] or None
    except Exception:
        return None


def _normalize_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def _render_with_browser(url: str, timeout_seconds: int) -> Optional[str]:
    """Return the post-JS HTML of *url*, or None if Playwright is unavailable."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed; skipping browser fallback for %s", url)
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(user_agent=_USER_AGENT)
                page = await context.new_page()
                # ``networkidle`` waits for the page to go quiet, which is what
                # SPAs need to fetch their content.  ``domcontentloaded`` is
                # too early.
                await page.goto(url, wait_until="networkidle", timeout=timeout_seconds * 1000)
                return await page.content()
            finally:
                await browser.close()
    except Exception as e:
        # Common cases: chromium binary not installed, navigation timeout,
        # site blocked the bot.  Caller falls back to the static result.
        logger.warning("Playwright render failed for %s: %s", url, e)
        return None


async def fetch_url(
    url: str,
    *,
    settings: Optional[Settings] = None,
    allow_browser: Optional[bool] = None,
) -> WebFetchResult:
    """Fetch *url* and return cleaned main-content text + raw HTML.

    Raises ``ValueError`` if the URL fails SSRF validation.  HTTP and
    network errors propagate as ``httpx`` exceptions so callers can
    surface them to the user.
    """
    settings = settings or Settings()
    if allow_browser is None:
        allow_browser = settings.web_fetcher_browser_enabled

    validate_outbound_url(url)

    raw_html: Optional[str] = None
    status_code: Optional[int] = None
    used_browser = False

    async with httpx.AsyncClient(
        timeout=settings.web_fetcher_timeout_seconds,
        follow_redirects=True,
        headers=_DEFAULT_HEADERS,
    ) as client:
        resp = await client.get(url)
        status_code = resp.status_code
        resp.raise_for_status()

        # PDF links (common for KB URL sources — agency forms, terms documents)
        # must be parsed as PDFs, not decoded as HTML. trafilatura/BeautifulSoup
        # on PDF bytes yields either nothing or raw binary, so without this a
        # direct .pdf URL ingests garbage or fails outright.
        if _looks_like_pdf(url, resp.headers.get("content-type", "")):
            pdf_text, pdf_title = _extract_pdf_response(resp.content, url)
            return WebFetchResult(
                url=url,
                title=pdf_title,
                text=pdf_text[: settings.web_fetcher_max_chars],
                raw_html=None,  # no HTML — nothing to crawl from a PDF
                used_browser=False,
                status_code=status_code,
            )

        raw_html = resp.text[: settings.web_fetcher_max_chars]

    text = _extract_main_text(raw_html)
    title = _extract_title(raw_html, url)

    if allow_browser and len(text) < settings.web_fetcher_min_chars:
        logger.info(
            "Static fetch yielded %d chars for %s; trying browser fallback",
            len(text), url,
        )
        rendered = await _render_with_browser(url, settings.web_fetcher_timeout_seconds)
        if rendered:
            rendered = rendered[: settings.web_fetcher_max_chars]
            rendered_text = _extract_main_text(rendered)
            if len(rendered_text) > len(text):
                raw_html = rendered
                text = rendered_text
                # Re-extract title from the rendered DOM; SPAs often set
                # <title> via JS after mount.
                title = _extract_title(rendered, url)
                used_browser = True

    return WebFetchResult(
        url=url,
        title=title,
        text=text[: settings.web_fetcher_max_chars],
        raw_html=raw_html,
        used_browser=used_browser,
        status_code=status_code,
    )


def fetch_url_sync(
    url: str,
    *,
    settings: Optional[Settings] = None,
    allow_browser: Optional[bool] = None,
) -> WebFetchResult:
    """Sync wrapper around :func:`fetch_url` for the Celery / workflow paths.

    Safe to call from threads with no running event loop (Celery workers).
    """
    return asyncio.run(fetch_url(url, settings=settings, allow_browser=allow_browser))
