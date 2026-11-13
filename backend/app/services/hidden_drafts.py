"""Keep a reply's hidden drafts out of the answer the user sees.

Output validators (spreadsheet figures, calculations, approval claims) send a
draft back to the model with ``ModelRetry``. The user never sees that draft.

Support ticket: asked to "Summarize the budget" in a new chat, the reply
said "My earlier figures were wrong — I had restated numbers that weren't in
the file. The correct Y1 is $304,000 (not $253,000)…", and the figure warning
listed the hidden draft's $253,000, $268,000… as "Not in the retrieved
sources". The retry instruction now says the draft was never shown, and this
module removes what a model still writes about it.
"""

import functools
import inspect
import re
from typing import Any, Callable, Iterable

from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelMessage, ModelRequest, RetryPromptPart

#: Appended to every output-validator retry instruction.
UNSEEN_DRAFT_INSTRUCTION = (
    "The user never saw your previous reply: do not mention it, apologise for it or say "
    "what changed (no \"earlier figures\", no \"(not $X)\"). Write the answer as if it "
    "were your first."
)


def _with_instruction(retry: ModelRetry) -> ModelRetry:
    return ModelRetry(f"{retry.message.rstrip()}\n\n{UNSEEN_DRAFT_INSTRUCTION}")


def unseen_draft_retry(validator: Callable[..., Any]) -> Callable[..., Any]:
    """An output validator whose retries say the draft was never shown."""
    if inspect.iscoroutinefunction(validator):
        @functools.wraps(validator)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await validator(*args, **kwargs)
            except ModelRetry as retry:
                raise _with_instruction(retry) from retry

        return async_wrapper

    @functools.wraps(validator)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return validator(*args, **kwargs)
        except ModelRetry as retry:
            raise _with_instruction(retry) from retry

    return wrapper

_MONEY = r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:[KkMm]|million|thousand))?"
# "(not $253,000)", "(previously $268,000)", "(was $257,000, now corrected)".
_REFUTED_PARENTHETICAL = re.compile(
    r"[ \t]*\((?:not|previously|was|instead of|rather than|corrected from)\s+" + _MONEY + r"[^()]*\)",
    re.IGNORECASE,
)
# ", not $253,000" / " instead of $253,000" after the corrected figure.
_REFUTED_TRAILING = re.compile(
    r",?[ \t]+(?:not|instead of|rather than)[ \t]+" + _MONEY + r"(?=[\s,.;:)]|$)",
    re.IGNORECASE,
)
_DRAFT_WORDS = (
    r"(?:reply|replies|answer|response|summary|draft|version|message|figures?|numbers?|"
    r"totals?|calculations?)"
)
# A sentence about the draft itself, not about the documents.
_ABOUT_DRAFT = re.compile(
    r"\b(?:my|the|an?)\s+(?:earlier|previous|prior|original|initial)\s+" + _DRAFT_WORDS + r"\b"
    r"|\bmy\s+(?:first|last)\s+" + _DRAFT_WORDS + r"\b"
    r"|\bI had (?:restated|stated|listed|given|reported|used|included|made)\b"
    r"|\b(?:apologi[sz]e|apologies|sorry)\b"
    r"|\b(?:here (?:is|are) the |with the )?corrected (?:" + _DRAFT_WORDS + r")\s*(?:follows?|below)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"[^.!?\n]*(?:[.!?]+(?=\s|$)|\n|$)")


def had_hidden_retry(messages: Iterable[ModelMessage]) -> bool:
    """Whether this run sent a finished draft back (an output-validator retry).

    A tool's argument retry carries the tool's name; a rejected final answer
    doesn't.
    """
    return any(
        isinstance(part, RetryPromptPart) and part.tool_name is None
        for message in messages if isinstance(message, ModelRequest)
        for part in message.parts
    )


def without_refuted_figures(text: str) -> str:
    """The text without figures it gives only as wrong ("$304,000 (not $253,000)")."""
    return _REFUTED_PARENTHETICAL.sub("", text or "")


def without_draft_corrections(text: str) -> str:
    """An answer without what it says about a draft the user never saw."""
    text = _REFUTED_TRAILING.sub("", without_refuted_figures(text))
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", text):
        kept = "".join(
            sentence for sentence in _SENTENCE.findall(paragraph)
            if not _ABOUT_DRAFT.search(sentence)
        ).strip()
        if kept:
            paragraphs.append(kept)
    return "\n\n".join(paragraphs)
