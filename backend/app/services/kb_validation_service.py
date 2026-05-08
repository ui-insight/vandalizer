"""Knowledge Base validation service - retrieval precision, source health, chunk coverage,
and LLM-as-judge answer evaluation (with optional baseline ablation for lift measurement).
"""

import asyncio
import logging
from typing import Optional

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.models.kb_test_query import KBTestQuery
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
from app.services.document_manager import DocumentManager
from app.services.llm_service import RAG_SYSTEM_PROMPT, get_agent_model

logger = logging.getLogger(__name__)

_dm: DocumentManager | None = None

# Module-level agent cache. Key: (purpose, model_name). Each judge/answer agent
# is reused across queries within a process.
_agent_cache: dict[tuple[str, str], Agent] = {}


# Stripped-down system prompt for baseline (no-KB) answers — used to measure how
# well the model would do without retrieval. Kept intentionally minimal so we
# isolate the model's general knowledge from any agentic scaffolding.
BASELINE_SYSTEM_PROMPT = (
    "Answer the user's question using only your general knowledge. "
    "Be concise and direct. If you do not know the answer, say so explicitly "
    "rather than guessing."
)


# ---------------------------------------------------------------------------
# RAG configuration — used by both the live RAG path (default values match
# legacy behaviour) and the KB Autovalidate optimizer (sweeps these values).
# ---------------------------------------------------------------------------

DEFAULT_K = 8

# Each prompt variant tells the LLM how to use the retrieved context. The
# optimizer can sweep across these to find the variant that scores best for a
# given KB. ``default`` reproduces the legacy behaviour of _generate_kb_answer.
RAG_PROMPT_VARIANTS: dict[str, str] = {
    "default": (
        "Answer the question using only the retrieved context. If the context "
        "is insufficient, say so rather than guessing."
    ),
    "strict": (
        "Answer the question using ONLY facts that appear verbatim or in close "
        "paraphrase in the retrieved context. Quote source names when citing. "
        "If a fact is not in the context, do not include it. If the context is "
        "insufficient, reply: \"The knowledge base does not contain enough "
        "information to answer this question.\""
    ),
    "concise": (
        "Answer the question in 1-3 sentences using only the retrieved context. "
        "Lead with the direct answer. Omit hedging unless the context itself is "
        "ambiguous."
    ),
}


class RAGConfig(BaseModel):
    """Configurable retrieval/generation knobs.

    Default values reproduce the legacy ``_generate_kb_answer`` behaviour —
    callers that don't pass a config get the same answer they did before. The
    KB Autovalidate optimizer sweeps these knobs across trials.
    """

    k: int = DEFAULT_K
    model: Optional[str] = None         # None = caller's resolved user model
    prompt_variant: str = "default"     # key into RAG_PROMPT_VARIANTS
    query_rewriting: bool = False       # if True, rewrite the user query via prompt agent before retrieval
    source_label_visibility: bool = True  # include "## Source: name" headers in the context block

    model_config = {"extra": "forbid"}

    def with_overrides(self, **kw) -> "RAGConfig":
        """Return a copy with the given fields overridden."""
        return self.model_copy(update=kw)


def _format_context_for_config(results: list[dict], cfg: RAGConfig) -> str:
    """Render retrieved chunks for the RAG prompt, honouring config knobs."""
    blocks: list[str] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        content = (r.get("content") or "").strip()
        if not content:
            continue
        if cfg.source_label_visibility:
            meta = r.get("metadata") or {}
            source_name = meta.get("source_name", "Unknown") if isinstance(meta, dict) else "Unknown"
            blocks.append(f"## Source: {source_name}\n{content}")
        else:
            blocks.append(content)
    return "\n\n".join(blocks)


def _usage_tokens(run) -> int:
    """Pull a conservative total token count from a pydantic-ai AgentRunResult.

    Sums input + output + cache-read + cache-write so the optimizer's budget
    reflects all tokens the provider charged for. Returns 0 when usage isn't
    available (e.g. mocked agents in tests).
    """
    try:
        usage = run.usage()
    except Exception:
        return 0
    if usage is None:
        return 0
    return (
        getattr(usage, "input_tokens", 0)
        + getattr(usage, "output_tokens", 0)
        + getattr(usage, "cache_read_tokens", 0)
        + getattr(usage, "cache_write_tokens", 0)
    )


async def _maybe_rewrite_query(query: str, model_name: str) -> tuple[str, int]:
    """If query rewriting is enabled, ask a prompt agent to optimise the query
    for retrieval. Falls back to the original query on any failure. Returns
    (effective_query, tokens_used) so callers can credit the rewrite cost.
    """
    from app.services.llm_service import PROMPT_AGENT_SYSTEM_PROMPT

    agent = _get_or_build_agent("kb_query_rewriter", model_name, PROMPT_AGENT_SYSTEM_PROMPT)
    try:
        run = await agent.run(f"Generate a search prompt for this user question: {query}")
        rewritten = (run.output or "").strip()
        return (rewritten or query, _usage_tokens(run))
    except Exception as e:
        logger.warning("Query rewrite failed; falling back to raw query: %s", e)
        return (query, 0)


def _get_dm() -> DocumentManager:
    global _dm
    if _dm is None:
        _dm = DocumentManager()
    return _dm


def _get_or_build_agent(purpose: str, model_name: str, system_prompt: str, model_settings: dict | None = None) -> Agent:
    """Return a cached pydantic-ai Agent for the given purpose+model."""
    key = (purpose, model_name)
    cached = _agent_cache.get(key)
    if cached is not None:
        return cached
    model = get_agent_model(model_name)
    kwargs: dict = {"system_prompt": system_prompt}
    if model_settings:
        kwargs["model_settings"] = model_settings
    agent = Agent(model, **kwargs)
    _agent_cache[key] = agent
    return agent


def _format_retrieved_context(results: list[dict]) -> str:
    """Render query_kb output as labelled source blocks for the RAG prompt."""
    blocks: list[str] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        meta = r.get("metadata") or {}
        source_name = meta.get("source_name", "Unknown") if isinstance(meta, dict) else "Unknown"
        content = (r.get("content") or "").strip()
        if not content:
            continue
        blocks.append(f"## Source: {source_name}\n{content}")
    return "\n\n".join(blocks)


async def _resolve_rag_config(kb_uuid: str, explicit: Optional[RAGConfig], k: int) -> RAGConfig:
    """Pick the RAGConfig to use for a query.

    Resolution order:
      1. Explicit ``config`` argument (e.g. an optimizer trial) — wins outright.
      2. KB-level ``rag_config_override`` (set by Autovalidate's "apply") — used
         for normal user-facing queries on KBs with an applied optimization.
      3. Default config built from the legacy ``k`` argument — preserves
         pre-Autovalidate behaviour exactly.
    """
    if explicit is not None:
        return explicit
    try:
        kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
        override = getattr(kb, "rag_config_override", None) if kb else None
        if isinstance(override, dict) and override:
            try:
                return RAGConfig(**override)
            except Exception as e:
                logger.warning(
                    "rag_config_override on KB %s is invalid (%s); using defaults",
                    kb_uuid, e,
                )
    except Exception as e:
        logger.debug("KB lookup for rag_config_override failed: %s", e)
    return RAGConfig(k=k)


async def _generate_kb_answer(
    kb_uuid: str,
    query: str,
    model_name: str,
    k: int = DEFAULT_K,
    *,
    config: Optional[RAGConfig] = None,
) -> tuple[str, list[dict], int]:
    """Run a headless RAG query against the KB.

    Returns ``(answer, retrieved_chunks, tokens_used)``. Tokens reflect actual
    pydantic-ai usage (input + output + cache); used by the Autovalidate
    optimizer for accurate per-trial budget enforcement.

    Intentionally simpler than ``llm_service.create_rag_agent``: no tool loop,
    no document re-ingestion, no chat-conversation side effects. We're testing
    the KB+retrieval+generation fundamentals — not chat-agent UX.

    The optional ``config`` overrides retrieval-time knobs (k, prompt variant,
    query rewriting, source-label visibility, model). When ``config`` is
    omitted, we fall back first to the KB's ``rag_config_override`` (set by
    Autovalidate apply), then to the legacy ``k`` argument and the caller's
    model — preserving the pre-Autovalidate behaviour exactly.
    """
    cfg = await _resolve_rag_config(kb_uuid, config, k)
    effective_model = cfg.model or model_name
    tokens = 0

    # Optionally rewrite the query before retrieval.
    if cfg.query_rewriting:
        retrieval_query, rewrite_tokens = await _maybe_rewrite_query(query, effective_model)
        tokens += rewrite_tokens
    else:
        retrieval_query = query

    dm = _get_dm()
    results = await asyncio.to_thread(dm.query_kb, kb_uuid, retrieval_query, cfg.k)
    if not results:
        return ("I could not find any relevant information in the knowledge base.", [], tokens)

    context = _format_context_for_config(results, cfg)
    instruction = RAG_PROMPT_VARIANTS.get(cfg.prompt_variant, RAG_PROMPT_VARIANTS["default"])
    # Cache key includes the prompt variant so different variants don't collide.
    purpose = f"kb_rag::{cfg.prompt_variant}"
    agent = _get_or_build_agent(purpose, effective_model, RAG_SYSTEM_PROMPT)
    user_prompt = (
        f"Question: {query}\n\n"
        f"Retrieved context:\n{context}\n\n"
        f"{instruction}"
    )
    try:
        run = await agent.run(user_prompt)
        answer = (run.output or "").strip()
        tokens += _usage_tokens(run)
    except Exception as e:
        logger.exception("KB RAG answer generation failed for %s: %s", kb_uuid, e)
        answer = ""
    return answer, results, tokens


async def _generate_baseline_answer(query: str, model_name: str) -> tuple[str, int]:
    """Answer the query with no retrieved context — same model, no KB.

    Returns ``(answer, tokens_used)``. Used in analysis mode to compute
    lift = with-KB judge score - baseline judge score.
    """
    agent = _get_or_build_agent("kb_baseline", model_name, BASELINE_SYSTEM_PROMPT)
    try:
        run = await agent.run(f"Question: {query}")
        return ((run.output or "").strip(), _usage_tokens(run))
    except Exception as e:
        logger.exception("KB baseline answer generation failed: %s", e)
        return ("", 0)


# ---------------------------------------------------------------------------
# LLM-as-judge
# ---------------------------------------------------------------------------


KB_JUDGE_SYSTEM_PROMPT = (
    "You are evaluating an answer against a canonical expected answer.\n"
    "Return ONLY JSON (no markdown, no extra text) with this shape:\n"
    '{"score": 0.0..1.0, "verdict": "PASS|FAIL|WARN", "confidence": 0.0..1.0, '
    '"reasoning": "...", "evidence": "...", "missing_facts": [...], '
    '"hallucinated_facts": [...]}\n'
    "Scoring guide:\n"
    "- 1.0 = covers all expected facts, no contradictions, no hallucinations\n"
    "- 0.5 = partial coverage OR one minor hallucination\n"
    "- 0.0 = wrong, contradictory, or fabricated\n"
    "Be lenient on phrasing, strict on facts.\n"
    "Verdict mapping: score >= 0.7 -> PASS, 0.4..0.7 -> WARN, < 0.4 -> FAIL.\n"
)


def _parse_kb_verdict(raw) -> dict:
    """Normalise LLM output into a KB judge verdict dict.

    Extends the workflow validator's verdict shape with score, missing_facts,
    and hallucinated_facts.
    """
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if not isinstance(raw, dict):
        raw = {}

    try:
        score = max(0.0, min(1.0, float(raw.get("score", 0.0))))
    except (TypeError, ValueError):
        score = 0.0

    verdict = str(raw.get("verdict", "")).upper().strip()
    if verdict not in ("PASS", "FAIL", "WARN"):
        # Derive from score if model didn't supply a verdict.
        verdict = "PASS" if score >= 0.7 else ("WARN" if score >= 0.4 else "FAIL")

    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5

    def _str_list(v):
        if isinstance(v, list):
            return [str(x) for x in v if x is not None][:10]
        return []

    return {
        "score": score,
        "verdict": verdict,
        "confidence": confidence,
        "reasoning": str(raw.get("reasoning", ""))[:1000],
        "evidence": str(raw.get("evidence", ""))[:1000],
        "missing_facts": _str_list(raw.get("missing_facts")),
        "hallucinated_facts": _str_list(raw.get("hallucinated_facts")),
    }


async def _judge_answer(
    *,
    query: str,
    expected_answer: str,
    actual_answer: str,
    model_name: str,
    retrieved_context: str | None = None,
) -> dict:
    """Run the LLM judge on a single (expected, actual) pair. Returns a parsed verdict.

    ``retrieved_context`` is included for the with-KB judge so the model can
    distinguish hallucination from grounded paraphrase. The baseline judge omits it.
    """
    # Lazy import to keep module import cheap.
    from app.services.workflow_validator import _extract_json

    agent = _get_or_build_agent(
        "kb_judge",
        model_name,
        KB_JUDGE_SYSTEM_PROMPT,
        model_settings={"temperature": 0.0},
    )

    parts = [
        f"Query:\n{query}",
        f"Expected answer:\n{expected_answer}",
        f"Actual answer:\n{actual_answer if actual_answer else '(empty)'}",
    ]
    if retrieved_context:
        # Truncate so the judge prompt stays manageable.
        parts.append(f"Retrieved context excerpt:\n{retrieved_context[:4000]}")
    user_prompt = "\n\n".join(parts)

    try:
        run = await agent.run(user_prompt)
        raw = _extract_json(run.output or "")
        tokens = _usage_tokens(run)
    except Exception as e:
        logger.exception("KB judge call failed: %s", e)
        return {
            "score": 0.0,
            "verdict": "WARN",
            "confidence": 0.0,
            "reasoning": f"judge error: {str(e)[:200]}",
            "evidence": "",
            "missing_facts": [],
            "hallucinated_facts": [],
            "tokens_used": 0,
        }
    verdict = _parse_kb_verdict(raw)
    verdict["tokens_used"] = tokens
    return verdict


def _classify_discrimination(with_kb_score: float, baseline_score: float | None) -> str:
    """Categorise a query by what its judge scores tell us about KB value."""
    if baseline_score is None:
        return "other"
    lift = with_kb_score - baseline_score
    if lift > 0.3:
        return "useful"
    if with_kb_score >= 0.7 and baseline_score >= 0.7:
        return "redundant"
    if with_kb_score < 0.5 and baseline_score < 0.5:
        return "failing"
    return "other"


async def judge_test_queries(
    kb_uuid: str,
    test_queries: list,
    model_name: str,
    *,
    mode: str = "judge",
    concurrency: int = 4,
) -> dict:
    """Run RAG (and optionally baseline) + judge per query in parallel.

    Returns a dict with per-query details and aggregates suitable for merging
    into the retrieval_precision result block.

    Skips queries with no ``expected_answer`` (records ``judge: None``). Catches
    per-query exceptions so one bad query doesn't fail the whole run.
    """
    judgeable = [tq for tq in test_queries if getattr(tq, "expected_answer", None)]
    skipped = [tq for tq in test_queries if not getattr(tq, "expected_answer", None)]

    sem = asyncio.Semaphore(max(1, concurrency))
    include_baseline = mode == "judge+baseline"

    async def judge_one(tq) -> dict:
        async with sem:
            try:
                kb_result = await _generate_kb_answer(
                    kb_uuid, tq.query, model_name
                )
                # Backward-compat: callers/mocks may return 2-tuple (legacy).
                if len(kb_result) == 3:
                    actual_answer, retrieved, kb_tokens = kb_result
                else:
                    actual_answer, retrieved = kb_result
                    kb_tokens = 0
                context = _format_retrieved_context(retrieved) if retrieved else None
                with_judge = await _judge_answer(
                    query=tq.query,
                    expected_answer=tq.expected_answer,
                    actual_answer=actual_answer,
                    model_name=model_name,
                    retrieved_context=context,
                )

                baseline_answer = None
                baseline_judge = None
                baseline_tokens = 0
                lift = None
                if include_baseline:
                    bl = await _generate_baseline_answer(tq.query, model_name)
                    if isinstance(bl, tuple):
                        baseline_answer, baseline_tokens = bl
                    else:  # legacy mock returning bare string
                        baseline_answer, baseline_tokens = bl, 0
                    baseline_judge = await _judge_answer(
                        query=tq.query,
                        expected_answer=tq.expected_answer,
                        actual_answer=baseline_answer,
                        model_name=model_name,
                        retrieved_context=None,
                    )
                    lift = with_judge["score"] - baseline_judge["score"]

                discrimination = _classify_discrimination(
                    with_judge["score"],
                    baseline_judge["score"] if baseline_judge else None,
                )

                tokens_used = (
                    kb_tokens
                    + baseline_tokens
                    + int(with_judge.get("tokens_used", 0) or 0)
                    + (int(baseline_judge.get("tokens_used", 0) or 0) if baseline_judge else 0)
                )

                return {
                    "query_uuid": getattr(tq, "uuid", ""),
                    "query": tq.query,
                    "category": getattr(tq, "category", None),
                    "actual_answer": (actual_answer or "")[:2000],
                    "baseline_answer": (baseline_answer or "")[:2000] if baseline_answer is not None else None,
                    "judge": with_judge,
                    "baseline_judge": baseline_judge,
                    "lift": round(lift, 3) if lift is not None else None,
                    "discrimination": discrimination,
                    "tokens_used": tokens_used,
                }
            except Exception as e:
                logger.exception("judge_test_queries: per-query failure for %s: %s", getattr(tq, "uuid", "?"), e)
                return {
                    "query_uuid": getattr(tq, "uuid", ""),
                    "query": tq.query,
                    "category": getattr(tq, "category", None),
                    "actual_answer": "",
                    "baseline_answer": None,
                    "judge": {
                        "score": 0.0,
                        "verdict": "SKIPPED",
                        "confidence": 0.0,
                        "reasoning": f"per-query failure: {str(e)[:200]}",
                        "evidence": "",
                        "missing_facts": [],
                        "hallucinated_facts": [],
                        "tokens_used": 0,
                    },
                    "baseline_judge": None,
                    "lift": None,
                    "discrimination": "other",
                    "tokens_used": 0,
                }

    judged_results = await asyncio.gather(*(judge_one(tq) for tq in judgeable))

    # Persist last_judged_score / last_judged_at on each judged query (best-effort).
    import datetime as _dt
    now = _dt.datetime.now(tz=_dt.timezone.utc)
    for tq, jr in zip(judgeable, judged_results):
        try:
            tq.last_judged_score = float(jr["judge"]["score"])
            tq.last_judged_at = now
            if hasattr(tq, "save"):
                await tq.save()
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("Could not persist last_judged_* on query %s: %s", getattr(tq, "uuid", "?"), e)

    # Append "skipped — no expected_answer" entries so the UI sees them.
    for tq in skipped:
        judged_results.append({
            "query_uuid": getattr(tq, "uuid", ""),
            "query": tq.query,
            "category": getattr(tq, "category", None),
            "actual_answer": "",
            "baseline_answer": None,
            "judge": None,
            "baseline_judge": None,
            "lift": None,
            "discrimination": None,
        })

    # Aggregates.
    judged_scores = [r["judge"]["score"] for r in judged_results if r["judge"] is not None]
    baseline_scores = [
        r["baseline_judge"]["score"] for r in judged_results
        if r["baseline_judge"] is not None
    ]
    avg_judge_score = sum(judged_scores) / len(judged_scores) if judged_scores else None
    avg_baseline_score = sum(baseline_scores) / len(baseline_scores) if baseline_scores else None
    avg_lift = (
        avg_judge_score - avg_baseline_score
        if (avg_judge_score is not None and avg_baseline_score is not None)
        else None
    )

    summary_counts = {"useful": 0, "redundant": 0, "failing": 0, "other": 0}
    for r in judged_results:
        d = r.get("discrimination")
        if d in summary_counts:
            summary_counts[d] += 1

    tokens_used = sum(int(r.get("tokens_used", 0) or 0) for r in judged_results)

    return {
        "details": judged_results,
        "num_queries_judged": len(judged_scores),
        "num_queries_baselined": len(baseline_scores),
        "avg_judge_score": round(avg_judge_score, 3) if avg_judge_score is not None else None,
        "avg_baseline_score": round(avg_baseline_score, 3) if avg_baseline_score is not None else None,
        "avg_lift": round(avg_lift, 3) if avg_lift is not None else None,
        "discrimination_summary": summary_counts,
        "tokens_used": tokens_used,
    }


async def _sample_judge_variance(
    kb_uuid: str,
    judged_details: list[dict],
    test_queries_by_uuid: dict,
    model_name: str,
) -> tuple[float | None, int]:
    """Re-judge a small sample to estimate judge nondeterminism.

    Picks up to 2 queries that were successfully judged, re-runs the judge once
    each, and returns ``(variance, tokens_used)``. Variance is None when we
    can't sample meaningfully (e.g. fewer than 2 judged queries). Tokens still
    accumulate across attempted samples so the optimizer's budget tracking is
    accurate even when the variance estimate is inconclusive.
    """
    candidates = [d for d in judged_details if d.get("judge") and d["judge"].get("verdict") != "SKIPPED"]
    if len(candidates) < 2:
        return (None, 0)

    sample = candidates[:2]
    deltas: list[float] = []
    tokens = 0
    for d in sample:
        tq = test_queries_by_uuid.get(d["query_uuid"])
        if not tq or not getattr(tq, "expected_answer", None):
            continue
        try:
            replay = await _judge_answer(
                query=tq.query,
                expected_answer=tq.expected_answer,
                actual_answer=d.get("actual_answer", "") or "",
                model_name=model_name,
                retrieved_context=None,
            )
            deltas.append(abs(d["judge"]["score"] - replay["score"]))
            tokens += int(replay.get("tokens_used", 0) or 0)
        except Exception:
            continue
    if not deltas:
        return (None, tokens)
    # stddev of single-shot deltas; for n=1..2 this is just mean abs delta — close enough as a noise floor.
    mean = sum(deltas) / len(deltas)
    variance = sum((x - mean) ** 2 for x in deltas) / len(deltas)
    return (round(variance ** 0.5, 4), tokens)


async def check_source_health(kb_uuid: str) -> dict:
    """Check health of all sources in a knowledge base.

    For URL sources: HTTP HEAD check.
    For document sources: verify SmartDocument still has text.
    """
    from app.models.document import SmartDocument

    sources = await KnowledgeBaseSource.find(
        KnowledgeBaseSource.knowledge_base_uuid == kb_uuid,
    ).to_list()

    if not sources:
        return {"total": 0, "healthy": 0, "unhealthy": 0, "ratio": 1.0, "details": []}

    details = []
    healthy = 0

    for source in sources:
        entry = {
            "uuid": source.uuid,
            "source_type": source.source_type,
            "name": source.url_title or source.url or source.document_uuid or "Unknown",
            "status": "unknown",
        }

        if source.source_type == "url" and source.url:
            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    resp = await client.head(source.url)
                    if resp.status_code < 400:
                        entry["status"] = "healthy"
                        healthy += 1
                    else:
                        entry["status"] = "unhealthy"
                        entry["error"] = f"HTTP {resp.status_code}"
            except Exception as e:
                entry["status"] = "unhealthy"
                entry["error"] = str(e)[:200]
        elif source.source_type == "document" and source.document_uuid:
            doc = await SmartDocument.find_one(SmartDocument.uuid == source.document_uuid)
            if doc and (doc.raw_text or "").strip():
                entry["status"] = "healthy"
                healthy += 1
            else:
                entry["status"] = "unhealthy"
                entry["error"] = "Document not found or has no text"
        else:
            entry["status"] = "unhealthy"
            entry["error"] = "Missing source reference"

        details.append(entry)

    total = len(sources)
    return {
        "total": total,
        "healthy": healthy,
        "unhealthy": total - healthy,
        "ratio": healthy / total if total > 0 else 0.0,
        "details": details,
    }


async def check_chunk_coverage(kb_uuid: str) -> dict:
    """Check chunk coverage - what fraction of sources have chunks."""
    sources = await KnowledgeBaseSource.find(
        KnowledgeBaseSource.knowledge_base_uuid == kb_uuid,
    ).to_list()

    if not sources:
        return {"total": 0, "with_chunks": 0, "without_chunks": 0, "ratio": 1.0, "total_chunks": 0}

    with_chunks = sum(1 for s in sources if s.chunk_count > 0)
    total_chunks = sum(s.chunk_count for s in sources)

    return {
        "total": len(sources),
        "with_chunks": with_chunks,
        "without_chunks": len(sources) - with_chunks,
        "ratio": with_chunks / len(sources) if sources else 0.0,
        "total_chunks": total_chunks,
    }


async def check_retrieval_precision(
    kb_uuid: str,
    test_queries: list[KBTestQuery],
) -> dict:
    """Test retrieval quality against sample queries.

    For each query, runs semantic search and checks if expected sources appear in top results.
    """
    if not test_queries:
        return {"total_queries": 0, "avg_precision": 0.0, "details": []}

    dm = _get_dm()
    details = []
    precision_sum = 0.0

    for tq in test_queries:
        try:
            results = await asyncio.to_thread(dm.query_kb, kb_uuid, tq.query, 8)
        except Exception as e:
            details.append({
                "query": tq.query,
                "precision": 0.0,
                "error": str(e)[:200],
            })
            continue

        if not results:
            details.append({"query": tq.query, "precision": 0.0, "retrieved_sources": []})
            continue

        # query_kb returns list[dict] with shape {"content", "metadata"}; tuple-unpacking
        # silently iterated dict keys before, so source_name was always empty.
        retrieved_sources = []
        for r in results:
            metadata = r.get("metadata") if isinstance(r, dict) else None
            source_name = metadata.get("source_name", "") if isinstance(metadata, dict) else ""
            retrieved_sources.append(source_name)

        if tq.expected_source_labels:
            hits = sum(
                1 for label in tq.expected_source_labels
                if any(label.lower() in src.lower() for src in retrieved_sources)
            )
            precision = hits / len(tq.expected_source_labels) if tq.expected_source_labels else 0.0
        else:
            # If no expected labels, just check we got results
            precision = 1.0 if results else 0.0

        # Check expected_answer_contains if set
        answer_match = None
        if tq.expected_answer_contains:
            combined_text = " ".join(
                r["content"] for r in results if isinstance(r, dict) and r.get("content")
            )
            answer_match = tq.expected_answer_contains.lower() in combined_text.lower()
            if not answer_match:
                precision *= 0.5  # Penalize if expected content not found

        precision_sum += precision
        details.append({
            "query": tq.query,
            "precision": round(precision, 3),
            "retrieved_sources": retrieved_sources[:5],
            "expected_sources": tq.expected_source_labels,
            "answer_match": answer_match,
        })

    avg_precision = precision_sum / len(test_queries) if test_queries else 0.0

    return {
        "total_queries": len(test_queries),
        "avg_precision": round(avg_precision, 3),
        "details": details,
    }


async def run_kb_validation(
    kb_uuid: str,
    user_id: str,
    *,
    mode: str = "judge",
    skip_judge: bool = False,
) -> dict:
    """Run full validation on a knowledge base.

    Combines source health, chunk coverage, retrieval precision, and (when test
    queries have ``expected_answer``) an LLM judge over actual RAG answers.

    Modes:
      - ``"judge"`` (default): RAG answer + with-KB judge per query.
      - ``"judge+baseline"``: also generates a no-KB baseline answer + judge per
        query, computing per-query lift and a discrimination summary. Used by
        the manual UI run; daily ``quality_monitor`` uses ``"judge"`` to
        control cost.

    ``skip_judge=True`` short-circuits the judge entirely (still fixes the
    bug-free retrieval-precision substring match) — used for cheap re-runs.
    """
    kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid)
    if not kb:
        raise ValueError("Knowledge base not found")

    # Run health and coverage checks in parallel
    health_task = check_source_health(kb_uuid)
    coverage_task = check_chunk_coverage(kb_uuid)
    test_queries = await KBTestQuery.find(
        KBTestQuery.knowledge_base_uuid == kb_uuid,
    ).to_list()

    health, coverage = await asyncio.gather(health_task, coverage_task)

    # Run retrieval precision if test queries exist
    retrieval = await check_retrieval_precision(kb_uuid, test_queries) if test_queries else {
        "total_queries": 0, "avg_precision": 0.0, "details": [],
    }

    # LLM judge — gated by skip_judge AND presence of expected_answer on any query.
    judge_payload: dict | None = None
    judge_model_used: str | None = None
    judge_variance: float | None = None
    if test_queries and not skip_judge and any(getattr(q, "expected_answer", None) for q in test_queries):
        try:
            # Resolve the model lazily and off the event loop (sync pymongo helper).
            from app.services.workflow_validator import _resolve_model_name as _resolve_sync
            judge_model_used = await asyncio.to_thread(_resolve_sync, user_id)
            if judge_model_used:
                judge_payload = await judge_test_queries(
                    kb_uuid, test_queries, judge_model_used, mode=mode,
                )
                # First-run variance sample: only when no prior ValidationRun exists for this KB.
                from app.models.validation_run import ValidationRun
                prior = await ValidationRun.find_one(
                    ValidationRun.item_kind == "knowledge_base",
                    ValidationRun.item_id == kb_uuid,
                )
                if prior is None:
                    by_uuid = {q.uuid: q for q in test_queries}
                    judge_variance, _variance_tokens = await _sample_judge_variance(
                        kb_uuid, judge_payload["details"], by_uuid, judge_model_used,
                    )
                    # Variance sampling tokens add to the run's accounting so
                    # the persisted ValidationRun reflects all token spend.
                    judge_payload["tokens_used"] = (
                        int(judge_payload.get("tokens_used", 0) or 0) + _variance_tokens
                    )
        except Exception as e:
            logger.exception("KB judge skipped due to error: %s", e)
            judge_payload = None

    # Merge judge details into retrieval.details by query (tolerate missing matches).
    if judge_payload:
        judge_by_uuid = {d.get("query_uuid"): d for d in judge_payload["details"]}
        for det in retrieval.get("details", []):
            # check_retrieval_precision currently keys details by query string; we add query_uuid lookup via test_queries order.
            pass
        # Build a query→uuid lookup so we can stitch details together by query string.
        q_to_uuid = {q.query: q.uuid for q in test_queries}
        for det in retrieval.get("details", []):
            qstr = det.get("query")
            uuid_for = q_to_uuid.get(qstr)
            judge_det = judge_by_uuid.get(uuid_for) if uuid_for else None
            if judge_det:
                det["query_uuid"] = uuid_for
                det["category"] = judge_det.get("category")
                det["actual_answer"] = judge_det.get("actual_answer")
                det["baseline_answer"] = judge_det.get("baseline_answer")
                det["judge"] = judge_det.get("judge")
                det["baseline_judge"] = judge_det.get("baseline_judge")
                det["lift"] = judge_det.get("lift")
                det["discrimination"] = judge_det.get("discrimination")
        # Append details for judged queries that retrieval didn't cover (defensive).
        existing_uuids = {det.get("query_uuid") for det in retrieval.get("details", [])}
        for det in judge_payload["details"]:
            if det.get("query_uuid") and det["query_uuid"] not in existing_uuids:
                retrieval.setdefault("details", []).append(det)
        # Top-level aggregates.
        retrieval["avg_judge_score"] = judge_payload.get("avg_judge_score")
        retrieval["avg_baseline_score"] = judge_payload.get("avg_baseline_score")
        retrieval["avg_lift"] = judge_payload.get("avg_lift")
        retrieval["num_queries_judged"] = judge_payload.get("num_queries_judged", 0)
        retrieval["num_queries_baselined"] = judge_payload.get("num_queries_baselined", 0)
        retrieval["discrimination_summary"] = judge_payload.get("discrimination_summary")
        retrieval["judge_variance"] = judge_variance

    # Scoring.
    retrieval_score = retrieval["avg_precision"] * 100
    health_score = health["ratio"] * 100
    coverage_score = coverage["ratio"] * 100

    judge_avg = retrieval.get("avg_judge_score") if judge_payload else None
    if test_queries and judge_avg is not None and retrieval.get("num_queries_judged", 0) > 0:
        # Judge-based weights: judge 40% + retrieval 25% + health 20% + coverage 15%
        judge_score = judge_avg * 100
        raw_score = (
            judge_score * 0.40
            + retrieval_score * 0.25
            + health_score * 0.20
            + coverage_score * 0.15
        )
    elif test_queries:
        # Retrieval-only (legacy / no expected_answer present).
        raw_score = retrieval_score * 0.5 + health_score * 0.3 + coverage_score * 0.2
    else:
        # No test queries — weight health and coverage.
        raw_score = health_score * 0.6 + coverage_score * 0.4

    result = {
        "kb_uuid": kb_uuid,
        "kb_title": kb.title,
        "source_health": health,
        "chunk_coverage": coverage,
        "retrieval_precision": retrieval,
        "raw_score": round(raw_score, 1),
        "num_test_queries": len(test_queries),
        "num_sources": health["total"],
        # Match the shape expected by persist_validation_run
        "sources": [{"label": s["name"], "status": s["status"]} for s in health["details"]],
        "num_runs": 1,
        "mode": mode,
        "judge_model": judge_model_used,
    }

    # Persist the validation run
    from app.services.quality_service import persist_validation_run

    await persist_validation_run(
        item_kind="knowledge_base",
        item_id=kb_uuid,
        item_name=kb.title,
        run_type="kb_validation",
        result=result,
        user_id=user_id,
    )

    return result
