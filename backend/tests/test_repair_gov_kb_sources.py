"""Unit tests for the poisoned-KB-source repair script."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import scripts.repair_gov_kb_sources as repair_mod
from scripts.repair_gov_kb_sources import _is_broken, repair

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
         patch("app.services.knowledge_service.recalculate_stats", recalc):
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
