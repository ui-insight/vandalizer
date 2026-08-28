"""Tests for the shared KB retrieval pipeline (``retrieve_kb_chunks``) and the
chat-side segment builder (``_build_kb_segment``).

These guard the "tuned config actually applies on the live path" seam: the
optimizer stores k / min_similarity / rerank / query_rewriting per KB, and both
the validation harness and streaming chat must route retrieval through the
same pipeline.
"""

import re
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
# Lexical pinning — literal strings the embedding barely represents: "§ 200.1",
# "CSU-PI-001", a quoted or questioned phrase
# ---------------------------------------------------------------------------


def test_extract_pin_terms_section_variants():
    assert chat_service._extract_pin_terms("What does § 200.1 say?") == ["200.1"]
    assert chat_service._extract_pin_terms("explain section 200.512") == ["200.512"]
    # A prefix pair on purpose: "200.1" is a text prefix of "200.10", and both
    # are separate lookups the user asked for. The retrieval-side post-filter
    # keeps them apart; extraction must not conflate them in the first place.
    assert chat_service._extract_pin_terms("compare 200.1 and 200.10") == ["200.1", "200.10"]
    assert chat_service._extract_pin_terms(
        "Compare section 200.1 with 200.512 and 200.1a."
    ) == ["200.1", "200.512", "200.1a"]
    # Dedup, order-preserving.
    assert chat_service._extract_pin_terms("§ 200.1 vs 200.1") == ["200.1"]
    # Bare integers / years must not trip it (no dotted part.section token).
    assert chat_service._extract_pin_terms("what happened in 2024?") == []
    assert chat_service._extract_pin_terms("the $200 cap") == []


def test_extract_pin_terms_identifier_shapes():
    """Role, award and form identifiers are what near-duplicate documents
    differ by, and they carry almost no weight in a mean-pooled bi-encoder."""
    assert chat_service._extract_pin_terms(
        "Where did CSU-PI-001 earn the Ph.D. credential, and in what field?"
    ) == ["CSU-PI-001"]
    assert chat_service._extract_pin_terms(
        "Award NSF-2024-117 and form OMB-3145-0279"
    ) == ["NSF-2024-117", "OMB-3145-0279"]
    # Identifier counterpart of the section prefix pair: one identifier being a
    # text prefix of another must not suppress the longer one.
    assert chat_service._extract_pin_terms(
        "Is CSU-PI-001 the same as CSU-PI-0012?"
    ) == ["CSU-PI-001", "CSU-PI-0012"]
    assert chat_service._extract_pin_terms("Do AA-1 and AA-11 both apply?") == [
        "AA-1", "AA-11",
    ]
    # Hyphen *and* a digit are both required, so capitalised words and
    # hyphenated prose stay out of the lane.
    for prose in (
        "Tell me about cost-sharing and NSF-funded work with the Co-PI.",
        "What did the CHIPS and Science Act require?",
        "Send an e-mail to the PI about the well-known issue.",
        # Hyphenated and upper-case, but carrying no digit — the digit is what
        # separates an identifier from a shouted phrase.
        "Compare the ABC-DEF and GHI-JKL sections.",
        # Lower-case is deliberately out of scope: matching it would mean
        # pinning ordinary hyphenated prose, and `$contains` is case-sensitive
        # anyway, so a lower-cased identifier would not match the stored text.
        "where did csu-pi-001 study?",
    ):
        assert chat_service._extract_pin_terms(prose) == [], prose


def test_extract_pin_terms_quoted_and_questioned_phrases():
    # An explicitly quoted string is a "find me this" instruction.
    assert chat_service._extract_pin_terms(
        'Find "Data Management Plan" for me'
    ) == ["Data Management Plan"]
    # The noun phrase a definitional question asks about, minus the count.
    assert chat_service._extract_pin_terms(
        "What are the three field sites?"
    ) == ["field sites"]
    assert chat_service._extract_pin_terms("What is the total budget?") == ["total budget"]


def test_questioned_phrase_stops_at_the_first_function_word():
    """"the name of the vendor" is not asking for the string "name of the".

    A phrase allowed to run through "of"/"for"/"between" is a fragment of
    English, not a string worth looking for — and on a small knowledge base,
    where the hit cut-off can never fire, pinning one fills the lane with every
    chunk that happens to contain it and displaces genuinely relevant chunks.
    """
    for prose in (
        "What is the name of the vendor?",
        "What is the status of the review?",
        "What is the deadline for the submission?",
        "What was the outcome of the audit?",
        "What is the address of the office?",
        "What is the main goal of this project?",
        "What is the difference between direct and indirect costs?",
        "What are my options here?",
    ):
        assert chat_service._extract_pin_terms(prose) == [], prose
    # A genuine noun phrase still survives, truncated at the function word that
    # ends it rather than dropped.
    assert chat_service._extract_pin_terms(
        "What is the effective date of the agreement?"
    ) == ["effective date"]
    assert chat_service._extract_pin_terms(
        "Which is the correct form to use?"
    ) == ["correct form"]


def test_extract_pin_terms_shouted_phrase_and_hyphenless_code():
    """Support ticket: "SCARLET ALBATROSS CLOSEOUT 9928" appears once in an
    indexed document and could not be found, while "SPC-0500" in the same
    document was found at once. The hyphenated code pinned; the shouted
    marker did not, so it went to semantic search alone, which scores such
    a string as noise."""
    assert chat_service._extract_pin_terms(
        "Where does SCARLET ALBATROSS CLOSEOUT 9928 appear?"
    ) == ["SCARLET ALBATROSS CLOSEOUT 9928"]
    assert chat_service._extract_pin_terms("SCARLET ALBATROSS CLOSEOUT 9928") == [
        "SCARLET ALBATROSS CLOSEOUT 9928"
    ]
    assert chat_service._extract_pin_terms(
        "find the PHASE II FINAL REPORT section"
    ) == ["PHASE II FINAL REPORT"]
    # Hyphenless codes: letters + digits, five or more characters.
    assert chat_service._extract_pin_terms("What is SPC0500?") == ["SPC0500"]
    assert chat_service._extract_pin_terms("look up R01CA123456 please") == ["R01CA123456"]
    # Both shapes in one message, both pinned, in message order.
    assert chat_service._extract_pin_terms(
        "Is SPC-0500 near SCARLET ALBATROSS CLOSEOUT 9928?"
    ) == ["SPC-0500", "SCARLET ALBATROSS CLOSEOUT 9928"]
    # A shouted run that wraps an already-pinned code is not pinned twice.
    assert chat_service._extract_pin_terms("SPC0500 CLOSEOUT") == ["SPC0500"]
    # Nor is the hyphenless stem of a hyphenated award number.
    assert chat_service._extract_pin_terms("Find R01CA123456-01A1 budget") == [
        "R01CA123456-01A1"
    ]


def test_extract_pin_terms_shouted_phrase_negatives():
    """Capitals in ordinary prose — an acronym, a two-letter word, a single
    shouted word, a year, a dollar amount — must not form a run."""
    for prose in (
        "What did the CHIPS and Science Act require?",
        "Does NSF allow this?",
        "I AM not sure about the PI.",
        "Compare the ABC-DEF and GHI-JKL sections.",
        "The budget was 2024 dollars, about $5000.",
        "Is the US a party to it?",
        "READ this carefully",
        # Lower / mixed case is out of scope for this channel — that is what
        # quoting is for.
        "where does scarlet albatross closeout 9928 appear?",
        "Where does Scarlet Albatross Closeout 9928 appear?",
        # A regulation citation is not a shouted run ("CFR 200" / "CFR 46").
        "What does 2 CFR 200 say about equipment?",
        "Is 45 CFR 46 the Common Rule?",
    ):
        assert chat_service._extract_pin_terms(prose) == [], prose
    assert chat_service._extract_pin_terms("What does 2 CFR 200.313 say?") == ["200.313"]
    # An acronym pair is a run by shape; it is harmless (the hit cap bounds
    # it) and deliberately not special-cased.
    assert chat_service._extract_pin_terms("NSF NIH policies") == ["NSF NIH"]
    # Four-character mixes stay out: "R01" fragments and form stems are too
    # common to spend lane slots on.
    assert chat_service._extract_pin_terms("the R01 mechanism and SF42") == []


@pytest.mark.asyncio
async def test_retrieve_pinned_chunks_tries_upper_case_variant_for_phrases():
    """``$contains`` is case-sensitive and a marker line is usually in
    capitals on the page, so a phrase is also looked up upper-cased."""
    fake_dm = MagicMock()
    fake_dm.get_kb_chunks_containing = MagicMock(return_value=[])
    with patch("app.services.document_manager.get_document_manager", return_value=fake_dm):
        await chat_service._retrieve_pinned_chunks("kb-1", ["scarlet albatross closeout 9928"])
    tried = [c.args[1] for c in fake_dm.get_kb_chunks_containing.call_args_list]
    assert "SCARLET ALBATROSS CLOSEOUT 9928" in tried
    assert "scarlet albatross closeout 9928" in tried


def test_project_kb_empty_prompt_forbids_claiming_text_is_not_indexed():
    """The assistant told a user the marker line "is not part of the
    searchable content". It was. Retrieval returning nothing is a fact about
    the search; the prompt must say that and forbid the stronger claim."""
    from app.services.llm_service import build_project_kb_empty_prompt

    prompt = build_project_kb_empty_prompt()
    assert "Never claim that a phrase, line, or fact is absent" in prompt
    assert "not part of the searchable content" in prompt  # named as the forbidden phrasing
    assert "double quotes" in prompt
    assert "no relevant content" not in prompt


def test_extract_pin_terms_drops_a_phrase_wrapping_a_pinned_term():
    """One concept must not spend two of the four slots — and four extra
    case-variant lookups — just because the question names it twice."""
    assert chat_service._extract_pin_terms(
        "What is CSU-COI-001's nine-month institutional base salary?"
    ) == ["CSU-COI-001"]
    assert chat_service._extract_pin_terms("What is the CO-PI-1 role?") == ["CO-PI-1"]
    # The questioned phrase here would carry literal quote characters, which
    # could never match stored text.
    assert chat_service._extract_pin_terms(
        'What is the "force majeure" clause?'
    ) == ["force majeure"]


def test_questioned_phrase_needs_a_question_frame():
    """"what/which is" mid-sentence is a relative clause, not a question.

    Unanchored, "Summarize the section which is most important for
    compliance" pinned "most important" — a junk bigram that, on a small
    knowledge base where the hit cut-off cannot fire, spends up to half the
    lane on whatever chunks happen to contain it.
    """
    for prose in (
        "Summarize the section which is most important for compliance",
        "Explain the clause that says what is allowable cost here",
        "List the vendors and note which are preferred suppliers today",
        "Tell me what is the total budget",
    ):
        assert chat_service._extract_pin_terms(prose) == [], prose
    # The frame still fires when it opens a sentence: at the start of the
    # message, after a sentence boundary, or behind a connective.
    assert chat_service._extract_pin_terms("what is the total budget") == ["total budget"]
    assert chat_service._extract_pin_terms(
        "Explain the budget. What are the field sites?"
    ) == ["field sites"]
    assert chat_service._extract_pin_terms(
        "Thanks. So, what is the total budget?"
    ) == ["total budget"]
    assert chat_service._extract_pin_terms(
        "First question: which is the correct form to use?"
    ) == ["correct form"]


def test_extract_pin_terms_ignores_plain_prose():
    """Ordinary requests must pin nothing — the lane costs half the top-k."""
    for prose in (
        "Summarize this document for me.",
        "Can you give me an overview of the project and its goals?",
        "What are you?",
        "What is this about?",
        "I don't know what isn't covered here",
        "Please compare the two budgets and explain the difference.",
        "",
    ):
        assert chat_service._extract_pin_terms(prose) == [], prose


def test_extract_pin_terms_capped_per_turn():
    msg = "Compare AAA-001, BBB-002, CCC-003, DDD-004 and EEE-005."
    assert chat_service._extract_pin_terms(msg) == [
        "AAA-001", "BBB-002", "CCC-003", "DDD-004",
    ]


def test_extract_pin_terms_does_not_cap_cited_sections():
    """The cap is on *inferred* terms. Five sections cited by hand are five
    deliberate lookups, and dropping the fifth would regress the CFR feature
    this lane originally shipped for."""
    assert chat_service._extract_pin_terms(
        "Compare 200.1, 200.2, 200.3, 200.4 and 200.5"
    ) == ["200.1", "200.2", "200.3", "200.4", "200.5"]


def test_rank_pinned_chunks_orders_by_mentions_then_position():
    """``get_kb_chunks_containing`` returns ChromaDB storage order, which is
    arbitrary. With more hits than pin slots, ordering decides whether the
    chunk the user asked about reaches the context at all."""
    chunks = [
        {"chunk_id": "passing", "content": "x" * 400 + " CSU-PI-001 was consulted."},
        {"chunk_id": "about", "content": "Biographical Sketch - CSU-PI-001\nNAME: CSU-PI-001"},
        {"chunk_id": "late-single", "content": "y" * 800 + " CSU-PI-001"},
        {"chunk_id": "early-single", "content": "CSU-PI-001 leads the work. " + "z" * 500},
    ]
    ranked = chat_service._rank_pinned_chunks(chunks, re.compile("CSU-PI-001"))

    assert [c["chunk_id"] for c in ranked] == [
        "about",          # two mentions, first at offset 0
        "early-single",   # one mention, offset 0
        "passing",        # one mention, offset 400
        "late-single",    # one mention, offset 800
    ]


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
async def test_retrieve_pinned_chunks_filters_substring_false_positives():
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
        out = await chat_service._retrieve_pinned_chunks("kb-1", ["200.1"])

    ids = [r["chunk_id"] for r in out]
    assert ids == ["c1"], "200.10 must not be returned for a 200.1 lookup"


@pytest.mark.asyncio
async def test_retrieve_pinned_chunks_tries_phrase_capitalisations():
    """ChromaDB's ``$contains`` is case-sensitive, so a phrase lifted from
    lower-case prose has to be looked up the way a heading would write it."""
    hits = {
        "Field sites": [{"content": "## 5.4 Field sites and reference sampling",
                         "chunk_id": "c32", "metadata": {"source_name": "desc.pdf"},
                         "score": None, "similarity": None}],
    }
    fake_dm = MagicMock()
    fake_dm.get_kb_chunks_containing = MagicMock(
        side_effect=lambda kb, sub, limit: hits.get(sub, []))

    with patch("app.services.document_manager.get_document_manager",
               return_value=fake_dm):
        out = await chat_service._retrieve_pinned_chunks("kb-1", ["field sites"])

    tried = [c.args[1] for c in fake_dm.get_kb_chunks_containing.call_args_list]
    assert "field sites" in tried and "Field sites" in tried
    assert [r["chunk_id"] for r in out] == ["c32"]


@pytest.mark.asyncio
async def test_retrieve_pinned_chunks_skips_boilerplate_identifier():
    """A project number stamped in every running header points nowhere; pinning
    an arbitrary handful of its hits would just cost the semantic pool slots.
    A section number the user cited explicitly stays exempt."""
    many = [
        {"content": f"CSU-NSF-001 header {i} — § 200.1 applies.", "chunk_id": f"c{i}",
         "metadata": {"source_name": "doc.pdf"}, "score": None, "similarity": None}
        for i in range(chat_service._MAX_PIN_TERM_HITS + 1)
    ]
    fake_dm = MagicMock()
    fake_dm.get_kb_chunks_containing = MagicMock(return_value=many)

    with patch("app.services.document_manager.get_document_manager",
               return_value=fake_dm):
        boilerplate = await chat_service._retrieve_pinned_chunks("kb-1", ["CSU-NSF-001"])
        cited = await chat_service._retrieve_pinned_chunks("kb-1", ["200.1"])

    assert boilerplate == []
    assert len(cited) == 6, "an explicitly cited section still pins"


@pytest.mark.asyncio
async def test_retrieve_pinned_chunks_counts_exact_hits_not_the_substring_pool():
    """The boilerplate cut-off must measure exact hits, not raw candidates.

    ``$contains "AA-1"`` also returns every "AA-11" chunk. Counting those
    discarded "AA-1" outright when it had two genuine hits — the SF-424 /
    SF-424A shape this product sees in every packet.
    """
    variants = [
        {"content": f"AA-11 running header {i}.", "chunk_id": f"v{i}",
         "metadata": {"source_name": "doc.pdf"}, "score": None, "similarity": None}
        for i in range(chat_service._MAX_PIN_TERM_HITS - 1)
    ]
    genuine = [
        {"content": "Form AA-1 is the base attachment.", "chunk_id": "g1",
         "metadata": {"source_name": "doc.pdf"}, "score": None, "similarity": None},
        {"content": "Submit AA-1 with the cover sheet.", "chunk_id": "g2",
         "metadata": {"source_name": "doc.pdf"}, "score": None, "similarity": None},
    ]
    fake_dm = MagicMock()
    fake_dm.get_kb_chunks_containing = MagicMock(return_value=variants + genuine)

    with patch("app.services.document_manager.get_document_manager",
               return_value=fake_dm):
        out = await chat_service._retrieve_pinned_chunks("kb-1", ["AA-1"])

    assert sorted(r["chunk_id"] for r in out) == ["g1", "g2"]
    # The pool is fetched wider than the cap so exact hits buried under their
    # own variants can be reached at all.
    assert fake_dm.get_kb_chunks_containing.call_args.args[2] > chat_service._MAX_PIN_TERM_HITS


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
         patch.object(chat_service, "_retrieve_pinned_chunks",
                      new=AsyncMock(return_value=[section_hit])):
        segment, sources = await chat_service._build_kb_segment(
            "kb-1", "What does § 200.1 say?", "test-model",
        )

    assert segment is not None
    assert len(sources) == 1
    assert sources[0]["document_title"] == "2 CFR 200"


@pytest.mark.asyncio
async def test_build_kb_segment_pins_identifier_chunk_the_vector_pool_missed():
    """The regression this lane exists for: two near-identical documents that
    differ only by a role identifier. The bi-encoder ranks the wrong one first
    and the right one nowhere near the top-k, so the chunk that literally names
    the identifier has to be pinned in."""
    cfg = RAGConfig(k=8)
    pool = [_chunk(i, source="11_Biographical_Sketch_CoPI.pdf") for i in range(8)]
    answer = _chunk(0, source="10_Biographical_Sketch_PI.pdf")

    async def fake_pin(kb_uuid, terms, **kwargs):
        assert terms == ["CSU-PI-001"]
        return [answer]

    with patch.object(kb_validation_service, "_ensure_system_config_loaded",
                      new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(return_value=(pool, cfg, 0))), \
         patch.object(chat_service, "_retrieve_pinned_chunks",
                      new=AsyncMock(side_effect=fake_pin)):
        segment, sources = await chat_service._build_kb_segment(
            "kb-1",
            "Where did CSU-PI-001 earn the Ph.D. credential, and in what field?",
            "test-model",
        )

    assert segment is not None
    assert sources[0]["document_title"] == "10_Biographical_Sketch_PI.pdf", (
        "the pinned chunk takes the first slot"
    )
    assert len(sources) == cfg.k, "the top-k is still filled to k"
    # The pin costs exactly one slot: the vector pool keeps the other seven,
    # in its own order, minus the one it lost.
    assert [s["chunk_id"] for s in sources[1:]] == [
        c["chunk_id"] for c in pool[: cfg.k - 1]
    ]


@pytest.mark.asyncio
async def test_build_kb_segment_leaves_prose_turns_on_the_vector_path():
    """No-regression: a turn with nothing pin-shaped in it must not touch the
    lexical lane, and its context must be exactly the vector top-k."""
    cfg = RAGConfig(k=4)
    pool = [_chunk(i) for i in range(4)]
    pin = AsyncMock(return_value=[])

    with patch.object(kb_validation_service, "_ensure_system_config_loaded",
                      new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(return_value=(pool, cfg, 0))), \
         patch.object(chat_service, "_retrieve_pinned_chunks", new=pin):
        _, sources = await chat_service._build_kb_segment(
            "kb-1", "Summarize this project for me.", "test-model",
        )

    pin.assert_not_awaited()
    assert [s["chunk_id"] for s in sources] == [c["chunk_id"] for c in pool]


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
         patch.object(chat_service, "_retrieve_pinned_chunks",
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


# ---------------------------------------------------------------------------
# Citations must carry an openable document, so a reader can check the page
# ---------------------------------------------------------------------------


def _find_returning(items):
    """Stand in for ``Model.find(query).to_list()``."""
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=items)
    return MagicMock(return_value=cursor)


@pytest.mark.asyncio
async def test_resolve_openable_documents_maps_live_document_sources():
    from types import SimpleNamespace

    from app.services import knowledge_service

    sources = [
        SimpleNamespace(uuid="s1", source_type="document", document_uuid="d1"),
        SimpleNamespace(uuid="s2", source_type="url", document_uuid=None),
        SimpleNamespace(uuid="s3", source_type="document", document_uuid="gone"),
    ]
    docs = [SimpleNamespace(uuid="d1")]

    with patch.object(knowledge_service, "KnowledgeBaseSource") as kbs, \
         patch.object(knowledge_service, "SmartDocument") as sd:
        kbs.find = _find_returning(sources)
        sd.find = _find_returning(docs)
        mapping = await knowledge_service.resolve_openable_documents(
            ["s1", "s2", "s3"],
        )
        doc_query = sd.find.call_args.args[0]

    # URL sources and sources whose document is gone stay preview-only.
    assert mapping == {"s1": "d1"}
    # A deleted document must never be offered as openable.
    assert doc_query["soft_deleted"] == {"$ne": True}


@pytest.mark.asyncio
async def test_resolve_openable_documents_drops_documents_the_reader_cannot_view():
    """Membership is checked against whoever *added* a document to the KB.

    A KB shared with a team can therefore hold sources pointing at another
    member's personal-space documents, which only their owner may view. Offering
    "open" on one produces a 404 from the download endpoint, so it must not be
    offered at all.
    """
    from types import SimpleNamespace

    from app.services import knowledge_service

    sources = [
        SimpleNamespace(uuid="s1", source_type="document", document_uuid="mine"),
        SimpleNamespace(uuid="s2", source_type="document", document_uuid="theirs"),
    ]
    docs = [SimpleNamespace(uuid="mine"), SimpleNamespace(uuid="theirs")]
    reader = SimpleNamespace(user_id="bob")

    with patch.object(knowledge_service, "KnowledgeBaseSource") as kbs, \
         patch.object(knowledge_service, "SmartDocument") as sd, \
         patch.object(knowledge_service, "User") as user_model, \
         patch.object(knowledge_service, "access_control") as ac:
        kbs.find = _find_returning(sources)
        sd.find = _find_returning(docs)
        user_model.find_one = AsyncMock(return_value=reader)
        user_model.user_id = MagicMock()
        ac.get_team_access_context = AsyncMock(return_value=SimpleNamespace())
        ac.can_view_document = MagicMock(side_effect=lambda d, u, t: d.uuid == "mine")

        mapping = await knowledge_service.resolve_openable_documents(
            ["s1", "s2"], user_id="bob"
        )

    assert mapping == {"s1": "mine"}


@pytest.mark.asyncio
async def test_resolve_openable_documents_without_a_reader_skips_the_access_check():
    """Callers with no reader in scope get the unfiltered mapping — and must
    not pay for a User lookup they cannot use."""
    from types import SimpleNamespace

    from app.services import knowledge_service

    sources = [SimpleNamespace(uuid="s1", source_type="document", document_uuid="d1")]

    with patch.object(knowledge_service, "KnowledgeBaseSource") as kbs, \
         patch.object(knowledge_service, "SmartDocument") as sd, \
         patch.object(knowledge_service, "User") as user_model:
        kbs.find = _find_returning(sources)
        sd.find = _find_returning([SimpleNamespace(uuid="d1")])
        user_model.find_one = AsyncMock()

        assert await knowledge_service.resolve_openable_documents(["s1"]) == {"s1": "d1"}
        user_model.find_one.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_openable_documents_denies_everything_for_an_unknown_reader():
    from types import SimpleNamespace

    from app.services import knowledge_service

    sources = [SimpleNamespace(uuid="s1", source_type="document", document_uuid="d1")]

    with patch.object(knowledge_service, "KnowledgeBaseSource") as kbs, \
         patch.object(knowledge_service, "SmartDocument") as sd, \
         patch.object(knowledge_service, "User") as user_model:
        kbs.find = _find_returning(sources)
        sd.find = _find_returning([SimpleNamespace(uuid="d1")])
        user_model.find_one = AsyncMock(return_value=None)
        user_model.user_id = MagicMock()

        assert await knowledge_service.resolve_openable_documents(
            ["s1"], user_id="ghost"
        ) == {}


@pytest.mark.asyncio
async def test_refresh_openable_citations_drops_a_uuid_that_no_longer_resolves():
    """document_uuid is stamped at answer time, so a conversation reopened after
    the document was deleted (or shared away) would still offer a dead "open"."""
    from app.routers import chat as chat_router

    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "there", "citations": [
            {"document_id": "s1", "document_uuid": "stale", "page": 3},
            {"document_id": "s2", "page": 4},
            {"page": 5},
        ]},
    ]

    with patch("app.services.knowledge_service.resolve_openable_documents",
               new=AsyncMock(return_value={"s2": "live"})) as resolver:
        await chat_router._refresh_openable_citations(messages, "bob")

    resolver.assert_awaited_once()
    assert resolver.await_args.kwargs["user_id"] == "bob"

    cites = messages[1]["citations"]
    # Resolved now -> gains the affordance, even though it was stored without one.
    assert cites[1]["document_uuid"] == "live"
    # No longer resolvable -> the stale affordance is withdrawn, not left to 404.
    assert "document_uuid" not in cites[0]
    # A citation with no source at all is untouched.
    assert cites[2] == {"page": 5}


@pytest.mark.asyncio
async def test_refresh_openable_citations_is_never_fatal():
    """Reading a conversation must not fail over a display nicety."""
    from app.routers import chat as chat_router

    messages = [{"role": "assistant", "content": "x", "citations": [
        {"document_id": "s1", "document_uuid": "keep"},
    ]}]

    with patch("app.services.knowledge_service.resolve_openable_documents",
               new=AsyncMock(side_effect=RuntimeError("mongo down"))):
        await chat_router._refresh_openable_citations(messages, "bob")

    # Left exactly as stored rather than half-rewritten.
    assert messages[0]["citations"][0]["document_uuid"] == "keep"

    # Nothing citable -> no round trip.
    with patch("app.services.knowledge_service.resolve_openable_documents",
               new=AsyncMock()) as resolver:
        await chat_router._refresh_openable_citations([{"role": "user"}], "bob")
        resolver.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_openable_documents_is_never_fatal():
    from app.services import knowledge_service

    with patch.object(knowledge_service, "KnowledgeBaseSource") as kbs:
        kbs.find = MagicMock(side_effect=RuntimeError("no mongo here"))
        assert await knowledge_service.resolve_openable_documents(["s1"]) == {}

    # No ids -> no round trip at all.
    with patch.object(knowledge_service, "KnowledgeBaseSource") as kbs:
        kbs.find = MagicMock()
        assert await knowledge_service.resolve_openable_documents([]) == {}
        kbs.find.assert_not_called()


@pytest.mark.asyncio
async def test_build_kb_segment_attaches_openable_document_uuid():
    """Citations carry the document behind them so the UI can offer "open at
    the cited page" — page numbers are a heuristic, and verifying one means
    reading the document, not the chunk we already showed."""
    chunks = [_chunk(0, source="proposal.pdf", page=12),
              _chunk(1, source="policy.html")]
    cfg = RAGConfig(k=2)

    with patch.object(kb_validation_service, "_ensure_system_config_loaded",
                      new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(return_value=(chunks, cfg, 0))), \
         patch("app.services.knowledge_service.resolve_openable_documents",
               new=AsyncMock(return_value={"src-proposal.pdf": "doc-1"})):
        _, sources = await chat_service._build_kb_segment(
            "kb-1", "q?", "test-model",
        )

    assert sources[0]["document_uuid"] == "doc-1"
    # Nothing openable behind the second source — the key is simply absent, so
    # old stored citations and URL sources look the same to the UI.
    assert "document_uuid" not in sources[1]


@pytest.mark.asyncio
async def test_kb_segment_explains_the_tilde_when_a_page_is_estimated():
    """The hedged label does not survive the model on its own.

    An unexplained tilde gets normalised away and the estimate is restated as
    fact — measured five times out of five at temperature 0 on a fully
    interpolated document, which is why ``page_note_for`` rules out exactness
    by name for document chat. KB chat puts the same ``p. ~N`` labels in front
    of the model, so it needs the same instruction.
    """
    chunks = [_chunk(0, source="scanned.pdf", page=234, page_approximate=True)]
    cfg = RAGConfig(k=1)

    with patch.object(kb_validation_service, "_ensure_system_config_loaded",
                      new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(return_value=(chunks, cfg, 0))), \
         patch("app.services.knowledge_service.resolve_openable_documents",
               new=AsyncMock(return_value={})):
        segment, sources = await chat_service._build_kb_segment(
            "kb-1", "q?", "test-model",
        )

    assert segment is not None
    assert "scanned.pdf (p. ~234)" in segment.text
    assert "estimate" in segment.text, (
        "the model was shown a tilde with nothing explaining it"
    )
    assert "explicitly" in segment.text, (
        "asserting exactness was not ruled out by name, which is the failure "
        "that was actually measured"
    )
    assert sources[0]["page_approximate"] is True


@pytest.mark.asyncio
async def test_kb_segment_stays_quiet_when_every_page_is_measured():
    """A rule about estimated pages has no business in front of a model that
    is not being shown any."""
    chunks = [_chunk(0, source="digital.pdf", page=12)]
    cfg = RAGConfig(k=1)

    with patch.object(kb_validation_service, "_ensure_system_config_loaded",
                      new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(return_value=(chunks, cfg, 0))), \
         patch("app.services.knowledge_service.resolve_openable_documents",
               new=AsyncMock(return_value={})):
        segment, _ = await chat_service._build_kb_segment(
            "kb-1", "q?", "test-model",
        )

    assert segment is not None
    assert "digital.pdf (p. 12)" in segment.text
    assert "estimate" not in segment.text
