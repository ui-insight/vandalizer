"""Whether a reply or Page credits the RA inbox as its source.

Support ticket: asked for a Page with "all upcoming deadlines from this
project's RA inbox", chat never read the inbox (it had no tool to), took the
dates from the subaward instead, and the Page and reply said they were
"from the RA inbox", including an RPPR item that isn't in it. Text may say
that only after list_project_inbox ran in the same turn.
"""

import re

_TAGS = re.compile(r"<[^>]+>")
_CREDITS_INBOX = re.compile(
    r"\b(?:from|in|per|according to|listed in|tracked in)\s+"
    r"(?:the\s+|this\s+project['’]s\s+|the\s+project['’]s\s+|your\s+)?(?:RA\s+)?inbox\b"
    r"|\((?:from\s+)?(?:the\s+)?RA\s+inbox\)",
    re.IGNORECASE,
)

PAGE_ERROR = (
    "This Page says its items come from the RA inbox, but the inbox wasn't read in this "
    "reply. Call list_project_inbox and use only the items it returns, or say which "
    "documents (and pages) the deadlines came from."
)
REPLY_NOTE = (
    "**Source note:** the RA inbox wasn't read for this reply. Items described as from the "
    "inbox were taken from the project's documents and may not match what the inbox holds."
)


def credits_inbox(text: str) -> bool:
    """Whether *text* (plain text or HTML) names the RA inbox as where items come from."""
    return bool(_CREDITS_INBOX.search(_TAGS.sub(" ", text or "")))
