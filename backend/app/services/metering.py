"""Central LLM token metering.

Every LLM call flows through the MeteredModel wrapper (llm_service.py), which
calls record_usage() once per model HTTP request. record_usage() accrues into
the metering scope set by the nearest enclosing `metered()` / `metered_async()`
context manager, and on scope exit one LlmUsageRecord is written (plus the
linked ActivityEvent's token fields, when an activity_id is set).

Why a contextvar instead of threading a usage object through every call site:
the chokepoint is deep in pydantic-ai (the Model), far below the call sites that
know *who* and *which feature*. A contextvar lets the call site declare context
once and have it picked up automatically by every (possibly nested) LLM call
underneath — including RAG tool sub-calls and workflow nodes. Workflow nodes run
on a ThreadPoolExecutor, which does not copy contextvars automatically; the
engine is patched to run each node within a copied context so the scope
propagates (see workflow_engine.process).
"""

from __future__ import annotations

import contextlib
import logging
import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterator, Optional

# Sentinel feature for calls that fire with no scope set (see record_usage).
from app.models.llm_usage import UNATTRIBUTED_FEATURE

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN_FALLBACK = 4


# ---------------------------------------------------------------------------
# Token estimation (used when the provider/gateway returns no usage)
# ---------------------------------------------------------------------------
_encoding: Any = None
_encoding_failed = False


def _get_encoding():
    global _encoding, _encoding_failed
    if _encoding is None and not _encoding_failed:
        try:
            import tiktoken

            _encoding = tiktoken.get_encoding("cl100k_base")
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("tiktoken unavailable, using char heuristic: %s", e)
            _encoding_failed = True
    return _encoding


def estimate_tokens(text: str) -> int:
    """Best-effort token count for a string. Never raises."""
    if not text:
        return 0
    enc = _get_encoding()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:  # pragma: no cover - defensive
            pass
    return max(1, len(text) // _CHARS_PER_TOKEN_FALLBACK)


def _text_of(obj: Any) -> str:
    """Pull display text out of a pydantic-ai message/part, best-effort."""
    content = getattr(obj, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        return " ".join(_text_of(c) for c in content)
    # request parts hold their text under .content; tool parts under .args etc.
    return content if isinstance(content, str) else ""


def estimate_messages_tokens(messages: Any) -> int:
    """Estimate input tokens from a list of pydantic-ai ModelMessages."""
    total = 0
    try:
        for msg in messages or []:
            for part in getattr(msg, "parts", []) or []:
                total += estimate_tokens(_text_of(part))
    except Exception:  # pragma: no cover - defensive
        return 0
    return total


def estimate_parts_tokens(parts: Any) -> int:
    """Estimate output tokens from a ModelResponse's parts."""
    total = 0
    try:
        for part in parts or []:
            total += estimate_tokens(_text_of(part))
    except Exception:  # pragma: no cover - defensive
        return 0
    return total


# ---------------------------------------------------------------------------
# Metering scope
# ---------------------------------------------------------------------------
@dataclass
class MeterScope:
    feature: str
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    space: Optional[str] = None
    activity_id: Optional[str] = None
    model: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    requests: int = 0
    estimated: bool = False
    # Every model the scope's calls used, by workflow step: (step index, step
    # name, model) -> [tokens in, tokens out, requests]. ``model`` above keeps
    # only the first, which is all the ledger row has room for; a run whose
    # steps override the model, or that falls back to another, used several
    # (support ticket: History couldn't say which model ran). Step is
    # (None, None) outside a workflow step.
    usage: dict = field(default_factory=dict)
    # A multi-task workflow step makes its calls from several threads at once.
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


# The workflow step whose calls are being made: (index, name). Set by the
# workflow engine around each step; the step's worker threads copy it.
_current_step: ContextVar[Optional[tuple[int, str]]] = ContextVar(
    "llm_meter_step", default=None
)


@contextlib.contextmanager
def metered_step(index: int, name: str) -> Iterator[None]:
    """Attribute the LLM calls made inside to workflow step ``index``."""
    token = _current_step.set((index, name))
    try:
        yield
    finally:
        _current_step.reset(token)


def model_usage_rows(scope: Optional["MeterScope"]) -> list[dict]:
    """The scope's per-step, per-model usage, as stored on an ActivityEvent."""
    if scope is None:
        return []
    with scope._lock:
        items = list(scope.usage.items())
    return [
        {
            "step_index": step_index, "step": step_name, "model": model,
            "tokens_input": tin, "tokens_output": tout, "requests": requests,
        }
        for (step_index, step_name, model), (tin, tout, requests) in items
    ]


def step_models(scope: Optional["MeterScope"], step_index: int) -> list[str]:
    """Models used by workflow step ``step_index`` so far, most tokens first."""
    rows = [r for r in model_usage_rows(scope) if r["step_index"] == step_index]
    rows.sort(key=lambda r: -(r["tokens_input"] + r["tokens_output"]))
    return list(dict.fromkeys(r["model"] for r in rows))


def summarize_model_usage(rows: list[dict] | None) -> dict:
    """Fold stored usage rows (possibly from several passes of one run: a
    retry, an approval resume) into what History shows: the run's models,
    most tokens first, and each workflow step's."""
    totals: dict[str, int] = {}
    steps: dict[int, dict] = {}
    for row in rows or []:
        model = row.get("model") or UNKNOWN_MODEL
        tokens = (row.get("tokens_input") or 0) + (row.get("tokens_output") or 0)
        totals[model] = totals.get(model, 0) + tokens
        index = row.get("step_index")
        if index is not None:
            step = steps.setdefault(index, {"index": index, "name": row.get("step"), "tokens": {}})
            step["tokens"][model] = step["tokens"].get(model, 0) + tokens

    def ordered(tokens: dict[str, int]) -> list[str]:
        return [m for m, _ in sorted(tokens.items(), key=lambda kv: -kv[1])]

    return {
        "models": ordered(totals),
        "steps": [
            {"index": s["index"], "name": s["name"], "models": ordered(s["tokens"])}
            for s in sorted(steps.values(), key=lambda s: s["index"])
        ],
    }


def run_model_fields(rows: list[dict] | None) -> dict:
    """``models`` and ``step_models`` for a run's API payload (History)."""
    summary = summarize_model_usage(rows)
    return {"models": summary["models"], "step_models": summary["steps"]}


# A call whose model the wrapper could not name.
UNKNOWN_MODEL = "unknown"


_current_scope: ContextVar[Optional[MeterScope]] = ContextVar(
    "llm_meter_scope", default=None
)


def current_scope() -> Optional[MeterScope]:
    return _current_scope.get()


def record_usage(
    model_name: Optional[str],
    input_tokens: int,
    output_tokens: int,
    *,
    estimated: bool = False,
) -> None:
    """Add one model request's usage to the active scope.

    Called by MeteredModel after every request. If no scope is set (a call site
    we haven't wired for attribution), the usage is still recorded under the
    `unattributed` feature so nothing is lost, and a warning is logged so the
    site can be found and wrapped.
    """
    scope = _current_scope.get()
    if scope is None:
        logger.warning(
            "LLM call with no metering scope (model=%s, in=%s, out=%s) — recording as unattributed",
            model_name, input_tokens, output_tokens,
        )
        backstop = MeterScope(
            feature=UNATTRIBUTED_FEATURE,
            model=model_name,
            tokens_in=input_tokens or 0,
            tokens_out=output_tokens or 0,
            requests=1,
            estimated=estimated,
        )
        flush_sync(backstop)
        return
    step_index, step_name = _current_step.get() or (None, None)
    key = (step_index, step_name, model_name or UNKNOWN_MODEL)
    with scope._lock:
        scope.tokens_in += input_tokens or 0
        scope.tokens_out += output_tokens or 0
        scope.requests += 1
        if estimated:
            scope.estimated = True
        if model_name and not scope.model:
            scope.model = model_name
        entry = scope.usage.setdefault(key, [0, 0, 0])
        entry[0] += input_tokens or 0
        entry[1] += output_tokens or 0
        entry[2] += 1


# ---------------------------------------------------------------------------
# Context managers
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def metered(
    feature: str,
    *,
    user_id: Optional[str] = None,
    team_id: Optional[str] = None,
    activity_id: Optional[str] = None,
    space: Optional[str] = None,
) -> Iterator[MeterScope]:
    """Sync metering scope (Celery tasks, engine run_sync paths).

    Raises TrialBudgetExceededError before yielding when `user_id` is a trial
    account that has exhausted its token budget (see trial_budget.py) — the
    scope entry is the one place every attributed spend path goes through.
    """
    if user_id:
        from app.services.trial_budget import check_sync

        check_sync(user_id)
    scope = MeterScope(
        feature=feature, user_id=user_id, team_id=team_id,
        activity_id=activity_id, space=space,
    )
    token = _current_scope.set(scope)
    try:
        yield scope
    finally:
        _current_scope.reset(token)
        flush_sync(scope)


@contextlib.asynccontextmanager
async def metered_async(
    feature: str,
    *,
    user_id: Optional[str] = None,
    team_id: Optional[str] = None,
    activity_id: Optional[str] = None,
    space: Optional[str] = None,
) -> AsyncIterator[MeterScope]:
    """Async metering scope (FastAPI routes/services using `await agent.run`).

    Raises TrialBudgetExceededError before yielding when `user_id` is a trial
    account that has exhausted its token budget (see trial_budget.py).
    """
    if user_id:
        from app.services.trial_budget import check_async

        await check_async(user_id)
    scope = MeterScope(
        feature=feature, user_id=user_id, team_id=team_id,
        activity_id=activity_id, space=space,
    )
    token = _current_scope.set(scope)
    try:
        yield scope
    finally:
        _current_scope.reset(token)
        await flush_async(scope)


# ---------------------------------------------------------------------------
# Flush  - persist a finished scope to the ledger (+ linked ActivityEvent)
# ---------------------------------------------------------------------------
def _record_doc(scope: MeterScope) -> dict:
    import datetime

    return {
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
        "feature": scope.feature,
        "user_id": scope.user_id,
        "team_id": scope.team_id,
        "space": scope.space,
        "activity_id": scope.activity_id,
        "model": scope.model,
        "tokens_input": scope.tokens_in,
        "tokens_output": scope.tokens_out,
        "total_tokens": scope.tokens_in + scope.tokens_out,
        "request_count": scope.requests,
        "estimated": scope.estimated,
        "status": "ok",
    }


def flush_sync(scope: MeterScope) -> None:
    """Write a usage row (and update the linked activity) from sync context."""
    if scope.requests == 0:
        return  # no LLM call happened under this scope
    try:
        from bson import ObjectId

        from app.tasks import get_sync_db

        db = get_sync_db()
        db.llm_usage.insert_one(_record_doc(scope))
        if scope.activity_id:
            db.activity_event.update_one(
                {"_id": ObjectId(scope.activity_id)},
                {
                    "$set": {
                        "tokens_input": scope.tokens_in,
                        "tokens_output": scope.tokens_out,
                        "total_tokens": scope.tokens_in + scope.tokens_out,
                    },
                    # Appended: a resumed or retried run flushes once per pass.
                    "$push": {"model_usage": {"$each": model_usage_rows(scope)}},
                },
            )
    except Exception as e:  # never let metering break the request
        logger.error("Failed to flush LLM usage (sync, feature=%s): %s", scope.feature, e)


async def flush_async(scope: MeterScope) -> None:
    """Write a usage row (and update the linked activity) from async context."""
    if scope.requests == 0:
        return
    try:
        from app.models.llm_usage import LlmUsageRecord

        await LlmUsageRecord(**_record_doc(scope)).insert()
        if scope.activity_id:
            from app.models.activity import ActivityEvent

            ev = await ActivityEvent.get(scope.activity_id)
            if ev:
                ev.tokens_input = scope.tokens_in
                ev.tokens_output = scope.tokens_out
                ev.total_tokens = scope.tokens_in + scope.tokens_out
                ev.model_usage = list(ev.model_usage or []) + model_usage_rows(scope)
                await ev.save()
    except Exception as e:
        logger.error("Failed to flush LLM usage (async, feature=%s): %s", scope.feature, e)
