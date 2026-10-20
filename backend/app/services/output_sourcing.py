"""Trace each statement in a workflow's output to where it came from.

After a run completes, every statement its outputs make (see
``output_statements``) is checked against two kinds of source: the run's
input documents, and every knowledge-base passage retrieved anywhere in the
run. A statement is linked only when all of these hold:

1. a temperature-0 judge, shown the statement and a few candidate passages,
   says one passage itself states it, and copies the excerpt that does;
2. that excerpt is in the passage the judge named, contiguous and verbatim
   (after folding case, whitespace, dashes and quotes, and ignoring the
   ``**``/``<u>`` formatting marks a text extractor writes) — checked here,
   not taken on the model's word, and an excerpt found twice there on
   different pages is refused, since it cannot say which page it means;
3. every number, date and identifier in the statement is in the excerpt as
   the same value (``extraction_sources.value_supported_by_quote`` plus the
   date/time/percent forms it does not cover);
4. the excerpt shares a content word with the statement or its label, says
   most of a statement of several words (not just its subject's name), the
   passage is about what a one- or two-word statement's label names, and
   for a statement with values, a shared word sits on a value's own line or
   the line before it with no other figure of the same kind in between —
   a form that lists labels in one block and figures in another cannot say
   which figure is the "Total Direct Costs", and is refused;
5. the page is the engine's: the document's ``text_markers`` at the
   excerpt's offset, keeping the estimated-page flag for scans.

Anything else — no candidate passage, a judge error, a check that fails —
leaves the statement plain. Nothing here changes an output: the result is a
separate sidecar (``sourcing``) the UI draws underlines from.

Pure logic plus one injected model call (``ask``); no database access.
"""

from __future__ import annotations

import bisect
import contextvars
import json
import logging
import math
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Callable

from app.services.extraction_sources import (
    normalize_with_map,
    page_marker_for_offset,
    value_supported_by_quote,
)
from app.services.output_statements import Statement, split_output
from app.services.page_locator import with_marker_provenance

logger = logging.getLogger(__name__)

VERSION = 1

WINDOW_CHARS = 700         # a candidate passage shown to the judge
WINDOW_STRIDE = 350        # windows overlap by half, so a short excerpt sits whole in one
KB_WHOLE_CHARS = 1400      # a knowledge-base passage this short is one window
CANDIDATES = 3             # passages per statement
BATCH_STATEMENTS = 8       # statements per judge call
BATCH_CHARS = 12000        # passage text per judge call
MAX_JUDGED = 300           # statements judged per run; the rest stay plain
MIN_QUOTE_CHARS = 12
MAX_QUOTE_CHARS = 600
BIND_MAX_CHARS = 160       # how far a label word may sit from its value
COVERAGE_MIN_WORDS = 4     # statements this long must be mostly in the excerpt:
COVERAGE_TEXT = 0.3        # share of the statement's own content words, or
COVERAGE_WITH_LABEL = 0.35  # share of its and its label's words together;
COVERAGE_TEXT_VALUES = 0.2  # less for a statement its values already anchor
COVERAGE_WITH_LABEL_VALUES = 0.25
EXCERPT_CONTEXT = 320      # document text kept either side of a quote for display

JUDGE_INSTRUCTIONS = (
    "You check statements taken from an AI-written report against passages from the "
    "documents and knowledge bases the report was written from. Each statement comes with "
    "a label — the field, table row or heading it sits under, which says what the statement "
    "is about — and the ids of up to three passages to check it against.\n\n"
    "For each statement decide whether one of its passages itself states it: the same "
    "subject and the same facts — every name, number, date, amount and condition in the "
    "statement — connected in the passage the way the statement connects them.\n\n"
    "Answer supported: false when\n"
    "- the passage only shares some words, names or numbers with the statement without "
    "stating what it says;\n"
    "- a number or date in the passage belongs to a different item than the statement's "
    "label (forms often list labels in one block and amounts in another; when you cannot "
    "tell which amount goes with which label, answer false);\n"
    "- the statement is a judgment, conclusion, recommendation, count, calculation or summary "
    "of several facts that the passage does not state in so many words (\"allowable\", "
    "\"eligible: yes\", \"no red flags\", \"falls within the period\", a total someone added up);\n"
    "- the statement says anything the passage does not.\n\n"
    "When supported is true, give the passage id and copy the excerpt of that passage that "
    "states it: one contiguous run of the passage's text, copied character for character, "
    "at most 300 characters, including the words that name the subject together with the "
    "values. Never skip words inside it, never use an ellipsis, never correct spelling or "
    "spacing.\n\n"
    "Reply with JSON only: "
    '{"items": [{"id": 1, "supported": true, "passage": "P2", "quote": "..."}, '
    '{"id": 2, "supported": false}]}'
)


# ---------------------------------------------------------------------------
# Values: numbers, dates, times and identifiers, with where they are
# ---------------------------------------------------------------------------

_MON = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_ORD = r"(?:st|nd|rd|th)?"

_DATE_PATTERNS = [
    ("ymd", re.compile(r"(?<![\d/.-])(\d{4})-(\d{1,2})-(\d{1,2})(?![\d])")),
    ("mdy", re.compile(r"(?<![\d/.-])(\d{1,2})[/-](\d{1,2})[/-](\d{4}|\d{2})(?![\d/])")),
    ("Mdy", re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}}){_ORD},?\s+(\d{{4}})\b", re.I)),
    ("dMy", re.compile(rf"\b(\d{{1,2}}){_ORD}\s+(?:of\s+)?({_MON})\.?,?\s+(\d{{4}})\b", re.I)),
]
_MONTH_YEAR_RE = re.compile(rf"\b({_MON})\.?,?\s+(\d{{4}})\b", re.I)
_MONTH_DAY_RE = re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}}){_ORD}\b", re.I)
_TIME_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s?m\b\.?|\b(\d{1,2}):(\d{2})\b|\b(noon|midnight)\b", re.I,
)
_TITLE_PREFIX_RE = re.compile(r"\b\d{1,2}\s*(?:C\.?F\.?R|U\.?S\.?C)\.?", re.I)
_DASHED_ID_RE = re.compile(r"(?<![\w.,])\d+(?:-\d+){2,}(?![\w])|(?<![\w.,])\d{3,}-\d{3,}(?![\w])")
_ALNUM_ID_RE = re.compile(
    r"(?<![\w$])(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{2,}(?:[-/.][A-Za-z0-9]+)*(?![\w])"
)
_NUMBER_RE = re.compile(
    r"(?<![\w.,])(\$\s?)?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s*(k|m|b|thousand|million|billion)\b)?"
    r"(\s*(?:%|percent\b|per\s+cent\b))?",
    re.I,
)
_SUFFIX = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}


@dataclass(frozen=True)
class Value:
    kind: str      # date | month | md | time | id | num | pct
    key: str
    start: int
    end: int
    raw: str
    # Whether value_supported_by_quote understands this form; the rest are
    # compared by key alone (percent words, times, money with K/M suffixes).
    literal_check: bool = False


def _num_key(v: float) -> str:
    s = f"{abs(v):.6f}".rstrip("0").rstrip(".")
    return s or "0"


def _month(word: str) -> int | None:
    return _MONTHS.get(word.lower()[:3])


def _year(y: str) -> int:
    n = int(y)
    return n + 2000 if len(y) == 2 else n


def _valid_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


# One character for one, so offsets into the folded text are offsets into
# the original: models and PDF text layers write "2025‑03‑14" with
# non-breaking hyphens and "50 %" with a narrow no-break space.
_FOLD = str.maketrans({
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-",
    "−": "-", " ": " ", " ": " ", " ": " ", " ": " ",
})


def values_in(text: str) -> list[Value]:
    """Every value in ``text``, each once, in order. A date's numbers are
    part of the date and a "2 CFR" title is part of the section it names,
    so neither yields a stray number."""
    original = text or ""
    text = original.translate(_FOLD)
    taken: list[tuple[int, int]] = []
    out: list[Value] = []

    def free(a: int, b: int) -> bool:
        return all(b <= x or a >= y for x, y in taken)

    def add(v: Value) -> None:
        taken.append((v.start, v.end))
        out.append(v)

    for kind, rx in _DATE_PATTERNS:
        for m in rx.finditer(text):
            if not free(m.start(), m.end()):
                continue
            g = m.groups()
            if kind == "ymd":
                d = _valid_date(int(g[0]), int(g[1]), int(g[2]))
            elif kind == "mdy":
                d = _valid_date(_year(g[2]), int(g[0]), int(g[1]))
            elif kind == "Mdy":
                mo = _month(g[0])
                d = _valid_date(int(g[2]), mo, int(g[1])) if mo else None
            else:
                mo = _month(g[1])
                d = _valid_date(int(g[2]), mo, int(g[0])) if mo else None
            if d:
                add(Value("date", f"date:{d.isoformat()}", m.start(), m.end(), m.group(), True))
    for m in _MONTH_YEAR_RE.finditer(text):
        mo = _month(m.group(1))
        if mo and free(m.start(), m.end()):
            add(Value("month", f"month:{int(m.group(2)):04d}-{mo:02d}", m.start(), m.end(), m.group()))
    for m in _MONTH_DAY_RE.finditer(text):
        mo = _month(m.group(1))
        day = int(m.group(2))
        if mo and 1 <= day <= 31 and free(m.start(), m.end()):
            add(Value("md", f"md:{mo:02d}-{day:02d}", m.start(), m.end(), m.group()))
    for m in _TIME_RE.finditer(text):
        if not free(m.start(), m.end()):
            continue
        if m.group(6):
            hh, mm = (12, 0) if m.group(6).lower() == "noon" else (0, 0)
        elif m.group(3):
            hh, mm = int(m.group(1)), int(m.group(2) or 0)
            if not 1 <= hh <= 12:
                continue
            hh = hh % 12 + (12 if m.group(3).lower() == "p" else 0)
        else:
            hh, mm = int(m.group(4)), int(m.group(5))
        if hh > 23 or mm > 59:
            continue
        add(Value("time", f"time:{hh:02d}:{mm:02d}", m.start(), m.end(), m.group()))
    for m in _TITLE_PREFIX_RE.finditer(text):
        if free(m.start(), m.end()):
            taken.append((m.start(), m.end()))
    for m in _DASHED_ID_RE.finditer(text):
        if free(m.start(), m.end()):
            add(Value("id", "id:" + re.sub(r"[^0-9]", "", m.group()), m.start(), m.end(), m.group(), True))
    for m in _ALNUM_ID_RE.finditer(text):
        tok = m.group()
        if not free(m.start(), m.end()):
            continue
        if re.fullmatch(r"\d+(?:st|nd|rd|th)", tok, re.I) or re.fullmatch(r"\d+(?:\.\d+)?[kmb]", tok, re.I):
            continue   # an ordinal or "300K": a number, below
        add(Value("id", "id:" + re.sub(r"[^a-z0-9]", "", tok.lower()), m.start(), m.end(), tok, True))
    for m in _NUMBER_RE.finditer(text):
        a, b = m.start(), m.end()
        if not free(a, b):
            continue
        digits = m.group(2)
        if "," not in digits and "." not in digits and len(digits) >= 7:
            # A long run of digits is an identifier (DUNS, account), compared as written.
            add(Value("id", "id:" + digits, a, b, m.group(), True))
            continue
        n = float(digits.replace(",", ""))
        suffix = (m.group(3) or "").lower()
        if suffix:
            n *= _SUFFIX[suffix]
        if m.group(4):
            add(Value("pct", f"pct:{_num_key(n)}", a, b, m.group()))
        else:
            add(Value("num", f"num:{_num_key(n)}", a, b, m.group(), not suffix))
    # Ordinals ("1st") are numbers too.
    for m in re.finditer(r"(?<![\w.,])(\d+)(?:st|nd|rd|th)\b", text, re.I):
        if free(m.start(), m.end()):
            add(Value("num", f"num:{_num_key(float(m.group(1)))}", m.start(), m.end(), m.group(1), True))
    out.sort(key=lambda v: v.start)
    return [replace(v, raw=original[v.start:v.end]) for v in out]


def _quote_keys(values: list[Value]) -> set[str]:
    """Keys a passage offers: a full date also offers its year, its month
    and its month-day, so "Fall 2022" or "July 13" can be found in it."""
    keys = set()
    for v in values:
        keys.add(v.key)
        if v.kind == "date":
            y, mo, d = v.key[5:].split("-")
            keys.update({f"num:{int(y)}", f"month:{y}-{mo}", f"md:{mo}-{d}"})
        elif v.kind == "month":
            keys.add(f"num:{int(v.key[6:10])}")
    return keys


# ---------------------------------------------------------------------------
# Content words
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’]*[A-Za-z]|[A-Za-z]")
_STOP = frozenset("""
a an the and or nor but of to in on for by with from at as is are was were be been being am
this that these those it its it's their they them there here which who whom whose what when
where how why not no yes if then than so such into onto upon over under per via any all each
every some may must shall should will would can could also only other more most very up out
about after before between within without during through both either neither own same too just
our your his her we you he she i me my mine us do does did done has have had having
""".split())


def stem(word: str) -> str:
    w = word.lower().replace("’", "'")
    if w.endswith("'s"):
        w = w[:-2]
    w = w.strip("'")
    if len(w) > 5 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
    elif len(w) > 4 and w.endswith("es") and w[-3] in "sxz":
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    if len(w) > 4 and w.endswith("e"):
        w = w[:-1]
    return w


def word_positions(text: str) -> list[tuple[str, int, int]]:
    """``(stem, start, end)`` of each content word."""
    out = []
    for m in _WORD_RE.finditer(text or ""):
        w = m.group()
        if w.lower().replace("’", "'") in _STOP:
            continue
        s = stem(w)
        if len(s) >= 3 and s not in _STOP:
            out.append((s, m.start(), m.end()))
    return out


def stems(text: str) -> set[str]:
    return {s for s, _, _ in word_positions(text)}


# Label words that name a slot rather than a subject ("item", "name").
_GENERIC_LABEL_WORDS = frozenset(stem(w) for w in (
    "item", "items", "name", "type", "detail", "details", "description", "value", "category",
    "categories", "field", "note", "notes", "summary", "text", "label", "title", "list", "entry",
    "kind", "data", "info", "information", "other", "general", "specific", "source", "document",
))


# ---------------------------------------------------------------------------
# Sources and their candidate windows
# ---------------------------------------------------------------------------

# Formatting marks a text extractor writes around words (Docling's
# "**All grants require …**", "*(up to 500 words)*", "<u>Budget Form</u>"):
# not text, and a judge copying the words drops or moves them.
_MARKUP_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9]{0,10}\s*/?>|[*`]+|(?<![A-Za-z0-9])_+|_+(?![A-Za-z0-9])")


def fold(text: str) -> tuple[str, list[int]]:
    """``normalize_with_map`` after dropping formatting marks: the text the
    words are compared in, and each character's offset in ``text``. Words,
    their order and everything between them must still match — an ellipsis
    or a skipped word does not."""
    kept: list[str] = []
    where: list[int] = []
    last = 0
    for m in _MARKUP_RE.finditer(text or ""):
        kept.append(text[last:m.start()])
        where.extend(range(last, m.start()))
        last = m.end()
    kept.append((text or "")[last:])
    where.extend(range(last, len(text or "")))
    norm, nmap = normalize_with_map("".join(kept))
    return norm, [where[i] for i in nmap]


@dataclass
class _Source:
    kind: str              # document | kb
    text: str
    meta: dict
    norm: tuple[str, list[int]] | None = None
    markers: list[dict] | None = None

    def normalized(self) -> tuple[str, list[int]]:
        if self.norm is None:
            self.norm = fold(self.text)
        return self.norm


@dataclass
class _Window:
    src: int
    start: int
    end: int
    tf: Counter
    length: int
    keys: set


def window_bounds(text: str, size: int = WINDOW_CHARS, stride: int = WINDOW_STRIDE) -> list[tuple[int, int]]:
    """Overlapping ``[start, end)`` windows over ``text``, cut at line ends
    or spaces where one is near."""
    n = len(text)
    out: list[tuple[int, int]] = []
    s = 0
    while s < n:
        e = min(n, s + size)
        if e < n:
            nl = text.find("\n", e, min(n, e + 100))
            if nl != -1:
                e = nl
            else:
                sp = text.rfind(" ", s + size // 2, e)
                if sp != -1:
                    e = sp
        out.append((s, e))
        if e >= n:
            break
        ns = s + stride
        nl = text.rfind("\n", s + 1, ns + 1)
        if nl != -1 and ns - nl <= 100:
            ns = nl + 1
        else:
            sp = text.rfind(" ", s + 1, ns + 1)
            if sp != -1 and ns - sp <= 60:
                ns = sp + 1
        s = max(ns, s + 1)
    return out


class Corpus:
    """The run's sources cut into windows, with an inverted index for
    picking each statement's candidates."""

    def __init__(self, documents: list[dict], passages: list[dict]) -> None:
        self.sources: list[_Source] = []
        for d in documents or []:
            text = d.get("raw_text") or d.get("text") or ""
            if isinstance(text, str) and text.strip():
                self.sources.append(_Source(
                    "document", text, d,
                    markers=with_marker_provenance(d.get("text_markers")) or [],
                ))
        for p in passages or []:
            text = p.get("content") if isinstance(p, dict) else None
            if isinstance(text, str) and text.strip():
                self.sources.append(_Source("kb", text, p))
        self.windows: list[_Window] = []
        self.by_stem: dict[str, set[int]] = defaultdict(set)
        self.by_key: dict[str, set[int]] = defaultdict(set)
        for si, src in enumerate(self.sources):
            bounds = (
                [(0, len(src.text))] if src.kind == "kb" and len(src.text) <= KB_WHOLE_CHARS
                else window_bounds(src.text)
            )
            for a, b in bounds:
                chunk = src.text[a:b]
                words = [w for w, _, _ in word_positions(chunk)]
                tf = Counter(words)
                keys = _quote_keys(values_in(chunk))
                wi = len(self.windows)
                self.windows.append(_Window(si, a, b, tf, max(1, len(words)), keys))
                for w in tf:
                    self.by_stem[w].add(wi)
                for k in keys:
                    self.by_key[k].add(wi)
        self.avg_len = (sum(w.length for w in self.windows) / len(self.windows)) if self.windows else 1.0

    def idf(self, term: str) -> float:
        n = len(self.windows)
        df = len(self.by_stem.get(term, ()))
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def _bm25(self, terms: set[str], w: _Window, weight: float = 1.0) -> float:
        k1, b = 1.2, 0.75
        score = 0.0
        for t in terms:
            f = w.tf.get(t, 0)
            if f:
                score += weight * self.idf(t) * f * (k1 + 1) / (f + k1 * (1 - b + b * w.length / self.avg_len))
        return score

    def candidates(self, st: Statement, k: int = CANDIDATES) -> list[int]:
        """The windows most likely to state ``st``: every value in it must be
        there; then the words of the statement, and less so of its label."""
        words = stems(st.text)
        label_words = stems(st.label) - words
        keys = {v.key for v in values_in(st.text)}
        if keys:
            pool = None
            for key in keys:
                hits = self.by_key.get(key, set())
                pool = hits if pool is None else pool & hits
                if not pool:
                    return []
            pool = {wi for wi in pool if any(t in self.windows[wi].tf for t in words | label_words)}
        else:
            if not words:
                return []
            counts: Counter = Counter()
            for t in words:
                for wi in self.by_stem.get(t, ()):
                    counts[wi] += 1
            need = min(2, len(words))
            pool = {wi for wi, c in counts.items() if c >= need}
        scored = sorted(
            ((self._bm25(words, self.windows[wi]) + self._bm25(label_words, self.windows[wi], 0.5), wi) for wi in pool),
            key=lambda x: (-x[0], x[1]),
        )
        chosen: list[int] = []
        for score, wi in scored:
            if score <= 0:
                break
            w = self.windows[wi]
            # Neighbouring windows share half their text; offering both
            # spends the judge's attention on the same lines twice.
            if any(
                self.windows[c].src == w.src
                and min(self.windows[c].end, w.end) - max(self.windows[c].start, w.start) >= (w.end - w.start) // 3
                for c in chosen
            ):
                continue
            chosen.append(wi)
            if len(chosen) >= k:
                break
        return chosen

    def window_text(self, wi: int) -> str:
        w = self.windows[wi]
        return self.sources[w.src].text[w.start:w.end]

    def window_heading(self, wi: int) -> str:
        w = self.windows[wi]
        src = self.sources[w.src]
        if src.kind == "document":
            title = src.meta.get("title") or "Document"
            marker = page_marker_for_offset(w.start, src.markers or [])
            if marker:
                return f"{title}, {'p. ~' if marker.get('approximate') else 'p. '}{marker.get('value')}"
            return title
        return src.meta.get("label") or src.meta.get("document_title") or "Knowledge base passage"


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _find_all(src: _Source, quote: str, start: int, end: int) -> list[tuple[int, int]]:
    """Raw ``[start, end)`` of each place ``quote`` occurs inside
    ``src.text[start:end]``, compared after normalization."""
    norm_text, index_map = src.normalized()
    nq, _ = fold(quote)
    if not nq:
        return []
    lo = bisect.bisect_left(index_map, start)
    hi = bisect.bisect_left(index_map, end)
    out = []
    at = norm_text.find(nq, lo, hi)
    while at != -1:
        last = at + len(nq) - 1
        out.append((index_map[at], index_map[last] + 1))
        at = norm_text.find(nq, at + 1, hi)
    return out


def _values_supported(st_values: list[Value], quote: str, quote_values: list[Value]) -> bool:
    keys = _quote_keys(quote_values)
    for v in st_values:
        if v.key not in keys:
            return False
        if v.literal_check:
            ok, _ = value_supported_by_quote(v.raw.strip(), quote)
            if ok is not True:
                return False
    return True


def _bound(st_values: list[Value], shared: set[str], quote: str, quote_values: list[Value]) -> bool:
    """Each value in the statement sits beside a word it shares with the
    excerpt: on the same line or the one before, close by, with no other
    figure of the same kind between them that the statement does not name."""
    st_keys = {v.key for v in st_values}
    words = [(s, a, b) for s, a, b in word_positions(quote) if s in shared]
    if not words:
        return False
    for v in st_values:
        spots = [q for q in quote_values if q.key == v.key or v.key in _quote_keys([q])]
        if not spots:
            return False
        ok = False
        for q in spots:
            for _, a, b in words:
                if b <= q.start:
                    lo, hi = b, q.start
                elif q.end <= a:
                    lo, hi = q.end, a
                else:
                    lo = hi = a   # the word is part of the value's own text
                between = quote[lo:hi]
                if len(between) > BIND_MAX_CHARS or between.count("\n") > 1:
                    continue
                if any(
                    o.kind == q.kind and o.start >= lo and o.end <= hi
                    and o.key not in st_keys and not (_quote_keys([o]) & st_keys)
                    for o in quote_values
                ):
                    continue
                ok = True
                break
            if ok:
                break
        if not ok:
            return False
    return True


@dataclass
class Verdict:
    link: dict | None
    reason: str


def verify(st: Statement, corpus: Corpus, wi: int, quote: str) -> Verdict:
    """Whether the judge's ``quote`` from window ``wi`` may source ``st``;
    when it may, the source entry the UI shows."""
    quote = (quote or "").strip()
    if len(quote) > MAX_QUOTE_CHARS:
        return Verdict(None, "quote_too_long")
    nq, _ = fold(quote)
    if len(nq) < MIN_QUOTE_CHARS or len(nq.split()) < 2:
        return Verdict(None, "quote_too_short")
    w = corpus.windows[wi]
    src = corpus.sources[w.src]
    spots = _find_all(src, quote, w.start, w.end)
    if not spots:
        return Verdict(None, "quote_not_in_passage")
    exact = src.text[spots[0][0]:spots[0][1]]

    st_values = values_in(st.text)
    q_values = values_in(exact)
    if not _values_supported(st_values, exact, q_values):
        return Verdict(None, "value_not_in_quote")
    text_words, quote_words = stems(st.text), stems(exact)
    words = text_words | stems(st.label)
    shared = words & quote_words
    if not shared:
        return Verdict(None, "no_shared_word")
    # A statement of several words needs an excerpt that says most of it,
    # not one that only names its subject: "acquire matching-fund letters
    # early to avoid delays" is not stated by "Matching Fund Verification
    # Letter(s)", nor "documentation confirming the purchase is authorized
    # under award L24AC00293-00" by "Award: L24AC00293-00". The label counts
    # too, for a statement the model paraphrased. A statement with values is
    # also anchored by them, so it needs less of its wording.
    if len(text_words) >= COVERAGE_MIN_WORDS:
        need_text, need_all = (
            (COVERAGE_TEXT_VALUES, COVERAGE_WITH_LABEL_VALUES) if st_values
            else (COVERAGE_TEXT, COVERAGE_WITH_LABEL)
        )
        if (
            len(text_words & quote_words) / len(text_words) < need_text
            and len(shared) / len(words) < need_all
        ):
            return Verdict(None, "quote_covers_too_little")
    # A one- or two-word statement ("USD", "Travel") says little on its own;
    # its label says what it is about ("Expense Record — currency",
    # "approved budget categories"). The passage the judge read must be
    # about that too, or "ALL AMOUNTS ARE SHOWN IN USD" on the award would
    # source the expense's currency.
    label_only = stems(st.label) - text_words - _GENERIC_LABEL_WORDS
    if len(text_words) <= 2 and label_only and not (label_only & stems(corpus.window_text(wi))):
        return Verdict(None, "label_not_in_passage")
    if st_values and not _bound(st_values, shared, exact, q_values):
        return Verdict(None, "value_not_bound_to_label")

    if src.kind == "document":
        pages = set()
        approx = False
        for a, _ in spots:
            marker = page_marker_for_offset(a, src.markers or [])
            pages.add(marker.get("value") if marker else None)
            approx = approx or bool(marker and marker.get("approximate"))
        if len(pages) > 1:
            return Verdict(None, "quote_on_several_pages")
        start, end = spots[0]
        return Verdict(_document_link(src, start, end, pages.pop(), approx), "ok")
    if len(spots) > 1 and len({_kb_page(src, a) for a, _ in spots}) > 1:
        return Verdict(None, "quote_on_several_pages")
    return Verdict(_kb_link(src, *spots[0]), "ok")


def _excerpt(text: str, start: int, end: int) -> tuple[str, int, int]:
    """The source text around ``[start, end)`` for display, cut at line
    breaks, with the quote's offsets inside it."""
    lo = max(0, start - EXCERPT_CONTEXT)
    hi = min(len(text), end + EXCERPT_CONTEXT)
    nl = text.find("\n", lo, start)
    if nl != -1 and lo > 0:
        lo = nl + 1
    nl = text.rfind("\n", end, hi)
    if nl != -1 and hi < len(text):
        hi = nl
    return text[lo:hi], start - lo, end - lo


def _document_link(src: _Source, start: int, end: int, page, approx: bool) -> dict:
    excerpt, qs, qe = _excerpt(src.text, start, end)
    link = {
        "kind": "document",
        "document_uuid": src.meta.get("uuid"),
        "document_title": src.meta.get("title") or "Document",
        "page": page if isinstance(page, int) and not isinstance(page, bool) else None,
        "quote": src.text[start:end],
        "excerpt": excerpt, "quote_start": qs, "quote_end": qe,
        "offset": start,
    }
    if approx:
        link["page_approximate"] = True
    return link


_KB_PAGE_RE = re.compile(r"\[p\. ~?(\d+)\]")


def _kb_page(src: _Source, offset: int):
    """The page of a place in a knowledge-base passage: the last "[p. N]"
    break before it (a passage that crosses pages carries them), else the
    passage's own page."""
    page = None
    for m in _KB_PAGE_RE.finditer(src.text, 0, offset):
        page = int(m.group(1))
    return page if page is not None else src.meta.get("page")


def _kb_link(src: _Source, start: int, end: int) -> dict:
    excerpt, qs, qe = _excerpt(src.text, start, end)
    m = src.meta
    inside = any(True for _ in _KB_PAGE_RE.finditer(src.text, 0, start))
    page = _kb_page(src, start)
    link = {
        "kind": "kb",
        "kb_title": m.get("kb_title"), "kb_uuid": m.get("kb_uuid"),
        "label": m.get("label"), "document_title": m.get("document_title"),
        "chunk_id": m.get("chunk_id"),
        "page": page if isinstance(page, int) and not isinstance(page, bool) else None,
        "page_end": None if inside else m.get("page_end"),
        "quote": src.text[start:end],
        "excerpt": excerpt, "quote_start": qs, "quote_end": qe,
    }
    if m.get("page_approximate"):
        link["page_approximate"] = True
    return link


# ---------------------------------------------------------------------------
# The judge
# ---------------------------------------------------------------------------

def _judge_prompt(items: list[tuple[int, Statement, list[int]]], corpus: Corpus) -> tuple[str, dict[str, int]]:
    ids: dict[int, str] = {}
    parts = ["PASSAGES"]
    for _, _, cands in items:
        for wi in cands:
            if wi not in ids:
                ids[wi] = f"P{len(ids) + 1}"
                parts.append(
                    f'<passage id="{ids[wi]}" source="{corpus.window_heading(wi)}">\n'
                    f"{corpus.window_text(wi).strip()}\n</passage>"
                )
    parts.append("STATEMENTS")
    for n, st, cands in items:
        parts.append(json.dumps(
            {"id": n, "label": st.label, "statement": st.text, "passages": [ids[wi] for wi in cands]},
            ensure_ascii=False,
        ))
    return "\n\n".join(parts), {v: k for k, v in ids.items()}


def _parse(reply: str) -> dict[int, dict]:
    from app.services.workflow_validator import _extract_json

    data = _extract_json(reply)
    items = data.get("items") if isinstance(data, dict) else data
    out: dict[int, dict] = {}
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and isinstance(it.get("id"), int) and not isinstance(it.get("id"), bool):
            out[it["id"]] = it
    return out


def _judge_batch(
    batch: list[tuple[str, Statement, list[int]]], corpus: Corpus, ask: Callable[[str, str], str],
) -> dict[str, Verdict]:
    items = [(n, st, cands) for n, (_, st, cands) in enumerate(batch, 1)]
    prompt, by_id = _judge_prompt(items, corpus)
    verdicts = _parse(ask(JUDGE_INSTRUCTIONS, prompt))
    out: dict[str, Verdict] = {}
    for n, (key, st, cands) in enumerate(batch, 1):
        v = verdicts.get(n) or {}
        try:
            if v.get("supported") is not True:
                out[key] = Verdict(None, "judge_unsupported")
                continue
            wi = by_id.get(str(v.get("passage") or "").strip())
            if wi is None or wi not in cands:
                out[key] = Verdict(None, "judge_named_no_passage")
                continue
            q = v.get("quote")
            out[key] = verify(st, corpus, wi, q if isinstance(q, str) else "")
        except Exception as e:  # noqa: BLE001 — a check that cannot run links nothing
            logger.warning("Source check failed for one statement: %s", e)
            out[key] = Verdict(None, "check_error")
    return out


def _batches(jobs: list[tuple[str, Statement, list[int]]], corpus: Corpus) -> list[list]:
    jobs = sorted(jobs, key=lambda j: (corpus.windows[j[2][0]].src, corpus.windows[j[2][0]].start))
    out: list[list] = []
    cur: list = []
    seen: set[int] = set()
    chars = 0
    for job in jobs:
        new = [wi for wi in job[2] if wi not in seen]
        add = sum(corpus.windows[wi].end - corpus.windows[wi].start for wi in new)
        if cur and (len(cur) >= BATCH_STATEMENTS or chars + add > BATCH_CHARS):
            out.append(cur)
            cur, seen, chars = [], set(), 0
            new = list(job[2])
            add = sum(corpus.windows[wi].end - corpus.windows[wi].start for wi in new)
        cur.append(job)
        seen.update(new)
        chars += add
    if cur:
        out.append(cur)
    return out


# ---------------------------------------------------------------------------
# A run's sourcing
# ---------------------------------------------------------------------------

def statement_key(st: Statement) -> str:
    return json.dumps([st.text.strip().lower(), st.label.strip().lower()], ensure_ascii=False)


@dataclass
class _Run:
    sources: list[dict] = field(default_factory=list)
    index: dict = field(default_factory=dict)

    def add(self, link: dict) -> int:
        key = (
            link.get("kind"), link.get("document_uuid") or link.get("chunk_id") or link.get("label"),
            link.get("offset", link.get("quote_start")), link.get("quote"),
        )
        if key not in self.index:
            self.index[key] = len(self.sources)
            self.sources.append({k: v for k, v in link.items() if k != "offset"})
        return self.index[key]


def trace_sources(
    targets: dict,
    documents: list[dict],
    passages: list[dict],
    *,
    ask: Callable[[str, str], str],
    deadline: float | None = None,
    workers: int = 3,
    max_judged: int = MAX_JUDGED,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Source every statement of every output in ``targets`` (key → value).

    Returns the sidecar the UI draws from::

        {"version", "status": "done", "sources": [link, …],
         "targets": {key: {"format", "statements": [{"s", "e", "p"?, "src"?, "t"?}],
                           "summary": {"statements", "traced"}}},
         "judged", "unchecked", "errors"}

    ``s``/``e`` are offsets into a text output (``format: text``) or into
    the leaf string at path ``p`` (``format: json``; absent for a whole
    number leaf). A text output that is JSON also gives each statement's
    path ``p`` and its offsets inside that leaf, ``ls``/``le``. Offsets
    count code points. ``src`` indexes ``sources``; ``t`` marks an
    ``absent`` or ``verdict`` statement. The outputs themselves are only read.
    """
    corpus = Corpus(documents, passages)
    split: dict[str, tuple[str, list[Statement]]] = {}
    unique: dict[str, Statement] = {}
    for key, value in (targets or {}).items():
        fmt, stmts = split_output(value)
        split[key] = (fmt, stmts)
        for st in stmts:
            if st.kind == "claim":
                unique.setdefault(statement_key(st), st)

    jobs = []
    for skey, st in unique.items():
        cands = corpus.candidates(st)
        if cands:
            jobs.append((skey, st, cands))
    unchecked = max(0, len(jobs) - max_judged)
    jobs = jobs[:max_judged]

    verdicts: dict[str, Verdict] = {}
    errors = 0
    batches = _batches(jobs, corpus)
    if batches and deadline is not None and clock() >= deadline:
        unchecked += len(jobs)
        batches = []
    if batches:
        pool = ThreadPoolExecutor(max_workers=max(1, workers))
        try:
            futures = {
                pool.submit(contextvars.copy_context().run, _judge_batch, b, corpus, ask): b
                for b in batches
            }
            remaining = None if deadline is None else max(0.0, deadline - clock())
            done, pending = wait(futures, timeout=remaining)
            for f in pending:
                f.cancel()
                unchecked += len(futures[f])
            for f in done:
                try:
                    verdicts.update(f.result())
                except Exception as e:  # noqa: BLE001 — a failed call links nothing
                    logger.warning("Source judge call failed: %s", e)
                    errors += 1
                    unchecked += len(futures[f])
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    run = _Run()
    out_targets: dict[str, dict] = {}
    for key, (fmt, stmts) in split.items():
        rows = []
        traced = 0
        for st in stmts:
            row: dict = {}
            if st.path is not None:
                row["p"] = st.path
            if st.start is not None:
                row["s"], row["e"] = st.start, st.end
            if fmt == "text" and "leaf" in st.extra:
                # JSON written as text: also where the statement sits inside
                # its leaf, for a view that pretty-prints the JSON.
                row["ls"], row["le"] = st.extra["leaf"]
            if st.kind != "claim":
                row["t"] = st.kind
            else:
                v = verdicts.get(statement_key(st))
                if v is not None and v.link is not None:
                    row["src"] = run.add(v.link)
                    traced += 1
            rows.append(row)
        out_targets[key] = {
            "format": fmt, "statements": rows,
            "summary": {"statements": len(rows), "traced": traced},
        }
    return {
        "version": VERSION,
        "status": "done",
        "sources": run.sources,
        "targets": out_targets,
        "judged": len(jobs),
        "unchecked": unchecked,
        "errors": errors,
        "reasons": dict(Counter(v.reason for v in verdicts.values())),
    }
