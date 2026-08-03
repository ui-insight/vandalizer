"""Unit tests for race-safe KB source URL dedup.

URL dedup in add_urls/_crawl_from_source is check-then-insert; two concurrent
ingest runs (e.g. a double-submitted Add URLs modal) could both pass the check
and ingest the same page twice (support ticket: one crawled document appeared
as two identical 378-chunk sources). A unique (knowledge_base_uuid, url) index
now arbitrates the insert; these tests cover the losing writer's skip path and
the startup ensure/self-heal that builds the index over legacy duplicate data.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymongo.errors import DuplicateKeyError, OperationFailure

from app.services import knowledge_service
from app.services.web_fetcher import WebFetchResult


def _html_result(url: str, html: str) -> WebFetchResult:
    return WebFetchResult(
        url=url, title="t", text="body text", raw_html=html,
        used_browser=False, status_code=200,
    )


# ---------------------------------------------------------------------------
# _insert_source_unless_duplicate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_returns_true_on_success():
    source = SimpleNamespace(url="https://a.gov/x", knowledge_base_uuid="kb-1")
    source.insert = AsyncMock()
    assert await knowledge_service._insert_source_unless_duplicate(source) is True
    source.insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_insert_swallows_duplicate_key_and_returns_false():
    source = SimpleNamespace(url="https://a.gov/x", knowledge_base_uuid="kb-1")
    source.insert = AsyncMock(side_effect=DuplicateKeyError("E11000 duplicate key"))
    assert await knowledge_service._insert_source_unless_duplicate(source) is False


@pytest.mark.asyncio
async def test_insert_propagates_other_errors():
    source = SimpleNamespace(url="https://a.gov/x", knowledge_base_uuid="kb-1")
    source.insert = AsyncMock(side_effect=OperationFailure("network down"))
    with pytest.raises(OperationFailure):
        await knowledge_service._insert_source_unless_duplicate(source)


# ---------------------------------------------------------------------------
# add_urls — concurrent seed insert loses the race
# ---------------------------------------------------------------------------


def _mock_source_cls(duplicate_urls: set[str] | None = None):
    """Stand-in for KnowledgeBaseSource.

    Constructed instances whose url is in ``duplicate_urls`` raise
    DuplicateKeyError on insert — simulating a concurrent run whose row
    landed first.
    """
    children = []
    duplicate_urls = duplicate_urls or set()

    def construct(**kwargs):
        src = SimpleNamespace(
            status="pending", error_message=None, uuid="src-1", **kwargs,
        )
        if kwargs.get("url") in duplicate_urls:
            src.insert = AsyncMock(side_effect=DuplicateKeyError("E11000"))
        else:
            src.insert = AsyncMock()
        src.delete = AsyncMock()
        src.save = AsyncMock()
        children.append(src)
        return src

    cls = MagicMock(side_effect=construct)
    cls.find_one = AsyncMock(return_value=None)  # pre-check never sees the other run
    cls.knowledge_base_uuid = MagicMock()
    cls.url = MagicMock()
    return cls, children


@pytest.mark.asyncio
async def test_add_urls_skips_seed_that_lost_the_insert_race():
    url = "https://www.federalregister.gov/documents/2024/04/22/2024-07496/guidance"
    cls, _children = _mock_source_cls(duplicate_urls={url})

    with patch.object(knowledge_service, "KnowledgeBaseSource", cls), \
         patch.object(knowledge_service, "_ingest_url_source", AsyncMock()) as ingest, \
         patch.object(knowledge_service, "recalculate_stats", AsyncMock()) as recalc:
        added = await knowledge_service.add_urls(MagicMock(uuid="kb-1"), [url])

    assert added == 0
    ingest.assert_not_awaited()  # the loser must not re-fetch/re-embed the page
    # Stats still recalculate so the router's status="building" gets restored
    # even when nothing was added.
    recalc.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_urls_continues_past_lost_race_to_next_url():
    lost = "https://a.gov/duplicated"
    won = "https://a.gov/fresh"
    cls, children = _mock_source_cls(duplicate_urls={lost})

    with patch.object(knowledge_service, "KnowledgeBaseSource", cls), \
         patch.object(knowledge_service, "_ingest_url_source",
                      AsyncMock(return_value=None)) as ingest, \
         patch.object(knowledge_service, "recalculate_stats", AsyncMock()):
        added = await knowledge_service.add_urls(MagicMock(uuid="kb-1"), [lost, won])

    assert added == 1
    assert [c.url for c in children] == [lost, won]
    assert ingest.await_count == 1
    assert ingest.await_args.args[0].url == won


# ---------------------------------------------------------------------------
# _crawl_from_source — concurrent child insert loses the race
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawl_skips_child_that_lost_the_insert_race():
    parent = SimpleNamespace(uuid="parent-1", url="https://a.gov/start", crawled_urls=None)
    parent.save = AsyncMock()
    fetched = _html_result(parent.url, '<a href="/dup">D</a> <a href="/ok">O</a>')
    cls, children = _mock_source_cls(duplicate_urls={"https://a.gov/dup"})

    with patch.object(knowledge_service, "KnowledgeBaseSource", cls), \
         patch.object(knowledge_service, "_ingest_url_source",
                      AsyncMock(return_value=None)) as ingest:
        added = await knowledge_service._crawl_from_source(
            parent, MagicMock(uuid="kb-1"), max_pages=5,
            allowed_domains="", parent_fetched=fetched,
        )

    # The lost child is skipped without fetching; the crawl continues.
    assert added == 1
    assert ingest.await_count == 1
    assert ingest.await_args.args[0].url == "https://a.gov/ok"
    assert parent.crawled_urls == ["https://a.gov/ok"]


# ---------------------------------------------------------------------------
# ensure_source_url_unique_index — startup build + self-heal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_index_creates_without_dedupe_when_data_is_clean():
    collection = MagicMock()
    collection.create_indexes = AsyncMock()

    with patch.object(knowledge_service.KnowledgeBaseSource, "get_motor_collection",
                      return_value=collection), \
         patch.object(knowledge_service, "_remove_duplicate_url_sources",
                      AsyncMock()) as dedupe:
        await knowledge_service.ensure_source_url_unique_index()

    collection.create_indexes.assert_awaited_once()
    dedupe.assert_not_awaited()
    (index_models,) = collection.create_indexes.await_args.args
    doc = index_models[0].document
    assert doc["unique"] is True
    assert doc["partialFilterExpression"] == {"url": {"$type": "string"}}
    assert list(doc["key"]) == ["knowledge_base_uuid", "url"]


@pytest.mark.asyncio
async def test_ensure_index_dedupes_and_retries_on_duplicate_key_failure():
    collection = MagicMock()
    collection.create_indexes = AsyncMock(
        side_effect=[OperationFailure("E11000 duplicate key error", 11000), None],
    )

    with patch.object(knowledge_service.KnowledgeBaseSource, "get_motor_collection",
                      return_value=collection), \
         patch.object(knowledge_service, "_remove_duplicate_url_sources",
                      AsyncMock(return_value=2)) as dedupe:
        await knowledge_service.ensure_source_url_unique_index()

    dedupe.assert_awaited_once()
    assert collection.create_indexes.await_count == 2


@pytest.mark.asyncio
async def test_ensure_index_propagates_non_duplicate_failures():
    collection = MagicMock()
    collection.create_indexes = AsyncMock(
        side_effect=OperationFailure("not authorized", 13),
    )

    with patch.object(knowledge_service.KnowledgeBaseSource, "get_motor_collection",
                      return_value=collection), \
         patch.object(knowledge_service, "_remove_duplicate_url_sources",
                      AsyncMock()) as dedupe:
        with pytest.raises(OperationFailure):
            await knowledge_service.ensure_source_url_unique_index()

    dedupe.assert_not_awaited()


# ---------------------------------------------------------------------------
# _remove_duplicate_url_sources — keeps the oldest copy, deletes chunks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_duplicates_keeps_oldest_and_cleans_chunks():
    url = "https://a.gov/page"
    oldest = SimpleNamespace(uuid="src-old", url=url, knowledge_base_uuid="kb-1")
    oldest.delete = AsyncMock()
    newer = SimpleNamespace(uuid="src-new", url=url, knowledge_base_uuid="kb-1")
    newer.delete = AsyncMock()

    collection = MagicMock()
    collection.aggregate.return_value.to_list = AsyncMock(return_value=[
        {"_id": {"kb": "kb-1", "url": url}, "count": 2},
    ])

    # Stub the whole model class: outside an initialized Beanie context the
    # real class raises on expression-field access (KnowledgeBaseSource.url).
    cls = MagicMock()
    cls.get_motor_collection.return_value = collection
    # find(...).sort(...).to_list() — created_at ascending, oldest first
    cls.find.return_value.sort.return_value.to_list = AsyncMock(
        return_value=[oldest, newer],
    )

    dm = MagicMock()
    kb = MagicMock(uuid="kb-1")
    kb_cls = MagicMock()
    kb_cls.find_one = AsyncMock(return_value=kb)

    with patch.object(knowledge_service, "KnowledgeBaseSource", cls), \
         patch.object(knowledge_service, "KnowledgeBase", kb_cls), \
         patch.object(knowledge_service, "_get_dm", return_value=dm), \
         patch.object(knowledge_service, "recalculate_stats", AsyncMock()) as recalc:
        removed = await knowledge_service._remove_duplicate_url_sources()

    assert removed == 1
    oldest.delete.assert_not_awaited()
    newer.delete.assert_awaited_once()
    dm.delete_kb_source.assert_called_once_with("kb-1", "src-new")
    recalc.assert_awaited_once_with(kb)
