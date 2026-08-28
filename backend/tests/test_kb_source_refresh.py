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
    with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result("fresh body"))), \
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
