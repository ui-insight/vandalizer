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

_MONEY = r"\$\s?\d(?:[\d,]*\d)?(?:\.\d+)?(?:\s?(?:[KkMm]|million|thousand)\b)?"
_REFUTING = r"(?:not|instead of|rather than)"
# The one figure a reply gives as wrong, right after the figure that replaces
# it: "$304,000 (not $253,000)", "$304,000, not $253,000", "$304,000 instead
# of $253,000". Group 1 is the refuted figure. "(was $1,800)" and
# "(previously $1,800)" are claims about the documents and stay checked.
_REFUTED_FIGURE = re.compile(
    _MONEY + r"[ \t]*(?:\([ \t]*|,[ \t]*|[ \t])" + _REFUTING + r"[ \t]+(" + _MONEY + r")",
    re.IGNORECASE,
)
# "$304,000 (not $253,000)": only a parenthetical that holds nothing else.
_REFUTED_PARENTHETICAL = re.compile(
    "(" + _MONEY + r")([ \t]*\([ \t]*(?:" + _REFUTING + r"|corrected from)[ \t]+" + _MONEY + r"[ \t]*\))",
    re.IGNORECASE,
)
# "$304,000, not $253,000." only where the phrase ends a clause, so nothing
# after it has to be rejoined ("but not $600,000 in Year 5" is left alone).
_REFUTED_TRAILING = re.compile(
    "(" + _MONEY + r")(,?[ \t]+" + _REFUTING + r"[ \t]+" + _MONEY + r")(?=[ \t]*(?:[.;:,!?)]|$))",
    re.IGNORECASE | re.MULTILINE,
)
_DRAFT_WORDS = (
    r"(?:reply|replies|answer|response|summary|draft|version|message|figures?|numbers?|"
    r"totals?|calculations?)"
)
# A sentence in which the model talks about its own draft. Only first-person
# self-correction: "the original figures submitted to NIH" is budget content.
_ABOUT_DRAFT = re.compile(
    r"\bmy\s+(?:earlier|previous|prior|original|initial|first|last)\s+" + _DRAFT_WORDS + r"\b"
    r"|\bI\s+(?:had\s+|have\s+)?(?:previously|earlier|mistakenly|incorrectly)\s+"
    r"(?:restated|stated|listed|gave|given|reported|said|wrote|used|included|made|summari[sz]ed)\b"
    r"|\bI\s+had\s+(?:restated|misstated|listed|given|reported|used|included)\b"
    r"|\bI\s+made\s+(?:an?\s+|some\s+)?(?:error|mistake)s?\b"
    r"|^(?:sorry|apologies|my apologies|I\s+apologi[sz]e)\b",
    re.IGNORECASE,
)
# A line that only announces the correction: "Here are the corrected figures:".
_CORRECTED_HEADER = re.compile(
    r"(?:here\s+(?:is|are)\s+)?(?:the\s+|my\s+)?corrected\s+" + _DRAFT_WORDS
    + r"(?:\s+(?:follows?|are\s+below|is\s+below|below))?\s*[:.]?",
    re.IGNORECASE,
)
# A sentence boundary: end punctuation, whitespace, then a capital letter.
# "52.5%", "e.g. the", "C.F.R. 200.414" and URLs are never split.
_BOUNDARY = re.compile(r"(?<=[.!?])[ \t]+(?=[*_\"'(\[]*[A-Z])")
_FENCE = re.compile(r"[ \t]{0,3}(```|~~~)")
_LIST_MARKER = re.compile(r"[ \t]*(?:[-*+]|\d+[.)])?[ \t]*")


def had_hidden_retry(messages: Iterable[ModelMessage]) -> bool:
    """Whether this run sent a finished draft back through ``unseen_draft_retry``.

    Only those retries carry the instruction; a tool's argument retry and
    pydantic-ai's own "Please return text or call a tool." (a response with
    only thinking) don't, and leave the reply untouched.
    """
    return any(
        isinstance(part, RetryPromptPart) and part.tool_name is None
        and isinstance(part.content, str) and UNSEEN_DRAFT_INSTRUCTION in part.content
        for message in messages if isinstance(message, ModelRequest)
        for part in message.parts
    )


def without_refuted_figures(text: str) -> str:
    """The text for the figure checks, without the one figure each correction refutes.

    "$304,000 (not $253,000)" is checked as "$304,000 (not )". Every other
    figure stays, including "(was $1,800)" and the rest of a parenthetical.
    """
    text = text or ""
    return _REFUTED_FIGURE.sub(lambda m: text[m.start():m.start(1)] + text[m.end(1):m.end()], text)


def _about_draft(sentence: str) -> bool:
    sentence = sentence.strip().lstrip("*_ ")
    return bool(_ABOUT_DRAFT.search(sentence) or _CORRECTED_HEADER.fullmatch(sentence.rstrip("*_ ")))


def _clean_line(line: str) -> str | None:
    """The line without its leading and trailing sentences about the draft.

    ``None`` when every sentence is about the draft. Kept text is a slice of
    the line, never rewritten.
    """
    body, newline = (line[:-1], "\n") if line.endswith("\n") else (line, "")
    marker = _LIST_MARKER.match(body)
    prefix = marker.end() if marker else 0
    starts = [prefix, *(m.end() for m in _BOUNDARY.finditer(body, prefix))]
    sentences = [(start, starts[i + 1] if i + 1 < len(starts) else len(body)) for i, start in enumerate(starts)]
    first, last = 0, len(sentences)
    while first < last and _about_draft(body[slice(*sentences[first])]):
        first += 1
    while last > first and _about_draft(body[slice(*sentences[last - 1])]):
        last -= 1
    if first == last:
        return None
    if first == 0 and last == len(sentences):
        return line
    start, end = sentences[first][0], sentences[last - 1][1]
    return body[:prefix] + body[start:end].rstrip(" \t") + newline


def without_draft_corrections(text: str) -> str:
    """An answer without what it says about a draft the user never saw.

    Removes whole sentences at the start or end of a line ("My earlier
    figures were wrong.", "Sorry for the confusion."), whole lines, and a
    refuted figure right after its correction ("$304,000 (not $253,000)",
    "$304,000, not $253,000."). Everything kept is unchanged, byte for byte.
    Code blocks are never touched; tables and quotes lose only refuted figures.
    """
    if not text:
        return text
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    in_fence = False
    removed_previous = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
            kept.append(line)
            removed_previous = False
            continue
        if in_fence:
            kept.append(line)
            continue
        cleaned: str | None = _REFUTED_TRAILING.sub(r"\1", _REFUTED_PARENTHETICAL.sub(r"\1", line))
        if not line.strip():
            # The blank line after a removed paragraph goes with it.
            if not removed_previous:
                kept.append(line)
            removed_previous = False
            continue
        if not line.lstrip().startswith(("|", ">")):
            cleaned = _clean_line(cleaned or "")
        removed_previous = cleaned is None
        if cleaned is not None:
            kept.append(cleaned)
    result = "".join(kept)
    if not result.strip():
        return text
    # A removed first or last paragraph leaves its separator behind.
    leading = len(text) - len(text.lstrip("\n"))
    trailing = len(text) - len(text.rstrip("\n"))
    return "\n" * leading + result.strip("\n") + "\n" * trailing
