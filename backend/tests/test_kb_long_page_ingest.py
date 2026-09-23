"""A long web page is indexed in full, not cut at the prompt-sized limit.

The reported case: the Federal Register's "Guidance for Federal Financial
Assistance" (the 2 CFR 200 rewrite) extracts to ~1.09 M characters. The
fetcher's 500 KB cap kept 46% of it and four whole subparts never reached the
index, behind a warning that told a research administrator the second half of
a regulation was unavailable — not something a user can act on.

The cap itself was not wrong, only shared: it protects callers that put fetched
text into a model prompt. KB ingestion chunks and embeds instead, so it asks
for its own, much larger limit.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import knowledge_service
from app.services.web_fetcher import WebFetchResult

# Comfortably past the 500 KB prompt cap, nowhere near the 5 M KB cap.
LONG_TEXT = "Subpart B—Requirements for Recipients. " * 30_000


def _source(**overrides):
    src = SimpleNamespace(
        uuid="src-1", knowledge_base_uuid="kb-1", source_type="url",
        url="https://www.federalregister.gov/documents/2024/04/22/2024-07496/x",
        url_title="Guidance for Federal Financial Assistance", custom_name=None,
        content="", status="pending", error_message=None, chunk_count=0,
        truncated=False, warnings=[], processed_at=None, last_ingested_at=None,
        last_retrieved_at=None, content_retrieved_at=None, content_hash=None,
        last_refresh_attempted_at=None, last_refresh_outcome=None,
        last_refresh_error=None, last_collapsed_hash=None,
    )
    for k, v in overrides.items():
        setattr(src, k, v)
    src.save = AsyncMock()
    return src


def _result(text: str, truncated: bool = False) -> WebFetchResult:
    return WebFetchResult(
        url="https://www.federalregister.gov/documents/2024/04/22/2024-07496/x",
        title="Guidance for Federal Financial Assistance", text=text,
        raw_html="<html/>", used_browser=False, status_code=200,
        truncated=truncated,
    )


class TestKbAsksForTheWholePage:
    @pytest.mark.asyncio
    async def test_refresh_requests_the_kb_limit_not_the_prompt_limit(self):
        src = _source(content="old", status="ready", chunk_count=3)
        dm = MagicMock()
        dm.add_to_kb.return_value = 1_360
        fetch = AsyncMock(return_value=_result(LONG_TEXT))

        with patch("app.services.web_fetcher.fetch_url", fetch), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

        assert reason is None
        assert fetch.await_args.kwargs["max_chars"] == knowledge_service._kb_text_cap()
        assert fetch.await_args.kwargs["max_chars"] > 500_000

    @pytest.mark.asyncio
    async def test_the_whole_page_is_what_gets_embedded(self):
        src = _source(content="old", status="ready", chunk_count=3)
        dm = MagicMock()
        dm.add_to_kb.return_value = 1_360

        with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(LONG_TEXT))), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

        # The text handed to the chunker is the page, entire.
        embedded = dm.add_to_kb.call_args[0][3]
        assert len(embedded) == len(LONG_TEXT)

    @pytest.mark.asyncio
    async def test_a_page_within_the_kb_limit_is_not_flagged_partial(self):
        """The warning is what the ticket is about: it must stop appearing on
        an ordinary regulation page."""
        src = _source(content="old", status="ready", chunk_count=3)
        dm = MagicMock()
        dm.add_to_kb.return_value = 1_360

        with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(LONG_TEXT))), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

        assert src.truncated is False
        assert src.status == "ready"

    @pytest.mark.asyncio
    async def test_a_page_past_even_the_kb_limit_still_warns(self):
        """Kept as the genuine extreme case, not the everyday one."""
        src = _source(content="old", status="ready", chunk_count=3)
        dm = MagicMock()
        dm.add_to_kb.return_value = 6_000

        with patch("app.services.web_fetcher.fetch_url",
                   AsyncMock(return_value=_result(LONG_TEXT, truncated=True))), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

        assert src.truncated is True


class TestSnapshotMatchesWhatWasIndexed:
    @pytest.mark.asyncio
    async def test_the_stored_snapshot_is_the_indexed_text(self):
        """Storing a shorter copy would make the inspector's "extracted text"
        a different document from the one the answers came from, and would
        make the next refresh measure a shrink that never happened."""
        src = _source(content="old", status="ready", chunk_count=3)
        dm = MagicMock()
        dm.add_to_kb.return_value = 1_360

        with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(LONG_TEXT))), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

        assert len(src.content) == len(LONG_TEXT)

    @pytest.mark.asyncio
    async def test_the_snapshot_and_the_embedded_text_are_the_same_text(self):
        """The invariant, stated directly: whatever went to the chunker is
        what the source row carries. A capped snapshot silently makes the
        inspector's "extracted text" a different, shorter document than the
        one the answers were built from, and makes the next refresh measure
        the page against a length it never had."""
        src = _source(content="old", status="ready", chunk_count=3)
        dm = MagicMock()
        dm.add_to_kb.return_value = 1_360

        with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(LONG_TEXT))), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

        embedded = dm.add_to_kb.call_args[0][3]
        assert src.content == embedded
