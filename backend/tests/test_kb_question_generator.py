"""Tests for KBQuestionGenerator — chunk sampling, output parsing, KB rejection."""

from unittest.mock import AsyncMock, MagicMock, patch

import json

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


def test_parse_questions_drops_sample_scoped_queries():
    """Questions referencing the generator's private sample ('the provided
    excerpt') are unanswerable as written at validation time — drop them."""
    raw = {"questions": [
        {"query": "Does the provided excerpt specify the year in which the paper was accepted?",
         "expected_answer": "No, the excerpt does not specify the acceptance year."},
        {"query": "According to this passage, who is the PI?",
         "expected_answer": "Dr. Smith."},
        {"query": "What year was the paper in EBSCO-FullText.pdf accepted?",
         "expected_answer": "2024."},
    ]}
    out = KBQuestionGenerator._parse_questions(raw, set(), set())
    assert [q["query"] for q in out] == [
        "What year was the paper in EBSCO-FullText.pdf accepted?"
    ]


def test_parse_questions_handles_list_at_top_level():
    raw = [
        {"query": "Q1", "expected_answer": "A1"},
        {"query": "Q2", "expected_answer": "A2"},
    ]
    out = KBQuestionGenerator._parse_questions(raw, set(), set())
    assert len(out) == 2


# ---------------------------------------------------------------------------
# Absence-claim verification against full-KB retrieval
# ---------------------------------------------------------------------------


def _absence_q(query="Does the article state the acceptance year?",
               expected="The document does not specify the acceptance year."):
    return {"query": query, "expected_answer": expected,
            "expected_source_labels": [], "source_chunk_ids": [], "category": "boundary"}


def _positive_q():
    return {"query": "When is the Q1 deadline?", "expected_answer": "March 15.",
            "expected_source_labels": [], "source_chunk_ids": [], "category": "factual"}


@pytest.mark.asyncio
async def test_absence_filter_drops_contradicted_question():
    """The ticket case: the generator's 600-char sample lacked the acceptance
    date, but full-KB retrieval finds it — the question must be dropped."""
    chunks = [{"content": "Accepted: January 14, 2024.",
               "metadata": {"source_name": "EBSCO-FullText.pdf"}}]
    checker_run = MagicMock()
    checker_run.output = '{"contradicted": true, "evidence": "Accepted: January 14, 2024"}'
    checker = MagicMock()
    checker.run = AsyncMock(return_value=checker_run)

    with patch("app.services.kb_validation_service.retrieve_kb_chunks",
               new=AsyncMock(return_value=(chunks, MagicMock(), 0))), \
         patch("app.services.kb_question_generator.Agent", return_value=checker):
        out = await KBQuestionGenerator()._filter_contradicted_absence_questions(
            "kb-1", [_absence_q(), _positive_q()], "test-model", MagicMock(),
        )

    assert [q["query"] for q in out] == [_positive_q()["query"]]
    # Only the absence question is verified — one retrieval-backed LLM call.
    checker.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_absence_filter_keeps_question_when_not_contradicted():
    chunks = [{"content": "The study covers Idaho wheat yields.",
               "metadata": {"source_name": "EBSCO-FullText.pdf"}}]
    checker_run = MagicMock()
    checker_run.output = '{"contradicted": false, "evidence": ""}'
    checker = MagicMock()
    checker.run = AsyncMock(return_value=checker_run)

    with patch("app.services.kb_validation_service.retrieve_kb_chunks",
               new=AsyncMock(return_value=(chunks, MagicMock(), 0))), \
         patch("app.services.kb_question_generator.Agent", return_value=checker):
        out = await KBQuestionGenerator()._filter_contradicted_absence_questions(
            "kb-1", [_absence_q()], "test-model", MagicMock(),
        )

    assert len(out) == 1


@pytest.mark.asyncio
async def test_absence_filter_keeps_question_on_verification_error():
    """Verification is a quality filter — an infra blip must not gut generation."""
    with patch("app.services.kb_validation_service.retrieve_kb_chunks",
               new=AsyncMock(side_effect=RuntimeError("chroma down"))), \
         patch("app.services.kb_question_generator.Agent", return_value=MagicMock()):
        out = await KBQuestionGenerator()._filter_contradicted_absence_questions(
            "kb-1", [_absence_q()], "test-model", MagicMock(),
        )

    assert len(out) == 1


@pytest.mark.asyncio
async def test_absence_filter_skips_llm_entirely_without_absence_claims():
    """Positive-fact questions must not trigger retrieval or checker calls."""
    with patch("app.services.kb_question_generator.Agent") as agent_cls:
        out = await KBQuestionGenerator()._filter_contradicted_absence_questions(
            "kb-1", [_positive_q()], "test-model", MagicMock(),
        )
    assert len(out) == 1
    agent_cls.assert_not_called()


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
    fake_kb.title = "Export Control Regulations"
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
         patch.object(kb_question_generator, "backfill_auto_query_ids", new=AsyncMock(return_value=0)), \
         patch.object(KBQuestionGenerator, "_existing_external_ids", new=AsyncMock(return_value=[])), \
         patch.object(KBQuestionGenerator, "_sample_chunks", return_value=sampled), \
         patch.object(kb_question_generator, "get_user_model_name", new=AsyncMock(return_value="test-model")), \
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
    # Standardized with imported rows: a stable, human-readable ID and a
    # provenance note in the Notes column.
    assert tq.external_id == "ECR-AUTO-Q001"
    assert tq.notes.startswith("Auto-generated ")
    assert "from Doc A" in tq.notes
    assert "(quick coverage, model test-model)" in tq.notes


def _run_generate(
    payload: dict, *, sampled, existing_ids, title="Doc KB", persist=False,
    backfill=None, existing_ids_reader=None, insert_side_effect=None,
):
    """Drive generate() with a canned LLM payload; returns the constructed rows.

    ``backfill`` / ``existing_ids_reader`` replace the legacy-ID backfill and
    the KB's ID read (both AsyncMocks by default) so a test can assert on
    their ordering; ``insert_side_effect`` is handed to every row's insert.
    """
    fake_kb = MagicMock()
    fake_kb.uuid = "kb-1"
    fake_kb.title = title
    sources = [_make_source("src-1", "Doc A", chunk_count=5), _make_source("src-2", "Doc B", chunk_count=5)]
    fake_run = MagicMock()
    fake_run.output = json.dumps(payload)
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value=fake_run)
    constructed = []
    backfill = backfill if backfill is not None else AsyncMock(return_value=0)
    # ``_existing_external_ids`` is a staticmethod; a plain coroutine function
    # patched onto the class would be bound and receive ``self``.
    existing_ids_reader = staticmethod(existing_ids_reader) if existing_ids_reader is not None \
        else AsyncMock(return_value=existing_ids)

    def make_tq(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items():
            setattr(m, k, v)
        m.insert = AsyncMock(side_effect=insert_side_effect)
        constructed.append(m)
        return m

    async def run():
        with patch.object(kb_question_generator, "KnowledgeBase") as KB, \
             patch.object(kb_question_generator, "KnowledgeBaseSource") as KBS, \
             patch.object(kb_question_generator, "KBTestQuery", side_effect=make_tq), \
             patch.object(kb_question_generator, "backfill_auto_query_ids", new=backfill), \
             patch.object(KBQuestionGenerator, "_existing_external_ids", new=existing_ids_reader), \
             patch.object(KBQuestionGenerator, "_sample_chunks", return_value=sampled), \
             patch.object(kb_question_generator, "get_user_model_name", new=AsyncMock(return_value="test-model")), \
             patch.object(kb_question_generator, "get_agent_model", return_value=MagicMock()), \
             patch("app.services.kb_question_generator.Agent", return_value=fake_agent):
            KB.find_one = AsyncMock(return_value=fake_kb)
            find_call = MagicMock()
            find_call.to_list = AsyncMock(return_value=sources)
            KBS.find = MagicMock(return_value=find_call)
            return await KBQuestionGenerator().generate("kb-1", "u1", coverage="quick", persist=persist)

    return run()


_TWO_CHUNKS = [
    {"chunk_id": "src-1_chunk_0", "source_id": "src-1", "source_name": "Doc A", "content": "x"},
    {"chunk_id": "src-2_chunk_0", "source_id": "src-2", "source_name": "Doc B", "content": "y"},
]


@pytest.mark.asyncio
async def test_generate_continues_numbering_after_existing_ids_and_keeps_imports():
    """A second generation must not reuse Q001, and an imported ID is never reassigned."""
    payload = {"questions": [
        {"query": "Q1?", "expected_answer": "A1.", "expected_source_labels": ["Doc A"], "source_chunk_ids": ["src-1_chunk_0"]},
        {"query": "Q2?", "expected_answer": "A2.", "expected_source_labels": ["Doc B"], "source_chunk_ids": ["src-2_chunk_0"]},
    ]}
    created = await _run_generate(
        payload, sampled=_TWO_CHUNKS,
        existing_ids=["SUB-002", "DOC-AUTO-Q001", "DOC-AUTO-Q004"],
    )
    assert [q.external_id for q in created] == ["DOC-AUTO-Q005", "DOC-AUTO-Q006"]


@pytest.mark.asyncio
async def test_generate_persisted_rows_reserve_ids_against_the_kb():
    """A persisted generation re-checks the KB per ID (a concurrent generation
    may have taken the number since the read); a preview does not touch it."""
    from app.services import kb_test_query_ids
    payload = {"questions": [
        {"query": "Q1?", "expected_answer": "A1.", "expected_source_labels": ["Doc A"], "source_chunk_ids": ["src-1_chunk_0"]},
    ]}
    tq_model = MagicMock()
    tq_model.find_one = AsyncMock(side_effect=[MagicMock(), None])  # Q001 taken meanwhile, Q002 free
    with patch("app.models.kb_test_query.KBTestQuery", tq_model):
        created = await _run_generate(payload, sampled=_TWO_CHUNKS, existing_ids=[], persist=True)
    assert [q.external_id for q in created] == ["DOC-AUTO-Q002"]
    created[0].insert.assert_awaited_once()

    tq_model.find_one.reset_mock(side_effect=True)
    tq_model.find_one.return_value = MagicMock()
    with patch("app.models.kb_test_query.KBTestQuery", tq_model):
        preview = await _run_generate(payload, sampled=_TWO_CHUNKS, existing_ids=[])
    assert [q.external_id for q in preview] == ["DOC-AUTO-Q001"]
    tq_model.find_one.assert_not_awaited()


_ONE_QUESTION = {"questions": [
    {"query": "Q1?", "expected_answer": "A1.", "expected_source_labels": ["Doc A"], "source_chunk_ids": ["src-1_chunk_0"]},
]}


@pytest.mark.asyncio
async def test_persisted_generation_numbers_legacy_rows_before_reading_ids_for_its_batch():
    """#886: the backfill moved off the GET onto the write paths. It must run
    before the allocator reads the KB's IDs, so pre-#876 rows take the low
    numbers and this batch continues after them; a preview never writes."""
    events = []

    async def backfill(kb):
        events.append(("backfill", kb.uuid))
        return 1

    async def read_ids(kb_uuid):
        events.append(("read_ids", kb_uuid))
        return ["DOC-AUTO-Q001"]  # what the backfill just wrote

    tq_model = MagicMock()
    tq_model.find_one = AsyncMock(return_value=None)
    with patch("app.models.kb_test_query.KBTestQuery", tq_model):
        created = await _run_generate(
            _ONE_QUESTION, sampled=_TWO_CHUNKS, existing_ids=[], persist=True,
            backfill=backfill, existing_ids_reader=read_ids,
        )
    assert events == [("backfill", "kb-1"), ("read_ids", "kb-1")]
    assert [q.external_id for q in created] == ["DOC-AUTO-Q002"]

    events.clear()
    await _run_generate(
        _ONE_QUESTION, sampled=_TWO_CHUNKS, existing_ids=[], persist=False,
        backfill=backfill, existing_ids_reader=read_ids,
    )
    assert events == [("read_ids", "kb-1")]


@pytest.mark.asyncio
async def test_persisted_generation_takes_the_next_number_when_the_insert_collides():
    """Two writers can both pass the pre-write re-check; the unique index
    rejects the second insert and the row is retried with the next number
    rather than failing the whole generation (#886)."""
    from pymongo.errors import DuplicateKeyError

    tq_model = MagicMock()
    tq_model.find_one = AsyncMock(return_value=None)
    with patch("app.models.kb_test_query.KBTestQuery", tq_model):
        created = await _run_generate(
            _ONE_QUESTION, sampled=_TWO_CHUNKS, existing_ids=[], persist=True,
            insert_side_effect=[DuplicateKeyError("E11000"), None],
        )
    assert [q.external_id for q in created] == ["DOC-AUTO-Q002"]
    assert created[0].insert.await_count == 2


@pytest.mark.asyncio
async def test_generate_fills_source_from_cited_chunks_when_labels_are_invented():
    """The Source column is never blank for a chunk-grounded question."""
    payload = {"questions": [
        {"query": "Q1?", "expected_answer": "A1.", "expected_source_labels": ["Made-up name"],
         "source_chunk_ids": ["src-2_chunk_0"], "category": "summary"},
    ]}
    created = await _run_generate(payload, sampled=_TWO_CHUNKS, existing_ids=[])
    tq = created[0]
    assert tq.expected_source_labels == ["Doc B"]
    assert tq.category == "summary"
    assert tq.external_id == "DOC-AUTO-Q001"
    assert "from Doc B" in tq.notes


@pytest.mark.asyncio
async def test_generate_caps_results_to_target_count():
    """Even if the LLM returns more questions than requested, we cap at target."""
    fake_kb = MagicMock()
    fake_kb.uuid = "kb-1"
    fake_kb.title = "Doc KB"
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
         patch.object(kb_question_generator, "backfill_auto_query_ids", new=AsyncMock(return_value=0)), \
         patch.object(KBQuestionGenerator, "_existing_external_ids", new=AsyncMock(return_value=[])), \
         patch.object(KBQuestionGenerator, "_sample_chunks", return_value=sampled), \
         patch.object(kb_question_generator, "get_user_model_name", new=AsyncMock(return_value="test-model")), \
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
    fake_kb.title = "Doc KB"
    sources = [_make_source("src-1", "Doc A", chunk_count=5)]
    sampled = [{"chunk_id": "src-1_chunk_0", "source_id": "src-1", "source_name": "Doc A", "content": "x"}]

    with patch.object(kb_question_generator, "KnowledgeBase") as KB, \
         patch.object(kb_question_generator, "KnowledgeBaseSource") as KBS, \
         patch.object(KBQuestionGenerator, "_sample_chunks", return_value=sampled), \
         patch.object(kb_question_generator, "get_user_model_name", new=AsyncMock(return_value="")):
        KB.find_one = AsyncMock(return_value=fake_kb)
        find_call = MagicMock()
        find_call.to_list = AsyncMock(return_value=sources)
        KBS.find = MagicMock(return_value=find_call)

        gen = KBQuestionGenerator()
        with pytest.raises(ValueError, match="No LLM model configured"):
            await gen.generate("kb-1", "u1", persist=False)
