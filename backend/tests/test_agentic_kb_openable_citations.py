"""The agentic KB tool must attach the openable file behind each citation.

Support ticket: "Open the source" on a KB citation showed "Source
unavailable" while the PDF sat in Files, Ready. `search_knowledge_base` emitted
only `document_id` — the KB *source* id — and the UI opened that as a file. The
classic KB path already resolves `document_uuid` through
`resolve_openable_documents` (per reader); the tool path never did, so its
chips had no "Open at p. N" either.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_agentic_kb_page_hedging import _passages, _result, _search


@pytest.mark.asyncio
async def test_citation_carries_the_file_the_reader_can_open():
    resolver = AsyncMock(return_value={"src-1": "smartdoc-1"})
    with patch("app.services.knowledge_service.resolve_openable_documents", new=resolver):
        _, ctx = await _search([_result("The page limit is 15.", page=137)])

    citation = ctx.deps.citation_annotations["call-1"][0]
    assert citation["document_id"] == "src-1"
    assert citation["document_uuid"] == "smartdoc-1"
    # Resolved for the person who will click it, not unchecked.
    assert resolver.await_args.kwargs["user_id"] == ctx.deps.user_id
    assert resolver.await_args.args[0] == ["src-1"]


@pytest.mark.asyncio
async def test_a_source_the_reader_cannot_open_stays_preview_only():
    resolver = AsyncMock(return_value={})
    with patch("app.services.knowledge_service.resolve_openable_documents", new=resolver):
        _, ctx = await _search([_result("The page limit is 15.", page=137)])

    assert "document_uuid" not in ctx.deps.citation_annotations["call-1"][0]


def _doc_source(document_uuid: str) -> MagicMock:
    src = MagicMock()
    src.uuid, src.source_type, src.document_uuid = "src-1", "document", document_uuid
    src.url, src.source_reference = None, None
    return src


@pytest.mark.asyncio
async def test_passage_card_links_only_a_file_the_reader_can_open():
    # The passage cards under the tool call opened the source's raw
    # document_uuid, unchecked: a soft-deleted file or another member's
    # personal-space file opened the viewer on "Source unavailable".
    resolver = AsyncMock(return_value={})
    with patch("app.services.knowledge_service.resolve_openable_documents", new=resolver):
        out, _ = await _search(
            [_result("The page limit is 15.", page=137)],
            sources=[_doc_source("deleted-doc")],
        )

    assert "document_uuid" not in _passages(out)[0]


@pytest.mark.asyncio
async def test_passage_card_links_the_resolved_file():
    resolver = AsyncMock(return_value={"src-1": "smartdoc-1"})
    with patch("app.services.knowledge_service.resolve_openable_documents", new=resolver):
        out, _ = await _search(
            [_result("The page limit is 15.", page=137)],
            sources=[_doc_source("smartdoc-1")],
        )

    assert _passages(out)[0]["document_uuid"] == "smartdoc-1"
