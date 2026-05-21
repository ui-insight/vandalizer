"""Tests for app.services.web_fetcher.

Covers the static-fetch happy path, the JS-render fallback trigger, SSRF
rejection, and graceful degradation when Playwright is missing.  No network
or real browser is required — httpx and the Playwright import path are
mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import Settings
from app.services.web_fetcher import (
    WebFetchResult,
    fetch_url,
    fetch_url_sync,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STATIC_PAGE_HTML = """<!DOCTYPE html>
<html><head><title>Policy 70.02 - Travel</title></head>
<body>
<main>
<article>
<h1>Travel Policy</h1>
<p>It is University policy to reimburse employees for expenses incurred
while traveling on official business. This includes lodging, transportation,
and meal per-diem amounts subject to applicable IRS and state rates.</p>
<p>Receipts are required for all expenses over $25. Travel advances must be
reconciled within 30 days of return from travel.</p>
<p>Reimbursement requests must be submitted using the official travel form
and approved by the department administrator before submission to Travel
Services.</p>
</article>
</main>
</body></html>"""

# A Next.js-style SSR shell: lots of head/script content, almost no body text
# before JS runs.  Trafilatura will extract very little from this.
SPA_SHELL_HTML = """<!DOCTYPE html>
<html><head>
<title>APM 70.02 - Travel | University of Idaho</title>
<meta name="description" content="Travel policy">
<link rel="stylesheet" href="/_next/static/css/a.css">
<script src="/_next/static/chunks/main.js"></script>
</head>
<body>
<div id="__next"><div class="loading">Loading...</div></div>
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{}}}</script>
</body></html>"""

# What Playwright would return after rendering the SPA — body now has content.
SPA_RENDERED_HTML = """<!DOCTYPE html>
<html><head><title>APM 70.02 - Travel | University of Idaho</title></head>
<body>
<div id="__next">
<main>
<h1>APM 70.02 - Travel</h1>
<p>This policy outlines allowable travel expenses for University employees.
Lodging at the government per-diem rate is reimbursable. Personal vehicle
mileage is reimbursed at the current IRS rate. Meals while in travel status
are reimbursed at the daily per-diem rate set by the GSA.</p>
<p>Items not reimbursable include personal entertainment, sightseeing, and
expenses for accompanying family members. Original receipts are required
for any single expense exceeding twenty-five dollars.</p>
</main>
</div>
</body></html>"""


def _mock_async_client(text: str, status: int = 200):
    """Return a MagicMock that mimics ``httpx.AsyncClient(...)`` as a context manager."""
    resp = MagicMock()
    resp.text = text
    resp.status_code = status
    resp.raise_for_status = MagicMock()

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ---------------------------------------------------------------------------
# Happy path: trafilatura extracts the body
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_static_html_extracts_main_content():
    settings = Settings(web_fetcher_browser_enabled=False)

    with patch("app.services.web_fetcher.httpx.AsyncClient",
               return_value=_mock_async_client(STATIC_PAGE_HTML)), \
         patch("app.services.web_fetcher.validate_outbound_url",
               return_value="https://example.com/policy"):
        result = await fetch_url("https://example.com/policy", settings=settings)

    assert result.used_browser is False
    assert "reimburse" in result.text.lower()
    assert "receipts" in result.text.lower()
    # Trafilatura strips the <title> from the body
    assert "Travel Policy" in result.text or "travel policy" in result.text.lower()
    # Title comes from trafilatura's metadata extractor — it may prefer the
    # H1 over <title>, both are valid.
    assert "Travel" in result.title
    assert result.status_code == 200


# ---------------------------------------------------------------------------
# JS fallback: trafilatura returns sparse text → Playwright takes over
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spa_shell_triggers_browser_fallback():
    settings = Settings(web_fetcher_browser_enabled=True, web_fetcher_min_chars=500)

    async def fake_render(url, timeout):
        return SPA_RENDERED_HTML

    with patch("app.services.web_fetcher.httpx.AsyncClient",
               return_value=_mock_async_client(SPA_SHELL_HTML)), \
         patch("app.services.web_fetcher.validate_outbound_url",
               return_value="https://www.uidaho.edu/policies/apm/70/02"), \
         patch("app.services.web_fetcher._render_with_browser",
               side_effect=fake_render) as mock_render:
        result = await fetch_url(
            "https://www.uidaho.edu/policies/apm/70/02", settings=settings,
        )

    assert mock_render.called, "Browser fallback should fire for sparse pages"
    assert result.used_browser is True
    assert "per-diem" in result.text.lower()
    assert "entertainment" in result.text.lower()


# ---------------------------------------------------------------------------
# Browser fallback disabled: only static text returned, even if sparse
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_browser_disabled_returns_static_only():
    settings = Settings(web_fetcher_browser_enabled=False, web_fetcher_min_chars=500)

    with patch("app.services.web_fetcher.httpx.AsyncClient",
               return_value=_mock_async_client(SPA_SHELL_HTML)), \
         patch("app.services.web_fetcher.validate_outbound_url",
               return_value="https://example.com"), \
         patch("app.services.web_fetcher._render_with_browser") as mock_render:
        result = await fetch_url("https://example.com", settings=settings)

    assert mock_render.called is False
    assert result.used_browser is False


# ---------------------------------------------------------------------------
# Playwright missing: graceful degradation to static result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_playwright_unavailable_returns_static():
    settings = Settings(web_fetcher_browser_enabled=True, web_fetcher_min_chars=500)

    async def fake_render(url, timeout):
        # Simulates _render_with_browser's own ImportError handling.
        return None

    with patch("app.services.web_fetcher.httpx.AsyncClient",
               return_value=_mock_async_client(SPA_SHELL_HTML)), \
         patch("app.services.web_fetcher.validate_outbound_url",
               return_value="https://example.com"), \
         patch("app.services.web_fetcher._render_with_browser",
               side_effect=fake_render):
        result = await fetch_url("https://example.com", settings=settings)

    assert result.used_browser is False  # fell back to static result


# ---------------------------------------------------------------------------
# SSRF: blocked URLs raise before any fetch happens
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_blocked_url_raises_value_error():
    settings = Settings()
    with patch("app.services.web_fetcher.validate_outbound_url",
               side_effect=ValueError("Blocked private IP")):
        with pytest.raises(ValueError, match="Blocked"):
            await fetch_url("http://169.254.169.254/", settings=settings)


# ---------------------------------------------------------------------------
# HTTP errors propagate so callers can show them
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_http_error_propagates():
    settings = Settings()
    resp = MagicMock()
    resp.text = ""
    resp.status_code = 404
    resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
        "404", request=MagicMock(), response=resp,
    ))
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.web_fetcher.httpx.AsyncClient", return_value=client), \
         patch("app.services.web_fetcher.validate_outbound_url",
               return_value="https://example.com/missing"):
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_url("https://example.com/missing", settings=settings)


# ---------------------------------------------------------------------------
# Sync wrapper threads through to the async path
# ---------------------------------------------------------------------------

def test_sync_wrapper_runs_async_path():
    settings = Settings(web_fetcher_browser_enabled=False)

    with patch("app.services.web_fetcher.httpx.AsyncClient",
               return_value=_mock_async_client(STATIC_PAGE_HTML)), \
         patch("app.services.web_fetcher.validate_outbound_url",
               return_value="https://example.com"):
        result = fetch_url_sync("https://example.com", settings=settings)

    assert isinstance(result, WebFetchResult)
    assert "reimburse" in result.text.lower()
