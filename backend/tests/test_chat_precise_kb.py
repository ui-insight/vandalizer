"""Chat retrieves knowledge-base passages the way workflow grounding does —
precise retrieval when it can run — and cites them by the same source line,
so the passages of a page-less source ("§ 200.308 · part 2") are told apart
instead of all reading as the bare source name."""

import asyncio
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
    # The question found these itself: no rewording caution.
    assert chat_service.RESCUED_SNIPPET_MARK not in segment.text
    assert chat_service.RESCUED_SNIPPETS_NOTE not in segment.text
    # Precise retrieval stands in for the vector pool and chat's own pins.
    mocks["app.services.kb_validation_service.retrieve_kb_chunks"].assert_not_awaited()
    mocks["app.services.chat_service._retrieve_pinned_chunks"].assert_not_awaited()


@pytest.mark.asyncio
async def test_a_question_the_base_cannot_answer_gets_no_snippets(precise_on, monkeypatch):
    monkeypatch.setattr(kb_grounding, "_precise_pool", lambda dm, kb, q, k, floor: [])
    asked = AsyncMock(return_value=[])
    monkeypatch.setattr("app.services.kb_paraphrase.paraphrases", asked)
    segment, sources = await _segment("Can grant funds buy beer for a lab party?", _patched())
    assert segment is None and sources == []
    # Asked again in the base's own words, which found nothing either.
    asked.assert_awaited_once_with("Can grant funds buy beer for a lab party?", "test-model")


@pytest.mark.asyncio
async def test_a_question_that_keeps_nothing_gets_what_its_paraphrase_finds(precise_on, monkeypatch):
    monkeypatch.setattr(kb_grounding, "_precise_pool", lambda dm, kb, q, k, floor: [])
    monkeypatch.setattr("app.services.kb_paraphrase.paraphrases",
                        AsyncMock(return_value=["revision of budget and program plans"]))
    found = MagicMock(return_value=[_section_chunk(4, 1)])
    monkeypatch.setattr(kb_grounding, "paraphrase_pool", found)
    segment, sources = await _segment("We want to move money between budget lines. Is that ok?", _patched())
    assert [s["label"] for s in sources] == [f"{SOURCE} · § 200.308 · part 1"]
    assert found.call_args.args[3] == ["revision of budget and program plans"]
    # The question as asked found none of it, and the model is told so.
    assert f"**[S1] Source: {SOURCE} · § 200.308 · part 1**\n{chat_service.RESCUED_SNIPPET_MARK}\n" in segment.text
    assert chat_service.RESCUED_SNIPPETS_NOTE in segment.text


@pytest.mark.asyncio
async def test_a_follow_up_is_searched_with_the_question_it_follows(precise_on, monkeypatch):
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

    pools = {
        "second no-cost extension after the one-time extension": [_section_chunk(6, 2)],
        "How long is the one-time no-cost extension we can take ourselves?": [_section_chunk(5, 1)],
    }
    asked: list[str] = []

    def pool(dm, kb, q, k, floor):
        asked.append(q)
        return list(pools.get(q, []))

    monkeypatch.setattr(kb_grounding, "_precise_pool", pool)
    history = [
        ModelRequest(parts=[UserPromptPart(content="How long is the one-time no-cost extension we can take ourselves?")]),
        ModelResponse(parts=[TextPart(content="Up to 12 months.")]),
    ]
    mocks = _patched(**{
        "app.services.kb_validation_service.condense_retrieval_query":
            AsyncMock(return_value=("second no-cost extension after the one-time extension", 0)),
    })
    patches = [patch(target, new=mock) for target, mock in mocks.items()]
    for p in patches:
        p.start()
    try:
        segment, sources = await chat_service._build_kb_segment(
            "kb-1", "We already used it. Can we get a second extension?", "test-model", history=history,
        )
    finally:
        for p in patches:
            p.stop()
    assert asked == list(pools)
    # The condensed query's passages first, then the earlier question's.
    assert [s["label"] for s in sources] == [f"{SOURCE} · § 200.308 · part 2", f"{SOURCE} · § 200.308 · part 1"]
    # The follow-up kept passages of its own, so none is marked.
    assert chat_service.RESCUED_SNIPPET_MARK not in segment.text


@pytest.mark.asyncio
async def test_a_follow_up_only_its_earlier_question_finds_is_marked(precise_on, monkeypatch):
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

    earlier = "How long is the one-time no-cost extension we can take ourselves?"
    monkeypatch.setattr(kb_grounding, "_precise_pool",
                        lambda dm, kb, q, k, floor: [_section_chunk(5, 1)] if q == earlier else [])
    monkeypatch.setattr("app.services.kb_paraphrase.paraphrases", AsyncMock(return_value=[]))
    history = [
        ModelRequest(parts=[UserPromptPart(content=earlier)]),
        ModelResponse(parts=[TextPart(content="Up to 12 months.")]),
    ]
    mocks = _patched(**{
        "app.services.kb_validation_service.condense_retrieval_query":
            AsyncMock(return_value=("second no-cost extension after the one-time extension", 0)),
    })
    patches = [patch(target, new=mock) for target, mock in mocks.items()]
    for p in patches:
        p.start()
    try:
        segment, sources = await chat_service._build_kb_segment(
            "kb-1", "We already used it. Can we get a second extension?", "test-model", history=history,
        )
    finally:
        for p in patches:
            p.stop()
    # The earlier question's passage is about the first extension, not the
    # second one asked about now.
    assert [s["label"] for s in sources] == [f"{SOURCE} · § 200.308 · part 1"]
    assert chat_service.RESCUED_SNIPPET_MARK in segment.text
    assert chat_service.RESCUED_SNIPPETS_NOTE in segment.text


@pytest.mark.asyncio
async def test_each_part_of_a_compound_question_is_searched(precise_on, monkeypatch):
    message = "Can we rebudget into equipment, and who approves the extension?"
    monkeypatch.setattr(kb_grounding, "_precise_pool", lambda dm, kb, q, k, floor: [_section_chunk(4, 1)])
    split = AsyncMock(return_value=["rebudgeting into equipment", "approval of a no-cost extension"])
    monkeypatch.setattr("app.services.kb_paraphrase.parts", split)
    found = {"rebudgeting into equipment": [_section_chunk(4, 1)],
             "approval of a no-cost extension": [_section_chunk(7, 2, section="200.309")]}
    cuts: list = []
    monkeypatch.setattr(kb_grounding, "paraphrase_pool",
                        lambda dm, kb, q, phrases, k, floor, min_score=None:
                        cuts.append(min_score) or list(found[phrases[0]]))
    segment, sources = await _segment(message, _patched())
    split.assert_awaited_once_with(message, "test-model")
    # Each part is held to the part cut, not the paraphrase cut.
    assert cuts == [kb_retrieval.PART_MIN_SCORE] * 2
    # The question's own passage, then the part the whole question missed.
    assert [s["label"] for s in sources] == [f"{SOURCE} · § 200.308 · part 1", f"{SOURCE} · § 200.309 · part 2"]
    # Beside a passage the question kept, a part's passages are not marked.
    assert chat_service.RESCUED_SNIPPET_MARK not in segment.text


@pytest.mark.asyncio
async def test_a_question_asking_one_thing_is_not_split(precise_on, monkeypatch):
    monkeypatch.setattr(kb_grounding, "_precise_pool", lambda dm, kb, q, k, floor: [_section_chunk(4, 1)])
    split = AsyncMock(return_value=[])
    monkeypatch.setattr("app.services.kb_paraphrase.parts", split)
    await _segment("Do we need prior approval to rebudget into equipment?", _patched())
    split.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_multi_kb_question_asking_one_thing_is_not_split(precise_on, monkeypatch):
    monkeypatch.setattr(kb_grounding, "_precise_pool", lambda dm, kb, q, k, floor: [])
    monkeypatch.setattr("app.services.kb_paraphrase.paraphrases", AsyncMock(return_value=[]))
    split = AsyncMock(return_value=["rebudgeting into equipment", "approval of a no-cost extension"])
    monkeypatch.setattr("app.services.kb_paraphrase.parts", split)
    patches = [patch(target, new=mock) for target, mock in _patched().items()]
    for p in patches:
        p.start()
    try:
        await chat_service._build_multi_kb_segment(
            [("kb-1", "Uniform Guidance"), ("kb-2", "UI policy")],
            "Do we need prior approval to rebudget into equipment?", "test-model",
        )
    finally:
        for p in patches:
            p.stop()
    split.assert_not_awaited()


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


@pytest.mark.asyncio
async def test_a_turn_s_snippets_get_their_adjacent_chunks_after_the_multi_kb_budget(monkeypatch):
    pools = {
        kb: [{**_section_chunk(n, 1, section=f"{100 + i}.{n}", parts=1), "chunk_id": f"{kb}_chunk_{n}"} for n in range(8)]
        for i, kb in enumerate(("kb-a", "kb-b"))
    }

    async def retrieve(kb_uuid, message, model_name, **kw):
        return [dict(r) for r in pools[kb_uuid]]

    seen = []

    def adjacent(dm, passages, n=None):
        seen.append([p["kb_uuid"] for p in passages])
        first = passages[0]
        return [first, {**first, "chunk_id": "beside", "content": "the rest of the rule"}, *passages[1:]]

    monkeypatch.setattr(chat_service, "_retrieve_kb_results", retrieve)
    monkeypatch.setattr(kb_grounding, "with_adjacent", adjacent)
    monkeypatch.setattr("app.services.document_manager.get_document_manager", lambda: MagicMock())
    patches = [patch(target, new=mock) for target, mock in _patched().items()]
    for p in patches:
        p.start()
    try:
        _, two = await chat_service._build_multi_kb_segment([("kb-a", "A"), ("kb-b", "B")], "q", "test-model")
        _, one = await chat_service._build_multi_kb_segment([("kb-a", "A")], "q", "test-model")
    finally:
        for p in patches:
            p.stop()
    # The budget cut first; the adjacent chunk comes on top of it, beside its passage.
    assert len(two) == chat_service.MULTI_KB_SNIPPET_BUDGET + 1
    assert [s["content"] for s in two][1] == "the rest of the rule"
    assert len(one) == 9 and one[1]["content"] == "the rest of the rule"
    assert seen[0].count("kb-a") == seen[0].count("kb-b") == 6 and set(seen[1]) == {"kb-a"}


def _two_pools():
    return {
        kb: [{**_section_chunk(n, 1, section=f"{100 + i}.{n}", parts=1), "chunk_id": f"{kb}_chunk_{n}"} for n in range(8)]
        for i, kb in enumerate(("kb-a", "kb-b"))
    }


async def _multi(kbs, monkeypatch, *, retrieve, pick_section, with_section=None):
    monkeypatch.setattr(chat_service, "_retrieve_kb_results", retrieve)
    monkeypatch.setattr(chat_service, "_pick_section", pick_section)
    monkeypatch.setattr(kb_grounding, "with_adjacent", lambda dm, passages, n=None: passages)
    if with_section is not None:
        monkeypatch.setattr(kb_grounding, "with_section", with_section)
    monkeypatch.setattr("app.services.document_manager.get_document_manager", lambda: MagicMock())
    patches = [patch(target, new=mock) for target, mock in _patched().items()]
    for p in patches:
        p.start()
    try:
        return await chat_service._build_multi_kb_segment(kbs, "q", "test-model")
    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_the_section_pick_is_asked_alongside_retrieval_and_added_after_every_cap(monkeypatch):
    pools = _two_pools()
    asked, asked_first, seen = [], [], []

    async def retrieve(kb_uuid, message, model_name, **kw):
        await asyncio.sleep(0)
        asked_first.append(bool(asked))
        return [dict(r) for r in pools[kb_uuid]]

    async def pick_section(kbs, message, model_name, history=None, effort=None):
        asked.append(([u for u, _ in kbs], effort))
        return ("kb-b", "picked")

    def with_section(dm, passages, picked, query, kb_title=None):
        seen.append((len(passages), picked, kb_title))
        return passages + [{**passages[0], "chunk_id": "picked", "content": "the governing rule"}]

    _, two = await _multi([("kb-a", "A"), ("kb-b", "B")], monkeypatch, retrieve=retrieve,
                          pick_section=pick_section, with_section=with_section)
    _, one = await _multi([("kb-a", "A")], monkeypatch, retrieve=retrieve,
                          pick_section=pick_section, with_section=with_section)
    # Asked both ways before the pools came back; added after the budget cut, last.
    assert asked == [(["kb-a", "kb-b"], None), (["kb-a", "kb-b"], "low"), (["kb-a"], None), (["kb-a"], "low")]
    assert all(asked_first)
    assert len(two) == chat_service.MULTI_KB_SNIPPET_BUDGET + 1 and two[-1]["content"] == "the governing rule"
    assert seen[0] == (chat_service.MULTI_KB_SNIPPET_BUDGET, ("kb-b", "picked"), "B")
    assert len(one) == 9 and one[-1]["content"] == "the governing rule" and seen[1][2] is None


@pytest.mark.asyncio
async def test_a_turn_with_no_passage_cancels_the_section_pick(monkeypatch):
    cancelled = []

    async def retrieve(kb_uuid, message, model_name, **kw):
        await asyncio.sleep(0)
        return []

    async def pick_section(kbs, message, model_name, history=None, effort=None):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append((len(kbs), effort))
            raise

    def with_section(*a, **k):
        raise AssertionError("nothing to add to")

    for kbs in ([("kb-a", "A")], [("kb-a", "A"), ("kb-b", "B")]):
        assert await _multi(kbs, monkeypatch, retrieve=retrieve, pick_section=pick_section,
                            with_section=with_section) == (None, [])
    await asyncio.sleep(0)
    assert cancelled == [(1, None), (1, "low"), (2, None), (2, "low")]


@pytest.mark.asyncio
async def test_the_snippets_stand_when_the_picked_section_cannot_be_added(monkeypatch):
    pools = _two_pools()

    async def retrieve(kb_uuid, message, model_name, **kw):
        return [dict(r) for r in pools[kb_uuid]]

    async def pick_section(kbs, message, model_name, history=None, effort=None):
        return ("kb-a", "picked")

    def with_section(*a, **k):
        raise RuntimeError("index gone")

    async def no_pick(kbs, message, model_name, history=None, effort=None):
        return None

    _, failed = await _multi([("kb-a", "A")], monkeypatch, retrieve=retrieve, pick_section=pick_section,
                             with_section=with_section)
    _, none = await _multi([("kb-a", "A")], monkeypatch, retrieve=retrieve, pick_section=no_pick,
                           with_section=with_section)
    assert len(failed) == len(none) == 8


@pytest.mark.asyncio
async def test_the_pick_reads_the_bases_indexes_and_the_question_a_follow_up_follows(monkeypatch):
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

    from app.services import kb_sections

    calls = []

    async def pick(bases, question, previous, model_name, effort=None):
        calls.append(([(u, t, ix) for u, t, ix in bases], question, previous, model_name, effort))
        return ("kb-a", "200.307")

    monkeypatch.setattr(kb_sections, "pick", pick)
    loaded = AsyncMock()
    monkeypatch.setattr("app.services.kb_validation_service._ensure_system_config_loaded", loaded)
    monkeypatch.setattr(kb_retrieval, "index_for", lambda dm, kb_uuid: None if kb_uuid == "kb-gone" else f"ix-{kb_uuid}")
    monkeypatch.setattr("app.services.document_manager.get_document_manager", lambda: MagicMock())
    history = [ModelRequest(parts=[UserPromptPart(content="Can we charge outsiders for the core facility?")]),
               ModelResponse(parts=[TextPart(content="Yes, as program income.")])]

    monkeypatch.setattr(kb_retrieval, "enabled", lambda: False)
    assert await chat_service._pick_section([("kb-a", "A")], "what about year 2?", "m", history) is None
    assert calls == []

    monkeypatch.setattr(kb_retrieval, "enabled", lambda: True)
    found = await chat_service._pick_section([("kb-a", "A"), ("kb-gone", "G")], "what about year 2?", "m", history)
    assert found == ("kb-a", "200.307") and loaded.await_count == 1
    assert calls[0] == ([("kb-a", "A", "ix-kb-a")], "what about year 2?",
                        "Can we charge outsiders for the core facility?", "m", None)
    await chat_service._pick_section([("kb-a", "A")], "Under 2 CFR 200, may a university keep the program income a core facility earns from outside users during a federal award?", "m", history)
    assert calls[1][2] is None
    await chat_service._pick_section([("kb-a", "A")], "what about year 2?", "m", history, effort="low")
    assert calls[2][4] == "low"


def _gated_picks(monkeypatch):
    """A stand-in _pick_section whose two calls (by effort) return what the
    test sets on their gate, when it sets it; and which of them were cancelled."""
    gates, cancelled = {}, []

    async def pick_section(kbs, message, model_name, history=None, effort=None):
        gates[effort] = asyncio.get_running_loop().create_future()
        try:
            return await gates[effort]
        except asyncio.CancelledError:
            cancelled.append(effort)
            raise

    monkeypatch.setattr(chat_service, "_pick_section", pick_section)
    return gates, cancelled


@pytest.mark.asyncio
@pytest.mark.parametrize("back, then, picked, cancelled", [
    # back when the bases have been searched | back after | the turn takes | cancelled
    ({None: ("kb-a", "full"), "low": ("kb-a", "fast")}, {}, ("kb-a", "full"), []),
    ({"low": ("kb-a", "fast")}, {}, ("kb-a", "fast"), [None]),
    ({}, {None: ("kb-a", "full")}, ("kb-a", "full"), ["low"]),
    ({}, {"low": ("kb-a", "fast")}, ("kb-a", "fast"), [None]),
    ({"low": None}, {None: ("kb-a", "full")}, ("kb-a", "full"), []),
    ({None: None}, {"low": ("kb-a", "fast")}, ("kb-a", "fast"), []),
    ({None: None, "low": None}, {}, None, []),
])
async def test_the_turn_takes_the_default_pick_if_back_else_whichever_next_names_a_section(
        monkeypatch, back, then, picked, cancelled):
    from app.services import kb_sections

    gates, was_cancelled = _gated_picks(monkeypatch)
    picks = chat_service._SectionPicks([("kb-a", "A")], "q", "m")
    await asyncio.sleep(0)
    assert set(gates) == {None, kb_sections.FAST_EFFORT} == {None, "low"}
    for effort, found in back.items():
        gates[effort].set_result(found)
    await asyncio.sleep(0)
    taking = asyncio.ensure_future(picks.result())
    await asyncio.sleep(0)
    assert not taking.done() or not then
    for effort, found in then.items():
        gates[effort].set_result(found)
    assert await taking == picked
    await asyncio.sleep(0)
    assert was_cancelled == cancelled
