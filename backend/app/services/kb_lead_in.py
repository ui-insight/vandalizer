"""The lead-in of a list whose items a knowledge-base chunk holds.

A regulation states a rule as a sentence that ends in a colon and the list
it governs: § 200.308(f) "A recipient … must request prior written approval
… for the following program and budget-related reasons:" and then (1)
through (10). Chunks are cut along lines, so a long list is split across
chunks and the later ones hold bare items — "(5) The transfer of funds
budgeted for participant support costs to other budget categories." Read
alone, that item says nothing about approval, and a chat answer citing it
told a user the transfer needs no prior approval: the opposite of the rule.

Here a chunk that opens with a list item gets the line that introduces its
list, read from the chunks before it in the same section, and that line's
own lead-in when it is itself an item of a list introduced by a colon
(§ 200.308(g)(2)(i) sits under "(2) One-time extensions. … require prior
approval … when:", which sits under "(g) … one or more of the following:").
The text is the source's own words, so a model citing the chunk reads it as
written and a reader sees it in the passage's popover.

Pure logic, plus :func:`attach_lead_ins`, which reads the earlier chunks
through the document manager's ``get_kb_chunks_by_ids``.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Chunks read back from one, enough for a long sub-list under a long item
# (§ 200.308(g)(2)(i) is three chunks after (g)).
LOOKBACK_CHUNKS = 4
# Levels of lead-in given: the list's own and the one above it.
MAX_DEPTH = 2
# A lead-in line longer than this keeps its opening (the item's marker and
# title) and its last sentence (the one ending in the colon).
LINE_MAX_CHARS = 320
HEAD_MAX_CHARS = 120

_CHUNK_ID_RE = re.compile(r"^(.*)_chunk_(\d+)$")
# "(5) ", "(ii) ", "(A) ", "5. ", "a) ", "iv. "; "(5)(i) " is an item "(i)"
# opening an item "(5)" that has no words of its own.
_ITEM_RE = re.compile(
    r"^[ \t]*(?P<chain>(?:\([0-9A-Za-z]{1,5}\))*)"
    r"(?:\((?P<p>\d{1,3}|[a-z]{1,5}|[A-Z]{1,2})\)|(?P<d>\d{1,3}|[a-z]|[A-Z]|[ivxlc]{2,6})[.)])[ \t]+\S"
)
_BULLET_RE = re.compile(r"^[ \t]*[-•*▪◦·][ \t]+\S")
# A policy page's sub-heading: "E-3. Financial set-up." is item 3 under "E.".
_SUB_RE = re.compile(r"^[ \t]*([A-Z])-(\d{1,2})\.[ \t]+\S")
_ROMAN_RE = re.compile(r"^[ivxlc]+$")
_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
# A line that introduces what follows it.
_INTRO_RE = re.compile(r"(?::|\bas follows\.?|\bthe following\.?)\s*$", re.I)
_SENTENCE_RE = re.compile(r"(?<=[.;])\s+(?=[A-Z(])")


def _roman(token: str) -> int:
    total = 0
    for a, b in zip(token, token[1:] + " "):
        v = _ROMAN[a]
        total += -v if b != " " and _ROMAN[b] > v else v
    return total


def _token(line: str) -> Optional[tuple[str, str]]:
    m = _ITEM_RE.match(line)
    if not m:
        return None
    return ("p", m.group("p")) if m.group("p") is not None else ("d", m.group("d"))


def _lettered(style: str, token: str, above: list[str]) -> bool:
    """Whether a lone "(i)", "(v)" or "(x)" continues a lettered list: the
    nearest lettered item above it, in its style, is the letter before
    ("(h)" over "(i) Transfer of funds."). Under "(2) One-time extensions …
    when:" the nearest one is "(g)", and "(i)" is a numeral."""
    for ln in reversed(above):
        t = _token(ln)
        if t and t[0] == style and len(t[1]) == 1 and t[1].islower() and t[1] != token:
            if t[1] not in "ivx" or ord(t[1]) == ord(token) - 1:
                return ord(t[1]) == ord(token) - 1
    return False


def _item(line: str, above: list[str] = ()) -> Optional[tuple[str, int]]:
    """``(kind, ordinal)`` of a list item line, or None. The kind tells one
    level of a list from another: "p:num" for "(5)", "d:lower" for "a.",
    "bullet"; a lone "(i)", "(v)" or "(x)" is a roman numeral unless the
    lines ``above`` it put it in a lettered list."""
    if _BULLET_RE.match(line):
        return ("bullet", 0)
    sub = _SUB_RE.match(line)
    if sub:
        return (f"sub:{sub.group(1)}", int(sub.group(2)))
    t = _token(line)
    if t is None:
        return None
    style, token = t
    if token.isdigit():
        return (f"{style}:num", int(token))
    if token.isupper():
        return (f"{style}:upper", ord(token[0]) - 64) if len(token) == 1 else None
    if len(token) == 1 and (token not in "ivx" or _lettered(style, token, list(above))):
        return (f"{style}:lower", ord(token) - 96)
    if _ROMAN_RE.match(token):
        return (f"{style}:roman", _roman(token))
    return None


def _shorten(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    if len(line) <= LINE_MAX_CHARS:
        return line
    sentences = _SENTENCE_RE.split(line)
    head, last = sentences[0], sentences[-1]
    if len(sentences) < 2 or len(head) > HEAD_MAX_CHARS:
        head = ""
    if len(last) > LINE_MAX_CHARS:
        last = last[-LINE_MAX_CHARS:].split(" ", 1)[-1]
        return f"{head} … {last}" if head else f"… {last}"
    return f"{head} … {last}" if head else last


def _lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip()]


def _introducer(lines: list[str], at: int, kind: str, ordinal: int) -> Optional[int]:
    """The index of the line that introduces the list holding the item of
    ``kind`` at ``lines[at]`` (or, with ``at == len(lines)``, an item about
    to follow): above its siblings and the items nested under them, the
    first line that is not one of them. None when the list runs past the
    text read."""
    first_seen = ordinal <= 1
    last = ordinal
    for i in range(at - 1, -1, -1):
        it = _item(lines[i], lines[:i])
        if it and it[0] == kind:
            if kind != "bullet" and it[1] >= last:
                # Numbering that does not count down is another list: a
                # table of contents ("A. Definitions … G. Contact") above
                # the body's "A. Definitions.".
                return None
            last = it[1]
            first_seen = it[1] <= 1
            m = _ITEM_RE.match(lines[i])
            if first_seen and m and m.group("chain"):
                # "(5)(i) Time logs … when:": the list's parent is "(5)" on
                # the same line, with no lead-in of its own; the colon there
                # introduces what is nested under "(i)".
                return None
            continue
        if first_seen:
            # The line above the list's first item: the list's own lead-in,
            # or the item it is nested under. Anything else below the first
            # item — another kind of item, a plain line — belongs to a
            # sibling ("E-3. Financial set-up … the following steps:" over
            # "F. Contact information." is E's, not F's).
            return i
    return None


def lead_in(before: str, text: str) -> Optional[str]:
    """The lines that introduce the list ``text`` opens with, read from
    ``before`` (the same section's text up to where ``text`` starts),
    outermost first; None when ``text`` does not open with a list item or
    no colon-ended lead-in is found."""
    first = next(iter(_lines(text)), "")
    prior = _lines(before)
    it = _item(first, prior)
    if it is None:
        return None
    found: list[str] = []
    at, (kind, ordinal) = len(prior), it
    for _ in range(MAX_DEPTH):
        i = _introducer(prior, at, kind, ordinal)
        if i is None:
            break
        line = prior[i]
        if not _INTRO_RE.search(line.strip()):
            break
        found.append(_shorten(line))
        parent = _item(line, prior[:i])
        if parent is None:
            break
        at, (kind, ordinal) = i, parent
    return "\n".join(reversed(found)) or None


def _join(text: str, nxt: str) -> tuple[str, int]:
    """``text`` then ``nxt`` without the overlap a length-cut chunker
    repeats, and where ``nxt`` starts in the result."""
    for n in range(min(len(text), len(nxt), 600), 11, -1):
        if text.endswith(nxt[:n]):
            return text + nxt[n:], len(text) - n
    return f"{text}\n\n{nxt}", len(text) + 2


def attach_lead_ins(dm, kb_uuid: str, passages: list[dict]) -> list[dict]:
    """Set ``lead_in`` on each chunk in ``passages`` that opens with a list
    item whose lead-in sits in an earlier chunk of its section. In place;
    returns ``passages``. A section passage (``_section``) starts at its
    heading and needs none. ``dm`` is the document manager, or a function
    returning it, called only when a passage needs earlier chunks. Never
    raises: a chunk read that fails leaves the passage as it was."""
    wanted: dict[str, list[str]] = {}
    for r in passages:
        if "lead_in" in r or r.get("_section"):
            continue
        meta = r.get("metadata") or {}
        part = meta.get("section_part")
        if isinstance(part, int) and part <= 1:
            continue
        m = _CHUNK_ID_RE.match(str(r.get("chunk_id") or ""))
        if not m or not _item(next(iter(_lines(r.get("content") or "")), "")):
            continue
        n = int(m.group(2))
        back = min(LOOKBACK_CHUNKS, n, part - 1 if isinstance(part, int) else LOOKBACK_CHUNKS)
        wanted[str(r["chunk_id"])] = [f"{m.group(1)}_chunk_{i}" for i in range(n - back, n)]
    if not wanted:
        return passages
    ids = list(dict.fromkeys(i for v in wanted.values() for i in v))
    try:
        if not hasattr(dm, "get_kb_chunks_by_ids") and callable(dm):
            dm = dm()
        by_id = {c.get("chunk_id"): c for c in dm.get_kb_chunks_by_ids(kb_uuid, ids) or []}
    except Exception as e:  # noqa: BLE001 — the passage stands without it
        logger.debug("Lead-in read failed for %s: %s", kb_uuid, e)
        return passages
    for r in passages:
        earlier = wanted.get(str(r.get("chunk_id")))
        if not earlier:
            continue
        key = (r.get("metadata") or {}).get("section_key")
        text = ""
        for cid in earlier:
            c = by_id.get(cid)
            if c is None or (key and (c.get("metadata") or {}).get("section_key") != key):
                text = ""   # a gap, or another section: only what follows counts
                continue
            text = _join(text, c.get("content") or "")[0] if text else (c.get("content") or "")
        if not text:
            continue
        joined, at = _join(text, r.get("content") or "")
        found = lead_in(joined[:at], r.get("content") or "")
        if found:
            r["lead_in"] = found
    return passages


def with_lead_in(content: str, lead: Optional[str]) -> str:
    """A passage's text as the model reads it: the list's lead-in, marked as
    earlier text of the same section, above the chunk."""
    if not lead:
        return content
    return f"[Lead-in, earlier in this section: {lead}]\n{content}"
