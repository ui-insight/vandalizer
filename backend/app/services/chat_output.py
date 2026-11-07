"""The public prose boundary for chat, separate from structured tool receipts.

Some models put approval deliberation in TextPart instead of ThinkingPart.
Never publish raw model deltas: even a tool name can span multiple deltas,
and output validators may reject an entire candidate answer. Call this only
on the accepted final output, before streaming or saving it.
"""

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


@lru_cache(maxsize=1)
def _tool_names() -> re.Pattern:
    # Derive names from registration so newly added tools are covered too.
    # Lazy import avoids the chat tools / llm_service import cycle.
    from app.services.chat_tools import TOOLS

    return re.compile(
        r"\b(?:" + "|".join(re.escape(tool.__name__) for tool in TOOLS) + r")\b",
        re.IGNORECASE,
    )


def public_chat_text(output: str) -> str:
    """Keep answer paragraphs; discard explicit implementation deliberation.

    Drop the whole affected paragraph, not just keywords, so quoted rules and
    the surrounding internal notes don't become misleading fragments. This
    supplements the channel boundary; it is not a general reasoning detector.
    User messages and structured tool results do not pass through this filter.
    """
    text = _PRIVATE_BLOCK.sub("", output)
    paragraphs = re.split(r"\n\s*\n", text)
    return "\n\n".join(
        paragraph.strip()
        for paragraph in paragraphs
        if paragraph.strip()
        and not _INTERNAL_PROSE.search(paragraph.replace(r"\_", "_"))
        and not _tool_names().search(paragraph.replace(r"\_", "_"))
    )
