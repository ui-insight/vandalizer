"""Unit tests for KB document-source ingestion timing.

A KB source can be added before its document's async text extraction has
finished. ``_ingest_document_source`` must park such a source as "pending"
(to be re-ingested by the extraction-completion hook) rather than recording a
permanent "no text" error.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import knowledge_service


def _make_source():
    src = SimpleNamespace(
        uuid="src-1",
        document_uuid="doc-1",
        status="pending",
        error_message=None,
        chunk_count=0,
        processed_at=None,
    )
    src.save = AsyncMock()
    return src


def _make_doc(**overrides):
    base = dict(
        uuid="doc-1",
        raw_text="",
        processing=False,
        task_status=None,
        error_message=None,
        title="terms.pdf",
        text_markers=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_parks_pending_while_extraction_in_flight():
    source = _make_source()
    doc = _make_doc(processing=True, task_status="extracting")

    with patch.object(knowledge_service, "SmartDocument",
                      MagicMock(find_one=AsyncMock(return_value=doc))), \
         patch.object(knowledge_service, "_get_dm") as mock_get_dm:
        await knowledge_service._ingest_document_source(source, MagicMock(uuid="kb-1"))

    assert source.status == "pending"
    assert source.error_message is None
    # Must not attempt to embed an empty document.
    mock_get_dm.assert_not_called()


@pytest.mark.asyncio
async def test_errors_when_extraction_finished_empty():
    source = _make_source()
    doc = _make_doc(task_status="complete", processing=False)

    with patch.object(knowledge_service, "SmartDocument",
                      MagicMock(find_one=AsyncMock(return_value=doc))), \
         patch.object(knowledge_service, "_get_dm") as mock_get_dm:
        await knowledge_service._ingest_document_source(source, MagicMock(uuid="kb-1"))

    assert source.status == "error"
    assert "no extractable text" in source.error_message.lower()
    mock_get_dm.assert_not_called()


@pytest.mark.asyncio
async def test_errors_when_extraction_failed_uses_doc_message():
    source = _make_source()
    doc = _make_doc(task_status="error", error_message="It may be image-only or encrypted.")

    with patch.object(knowledge_service, "SmartDocument",
                      MagicMock(find_one=AsyncMock(return_value=doc))):
        await knowledge_service._ingest_document_source(source, MagicMock(uuid="kb-1"))

    assert source.status == "error"
    assert source.error_message == "It may be image-only or encrypted."


@pytest.mark.asyncio
async def test_missing_document_errors_distinctly():
    source = _make_source()

    with patch.object(knowledge_service, "SmartDocument",
                      MagicMock(find_one=AsyncMock(return_value=None))):
        await knowledge_service._ingest_document_source(source, MagicMock(uuid="kb-1"))

    assert source.status == "error"
    assert source.error_message == "Document not found"


@pytest.mark.asyncio
async def test_ingests_when_text_present():
    source = _make_source()
    doc = _make_doc(raw_text="Real content here.", task_status="complete",
                    text_markers=[{"char_offset": 0, "kind": "page", "value": 1}])

    dm = MagicMock()
    dm.add_to_kb.return_value = 9

    with patch.object(knowledge_service, "SmartDocument",
                      MagicMock(find_one=AsyncMock(return_value=doc))), \
         patch.object(knowledge_service, "_get_dm", return_value=dm):
        await knowledge_service._ingest_document_source(source, MagicMock(uuid="kb-1"))

    assert source.status == "ready"
    assert source.chunk_count == 9
    # Markers are forwarded so chunks keep page citations.
    _, kwargs = dm.add_to_kb.call_args
    called_args = dm.add_to_kb.call_args[0]
    assert doc.text_markers in called_args or kwargs.get("text_markers") == doc.text_markers
