"""Extraction LLM judge — semantic-equality scoring for field values.

Strict-match (in ``extraction_validation_service._values_match``) flags many
borderline-correct extractions as failures: "Jan 5, 2026" vs "2026-01-05",
"Smith, John" vs "John Smith", "$1,000" vs "1000". The judge resolves these
without hand-tuning per-field comparators.

Phase 1B addition. Strict-match remains the default and the regression check;
the optimizer uses judge scores when ``include_judge=True``.

Shape:
    judge_field_value(field_name, expected, actual, model_name) -> dict
        Returns {score: 0..1, verdict: PASS|PARTIAL|FAIL, reasoning, tokens_used}.
    judge_test_case_extraction(keys, expected, actual, model_name) -> dict
        Per-field judgements + aggregate avg_score for one test case.
"""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from typing import Any

from pydantic_ai.agent import Agent

from app.models.system_config import SystemConfig
from app.services.llm_service import get_agent_model

logger = logging.getLogger(__name__)


EXTRACTION_JUDGE_SYSTEM_PROMPT = (
    "You evaluate ONE extracted field value against its expected value.\n"
    "Be lenient on phrasing/format, strict on facts. Length is not quality:\n"
    "a longer answer is NOT a better answer — never credit verbosity.\n"
    "Return ONLY JSON (no markdown, no extra text):\n"
    '{"score": 0.0..1.0, "verdict": "PASS|PARTIAL|FAIL", "reasoning": "..."}\n'
    "\n"
    "Scoring anchors:\n"
    "  1.0 — Same fact, any reasonable formatting variation. Examples:\n"
    "    'Jan 5, 2026' ≡ '2026-01-05'\n"
    "    'Smith, John' ≡ 'John Smith'\n"
    "    '$1,000' ≡ '1000' ≡ '1,000.00'\n"
    "    'USA' ≡ 'United States'\n"
    "  0.5 — Right fact buried in extra text that adds NO information\n"
    "        (a label, restating the question, or unit annotation), OR\n"
    "        one of several equally-valid forms when the field genuinely\n"
    "        has multiple right answers. Mere wordiness alone is not 0.5.\n"
    "  0.0 — Wrong fact, hallucinated value, contradicts expected, or\n"
    "        contains both the right answer and a contradicting wrong answer.\n"
    "\n"
    "Multi-valued fields (lists, sets, comma-separated): order does NOT\n"
    "matter. If actual is missing required elements OR contains extras\n"
    "not in expected, score 0.5 (PARTIAL). All elements match → 1.0.\n"
    "\n"
    "Absence equality: if BOTH expected and actual indicate 'not found'\n"
    "(empty, 'N/A', 'not present', '-', 'unknown'), score 1.0. If only\n"
    "one is absent, score 0.0.\n"
    "\n"
    "Verdict mapping: score ≥ 0.7 → PASS, 0.4–0.7 → PARTIAL, < 0.4 → FAIL.\n"
    "Reasoning must be ≤ 30 words and cite the specific discrepancy, not\n"
    "restate the values.\n"
)


# Pydantic-ai agents are stateful: each carries an httpx pool bound (via
# get_agent_model -> _get_loop_http_client) to the event loop that built it.
# Celery runs each task on its own loop, so an agent cached on a prior task's
# (now-closed) loop fails a later call with "bound to a different event loop",
# which the OpenAI SDK re-wraps as a zero-token "Connection error". Key the cache
# on (loop, agent) and reuse only within the same running loop — see the same
# fix in kb_validation_service._get_or_build_agent and the rule documented in
# llm_service.create_chat_agent.
_agent_cache: dict[str, tuple[asyncio.AbstractEventLoop, Agent]] = {}
_system_config_doc_ctx: ContextVar[dict | None] = ContextVar("_ej_sys_cfg", default=None)


async def _ensure_system_config_loaded() -> None:
    if _system_config_doc_ctx.get() is not None:
        return
    sys_cfg = await SystemConfig.get_config()
    _system_config_doc_ctx.set(sys_cfg.model_dump() if sys_cfg else {})


def _get_agent(model_name: str) -> Agent:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    cached = _agent_cache.get(model_name)
    if cached is not None and loop is not None and cached[0] is loop:
        return cached[1]

    model = get_agent_model(
        model_name,
        system_config_doc=_system_config_doc_ctx.get(),
    )
    agent = Agent(
        model,
        system_prompt=EXTRACTION_JUDGE_SYSTEM_PROMPT,
        model_settings={"temperature": 0.0},
    )
    if loop is not None:
        _agent_cache[model_name] = (loop, agent)
    return agent


def _usage_tokens(run: Any) -> int:
    try:
        usage = run.usage() if callable(getattr(run, "usage", None)) else None
        if usage is None:
            return 0
        return int(
            getattr(usage, "total_tokens", 0)
            or (getattr(usage, "request_tokens", 0) + getattr(usage, "response_tokens", 0))
        )
    except Exception:
        return 0


def _extract_json(text: str) -> dict | list:
    """Strip markdown fences and parse JSON. Mirrors workflow_validator helper."""
    import json
    s = (text or "").strip()
    if s.startswith("```"):
        # Strip ```json ... ``` or ``` ... ``` fences
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[: -3]
        s = s.strip()
    # Fall back to substring slice when the model wrapped the JSON in prose
    if not (s.startswith("{") or s.startswith("[")):
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            s = s[start : end + 1]
    try:
        return json.loads(s)
    except Exception:
        return {}


def _parse_verdict(raw: Any) -> dict:
    """Normalise model output into the judge verdict shape."""
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if not isinstance(raw, dict):
        raw = {}

    try:
        score = max(0.0, min(1.0, float(raw.get("score", 0.0))))
    except (TypeError, ValueError):
        score = 0.0

    verdict = str(raw.get("verdict", "")).upper().strip()
    if verdict not in ("PASS", "PARTIAL", "FAIL"):
        verdict = "PASS" if score >= 0.7 else ("PARTIAL" if score >= 0.4 else "FAIL")

    return {
        "score": score,
        "verdict": verdict,
        "reasoning": str(raw.get("reasoning", ""))[:500],
    }


async def judge_field_value(
    *,
    field_name: str,
    expected: str,
    actual: str | None,
    model_name: str,
    field_metadata: dict | None = None,
) -> dict:
    """Judge a single (expected, actual) pair for one field.

    Returns ``{score, verdict, reasoning, tokens_used, comparator}``. On judge
    failure returns ``verdict='FAIL', score=0.0`` rather than raising — the
    caller is typically inside a per-trial loop and one judge error shouldn't
    crash the whole trial.

    For dates/numbers/enums/exact-string matches, the deterministic pre-judge
    router resolves the comparison without an LLM call (``comparator="deterministic"``).
    Only ambiguous cases reach the LLM (``comparator="llm"``).
    """
    # Deterministic short-circuit first — saves an LLM call when the comparison
    # is unambiguous (dates, numbers, enums, exact-or-normalized matches).
    from app.services.extraction_judge_router import prejudge
    prejudged = prejudge(
        field_name=field_name,
        expected=expected,
        actual=actual,
        field_metadata=field_metadata,
    )
    if prejudged is not None:
        return prejudged

    await _ensure_system_config_loaded()
    agent = _get_agent(model_name)

    user_prompt = (
        f"Field: {field_name}\n"
        f"Expected: {expected}\n"
        f"Actual: {actual if actual is not None and actual != '' else '(empty)'}"
    )

    try:
        run = await agent.run(user_prompt)
        raw = _extract_json(run.output or "")
        tokens = _usage_tokens(run)
    except Exception as e:
        logger.exception("Extraction judge call failed for field %s: %s", field_name, e)
        return {
            "score": 0.0,
            "verdict": "FAIL",
            "reasoning": f"judge error: {str(e)[:200]}",
            "tokens_used": 0,
            "comparator": "llm_error",
        }

    verdict = _parse_verdict(raw)
    verdict["tokens_used"] = tokens
    verdict["comparator"] = "llm"
    return verdict


async def judge_test_case_extraction(
    *,
    keys: list[str],
    expected: dict[str, Any],
    actual: dict[str, Any],
    model_name: str,
    concurrency: int = 4,
    field_metadata_by_key: dict[str, dict] | None = None,
) -> dict:
    """Judge every expected-valued field for one test-case extraction.

    Returns:
        {
          "fields": [{field, score, verdict, reasoning}, ...],
          "avg_score": float,
          "num_fields_judged": int,
          "tokens_used": int,
        }

    Skips fields that have no expected value (we can't judge what we can't
    compare). The aggregate is over fields actually judged.
    """
    sem = asyncio.Semaphore(max(1, concurrency))

    async def judge_one(field: str) -> dict:
        exp = expected.get(field)
        if exp is None or exp == "":
            return {"field": field, "skipped": True}
        async with sem:
            v = await judge_field_value(
                field_name=field,
                expected=str(exp),
                actual=str(actual.get(field, "")) if actual.get(field) is not None else "",
                model_name=model_name,
                field_metadata=(field_metadata_by_key or {}).get(field),
            )
        return {
            "field": field,
            "score": v["score"],
            "verdict": v["verdict"],
            "reasoning": v["reasoning"],
            "tokens_used": v.get("tokens_used", 0),
        }

    field_results = await asyncio.gather(*(judge_one(k) for k in keys))
    judged = [r for r in field_results if not r.get("skipped")]
    avg = sum(r["score"] for r in judged) / len(judged) if judged else 0.0
    tokens = sum(int(r.get("tokens_used", 0) or 0) for r in judged)

    return {
        "fields": field_results,
        "avg_score": round(avg, 4),
        "num_fields_judged": len(judged),
        "tokens_used": tokens,
    }
