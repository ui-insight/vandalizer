"""A web-source refresh that never finishes is settled, not left "pending".

Support ticket: the FCOI and NSF knowledge bases showed "Reprocessing —
queued", then "Waiting for document text to finish extracting…", over a
weekend, with the KB stuck at "building" and chat disabled. v4.14.0's
per-source Refresh crashed before fetching (the naive/aware stamp compare,
fixed on main in defb8493), and nothing ever moved the source on: the
stale-refresh window only made it refreshable again, and the UI disabled
Refresh on a "pending" source.

Separately, every caller marks a source "pending" before queueing its
refresh, so ``refresh_url_source`` never saw "ready": a failed refresh of a
working source made it an error while its chunks still answered.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import kb_url_refresh as r
from app.services import knowledge_service
from app.services.web_fetcher import WebFetchResult

NOW = datetime.datetime.now(tz=datetime.timezone.utc)
# A page the catalog does not bundle, so refresh fetches it live (a bundled
# eCFR URL is served from its bundle; see test_bundled_sources.py).
URL = "https://grants.nih.gov/policy-and-compliance/fcoi"
TEXT = "§ 50.601 Purpose. This subpart promotes objectivity in research. " * 200


def _source(**overrides):
    src = SimpleNamespace(
        uuid="src-1", knowledge_base_uuid="kb-1", source_type="url", url=URL,
        url_title="42 CFR Part 50 Subpart F", custom_name=None, content=TEXT,
        # What the per-source Refresh, Reprocess, Refresh all and the
        # schedule all leave behind before the task runs.
        status="pending", error_message=None, chunk_count=208, truncated=False,
        warnings=[], processed_at=None, last_collapsed_hash=None, parent_source_uuid=None,
        content_hash=None, created_at=NOW - datetime.timedelta(days=30),
        refresh_queued_at=NOW, last_refresh_attempted_at=None,
        last_refresh_outcome=None, last_refresh_error=None,
    )
    for k, v in overrides.items():
        setattr(src, k, v)
    src.save = AsyncMock()
    return src


def _result(text: str = TEXT) -> WebFetchResult:
    return WebFetchResult(
        url=URL, title="42 CFR Part 50 Subpart F", text=text,
        raw_html="<html/>", used_browser=False, status_code=200,
    )


class TestAFailedRefreshKeepsAWorkingSource:
    @pytest.mark.asyncio
    async def test_a_fetch_error_leaves_it_ready_on_its_previous_text(self):
        src, dm = _source(), MagicMock()
        with patch("app.services.web_fetcher.fetch_url", AsyncMock(side_effect=httpx.ConnectError("refused"))), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

        assert reason
        dm.replace_kb_source.assert_not_called()
        assert src.status == "ready"
        assert src.chunk_count == 208
        assert src.error_message.startswith("Refresh failed — previous content kept")

    @pytest.mark.asyncio
    async def test_an_index_write_failure_leaves_it_ready_too(self):
        src, dm = _source(), MagicMock()
        dm.replace_kb_source.side_effect = RuntimeError("chroma down")
        with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(TEXT + " amended"))), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))
        assert src.status == "ready"
        assert "previous content kept" in src.error_message

    @pytest.mark.asyncio
    async def test_an_unchanged_page_is_not_re_embedded(self):
        from app.utils import kb_source_currency as currency

        src, dm = _source(content_hash=currency.content_fingerprint(TEXT)), MagicMock()
        with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result())), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))
        dm.replace_kb_source.assert_not_called()
        assert src.last_refresh_outcome == "unchanged"
        assert src.status == "ready"

    @pytest.mark.asyncio
    async def test_a_source_with_nothing_indexed_still_errors(self):
        src = _source(chunk_count=0, content=None)
        with patch("app.services.web_fetcher.fetch_url", AsyncMock(side_effect=httpx.ConnectError("refused"))), \
             patch.object(knowledge_service, "_get_dm", return_value=MagicMock()):
            await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))
        assert src.status == "error"


def _find(items):
    q = MagicMock()
    q.to_list = AsyncMock(return_value=items)
    return q


class TestStalledSourcesAreRecovered:
    def test_stalled_only_past_the_window(self):
        old = NOW - r.STALE_IN_FLIGHT - datetime.timedelta(minutes=1)
        assert r.is_stalled(_source(refresh_queued_at=old, created_at=old), NOW)
        assert not r.is_stalled(_source(refresh_queued_at=NOW), NOW)
        assert not r.is_stalled(_source(status="ready", refresh_queued_at=old, created_at=old), NOW)

    @pytest.mark.asyncio
    async def test_the_sweep_settles_dead_refreshes_and_unsticks_the_kb(self):
        old = NOW - datetime.timedelta(days=2)
        refreshed = _source(uuid="fcoi", refresh_queued_at=old, created_at=old)
        never_added = _source(uuid="new", knowledge_base_uuid="kb-2", chunk_count=0,
                              refresh_queued_at=None, created_at=old)
        running = _source(uuid="live", refresh_queued_at=NOW)
        kb = MagicMock(uuid="kb-1")
        find = MagicMock(return_value=_find([refreshed, never_added, running]))

        with patch.object(r.KnowledgeBaseSource, "find", find), \
             patch.object(r.KnowledgeBase, "find_one", AsyncMock(return_value=kb)), \
             patch.object(knowledge_service, "recalculate_stats", AsyncMock()) as recalc:
            out = await r.recover_stalled_sources(NOW)

        # Only web sources: a document source can wait on a long extraction.
        assert find.call_args.args[0]["source_type"] == "url"
        assert out == {"sources": 2, "knowledge_bases": 2}
        assert refreshed.status == "ready"
        assert refreshed.error_message == r.STALLED_REFRESH_MESSAGE
        assert refreshed.last_refresh_outcome == "retrieval_failed"
        assert never_added.status == "error"
        assert running.status == "pending"
        running.save.assert_not_awaited()
        assert recalc.await_count == 2

    @pytest.mark.asyncio
    async def test_the_hourly_beat_runs_the_sweep_even_with_auto_refresh_off(self):
        from app.tasks import kb_validation_tasks as t

        with patch("app.database.init_db", AsyncMock()), \
             patch.object(r, "recover_stalled_sources", AsyncMock(return_value={"sources": 1, "knowledge_bases": 1})) as sweep, \
             patch.object(r, "refresh_due_sources", AsyncMock(return_value={"knowledge_bases": 0, "queued": 0})):
            out = await t._refresh_due_url_sources_async()
        sweep.assert_awaited_once()
        assert out["recovered"] == 1


class TestChatKeepsAnswering:
    @pytest.mark.asyncio
    async def test_a_refreshing_source_still_counts_its_chunks(self):
        kb = MagicMock(save=AsyncMock())
        sources = [SimpleNamespace(status="pending", chunk_count=208)]
        with patch.object(knowledge_service, "get_kb_sources", AsyncMock(return_value=sources)):
            await knowledge_service.recalculate_stats(kb)
        assert kb.total_chunks == 208
        assert kb.status == "building"

    @pytest.mark.asyncio
    async def test_chat_is_not_told_a_refreshing_source_is_unsearchable(self):
        sources = [
            SimpleNamespace(uuid="a", custom_name="FCOI", source_type="url", url=URL, url_title="",
                            document_uuid=None, status="pending", chunk_count=208),
            SimpleNamespace(uuid="b", custom_name="New page", source_type="url", url=URL, url_title="",
                            document_uuid=None, status="pending", chunk_count=0),
        ]
        with patch.object(knowledge_service, "get_kb_sources", AsyncMock(return_value=sources)), \
             patch.object(knowledge_service, "resolve_document_titles", AsyncMock(return_value={})):
            manifest = await knowledge_service.get_kb_manifest("kb-1")
        assert [m["status"] for m in manifest] == ["ready", "pending"]
