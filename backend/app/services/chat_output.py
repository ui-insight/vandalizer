"""The public prose boundary for chat, separate from structured tool receipts.

Some models put approval deliberation in TextPart instead of ThinkingPart.
Never publish raw model deltas: even a tool name can span multiple deltas,
and output validators may reject an entire candidate answer. Call this only
on the accepted final output, before streaming or saving it.
"""

import json
import re
from functools import lru_cache


_PRIVATE_BLOCK = re.compile(
    r"<(think|thinking|analysis|system-reminder)\b[^>]*>.*?(?:</\1\s*>|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_INTERNAL_PROSE = re.compile(
    r"\b(?:system[ -]reminders?|(?:hidden|system|developer) (?:instructions?|prompts?))\b"
    r"|\bconfirmation (?:text is part|is a separate user turn)\b"
    r"|\bconfirmed[\s`*\"']*[=:][\s`*\"']*(?:true|false)\b"
    r"|\b(?:needs_confirmation|awaiting_user_confirmation)\b"
    r"|\bI (?:should|must|need to) (?:now )?(?:call|invoke|execute)\b"
    r"|\b(?:the )?user has approved\b",
    re.IGNORECASE,
)
# Support ticket: "…let me retry with different evidence phrasing." is the
# model narrating its next tool attempt. Only a paragraph that is nothing but
# that narration is dropped: "Let me try again: the rate is 52.5%." carries the
# answer and stays, narration and all.
_RETRY_NARRATION = re.compile(
    r"(?:(?:ok(?:ay)?|alright|hmm)[,.!]?\s+)?let me (?:retry|try again)\b[^.!?:;\n]*[.!?…]?",
    re.IGNORECASE,
)
# Support ticket: a reply ended "…phrasing.Version:1.1:{"model":"openai/gpt-oss-120b",
# "name":"VandalAI"}". The model wrote a metadata header (naming a model other
# than the selected one) into its text. Only a header immediately followed by
# a JSON object with a "model" key is removed; the object is parsed, not
# pattern-matched, so nested objects go too and "Version:2: report due" stays.
_METADATA_HEADER = re.compile(r"(?<![A-Za-z0-9])Version:[ \t]*\d+(?:\.\d+)*:[ \t]*\n?[ \t]*(?=\{)")
# The ticket quoted the object with typographic quotes. Same-length mapping, so
# offsets in the parse copy are offsets in the reply.
_JSON_QUOTES = str.maketrans({"\u201c": '"', "\u201d": '"'})
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})", re.MULTILINE)
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)*")
_INLINE_CODE = re.compile(r"(`+)[\s\S]*?(?<!`)\1(?!`)")
_JSON = json.JSONDecoder()


def _model_object_end(text: str, start: int) -> int | None:
    """End offset of a JSON object at ``start`` that has a "model" key."""
    try:
        value, end = _JSON.raw_decode(text.translate(_JSON_QUOTES), start)
    except ValueError:
        return None
    return end if isinstance(value, dict) and "model" in value else None


def _strip_leaked_metadata(text: str) -> str:
    # A header quoted in inline code is the user's or the answer's, not a leak.
    quoted = [span.span() for span in _INLINE_CODE.finditer(text)]
    out, pos = [], 0
    for header in _METADATA_HEADER.finditer(text):
        if header.start() < pos or any(a <= header.start() < b for a, b in quoted):
            continue
        end = _model_object_end(text, header.end())
        if end is None:
            continue
        start = header.start()
        line_rest = re.match(r"[ \t]*(?=\n|\Z)", text[end:])
        if line_rest:
            # Nothing follows on its line: take the spaces that led up to it.
            while start > pos and text[start - 1] in " \t":
                start -= 1
            end += line_rest.end()
        elif start == 0 or text[start - 1] in " \t\n":
            # Text follows and the header had its own leading space: take the
            # trailing spaces, so "a Version:…{…} b" reads "a b".
            end += len(text[end:]) - len(text[end:].lstrip(" \t"))
        out.append(text[pos:start])
        pos = end
    out.append(text[pos:])
    return "".join(out)


def _is_model_object(paragraph: str) -> bool:
    body = paragraph.strip()
    return body.startswith("{") and _model_object_end(body, 0) == len(body)


@lru_cache(maxsize=1)
def _tool_names() -> re.Pattern:
    # Derive names from registration so newly added tools are covered too.
    # Lazy import avoids the chat tools / llm_service import cycle.
    from app.services.chat_tools import TOOLS

    return re.compile(
        r"\b(?:" + "|".join(re.escape(tool.__name__) for tool in TOOLS) + r")\b",
        re.IGNORECASE,
    )


def _segments(text: str) -> list[tuple[str, str, bool]]:
    """Split into (separator, paragraph, fenced) with every byte accounted for.

    A paragraph that opens or closes a code fence is fenced, and blank lines
    inside a fence don't end it.
    """
    segments: list[tuple[str, str, bool]] = []
    separator, pos, open_fence = "", 0, None
    for brk in [*_PARAGRAPH_BREAK.finditer(text), None]:
        paragraph = text[pos:brk.start() if brk else len(text)]
        inside = open_fence is not None
        fences = [fence.group(1) for fence in _FENCE.finditer(paragraph)]
        for marker in fences:
            if open_fence is None:
                open_fence = marker
            elif marker[0] == open_fence[0] and len(marker) >= len(open_fence):
                open_fence = None
        if inside:
            prev_separator, prev, _ = segments.pop()
            segments.append((prev_separator, prev + separator + paragraph, True))
        else:
            segments.append((separator, paragraph, bool(fences)))
        if brk:
            separator, pos = brk.group(), brk.end()
    return segments


def _is_private(paragraph: str) -> bool:
    plain = paragraph.replace(r"\_", "_")
    body = paragraph.strip()
    return (
        not body
        or bool(_INTERNAL_PROSE.search(plain))
        or bool(_tool_names().search(plain))
        or bool(_RETRY_NARRATION.fullmatch(body))
        or _is_model_object(body)
    )


def public_chat_text(output: str) -> str:
    """Keep answer paragraphs; discard explicit implementation deliberation.

    Drop the whole affected paragraph, not just keywords, so quoted rules and
    the surrounding internal notes don't become misleading fragments. This
    supplements the channel boundary; it is not a general reasoning detector.
    User messages and structured tool results do not pass through this filter.

    Kept paragraphs, and the breaks between them, are returned byte for byte;
    the paragraph and metadata rules never edit or drop fenced code.
    """
    kept: list[str] = []
    for separator, paragraph, fenced in _segments(_PRIVATE_BLOCK.sub("", output)):
        if not fenced:
            paragraph = _strip_leaked_metadata(paragraph)
            if _is_private(paragraph):
                continue
        if kept:
            kept.append(separator)
        kept.append(paragraph)
    return re.sub(r"\A(?:[ \t]*\n)+", "", "".join(kept)).rstrip()
