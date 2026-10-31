"""Keep a tool call the model wrote out as text from becoming the answer.

gpt-oss speaks its own chat format ("harmony"), and the model server turns the
tool calls in it into real ones. Now and then the model writes a call the
server can't parse, and the server passes it through as reply text. The
whole answer the user got was

    <|start|>assistant<|channel|>commentary to=functions.search_documents
    <|constrain|>json={"query":"indirect rate","search_content":false}<|call|>

(attached-document eval, 2026-10-29: 2 of 630 turns). So the stream holds
such text back instead of showing it, and the agent's output validator sends
the reply back once so the model makes the call properly.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Protocol

from pydantic_ai import ModelRetry, RunContext

if TYPE_CHECKING:
    from app.services.chat_deps import AgenticChatDeps

logger = logging.getLogger(__name__)

# The markers only a harmony tool call (or a leaked harmony message) carries.
_MARKERS = ("<|channel|>", "<|call|>")
_CALL_TARGET_RE = re.compile(r"to=functions\.(\w+)")


def has_tool_call_markup(text: str) -> bool:
    """Whether *text* holds harmony tool-call markup."""
    return any(marker in (text or "") for marker in _MARKERS)


class _Parser(Protocol):
    def feed(self, text: str) -> list[tuple[str, str]]: ...
    def flush(self) -> list[tuple[str, str]]: ...


class MarkupHoldback:
    """Hold streamed reply text back from a "<|" on, until the model's response ends.

    Wraps the think-tag parser and keeps its interface: ``feed`` and ``flush``
    return (kind, text) pairs, and chat_stream flushes at the end of each
    model response. Held text with tool-call markup in it is dropped there;
    anything else is released, only later. ``ended_in_markup`` says whether
    the last response's text was dropped.
    """

    def __init__(self, parser: _Parser) -> None:
        self._parser = parser
        self._held = ""
        self.ended_in_markup = False

    def feed(self, text: str) -> list[tuple[str, str]]:
        return self._hold(self._parser.feed(text))

    def flush(self) -> list[tuple[str, str]]:
        out = self._hold(self._parser.flush())
        held, self._held = self._held, ""
        self.ended_in_markup = has_tool_call_markup(held)
        if self.ended_in_markup:
            logger.warning("Dropped tool-call markup the model wrote as its reply: %.300r", held)
        elif held:
            out.append(("text", held))
        return out

    def _hold(self, pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for kind, text in pairs:
            if kind != "text":
                out.append((kind, text))
                continue
            if self._held.startswith("<|"):
                self._held += text
                continue
            text, self._held = self._held + text, ""
            start = text.find("<|")
            if start == -1 and text.endswith("<"):
                start = len(text) - 1  # may open a "<|" the next chunk finishes
            if start == -1:
                out.append(("text", text))
                continue
            if start:
                out.append(("text", text[:start]))
            self._held = text[start:]
        return out


RETRY_INSTRUCTION = (
    "Your reply was a tool call{tool} written out as text, in chat markup "
    "(<|channel|>, <|call|>), so no tool ran and the user saw only the markup. "
    "If you need the tool, call it through the tool interface; otherwise "
    "answer the user directly. Never write chat markup in a reply."
)

# Shown when the reply was still markup once the run had no retry left: the
# markup itself never reaches the user, so without this the answer is blank.
UNFINISHED_NOTE = (
    "_This reply didn't finish: the model wrote a tool call out as text "
    "instead of running it. Please ask again._"
)


def require_no_tool_call_markup(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send a reply written as tool-call markup back to the model.

    Only while the run has an output retry left. pydantic-ai counts output
    retries per run, across all validators, and ends the run with an error
    once they run out; a reply it can't send back is dropped from the stream
    instead (see ``MarkupHoldback``).
    """
    if ctx.partial_output or ctx.retry >= ctx.max_retries or not has_tool_call_markup(output):
        return output
    target = _CALL_TARGET_RE.search(output)
    raise ModelRetry(RETRY_INSTRUCTION.format(tool=f" to {target.group(1)}" if target else ""))
