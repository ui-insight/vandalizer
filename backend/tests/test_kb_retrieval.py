"""Tests for the shared KB retrieval pipeline (``retrieve_kb_chunks``) and the
chat-side segment builder (``_build_kb_segment``).

These guard the "tuned config actually applies on the live path" seam: the
optimizer stores k / min_similarity / rerank / query_rewriting per KB, and both
the validation harness and streaming chat must route retrieval through the
same pipeline.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import chat_service, kb_validation_service
from app.services.kb_validation_service import RAGConfig


def _chunk(i: int, source: str = "doc.pdf", **meta) -> dict:
    metadata = {"source_name": source, "source_id": f"src-{source}"}
    metadata.update(meta)
    return {
        "content": f"chunk {i} content",
        "metadata": metadata,
        "chunk_id": f"src-{source}_chunk_{i}",
        "score": 0.1 * i,
        "similarity": round(0.95 - 0.1 * i, 2),
    }


def _make_mock_run(output: str, tokens: int = 0):
    run = MagicMock()
    run.output = output
    usage = MagicMock()
    usage.input_tokens = tokens
    usage.output_tokens = 0
    usage.cache_read_tokens = 0
    usage.cache_write_tokens = 0
    run.usage = MagicMock(return_value=usage)
    return run


@pytest.mark.asyncio
async def test_explicit_config_k_and_floor_reach_query_kb():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[_chunk(0)])
    cfg = RAGConfig(k=4, min_similarity=0.35)

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm):
        results, resolved, tokens = await kb_validation_service.retrieve_kb_chunks(
            "kb-1", "q?", "test-model", config=cfg,
        )

    fake_dm.query_kb.assert_called_once_with("kb-1", "q?", 4, 0.35)
    assert len(results) == 1
    assert resolved.k == 4
    assert tokens == 0


@pytest.mark.asyncio
async def test_kb_override_resolved_when_no_explicit_config():
    """A KB with an applied rag_config_override must drive retrieval with its
    tuned k, not the hardcoded legacy default."""
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[])
    kb = MagicMock()
    kb.rag_config_override = {"k": 4, "min_similarity": 0.2}

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "KnowledgeBase") as KB:
        KB.find_one = AsyncMock(return_value=kb)
        _, resolved, _ = await kb_validation_service.retrieve_kb_chunks(
            "kb-1", "q?", "test-model",
        )

    fake_dm.query_kb.assert_called_once_with("kb-1", "q?", 4, 0.2)
    assert resolved.k == 4


@pytest.mark.asyncio
async def test_overfetch_multiplier_expands_pool():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[])
    cfg = RAGConfig(k=4)

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm):
        await kb_validation_service.retrieve_kb_chunks(
            "kb-1", "q?", "test-model", config=cfg, overfetch_multiplier=3,
        )

    fake_dm.query_kb.assert_called_once_with("kb-1", "q?", 12, 0.0)


@pytest.mark.asyncio
async def test_rerank_reduces_pool_and_scores_raw_query():
    """rerank='llm' retrieves an oversampled pool, then the rerank agent picks
    cfg.k — and it must be asked about the raw user query."""
    chunks = [_chunk(i) for i in range(5)]
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=chunks)

    captured = {}

    async def fake_run(prompt):
        captured["prompt"] = prompt
        return _make_mock_run("[3, 1]", tokens=77)

    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=fake_run)
    cfg = RAGConfig(k=2, rerank="llm")

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent):
        results, _, tokens = await kb_validation_service.retrieve_kb_chunks(
            "kb-1", "the raw question?", "test-model", config=cfg,
        )

    # Pool oversampled by RERANK_POOL_MULTIPLIER.
    fake_dm.query_kb.assert_called_once_with("kb-1", "the raw question?", 4, 0.0)
    # Rerank output order respected.
    assert [r["chunk_id"] for r in results] == [chunks[3]["chunk_id"], chunks[1]["chunk_id"]]
    assert "the raw question?" in captured["prompt"]
    assert tokens == 77


@pytest.mark.asyncio
async def test_query_rewriting_rewrites_retrieval_but_not_rerank():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[])
    cfg = RAGConfig(k=8, query_rewriting=True)

    rewriter = MagicMock()
    rewriter.run = AsyncMock(return_value=_make_mock_run("rewritten search terms", tokens=9))

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=rewriter):
        _, _, tokens = await kb_validation_service.retrieve_kb_chunks(
            "kb-1", "original question", "test-model", config=cfg,
        )

    fake_dm.query_kb.assert_called_once_with("kb-1", "rewritten search terms", 8, 0.0)
    assert tokens == 9


@pytest.mark.asyncio
async def test_build_kb_segment_trims_to_cfg_k_and_builds_sources():
    chunks = [
        _chunk(0, source="budget.xlsx", sheet="Year 1"),
        _chunk(1, source="proposal.pdf", page=12),
        _chunk(2, source="proposal.pdf", page=13),
    ]
    cfg = RAGConfig(k=2)

    with patch.object(kb_validation_service, "_ensure_system_config_loaded",
                      new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(return_value=(chunks, cfg, 0))):
        segment, sources = await chat_service._build_kb_segment(
            "kb-1", "q?", "test-model",
        )

    assert segment is not None
    # Over-fetched pool trimmed back to the tuned k.
    assert len(sources) == 2
    assert "budget.xlsx (Year 1)" in segment.text
    assert "proposal.pdf (p. 12)" in segment.text
    assert "chunk 2 content" not in segment.text
    assert sources[0]["document_title"] == "budget.xlsx"
    assert sources[0]["sheet"] == "Year 1"
    assert sources[1]["page"] == 12
    assert sources[0]["similarity"] == 0.95


@pytest.mark.asyncio
async def test_build_kb_segment_empty_retrieval_returns_none():
    cfg = RAGConfig()
    with patch.object(kb_validation_service, "_ensure_system_config_loaded",
                      new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(return_value=([], cfg, 0))):
        segment, sources = await chat_service._build_kb_segment(
            "kb-1", "q?", "test-model",
        )

    assert segment is None
    assert sources == []


# ---------------------------------------------------------------------------
# Diversity selection, named-document targeting, manifest
# ---------------------------------------------------------------------------


def test_select_diverse_chunks_caps_dominant_source():
    dominant = [_chunk(i, source="narrative.pdf") for i in range(6)]
    short = [_chunk(9, source="timeline.docx")]
    # Relevance order: narrative fills the top, timeline dead last.
    results = dominant + short

    selected = chat_service._select_diverse_chunks(results, k=4, max_per_source=3)

    sources = [r["metadata"]["source_name"] for r in selected]
    assert sources.count("narrative.pdf") == 3
    assert "timeline.docx" in sources


def test_select_diverse_chunks_backfills_single_source():
    results = [_chunk(i, source="only.pdf") for i in range(5)]
    selected = chat_service._select_diverse_chunks(results, k=4, max_per_source=2)
    # Cap would leave slots empty; backfill keeps k full for single-source KBs.
    assert len(selected) == 4


def test_match_named_sources_matches_with_and_without_extension():
    manifest = [
        {"name": "Project Timeline.docx"},
        {"name": "budget_justification.xlsx"},
        {"name": "a.txt"},
    ]
    assert chat_service._match_named_sources(
        "what does the project timeline say about milestones?", manifest,
    ) == ["Project Timeline.docx"]
    assert chat_service._match_named_sources(
        "open budget_justification.xlsx please", manifest,
    ) == ["budget_justification.xlsx"]
    # Underscores/hyphens normalize to spaces.
    assert chat_service._match_named_sources(
        "check the budget justification numbers", manifest,
    ) == ["budget_justification.xlsx"]


def test_match_named_sources_ignores_short_names():
    manifest = [{"name": "a.txt"}, {"name": "OK.pdf"}]
    assert chat_service._match_named_sources("a fine question, ok?", manifest) == []


def test_compose_kb_results_guarantees_named_slots():
    general = [_chunk(i, source="narrative.pdf") for i in range(8)]
    named = [_chunk(i, source="timeline.docx") for i in range(3)]

    final = chat_service._compose_kb_results(general, named, k=4)

    sources = [r["metadata"]["source_name"] for r in final]
    # ceil(4/2) = 2 slots guaranteed for the named document, rest general.
    assert sources.count("timeline.docx") == 2
    assert len(final) == 4


def test_compose_kb_results_dedupes_named_from_general():
    shared = _chunk(0, source="timeline.docx")
    general = [shared] + [_chunk(i, source="narrative.pdf") for i in range(1, 5)]
    named = [shared, _chunk(1, source="timeline.docx")]

    final = chat_service._compose_kb_results(general, named, k=4)

    ids = [r["chunk_id"] for r in final]
    assert len(ids) == len(set(ids)), "shared chunk must not appear twice"


def test_query_kb_passes_where_filter_to_chroma():
    from app.services.document_manager import DocumentManager

    dm = object.__new__(DocumentManager)
    fake_collection = MagicMock()
    fake_collection.query = MagicMock(return_value={
        "documents": [["some text"]],
        "metadatas": [[{"source_name": "timeline.docx"}]],
        "ids": [["src_chunk_0"]],
        "distances": [[0.4]],
    })
    dm.get_kb_collection_readonly = MagicMock(return_value=fake_collection)

    where = {"source_name": "timeline.docx"}
    results = dm.query_kb("kb-1", "q?", 4, 0.0, where=where)

    fake_collection.query.assert_called_once_with(
        query_texts=["q?"], n_results=4, where=where,
    )
    assert len(results) == 1


@pytest.mark.asyncio
async def test_retrieve_kb_chunks_source_filter_builds_where():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[])
    cfg = RAGConfig(k=4)

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm):
        await kb_validation_service.retrieve_kb_chunks(
            "kb-1", "q?", "test-model", config=cfg,
            source_filter=["timeline.docx", "budget.xlsx"],
        )

    assert fake_dm.query_kb.call_args.kwargs["where"] == {
        "source_name": {"$in": ["timeline.docx", "budget.xlsx"]},
    }


@pytest.mark.asyncio
async def test_build_kb_segment_targets_named_document():
    """A message naming a manifest file triggers a second, source-filtered
    retrieval whose chunks are guaranteed slots in the final context."""
    general = [_chunk(i, source="narrative.pdf") for i in range(6)]
    named = [_chunk(0, source="Project Timeline.docx")]
    cfg = RAGConfig(k=4)
    calls = []

    async def fake_retrieve(kb_uuid, message, model_name, **kwargs):
        calls.append(kwargs)
        if kwargs.get("source_filter"):
            return named, cfg, 0
        return general, cfg, 0

    manifest = [{"name": "Project Timeline.docx", "status": "ready"}]

    with patch.object(kb_validation_service, "_ensure_system_config_loaded",
                      new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(side_effect=fake_retrieve)):
        segment, sources = await chat_service._build_kb_segment(
            "kb-1", "what does the project timeline say?", "test-model",
            manifest=manifest,
        )

    assert len(calls) == 2
    assert calls[1]["source_filter"] == ["Project Timeline.docx"]
    titles = [s["document_title"] for s in sources]
    assert "Project Timeline.docx" in titles
    assert len(sources) == 4


@pytest.mark.asyncio
async def test_get_kb_manifest_resolves_effective_names():
    from types import SimpleNamespace

    from app.services import knowledge_service

    sources = [
        SimpleNamespace(uuid="s1", source_type="document", document_uuid="d1",
                        custom_name=None, url=None, url_title=None, status="ready"),
        SimpleNamespace(uuid="s2", source_type="document", document_uuid="d2",
                        custom_name="My Custom Label", url=None, url_title=None,
                        status="processing"),
        SimpleNamespace(uuid="s3", source_type="url", document_uuid=None,
                        custom_name=None, url="https://x.test/page",
                        url_title="Page Title", status="ready"),
    ]

    with patch.object(knowledge_service, "get_kb_sources",
                      new=AsyncMock(return_value=sources)), \
         patch.object(knowledge_service, "resolve_document_titles",
                      new=AsyncMock(return_value={"d1": "grant_proposal.pdf"})):
        manifest = await knowledge_service.get_kb_manifest("kb-1")

    assert [m["name"] for m in manifest] == [
        "grant_proposal.pdf", "My Custom Label", "Page Title",
    ]
    assert manifest[1]["status"] == "processing"


# ---------------------------------------------------------------------------
# Manifest-aware prompts + numeric/consistency guardrails
# ---------------------------------------------------------------------------


def test_build_manifest_block_lists_names_and_statuses():
    manifest = [
        {"name": "Project Timeline.docx", "status": "ready"},
        {"name": "budget.xlsx", "status": "processing"},
    ]
    block = chat_service._build_manifest_block(manifest)
    assert "## Project Document Manifest" in block
    assert "- Project Timeline.docx" in block
    assert "- budget.xlsx (still indexing)" in block
    assert "isn't part of this project" in block


def test_build_manifest_block_empty_manifest_is_empty():
    assert chat_service._build_manifest_block([]) == ""


def test_build_manifest_block_caps_entries():
    manifest = [{"name": f"doc_{i:03d}.pdf", "status": "ready"} for i in range(70)]
    block = chat_service._build_manifest_block(manifest)
    assert "doc_059.pdf" in block
    assert "doc_060.pdf" not in block
    assert "…and 10 more document(s)" in block


def test_project_kb_empty_prompt_distinguishes_with_manifest():
    from app.services.llm_service import (
        PROJECT_KB_EMPTY_SYSTEM_PROMPT,
        build_project_kb_empty_prompt,
    )

    plain = build_project_kb_empty_prompt(None)
    assert plain == PROJECT_KB_EMPTY_SYSTEM_PROMPT

    block = chat_service._build_manifest_block(
        [{"name": "Project Timeline.docx", "status": "ready"}]
    )
    with_manifest = build_project_kb_empty_prompt(block)
    assert "Project Timeline.docx" in with_manifest
    assert "Not retrieved vs. not in this project" in with_manifest


def test_kb_chat_prompt_has_numeric_and_consistency_guardrails():
    from app.services.llm_service import KB_CHAT_SYSTEM_PROMPT

    assert "Never derive figures" in KB_CHAT_SYSTEM_PROMPT
    assert "Consistency questions" in KB_CHAT_SYSTEM_PROMPT
    assert "same field, period, and unit" in KB_CHAT_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Conversation-aware retrieval query (condense)
# ---------------------------------------------------------------------------


def test_looks_anaphoric_table():
    cases = [
        ("what about year 2?", True),                       # short
        ("And the indirect cost rate?", True),              # short + starter
        ("Compare the Year 1 obligation figures in the budget justification "
         "workbook against the award notice, then summarize any differences.",
         False),                                            # long, self-contained
        ("Summarize what it says about equipment spending across the full "
         "progress report and the final approved budget documents please.",
         True),                                             # long but pronoun
        ("", False),
    ]
    for message, expected in cases:
        assert chat_service._looks_anaphoric(message) is expected, message


def test_recent_turns_flattens_history():
    from pydantic_ai.messages import (
        ModelRequest, ModelResponse, SystemPromptPart, TextPart, UserPromptPart,
    )

    history = [
        ModelRequest(parts=[SystemPromptPart(content="system stuff")]),
        ModelRequest(parts=[UserPromptPart(content="What is the IRB expiration date?")]),
        ModelResponse(parts=[TextPart(content="It expires on 2027-03-01.")]),
    ]
    turns = chat_service._recent_turns(history)
    assert turns == [
        ("user", "What is the IRB expiration date?"),
        ("assistant", "It expires on 2027-03-01."),
    ]


@pytest.mark.asyncio
async def test_condense_retrieval_query_uses_agent_output():
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(
        return_value=_make_mock_run("IRB expiration date renewal year 2", tokens=12),
    )
    with patch.object(kb_validation_service, "_get_or_build_agent",
                      return_value=fake_agent):
        query, tokens = await kb_validation_service.condense_retrieval_query(
            "what about year 2?",
            [("user", "What is the IRB expiration date?"), ("assistant", "2027-03-01.")],
            "test-model",
        )
    assert query == "IRB expiration date renewal year 2"
    assert tokens == 12
    prompt = fake_agent.run.await_args.args[0]
    assert "What is the IRB expiration date?" in prompt
    assert "what about year 2?" in prompt


@pytest.mark.asyncio
async def test_condense_retrieval_query_falls_back_to_keyword_carryover():
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=RuntimeError("model down"))
    with patch.object(kb_validation_service, "_get_or_build_agent",
                      return_value=fake_agent):
        query, tokens = await kb_validation_service.condense_retrieval_query(
            "what about year 2?",
            [("user", "What is the IRB expiration date?"), ("assistant", "2027.")],
            "test-model",
        )
    # Last user turn prepended so retrieval still carries the topic keywords.
    assert query == "What is the IRB expiration date?\nwhat about year 2?"
    assert tokens == 0


@pytest.mark.asyncio
async def test_retrieve_kb_chunks_retrieval_query_overrides_search_text():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[])
    # query_rewriting=True must be skipped when a condensed query is supplied.
    cfg = RAGConfig(k=8, query_rewriting=True)

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent") as get_agent:
        await kb_validation_service.retrieve_kb_chunks(
            "kb-1", "what about year 2?", "test-model", config=cfg,
            retrieval_query="IRB expiration date year 2",
        )

    fake_dm.query_kb.assert_called_once_with(
        "kb-1", "IRB expiration date year 2", 8, 0.0,
    )
    get_agent.assert_not_called()


@pytest.mark.asyncio
async def test_build_kb_segment_condenses_anaphoric_followups():
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

    cfg = RAGConfig(k=4)
    history = [
        ModelRequest(parts=[UserPromptPart(content="What is the IRB expiration date?")]),
        ModelResponse(parts=[TextPart(content="2027-03-01.")]),
    ]
    retrieve = AsyncMock(return_value=([_chunk(0)], cfg, 0))
    condense = AsyncMock(return_value=("IRB expiration date year 2", 0))

    with patch.object(kb_validation_service, "_ensure_system_config_loaded",
                      new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks", new=retrieve), \
         patch.object(kb_validation_service, "condense_retrieval_query", new=condense):
        await chat_service._build_kb_segment(
            "kb-1", "what about year 2?", "test-model", history=history,
        )

    condense.assert_awaited_once()
    assert retrieve.await_args.kwargs["retrieval_query"] == "IRB expiration date year 2"
    # The raw message stays the primary query (answer prompt + rerank target).
    assert retrieve.await_args.args[1] == "what about year 2?"


# ---------------------------------------------------------------------------
# Section-number (identifier) lexical lookup — bare "§ 200.1" style queries
# ---------------------------------------------------------------------------


def test_extract_section_refs_variants():
    assert chat_service._extract_section_refs("What does § 200.1 say?") == ["200.1"]
    assert chat_service._extract_section_refs("explain section 200.512") == ["200.512"]
    assert chat_service._extract_section_refs("compare 200.1 and 200.400") == ["200.1", "200.400"]
    # Dedup, order-preserving.
    assert chat_service._extract_section_refs("§ 200.1 vs 200.1") == ["200.1"]
    # Bare integers / years must not trip it (no dotted part.section token).
    assert chat_service._extract_section_refs("what happened in 2024?") == []
    assert chat_service._extract_section_refs("the $200 cap") == []


def test_get_kb_chunks_containing_uses_where_document():
    from app.services.document_manager import DocumentManager

    dm = object.__new__(DocumentManager)
    fake_collection = MagicMock()
    fake_collection.get = MagicMock(return_value={
        "documents": ["§ 200.1 Definitions ..."],
        "metadatas": [{"source_name": "2 CFR 200"}],
        "ids": ["src_chunk_3"],
    })
    dm.get_kb_collection_readonly = MagicMock(return_value=fake_collection)

    results = dm.get_kb_chunks_containing("kb-1", "200.1", limit=5)

    fake_collection.get.assert_called_once_with(
        where_document={"$contains": "200.1"}, limit=5,
    )
    assert len(results) == 1
    assert results[0]["chunk_id"] == "src_chunk_3"
    assert results[0]["similarity"] is None


@pytest.mark.asyncio
async def test_retrieve_section_chunks_filters_substring_false_positives():
    """A "$contains: 200.1" candidate pool would also match "200.10"; the
    word-boundary post-filter must keep only exact section hits."""
    candidates = [
        {"content": "§ 200.1 Definitions apply here.", "chunk_id": "c1",
         "metadata": {"source_name": "2 CFR 200"}, "score": None, "similarity": None},
        {"content": "§ 200.10 U.S. Federal awarding agency.", "chunk_id": "c2",
         "metadata": {"source_name": "2 CFR 200"}, "score": None, "similarity": None},
    ]
    fake_dm = MagicMock()
    fake_dm.get_kb_chunks_containing = MagicMock(return_value=candidates)

    with patch("app.services.document_manager.get_document_manager",
               return_value=fake_dm):
        out = await chat_service._retrieve_section_chunks("kb-1", ["200.1"])

    ids = [r["chunk_id"] for r in out]
    assert ids == ["c1"], "200.10 must not be returned for a 200.1 lookup"


@pytest.mark.asyncio
async def test_build_kb_segment_answers_section_only_query_when_semantic_empty():
    """A bare "§ 200.1" retrieves nothing semantically (gated by the floor),
    but the lexical section lookup must still surface the chunk so chat can
    answer instead of abstaining."""
    cfg = RAGConfig(k=4)
    section_hit = _chunk(0, source="2 CFR 200")

    with patch.object(kb_validation_service, "_ensure_system_config_loaded",
                      new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(return_value=([], cfg, 0))), \
         patch.object(chat_service, "_retrieve_section_chunks",
                      new=AsyncMock(return_value=[section_hit])):
        segment, sources = await chat_service._build_kb_segment(
            "kb-1", "What does § 200.1 say?", "test-model",
        )

    assert segment is not None
    assert len(sources) == 1
    assert sources[0]["document_title"] == "2 CFR 200"


# ---------------------------------------------------------------------------
# Multi-question fan-out — several questions in one message must not starve
# ---------------------------------------------------------------------------


def test_split_questions_only_fans_out_on_multiple():
    assert chat_service._split_questions("Just one question?") == []
    assert chat_service._split_questions("No question mark here") == []
    two = chat_service._split_questions(
        "What is a non-Federal entity? And what does § 200.1 cover?"
    )
    assert two == [
        "What is a non-Federal entity?",
        "And what does § 200.1 cover?",
    ]


def test_round_robin_merge_interleaves_and_dedupes():
    a = [_chunk(0, source="A"), _chunk(1, source="A")]
    b = [_chunk(0, source="B"), _chunk(1, source="B")]
    shared = _chunk(0, source="A")
    c = [shared, shared]  # duplicate chunk_id within a pool

    merged = chat_service._round_robin_merge([a, b, c])
    ids = [r["chunk_id"] for r in merged]
    # First tier is one chunk from each pool before any pool's second chunk.
    assert ids[0] == "src-A_chunk_0"
    assert ids[1] == "src-B_chunk_0"
    assert len(ids) == len(set(ids)), "duplicates must be dropped"


@pytest.mark.asyncio
async def test_build_kb_segment_fans_out_per_question():
    """Two questions in one turn each get their own retrieval and fair
    representation in the composed top-k."""
    cfg = RAGConfig(k=4)
    q1_pool = [_chunk(i, source="entity.txt") for i in range(4)]
    q2_pool = [_chunk(i, source="section.txt") for i in range(4)]
    calls = []

    async def fake_retrieve(kb_uuid, message, model_name, **kwargs):
        calls.append(message)
        return (q1_pool if "non-Federal" in message else q2_pool), cfg, 0

    msg = "What does 'non-Federal entity' mean? What does § 200.400 cover?"
    with patch.object(kb_validation_service, "_ensure_system_config_loaded",
                      new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(side_effect=fake_retrieve)), \
         patch.object(chat_service, "_retrieve_section_chunks",
                      new=AsyncMock(return_value=[])):
        segment, sources = await chat_service._build_kb_segment(
            "kb-1", msg, "test-model",
        )

    # One retrieval per sub-question (no whole-message blend).
    assert len(calls) == 2
    titles = {s["document_title"] for s in sources}
    assert titles == {"entity.txt", "section.txt"}, (
        "both questions must contribute chunks"
    )
