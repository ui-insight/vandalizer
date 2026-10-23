"""Structure-aware chunking for knowledge-base sources.

Knowledge-base chunks used to be cut every 1,000 characters with a
200-character overlap, whatever the text said. A section shorter than a chunk
("§ 200.423 Alcoholic beverages. The cost of alcoholic beverages is
unallowable.") shared its chunk with two or three neighbours, so neither the
embedding nor the reranker ever read it alone, and three chunks in four
carried no heading at all.

Here a source is cut where its structure says. Section headings are hard
boundaries — 2 CFR's "§ 200.414 Indirect (F&A) costs.", FAR's "31.205-6
Compensation…", "Appendix III to Part 200—…", a policy page's "45.13 - Program
Income" — and no chunk spans two sections. Sub-headings ("C-1. Indirect
rate.", "A. General."), markdown headings and tables are soft boundaries: a
chunk starts at one when it can, and a stub of a sub-section is folded into
the next one. A long section is packed line by line into chunks of at most
``MAX_CHARS``, cut evenly instead of leaving a stub at the end. There is no
overlap: a section is whole across its chunks, in order.

Each chunk carries where it sits — its section key and title, the heading
path above it, and which part of its section it is — so the index
(:mod:`app.services.kb_retrieval`) need not rebuild sections from chunk
order, a citation can name the section, and the embedding reads the heading
with the text: the document stored is the text alone, the vector is of
``heading path + "\\n" + text`` (:meth:`DocumentManager.add_to_kb`).

The heading patterns are the ones the index has always used to rebuild
sections over chunks cut by length — still the path for sources chunked
before this existed — so both agree on what a section is.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import NamedTuple, Optional

#: Bumped whenever the split changes, so the migration
#: (:mod:`app.services.kb_rechunk`) knows which sources to rebuild. Version 1
#: was the fixed 1,000-character window with a 200-character overlap; sources
#: chunked with it carry no version.
CHUNKER_VERSION = 2
#: The most characters of source text in a chunk (a repeated table header
#: counts). The default embedder reads about 256 tokens, so the heading path
#: and the text it embeds must stay near this.
MAX_CHARS = 1000
# A sub-section shorter than this is folded into the next one when both fit.
MIN_CHARS = 250
# How far past an even share of a long section a cut may land to end a line.
_CUT_SLACK = 120
HEADING_PATH_MAX_CHARS = 300

# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------

_MD = r"[ \t]*(?:#{1,6}[ \t]+)?"
# "§ 200.414 Indirect costs.", FAR's "31.205-6 Compensation…".
SECTION_RE = re.compile(
    rf"^{_MD}(?:§[ \t]*)?(?P<num>\d{{1,4}}\.\d{{1,4}}(?:-\d{{1,3}})?[a-z]?)(?![\d(\-–—]|\.\d)[ \t]+(?P<title>[A-Z\[][^\n]{{0,200}})$",
    re.MULTILINE,
)
# A numbered policy page: "45.10 - Facilities and Administrative (Indirect) Rate".
POLICY_RE = re.compile(
    rf"^{_MD}(?P<num>\d{{1,3}}\.\d{{1,3}})[ \t]+[-–—][ \t]+(?P<title>[A-Z][^\n]{{0,200}})$",
    re.MULTILINE,
)
# "Appendix III to Part 200—Indirect (F&A) Costs Identification and …".
APPENDIX_RE = re.compile(rf"^{_MD}(?P<num>Appendix [IVXLC]+)\b(?P<title>[^\n]{{0,240}})$", re.MULTILINE)
# "Subpart E—Cost Principles": a group boundary, not a section of its own.
GROUP_RE = re.compile(rf"^{_MD}(?:Subpart|SUBPART|Part|PART)[ \t]+[\w.]+[ \t]*(?:[-—–:][^\n]*)?$", re.MULTILINE)
# Sub-headings inside a section: "C-1. Indirect rate.", "D. Policy.", "A. General".
SUB_RE = re.compile(r"^(?P<label>[A-Z](?:-\d+)?(?:\.[a-z])?)\.[ \t]+(?P<text>[^\n]{2,160})", re.MULTILINE)
# A defined term: "Program income means …".
DEFINITION_RE = re.compile(r"^(?P<term>[A-Z][^\n]{1,90}?) (?:means|is defined)\b", re.MULTILINE)
NUMBER_IN_NAME_RE = re.compile(r"(?<![\d.])(\d{1,4}\.\d{1,4}(?:-\d{1,3})?)(?![\d])")
# "## Allowable costs" — a document converted to markdown.
_MARKDOWN_HEADING_RE = re.compile(r"^[ \t]*(?P<level>#{1,6})[ \t]+(?P<text>[^\n]{1,200}?)[ \t#]*$", re.MULTILINE)
# A numbered heading on a line of its own: Appendix III's "1. Indirect (F&A) cost pools."
_NUMBERED_HEADING_RE = re.compile(r"^\d{1,2}\.[ \t]+[A-Z][^\n]{2,90}$", re.MULTILINE)
# eCFR's undesignated centre heading ("Procurement Standards") ends the text
# before the sections it heads: it belongs to the next one.
_CENTER_HEADING_TAIL_RE = re.compile(r"\n[ \t]*[A-Z][^\d\n]{0,78}[^\d\s.;:,)\]]\s*$")
_HEADING_RES = (SECTION_RE, POLICY_RE, APPENDIX_RE, GROUP_RE)


def short_title(text: str) -> str:
    """'C-2. Residual funds. Residual funds are …' -> 'Residual funds'."""
    m = re.match(r"([^.:\n]{2,90})[.:]", text)
    return (m.group(1) if m else text[:90]).strip()


def title_words(heading: str) -> str:
    """The words of a heading without its number or trailing period."""
    text = re.sub(r"^\s*#{1,6}\s*", "", heading)
    text = re.sub(r"^§\s*", "", text)
    text = re.sub(r"^(?:\d{1,4}\.\d{1,4}(?:-\d{1,3})?[a-z]?|Appendix [IVXLC]+(?: to Part \d+)?)\s*[-–—:]?\s*", "", text)
    return text.strip().rstrip(".").strip()


def is_definitions(heading: str) -> bool:
    return bool(re.search(r"\bdefinitions\b", heading or "", re.IGNORECASE))


class Bound(NamedTuple):
    """One section of a source's text: ``[start, end)``, its key ("200.414",
    "Appendix III", "45.13", ``group:…`` for a Subpart or Part title,
    ``source:…`` for text under no heading) and its heading line. ``front``
    marks the text before the first heading, named by the source."""
    start: int
    end: int
    key: str
    heading: str
    front: bool = False

    @property
    def group(self) -> bool:
        return self.key.startswith("group:")


def section_bounds(text: str, name: str = "") -> list[Bound]:
    """The sections of a source's text, in order. Whatever precedes the first
    heading is keyed by the section number in the source's name, if it has
    one, else by the name."""
    marks: list[tuple[int, str, str]] = []
    for rx in (SECTION_RE, POLICY_RE, APPENDIX_RE):
        for m in rx.finditer(text):
            marks.append((m.start(), m.group("num"), m.group(0).strip()))
    for m in GROUP_RE.finditer(text):
        if not any(abs(m.start() - at) < 3 for at, _, _ in marks):
            marks.append((m.start(), f"group:{m.group(0).strip()[:60]}", m.group(0).strip()))
    marks.sort()
    # A contents list names each section on a line of its own: a heading
    # with nothing but the next heading after it is a contents line, not
    # the section (a one-sentence section such as "See § 200.425." stays).
    marks = [mk for i, mk in enumerate(marks)
             if i + 1 >= len(marks) or mk[1].startswith("group:")
             or len(text[mk[0]:marks[i + 1][0]].strip()) > len(mk[2]) + 2]
    front = not marks or marks[0][0] > 0
    if front:
        m = NUMBER_IN_NAME_RE.search(name)
        marks.insert(0, (0, m.group(1) if m else f"source:{name[:60]}", name))
    return [
        Bound(at, marks[i + 1][0] if i + 1 < len(marks) else len(text), key, head, front and i == 0)
        for i, (at, key, head) in enumerate(marks)
    ]


def sub_headings(text: str) -> list[tuple[int, str]]:
    """(offset, short title) of each sub-heading ("C-1. Indirect rate.")."""
    return [(m.start(), short_title(m.group("text"))) for m in SUB_RE.finditer(text)]


def heading_path(bound: Bound, *, sub: Optional[str], content: str) -> str:
    """What a chunk sits under: its section heading, then the sub-heading
    over it, and for a definitions section the terms the chunk defines."""
    parts = [re.sub(r"\s+", " ", bound.heading).strip(), sub or ""]
    if is_definitions(bound.heading):
        parts.append("; ".join(m.group("term") for m in list(DEFINITION_RE.finditer(content))[:6]))
    return " — ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

class Chunk(NamedTuple):
    text: str
    offset: int                 # where the text starts in the source
    section_key: str
    section_title: str
    heading_path: str
    section_part: int           # 1-based, in source order
    section_parts: int


def _segments(text: str, bounds: list[Bound]) -> list[tuple[int, int, Bound]]:
    """One span per section, hard boundaries between them. A Subpart title,
    or text before the first heading, too short to stand alone opens the
    section after it; an eCFR centre heading closing a section moves to the
    section it heads."""
    out: list[tuple[int, int, Bound]] = []
    carry: Optional[int] = None
    for i, b in enumerate(bounds):
        start = b.start if carry is None else carry
        carry = None
        end = b.end
        if i + 1 < len(bounds):
            line_end = text.find("\n", b.start, b.end)
            line_end = b.end if line_end < 0 else line_end
            if (b.group or b.front) and len(text[line_end if b.group else b.start:b.end].strip()) < MIN_CHARS:
                carry = start
                continue
            if not b.group:
                while (tail := _CENTER_HEADING_TAIL_RE.search(text, line_end, end)) \
                        and len(text[line_end:tail.start()].strip()) >= 20:
                    end = tail.start() + 1
                if end < b.end:
                    carry = end
        out.append((start, end, b))
    return out


def _inner_headings(text: str) -> list[tuple[int, int, str]]:
    """(offset, level, title) of the headings inside sections, in order:
    markdown headings (levels 1–6) that are not section headings themselves
    ("## § 200.414 …" is the section), then "C." (7), "C-1." or a numbered
    heading line (8), "C-1.a." (9)."""
    out = [
        (m.start(), len(m.group("level")), m.group("text").strip())
        for m in _MARKDOWN_HEADING_RE.finditer(text)
        if not any(rx.match(text, m.start()) for rx in _HEADING_RES)
    ]
    for m in SUB_RE.finditer(text):
        label = m.group("label")
        out.append((m.start(), 9 if "." in label else 8 if "-" in label else 7, short_title(m.group("text"))))
    out.extend((m.start(), 8, short_title(re.sub(r"^\d{1,2}\.\s*", "", m.group(0))))
               for m in _NUMBERED_HEADING_RE.finditer(text))
    return sorted(out)


def _sub_path(start: int, end: int, bound: Bound, inner: list[tuple[int, int, str]]) -> Optional[str]:
    """The headings inside ``bound`` over the chunk ``[start, end)``: those
    over the stretch of it under one heading that holds most of its text — a
    chunk that opens on a sub-section's last lines and is mostly the next one
    is named by the next one."""
    marks = [h for h in inner if bound.start <= h[0] < end]
    best, best_len = None, -1
    edges = [start] + [at for at, _, _ in marks if at > start] + [end]
    for a, b in zip(edges, edges[1:]):
        if b - a > best_len:
            best, best_len = a, b - a
    stack: list[tuple[int, int, str]] = []
    for at, level, title in marks:
        if at > best:
            break
        while stack and stack[-1][1] >= level:
            stack.pop()
        stack.append((at, level, title))
    return " — ".join(t for _, _, t in stack) or None


def _blocks(text: str, start: int, end: int, soft: list[int], max_chars: int) -> list[tuple[int, int]]:
    """``[start, end)`` cut at its soft boundaries, a short block opening the
    one after it (a caption before a table, "B. Scope." before "C.")."""
    cuts = [start] + [p for p in soft if start < p < end] + [end]
    floor = min(MIN_CHARS, max_chars // 4)
    out: list[tuple[int, int]] = []
    for a, b in zip(cuts, cuts[1:]):
        if not text[a:b].strip():
            continue
        if out and len(text[out[-1][0]:out[-1][1]].strip()) < floor:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def _cut(text: str, lo: int, hi: int, limit: int) -> int:
    """Where to end a chunk: a line end, else a sentence end, else a space,
    the nearest before ``hi`` and failing that before ``limit``."""
    for sep, shift in (("\n", 0), (". ", 1), ("; ", 1), (" ", 0)):
        c = text.rfind(sep, lo, hi)
        if c < lo:
            c = text.rfind(sep, lo, limit)
        if c >= lo:
            return c + shift
    return limit


def _pack(text: str, a: int, b: int, max_chars: int,
          tables: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """``[a, b)`` as (start, end, text) chunks of at most ``max_chars``. A chunk
    that starts inside a table repeats the table's header rows, so its
    numbers keep their column labels; the offset is still where its own
    text starts."""
    from app.services.document_manager import _TABLE_HEADER_MAX_CHARS

    out: list[tuple[int, int, str]] = []
    pos = a
    while pos < b:
        while pos < b and text[pos].isspace():
            pos += 1
        if pos >= b:
            break
        header = next((h for s, e, h in tables if s < pos < e and 0 < len(h) <= _TABLE_HEADER_MAX_CHARS), "")
        room = max(1, max_chars - (len(header) + 1 if header else 0))
        if b - pos <= room:
            cut = b
        else:
            share = math.ceil((b - pos) / math.ceil((b - pos) / room))
            cut = _cut(text, pos + room // 3, pos + min(room, share + _CUT_SLACK), pos + room)
        piece = text[pos:cut].rstrip()
        if piece:
            end = pos + len(piece)
            if header and not piece.startswith(header):
                piece = f"{header}\n{piece}"
            out.append((pos, end, piece))
        pos = cut
    return out


def chunk_source(text: str, name: str = "", *, max_chars: int = MAX_CHARS) -> list[Chunk]:
    """A source's text as chunks that follow its sections (see the module
    docstring). ``name`` is the source's name, which keys and heads any text
    before its first heading."""
    if not text or not text.strip():
        return []
    from app.services.document_manager import _find_table_spans

    bounds = section_bounds(text, name)
    inner = _inner_headings(text)
    tables = _find_table_spans(text) if "|" in text else []
    soft = sorted({at for at, _, _ in inner} | {s for s, _, _ in tables})

    pieces: list[tuple[int, int, str, Bound]] = []
    for start, end, bound in _segments(text, bounds):
        for a, b in _blocks(text, start, end, soft, max_chars):
            pieces.extend((*piece, bound) for piece in _pack(text, a, b, max_chars, tables))

    parts = Counter(bound.key for *_, bound in pieces)
    seen: Counter = Counter()
    out: list[Chunk] = []
    for offset, end, piece, bound in pieces:
        seen[bound.key] += 1
        out.append(Chunk(
            text=piece, offset=offset, section_key=bound.key,
            section_title=title_words(bound.heading),
            heading_path=heading_path(
                bound, sub=_sub_path(offset, end, bound, inner), content=piece,
            )[:HEADING_PATH_MAX_CHARS],
            section_part=seen[bound.key], section_parts=parts[bound.key],
        ))
    return out
