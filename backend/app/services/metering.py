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
from contextvars import ContextVar
from dataclasses import dataclass
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
    scope.tokens_in += input_tokens or 0
    scope.tokens_out += output_tokens or 0
    scope.requests += 1
    if estimated:
        scope.estimated = True
    if model_name and not scope.model:
        scope.model = model_name


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
    """Sync metering scope (Celery tasks, engine run_sync paths)."""
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
    """Async metering scope (FastAPI routes/services using `await agent.run`)."""
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
                {"$set": {
                    "tokens_input": scope.tokens_in,
                    "tokens_output": scope.tokens_out,
                    "total_tokens": scope.tokens_in + scope.tokens_out,
                }},
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
                await ev.save()
    except Exception as e:
        logger.error("Failed to flush LLM usage (async, feature=%s): %s", scope.feature, e)
