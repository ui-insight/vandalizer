"""Unit tests for KB crawl link-seeding, including PDF sources.

Crawl-enabled URL sources follow links found on the fetched page. For HTML
that means <a href> anchors; for PDF URLs (ticket #1238) it means the
hyperlinks embedded in the PDF, subject to the same domain filter and
max-pages cap.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import knowledge_service
from app.services.web_fetcher import WebFetchResult


def _html_result(url: str, html: str, final_url: str | None = None) -> WebFetchResult:
    return WebFetchResult(
        url=url, title="t", text="body text", raw_html=html,
        used_browser=False, status_code=200, final_url=final_url,
    )


def _pdf_result(url: str, links: list[str] | None) -> WebFetchResult:
    return WebFetchResult(
        url=url, title="terms.pdf", text="pdf text", raw_html=None,
        used_browser=False, status_code=200, pdf_links=links,
    )


# ---------------------------------------------------------------------------
# _crawlable_links — one seeding path for HTML and PDF fetches
# ---------------------------------------------------------------------------


def test_crawlable_links_html_extracts_anchors():
    html = '<a href="/a">A</a> <a href="https://other.gov/b#frag">B</a>'
    links = knowledge_service._crawlable_links(
        _html_result("https://example.gov/page", html), "https://example.gov/page",
    )
    assert links == ["https://example.gov/a", "https://other.gov/b"]


def test_crawlable_links_pdf_normalizes_and_dedupes():
    fetched = _pdf_result("https://example.gov/doc.pdf", [
        "https://example.gov/terms/",
        "https://example.gov/terms#section-2",  # same page after normalization
        "https://other.gov/forms",
    ])
    links = knowledge_service._crawlable_links(fetched, "https://example.gov/doc.pdf")
    assert links == ["https://example.gov/terms", "https://other.gov/forms"]


def test_crawlable_links_pdf_without_links_is_empty():
    fetched = _pdf_result("https://example.gov/doc.pdf", None)
    assert knowledge_service._crawlable_links(fetched, "https://example.gov/doc.pdf") == []


# ---------------------------------------------------------------------------
# _crawl_from_source seeded by a PDF parent
# ---------------------------------------------------------------------------


def _make_parent(url: str):
    parent = SimpleNamespace(uuid="parent-1", url=url, crawled_urls=None)
    parent.save = AsyncMock()
    return parent


def _mock_source_cls():
    """Stand-in for KnowledgeBaseSource: records constructed children."""
    children = []

    def construct(**kwargs):
        child = SimpleNamespace(status="pending", **kwargs)
        child.insert = AsyncMock()
        children.append(child)
        return child

    cls = MagicMock(side_effect=construct)
    cls.find_one = AsyncMock(return_value=None)  # no duplicates in the KB
    cls.knowledge_base_uuid = MagicMock()
    cls.url = MagicMock()
    return cls, children


@pytest.mark.asyncio
async def test_pdf_parent_seeds_crawl_same_domain_only():
    parent = _make_parent("https://www.usda.gov/x/terms.pdf")
    fetched = _pdf_result(parent.url, [
        "https://www.usda.gov/ocfo/assistance",
        "https://www.usda.gov/policies",
        "https://www.grants.gov/learn",  # off-domain, not in allowed_domains
    ])
    cls, children = _mock_source_cls()

    with patch.object(knowledge_service, "KnowledgeBaseSource", cls), \
         patch.object(knowledge_service, "_ingest_url_source",
                      AsyncMock(return_value=None)) as mock_ingest:
        added = await knowledge_service._crawl_from_source(
            parent, MagicMock(uuid="kb-1"), max_pages=5,
            allowed_domains="", parent_fetched=fetched,
        )

    assert added == 2
    assert [c.url for c in children] == [
        "https://www.usda.gov/ocfo/assistance",
        "https://www.usda.gov/policies",
    ]
    assert all(c.parent_source_uuid == "parent-1" for c in children)
    assert mock_ingest.await_count == 2
    assert parent.crawled_urls == [
        "https://www.usda.gov/ocfo/assistance",
        "https://www.usda.gov/policies",
    ]


@pytest.mark.asyncio
async def test_pdf_parent_respects_allowed_domains_and_max_pages():
    parent = _make_parent("https://www.usda.gov/x/terms.pdf")
    fetched = _pdf_result(parent.url, [
        "https://www.usda.gov/a",
        "https://www.grants.gov/b",
        "https://www.usda.gov/c",
    ])
    cls, children = _mock_source_cls()

    with patch.object(knowledge_service, "KnowledgeBaseSource", cls), \
         patch.object(knowledge_service, "_ingest_url_source",
                      AsyncMock(return_value=None)):
        added = await knowledge_service._crawl_from_source(
            parent, MagicMock(uuid="kb-1"), max_pages=2,
            allowed_domains="www.usda.gov, www.grants.gov", parent_fetched=fetched,
        )

    # grants.gov is allowed via allowed_domains; max_pages=2 stops before /c.
    assert added == 2
    assert [c.url for c in children] == [
        "https://www.usda.gov/a",
        "https://www.grants.gov/b",
    ]


@pytest.mark.asyncio
async def test_explicit_allowed_domains_replace_parent_domain():
    """An allowed-domains entry defines the whole scope — it no longer
    silently unions with the parent's domain (the ticket's no-op case)."""
    parent = _make_parent("https://www.usda.gov/x/terms.pdf")
    fetched = _pdf_result(parent.url, [
        "https://www.usda.gov/a",
        "https://www.grants.gov/b",
    ])
    cls, children = _mock_source_cls()

    with patch.object(knowledge_service, "KnowledgeBaseSource", cls), \
         patch.object(knowledge_service, "_ingest_url_source",
                      AsyncMock(return_value=None)):
        added = await knowledge_service._crawl_from_source(
            parent, MagicMock(uuid="kb-1"), max_pages=5,
            allowed_domains="www.grants.gov", parent_fetched=fetched,
        )

    assert added == 1
    assert [c.url for c in children] == ["https://www.grants.gov/b"]


@pytest.mark.asyncio
async def test_path_qualified_allowed_domain_scopes_crawl_to_subdirectory():
    """A full URL with a path in Allowed domains restricts the crawl to that
    section of the site (support ticket: suu.edu/irb pulled in all of suu.edu)."""
    parent = _make_parent("https://www.suu.edu/irb/")
    parent_fetched = _html_result(parent.url, """
        <a href="/irb/apply">Apply</a>
        <a href="/irb/forms/consent">Consent</a>
        <a href="/irb-archive/2019">Archive</a>
        <a href="/admissions">Admissions</a>
        <a href="https://www.suu.edu/">Home</a>
    """)
    cls, children = _mock_source_cls()

    with patch.object(knowledge_service, "KnowledgeBaseSource", cls), \
         patch.object(knowledge_service, "_ingest_url_source",
                      AsyncMock(return_value=None)):
        added = await knowledge_service._crawl_from_source(
            parent, MagicMock(uuid="kb-1"), max_pages=10,
            allowed_domains="https://www.suu.edu/irb", parent_fetched=parent_fetched,
        )

    assert added == 2
    assert [c.url for c in children] == [
        "https://www.suu.edu/irb/apply",
        "https://www.suu.edu/irb/forms/consent",
    ]


@pytest.mark.asyncio
async def test_crawl_follows_links_found_on_child_pdfs():
    """BFS continues through a crawled child that is itself a PDF."""
    parent = _make_parent("https://example.gov/index")
    parent_fetched = _html_result(
        parent.url, '<a href="https://example.gov/guide.pdf">Guide</a>',
    )
    child_pdf = _pdf_result(
        "https://example.gov/guide.pdf", ["https://example.gov/appendix"],
    )
    cls, children = _mock_source_cls()

    # First child fetch returns the PDF (with a link); second returns None.
    with patch.object(knowledge_service, "KnowledgeBaseSource", cls), \
         patch.object(knowledge_service, "_ingest_url_source",
                      AsyncMock(side_effect=[child_pdf, None])):
        added = await knowledge_service._crawl_from_source(
            parent, MagicMock(uuid="kb-1"), max_pages=5,
            allowed_domains="", parent_fetched=parent_fetched,
        )

    assert added == 2
    assert [c.url for c in children] == [
        "https://example.gov/guide.pdf",
        "https://example.gov/appendix",
    ]


@pytest.mark.asyncio
async def test_redirect_landing_url_not_crawled_again():
    """A child fetched via redirect isn't crawled again under the URL it
    landed on — both spellings of the page sit in the queue before the first
    fetch reveals where it redirects to."""
    parent = _make_parent("https://example.gov/index")
    parent_fetched = _html_result(parent.url, """
        <a href="https://example.gov/guide">Guide</a>
        <a href="https://www.example.gov/guide#top">Guide (www)</a>
    """)
    # Fetching the bare-host spelling redirects to the www spelling.
    child = _html_result(
        "https://example.gov/guide", "<p>no links</p>",
        final_url="https://www.example.gov/guide",
    )
    cls, children = _mock_source_cls()

    with patch.object(knowledge_service, "KnowledgeBaseSource", cls), \
         patch.object(knowledge_service, "_ingest_url_source",
                      AsyncMock(return_value=child)) as mock_ingest:
        added = await knowledge_service._crawl_from_source(
            parent, MagicMock(uuid="kb-1"), max_pages=5,
            allowed_domains="example.gov, www.example.gov",
            parent_fetched=parent_fetched,
        )

    assert added == 1
    assert [c.url for c in children] == ["https://example.gov/guide"]
    assert mock_ingest.await_count == 1


@pytest.mark.asyncio
async def test_redirected_parent_stamps_landing_url():
    """Links back to the parent's landing URL (uidaho.edu → www.uidaho.edu)
    aren't crawled as new pages."""
    parent = _make_parent("https://example.gov")
    parent_fetched = _html_result(
        parent.url, """
        <a href="https://www.example.gov/#content">Skip to content</a>
        <a href="https://www.example.gov/a">A</a>
        """,
        final_url="https://www.example.gov/",
    )
    cls, children = _mock_source_cls()

    with patch.object(knowledge_service, "KnowledgeBaseSource", cls), \
         patch.object(knowledge_service, "_ingest_url_source",
                      AsyncMock(return_value=None)):
        added = await knowledge_service._crawl_from_source(
            parent, MagicMock(uuid="kb-1"), max_pages=5,
            allowed_domains="example.gov, www.example.gov",
            parent_fetched=parent_fetched,
        )

    assert added == 1
    assert [c.url for c in children] == ["https://www.example.gov/a"]


# ---------------------------------------------------------------------------
# Bot-challenge pages must not be ingested as KB source content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_url_source_errors_on_bot_challenge():
    source = SimpleNamespace(
        uuid="src-1", url="https://www.walmart.com/help", status="pending",
        error_message=None, content=None, url_title=None,
        chunk_count=0, processed_at=None,
    )
    source.save = AsyncMock()
    fetched = WebFetchResult(
        url=source.url, title="Robot or human?",
        text="Robot or human? Activate and hold the button to confirm that you're human.",
        raw_html="<html><body>Robot or human?</body></html>",
        used_browser=False, status_code=200,
    )

    with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=fetched)), \
         patch.object(knowledge_service, "_get_dm") as mock_get_dm:
        out = await knowledge_service._ingest_url_source(source, MagicMock(uuid="kb-1"))

    assert out is None
    assert source.status == "error"
    assert "bot protection" in source.error_message
    # The junk text must never reach ChromaDB.
    mock_get_dm.assert_not_called()
