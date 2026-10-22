"""Conversation compaction — summarize older messages, keep a verbatim tail.

Shared by the manual ``/chat/compact`` endpoint and the auto-compaction
trigger in ``chat_stream`` (uplift plan Phase 4). The summary replaces
messages before ``context_cutoff_index`` in the model's replayed history;
the stored messages themselves are never modified.

Post-compact re-grounding is deliberately absent: unlike Claude Code (which
must re-attach recently read files), every volatile block here — open
documents, KB manifest, project context, workspace inventory — is rebuilt on
each turn's user prompt, so nothing needs restoring after the cutoff moves.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.models.chat import ChatConversation, ChatMessage, ChatRole
from app.services.context_budget import rough_text_tokens

logger = logging.getLogger(__name__)


# Verbatim tail kept out of the summary on auto-compaction. Minimums win over
# the cap: the tail keeps growing backward until BOTH minimums are met, then
# stops before exceeding the cap (values from Claude Code's session-memory
# compaction config, adapted to message granularity).
TAIL_MIN_TOKENS = 10_000
TAIL_MAX_TOKENS = 40_000
TAIL_MIN_MESSAGES = 8  # ~4 exchanges

# The compact request itself can overflow the model; each retry drops the
# oldest quarter of the summarized span.
MAX_PROMPT_TOO_LONG_RETRIES = 3

_ANALYSIS_RE = re.compile(r"<analysis>[\s\S]*?(?:</analysis>|$)", re.IGNORECASE)
_SUMMARY_RE = re.compile(r"<summary>([\s\S]*?)(?:</summary>|$)", re.IGNORECASE)

_CONTEXT_LENGTH_INDICATORS = (
    "context length",
    "context_length",
    "prompt is too long",
    "input length",
    "maximum context",
    "too many tokens",
    "context window",
)

# Prepended to the stored summary. ChatConversation.to_model_messages adds its
# own "Previous conversation summary:" header, so this only carries the
# behavioral instruction.
CONTINUATION_PREAMBLE = (
    "(This conversation is being continued from an earlier portion that was "
    "summarized to stay within memory limits. The summary covers that earlier "
    "portion; later messages are verbatim. Resume directly — do not "
    "acknowledge or mention this summary to the user.)\n\n"
)


class CompactionError(Exception):
    """Compaction could not produce a usable summary."""


@dataclass
class CompactionResult:
    summary: str
    cutoff: int
    summarized_count: int


def _message_tokens(m: ChatMessage) -> int:
    total = rough_text_tokens(m.message or "")
    for seg in (m.segments or []):
        kind = seg.get("kind")
        if kind == "tool_result":
            total += rough_text_tokens(str(seg.get("result", {}).get("content", "")))
        elif kind == "tool_call":
            total += rough_text_tokens(str(seg.get("call", {}).get("args", "")))
    return total + 4


def _pending_confirmation_floor(conversation: ChatConversation) -> Optional[int]:
    """Earliest message index that a pending write confirmation depends on.

    Confirmation entries record the message count at arming time; the armed
    preview lives in messages from that index on. Summarizing past it would
    destroy the verbatim preview the confirm gate replays, so the cutoff must
    stay at or below the earliest armed turn.
    """
    turns = [
        int(entry.get("turn", 0))
        for entry in (conversation.pending_confirmations or [])
        if isinstance(entry, dict)
    ]
    return min(turns) if turns else None


def compute_tail_cutoff(
    msgs: list[ChatMessage],
    conversation: ChatConversation,
    *,
    keep_tail: bool = True,
) -> int:
    """Index into ``msgs`` where the verbatim tail starts (the new cutoff).

    ``keep_tail=False`` (manual /compact) summarizes everything, subject only
    to the pending-confirmation floor.
    """
    start = (
        conversation.context_cutoff_index
        if conversation.context_mode in ("truncated", "compacted")
        else 0
    )
    n = len(msgs)
    cutoff = n

    if keep_tail:
        tokens = 0
        while cutoff > start:
            candidate = tokens + _message_tokens(msgs[cutoff - 1])
            minimums_met = tokens >= TAIL_MIN_TOKENS and (n - cutoff) >= TAIL_MIN_MESSAGES
            if minimums_met and candidate > TAIL_MAX_TOKENS:
                break
            cutoff -= 1
            tokens = candidate

        # Snap backward to a user-message boundary so the verbatim tail starts
        # with the user turn that opened the exchange (never mid-exchange).
        while start < cutoff < n and msgs[cutoff].role != ChatRole.USER:
            cutoff -= 1

    floor = _pending_confirmation_floor(conversation)
    if floor is not None:
        cutoff = min(cutoff, max(start, floor))
        while start < cutoff < n and msgs[cutoff].role != ChatRole.USER:
            cutoff -= 1

    return cutoff


def _render_transcript(msgs: list[ChatMessage], prior_summary: Optional[str]) -> str:
    """Flatten messages (including tool activity) for the summarizer.

    Tool results are capped per entry — the summary needs what a tool did and
    found, not the full payload that got the conversation here to begin with.
    """
    lines: list[str] = []
    if prior_summary:
        lines.append(f"[Summary of even earlier conversation]\n{prior_summary}\n")
    for m in msgs:
        role = m.role.value
        if m.segments:
            for seg in m.segments:
                kind = seg.get("kind")
                if kind == "text":
                    content = seg.get("content", "")
                    if content:
                        lines.append(f"{role}: {content}")
                elif kind == "tool_call":
                    call = seg.get("call", {})
                    try:
                        args = json.dumps(call.get("args", {}))[:300]
                    except (TypeError, ValueError):
                        args = str(call.get("args", ""))[:300]
                    lines.append(f"{role} [ran tool] {call.get('tool_name', '?')}({args})")
                elif kind == "tool_result":
                    result = seg.get("result", {})
                    content = str(result.get("content", ""))[:800]
                    lines.append(f"[tool result] {result.get('tool_name', '?')}: {content}")
        elif m.message:
            lines.append(f"{role}: {m.message}")
    return "\n".join(lines)


def format_compact_summary(raw: str) -> str:
    """Strip the <analysis> scratchpad, unwrap <summary>, add continuation."""
    text = _ANALYSIS_RE.sub("", raw or "")
    match = _SUMMARY_RE.search(text)
    if match:
        text = match.group(1)
    text = text.strip()
    if not text:
        raise CompactionError("Summarizer returned an empty summary")
    return CONTINUATION_PREAMBLE + text


def _is_context_length_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(tok in msg for tok in _CONTEXT_LENGTH_INDICATORS)


async def _summarize(
    transcript: str,
    model_name: str,
    sys_config_doc: dict,
    user_id: str,
    team_id: Optional[str],
) -> str:
    from app.services.llm_service import COMPACT_SYSTEM_PROMPT, create_chat_agent
    from app.services.metering import metered_async

    agent = create_chat_agent(
        model_name,
        system_prompt=COMPACT_SYSTEM_PROMPT,
        system_config_doc=sys_config_doc,
    )
    async with metered_async("chat_summarize", user_id=user_id, team_id=team_id):
        result = await agent.run(
            "Summarize the following conversation transcript:\n\n" + transcript
        )
    return result.output if hasattr(result, "output") else str(result.data)


async def compact_conversation(
    conversation: ChatConversation,
    *,
    model_name: str,
    sys_config_doc: dict,
    user_id: str,
    team_id: Optional[str] = None,
    keep_tail: bool = True,
) -> CompactionResult:
    """Summarize older messages and move the context cutoff.

    Raises :class:`CompactionError` when there is nothing old enough to
    compact or the summarizer fails; callers decide how to surface it (the
    auto path counts it toward the circuit breaker, the manual endpoint
    returns a 400).
    """
    msgs = await ChatMessage.find({"_id": {"$in": conversation.messages}}).to_list()
    order = {mid: i for i, mid in enumerate(conversation.messages)}
    msgs.sort(key=lambda m: order.get(m.id, 0))

    start = (
        conversation.context_cutoff_index
        if conversation.context_mode in ("truncated", "compacted")
        else 0
    )
    cutoff = compute_tail_cutoff(msgs, conversation, keep_tail=keep_tail)
    source = msgs[start:cutoff]
    if len(source) < 2:
        raise CompactionError(
            "Nothing old enough to compact — the recent conversation is kept verbatim."
        )

    prior_summary = (
        conversation.compact_summary
        if conversation.context_mode == "compacted"
        else None
    )

    raw: Optional[str] = None
    span = list(source)
    for attempt in range(MAX_PROMPT_TOO_LONG_RETRIES + 1):
        transcript = _render_transcript(span, prior_summary)
        try:
            raw = await _summarize(transcript, model_name, sys_config_doc, user_id, team_id)
            break
        except Exception as e:
            if (
                _is_context_length_error(e)
                and attempt < MAX_PROMPT_TOO_LONG_RETRIES
                and len(span) > 4
            ):
                drop = max(1, len(span) // 4)
                logger.warning(
                    "Compact request overflowed for conversation=%s; dropping "
                    "%d oldest messages and retrying (%d/%d)",
                    conversation.uuid, drop, attempt + 1, MAX_PROMPT_TOO_LONG_RETRIES,
                )
                span = span[drop:]
                continue
            raise CompactionError(f"Summarization failed: {e}") from e
    if raw is None:
        raise CompactionError("Summarization failed: request could not be shrunk to fit")

    summary = format_compact_summary(raw)

    conversation.context_mode = "compacted"
    conversation.compact_summary = summary
    conversation.context_cutoff_index = cutoff
    # The usage anchor measured the pre-compaction context; next turn counts
    # the compacted replay and re-anchors on real usage after that.
    conversation.last_context_tokens = 0
    conversation.last_context_message_count = -1
    conversation.consecutive_autocompact_failures = 0
    await conversation.save()

    return CompactionResult(
        summary=summary, cutoff=cutoff, summarized_count=len(source),
    )
