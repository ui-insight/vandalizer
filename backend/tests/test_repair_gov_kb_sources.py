"""Unit tests for the poisoned-KB-source repair script."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import scripts.repair_gov_kb_sources as repair_mod
from scripts.repair_gov_kb_sources import (
    _classify_failure,
    _is_broken,
    _split_chapter_source,
    repair,
)

REQUEST_ACCESS_PAGE = (
    "Federal Register :: Request Access. Due to aggressive automated scraping "
    "of FederalRegister.gov and eCFR.gov, programmatic access to these sites "
    "is limited to access to our extensive developer APIs."
)

ECFR_URL = "https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/subpart-A"


def _source(**kwargs) -> SimpleNamespace:
    base = dict(
        uuid="src1", knowledge_base_uuid="kb1", source_type="url",
        url=None, content=None, status="ready", error_message=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _kb(**kwargs) -> SimpleNamespace:
    base = dict(uuid="kb1", title="OMB Uniform Guidance")
    base.update(kwargs)
    return SimpleNamespace(**base)


# --- _is_broken ---

def test_cached_challenge_page_is_broken():
    src = _source(url=ECFR_URL, content=REQUEST_ACCESS_PAGE)
    assert _is_broken(src) == "cached bot-challenge page"


def test_error_status_is_broken():
    src = _source(url="https://example.gov/x", content="real text " * 500,
                  status="error", error_message="HTTP 403")
    assert _is_broken(src).startswith("error status")


def test_empty_content_is_broken():
    src = _source(url="https://example.gov/x", content=None)
    assert _is_broken(src) == "no cached content"


def test_healthy_source_is_not_broken():
    src = _source(url=ECFR_URL, content="Subpart A—Definitions " * 300)
    assert _is_broken(src) is None


# --- repair() flow ---

def _patch_models(kb, sources):
    kb_cls = MagicMock()
    kb_cls.find_all.return_value.to_list = AsyncMock(return_value=[kb])
    src_cls = MagicMock()
    src_cls.find.return_value.to_list = AsyncMock(return_value=sources)
    return (
        patch.object(repair_mod, "KnowledgeBase", kb_cls),
        patch.object(repair_mod, "KnowledgeBaseSource", src_cls),
    )


async def test_repair_uses_bundled_text(tmp_path, monkeypatch):
    (tmp_path / "sub-a.txt").write_text("Subpart A regulation text.")
    monkeypatch.setattr(repair_mod, "DEFAULT_OUT_DIR", tmp_path)
    monkeypatch.setattr(
        repair_mod, "_load_manifest",
        lambda: {ECFR_URL: {"file": "sub-a.txt", "title": "Subpart A"}},
    )
    kb = _kb()
    poisoned = _source(url=ECFR_URL, content=REQUEST_ACCESS_PAGE)
    healthy = _source(uuid="src2", url="https://example.gov/ok",
                      content="fine " * 1000)
    ingest_text = AsyncMock(return_value=7)
    ingest_url = AsyncMock(return_value=None)
    recalc = AsyncMock()
    p_kb, p_src = _patch_models(kb, [poisoned, healthy])
    with p_kb, p_src, \
         patch("app.services.knowledge_service.ingest_text_into_source", ingest_text), \
         patch("app.services.knowledge_service._ingest_url_source", ingest_url), \
         patch("app.services.knowledge_service.recalculate_stats", recalc), \
         patch("app.services.document_manager.get_document_manager", return_value=MagicMock()):
        await repair(dry_run=False, refetch_others=True)

    ingest_text.assert_awaited_once()
    args = ingest_text.await_args
    assert args.args[0] is poisoned
    assert args.args[2] == "Subpart A regulation text."
    assert args.kwargs["label"] == "Subpart A"
    ingest_url.assert_not_awaited()  # healthy source untouched
    recalc.assert_awaited_once()


async def test_repair_refetches_non_ecfr_broken_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(repair_mod, "DEFAULT_OUT_DIR", tmp_path)
    monkeypatch.setattr(repair_mod, "_load_manifest", lambda: {})
    kb = _kb()
    broken = _source(url="https://grants.gov/policies", status="error",
                     error_message="Blocked by bot protection")
    ingest_text = AsyncMock(return_value=1)
    ingest_url = AsyncMock(return_value=object())
    recalc = AsyncMock()
    dm = MagicMock()
    p_kb, p_src = _patch_models(kb, [broken])
    with p_kb, p_src, \
         patch("app.services.knowledge_service.ingest_text_into_source", ingest_text), \
         patch("app.services.knowledge_service._ingest_url_source", ingest_url), \
         patch("app.services.knowledge_service.recalculate_stats", recalc), \
         patch("app.services.document_manager.get_document_manager", return_value=dm):
        await repair(dry_run=False, refetch_others=True)

    ingest_text.assert_not_awaited()
    dm.delete_kb_source.assert_called_once_with(kb.uuid, broken.uuid)
    ingest_url.assert_awaited_once_with(broken, kb)
    recalc.assert_awaited_once()


async def test_repair_aborts_when_vector_store_readonly(monkeypatch, tmp_path):
    monkeypatch.setattr(repair_mod, "DEFAULT_OUT_DIR", tmp_path)
    monkeypatch.setattr(repair_mod, "_load_manifest", lambda: {})
    monkeypatch.setattr(
        repair_mod, "_vector_store_write_error",
        lambda: "OperationalError: attempt to write a readonly database",
    )
    kb = _kb()
    broken = _source(url=ECFR_URL, content=REQUEST_ACCESS_PAGE)
    ingest_text = AsyncMock()
    ingest_url = AsyncMock()
    p_kb, p_src = _patch_models(kb, [broken])
    with p_kb, p_src, \
         patch("app.services.knowledge_service.ingest_text_into_source", ingest_text), \
         patch("app.services.knowledge_service._ingest_url_source", ingest_url):
        await repair(dry_run=False, refetch_others=True)

    ingest_text.assert_not_awaited()
    ingest_url.assert_not_awaited()


# --- chapter splitting ---

CHAPTER_URL = "https://www.ecfr.gov/current/title-48/chapter-99"


def _chapter_parts():
    return [
        {"part": 9901, "label": "PART 9901—RULES AND PROCEDURES",
         "url": f"{CHAPTER_URL}/subchapter-A/part-9901", "text": "part 9901 text"},
        {"part": 9904, "label": "PART 9904—COST ACCOUNTING STANDARDS",
         "url": f"{CHAPTER_URL}/subchapter-B/part-9904", "text": "part 9904 text"},
    ]


def _chapter_src():
    return SimpleNamespace(
        uuid="src1", knowledge_base_uuid="kb1", url=CHAPTER_URL,
        error_message=None, save=AsyncMock(), delete=AsyncMock(),
    )


def _patch_source_cls(created: list):
    """KnowledgeBaseSource stand-in: find_one misses, constructor records."""
    src_cls = MagicMock()
    src_cls.find_one = AsyncMock(return_value=None)

    def construct(**kwargs):
        obj = SimpleNamespace(**kwargs, insert=AsyncMock())
        created.append(obj)
        return obj

    src_cls.side_effect = construct
    return patch.object(repair_mod, "KnowledgeBaseSource", src_cls)


async def test_chapter_source_splits_into_part_sources():
    kb, src, created = _kb(), _chapter_src(), []
    ingest_text = AsyncMock(return_value=5)
    dm = MagicMock()
    with _patch_source_cls(created), \
         patch.object(repair_mod, "fetch_parts_for_chapter_url",
                      return_value=("Chapter 99", _chapter_parts())), \
         patch("app.services.knowledge_service.ingest_text_into_source", ingest_text), \
         patch("app.services.document_manager.get_document_manager", return_value=dm):
        assert await _split_chapter_source(src, kb, api_client=MagicMock()) is True

    assert [s.url for s in created] == [
        f"{CHAPTER_URL}/subchapter-A/part-9901",
        f"{CHAPTER_URL}/subchapter-B/part-9904",
    ]
    assert all(s.source_type == "url" for s in created)
    assert ingest_text.await_count == 2
    assert ingest_text.await_args_list[1].kwargs["label"] == "PART 9904—COST ACCOUNTING STANDARDS"
    dm.delete_kb_source.assert_called_once_with(kb.uuid, src.uuid)
    src.delete.assert_awaited_once()


async def test_partial_chapter_split_keeps_original_source():
    kb, src, created = _kb(), _chapter_src(), []
    ingest_text = AsyncMock(side_effect=[5, None])  # second part fails
    dm = MagicMock()
    with _patch_source_cls(created), \
         patch.object(repair_mod, "fetch_parts_for_chapter_url",
                      return_value=("Chapter 99", _chapter_parts())), \
         patch("app.services.knowledge_service.ingest_text_into_source", ingest_text), \
         patch("app.services.document_manager.get_document_manager", return_value=dm):
        assert await _split_chapter_source(src, kb, api_client=MagicMock()) is False

    dm.delete_kb_source.assert_not_called()
    src.delete.assert_not_awaited()
    assert "1/2 parts ingested" in src.error_message
    src.save.assert_awaited()


async def test_chapter_fetch_failure_marks_source():
    kb, src = _kb(), _chapter_src()
    with patch.object(repair_mod, "fetch_parts_for_chapter_url",
                      side_effect=ValueError("no issue date for title 48")):
        assert await _split_chapter_source(src, kb, api_client=MagicMock()) is False
    assert "no issue date" in src.error_message
    src.delete.assert_not_awaited()


# --- failure classification ---

def test_classify_failure_buckets():
    assert _classify_failure("attempt to write a readonly database").startswith("infrastructure")
    assert _classify_failure("Client error '404 Not Found' for url 'x'").startswith("dead links")
    assert _classify_failure("Cannot resolve hostname: www.cfo.gov").startswith("dead links")
    assert _classify_failure("The website did not respond before the request timed out").startswith("dead links")
    assert _classify_failure("Client error '403 Forbidden' for url 'x'").startswith("bot-blocked")
    assert _classify_failure("Blocked by the site's bot protection").startswith("bot-blocked")
    assert _classify_failure("something novel") == "other"
    assert _classify_failure(None) == "other"


async def test_dry_run_changes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(repair_mod, "DEFAULT_OUT_DIR", tmp_path)
    monkeypatch.setattr(repair_mod, "_load_manifest", lambda: {})
    kb = _kb()
    broken = _source(url=ECFR_URL, content=REQUEST_ACCESS_PAGE)
    ingest_text = AsyncMock()
    ingest_url = AsyncMock()
    p_kb, p_src = _patch_models(kb, [broken])
    with p_kb, p_src, \
         patch("app.services.knowledge_service.ingest_text_into_source", ingest_text), \
         patch("app.services.knowledge_service._ingest_url_source", ingest_url):
        await repair(dry_run=True, refetch_others=True)

    ingest_text.assert_not_awaited()
    ingest_url.assert_not_awaited()
