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
]

DEFAULT_CONTEXT_WINDOW = 65_536


def resolve_context_window(
    model_name: str, model_config: Optional[dict] = None
) -> int:
    """Return the max input-context length for a model, in tokens.

    Priority: ``model_config['context_window']`` → fallback registry → default.
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
