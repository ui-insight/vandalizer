"""Bulk URL adds are registered up front and fetched in batches.

Feature request (bulk/sitemap URL import): one add_urls task fetched every
URL in turn, so a few hundred pages outran its time limit and the rest were
silently never added. Rows are now created before any fetch, and each batch
task ingests only rows that are still waiting.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import knowledge_service as ks

KB = SimpleNamespace(uuid="kb-1")


@pytest.mark.asyncio
async def test_register_creates_pending_rows_for_new_urls_only():
    inserted = []

    async def insert(source):
        inserted.append(source)
        return source.url != "https://a.gov/raced"  # another writer got this one

    made = iter(range(100))

    def source(**fields):
        # The model's own default status and per-row uuid, without Beanie.
        return SimpleNamespace(status="pending", uuid=f"u{next(made)}", **fields)

    with patch.object(ks, "partition_new_urls", AsyncMock(return_value=(
        ["https://a.gov/1", "https://a.gov/raced", "https://a.gov/2"], ["https://a.gov/held"],
    ))), patch.object(ks, "_insert_source_unless_duplicate", insert), \
         patch.object(ks, "KnowledgeBaseSource", source):
        uuids = await ks.register_url_sources(KB, ["…"], crawl_enabled=True, max_crawl_pages=7)

    assert [s.url for s in inserted] == ["https://a.gov/1", "https://a.gov/raced", "https://a.gov/2"]
    assert all(s.status == "pending" and s.crawl_enabled and s.max_crawl_pages == 7 for s in inserted)
    assert uuids == [inserted[0].uuid, inserted[2].uuid]


@pytest.mark.asyncio
async def test_ingest_skips_deleted_and_finished_rows_and_crawls_the_rest():
    rows = {
        "pending": SimpleNamespace(uuid="pending", status="pending"),
        "stuck": SimpleNamespace(uuid="stuck", status="processing"),  # a retried task's
        "done": SimpleNamespace(uuid="done", status="ready"),
    }
    order = ["pending", "gone", "done", "stuck"]
    cls = MagicMock()
    cls.find_one = AsyncMock(side_effect=lambda *conds: rows.get(order.pop(0)))
    fetched = object()
    ingest = AsyncMock(return_value=fetched)
    crawl = AsyncMock(return_value=3)
    recalc = AsyncMock()
    with patch.object(ks, "KnowledgeBaseSource", cls), \
         patch.object(ks, "_ingest_url_source", ingest), \
         patch.object(ks, "_crawl_from_source", crawl), \
         patch.object(ks, "recalculate_stats", recalc):
        added = await ks.ingest_url_sources(
            KB, ["pending", "gone", "done", "stuck"], crawl_enabled=True, max_crawl_pages=4, allowed_domains="a.gov",
        )

    assert [c.args[0].uuid for c in ingest.await_args_list] == ["pending", "stuck"]
    assert crawl.await_args.args[2:4] == (4, "a.gov")
    assert added == 2 + 2 * 3
    recalc.assert_awaited_once_with(KB)
