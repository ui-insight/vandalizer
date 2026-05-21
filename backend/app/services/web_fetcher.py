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

_USER_AGENT = (
    "Mozilla/5.0 (compatible; VandalizerBot/1.0; +https://vandalizer.uidaho.edu)"
)


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
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        resp = await client.get(url)
        status_code = resp.status_code
        resp.raise_for_status()
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
