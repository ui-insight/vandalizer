"""Tests for KBQuestionGenerator — chunk sampling, output parsing, KB rejection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import kb_question_generator
from app.services.kb_question_generator import KBQuestionGenerator


def _make_source(uuid="src-1", name="Doc A", chunk_count=3):
    s = MagicMock()
    s.uuid = uuid
    s.url_title = name
    s.url = None
    s.document_uuid = uuid
    s.chunk_count = chunk_count
    return s


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------


def test_parse_questions_filters_invented_sources_and_chunk_ids():
    raw = {"questions": [
        {
            "query": "What is the Q1 deadline?",
            "expected_answer": "March 15.",
            "expected_source_labels": ["Schedule", "Hallucinated Source"],
            "source_chunk_ids": ["src-1_chunk_0", "made_up_id"],
            "category": "factual",
        },
        {
            # Empty query — must be filtered.
            "query": "",
            "expected_answer": "Foo",
        },
        {
            "query": "Describe the budget.",
            "expected_answer": "$1.2M annually.",
            "expected_source_labels": [],
            "source_chunk_ids": [],
            "category": "summary",
        },
    ]}
    out = KBQuestionGenerator._parse_questions(
        raw,
        valid_source_names={"Schedule 2025", "Budget Doc"},
        provided_chunk_ids={"src-1_chunk_0"},
    )
    assert len(out) == 2
    assert out[0]["query"] == "What is the Q1 deadline?"
    assert out[0]["expected_source_labels"] == ["Schedule"]  # "Hallucinated Source" stripped
    assert out[0]["source_chunk_ids"] == ["src-1_chunk_0"]   # "made_up_id" stripped
    assert out[1]["category"] == "summary"


def test_parse_questions_normalises_invalid_category():
    raw = {"questions": [{
        "query": "Q?", "expected_answer": "A.", "category": "wibble",
    }]}
    out = KBQuestionGenerator._parse_questions(raw, set(), set())
    assert out[0]["category"] == "factual"


def test_parse_questions_handles_list_at_top_level():
    raw = [
        {"query": "Q1", "expected_answer": "A1"},
        {"query": "Q2", "expected_answer": "A2"},
    ]
    out = KBQuestionGenerator._parse_questions(raw, set(), set())
    assert len(out) == 2


# ---------------------------------------------------------------------------
# Chunk sampling
# ---------------------------------------------------------------------------


def test_sample_chunks_pulls_one_per_source_and_random_extras():
    sources = [
        _make_source("src-1", "Doc A", chunk_count=10),
        _make_source("src-2", "Doc B", chunk_count=2),
    ]

    fake_collection = MagicMock()
    # Anchor chunks: per-source .get(where=...)
    def fake_get(where=None, limit=None, **kw):
        if where and where.get("source_id") == "src-1":
            return {
                "ids": ["src-1_chunk_0"],
                "documents": ["Anchor for Doc A " * 5],
                "metadatas": [{"source_id": "src-1", "source_name": "Doc A"}],
            }
        if where and where.get("source_id") == "src-2":
            return {
                "ids": ["src-2_chunk_0"],
                "documents": ["Anchor for Doc B"],
                "metadatas": [{"source_id": "src-2", "source_name": "Doc B"}],
            }
        # No where clause → pool fetch for random extras
        return {
            "ids": ["src-1_chunk_3", "src-2_chunk_1", "src-1_chunk_0"],  # last is dup
            "documents": ["extra1", "extra2", "dup"],
            "metadatas": [
                {"source_id": "src-1", "source_name": "Doc A"},
                {"source_id": "src-2", "source_name": "Doc B"},
                {"source_id": "src-1", "source_name": "Doc A"},
            ],
        }

    fake_collection.get = fake_get
    fake_dm = MagicMock()
    fake_dm.get_kb_collection = MagicMock(return_value=fake_collection)

    with patch.object(kb_question_generator, "_get_dm", return_value=fake_dm):
        sampled = KBQuestionGenerator._sample_chunks("kb-1", sources, target_count=4)

    chunk_ids = [c["chunk_id"] for c in sampled]
    # Anchors must always appear:
    assert "src-1_chunk_0" in chunk_ids
    assert "src-2_chunk_0" in chunk_ids
    # No duplicates:
    assert len(chunk_ids) == len(set(chunk_ids))
    # All chunks have a source name + truncated content
    for c in sampled:
        assert c["source_name"] in ("Doc A", "Doc B")
        assert len(c["content"]) <= kb_question_generator.MAX_CHUNK_CHARS


def test_sample_chunks_respects_max_sources_cap():
    """Generator caps anchor sampling at MAX_SAMPLED_SOURCES to bound prompt size."""
    sources = [_make_source(f"src-{i}", f"Doc {i}", chunk_count=1) for i in range(50)]
    seen_source_filters = []

    fake_collection = MagicMock()
    def fake_get(where=None, limit=None, **kw):
        if where and "source_id" in where:
            seen_source_filters.append(where["source_id"])
            return {"ids": [], "documents": [], "metadatas": []}
        return {"ids": [], "documents": [], "metadatas": []}
    fake_collection.get = fake_get
    fake_dm = MagicMock()
    fake_dm.get_kb_collection = MagicMock(return_value=fake_collection)

    with patch.object(kb_question_generator, "_get_dm", return_value=fake_dm):
        KBQuestionGenerator._sample_chunks("kb-1", sources, target_count=5)

    assert len(seen_source_filters) == kb_question_generator.MAX_SAMPLED_SOURCES


# ---------------------------------------------------------------------------
# Public generate() flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_rejects_empty_kb():
    """A KB with no indexed chunks must fail before any LLM call is made."""
    fake_kb = MagicMock()
    fake_kb.uuid = "kb-1"
    sources = [_make_source("src-1", "Doc A", chunk_count=0)]

    with patch.object(kb_question_generator, "KnowledgeBase") as KB, \
         patch.object(kb_question_generator, "KnowledgeBaseSource") as KBS:
        KB.find_one = AsyncMock(return_value=fake_kb)
        # Configure KBS.find(...).to_list() chain.
        find_call = MagicMock()
        find_call.to_list = AsyncMock(return_value=sources)
        KBS.find = MagicMock(return_value=find_call)

        gen = KBQuestionGenerator()
        with pytest.raises(ValueError, match="no indexed content"):
            await gen.generate("kb-1", "u1", coverage="quick", persist=False)


@pytest.mark.asyncio
async def test_generate_rejects_unknown_kb():
    with patch.object(kb_question_generator, "KnowledgeBase") as KB:
        KB.find_one = AsyncMock(return_value=None)
        gen = KBQuestionGenerator()
        with pytest.raises(ValueError, match="not found"):
            await gen.generate("kb-missing", "u1", coverage="quick", persist=False)


@pytest.mark.asyncio
async def test_generate_end_to_end_persist_false():
    """Happy path: sample chunks → call LLM (mocked) → parse → return KBTestQuery objects."""
    fake_kb = MagicMock()
    fake_kb.uuid = "kb-1"
    sources = [_make_source("src-1", "Doc A", chunk_count=5)]

    sampled = [{
        "chunk_id": "src-1_chunk_0",
        "source_id": "src-1",
        "source_name": "Doc A",
        "content": "Quarterly deadlines apply: Q1 March 15.",
    }]

    fake_run = MagicMock()
    fake_run.output = (
        '{"questions": [{"query": "When is the Q1 deadline?", '
        '"expected_answer": "March 15.", "expected_source_labels": ["Doc A"], '
        '"source_chunk_ids": ["src-1_chunk_0"], "category": "factual"}]}'
    )
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value=fake_run)

    # KBTestQuery is a Beanie Document — its constructor needs init_db, which we
    # don't have in unit tests. Patch the constructor to a MagicMock that captures
    # the kwargs so we can assert on them.
    constructed = []

    def make_tq(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items():
            setattr(m, k, v)
        m.insert = AsyncMock()
        constructed.append(m)
        return m

    with patch.object(kb_question_generator, "KnowledgeBase") as KB, \
         patch.object(kb_question_generator, "KnowledgeBaseSource") as KBS, \
         patch.object(kb_question_generator, "KBTestQuery", side_effect=make_tq), \
         patch.object(KBQuestionGenerator, "_sample_chunks", return_value=sampled), \
         patch.object(kb_question_generator, "_resolve_model_name", return_value="test-model"), \
         patch.object(kb_question_generator, "get_agent_model", return_value=MagicMock()), \
         patch("app.services.kb_question_generator.Agent", return_value=fake_agent):
        KB.find_one = AsyncMock(return_value=fake_kb)
        find_call = MagicMock()
        find_call.to_list = AsyncMock(return_value=sources)
        KBS.find = MagicMock(return_value=find_call)

        gen = KBQuestionGenerator()
        created = await gen.generate("kb-1", "u1", coverage="quick", persist=False)

    assert len(created) == 1
    tq = created[0]
    assert tq.query == "When is the Q1 deadline?"
    assert tq.expected_answer == "March 15."
    assert tq.expected_source_labels == ["Doc A"]
    assert tq.source_chunk_ids == ["src-1_chunk_0"]
    assert tq.category == "factual"
    assert tq.auto_generated is True


@pytest.mark.asyncio
async def test_generate_caps_results_to_target_count():
    """Even if the LLM returns more questions than requested, we cap at target."""
    fake_kb = MagicMock()
    fake_kb.uuid = "kb-1"
    sources = [_make_source("src-1", "Doc A", chunk_count=5)]
    sampled = [{"chunk_id": "src-1_chunk_0", "source_id": "src-1", "source_name": "Doc A", "content": "x"}]

    # 8 questions returned, but coverage="quick" -> target_count=5
    payload = {"questions": [
        {"query": f"Q{i}?", "expected_answer": f"A{i}.", "expected_source_labels": ["Doc A"]}
        for i in range(8)
    ]}
    import json
    fake_run = MagicMock()
    fake_run.output = json.dumps(payload)
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value=fake_run)

    def make_tq(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items():
            setattr(m, k, v)
        m.insert = AsyncMock()
        return m

    with patch.object(kb_question_generator, "KnowledgeBase") as KB, \
         patch.object(kb_question_generator, "KnowledgeBaseSource") as KBS, \
         patch.object(kb_question_generator, "KBTestQuery", side_effect=make_tq), \
         patch.object(KBQuestionGenerator, "_sample_chunks", return_value=sampled), \
         patch.object(kb_question_generator, "_resolve_model_name", return_value="test-model"), \
         patch.object(kb_question_generator, "get_agent_model", return_value=MagicMock()), \
         patch("app.services.kb_question_generator.Agent", return_value=fake_agent):
        KB.find_one = AsyncMock(return_value=fake_kb)
        find_call = MagicMock()
        find_call.to_list = AsyncMock(return_value=sources)
        KBS.find = MagicMock(return_value=find_call)

        gen = KBQuestionGenerator()
        created = await gen.generate("kb-1", "u1", coverage="quick", persist=False)

    assert len(created) == 5  # capped


@pytest.mark.asyncio
async def test_generate_raises_when_no_model_configured():
    fake_kb = MagicMock()
    fake_kb.uuid = "kb-1"
    sources = [_make_source("src-1", "Doc A", chunk_count=5)]
    sampled = [{"chunk_id": "src-1_chunk_0", "source_id": "src-1", "source_name": "Doc A", "content": "x"}]

    with patch.object(kb_question_generator, "KnowledgeBase") as KB, \
         patch.object(kb_question_generator, "KnowledgeBaseSource") as KBS, \
         patch.object(KBQuestionGenerator, "_sample_chunks", return_value=sampled), \
         patch.object(kb_question_generator, "_resolve_model_name", return_value=""):
        KB.find_one = AsyncMock(return_value=fake_kb)
        find_call = MagicMock()
        find_call.to_list = AsyncMock(return_value=sources)
        KBS.find = MagicMock(return_value=find_call)

        gen = KBQuestionGenerator()
        with pytest.raises(ValueError, match="No LLM model configured"):
            await gen.generate("kb-1", "u1", persist=False)
