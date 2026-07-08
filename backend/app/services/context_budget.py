"""Context-budget planning and compaction for chat requests.

Sizes every component of a prompt, decides what to trim when the total
exceeds the model's input budget, and returns compacted pieces the caller
can safely send to the LLM.  All compaction is logged as structured
``CompactionAction`` entries so the caller can surface them to the user
and to Sentry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

_CHAR_TO_TOKEN_RATIO = 4


@lru_cache(maxsize=8)
def _get_encoder(encoding_name: str):
    try:
        import tiktoken

        return tiktoken.get_encoding(encoding_name)
    except Exception as exc:
        logger.warning("tiktoken unavailable (%s); falling back to char heuristic", exc)
        return None


def _encoding_for(model_name: str) -> str:
    name = (model_name or "").lower()
    if any(tok in name for tok in ("gpt-4o", "gpt-4.1", "o1", "o3", "o4")):
        return "o200k_base"
    return "cl100k_base"


def count_tokens(text: str, model_name: str = "") -> int:
    """Estimate token count for ``text`` using tiktoken when available."""
    if not text:
        return 0
    encoder = _get_encoder(_encoding_for(model_name))
    if encoder is not None:
        try:
            return len(encoder.encode(text, disallowed_special=()))
        except Exception:
            pass
    return max(1, len(text) // _CHAR_TO_TOKEN_RATIO)


def count_message_tokens(message: Any, model_name: str = "") -> int:
    """Estimate tokens for one pydantic-ai ``ModelMessage``."""
    total = 4  # per-message overhead for role wrapping
    for part in getattr(message, "parts", ()):
        content = getattr(part, "content", None)
        if content is None:
            content = str(part)
        total += count_tokens(str(content), model_name)
    return total


# ---------------------------------------------------------------------------
# Model context window
# ---------------------------------------------------------------------------

# Order matters — the first substring match wins, so more specific entries
# must appear before broader ones.
_CONTEXT_WINDOW_FALLBACKS: list[tuple[str, int]] = [
    ("gpt-4.1", 1_000_000),
    ("gpt-4o-mini", 128_000),
    ("gpt-4o", 128_000),
    ("gpt-4-turbo", 128_000),
    ("gpt-4-32k", 32_768),
    ("gpt-4", 8_192),
    ("gpt-3.5", 16_385),
    ("o1-mini", 128_000),
    ("o1", 200_000),
    ("o3", 200_000),
    ("o4", 200_000),
    ("claude-opus-4", 200_000),
    ("claude-sonnet-4", 200_000),
    ("claude-haiku-4", 200_000),
    ("claude-3-7", 200_000),
    ("claude-3-5", 200_000),
    ("claude-3", 200_000),
    ("llama-3", 131_072),
    ("llama3", 131_072),
    ("mixtral", 32_768),
    ("mistral", 32_768),
    ("qwen", 131_072),
    ("gemma", 8_192),
    # Conservative catch-all: every Claude generation since 3 has had at least
    # a 200k window. Must stay after the specific claude-* entries.
    ("claude", 200_000),
]

DEFAULT_CONTEXT_WINDOW = 65_536

# Models we've already warned about falling back to the default window —
# once per process per model, not once per turn.
_window_fallback_warned: set[str] = set()


def resolve_context_window(
    model_name: str, model_config: Optional[dict] = None
) -> int:
    """Return the max input-context length for a model, in tokens.

    Priority: ``model_config['context_window']`` → fallback registry → default.
    Hitting the default is almost always an admin-config gap (the registry is
    a convenience, not a source of truth), so it logs a warning once per model:
    a wrong window makes every budget/threshold decision wrong.
    """
    if model_config:
        raw = model_config.get("context_window")
        try:
            value = int(raw) if raw not in (None, "") else 0
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value

    name = (model_name or "").lower()
    for pattern, window in _CONTEXT_WINDOW_FALLBACKS:
        if pattern in name:
            return window
    if model_name and model_name not in _window_fallback_warned:
        _window_fallback_warned.add(model_name)
        logger.warning(
            "No context_window configured for model %r and no registry match; "
            "assuming %d tokens. Set context_window in the model's System "
            "Config entry — budgets and context warnings are wrong without it.",
            model_name, DEFAULT_CONTEXT_WINDOW,
        )
    return DEFAULT_CONTEXT_WINDOW


# ---------------------------------------------------------------------------
# Budgeting + compaction
# ---------------------------------------------------------------------------


@dataclass
class DocumentSegment:
    """A single compactable chunk of context (doc body, KB block, attachment)."""

    label: str
    text: str
    required: bool = False  # required segments are never trimmed


@dataclass
class CompactionAction:
    """A single edit the planner applied to fit the budget."""

    kind: str  # "history_trimmed" | "documents_trimmed" | "attachments_trimmed" | "over_budget"
    detail: str
    tokens_dropped: int = 0

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "detail": self.detail,
            "tokens_dropped": self.tokens_dropped,
        }


@dataclass
class BudgetPlan:
    model: str
    context_window: int
    response_reserve: int
    input_budget: int

    system_tokens: int = 0
    user_message_tokens: int = 0
    history_tokens: int = 0
    documents_tokens: int = 0
    attachments_tokens: int = 0

    @property
    def total_input_tokens(self) -> int:
        return (
            self.system_tokens
            + self.user_message_tokens
            + self.history_tokens
            + self.documents_tokens
            + self.attachments_tokens
        )

    @property
    def over_budget(self) -> bool:
        return self.total_input_tokens > self.input_budget

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "context_window": self.context_window,
            "response_reserve": self.response_reserve,
            "input_budget": self.input_budget,
            "total_input_tokens": self.total_input_tokens,
            "system_tokens": self.system_tokens,
            "user_message_tokens": self.user_message_tokens,
            "history_tokens": self.history_tokens,
            "documents_tokens": self.documents_tokens,
            "attachments_tokens": self.attachments_tokens,
            "headroom_tokens": self.input_budget - self.total_input_tokens,
        }


@dataclass
class CompactedContext:
    documents: list[DocumentSegment]
    attachments: list[DocumentSegment]
    history: list  # list[pydantic_ai.messages.ModelMessage]
    plan: BudgetPlan
    actions: list[CompactionAction] = field(default_factory=list)

    @property
    def fatal(self) -> bool:
        """True when we could not shrink the request below the input budget."""
        return self.plan.over_budget


def _default_response_reserve(context_window: int) -> int:
    """Reserve tokens for the model's response.

    Scales with window size so tiny models don't lose all their budget to the
    reserve and large models don't overreserve.
    """
    return max(1024, min(8192, context_window // 4))


def _truncate_text_to_tokens(
    text: str,
    max_tokens: int,
    model_name: str,
    marker: str = "\n\n…[truncated]…\n\n",
) -> tuple[str, int]:
    """Truncate ``text`` to ≤ ``max_tokens``, preserving head and tail.

    Returns ``(truncated_text, dropped_tokens)``.
    """
    original_tokens = count_tokens(text, model_name)
    if max_tokens <= 0:
        return "", original_tokens
    if original_tokens <= max_tokens:
        return text, 0

    marker_tokens = count_tokens(marker, model_name)
    usable = max(1, max_tokens - marker_tokens)

    encoder = _get_encoder(_encoding_for(model_name))
    if encoder is not None:
        try:
            toks = encoder.encode(text, disallowed_special=())
            head_n = int(usable * 0.75)
            tail_n = max(0, usable - head_n)
            head_text = encoder.decode(toks[:head_n]) if head_n else ""
            tail_text = encoder.decode(toks[-tail_n:]) if tail_n else ""
            new_text = head_text + marker + tail_text
            return new_text, original_tokens - count_tokens(new_text, model_name)
        except Exception:
            pass

    approx_chars = usable * _CHAR_TO_TOKEN_RATIO
    head_chars = int(approx_chars * 0.75)
    tail_chars = max(0, approx_chars - head_chars)
    new_text = text[:head_chars] + marker + (text[-tail_chars:] if tail_chars else "")
    return new_text, original_tokens - count_tokens(new_text, model_name)


def plan_and_compact_context(
    *,
    model_name: str,
    model_config: Optional[dict],
    system_prompt: str,
    user_message: str,
    history: list,
    documents: list[DocumentSegment],
    attachments: list[DocumentSegment],
    response_reserve: Optional[int] = None,
) -> CompactedContext:
    """Plan a context budget for this request and compact oversize components.

    Returns the same pieces (possibly trimmed) plus a ``BudgetPlan`` and the
    list of ``CompactionAction``s the planner applied.  The caller should
    check ``result.fatal`` — if true, sending the request will still fail.
    """
    documents = list(documents)
    attachments = list(attachments)
    history = list(history)

    context_window = resolve_context_window(model_name, model_config)
    reserve = (
        response_reserve
        if response_reserve is not None
        else _default_response_reserve(context_window)
    )
    input_budget = max(1, context_window - reserve)

    plan = BudgetPlan(
        model=model_name,
        context_window=context_window,
        response_reserve=reserve,
        input_budget=input_budget,
    )
    actions: list[CompactionAction] = []

    plan.system_tokens = count_tokens(system_prompt, model_name) if system_prompt else 0
    plan.user_message_tokens = count_tokens(user_message, model_name)
    plan.history_tokens = sum(count_message_tokens(m, model_name) for m in history)
    plan.documents_tokens = sum(count_tokens(d.text, model_name) for d in documents)
    plan.attachments_tokens = sum(
        count_tokens(a.text, model_name) for a in attachments
    )

    if not plan.over_budget:
        return CompactedContext(
            documents=documents,
            attachments=attachments,
            history=history,
            plan=plan,
            actions=actions,
        )

    # Non-compactable floor covers the system prompt, user message, and an
    # allowance for prompt scaffolding ("--- BEGIN REFERENCE DOCUMENTS ---" etc.).
    floor = plan.system_tokens + plan.user_message_tokens + 64
    if floor >= input_budget:
        actions.append(
            CompactionAction(
                kind="over_budget",
                detail=(
                    f"System prompt + your message alone ({floor} tokens) already "
                    f"exceed this model's input budget ({input_budget} tokens). "
                    "Shorten the message or pick a larger model."
                ),
            )
        )
        return CompactedContext(
            documents=documents,
            attachments=attachments,
            history=history,
            plan=plan,
            actions=actions,
        )

    remaining = input_budget - floor
    doc_target = int(remaining * 0.65)
    hist_target = int(remaining * 0.25)
    attach_target = remaining - doc_target - hist_target

    # 1. Drop oldest history messages until under target.
    if plan.history_tokens > hist_target:
        dropped = 0
        while history and sum(
            count_message_tokens(m, model_name) for m in history
        ) > hist_target:
            m = history.pop(0)
            dropped += count_message_tokens(m, model_name)
        plan.history_tokens = sum(count_message_tokens(m, model_name) for m in history)
        if dropped:
            actions.append(
                CompactionAction(
                    kind="history_trimmed",
                    detail=f"Dropped {dropped} tokens of older conversation history.",
                    tokens_dropped=dropped,
                )
            )

    # 2. Trim attachments proportionally.
    if plan.attachments_tokens > attach_target and attachments:
        dropped = 0
        scale = attach_target / max(1, plan.attachments_tokens)
        for i, a in enumerate(attachments):
            if a.required:
                continue
            raw = count_tokens(a.text, model_name)
            allowed = max(256, int(raw * scale))
            if allowed >= raw:
                continue
            new_text, loss = _truncate_text_to_tokens(a.text, allowed, model_name)
            dropped += loss
            attachments[i] = DocumentSegment(
                label=a.label, text=new_text, required=a.required
            )
        plan.attachments_tokens = sum(
            count_tokens(a.text, model_name) for a in attachments
        )
        if dropped:
            actions.append(
                CompactionAction(
                    kind="attachments_trimmed",
                    detail=f"Trimmed {dropped} tokens from attached files.",
                    tokens_dropped=dropped,
                )
            )

    # 3. Trim documents proportionally.
    if plan.documents_tokens > doc_target and documents:
        dropped = 0
        scale = doc_target / max(1, plan.documents_tokens)
        for i, d in enumerate(documents):
            if d.required:
                continue
            raw = count_tokens(d.text, model_name)
            allowed = max(512, int(raw * scale))
            if allowed >= raw:
                continue
            new_text, loss = _truncate_text_to_tokens(d.text, allowed, model_name)
            dropped += loss
            documents[i] = DocumentSegment(
                label=d.label, text=new_text, required=d.required
            )
        plan.documents_tokens = sum(
            count_tokens(d.text, model_name) for d in documents
        )
        if dropped:
            actions.append(
                CompactionAction(
                    kind="documents_trimmed",
                    detail=f"Trimmed {dropped} tokens from reference documents.",
                    tokens_dropped=dropped,
                )
            )

    # 4. Last-ditch: aggressively shrink or drop segments until we fit.
    _MIN_USEFUL_TOKENS = 64  # smaller than this is not worth keeping
    safety_counter = 0
    while plan.over_budget and safety_counter < 50:
        safety_counter += 1
        overflow = plan.total_input_tokens - input_budget
        candidate: Optional[DocumentSegment] = None
        bucket_name: Optional[str] = None
        container: Optional[list[DocumentSegment]] = None
        for bucket_name_try, bucket in (
            ("documents", documents),
            ("attachments", attachments),
        ):
            for seg in bucket:
                if seg.required:
                    continue
                if candidate is None or count_tokens(
                    seg.text, model_name
                ) > count_tokens(candidate.text, model_name):
                    candidate = seg
                    bucket_name = bucket_name_try
                    container = bucket
        if candidate is None or container is None:
            actions.append(
                CompactionAction(
                    kind="over_budget",
                    detail=(
                        f"Compaction could not reduce input below {input_budget} "
                        f"tokens (still at {plan.total_input_tokens}). "
                        "Remove some documents or switch to a larger model."
                    ),
                )
            )
            break

        raw = count_tokens(candidate.text, model_name)
        target = raw - overflow - 8  # shave 8 extra tokens of slack
        if target < _MIN_USEFUL_TOKENS:
            # Not worth keeping a tiny sliver — drop the segment entirely.
            container.remove(candidate)
            actions.append(
                CompactionAction(
                    kind=f"{bucket_name}_trimmed",
                    detail=f"Dropped '{candidate.label}' to fit budget ({raw} tokens).",
                    tokens_dropped=raw,
                )
            )
        else:
            new_text, loss = _truncate_text_to_tokens(
                candidate.text, target, model_name
            )
            if loss <= 0:
                # No forward progress possible on this segment; drop it.
                container.remove(candidate)
                actions.append(
                    CompactionAction(
                        kind=f"{bucket_name}_trimmed",
                        detail=f"Dropped '{candidate.label}' to fit budget ({raw} tokens).",
                        tokens_dropped=raw,
                    )
                )
            else:
                candidate.text = new_text
                actions.append(
                    CompactionAction(
                        kind=f"{bucket_name}_trimmed",
                        detail=(
                            f"Additional trim of {loss} tokens from "
                            f"'{candidate.label}' to fit budget."
                        ),
                        tokens_dropped=loss,
                    )
                )
        plan.documents_tokens = sum(
            count_tokens(d.text, model_name) for d in documents
        )
        plan.attachments_tokens = sum(
            count_tokens(a.text, model_name) for a in attachments
        )

    return CompactedContext(
        documents=documents,
        attachments=attachments,
        history=history,
        plan=plan,
        actions=actions,
    )


# ---------------------------------------------------------------------------
# Usage-anchored estimation + context meter (uplift plan Phase 2)
# ---------------------------------------------------------------------------
#
# The tiktoken counting above re-encodes the entire request every turn and is
# only approximate for non-OpenAI tokenizers anyway. The cheap, more honest
# alternative (Claude Code's approach): anchor on the provider's *reported*
# usage from the previous turn's final model request — that number IS the
# context size, no tokenizer needed — and char-estimate only what's new since.
# Because the anchor is stamped after the whole turn persists, the only new
# content at the next turn's pre-flight is the user's new message.

# Conservative pad on rough estimates: under-estimating fires warnings too
# late, which is the expensive direction (Claude Code pads 4/3 for the same
# reason).
_ESTIMATE_PAD_NUM = 4
_ESTIMATE_PAD_DEN = 3


def rough_text_tokens(text: str) -> int:
    """Char-based token estimate (~4 chars/token), no tokenizer, no pad."""
    if not text:
        return 0
    return max(1, len(text) // _CHAR_TO_TOKEN_RATIO)


def estimate_next_request_tokens(
    *,
    anchor_tokens: int,
    new_text: str,
) -> int:
    """Estimate the next request's input size from the previous turn's anchor.

    ``anchor_tokens`` is the previous turn's final-request context size as
    reported by the provider (input + cache_read + cache_write + output — the
    output becomes replayed history next turn). ``new_text`` is everything new
    since the anchor: in practice the user's new message (the per-turn
    reminder/document blocks were already counted inside the anchor's request
    and are re-sent at roughly the same size). The rough delta is padded 4/3;
    the exact anchor is not.
    """
    delta = rough_text_tokens(new_text)
    return anchor_tokens + delta * _ESTIMATE_PAD_NUM // _ESTIMATE_PAD_DEN


# Threshold ladder (tokens of headroom below the effective window). Values
# from Claude Code's autoCompact.ts, which arrived at them empirically:
# warn with ~20k left, compact with ~13k (or 6% of window) left, hard-block
# with 3k left. Small windows use percentages instead — flat buffers would
# consume most of the budget.
_WARN_BUFFER_TOKENS = 20_000
_COMPACT_BUFFER_TOKENS = 13_000
_COMPACT_BUFFER_WINDOW_FRACTION = 0.06
_BLOCK_BUFFER_TOKENS = 3_000
_SMALL_WINDOW_TOKENS = 32_000
_SMALL_WARN_FRACTION = 0.75
_SMALL_COMPACT_FRACTION = 0.85
_SMALL_BLOCK_FRACTION = 0.97

METER_OK = "ok"
METER_WARNING = "warning"
METER_COMPACT = "compact"
METER_BLOCKED = "blocked"


@dataclass
class ContextMeter:
    """Per-turn context utilization + the escalation ladder state.

    ``state`` escalates ok → warning → compact → blocked. ``compact`` means
    "past the auto-compact threshold" — Phase 4 will act on it; until then the
    UI treats it as a strong warning. ``percent_until_compact`` is headroom
    relative to the compact threshold (0 once past it).
    """

    estimated_tokens: int
    context_window: int
    effective_window: int
    warn_threshold: int
    compact_threshold: int
    block_threshold: int
    state: str
    percent_until_compact: int
    estimate_source: str  # "usage_anchor" | "token_count"

    def to_dict(self) -> dict:
        return {
            "estimated_tokens": self.estimated_tokens,
            "context_window": self.context_window,
            "effective_window": self.effective_window,
            "warn_threshold": self.warn_threshold,
            "compact_threshold": self.compact_threshold,
            "block_threshold": self.block_threshold,
            "state": self.state,
            "percent_until_compact": self.percent_until_compact,
            "estimate_source": self.estimate_source,
        }


def build_context_meter(
    *,
    estimated_tokens: int,
    context_window: int,
    response_reserve: Optional[int] = None,
    estimate_source: str = "token_count",
) -> ContextMeter:
    """Place an estimate on the warn/compact/block escalation ladder."""
    reserve = (
        response_reserve
        if response_reserve is not None
        else _default_response_reserve(context_window)
    )
    effective = max(1, context_window - reserve)

    if context_window < _SMALL_WINDOW_TOKENS:
        warn_at = int(effective * _SMALL_WARN_FRACTION)
        compact_at = int(effective * _SMALL_COMPACT_FRACTION)
        block_at = int(effective * _SMALL_BLOCK_FRACTION)
    else:
        compact_buffer = max(
            _COMPACT_BUFFER_TOKENS,
            int(context_window * _COMPACT_BUFFER_WINDOW_FRACTION),
        )
        warn_at = effective - max(_WARN_BUFFER_TOKENS, compact_buffer + 4_000)
        compact_at = effective - compact_buffer
        block_at = effective - _BLOCK_BUFFER_TOKENS

    # The ladder must be strictly ordered even for odd window configs.
    warn_at = max(1, min(warn_at, compact_at - 1))
    block_at = max(compact_at + 1, block_at)

    if estimated_tokens >= block_at:
        state = METER_BLOCKED
    elif estimated_tokens >= compact_at:
        state = METER_COMPACT
    elif estimated_tokens >= warn_at:
        state = METER_WARNING
    else:
        state = METER_OK

    percent = 0
    if compact_at > 0:
        percent = max(0, round((compact_at - estimated_tokens) / compact_at * 100))

    return ContextMeter(
        estimated_tokens=estimated_tokens,
        context_window=context_window,
        effective_window=effective,
        warn_threshold=warn_at,
        compact_threshold=compact_at,
        block_threshold=block_at,
        state=state,
        percent_until_compact=percent,
        estimate_source=estimate_source,
    )


# ---------------------------------------------------------------------------
# Pre-flight oversize check (no LLM call required)
# ---------------------------------------------------------------------------


@dataclass
class OversizeDocument:
    uuid: str
    title: str
    token_count: int

    def to_dict(self) -> dict:
        return {"uuid": self.uuid, "title": self.title, "token_count": self.token_count}


def find_oversize_documents(
    *,
    documents: list[dict],
    model_name: str,
    model_config: Optional[dict] = None,
    overhead_tokens: int = 1024,
) -> list[OversizeDocument]:
    """Return docs whose token_count alone would not fit the model's input budget.

    A doc is "oversize" if its `token_count` exceeds the per-request budget
    after reserving room for the response and a small overhead (system prompt,
    user message, scaffolding). Returns docs sorted largest-first. The caller
    uses this to recommend "Convert to Knowledge Base" rather than running
    compaction and silently truncating.

    ``documents`` is a list of dicts each with at least ``uuid``, ``title``,
    ``token_count``. Accepting dicts (not the Beanie model) keeps this usable
    from sync Celery code.
    """
    context_window = resolve_context_window(model_name, model_config)
    reserve = _default_response_reserve(context_window)
    budget = max(1, context_window - reserve - overhead_tokens)

    oversize: list[OversizeDocument] = []
    for d in documents:
        tc = int(d.get("token_count") or 0)
        if tc > budget:
            oversize.append(OversizeDocument(
                uuid=str(d.get("uuid") or ""),
                title=str(d.get("title") or d.get("uuid") or "Untitled"),
                token_count=tc,
            ))
    oversize.sort(key=lambda o: o.token_count, reverse=True)
    return oversize
