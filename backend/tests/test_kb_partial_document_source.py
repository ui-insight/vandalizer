"""A KB source whose document was only partly converted.

Support ticket: a KB built on nsf24_1.pdf answered from text that held the
Introduction, Chapter II and Chapter XII of the PAPPG and none of Chapters
I, III, IV or V, with the source wearing a green check — and the inspector's
File view answered ``{"detail": "File not found"}``. The document pipeline
already records a partial conversion on the document (``ingestion_warnings``);
chat and the file list say so. The KB did not, anywhere: not the source row,
not the inspector, not the export, and not source health, which is a fifth of
the KB's quality score.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import knowledge_service, kb_validation_service
from app.routers import knowledge as routes


def _source(uuid="src-1", document_uuid="doc-1", source_type="document", **overrides):
    s = SimpleNamespace(
        uuid=uuid, source_type=source_type, document_uuid=document_uuid,
        document_title=None, url=None, url_title=None, custom_name=None,
        source_reference=None, status="ready", error_message=None, chunk_count=7,
        truncated=False, created_at=None, processed_at=None, content=None,
        crawl_enabled=False, max_crawl_pages=5, parent_source_uuid=None,
        crawled_urls=None,
    )
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _doc(uuid="doc-1", warnings=(), raw_text="Chapter II. Proposal Preparation …", **overrides):
    d = MagicMock()
    d.uuid = uuid
    d.title = "nsf24_1.pdf"
    d.raw_text = raw_text
    d.ingestion_warnings = list(warnings)
    d.downloadpath = "uploads/nsf24_1.pdf"
    d.path = None
    for k, v in overrides.items():
        setattr(d, k, v)
    return d


def _find_returning(docs):
    model = MagicMock()
    model.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=docs)))
    return model


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class TestResolveDocumentIngestionWarnings:
    @pytest.mark.asyncio
    async def test_reports_the_pipeline_codes_for_a_partial_document(self):
        with patch.object(
            knowledge_service, "SmartDocument",
            _find_returning([_doc(warnings=["partial_ocr"])]),
        ):
            out = await knowledge_service.resolve_document_ingestion_warnings([_source()])
        assert out == {"src-1": ["partial_ocr"]}

    @pytest.mark.asyncio
    async def test_a_complete_document_and_a_url_source_are_absent(self):
        sources = [_source(), _source(uuid="src-2", document_uuid=None, source_type="url")]
        with patch.object(knowledge_service, "SmartDocument", _find_returning([_doc()])):
            out = await knowledge_service.resolve_document_ingestion_warnings(sources)
        assert out == {}

    @pytest.mark.asyncio
    async def test_codes_the_pipeline_no_longer_emits_are_dropped(self):
        with patch.object(
            knowledge_service, "SmartDocument",
            _find_returning([_doc(warnings=["retired_code", "sparse_text"])]),
        ):
            out = await knowledge_service.resolve_document_ingestion_warnings([_source()])
        assert out == {"src-1": ["sparse_text"]}

    @pytest.mark.asyncio
    async def test_a_lookup_failure_warns_about_nothing(self):
        model = MagicMock()
        model.find = MagicMock(side_effect=RuntimeError("no beanie"))
        with patch.object(knowledge_service, "SmartDocument", model):
            out = await knowledge_service.resolve_document_ingestion_warnings([_source()])
        assert out == {}


# ---------------------------------------------------------------------------
# Source row
# ---------------------------------------------------------------------------

def test_source_response_carries_the_warning_and_its_text():
    resp = routes._source_response(_source(), ingestion_warnings=["partial_ocr"])
    assert resp.ingestion_warnings == ["partial_ocr"]
    assert resp.ingestion_warning_text == "only part of this document could be converted"
    # Still "ready": the chunks are real and still answer. The row decides
    # how to paint that, the way it does for a truncated URL source.
    assert resp.status == "ready"


def test_source_response_without_warnings_is_unchanged():
    resp = routes._source_response(_source())
    assert resp.ingestion_warnings == []
    assert resp.ingestion_warning_text is None


def test_source_response_joins_several_warnings():
    resp = routes._source_response(
        _source(), ingestion_warnings=["partial_ocr", "sparse_text", "bogus"],
    )
    assert resp.ingestion_warnings == ["partial_ocr", "sparse_text"]
    assert resp.ingestion_warning_text == (
        "only part of this document could be converted; "
        "far less text than its page count suggests"
    )


# ---------------------------------------------------------------------------
# Whether the File view can be offered
# ---------------------------------------------------------------------------

class TestDocumentFileStatus:
    async def _status(self, doc, *, authorized, exists):
        storage = MagicMock()
        storage.exists = AsyncMock(return_value=exists)
        with patch("app.services.access_control.get_authorized_document",
                   AsyncMock(return_value=doc if authorized else None)), \
             patch("app.services.storage.get_storage", return_value=storage), \
             patch("app.dependencies.get_settings", return_value=MagicMock()):
            return await routes._document_file_status(doc, MagicMock())

    @pytest.mark.asyncio
    async def test_available_when_the_viewer_may_open_it_and_the_file_is_there(self):
        assert await self._status(_doc(), authorized=True, exists=True) == "available"

    @pytest.mark.asyncio
    async def test_no_access_when_the_kb_is_shared_but_the_document_is_not(self):
        assert await self._status(_doc(), authorized=False, exists=True) == "no_access"

    @pytest.mark.asyncio
    async def test_missing_when_the_stored_file_is_gone(self):
        assert await self._status(_doc(), authorized=True, exists=False) == "missing"

    @pytest.mark.asyncio
    async def test_missing_when_the_document_has_no_stored_path(self):
        doc = _doc(downloadpath=None, path=None)
        assert await self._status(doc, authorized=True, exists=True) == "missing"

    @pytest.mark.asyncio
    async def test_a_storage_error_counts_as_missing(self):
        storage = MagicMock()
        storage.exists = AsyncMock(side_effect=OSError("bucket unreachable"))
        with patch("app.services.access_control.get_authorized_document",
                   AsyncMock(return_value=_doc())), \
             patch("app.services.storage.get_storage", return_value=storage), \
             patch("app.dependencies.get_settings", return_value=MagicMock()):
            assert await routes._document_file_status(_doc(), MagicMock()) == "missing"


# ---------------------------------------------------------------------------
# Source health — a fifth of the KB quality score
# ---------------------------------------------------------------------------

class TestSourceHealth:
    async def _health(self, doc):
        sources = MagicMock()
        sources.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[_source()])))
        model = MagicMock()
        model.find_one = AsyncMock(return_value=doc)
        with patch.object(kb_validation_service, "KnowledgeBaseSource", sources), \
             patch("app.models.document.SmartDocument", model):
            return await kb_validation_service.check_source_health("kb-1")

    @pytest.mark.asyncio
    async def test_a_partial_document_is_not_a_healthy_source(self):
        health = await self._health(_doc(warnings=["partial_ocr"]))
        assert health["healthy"] == 0
        assert health["unhealthy"] == 1
        entry = health["details"][0]
        assert entry["status"] == "partial"
        assert entry["error"] == "only part of this document could be converted"

    @pytest.mark.asyncio
    async def test_a_complete_document_still_is(self):
        health = await self._health(_doc())
        assert health["healthy"] == 1
        assert health["details"][0]["status"] == "healthy"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_export_names_the_warning_beside_the_partial_text():
    kb = MagicMock(uuid="kb-1", title="NSF PAPPG", description="", tags=[])
    with patch.object(knowledge_service, "require_kb_sources", AsyncMock()), \
         patch.object(knowledge_service, "get_kb_sources", AsyncMock(return_value=[_source()])), \
         patch.object(knowledge_service, "SmartDocument",
                      MagicMock(find_one=AsyncMock(return_value=_doc(warnings=["partial_ocr"])))):
        payload = await knowledge_service.export_knowledge_base(kb)
    exported = payload["sources"][0]
    assert exported["content"] == "Chapter II. Proposal Preparation …"
    assert exported["ingestion_warnings"] == ["partial_ocr"]
