"""Unit tests for KB URL source version history.

Support ticket: a refresh that found a revised page replaced the source's text
and discarded the old one, so there was no way to show what the source said
when an earlier answer was produced. The database round trip is covered in
tests/integration/test_tier2_kb_source_versions.py; these cover the date
logic, the diff, and where the refresh path records versions.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import kb_source_versions, knowledge_service
from app.services.web_fetcher import WebFetchResult

UTC = datetime.timezone.utc


def _v(number, start, end):
    return SimpleNamespace(uuid=f"v{number}", number=number, in_effect_from=start, superseded_at=end)


JUN = datetime.datetime(2026, 6, 1, tzinfo=UTC)
AUG = datetime.datetime(2026, 8, 1, tzinfo=UTC)
OCT = datetime.datetime(2026, 10, 1, tzinfo=UTC)
VERSIONS = [_v(3, OCT, None), _v(2, AUG, OCT), _v(1, JUN, AUG)]


@pytest.mark.parametrize("at, expected", [
    (datetime.datetime(2026, 7, 4, tzinfo=UTC), "v1"),
    (AUG, "v2"),  # a version takes effect at its start instant
    (OCT - datetime.timedelta(seconds=1), "v2"),
    (datetime.datetime(2026, 12, 25, tzinfo=UTC), "v3"),
    (datetime.datetime(2026, 1, 1, tzinfo=UTC), None),  # before anything was indexed
])
def test_version_in_effect_at(at, expected):
    found = kb_source_versions.version_in_effect_at(VERSIONS, at)
    assert (found.uuid if found else None) == expected


def test_version_in_effect_at_reads_naive_mongo_datetimes_as_utc():
    naive = [_v(2, AUG.replace(tzinfo=None), None), _v(1, JUN.replace(tzinfo=None), AUG.replace(tzinfo=None))]
    assert kb_source_versions.version_in_effect_at(naive, datetime.datetime(2026, 7, 4, tzinfo=UTC)).uuid == "v1"


def test_diff_marks_added_and_removed_lines():
    out = kb_source_versions._diff("a\nthreshold $25,000\nc", "a\nthreshold $50,000\nc", "v1", "v2")
    assert (out["added"], out["removed"], out["truncated"]) == (1, 1, False)
    assert {"op": "-", "text": "threshold $25,000"} in out["lines"]
    assert {"op": "+", "text": "threshold $50,000"} in out["lines"]
    assert out["lines"][0]["op"] == "@"


def test_diff_is_capped_and_says_so():
    old = "\n".join(f"old {i}" for i in range(kb_source_versions.MAX_DIFF_LINES))
    new = "\n".join(f"new {i}" for i in range(kb_source_versions.MAX_DIFF_LINES))
    out = kb_source_versions._diff(old, new, "v1", "v2")
    assert len(out["lines"]) == kb_source_versions.MAX_DIFF_LINES
    assert out["truncated"] is True
    # The counts still describe the whole change, not the shown part.
    assert out["added"] == out["removed"] == kb_source_versions.MAX_DIFF_LINES


@pytest.mark.asyncio
async def test_recording_never_fails_the_caller():
    src = SimpleNamespace(uuid="s", source_type="url", content="text", content_hash=None)
    with patch.object(kb_source_versions, "_latest", AsyncMock(side_effect=RuntimeError("mongo down"))):
        await kb_source_versions.ensure_baseline(src)
        await kb_source_versions.record_current(src, origin="refresh")


@pytest.mark.asyncio
async def test_document_sources_have_no_history():
    src = SimpleNamespace(uuid="s", source_type="document", content="text")
    with patch.object(kb_source_versions, "_latest", AsyncMock()) as latest:
        await kb_source_versions.ensure_baseline(src)
        await kb_source_versions.record_current(src, origin="ingest")
    latest.assert_not_called()


# --- where refresh_url_source records versions -----------------------------

OLD = "Last updated: December 1, 2018\nA. Overview. old text " * 3
NEW = "Last Updated: July 13, 2026\nA. Purpose. new text " * 3


def _source():
    src = SimpleNamespace(
        uuid="src-1", knowledge_base_uuid="kb-1", source_type="url",
        url="https://www.uidaho.edu/policies/apm/45/14", url_title="APM 45.14", custom_name=None,
        content=OLD, status="ready", error_message=None, chunk_count=3, truncated=False,
        processed_at=None, last_collapsed_hash=None, parent_source_uuid=None,
    )
    src.save = AsyncMock()
    return src


def _result(text):
    return WebFetchResult(
        url="https://www.uidaho.edu/policies/apm/45/14", title="APM 45.14", text=text,
        raw_html="<html/>", used_browser=False, status_code=200,
    )


async def _refresh(src, fetch):
    dm = MagicMock()
    dm.replace_kb_source.return_value = 4
    seen = {}

    async def baseline(source):
        # The baseline must see the text the source held before this refresh.
        seen["baseline_content"] = source.content

    async def record(source, *, origin):
        seen["recorded_content"] = source.content
        seen["saved_before_record"] = source.save.await_count > 0
        seen["origin"] = origin

    with patch("app.services.web_fetcher.fetch_url", fetch), \
         patch.object(knowledge_service, "_get_dm", return_value=dm), \
         patch.object(kb_source_versions, "ensure_baseline", side_effect=baseline), \
         patch.object(kb_source_versions, "record_current", side_effect=record):
        reason = await knowledge_service.refresh_url_source(src, MagicMock(uuid="kb-1"))
    return reason, seen


@pytest.mark.asyncio
async def test_refresh_keeps_the_old_text_before_overwriting_it():
    reason, seen = await _refresh(_source(), AsyncMock(return_value=_result(NEW)))

    assert reason is None
    assert seen["baseline_content"] == OLD
    assert seen["recorded_content"] == NEW
    assert seen["saved_before_record"] is True
    assert seen["origin"] == "refresh"


@pytest.mark.asyncio
async def test_failed_refresh_records_no_version():
    reason, seen = await _refresh(_source(), AsyncMock(side_effect=RuntimeError("boom")))

    assert reason
    assert "recorded_content" not in seen
