"""Unit tests for in-place refresh of KB URL sources.

Support ticket: a catalog KB kept serving Dec-2018 APM policy text months
after the pages were revised. Re-adding the URLs was a silent dedupe no-op
(the UI still said "Added 2 URLs") and /reingest re-embeds the stored
snapshot without fetching, so nothing in the product could pick up the new
page. These cover the new refresh path and the honest add_urls partition.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import knowledge_service
from app.services.web_fetcher import WebFetchResult


def _source(**overrides):
    src = SimpleNamespace(
        uuid="src-1",
        knowledge_base_uuid="kb-1",
        source_type="url",
        url="https://www.uidaho.edu/policies/apm/45/14",
        url_title="APM 45.14 - Sponsored Projects Changes Requiring Prior Approval | UI",
        custom_name=None,
        content="Last updated: December 1, 2018\nA. Overview. old text",
        status="ready",
        error_message=None,
        chunk_count=3,
        truncated=False,
        processed_at=None,
    )
    for k, v in overrides.items():
        setattr(src, k, v)
    src.save = AsyncMock()
    return src


def _result(text: str, title: str = "APM 45.14 - Changes Requiring Prior Approval | UI") -> WebFetchResult:
    return WebFetchResult(
        url="https://www.uidaho.edu/policies/apm/45/14", title=title, text=text,
        raw_html="<html/>", used_browser=False, status_code=200,
    )


def _dm():
    dm = MagicMock()
    dm.add_to_kb.return_value = 7
    return dm


@pytest.mark.asyncio
async def test_refresh_replaces_text_title_and_chunks_on_good_fetch():
    src = _source()
    dm = _dm()
    new_text = "Last Updated: July 13, 2026\nA. Purpose. new text"

    with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(new_text))), \
         patch.object(knowledge_service, "_get_dm", return_value=dm):
        reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

    assert reason is None
    # Old chunks are dropped before the new ones land, under the same source id.
    dm.delete_kb_source.assert_called_once_with("kb-1", "src-1")
    dm.add_to_kb.assert_called_once()
    assert dm.add_to_kb.call_args.args[:3] == ("kb-1", "src-1", "APM 45.14 - Changes Requiring Prior Approval | UI")
    assert src.content == new_text
    assert src.url_title == "APM 45.14 - Changes Requiring Prior Approval | UI"
    assert src.chunk_count == 7
    assert src.status == "ready"
    assert src.error_message is None
    assert src.processed_at is not None


@pytest.mark.asyncio
async def test_refresh_keeps_custom_name_as_chunk_label():
    src = _source(custom_name="Prior approvals policy")
    dm = _dm()
    fresh = "Last Updated: July 13, 2026\nA. Purpose. Prior approval is required for changes in scope."
    with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(fresh))), \
         patch.object(knowledge_service, "_get_dm", return_value=dm):
        await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))
    assert dm.add_to_kb.call_args.args[2] == "Prior approvals policy"


@pytest.mark.asyncio
async def test_refresh_keeps_previous_content_when_fetch_errors():
    """A page that's down for the afternoon must not blank out a working source."""
    src = _source()
    dm = _dm()
    boom = httpx.ConnectError("connection refused")

    with patch("app.services.web_fetcher.fetch_url", AsyncMock(side_effect=boom)), \
         patch.object(knowledge_service, "_get_dm", return_value=dm):
        reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

    assert reason
    dm.delete_kb_source.assert_not_called()
    dm.add_to_kb.assert_not_called()
    assert src.content.startswith("Last updated: December 1, 2018")
    assert src.chunk_count == 3
    assert src.status == "ready"  # still serves the old text
    assert src.error_message.startswith("Refresh failed — previous content kept:")


@pytest.mark.asyncio
async def test_refresh_keeps_previous_content_when_page_is_bot_challenge():
    src = _source()
    dm = _dm()
    challenge = "Request Access\nDue to aggressive automated scraping ... verify you are a human"

    with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(challenge))), \
         patch("app.utils.bot_challenge.looks_like_bot_challenge", return_value=True), \
         patch.object(knowledge_service, "_get_dm", return_value=dm):
        reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

    assert "bot protection" in reason
    dm.delete_kb_source.assert_not_called()
    assert src.status == "ready"
    assert src.content.startswith("Last updated: December 1, 2018")


@pytest.mark.asyncio
async def test_refresh_of_errored_source_stays_error_on_failed_fetch():
    """No previous good text to keep — the failure is the source's state."""
    src = _source(status="error", content=None, chunk_count=0)
    dm = _dm()
    with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result("   "))), \
         patch.object(knowledge_service, "_get_dm", return_value=dm):
        reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))
    assert reason
    assert src.status == "error"
    assert not src.error_message.startswith("Refresh failed — previous content kept")


@pytest.mark.asyncio
async def test_refresh_rejects_document_sources():
    src = _source(source_type="document", url=None)
    with patch("app.services.web_fetcher.fetch_url", AsyncMock()) as fetch:
        reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))
    assert reason == "Only URL sources can be refreshed"
    fetch.assert_not_awaited()
    src.save.assert_not_awaited()


# ---------------------------------------------------------------------------
# partition_new_urls — what add_urls will actually fetch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partition_new_urls_splits_present_from_new_and_normalizes():
    present = {"https://www.uidaho.edu/policies/apm/45/13"}

    async def find_one(*conds):
        # Beanie comparison conditions are opaque here; recover the URL from
        # the second condition's rendered form.
        rendered = str(conds[1])
        return object() if any(u in rendered for u in present) else None

    cls = MagicMock()
    cls.find_one = AsyncMock(side_effect=find_one)
    cls.knowledge_base_uuid = MagicMock()
    cls.url = MagicMock()
    # Make `KnowledgeBaseSource.url == url` render the url so find_one can see it.
    cls.url.__eq__ = lambda self, other: f"url=={other}"

    with patch.object(knowledge_service, "KnowledgeBaseSource", cls):
        new, skipped = await knowledge_service.partition_new_urls(
            MagicMock(uuid="kb-1"),
            [
                " www.uidaho.edu/policies/apm/45/13 ",   # normalized → present
                "https://www.uidaho.edu/policies/apm/45/14",  # new
                "https://www.uidaho.edu/policies/apm/45/14",  # duplicate in request
                "",
            ],
        )

    assert new == ["https://www.uidaho.edu/policies/apm/45/14"]
    assert skipped == ["https://www.uidaho.edu/policies/apm/45/13"]


# ---------------------------------------------------------------------------
# A refresh that comes back with a fraction of the content it is replacing
# ---------------------------------------------------------------------------
# Support ticket: refreshing the Subpart E source of a 2 CFR 200 KB fetched
# eCFR's JavaScript shell instead of the regulation. The shell carried no
# phrase the wording-based gates knew, so it passed them, and the refresh
# replaced 208 chunks with 1 — marked "Refreshed" with a green check. Chat
# then answered §200.414 questions from general knowledge, wrongly.

_SUBPART_E = "\n".join(
    f"§ 200.{400 + i} Cost principle {i}. (a) Costs must be necessary and reasonable "
    "for the performance of the Federal award and be allocable thereto under these "
    "principles. (b) Conform to any limitations or exclusions set forth in these "
    "principles or in the Federal award as to types or amount of cost items."
    for i in range(300)
)

# eCFR's shell: the .gov banner and navigation, and none of the regulation.
# Deliberately free of the session-dialog and JS-required phrases the
# boilerplate gate needs, so it reaches the gate under test.
_ECFR_SHELL = (
    "eCFR :: 2 CFR Part 200 Subpart E -- Cost Principles\n"
    "An official website of the United States government. Here's how you know.\n"
    "Title 2 Subtitle A Chapter II Part 200 Subpart E\n"
    "Enhanced Content - Table of Contents. Browse. Search. Timeline. Details. "
    "Print/PDF. Display Options. Go to CFR Reference. Recent Changes. Comparison."
)


@pytest.mark.asyncio
async def test_refresh_refuses_a_page_that_is_a_fraction_of_the_indexed_text():
    src = _source(content=_SUBPART_E, chunk_count=208, content_hash="abc")
    dm = _dm()
    with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(_ECFR_SHELL))), \
         patch.object(knowledge_service, "_get_dm", return_value=dm):
        reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

    assert reason and "looks like the site's shell" in reason
    # The index was never touched: the 208 chunks are still what chat searches.
    dm.delete_kb_source.assert_not_called()
    dm.add_to_kb.assert_not_called()
    assert src.content == _SUBPART_E
    assert src.chunk_count == 208
    # And it does not wear a green check.
    assert src.status == "ready"
    assert src.error_message.startswith("Refresh failed — previous content kept:")
    assert src.last_refresh_outcome == "retrieval_failed"
    assert src.last_refresh_error == reason
    # The content was not retrieved, so the retrieval date must not move.
    assert getattr(src, "last_retrieved_at", None) is None


@pytest.mark.asyncio
async def test_refresh_accepts_a_genuine_revision_that_shrinks_the_page():
    """A page that lost a third of its text was edited, not broken."""
    revised = "\n".join(_SUBPART_E.splitlines()[:200])
    src = _source(content=_SUBPART_E, chunk_count=208, content_hash="abc")
    dm = _dm()
    with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(revised))), \
         patch.object(knowledge_service, "_get_dm", return_value=dm):
        reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

    assert reason is None
    dm.add_to_kb.assert_called_once()
    assert src.content == revised
    assert src.last_refresh_outcome == "refreshed"


@pytest.mark.asyncio
async def test_refresh_of_source_with_no_retained_text_has_nothing_to_compare():
    """An errored source has no baseline, so a short real page is simply ingested."""
    src = _source(status="error", content=None, chunk_count=0)
    dm = _dm()
    short_page = "A. Purpose. This policy sets the prior-approval thresholds for sponsored projects."
    with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(short_page))), \
         patch.object(knowledge_service, "_get_dm", return_value=dm):
        reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

    assert reason is None
    assert src.status == "ready"
    assert src.content == short_page


def test_collapse_gate_boundary():
    gate = knowledge_service._reject_collapsed_refresh
    previous = "x" * 1000
    assert gate(previous, "y" * 249) is not None
    assert gate(previous, "y" * 250) is None
    assert gate(None, "y") is None
    assert gate("", "y") is None
    assert gate("   ", "y") is None
    assert "1,000" in gate(previous, "y" * 10)
