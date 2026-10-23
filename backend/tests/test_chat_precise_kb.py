"""Chat retrieves knowledge-base passages the way workflow grounding does —
precise retrieval when it can run — and cites them by the same source line,
so the passages of a page-less source ("§ 200.308 · part 2") are told apart
instead of all reading as the bare source name."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import chat_service, kb_grounding, kb_retrieval
from app.services.kb_answer_grounding import used_snippet_refs
from app.services.kb_validation_service import AmendmentLinks, RAGConfig

SOURCE = "OMB Uniform Guidance — Subpart D"


def _section_chunk(n: int, part: int, *, section: str = "200.308", parts: int = 2) -> dict:
    return {
        "content": f"§ {section} Revision of budget and program plans, part {part}.",
        "metadata": {"source_name": SOURCE, "source_id": "src-d", "section_key": section,
                     "section_part": part, "section_parts": parts},
        "chunk_id": f"src-d_chunk_{n}",
        "score": 0.5,
        "similarity": 0.8,
    }


@pytest.fixture
def precise_on(monkeypatch):
    monkeypatch.setattr(kb_retrieval, "enabled", lambda: True)
    monkeypatch.setattr("app.services.document_manager.get_document_manager", lambda: MagicMock())


def _patched(**overrides):
    mocks = {
        "app.services.kb_validation_service._ensure_system_config_loaded": AsyncMock(),
        "app.services.kb_validation_service.resolve_kb_rag_config": AsyncMock(return_value=RAGConfig(k=4)),
        "app.services.kb_validation_service.retrieve_kb_chunks": AsyncMock(return_value=([], RAGConfig(k=4), 0)),
        "app.services.kb_validation_service.load_amendment_links": AsyncMock(return_value=AmendmentLinks()),
        "app.services.kb_validation_service.retrieve_amendment_chunks": AsyncMock(return_value=[]),
        "app.services.knowledge_service.resolve_openable_documents": AsyncMock(return_value={}),
        "app.services.chat_service._retrieve_pinned_chunks": AsyncMock(return_value=[]),
    }
    mocks.update(overrides)
    return mocks


async def _segment(message: str, mocks: dict):
    patches = [patch(target, new=mock) for target, mock in mocks.items()]
    for p in patches:
        p.start()
    try:
        return await chat_service._build_kb_segment("kb-1", message, "test-model")
    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_chat_uses_precise_retrieval_and_cites_sections(precise_on, monkeypatch):
    pool = [_section_chunk(4, 1), _section_chunk(5, 2)]
    monkeypatch.setattr(kb_grounding, "_precise_pool", lambda dm, kb, q, k, floor: list(pool))
    mocks = _patched()
    segment, sources = await _segment("What does § 200.308 say about revising a budget?", mocks)

    assert [s["label"] for s in sources] == [f"{SOURCE} · § 200.308 · part 1", f"{SOURCE} · § 200.308 · part 2"]
    assert [s["cite_label"] for s in sources] == [s["label"] for s in sources]
    assert sources[1]["content"] == pool[1]["content"]
    assert f"**[S2] Source: {SOURCE} · § 200.308 · part 2**" in segment.text
    # Precise retrieval stands in for the vector pool and chat's own pins.
    mocks["app.services.kb_validation_service.retrieve_kb_chunks"].assert_not_awaited()
    mocks["app.services.chat_service._retrieve_pinned_chunks"].assert_not_awaited()


@pytest.mark.asyncio
async def test_a_question_the_base_cannot_answer_gets_no_snippets(precise_on, monkeypatch):
    monkeypatch.setattr(kb_grounding, "_precise_pool", lambda dm, kb, q, k, floor: [])
    segment, sources = await _segment("Can grant funds buy beer for a lab party?", _patched())
    assert segment is None and sources == []


@pytest.mark.asyncio
async def test_the_vector_pipeline_stands_when_precise_retrieval_cannot_run(precise_on, monkeypatch):
    monkeypatch.setattr(kb_grounding, "_precise_pool", lambda dm, kb, q, k, floor: None)
    vector = AsyncMock(return_value=([_section_chunk(1, 1)], RAGConfig(k=4), 0))
    mocks = _patched(**{"app.services.kb_validation_service.retrieve_kb_chunks": vector})
    _, sources = await _segment("revision of budget", mocks)
    vector.assert_awaited()
    assert sources[0]["label"] == f"{SOURCE} · § 200.308 · part 1"


@pytest.mark.asyncio
async def test_amendment_passages_are_held_to_the_relevance_cut(precise_on, monkeypatch):
    monkeypatch.setattr(kb_grounding, "_precise_pool", lambda dm, kb, q, k, floor: [_section_chunk(4, 1)])
    off_topic = {"content": "Unrelated amendment text.", "metadata": {"source_name": "Supplement", "source_id": "s2"},
                 "chunk_id": "s2_chunk_0", "score": 0.1}
    cut = MagicMock(return_value=[])
    monkeypatch.setattr(kb_grounding, "precise_cut", cut)
    mocks = _patched(**{
        "app.services.kb_validation_service.retrieve_amendment_chunks": AsyncMock(return_value=[off_topic]),
    })
    _, sources = await _segment("revision of budget", mocks)
    assert cut.called
    assert [s["document_title"] for s in sources] == [SOURCE]


def test_a_section_citation_marks_only_that_passage_used():
    sources = [
        {"ref": 1, "document_title": SOURCE, "label": f"{SOURCE} · § 200.308 · part 1"},
        {"ref": 2, "document_title": SOURCE, "label": f"{SOURCE} · § 200.308 · part 2"},
        {"ref": 3, "document_title": SOURCE, "label": f"{SOURCE} · § 200.309"},
    ]
    assert used_snippet_refs(f"Rebudgeting [Source: {SOURCE} · § 200.308 · part 2].", sources) == [2]
    assert used_snippet_refs(f"[Source: {SOURCE} · § 200.309; {SOURCE} · § 200.308 · part 1]", sources) == [1, 3]
    # A citation naming only the source still counts for all of its passages.
    assert used_snippet_refs(f"[Source: {SOURCE}]", sources) == [1, 2, 3]
    # "part 2" is not a page.
    assert used_snippet_refs(f"[Source: {SOURCE}, part 2]", sources) == []


@pytest.mark.asyncio
async def test_the_agent_search_returns_labels_to_cite(precise_on, monkeypatch):
    from tests.test_agentic_kb_page_hedging import _kb, _make_context

    monkeypatch.setattr(kb_grounding, "_precise_pool",
                        lambda dm, kb, q, k, floor: [_section_chunk(4, 1), _section_chunk(5, 2)])
    ctx = _make_context()
    ctx.tool_call_id = "call-1"
    with (
        patch("app.services.chat_tools.KnowledgeBase") as kb_cls,
        patch("app.services.chat_tools.KnowledgeBaseSource") as source_cls,
        patch("app.services.kb_validation_service._ensure_system_config_loaded", new=AsyncMock()),
        patch("app.services.kb_validation_service.resolve_kb_rag_config",
              new=AsyncMock(return_value=RAGConfig(k=4))),
        patch("app.services.kb_validation_service.retrieve_kb_chunks", new=AsyncMock()) as vector,
        patch("app.services.user_memory_service.record_kb_query", new=AsyncMock()),
        patch("app.services.knowledge_service.resolve_openable_documents", new=AsyncMock(return_value={})),
    ):
        kb_cls.find_one = AsyncMock(return_value=_kb())
        source_cls.find.return_value.to_list = AsyncMock(return_value=[])
        from app.services.chat_tools import search_knowledge_base

        out = await search_knowledge_base(ctx, "revising a budget", kb_uuid="kb-1")
    vector.assert_not_awaited()
    assert [e["label"] for e in out] == [f"{SOURCE} · § 200.308 · part 1", f"{SOURCE} · § 200.308 · part 2"]
    citations = ctx.deps.citation_annotations["call-1"]
    assert [c["cite_label"] for c in citations] == [e["label"] for e in out]
    assert citations[0]["content"].startswith("§ 200.308")


def test_ui_sidecars_leave_the_result_the_model_reads():
    content = {"status": "completed", "output": "x", "quality": {"score": 90}, "cited_sources": [{"label": "L"}]}
    same = content
    quality, cited = chat_service._pop_ui_sidecars(content)
    assert quality == {"score": 90} and cited == [{"label": "L"}]
    # Popped in place: the next model request sends this very object.
    assert same is content and content == {"status": "completed", "output": "x"}
    assert chat_service._pop_ui_sidecars(["not", "a", "dict"]) == (None, None)
