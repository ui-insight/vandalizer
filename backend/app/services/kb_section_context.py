"""Which section of its source a retrieved knowledge-base passage sits in.

Support ticket: asked for the full NIH prior-approval list, chat searched the
NIH Grants Policy Statement and built a table from the passages. It credited
"direct charging administrative/clerical salaries" (8.1.1.5, an NIH Standard
Term of Award) to Exhibit 7, the summary of actions requiring prior approval;
it said the equipment threshold was not returned when the passage read
"Purchase of a unit of equipment exceeding $25,000"; and it left out the
Exhibit 7 row for 8.1.2.17.

Each of those passages was a 1,000-character slice that began in the middle
of a section, or in the middle of a table that continues over a page break,
and carried no heading. The model had only neighbouring passages to guess
which section or table a slice belonged to. The source's full text is stored
beside its chunks, so the heading each passage starts under can be read from
it and sent with the passage.
"""

from __future__ import annotations

import re
from typing import Optional

# A heading line: "8.1.2.5 Change in Scope", "§ 200.308 Revision of budget
# and program plans.", "Exhibit 7. Summary of Actions Requiring …". A lone
# number ("7. Fixed Rates …") is as likely a list item, so it is not one.
_NUMBERED_RE = re.compile(r"(?P<num>\d+(?:\.\d+)+)\.?\s+(?P<title>[A-Z][^\n]*)")
_SECTION_SIGN_RE = re.compile(r"§\s*(?P<num>\d+(?:\.\d+)+)\s+(?P<title>[A-Z][^\n]*)")
_CAPTION_RE = re.compile(
    r"(?P<kind>Exhibit|Table|Appendix)\s+(?P<num>[A-Z0-9]+(?:[.-]\d+)*)\s*[.:]\s+(?P<title>[A-Z][^\n]*)"
)
_MAX_HEADING_CHARS = 160
# A passage is looked up by its opening text. Long enough to be unique in a
# chapter, short enough to survive a table header the splitter prepended.
_PROBE_CHARS = 160


class _Heading:
    __slots__ = ("offset", "label", "number", "caption")

    def __init__(self, offset: int, label: str, number: Optional[str], caption: bool) -> None:
        self.offset = offset
        self.label = label
        self.number = number
        self.caption = caption


def _clean(line: str) -> str:
    return " ".join(line.split()).rstrip(" :,")


def _reads_as_title(title: str) -> bool:
    """Title Case or ALL CAPS, as a heading is; a sentence is not.

    A wrapped citation leaves "75.100. Pass-through entities may, but are not
    required, to negotiate …" at the start of a line.
    """
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'/-]*", title) if len(w) > 3]
    if not words:
        return True
    return bool(sum(1 for w in words if w[0].isupper()) * 2 >= len(words))


def _headings(text: str) -> list[_Heading]:
    out: list[_Heading] = []
    pos = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and len(stripped) <= _MAX_HEADING_CHARS:
            m = _SECTION_SIGN_RE.fullmatch(stripped)
            if m is None:
                m = _NUMBERED_RE.fullmatch(stripped)
                if m and not _reads_as_title(m.group("title")):
                    m = None
            if m and stripped.count(")") <= stripped.count("("):
                # "8.1.2.5 Change in Scope) for details" is a wrapped
                # cross-reference, not a heading.
                out.append(_Heading(pos, _clean(stripped), m.group("num"), False))
            else:
                c = _CAPTION_RE.fullmatch(stripped)
                if c:
                    out.append(_Heading(pos, _clean(stripped), None, True))
        pos += len(line) + 1
    return out


def _locate(text: str, passage: str) -> int:
    """Offset of *passage* in *text*, or -1."""
    passage = passage.strip()
    if not passage:
        return -1
    at = text.find(passage)
    if at != -1:
        return at
    # A chunk that starts inside a pipe table carries that table's header in
    # front of its own text, so the whole chunk is not a substring. Its later
    # lines still are.
    for line in passage.split("\n")[1:4]:
        probe = line.strip()[:_PROBE_CHARS]
        if len(probe) >= 40 and text.count(probe) == 1:
            return text.find(probe)
    probe = passage[:_PROBE_CHARS]
    return text.find(probe) if len(probe) >= 40 else -1


class SectionIndex:
    """The headings of one source's text, for labelling passages from it."""

    def __init__(self, text: str) -> None:
        self._text = text or ""
        self._headings = _headings(self._text)

    def section_for(self, passage: str) -> Optional[str]:
        """The heading *passage* starts under, with its parent section.

        ``"8.1.1 NIH Standard Terms of Award > 8.1.1.5 Direct Charging
        Salaries of Administrative and Clerical Staff"``. A passage that
        starts inside an exhibit or table names it after the section holding
        it. None when the source has no recognisable headings before the
        passage, or the passage can't be found in it.
        """
        if not self._headings:
            return None
        at = _locate(self._text, passage)
        if at == -1:
            return None
        before = [h for h in self._headings if h.offset <= at]
        if not before:
            return None
        current = before[-1]
        parts: list[str] = []
        section = current
        if current.caption:
            # An exhibit runs until the next numbered heading; it belongs to
            # the nearest one above it.
            numbered = [h for h in before if not h.caption]
            if not numbered:
                return current.label
            section = numbered[-1]
        parent = self._parent(before, section)
        if parent is not None:
            parts.append(parent.label)
        parts.append(section.label)
        if current.caption:
            parts.append(current.label)
        return " > ".join(parts)

    @staticmethod
    def _parent(before: list[_Heading], section: _Heading) -> Optional[_Heading]:
        if not section.number or "." not in section.number:
            return None
        parent_number = section.number.rsplit(".", 1)[0]
        for h in reversed(before):
            if h.number == parent_number:
                return h
        return None


SECTION_NOTE = (
    "`section` is where the passage BEGINS in its source (parent section > "
    "section > exhibit or table). A passage with no heading of its own belongs "
    "to that section or table, and may be the continuation of a table that "
    "began in another passage. Credit each statement to the section or table "
    "it sits in, not to one named in a neighbouring passage. A heading inside "
    "the passage starts a new section from that point."
)
