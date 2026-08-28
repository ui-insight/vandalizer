"""Per-source refresh / ingestion provenance ("currency").

Support ticket: evaluators verifying that a KB's sources are current had to
compare every exported source against the live original by hand, because the
only freshness signal anywhere was one overloaded ``processed_at``. These pin
the distinct fields (last attempt / last retrieval / last ingestion / retained
content date / outcome / content hash), how they are stamped at ingest and
refresh, the legacy fallbacks, and that the KB export carries them.
Mocked models — no DB.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import knowledge_service
from app.services.web_fetcher import WebFetchResult
from app.utils import kb_source_currency as cur

UTC = datetime.timezone.utc
T_OLD = datetime.datetime(2026, 6, 24, 9, 0, tzinfo=UTC)
T_ATTEMPT = datetime.datetime(2026, 8, 27, 15, 30, tzinfo=UTC)
OLD_TEXT = "Last updated: December 1, 2018\nA. Overview. old text"
NEW_TEXT = "Last Updated: July 13, 2026\nA. Purpose. new text"


def _row(**overrides):
    row = dict(
        uuid="src-1", source_type="url", url="https://example.edu/p", status="ready",
        content=OLD_TEXT, truncated=False, chunk_count=3, processed_at=T_OLD,
    )
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# derive_source_currency — the read side
# ---------------------------------------------------------------------------

class TestDeriveSourceCurrency:
    def test_legacy_row_falls_back_to_processed_at_and_hashes_the_snapshot(self):
        """A row written before the fields existed still answers every
        question it can: dates from processed_at, a hash of the retained
        snapshot flagged as not recorded at ingest, status "ingested"."""
        out = cur.derive_source_currency(_row())
        assert out["status"] == cur.STATUS_INGESTED
        assert out["last_ingested_at"] == T_OLD.isoformat()
        assert out["last_retrieved_at"] == T_OLD.isoformat()
        assert out["content_retrieved_at"] == T_OLD.isoformat()
        assert out["last_refresh_attempted_at"] is None
        assert out["content_hash"] == cur.content_fingerprint(OLD_TEXT)
        assert out["content_hash_algorithm"] == "sha256"
        assert out["content_hash_recorded"] is False
        assert out["last_refresh_outcome"] is None

    def test_legacy_truncated_snapshot_gets_no_hash(self):
        """The stored snapshot of a truncated page is not the indexed text,
        so hashing it would identify the wrong thing."""
        out = cur.derive_source_currency(_row(truncated=True))
        assert out["content_hash"] is None
        assert out["content_hash_recorded"] is False

    def test_never_ingested(self):
        out = cur.derive_source_currency(_row(status="pending", processed_at=None, content=None))
        assert out["status"] == cur.STATUS_NEVER_INGESTED
        assert out["last_ingested_at"] is None
        assert out["content_hash"] is None

    def test_recorded_fields_win_over_processed_at(self):
        out = cur.derive_source_currency(_row(
            processed_at=T_ATTEMPT, last_ingested_at=T_ATTEMPT, last_retrieved_at=T_ATTEMPT,
            content_retrieved_at=T_OLD, content_hash="abc", last_refresh_attempted_at=T_ATTEMPT,
        ))
        assert out["content_retrieved_at"] == T_OLD.isoformat()
        assert out["last_ingested_at"] == T_ATTEMPT.isoformat()
        assert out["content_hash"] == "abc"
        assert out["content_hash_recorded"] is True

    @pytest.mark.parametrize("outcome, status, expected", [
        (cur.OUTCOME_REFRESHED, "ready", cur.STATUS_REFRESHED),
        (cur.OUTCOME_UNCHANGED, "ready", cur.STATUS_UNCHANGED),
        # Failed fetch on a working source: the previous good version is
        # still served — the ticket's "retained last good version".
        (cur.OUTCOME_RETRIEVAL_FAILED, "ready", cur.STATUS_RETAINED_PREVIOUS),
        # Failed fetch with nothing good to fall back on.
        (cur.OUTCOME_RETRIEVAL_FAILED, "error", cur.STATUS_RETRIEVAL_FAILED),
        (cur.OUTCOME_INGESTION_FAILED, "error", cur.STATUS_INGESTION_FAILED),
    ])
    def test_status_from_last_refresh_outcome(self, outcome, status, expected):
        out = cur.derive_source_currency(_row(
            status=status, last_refresh_outcome=outcome,
            last_refresh_attempted_at=T_ATTEMPT, last_refresh_error="boom" if "failed" in outcome else None,
        ))
        assert out["status"] == expected
        assert out["last_refresh_attempted_at"] == T_ATTEMPT.isoformat()
        assert out["last_refresh_outcome"] == outcome

    def test_retrieval_failed_with_no_prior_ingest_is_not_retained(self):
        out = cur.derive_source_currency(_row(
            status="ready", processed_at=None, last_refresh_outcome=cur.OUTCOME_RETRIEVAL_FAILED,
        ))
        assert out["status"] == cur.STATUS_RETRIEVAL_FAILED

    def test_works_on_a_beanie_style_object(self):
        src = SimpleNamespace(**_row(last_refresh_error="x"))
        out = cur.derive_source_currency(src)
        assert out["status"] == cur.STATUS_INGESTED
        assert out["last_refresh_error"] == "x"

    def test_tolerates_stand_in_values_without_raising(self):
        """A test double / corrupt row must not 500 the source list: every
        non-string, non-datetime value reads as absent."""
        out = cur.derive_source_currency(MagicMock())
        assert out["content_hash"] is None
        assert out["last_refresh_error"] is None
        assert out["last_refresh_outcome"] is None
        assert out["last_ingested_at"] is None
        assert out["status"] == cur.STATUS_NEVER_INGESTED


# ---------------------------------------------------------------------------
# ingestion_stamp / stamp_ingested — the write side
# ---------------------------------------------------------------------------

class TestIngestionStamp:
    def test_retrieval_stamps_every_date_and_the_hash(self):
        out = cur.ingestion_stamp(NEW_TEXT, now=T_ATTEMPT)
        assert out == {
            "content_hash": cur.content_fingerprint(NEW_TEXT),
            "last_ingested_at": T_ATTEMPT,
            "processed_at": T_ATTEMPT,
            "last_retrieved_at": T_ATTEMPT,
            "content_retrieved_at": T_ATTEMPT,
        }

    def test_reingest_moves_only_the_ingestion_dates(self):
        """/reingest re-embeds the stored snapshot: the text is no newer than
        it was, so the retrieval dates must not move to "now"."""
        out = cur.ingestion_stamp(OLD_TEXT, now=T_ATTEMPT, retrieved=False)
        assert "last_retrieved_at" not in out
        assert "content_retrieved_at" not in out
        assert out["last_ingested_at"] == T_ATTEMPT

    def test_reingest_backfills_a_retained_date_for_legacy_rows(self):
        out = cur.ingestion_stamp(OLD_TEXT, now=T_ATTEMPT, retrieved=False, retrieved_at=T_OLD)
        assert out["content_retrieved_at"] == T_OLD
        assert "last_retrieved_at" not in out

    def test_stamp_ingested_sets_attributes(self):
        src = SimpleNamespace()
        cur.stamp_ingested(src, NEW_TEXT, now=T_ATTEMPT)
        assert src.content_hash == cur.content_fingerprint(NEW_TEXT)
        assert src.processed_at == T_ATTEMPT
        assert src.content_retrieved_at == T_ATTEMPT

    def test_fingerprint_is_stable_and_content_sensitive(self):
        assert cur.content_fingerprint("a") == cur.content_fingerprint("a")
        assert cur.content_fingerprint("a") != cur.content_fingerprint("a ")
        assert len(cur.content_fingerprint("a")) == 64


# ---------------------------------------------------------------------------
# refresh_url_source records every attempt
# ---------------------------------------------------------------------------

def _source(**overrides):
    src = SimpleNamespace(
        uuid="src-1", knowledge_base_uuid="kb-1", source_type="url",
        url="https://example.edu/p", url_title="Old title", custom_name=None,
        content=OLD_TEXT, status="ready", error_message=None, chunk_count=3, truncated=False,
        processed_at=T_OLD, last_ingested_at=T_OLD, last_retrieved_at=T_OLD,
        content_retrieved_at=T_OLD, content_hash=cur.content_fingerprint(OLD_TEXT),
        last_refresh_attempted_at=None, last_refresh_outcome=None, last_refresh_error=None,
    )
    for k, v in overrides.items():
        setattr(src, k, v)
    src.save = AsyncMock()
    return src


def _result(text: str) -> WebFetchResult:
    return WebFetchResult(
        url="https://example.edu/p", title="New title", text=text,
        raw_html="<html/>", used_browser=False, status_code=200,
    )


def _dm(chunks=7):
    dm = MagicMock()
    dm.add_to_kb.return_value = chunks
    return dm


class TestRefreshCurrency:
    @pytest.mark.asyncio
    async def test_failed_fetch_records_the_attempt_and_keeps_the_retained_dates(self):
        src = _source()
        dm = _dm()
        with patch("app.services.web_fetcher.fetch_url", AsyncMock(side_effect=httpx.ConnectError("refused"))), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

        assert reason
        assert src.last_refresh_attempted_at is not None
        assert src.last_refresh_outcome == cur.OUTCOME_RETRIEVAL_FAILED
        assert src.last_refresh_error == reason
        # What is served is exactly what was there, dated as it was.
        assert src.content == OLD_TEXT
        assert src.content_retrieved_at == T_OLD
        assert src.last_ingested_at == T_OLD
        assert src.last_retrieved_at == T_OLD
        assert src.content_hash == cur.content_fingerprint(OLD_TEXT)
        assert cur.derive_source_currency(src)["status"] == cur.STATUS_RETAINED_PREVIOUS

    @pytest.mark.asyncio
    async def test_good_fetch_records_refreshed_with_the_new_hash(self):
        src = _source()
        dm = _dm()
        with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(NEW_TEXT))), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

        assert reason is None
        dm.add_to_kb.assert_called_once()
        assert src.last_refresh_outcome == cur.OUTCOME_REFRESHED
        assert src.last_refresh_error is None
        assert src.content_hash == cur.content_fingerprint(NEW_TEXT)
        assert src.last_refresh_attempted_at is not None
        assert src.last_retrieved_at > T_OLD
        assert src.content_retrieved_at == src.last_retrieved_at
        assert src.last_ingested_at == src.processed_at
        assert cur.derive_source_currency(src)["status"] == cur.STATUS_REFRESHED

    @pytest.mark.asyncio
    async def test_identical_text_is_unchanged_and_not_reembedded(self):
        """Same bytes as what is indexed: a currency check, not a rebuild.
        The retrieval date moves (the page was just read), the retained
        content date and hash do not, and an earlier failure is cleared."""
        src = _source(
            error_message="Refresh failed — previous content kept: 503",
            last_refresh_outcome=cur.OUTCOME_RETRIEVAL_FAILED, last_refresh_error="503",
        )
        dm = _dm()
        with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(OLD_TEXT))), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

        assert reason is None
        dm.delete_kb_source.assert_not_called()
        dm.add_to_kb.assert_not_called()
        assert src.last_refresh_outcome == cur.OUTCOME_UNCHANGED
        assert src.last_refresh_error is None
        assert src.error_message is None
        assert src.status == "ready"
        assert src.chunk_count == 3
        assert src.url_title == "New title"
        assert src.last_retrieved_at > T_OLD
        assert src.content_retrieved_at == T_OLD
        assert src.last_ingested_at == T_OLD
        assert cur.derive_source_currency(src)["status"] == cur.STATUS_UNCHANGED

    @pytest.mark.asyncio
    async def test_identical_text_on_an_errored_source_is_still_reembedded(self):
        """"Unchanged" only means anything when the index holds that text."""
        src = _source(status="error", chunk_count=0)
        dm = _dm()
        with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(OLD_TEXT))), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

        assert reason is None
        dm.add_to_kb.assert_called_once()
        assert src.last_refresh_outcome == cur.OUTCOME_REFRESHED
        assert src.status == "ready"

    @pytest.mark.asyncio
    async def test_legacy_source_without_a_hash_is_reembedded_and_gains_one(self):
        src = _source(content_hash=None, last_ingested_at=None, content_retrieved_at=None)
        dm = _dm()
        with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(OLD_TEXT))), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

        dm.add_to_kb.assert_called_once()
        assert src.content_hash == cur.content_fingerprint(OLD_TEXT)
        assert src.last_refresh_outcome == cur.OUTCOME_REFRESHED

    @pytest.mark.asyncio
    async def test_reindex_failure_records_ingestion_failed(self):
        src = _source()
        dm = _dm()
        dm.add_to_kb.side_effect = RuntimeError("chroma down")
        with patch("app.services.web_fetcher.fetch_url", AsyncMock(return_value=_result(NEW_TEXT))), \
             patch.object(knowledge_service, "_get_dm", return_value=dm):
            reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))

        assert "re-indexing" in reason
        assert src.status == "error"
        assert src.last_refresh_outcome == cur.OUTCOME_INGESTION_FAILED
        assert src.last_refresh_error == reason
        # Retrieval worked; what is retained is still the old text.
        assert src.last_retrieved_at > T_OLD
        assert src.content == OLD_TEXT
        assert src.content_retrieved_at == T_OLD
        assert src.content_hash == cur.content_fingerprint(OLD_TEXT)
        assert cur.derive_source_currency(src)["status"] == cur.STATUS_INGESTION_FAILED


# ---------------------------------------------------------------------------
# KB export carries it
# ---------------------------------------------------------------------------

class TestExportCurrency:
    @pytest.mark.asyncio
    async def test_export_includes_per_source_currency_and_status(self):
        src = SimpleNamespace(
            **_row(
                url_title="Policy", custom_name=None, document_uuid=None, source_reference="https://example.edu/p",
                crawl_enabled=False, max_crawl_pages=5, parent_source_uuid=None, crawled_urls=None,
                created_at=T_OLD, last_refresh_attempted_at=T_ATTEMPT,
                last_refresh_outcome=cur.OUTCOME_RETRIEVAL_FAILED, last_refresh_error="HTTP 503",
                content_hash="deadbeef", last_ingested_at=T_OLD, last_retrieved_at=T_OLD, content_retrieved_at=T_OLD,
            )
        )
        kb = MagicMock(uuid="kb-1", title="Policies", description="", tags=[])
        with patch.object(knowledge_service, "require_kb_sources", AsyncMock()), \
             patch.object(knowledge_service, "get_kb_sources", AsyncMock(return_value=[src])):
            payload = await knowledge_service.export_knowledge_base(kb)

        assert payload["format_version"] == 1  # additive: old importers still accept it
        exported = payload["sources"][0]
        assert exported["content"] == OLD_TEXT
        assert exported["status"] == "ready"
        assert exported["chunk_count"] == 3
        assert exported["source_reference"] == "https://example.edu/p"
        assert exported["created_at"] == T_OLD.isoformat()
        c = exported["currency"]
        assert c["status"] == cur.STATUS_RETAINED_PREVIOUS
        assert c["last_refresh_attempted_at"] == T_ATTEMPT.isoformat()
        assert c["last_retrieved_at"] == T_OLD.isoformat()
        assert c["last_ingested_at"] == T_OLD.isoformat()
        assert c["content_retrieved_at"] == T_OLD.isoformat()
        assert c["content_hash"] == "deadbeef"
        assert c["content_hash_recorded"] is True
        assert c["last_refresh_outcome"] == cur.OUTCOME_RETRIEVAL_FAILED
        assert c["last_refresh_error"] == "HTTP 503"

    @pytest.mark.asyncio
    async def test_export_hash_matches_the_exported_content_for_legacy_sources(self):
        """A source that predates hash recording gets a hash of the snapshot
        that is in the same file, so an evaluator can verify it in place."""
        src = SimpleNamespace(**_row(
            url_title="Policy", custom_name=None, document_uuid=None, crawl_enabled=False,
            max_crawl_pages=5, parent_source_uuid=None, crawled_urls=None, created_at=T_OLD,
        ))
        kb = MagicMock(uuid="kb-1", title="Policies", description="", tags=[])
        with patch.object(knowledge_service, "require_kb_sources", AsyncMock()), \
             patch.object(knowledge_service, "get_kb_sources", AsyncMock(return_value=[src])):
            payload = await knowledge_service.export_knowledge_base(kb)

        exported = payload["sources"][0]
        assert exported["currency"]["content_hash"] == cur.content_fingerprint(exported["content"])
        assert exported["currency"]["content_hash_recorded"] is False
        assert exported["currency"]["status"] == cur.STATUS_INGESTED


# ---------------------------------------------------------------------------
# Source API response carries it
# ---------------------------------------------------------------------------

def test_source_response_includes_currency():
    from app.routers.knowledge import _source_response

    src = SimpleNamespace(**_row(
        url_title="Policy", custom_name=None, document_uuid=None, source_reference=None,
        error_message=None, created_at=T_OLD, last_refresh_attempted_at=T_ATTEMPT,
        last_refresh_outcome=cur.OUTCOME_UNCHANGED,
    ))
    resp = _source_response(src)
    assert resp.currency is not None
    assert resp.currency.status == cur.STATUS_UNCHANGED
    assert resp.currency.last_refresh_attempted_at == T_ATTEMPT.isoformat()
    assert resp.currency.content_hash == cur.content_fingerprint(OLD_TEXT)
    assert resp.processed_at == T_OLD.isoformat()
