"""Tests for app.services.kb_validation_service.

Focuses on the retrieval-precision tuple-unpack bug regression: query_kb returns
list[dict] with shape {"content", "metadata"}, but the prior implementation
unpacked each result as a 2-tuple, which silently iterated the dict's keys and
produced empty source names.

Also covers the KBTestQuery field additions for the LLM-as-judge feature.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.kb_test_query import KBTestQuery
from app.services import kb_validation_service


def _make_test_query(
    query="What is the grant deadline?",
    expected_source_labels=None,
    expected_answer_contains=None,
):
    tq = MagicMock()
    tq.uuid = "tq-1"
    tq.query = query
    tq.expected_source_labels = expected_source_labels or []
    tq.expected_answer_contains = expected_answer_contains
    return tq


@pytest.mark.asyncio
async def test_check_retrieval_precision_extracts_source_names_from_dict_results():
    """Regression: query_kb returns list[dict], not list[tuple]. We must read
    metadata.source_name via dict access, not via tuple unpacking."""

    fake_kb_uuid = "kb-1"
    fake_results = [
        {"content": "Grant deadlines are quarterly.", "metadata": {"source_name": "Grant Handbook 2025"}},
        {"content": "Q1 deadline is March 15.", "metadata": {"source_name": "Q1 Schedule"}},
    ]

    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=fake_results)

    tq = _make_test_query(
        query="When is Q1 due?",
        expected_source_labels=["Grant Handbook"],
    )

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm):
        result = await kb_validation_service.check_retrieval_precision(fake_kb_uuid, [tq])

    assert result["total_queries"] == 1
    detail = result["details"][0]
    assert detail["retrieved_sources"] == ["Grant Handbook 2025", "Q1 Schedule"]
    assert detail["precision"] == 1.0
    assert result["avg_precision"] == 1.0


@pytest.mark.asyncio
async def test_check_retrieval_precision_no_match_yields_zero():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(
        return_value=[
            {"content": "Unrelated text.", "metadata": {"source_name": "Other Doc"}},
        ]
    )
    tq = _make_test_query(expected_source_labels=["Grant Handbook"])

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm):
        result = await kb_validation_service.check_retrieval_precision("kb-1", [tq])

    assert result["details"][0]["precision"] == 0.0
    assert result["details"][0]["retrieved_sources"] == ["Other Doc"]


@pytest.mark.asyncio
async def test_check_retrieval_precision_answer_contains_uses_content_field():
    """expected_answer_contains must search across the content of each result dict
    (formerly was unpacking a tuple, which would fail or be empty)."""
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(
        return_value=[
            {"content": "The annual budget is $1.2M.", "metadata": {"source_name": "Budget Doc"}},
            {"content": "Last fiscal year saw a 5% increase.", "metadata": {"source_name": "FY Report"}},
        ]
    )
    tq = _make_test_query(
        query="What is the budget?",
        expected_source_labels=[],
        expected_answer_contains="$1.2M",
    )

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm):
        result = await kb_validation_service.check_retrieval_precision("kb-1", [tq])

    detail = result["details"][0]
    assert detail["answer_match"] is True
    assert detail["precision"] == 1.0


@pytest.mark.asyncio
async def test_check_retrieval_precision_answer_contains_missing_penalises():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(
        return_value=[
            {"content": "Some other content.", "metadata": {"source_name": "Doc A"}},
        ]
    )
    tq = _make_test_query(
        expected_source_labels=["Doc A"],
        expected_answer_contains="quarterly meetings",
    )

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm):
        result = await kb_validation_service.check_retrieval_precision("kb-1", [tq])

    detail = result["details"][0]
    assert detail["answer_match"] is False
    # source label matched (precision 1.0) but answer missing → 0.5x penalty
    assert detail["precision"] == 0.5


@pytest.mark.asyncio
async def test_check_retrieval_precision_handles_empty_results():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[])
    tq = _make_test_query(expected_source_labels=["Doc A"])

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm):
        result = await kb_validation_service.check_retrieval_precision("kb-1", [tq])

    detail = result["details"][0]
    assert detail["precision"] == 0.0
    assert detail["retrieved_sources"] == []


@pytest.mark.asyncio
async def test_check_retrieval_precision_no_test_queries_returns_zeroed_summary():
    result = await kb_validation_service.check_retrieval_precision("kb-1", [])
    assert result == {"total_queries": 0, "avg_precision": 0.0, "details": []}


# ---------------------------------------------------------------------------
# KBTestQuery schema additions (LLM-as-judge support)
# ---------------------------------------------------------------------------


def test_kb_test_query_supports_judge_fields():
    """The new fields for LLM-as-judge + auto-generation must round-trip."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    tq = KBTestQuery.model_construct(
        uuid="tq-1",
        knowledge_base_uuid="kb-1",
        query="What is X?",
        expected_source_labels=["Doc A"],
        expected_answer_contains="42",
        expected_answer="The answer is 42.",
        auto_generated=True,
        category="factual",
        source_chunk_ids=["src-1_chunk_0"],
        last_judged_score=0.85,
        last_judged_at=now,
        user_id="u1",
        created_at=now,
    )
    d = tq.model_dump()
    assert d["expected_answer"] == "The answer is 42."
    assert d["auto_generated"] is True
    assert d["category"] == "factual"
    assert d["source_chunk_ids"] == ["src-1_chunk_0"]
    assert d["last_judged_score"] == 0.85
    assert d["last_judged_at"] == now


def test_kb_test_query_backward_compatible_defaults():
    """Existing rows without the new fields should still load with sane defaults."""
    tq = KBTestQuery.model_construct(
        uuid="tq-2",
        knowledge_base_uuid="kb-1",
        query="Q",
        user_id="u1",
    )
    d = tq.model_dump()
    assert d["expected_answer"] is None
    assert d["auto_generated"] is False
    assert d["category"] is None
    assert d["source_chunk_ids"] == []
    assert d["last_judged_score"] is None
    assert d["last_judged_at"] is None


# ---------------------------------------------------------------------------
# Answer-generation helpers (headless RAG + baseline)
# ---------------------------------------------------------------------------


def _make_mock_run(output: str, tokens: int = 0):
    """A pydantic-ai-like AgentRunResult with .output and a .usage() method."""
    run_result = MagicMock()
    run_result.output = output
    usage = MagicMock()
    usage.input_tokens = tokens // 2
    usage.output_tokens = tokens - tokens // 2
    usage.cache_read_tokens = 0
    usage.cache_write_tokens = 0
    run_result.usage = MagicMock(return_value=usage)
    return run_result


def _make_mock_agent(output: str, tokens: int = 0):
    agent = MagicMock()
    agent.run = AsyncMock(return_value=_make_mock_run(output, tokens))
    return agent


@pytest.fixture(autouse=True)
def _clear_agent_cache():
    kb_validation_service._agent_cache.clear()
    yield
    kb_validation_service._agent_cache.clear()


def test_format_retrieved_context_renders_source_blocks():
    chunks = [
        {"content": "Quarterly deadlines apply.", "metadata": {"source_name": "Handbook"}},
        {"content": "Q1 due March 15.", "metadata": {"source_name": "Schedule"}},
        {"content": "", "metadata": {"source_name": "Empty"}},  # skipped
    ]
    formatted = kb_validation_service._format_retrieved_context(chunks)
    assert "## Source: Handbook" in formatted
    assert "Quarterly deadlines apply." in formatted
    assert "## Source: Schedule" in formatted
    assert "## Source: Empty" not in formatted


def test_get_or_build_agent_reuses_within_same_loop():
    """Same running loop + same (purpose, model) -> one agent, built once."""
    import asyncio

    sentinel_agent = object()
    with patch.object(kb_validation_service, "get_agent_model", return_value=MagicMock()), \
         patch.object(kb_validation_service, "Agent", return_value=sentinel_agent) as agent_ctor:
        async def _twice():
            a = kb_validation_service._get_or_build_agent("kb_judge:factoid", "m", "prompt")
            b = kb_validation_service._get_or_build_agent("kb_judge:factoid", "m", "prompt")
            return a, b

        a, b = asyncio.run(_twice())
    assert a is b is sentinel_agent
    assert agent_ctor.call_count == 1


def test_get_or_build_agent_rebuilds_across_loops():
    """A cached agent from a prior, now-closed loop is NOT reused on a new loop.

    Regression for "Judge error: Connection error" after KB tuning: the agent's
    httpx pool is bound to the loop that built it, so reusing it on a later
    Celery task's loop raised a zero-token connection error on every query.
    """
    import asyncio

    with patch.object(kb_validation_service, "get_agent_model", return_value=MagicMock()), \
         patch.object(kb_validation_service, "Agent", side_effect=lambda *a, **k: object()) as agent_ctor:
        async def _build():
            return kb_validation_service._get_or_build_agent("kb_judge:factoid", "m", "prompt")

        first = asyncio.run(_build())   # loop A (closed on return)
        second = asyncio.run(_build())  # loop B — must rebuild, not reuse loop A's agent
    assert first is not second
    assert agent_ctor.call_count == 2


@pytest.mark.asyncio
async def test_generate_kb_answer_uses_retrieved_context():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[
        {"content": "The Q1 deadline is March 15.", "metadata": {"source_name": "Schedule"}},
    ])
    captured_prompt = {}

    async def fake_run(prompt):
        captured_prompt["value"] = prompt
        return _make_mock_run("The Q1 deadline is March 15.", tokens=1234)

    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=fake_run)

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent):
        answer, retrieved, tokens = await kb_validation_service._generate_kb_answer(
            "kb-1", "When is Q1 due?", "test-model"
        )

    assert "March 15" in answer
    assert len(retrieved) == 1
    assert "## Source: Schedule" in captured_prompt["value"]
    assert "When is Q1 due?" in captured_prompt["value"]
    # Token usage flowed through from the mocked usage() call.
    assert tokens == 1234


@pytest.mark.asyncio
async def test_generate_kb_answer_handles_empty_retrieval():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[])

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm):
        answer, retrieved, tokens = await kb_validation_service._generate_kb_answer(
            "kb-1", "Q?", "test-model"
        )

    assert "could not find" in answer.lower()
    assert retrieved == []
    # No agent call when retrieval is empty.
    assert tokens == 0


@pytest.mark.asyncio
async def test_generate_baseline_answer_uses_baseline_prompt_no_kb():
    captured_prompt = {}

    async def fake_run(prompt):
        captured_prompt["value"] = prompt
        return _make_mock_run("I do not know.", tokens=500)

    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=fake_run)

    with patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent) as get_agent:
        answer, tokens = await kb_validation_service._generate_baseline_answer("Q?", "test-model")

    assert answer == "I do not know."
    assert tokens == 500
    # Baseline never has a "Source:" block — verify by absence of that fingerprint.
    assert "## Source:" not in captured_prompt["value"]
    # Verify the agent was constructed with the baseline purpose.
    get_agent.assert_called_once()
    purpose, model_name, system_prompt = get_agent.call_args.args[:3]
    assert purpose == "kb_baseline"
    assert model_name == "test-model"
    assert system_prompt is kb_validation_service.BASELINE_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_generate_kb_answer_swallows_agent_errors():
    """Per-query LLM failures must not crash the run — judge_test_queries
    relies on this for resilience."""
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[
        {"content": "ctx", "metadata": {"source_name": "S"}},
    ])
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=RuntimeError("LLM down"))

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent):
        answer, retrieved, tokens = await kb_validation_service._generate_kb_answer(
            "kb-1", "Q?", "test-model"
        )

    assert answer == ""
    assert len(retrieved) == 1
    assert tokens == 0  # exception swallowed before usage() ran


@pytest.mark.asyncio
async def test_generate_kb_answer_forwards_min_similarity_floor():
    """The configured relevance floor must reach query_kb so gating happens at
    retrieval — not be silently dropped on the way down."""
    from app.services.kb_validation_service import RAGConfig

    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[
        {"content": "ctx", "metadata": {"source_name": "S"}},
    ])
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value=_make_mock_run("answer", tokens=10))

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent):
        await kb_validation_service._generate_kb_answer(
            "kb-1", "Q?", "test-model", config=RAGConfig(min_similarity=0.3),
        )

    # query_kb(kb_uuid, query, retrieve_k, min_similarity) — floor is 4th arg.
    assert fake_dm.query_kb.call_args.args == ("kb-1", "Q?", 8, 0.3)


@pytest.mark.asyncio
async def test_generate_kb_answer_gated_empty_abstains():
    """When the floor filters every chunk, query_kb returns [] and the answer is
    the clean abstention — no generation from junk."""
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[])  # everything fell below the floor
    from app.services.kb_validation_service import RAGConfig

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm):
        answer, retrieved, tokens = await kb_validation_service._generate_kb_answer(
            "kb-1", "out of scope?", "test-model", config=RAGConfig(min_similarity=0.9),
        )

    assert "could not find" in answer.lower()
    assert retrieved == []
    assert tokens == 0


@pytest.mark.asyncio
async def test_resolve_kb_min_similarity_reads_resolved_config():
    """The live chat path surfaces the floor from the resolved per-KB config —
    the same RAGConfig the validation/optimizer path uses."""
    from app.services.kb_validation_service import RAGConfig

    with patch.object(
        kb_validation_service, "_resolve_rag_config",
        AsyncMock(return_value=RAGConfig(min_similarity=0.42)),
    ):
        floor = await kb_validation_service.resolve_kb_min_similarity("kb-1")

    assert floor == 0.42


@pytest.mark.asyncio
async def test_resolve_kb_min_similarity_defaults_zero_on_error():
    """A config-resolution failure must degrade to 0.0 (gating off) rather than
    propagate — retrieval should never break or spuriously over-filter."""
    with patch.object(
        kb_validation_service, "_resolve_rag_config",
        AsyncMock(side_effect=RuntimeError("db down")),
    ):
        floor = await kb_validation_service.resolve_kb_min_similarity("kb-x")

    assert floor == 0.0


# ---------------------------------------------------------------------------
# LLM judge: parsing, scoring, lift, discrimination
# ---------------------------------------------------------------------------


def test_parse_kb_verdict_handles_well_formed_response():
    raw = {
        "score": 0.85,
        "verdict": "PASS",
        "confidence": 0.9,
        "reasoning": "Covers all expected facts.",
        "evidence": "$1.2M is mentioned.",
        "missing_facts": [],
        "hallucinated_facts": [],
    }
    v = kb_validation_service._parse_kb_verdict(raw)
    assert v["score"] == 0.85
    assert v["verdict"] == "PASS"
    assert v["missing_facts"] == []


def test_parse_kb_verdict_derives_verdict_from_score_when_missing():
    v = kb_validation_service._parse_kb_verdict({"score": 0.3})
    assert v["verdict"] == "FAIL"
    v = kb_validation_service._parse_kb_verdict({"score": 0.5})
    assert v["verdict"] == "WARN"
    v = kb_validation_service._parse_kb_verdict({"score": 0.95})
    assert v["verdict"] == "PASS"


def test_parse_kb_verdict_clamps_invalid_inputs():
    v = kb_validation_service._parse_kb_verdict({"score": 5.0, "confidence": "bogus"})
    assert v["score"] == 1.0
    assert v["confidence"] == 0.5
    v = kb_validation_service._parse_kb_verdict({"score": -1.0})
    assert v["score"] == 0.0


def test_classify_discrimination():
    assert kb_validation_service._classify_discrimination(0.9, 0.4) == "useful"
    assert kb_validation_service._classify_discrimination(0.85, 0.8) == "redundant"
    assert kb_validation_service._classify_discrimination(0.2, 0.2) == "failing"
    assert kb_validation_service._classify_discrimination(0.6, 0.5) == "other"
    # No baseline → "other" (judge-only mode)
    assert kb_validation_service._classify_discrimination(0.9, None) == "other"


@pytest.mark.asyncio
async def test_judge_test_queries_judge_only_mode():
    """In mode='judge', no baseline is generated. lift and baseline_judge stay None."""

    tq_good = MagicMock()
    tq_good.uuid = "tq-1"
    tq_good.query = "What is the budget?"
    tq_good.expected_answer = "$1.2M"
    tq_good.category = "factual"
    tq_good.last_judged_score = None
    tq_good.last_judged_at = None
    tq_good.save = AsyncMock()

    async def fake_kb_answer(kb_uuid, query, model_name, k=8):
        return ("The budget is $1.2M.", [{"content": "Budget: $1.2M", "metadata": {"source_name": "Doc"}}])

    async def fake_judge(*, query, expected_answer, actual_answer, model_name, retrieved_context=None, category=None):
        return {
            "score": 0.9,
            "verdict": "PASS",
            "confidence": 0.95,
            "reasoning": "Matches expected.",
            "evidence": "$1.2M present.",
            "missing_facts": [],
            "hallucinated_facts": [],
        }

    with patch.object(kb_validation_service, "_generate_kb_answer", side_effect=fake_kb_answer), \
         patch.object(kb_validation_service, "_judge_answer", side_effect=fake_judge), \
         patch.object(kb_validation_service, "_generate_baseline_answer") as baseline_mock:
        out = await kb_validation_service.judge_test_queries(
            "kb-1", [tq_good], "test-model", mode="judge"
        )

    baseline_mock.assert_not_called()
    assert out["num_queries_judged"] == 1
    assert out["num_queries_baselined"] == 0
    assert out["avg_judge_score"] == 0.9
    assert out["avg_baseline_score"] is None
    assert out["avg_lift"] is None
    detail = out["details"][0]
    assert detail["judge"]["verdict"] == "PASS"
    assert detail["baseline_judge"] is None
    assert detail["lift"] is None
    assert detail["discrimination"] == "other"
    # last_judged_* persisted
    tq_good.save.assert_awaited_once()
    assert tq_good.last_judged_score == 0.9


@pytest.mark.asyncio
async def test_judge_test_queries_judge_plus_baseline_computes_lift_and_discrimination():
    tq = MagicMock()
    tq.uuid = "tq-1"
    tq.query = "What is the internal codename?"
    tq.expected_answer = "Project Gardenia."
    tq.category = "factual"
    tq.last_judged_score = None
    tq.save = AsyncMock()

    async def fake_kb_answer(kb_uuid, query, model_name, k=8):
        return ("The codename is Project Gardenia.", [
            {"content": "internal codename: Project Gardenia", "metadata": {"source_name": "Memo"}},
        ])

    async def fake_baseline_answer(query, model_name):
        return "I don't know the internal codename of that project."

    judge_calls = []

    async def fake_judge(*, query, expected_answer, actual_answer, model_name, retrieved_context=None, category=None):
        judge_calls.append({"actual": actual_answer, "has_context": retrieved_context is not None})
        if "Project Gardenia" in actual_answer:
            return {"score": 0.95, "verdict": "PASS", "confidence": 0.95,
                    "reasoning": "matches", "evidence": "", "missing_facts": [], "hallucinated_facts": []}
        return {"score": 0.1, "verdict": "FAIL", "confidence": 0.9,
                "reasoning": "doesn't know", "evidence": "", "missing_facts": ["codename"], "hallucinated_facts": []}

    with patch.object(kb_validation_service, "_generate_kb_answer", side_effect=fake_kb_answer), \
         patch.object(kb_validation_service, "_generate_baseline_answer", side_effect=fake_baseline_answer), \
         patch.object(kb_validation_service, "_judge_answer", side_effect=fake_judge):
        out = await kb_validation_service.judge_test_queries(
            "kb-1", [tq], "test-model", mode="judge+baseline"
        )

    assert out["num_queries_judged"] == 1
    assert out["num_queries_baselined"] == 1
    assert out["avg_judge_score"] == 0.95
    assert out["avg_baseline_score"] == 0.1
    assert out["avg_lift"] == 0.85  # 0.95 - 0.1
    assert out["details"][0]["lift"] == 0.85
    assert out["details"][0]["discrimination"] == "useful"
    # KB judge call had retrieved context; baseline judge call did not.
    assert len(judge_calls) == 2
    assert judge_calls[0]["has_context"] is True   # KB judge first
    assert judge_calls[1]["has_context"] is False  # baseline judge second


@pytest.mark.asyncio
async def test_judge_test_queries_skips_queries_without_expected_answer():
    tq_skip = MagicMock()
    tq_skip.uuid = "tq-skip"
    tq_skip.query = "Q?"
    tq_skip.expected_answer = None
    tq_skip.category = None
    tq_skip.save = AsyncMock()

    out = await kb_validation_service.judge_test_queries(
        "kb-1", [tq_skip], "test-model", mode="judge"
    )

    assert out["num_queries_judged"] == 0
    assert out["avg_judge_score"] is None
    assert len(out["details"]) == 1
    assert out["details"][0]["judge"] is None
    tq_skip.save.assert_not_called()


@pytest.mark.asyncio
async def test_judge_test_queries_per_query_failure_does_not_crash():
    tq = MagicMock()
    tq.uuid = "tq-1"
    tq.query = "Q?"
    tq.expected_answer = "A"
    tq.category = None
    tq.save = AsyncMock()

    async def fake_kb_answer(*args, **kwargs):
        raise RuntimeError("retrieval failed")

    with patch.object(kb_validation_service, "_generate_kb_answer", side_effect=fake_kb_answer):
        out = await kb_validation_service.judge_test_queries(
            "kb-1", [tq], "test-model", mode="judge"
        )

    assert len(out["details"]) == 1
    assert out["details"][0]["judge"]["verdict"] == "SKIPPED"
    assert "retrieval failed" in out["details"][0]["judge"]["reasoning"]


# ---------------------------------------------------------------------------
# RAGConfig — KB Autovalidate's optimization knobs
# ---------------------------------------------------------------------------


def test_rag_config_defaults_match_legacy_behaviour():
    """The default RAGConfig must reproduce pre-Autovalidate behaviour exactly,
    so unconfigured callers see no change."""
    cfg = kb_validation_service.RAGConfig()
    assert cfg.k == kb_validation_service.DEFAULT_K == 8
    assert cfg.model is None
    assert cfg.prompt_variant == "default"
    assert cfg.query_rewriting is False
    assert cfg.source_label_visibility is True


def test_rag_config_with_overrides_returns_copy():
    cfg = kb_validation_service.RAGConfig()
    cfg2 = cfg.with_overrides(k=12, query_rewriting=True)
    assert cfg.k == 8 and cfg.query_rewriting is False  # original unchanged
    assert cfg2.k == 12 and cfg2.query_rewriting is True


def test_rag_config_rejects_unknown_fields():
    """Forbid-extra protects the optimizer from typos in trial configs."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        kb_validation_service.RAGConfig(unknown_knob="oops")


def test_format_context_for_config_omits_source_labels_when_disabled():
    chunks = [
        {"content": "fact A", "metadata": {"source_name": "Doc 1"}},
        {"content": "fact B", "metadata": {"source_name": "Doc 2"}},
    ]
    cfg = kb_validation_service.RAGConfig(source_label_visibility=False)
    out = kb_validation_service._format_context_for_config(chunks, cfg)
    assert "## Source:" not in out
    assert "fact A" in out and "fact B" in out


def test_format_context_for_config_includes_labels_by_default():
    chunks = [
        {"content": "fact A", "metadata": {"source_name": "Doc 1"}},
    ]
    cfg = kb_validation_service.RAGConfig()
    out = kb_validation_service._format_context_for_config(chunks, cfg)
    assert "## Source: Doc 1" in out


@pytest.mark.asyncio
async def test_generate_kb_answer_with_explicit_config_overrides_k():
    """Passing config.k=12 must result in dm.query_kb being called with k=12."""
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[
        {"content": "ctx", "metadata": {"source_name": "S"}},
    ])
    fake_run = MagicMock()
    fake_run.output = "answer"
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value=fake_run)

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent):
        cfg = kb_validation_service.RAGConfig(k=12)
        await kb_validation_service._generate_kb_answer(
            "kb-1", "Q?", "test-model", config=cfg
        )

    # 4th arg is the similarity floor (default 0.0 = ungated for this config).
    fake_dm.query_kb.assert_called_once_with("kb-1", "Q?", 12, 0.0)


@pytest.mark.asyncio
async def test_generate_kb_answer_with_query_rewriting_uses_rewritten_query():
    """When query_rewriting=True, the rewritten query is what hits dm.query_kb,
    but the *original* query stays in the user prompt for the LLM."""
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[
        {"content": "ctx", "metadata": {"source_name": "S"}},
    ])
    captured_prompts = []

    async def fake_run(prompt):
        captured_prompts.append(prompt)
        out = MagicMock()
        out.output = "rewritten search prompt" if "Generate a search prompt" in prompt else "final answer"
        return out

    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=fake_run)

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent):
        cfg = kb_validation_service.RAGConfig(query_rewriting=True)
        await kb_validation_service._generate_kb_answer(
            "kb-1", "When is Q1 due?", "test-model", config=cfg
        )

    # Retrieval uses the rewritten query, not the raw user question.
    fake_dm.query_kb.assert_called_once()
    args = fake_dm.query_kb.call_args.args
    assert args[1] == "rewritten search prompt"
    # And the answer prompt still references the original user question.
    answer_prompt = next(p for p in captured_prompts if "Retrieved context" in p)
    assert "When is Q1 due?" in answer_prompt


@pytest.mark.asyncio
async def test_generate_kb_answer_query_rewrite_failure_falls_back_to_raw():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[
        {"content": "ctx", "metadata": {"source_name": "S"}},
    ])

    async def fake_run(prompt):
        if "Generate a search prompt" in prompt:
            raise RuntimeError("rewriter died")
        out = MagicMock()
        out.output = "answer"
        return out

    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=fake_run)

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent):
        cfg = kb_validation_service.RAGConfig(query_rewriting=True)
        await kb_validation_service._generate_kb_answer(
            "kb-1", "raw question", "test-model", config=cfg
        )

    args = fake_dm.query_kb.call_args.args
    assert args[1] == "raw question"  # fell back


@pytest.mark.asyncio
async def test_generate_kb_answer_strict_prompt_variant_uses_strict_instructions():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[
        {"content": "ctx", "metadata": {"source_name": "S"}},
    ])
    captured_prompts = []

    async def fake_run(prompt):
        captured_prompts.append(prompt)
        out = MagicMock()
        out.output = "answer"
        return out

    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=fake_run)

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent):
        cfg = kb_validation_service.RAGConfig(prompt_variant="strict")
        await kb_validation_service._generate_kb_answer(
            "kb-1", "Q?", "test-model", config=cfg
        )

    answer_prompt = captured_prompts[0]
    assert "verbatim or in close paraphrase" in answer_prompt


@pytest.mark.asyncio
async def test_generate_kb_answer_unknown_prompt_variant_falls_back_to_default():
    """Optimizer should never hand us an unknown variant, but if it does we
    don't crash — we use the default instruction."""
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[
        {"content": "ctx", "metadata": {"source_name": "S"}},
    ])
    captured_prompts = []

    async def fake_run(prompt):
        captured_prompts.append(prompt)
        out = MagicMock()
        out.output = "answer"
        return out

    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=fake_run)

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent):
        cfg = kb_validation_service.RAGConfig(prompt_variant="bogus_variant")
        await kb_validation_service._generate_kb_answer(
            "kb-1", "Q?", "test-model", config=cfg
        )

    default_instr = kb_validation_service.RAG_PROMPT_VARIANTS["default"]
    assert default_instr in captured_prompts[0]


@pytest.mark.asyncio
async def test_generate_kb_answer_config_model_overrides_caller_model():
    fake_dm = MagicMock()
    fake_dm.query_kb = MagicMock(return_value=[
        {"content": "ctx", "metadata": {"source_name": "S"}},
    ])
    fake_run = MagicMock()
    fake_run.output = "answer"
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value=fake_run)

    with patch.object(kb_validation_service, "_get_dm", return_value=fake_dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent) as get_agent:
        cfg = kb_validation_service.RAGConfig(model="override-model")
        await kb_validation_service._generate_kb_answer(
            "kb-1", "Q?", "caller-model", config=cfg
        )

    # _get_or_build_agent receives the override, not the caller's model
    purpose, model_name, _system_prompt = get_agent.call_args.args[:3]
    assert model_name == "override-model"
    assert purpose.startswith("kb_rag::")


# ---------------------------------------------------------------------------
# rag_config_override on KnowledgeBase — Autovalidate apply path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_rag_config_uses_kb_override_when_no_explicit_config():
    """When no explicit config is passed, the KB's saved override is used."""
    fake_kb = MagicMock()
    fake_kb.rag_config_override = {"k": 14, "prompt_variant": "concise"}

    with patch.object(kb_validation_service, "KnowledgeBase") as KB:
        KB.find_one = AsyncMock(return_value=fake_kb)
        # Trigger resolution by calling the public path
        cfg = await kb_validation_service._resolve_rag_config("kb-1", None, k=8)

    assert cfg.k == 14
    assert cfg.prompt_variant == "concise"


@pytest.mark.asyncio
async def test_resolve_rag_config_explicit_wins_over_kb_override():
    """An explicit config (e.g. from an optimizer trial) wins outright."""
    fake_kb = MagicMock()
    fake_kb.rag_config_override = {"k": 14}
    explicit = kb_validation_service.RAGConfig(k=4)

    with patch.object(kb_validation_service, "KnowledgeBase") as KB:
        KB.find_one = AsyncMock(return_value=fake_kb)
        cfg = await kb_validation_service._resolve_rag_config("kb-1", explicit, k=8)

    assert cfg.k == 4  # explicit, not the override


@pytest.mark.asyncio
async def test_resolve_rag_config_invalid_override_falls_back_to_default():
    """Garbage in the override dict must not crash queries — it falls back."""
    fake_kb = MagicMock()
    fake_kb.rag_config_override = {"unknown_knob": "garbage", "k": 12}

    with patch.object(kb_validation_service, "KnowledgeBase") as KB:
        KB.find_one = AsyncMock(return_value=fake_kb)
        cfg = await kb_validation_service._resolve_rag_config("kb-1", None, k=8)

    # forbid-extra rejected the dict; we got the legacy default.
    assert cfg.k == 8
    assert cfg.prompt_variant == "default"


@pytest.mark.asyncio
async def test_resolve_rag_config_no_kb_or_no_override_uses_legacy_default():
    """KB missing or override absent → legacy behaviour."""
    with patch.object(kb_validation_service, "KnowledgeBase") as KB:
        KB.find_one = AsyncMock(return_value=None)
        cfg = await kb_validation_service._resolve_rag_config("kb-1", None, k=8)
    assert cfg.k == 8

    fake_kb = MagicMock()
    fake_kb.rag_config_override = None
    with patch.object(kb_validation_service, "KnowledgeBase") as KB:
        KB.find_one = AsyncMock(return_value=fake_kb)
        cfg = await kb_validation_service._resolve_rag_config("kb-1", None, k=10)
    assert cfg.k == 10


# ---------------------------------------------------------------------------
# Token accounting (real pydantic-ai usage flowing through helpers + judge)
# ---------------------------------------------------------------------------


def test_usage_tokens_sums_input_output_and_cache():
    """_usage_tokens() must include input + output + cache reads + cache writes."""
    run = MagicMock()
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50
    usage.cache_read_tokens = 30
    usage.cache_write_tokens = 20
    run.usage = MagicMock(return_value=usage)
    assert kb_validation_service._usage_tokens(run) == 200


def test_usage_tokens_returns_zero_when_usage_unavailable():
    """Any failure in run.usage() (e.g. mock default) should be safe."""
    run = MagicMock()
    run.usage = MagicMock(side_effect=Exception("no usage"))
    assert kb_validation_service._usage_tokens(run) == 0

    # None usage is also tolerated
    run2 = MagicMock()
    run2.usage = MagicMock(return_value=None)
    assert kb_validation_service._usage_tokens(run2) == 0


@pytest.mark.asyncio
async def test_judge_answer_records_token_usage():
    """_judge_answer must include tokens_used in its return dict."""
    fake_run = _make_mock_run('{"score": 0.8, "verdict": "PASS"}', tokens=850)
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value=fake_run)

    with patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent):
        verdict = await kb_validation_service._judge_answer(
            query="Q?", expected_answer="A.", actual_answer="A.",
            model_name="test-model",
        )
    assert verdict["tokens_used"] == 850
    assert verdict["score"] == 0.8
    assert verdict["verdict"] == "PASS"


@pytest.mark.asyncio
async def test_judge_answer_returns_zero_tokens_on_error():
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(side_effect=RuntimeError("model died"))
    with patch.object(kb_validation_service, "_get_or_build_agent", return_value=fake_agent):
        verdict = await kb_validation_service._judge_answer(
            query="Q?", expected_answer="A.", actual_answer="A.",
            model_name="test-model",
        )
    assert verdict["tokens_used"] == 0
    assert verdict["verdict"] == "WARN"  # error path


@pytest.mark.asyncio
async def test_judge_test_queries_aggregates_real_tokens():
    """In judge+baseline mode, tokens_used = sum(rag, baseline, with_judge, baseline_judge)."""
    tq = MagicMock()
    tq.uuid = "tq-1"
    tq.query = "Q?"
    tq.expected_answer = "A."
    tq.category = None
    tq.save = AsyncMock()

    async def fake_kb_answer(*a, **kw):
        return ("rag answer", [{"content": "ctx", "metadata": {"source_name": "S"}}], 1000)

    async def fake_baseline_answer(*a, **kw):
        return ("baseline answer", 500)

    async def fake_judge(*, query, expected_answer, actual_answer, model_name, retrieved_context=None, category=None):
        return {
            "score": 0.5, "verdict": "WARN", "confidence": 0.8,
            "reasoning": "...", "evidence": "", "missing_facts": [], "hallucinated_facts": [],
            "tokens_used": 200 if retrieved_context else 150,
        }

    with patch.object(kb_validation_service, "_generate_kb_answer", side_effect=fake_kb_answer), \
         patch.object(kb_validation_service, "_generate_baseline_answer", side_effect=fake_baseline_answer), \
         patch.object(kb_validation_service, "_judge_answer", side_effect=fake_judge):
        out = await kb_validation_service.judge_test_queries(
            "kb-1", [tq], "test-model", mode="judge+baseline",
        )

    # 1000 (rag) + 500 (baseline) + 200 (with-KB judge incl. context) + 150 (baseline judge)
    assert out["tokens_used"] == 1850
    assert out["details"][0]["tokens_used"] == 1850


@pytest.mark.asyncio
async def test_judge_test_queries_judge_only_mode_excludes_baseline_tokens():
    tq = MagicMock()
    tq.uuid = "tq-1"
    tq.query = "Q?"
    tq.expected_answer = "A."
    tq.category = None
    tq.save = AsyncMock()

    async def fake_kb_answer(*a, **kw):
        return ("rag answer", [{"content": "ctx", "metadata": {"source_name": "S"}}], 1000)

    async def fake_judge(**kw):
        return {
            "score": 0.7, "verdict": "PASS", "confidence": 0.9,
            "reasoning": "...", "evidence": "", "missing_facts": [], "hallucinated_facts": [],
            "tokens_used": 300,
        }

    with patch.object(kb_validation_service, "_generate_kb_answer", side_effect=fake_kb_answer), \
         patch.object(kb_validation_service, "_generate_baseline_answer") as bl, \
         patch.object(kb_validation_service, "_judge_answer", side_effect=fake_judge):
        out = await kb_validation_service.judge_test_queries(
            "kb-1", [tq], "test-model", mode="judge",
        )

    bl.assert_not_called()
    assert out["tokens_used"] == 1300  # 1000 (rag) + 300 (judge)


def test_knowledge_base_supports_rag_config_override_field():
    """KnowledgeBase model has the new override fields."""
    import datetime as dt
    from app.models.knowledge import KnowledgeBase
    kb = KnowledgeBase.model_construct(
        uuid="kb-1",
        title="t",
        user_id="u1",
        rag_config_override={"k": 12, "model": "claude-haiku-4-5"},
        rag_config_override_set_at=dt.datetime.now(tz=dt.timezone.utc),
        rag_config_override_run_uuid="opt-42",
    )
    d = kb.model_dump()
    assert d["rag_config_override"]["k"] == 12
    assert d["rag_config_override_run_uuid"] == "opt-42"

    # Backward compat: existing rows without overrides should still load.
    kb2 = KnowledgeBase.model_construct(uuid="kb-2", title="t", user_id="u1")
    d2 = kb2.model_dump()
    assert d2["rag_config_override"] is None
    assert d2["rag_config_override_set_at"] is None
    assert d2["rag_config_override_run_uuid"] is None
