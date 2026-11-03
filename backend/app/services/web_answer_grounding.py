"""Exact facts in a web answer that no page the Assistant read states.

Support ticket (NSF PAPPG): asked for the current PAPPG and its effective
date, chat ran a web search and answered "Supplement 1 (effective Oct. 8,
2025)" beside official nsf.gov links and source chips. The hub page it linked
says Dec. 8, 2025. Asked to open that page, chat read it and answered Dec. 8
without saying its first answer had been wrong.

A search result is a provider's excerpt, which can be stale, truncated or
from a different page than its title suggests, and the model blends it with
memory. The KB figure check counts every tool output as a source, so a
snippet's (or a recalled) date passed as confirmed; dates were not checked
at all.

So two checks run on the finished answer of a turn that searched the web:

* ``unconfirmed_web_facts`` — the dates, dollar amounts and percentages in
  the answer that no page read in the conversation, document, knowledge-base
  passage or non-search tool result states. A search snippet is not support.
  Chat shows them under the answer and stores them on the message.
* ``missed_corrections`` — on a later turn that read a page the earlier answer
  cited: an earlier unconfirmed fact the page doesn't state, which the new
  answer silently replaced with a fact of the same kind the page does state.
  Chat appends a correction note, since the prompt asking the model to say
  "Correction: …" cannot make it comply.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit

from app.services.kb_answer_grounding import _money_values, _percent_values

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))

# "December 8, 2025", "Dec. 8, 2025", "Dec 8th 2025".
_MDY_RE = re.compile(
    rf"\b({_MONTH})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.IGNORECASE,
)
# "8 December 2025", "8th Dec. 2025".
_DMY_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH})\.?,?\s+(\d{{4}})\b", re.IGNORECASE,
)
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_US_RE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4})(?![\d/])")

Date = tuple[int, int, int]


def _valid(y: int, m: int, d: int) -> Date | None:
    return (y, m, d) if 1 <= m <= 12 and 1 <= d <= 31 and 1900 <= y <= 2200 else None


def date_values(text: str) -> dict[Date, str]:
    """Full calendar dates in *text*, normalized, with the first wording of each."""
    found: list[tuple[int, Date, str]] = []
    for m in _MDY_RE.finditer(text or ""):
        v = _valid(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
        if v:
            found.append((m.start(), v, m.group(0)))
    for m in _DMY_RE.finditer(text or ""):
        v = _valid(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
        if v:
            found.append((m.start(), v, m.group(0)))
    for m in _ISO_RE.finditer(text or ""):
        v = _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if v:
            found.append((m.start(), v, m.group(0)))
    for m in _US_RE.finditer(text or ""):
        v = _valid(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        if v:
            found.append((m.start(), v, m.group(0)))
    out: dict[Date, str] = {}
    for _, value, label in sorted(found):
        out.setdefault(value, label.strip())
    return out


def _facts(text: str) -> dict[tuple[str, object], str]:
    """Every checked fact in *text*, keyed by (kind, value)."""
    facts: dict[tuple[str, object], str] = {}
    for kind, values in (
        ("date", date_values(text)),
        ("money", _money_values(text)),
        ("percent", _percent_values(text)),
    ):
        for value, label in values.items():
            facts.setdefault((kind, value), label)
    return facts


# How much of a line before a fact counts as its context. Sentences are not
# split on full stops: "Oct. 8, 2025" would end one mid-date.
_CONTEXT_BEFORE = 160
_CONTEXT_AFTER = 60
_CORRECTION_CUE_RE = re.compile(
    r"\b(?:correct(?:ion|ed)?|incorrect|mistaken(?:ly)?|wrong|"
    r"as I (?:said|stated|wrote|gave|mentioned)|(?:my|the) (?:earlier|previous|prior) answer|"
    r"I (?:earlier|previously) (?:said|stated|gave|wrote))\b",
    re.IGNORECASE,
)


def _context(text: str, label: str) -> str:
    """The part of *label*'s line around its first occurrence in *text*."""
    at = text.find(label)
    if at < 0:
        return ""
    start = max(text.rfind("\n", 0, at) + 1, at - _CONTEXT_BEFORE)
    end = text.find("\n", at + len(label))
    end = len(text) if end < 0 else min(end, at + len(label) + _CONTEXT_AFTER)
    return text[start:end]


def unconfirmed_web_facts(
    answer: str,
    read_text: str,
    *,
    already_flagged: Iterable[str] = (),
) -> list[str]:
    """Dates, amounts and percentages in *answer* that *read_text* never states.

    *read_text* is everything the answer may rest on except search snippets.
    A fact the answer names only to retract it ("not Oct. 8, 2025 as I said
    earlier") is not one it asserts. *already_flagged* — the figure check's
    labels — are left out so one value isn't reported twice.
    """
    if not answer or not answer.strip():
        return []
    supported = set(_facts(read_text or ""))
    skip = set(already_flagged)
    missing = [
        (answer.find(label), label)
        for key, label in _facts(answer).items()
        if key not in supported and label not in skip
        and not _CORRECTION_CUE_RE.search(_context(answer, label))
    ]
    return [label for _, label in sorted(missing)]


_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the "
    "this to was were will with effective date dated current version".split()
)


def _pairs(text: str, labels: Iterable[str]) -> set[tuple[str, str]]:
    """Adjacent content-word pairs of *text* with the facts themselves removed."""
    for label in labels:
        text = text.replace(label, " ")
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS]
    return set(zip(words, words[1:]))


def _url_key(url: str) -> str:
    parts = urlsplit((url or "").strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    return host + (parts.path.rstrip("/") or "")


def missed_corrections(
    *,
    earlier_unconfirmed: Iterable[str],
    earlier_cited_urls: Iterable[str],
    earlier_answer: str,
    answer: str,
    pages_read: Iterable[tuple[str, str]],
) -> list[str]:
    """Earlier unconfirmed facts this turn's reading contradicts, unacknowledged.

    Fires only when this turn read a page the earlier answer cited (the page
    it implied said so), that page doesn't state the earlier fact, the new
    answer neither repeats nor retracts it, and the new answer states a fact
    of the same kind the page does state and the earlier answer didn't — the
    silent replacement in the ticket. Returned in the earlier answer's wording.
    """
    cited = {_url_key(u) for u in earlier_cited_urls if u}
    page_text = "\n".join(text for url, text in pages_read if _url_key(url) in cited)
    if not page_text.strip():
        return []
    on_page = set(_facts(page_text))
    answer_facts = _facts(answer)
    earlier_facts = _facts(earlier_answer)
    # The new answer's facts that came from the page and weren't in the earlier
    # answer — candidates for what replaced an earlier value — with the words
    # around each, so a replacement is matched to the claim it replaces
    # ("Supplement 1"), not to every earlier date the page happens to omit.
    replacements = [
        (key[0], _pairs(_context(answer, label), answer_facts.values()))
        for key, label in answer_facts.items()
        if key in on_page and key not in earlier_facts
    ]
    out: list[str] = []
    for label in earlier_unconfirmed:
        keys = set(_facts(label))
        if not keys or keys & on_page or keys & set(answer_facts):
            continue
        kinds = {kind for kind, _ in keys}
        around = _pairs(_context(earlier_answer, label), earlier_facts.values())
        if any(kind in kinds and around & pairs for kind, pairs in replacements):
            out.append(label)
    return out


def correction_note(labels: list[str]) -> str:
    """The note appended to an answer that corrected an earlier one silently."""
    if not labels:
        return ""
    quoted = ", ".join(f"**{label}**" for label in labels)
    return (
        f"\n\n_Correction: my earlier answer gave {quoted} from a web search, "
        "without reading the page. The page I read for this answer doesn't say that, "
        "so use the value above, not the earlier one._"
    )
