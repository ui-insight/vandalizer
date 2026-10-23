"""Trace each statement in a workflow's output to where it came from.

After a run completes, every statement its outputs make (see
``output_statements``) is checked against two kinds of source: the run's
input documents, and every knowledge-base passage retrieved anywhere in the
run. A statement is linked only when all of these hold:

1. a temperature-0 judge, shown the statement and a few candidate passages,
   says one passage itself states it, and copies the excerpt that does;
2. that excerpt is in the passage the judge named, verbatim (after folding
   case, whitespace, dashes and quotes, and ignoring the ``**``/``<u>``
   formatting marks a text extractor writes) — checked here, not taken on
   the model's word, and an excerpt found twice there on different pages
   is refused, since it cannot say which page it means. An ellipsis at
   either end is dropped; an excerpt the judge cut with one inside counts
   only when every piece is there, in order, within one page — then the
   whole stretch is shown and a separate call must confirm it. An excerpt
   that is not in the named passage but is, word for word, in exactly one
   place among the other passages offered for the statement is checked
   there instead. A statement of several words that is itself word for
   word in a source must link to that place;
3. every number, date, identifier and section number ("F.2") in the
   statement is in the excerpt as the same value
   (``extraction_sources.value_supported_by_quote`` plus the
   date/time/percent forms it does not cover; "two" is 2);
4. the excerpt shares a content word with the statement or its label, says
   most of a statement of several words (not just its subject's name), the
   passage is about what a one- or two-word statement's label names (or a
   field it names otherwise: "Type of Award" for "Funding Instrument"), and
   for a statement with values, a shared word sits on a value's own line or
   the line before it with no other figure of the same kind in between —
   a form that lists labels in one block and figures in another cannot say
   which figure is the "Total Direct Costs", and is refused, while the far
   end of a range, a list under a plural heading ("Submission Window
   Date(s): …") and a list of the statement's own figures are not "other
   figures". An excerpt that only says a thing may or should be done, in
   itself or in its sentence, does not source a statement that it must
   (nor "must" an "optional"; see ``obligation_differs``), and one that
   requires it only in a case ("if using Government-furnished ATVs") does
   not source a statement that it is required outright
   (``condition_dropped``). A part of a
   submission named in the report's list of parts ("Data Management Plan")
   links only where the passage lists it, heads a section with it or asks
   for it (``presented_as_item``); a statement about one stage (the letter
   of intent, the full proposal) is not sourced to another's; a statement
   that names one part of a program by its abbreviation ("RAPID Facility
   certification…") needs that part named where it links, and so does a
   row scoped to one ("By end of sixth month of award (EF)") when nothing
   else ties it there;
5. the page is the engine's: the document's ``text_markers`` at the
   excerpt's offset, keeping the estimated-page flag for scans;
6. for a statement of a few words whose label says what it is in words of
   its own ("sponsor" over "Bureau of Land Management", "check name" over
   "Consistent Cost Treatment"), separate temperature-0 calls, asked only
   that, each confirm the excerpt itself gives it as what the label names.
   Every word of "sponsor: BLM, Southern Utah University" is in "…Bureau
   of Land Management (BLM), and Southern Utah University", and the judge
   said so; the university is the recipient, which no word count can see.
   And "Sponsor: National Science Foundation" was linked to the NSF's
   hearing-impaired relay service, because the text around it says the
   NSF awards grants;
7. for a statement whose excerpt may say less than it does — a case in the
   excerpt's sentence the statement leaves out, or for a statement of a
   rule, words the excerpt adds inside what it says ("funds budgeted for
   participant support costs" for "Transfer of funds between budget
   categories") — separate calls confirm the excerpt states all of it, a
   majority of three deciding (``narrows``).

A Markdown statement is judged with the headings and list items above it
(``Statement.context``), and a statement with no label of its own is
gated by the one it sits directly under (``field_label``). A first look
that misses gets a second look with more passages; one refused for what
its passage is about (a role, a sponsor, a part, a stage, a component) gets
a second look at other passages only.

Anything else — no candidate passage, a judge error, a check that fails —
leaves the statement plain. Nothing here changes an output: the result is a
separate sidecar (``sourcing``) the UI draws underlines from.

Pure logic plus injected model calls (``ask``); no database access.
"""

from __future__ import annotations

import bisect
import contextvars
import functools
import json
import logging
import math
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
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
RETRY_CANDIDATES = 5       # passages per statement on its second look
BATCH_STATEMENTS = 8       # statements per judge call
WORKERS = 16               # model calls at once: the server batches them, so more is faster up to a point
MAX_RETRIED = 160          # second looks per run
PUBLISH_EVERY = 0.75       # seconds between partial results written while tracing
BATCH_CHARS = 12000        # passage text per judge call
ROLE_BATCH = 8             # statements per role check
ROLE_MAX_WORDS = 6         # a statement this short takes its meaning from its label
ROLE_VOTES = 2             # role checks per statement; every one must say yes
MAX_JUDGED = 400           # statements judged per run; the rest stay plain
MIN_QUOTE_CHARS = 12
MAX_QUOTE_CHARS = 600
PIECE_MIN_WORDS = 2        # each piece of an excerpt the judge cut with "…"
PIECED_MAX_CHARS = 900     # from the first piece to the last
EDGE_CHARS = 150           # how far past its passage's edge an excerpt may run
VERBATIM_MIN_WORDS = 4     # a statement this long found word for word in a source came from there
BIND_MAX_CHARS = 160       # how far a label word may sit from its value
BIND_LIST_MAX_CHARS = 400  # how far down a list of values its heading may sit
ITEM_MAX_WORDS = 5         # a name of a part of a submission is no longer than this
LABEL_ABOVE_LINES = 8      # lines of values a label may head, read upward from an excerpt
COVERAGE_MIN_WORDS = 4     # statements this long must be mostly in the excerpt:
COVERAGE_TEXT = 0.3        # share of the statement's own content words, or
COVERAGE_WITH_LABEL = 0.35  # share of its and its label's words together;
COVERAGE_TEXT_VALUES = 0.2  # less for a statement its values already anchor
COVERAGE_WITH_LABEL_VALUES = 0.25
CONFIRM_BELOW = 0.8        # a linked statement with less of its wording in the excerpt is confirmed apart
EXCERPT_CONTEXT = 320      # document text kept either side of a quote for display

JUDGE_INSTRUCTIONS = (
    "You check statements taken from an AI-written report against passages from the "
    "documents and knowledge bases the report was written from. Each statement comes with "
    "a label — the field, table row or heading it sits under, which says what the statement "
    "is about — sometimes a context, the headings and list items above it (\"Eligible "
    "Individuals — Co-Principal Investigator\" makes \"Criteria: …\" the co-PI's criteria), "
    "and the ids of up to three passages to check it against.\n\n"
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
    "- the statement tells the reader what to do in this case (\"Obtain quotations…\", "
    "\"Provide documentation…\") and the passage is a rule that applies only under conditions "
    "or within a scope — a dollar threshold, a type of cost or purchase, a procurement method, "
    "an \"if …\" — that the statement does not itself show are met;\n"
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

# Asked apart from the judge, and only this: a judge that has just found
# every word of a statement in a passage reads it as stated. Saying first
# what the passage makes each item keeps a batch of easy yeses from
# carrying a wrong one along.
ROLE_INSTRUCTIONS = (
    "You check links between statements in an AI-written report and the passages they were traced to. "
    "Each statement is a few words — a name, a date, an amount, a short phrase — and its label, the field, "
    "table row or heading it sits under in the report, says what it is: a sponsor, a due date, a budget "
    "category. The statement's words are already known to be in the excerpt. Decide only whether the "
    "excerpt — the words a reader will see highlighted as this statement's source — gives the statement as "
    "what its label names. The passage around the excerpt only helps you read it: a role the passage gives "
    "elsewhere, outside the excerpt, does not count.\n\n"
    "For each statement, first say in passage_says, in a few words, what the passage makes each name, date "
    "or amount in the statement: its role, or the item it belongs to. Then answer shown.\n\n"
    "shown: true when the passage ties the statement to what its label names: by the label's words or its "
    "own words for the same thing, by a form field or heading the statement sits under, or by what a "
    "sentence says about it (\"X announces the program\" makes X its sponsor; \"applications are welcome "
    "from X\" makes X eligible).\n\n"
    "shown: false when\n"
    "- the passage gives a name, date or amount in the statement a different role, or puts it with a "
    "different item, than the label names (a party the passage names as the recipient is not the sponsor; "
    "the date of one event is not the date of another);\n"
    "- the statement lists several items and the passage gives any one of them a different role;\n"
    "- the statement is the name the report gives one of its own parts — a check, step or section it "
    "carries out — even when the passage is what that part is about: the report named it, the passage "
    "did not;\n"
    "- the excerpt only describes the organization or person itself — what it is, its history or legal "
    "basis, its services, offices or contact details — and does not tie it to this program, solicitation, "
    "award or document in the role the label names;\n"
    "- the label names a party — a sponsor, funder, issuing agency, recipient or applicant — and the excerpt "
    "does not say the name announces, issues, funds, awards, administers, receives or applies for this "
    "program, solicitation or award (a sentence about what the organization is, when it was created or what "
    "it does in general does not);\n"
    "- the excerpt does not let you tell.\n\n"
    "Reply with JSON only: "
    '{"items": [{"id": 1, "passage_says": "...", "shown": true}, {"id": 2, "passage_says": "...", "shown": false}]}'
)

# A second look is a second chance for the judge to say yes; a link it
# finds then must also be confirmed, apart, by a call asked only that.
RETRY_NOTE = (
    "\n\nThese statements were checked once and not linked. Read every passage offered for each "
    "statement afresh; some are new. When one states it, copy the excerpt exactly: one contiguous run "
    "of that passage, character for character, with no ellipsis, including the words that name the "
    "subject together with the values."
)

CONFIRM_INSTRUCTIONS = (
    "You check links between statements in an AI-written report and the excerpts they were traced to. "
    "Each item gives a statement, its label — the field, table row or heading it sits under — sometimes "
    "its context, the headings and list items above it, and an excerpt with the passage around it.\n\n"
    "Answer stated: true only when the excerpt itself states the statement: the same subject, and every "
    "fact in it — each name, number, date, amount and condition — connected as the statement connects "
    "them, read as its label and context put it.\n\n"
    "Answer stated: false when the excerpt only shares words with the statement; states something "
    "narrower, broader or conditional that the statement does not; needs a fact from outside the excerpt; "
    "is about a different item, person or program than the label and context name; or does not let you "
    "tell.\n\n"
    "Narrower or conditional includes an excerpt that limits what it says to a kind of cost, item, party, "
    "amount or case the statement leaves out: \"The transfer of funds budgeted for participant support "
    "costs to other budget categories\" does not state \"Transfer of funds between budget categories\", "
    "and \"required to complete a safety and training program if using Government-furnished ATVs\" does "
    "not state \"Mandatory safety and training courses\". A statement that keeps the limit, in its own "
    "words or its label, is stated. Leaving out what only explains or illustrates — an aside in "
    "parentheses, an example, a reason, who may do it, a definition's wording — does not make the excerpt "
    "narrower: \"funding for one or more project representatives (PI/co-PI/senior researcher) to attend the "
    "PI meeting\" states \"travel funding for at least one representative to attend the PI meeting\". Only "
    "a limit on what the rule covers does.\n\n"
    "Reply with JSON only: "
    '{"items": [{"id": 1, "stated": true}, {"id": 2, "stated": false}]}'
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
# A dotted section number with a letter and a digit in it: "F.2", "2.A",
# "II.C.2.d.iii". "Facility will be responsible for insurance (Section F.2)"
# was linked to item 1 of Section II.F: the statement names a section the
# excerpt is not.
_SECTION_REF_RE = re.compile(
    r"(?<![\w.])(?=[A-Za-z0-9.]*\d)(?=[A-Za-z0-9.]*[A-Za-z])(?:[A-Z]{1,4}|\d{1,3})(?:\.[A-Za-z0-9]{1,4})+(?![\w]|\.\w)"
)
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
# A number written as a word is the same value as the figure: "references
# up to 5 pages" is "References … up to five pages", and "maximum of two
# proposals per institution" is "Limit on Number of Proposals per
# Organization: 2".
_UNITS = ("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
          "sixteen seventeen eighteen nineteen").split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
# "Any collaboration letter may be no longer than a single page" is a
# one-page letter.
NUMBER_WORDS = {w: n for n, w in enumerate(_UNITS, 1)} | {w: 10 * n for n, w in enumerate(_TENS, 2)} | {"single": 1}
_NUMBER_WORD_RE = re.compile(
    rf"\b(?:({'|'.join(_TENS)})[-‐‑ ]({'|'.join(_UNITS[:9])})|({'|'.join(NUMBER_WORDS)}))\b", re.I,
)


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
    for m in _SECTION_REF_RE.finditer(text):
        if free(m.start(), m.end()):
            add(Value("id", "id:" + re.sub(r"[^a-z0-9]", "", m.group().lower()), m.start(), m.end(), m.group(), True))
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
    for m in _NUMBER_WORD_RE.finditer(text):
        if free(m.start(), m.end()):
            if m.group(1):
                n = NUMBER_WORDS[m.group(1).lower()] + NUMBER_WORDS[m.group(2).lower()]
            else:
                n = NUMBER_WORDS[m.group(3).lower()]
            add(Value("num", f"num:{n}", m.start(), m.end(), m.group()))
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


_NUMBER_STEMS = {stem(w): n for w, n in NUMBER_WORDS.items()}


# Label words that name a slot ("item", "name") or qualify one ("approved",
# "required") rather than name a subject. In a real run "approved budget
# categories — Supplies" passed on the expense record's "Approved by: PI";
# the subject, "budget", is what the passage has to be about.
_GENERIC_LABEL_WORDS = frozenset(stem(w) for w in (
    "item", "items", "name", "type", "detail", "details", "description", "value", "category",
    "categories", "field", "note", "notes", "summary", "text", "label", "title", "list", "entry",
    "kind", "data", "info", "information", "other", "general", "specific", "source", "document",
    "approved", "total", "required", "optional", "anticipated", "applicable", "maximum",
    "minimum", "estimated", "proposed", "current", "expected", "allowable", "special",
    "requirement", "requirements",
))

# Fields a funding announcement names in words of its own: "Funding
# Instrument: Cooperative Agreement" is stated as "Anticipated Type of
# Award: Cooperative Agreement"; a CFDA number is an "Assistance Listing".
# (label words, phrases a passage may use for them instead)
_LABEL_ALIASES: tuple[tuple[frozenset, tuple[str, ...]], ...] = (
    (frozenset({stem("instrument")}), ("award",)),
    (frozenset({stem("mechanism")}), ("award",)),
    (frozenset({stem("cfda")}), ("catalog of federal domestic assistance", "assistance listing")),
)


def _named_otherwise(label_words: set[str], passage: str) -> bool:
    """Whether ``passage`` names a field these label words name, in its own words."""
    low = " ".join(passage.lower().split())
    return any(
        keys <= label_words and any(re.search(rf"\b{re.escape(p)}", low) for p in phrases)
        for keys, phrases in _LABEL_ALIASES
    )


# ---------------------------------------------------------------------------
# How strongly something is asked: must, may, must not
# ---------------------------------------------------------------------------

# "Need not" and "not required" first: they say a thing is optional.
_NOT_REQUIRED_RE = re.compile(
    r"\bnot\s+(?:be\s+)?(?:required|mandatory|necessary)\b|\bneed\s+not\b|\bno\s+requirements?\b", re.I,
)
_FORBIDDEN_RE = re.compile(
    r"\b(?:must|shall|may|can|will|should)\s+not\b|\bcannot\b|\bcan[’']t\b|\bprohibit(?:s|ed|ing)?\b"
    r"|\bnot\s+(?:be\s+)?(?:permitted|allowed|authorized)\b",
    re.I,
)
# Not "obligated": funds are obligated, which is not a duty. A duty is also
# stated as a noun: "Requirement to complete DOI … Security Awareness
# training".
_REQUIRED_RE = re.compile(
    r"\b(?:must|shall|required|requires?|mandatory)\b|\brequirements?\s+(?:to|that)\b", re.I,
)
# "May" before a day or after a preposition is the month.
_PERMITTED_RE = re.compile(
    r"(?<!\bin )(?<!\bof )(?<!\bby )(?<!\bon )(?<!\bto )\bmay\b(?!\s*\d)|\bcan\b|\boptional(?:ly)?\b|\b(?:is|are) free to\b",
    re.I,
)
# Lower-case "should" only: a sentence that opens "Should a subaward be
# issued, …" is a condition, not advice.
_ADVISED_RE = re.compile(r"\bshould\b|\bSHOULD\b|\b(?i:encourag(?:e|es|ed|ing)|recommend(?:s|ed)?)\b")
# A cap is often written as leave ("a maximum of 10% may be used"): the
# same rule as "must not exceed 10%".
_LIMIT_RE = re.compile(
    r"\b(?:maximum|minimum|up to|no more than|no less than|at most|at least|not (?:to )?exceed|exceed(?:s|ing)?"
    r"|limit(?:s|ed)?|cap(?:s|ped)?|only)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Advice for this case, and rules that apply only in some cases
# ---------------------------------------------------------------------------

# Imperatives a report opens a recommendation or follow-up action with.
_ACTION_VERBS = frozenset("""
obtain provide request submit ensure verify document confirm maintain retain prepare collect attach
include register contact clarify secure acquire get seek consider follow complete file keep supply
upload send notify update revise add track monitor establish develop implement justify demonstrate
assess evaluate determine compare reconcile resolve gather identify check review
""".split())
_ACTION_LABEL_RE = re.compile(
    r"\bfollow[- ]?ups?\b|\brecommend|\bnext steps?\b|\bactions?\b|\bto[- ]dos?\b|\bremediat|\bmitigat", re.I,
)
# A rule that applies only in some cases: a condition, or a threshold.
_CONDITION_RE = re.compile(
    r"\b(?:if|unless|whenever|provided that|in the case of|in cases where|only when|only if)\b"
    r"|\bwhen\b(?!\s+(?:applicable|appropriate|possible|practicable|necessary|available|requested))"
    r"|\b(?:above|below|over|under|exceed(?:s|ing)?|in excess of|less than|more than|greater than)\s+"
    r"(?:the\s+)?(?:\$|micro-?purchase|simplified acquisition|threshold)"
    r"|[<>≤≥]\s*\$?\d"
    r"|\bthreshold\b",
    re.I,
)


# A clause that says when what a sentence states applies: "if using
# Government-furnished ATVs", "provided that …", "only when …". Not "even
# if" (the rule holds regardless), not "unless" (the exception is usually
# the rule itself: "no funds may be obligated unless all iron … is produced
# in the United States"), and not one that only hedges ("if applicable",
# "when allowed").
_IF_CLAUSE_RE = re.compile(
    r"(?<!\beven )\b(?:only\s+)?(?:if|whenever|when|provided\s+that|in\s+(?:the\s+)?cases?\s+(?:of|where))\b"
    r"(?!\s+(?:applicable|appropriate|possible|practicable|necessary|needed|available|any|requested|required"
    r"|allowed|permitted)\b)",
    re.I,
)
# Not the comma or point inside a figure: "a budget exceeding $600,000".
_CLAUSE_END_RE = re.compile(r"[,.](?!\d)|(?<!\d)[,.]|[;:()\n]|\s[-–—]\s")
# A precondition is a case too — "Before the recipient … are granted access
# to the BLM Federal computer system, they must first … complete …" — but
# only a clause with a verb: "before December 31" is a date.
_BEFORE_RE = re.compile(r"\b(?:before|prior\s+to)\b", re.I)
_VERB_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|being|has|have|had|can|could|will|would|shall|should|may|might|must"
    r"|(?!(?:during|including|regarding|concerning|following|pending|according|excluding|nothing|something"
    r"|anything|everything|thing|hundred|need|bed|red|shed)\b)[a-z]+(?:ing|ed))\b",
    re.I,
)
# A line a PDF wrapped mid-sentence: "…granted access to the BLM Federal \ncomputer system".
_WRAPPED_LINE_RE = re.compile(r"[ \t]*\n[ \t]*(?=[a-z])")
# A word this common in the source does not name a case: on a BLM award
# "Federal" and "system" are everywhere.
CASE_COMMON_MIN = 10
# Labels and headings a statement of a rule sits under: "prior approval
# requirements", "special conditions", "unallowable costs".
_RULE_CONTEXT_RE = re.compile(
    r"\b(?:requir|condition|approv|restrict|allow|unallow|prohibit|rules?\b|regulat|polic|complian|obligat"
    r"|mandat|eligib|terms?\b|limit)",
    re.I,
)
NARROWING_MIN_WORDS = 2    # words an excerpt adds inside what a statement says that make it narrower
NARROWING_VOTES = 3        # confirmations asked of a link whose excerpt may say less; a majority decides


def _case_clause(text: str, start: int) -> str:
    """The clause that opens at ``start``, read past commas until it has a
    verb: "the recipient, or any of its employees or subrecipients, are
    granted access to the BLM Federal computer system"."""
    rest = text[start:start + 240]
    end = 0
    while True:
        stop = _CLAUSE_END_RE.search(rest, end)
        if stop is None:
            return rest[:160].strip()
        end = stop.start()
        if rest[end] != "," or end > 160 or _VERB_RE.search(rest[:end]):
            return rest[:end].strip()
        end += 1


def _cases(text: str):
    """Each clause in ``text`` that says when what it states applies."""
    text = _WRAPPED_LINE_RE.sub(" ", text or "")
    found = [(m.end(), False) for m in _IF_CLAUSE_RE.finditer(text)]
    found += [(m.end(), True) for m in _BEFORE_RE.finditer(text)]
    for at, needs_verb in sorted(found):
        clause = _case_clause(text, at)
        if needs_verb and not _VERB_RE.search(clause):
            continue
        yield clause


def dropped_condition(st: Statement, text: str, common: frozenset = frozenset()) -> str | None:
    """A clause in ``text`` saying when what it states applies that the
    statement, its label and its headings do not name: the case the
    statement leaves out. None when there is no such clause. A word common
    in the source (``common``) does not name a case: on a BLM award
    "Federal" and "system" are everywhere."""
    have = stems(st.text) | stems(st.label) | stems(" ".join(st.context))
    for clause in _cases(text):
        words = stems(clause) - _GENERIC_LABEL_WORDS
        if not words:
            continue
        if not (words & have) - common:
            return clause
    return None


def condition_dropped(st: Statement, text: str, common: frozenset = frozenset()) -> bool:
    """Whether a statement says outright that something must (or must not)
    be done, sourced to text that says so only in some case it leaves out:
    "Mandatory BLM‑approved safety and training courses" from "required to
    complete a BLM-approved … safety and training program if using
    Government-furnished ATVs". Only the statement's own words count: under
    "required components", "Maximum 2 pages" is the plan's page limit, not
    a claim that the plan is always required. A statement with a case of
    its own is left to the confirmation (``narrows``)."""
    required, forbidden, _ = obligation(st.text)
    if not (required or forbidden) or _CONDITION_RE.search(st.text) or next(_cases(st.text), None) is not None:
        return False
    return dropped_condition(st, text, common) is not None


@functools.lru_cache(maxsize=16)
def common_words(text: str) -> frozenset:
    """Content words that occur at least ``CASE_COMMON_MIN`` times in ``text``."""
    counts: dict[str, int] = {}
    for s, _, _ in word_positions(text):
        counts[s] = counts.get(s, 0) + 1
    return frozenset(s for s, n in counts.items() if n >= CASE_COMMON_MIN)


def _added_inside(st: Statement, quote: str) -> str | None:
    """The longest run of words the excerpt has, between the first and the
    last word it shares with the statement, that the statement (and its
    label and headings) does not: "participant support costs" in "The
    transfer of funds budgeted for participant support costs to other budget
    categories" for "Transfer of funds between budget categories". Only the
    statement's own words bound the stretch read: "2 CFR 200.403(b)" under
    "regulation anchor" says nothing an excerpt could narrow."""
    own = stems(st.text)
    have = own | stems(st.label) | stems(" ".join(st.context))
    pos = word_positions(quote)
    shared = [i for i, (s, _, _) in enumerate(pos) if s in own]
    if len(shared) < 2:
        return None
    best: list = []
    run: list = []
    for s, a, b in pos[shared[0]:shared[-1] + 1] + [("", 0, 0)]:
        if s in have or not s:
            best, run = (run if len(run) > len(best) else best), []
        else:
            run.append((a, b))
    return quote[best[0][0]:best[-1][1]] if len(best) >= NARROWING_MIN_WORDS else None


def narrows(st: Statement, link: dict | None) -> bool:
    """Whether an excerpt may say less than its statement, in a way no word
    count can settle: it attaches a case the statement leaves out, or — for
    a statement of a rule, by its own words or the label and headings it sits
    under — adds words inside what the statement says ("funds budgeted for
    participant support costs" for "funds"). Then a separate call must
    confirm the excerpt states all of it."""
    if not link:
        return False
    quote = link.get("judge_quote") or link.get("quote") or ""
    excerpt, qs, qe = link.get("excerpt") or "", link.get("quote_start"), link.get("quote_end")
    sentence = sentence_around(excerpt, qs, qe) if isinstance(qs, int) and isinstance(qe, int) else ""
    if dropped_condition(st, quote) or dropped_condition(st, sentence):
        return True
    rule = any(obligation(st.text)) or bool(_RULE_CONTEXT_RE.search(" ".join([st.label or "", *st.context])))
    return rule and _added_inside(st, quote) is not None


def is_action(st: Statement) -> bool:
    """Whether a statement tells the reader what to do in this case: it
    opens with an imperative ("Obtain vendor quotations…"), or sits under a
    follow-up or recommendation label. A verb followed by a number names a
    thing: "Track 1 requests >$100,000…" is about a track."""
    first = re.match(r"\W*([A-Za-z]+)(\s+\d)?", st.text or "")
    imperative = bool(first and first.group(1).lower() in _ACTION_VERBS and not first.group(2))
    return imperative or bool(_ACTION_LABEL_RE.search(st.label or ""))


def _sentence_start(text: str, pos: int, lo: int = 0) -> int:
    """Where the sentence (or line) holding ``text[pos - 1]`` begins, not
    before ``lo``."""
    dot, nl = text.rfind(". ", lo, pos), text.rfind("\n", lo, pos)
    return max(dot + 2 if dot != -1 else lo, nl + 1 if nl != -1 else lo, lo)


def sentence_around(text: str, start: int, end: int) -> str:
    """The sentence (or list item) ``text[start:end]`` sits in."""
    lo = _sentence_start(text, start)
    stops = [i for i in (text.find(". ", end), text.find("\n", end)) if i != -1]
    hi = min(stops) + 1 if stops else len(text)
    return text[lo:hi]


# ---------------------------------------------------------------------------
# Whose rule it is: the PI's or a co-PI's; whose program: this one
# ---------------------------------------------------------------------------

_CO_ROLE_RE = re.compile(r"\bco[-‐‑ ]?(?:pis?|principal|investigators?)\b", re.I)
_PI_ROLE_RE = re.compile(r"(?<![-‐‑\w])(?:pis?|principal investigators?)\b", re.I)


def _role_named(text: str) -> str | None:
    """"co" or "pi" when ``text`` speaks of a co-PI or of the PI only."""
    co, pi = bool(_CO_ROLE_RE.search(text or "")), bool(_PI_ROLE_RE.search(text or ""))
    if co == pi:
        return None
    return "co" if co else "pi"


def subject_differs(st: Statement, sentence: str) -> bool:
    """Whether a statement about a co-PI is sourced to a sentence that
    speaks of the PI only, or the reverse. A statement with no subject of
    its own ("Criteria: Must be a full-time employee…") is about the list
    item it sits under. Seen in the NSF run: the co-investigator's criterion
    linked to "The PI must be a full-time employee…", which the RFA says of
    the PI alone; its context named the co-investigator, and the judge
    linked it anyway."""
    role = _role_named(st.text) or _role_named(" ".join([st.label, *st.context[-1:]]))
    if role is None:
        return False
    co, pi = bool(_CO_ROLE_RE.search(sentence)), bool(_PI_ROLE_RE.search(sentence))
    return (not co and pi) if role == "co" else (co and not pi)


# A label that names who offers the opportunity. The documents that name
# the organization most often describe it — "The National Science
# Foundation (NSF) is an independent Federal agency…", its relay service
# for the hearing-impaired — which says nothing of who sponsors this one.
_PARTY_LABEL_RE = re.compile(
    r"\b(?:sponsor|funder|grantor|funding (?:agency|organi[sz]ation|source)"
    r"|(?:issuing|awarding) (?:agency|organi[sz]ation))", re.I,
)
_BOUND_TO_THIS_RE = re.compile(
    r"\b(?:announc|invit|solicit|seek)\w*"
    r"|\bthis\s+(?:[\w&-]+\s+){0,3}(?:program|programme|solicitation|opportunity|announcement|agreement"
    r"|award|grant|initiative|competition|funding|rfa|rfp|nofo|foa)\b"
    r"|\b(?:made|entered into)\b[^.]{0,80}?\bby\b"
    r"|\bsponsor(?:ed|s)?\b|\bfunded by\b",
    re.I,
)


def party_unbound(st: Statement, sentence: str) -> bool:
    """Whether a sponsor or funder is sourced to a sentence that does not
    tie the organization to this opportunity (it announces, invites or
    funds it; this agreement is made by it)."""
    return bool(_PARTY_LABEL_RE.search(field_label(st))) and not _BOUND_TO_THIS_RE.search(sentence)


def _letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", (text or "").lower())


def negation_differs(st: Statement, sentence: str) -> bool:
    """Whether a statement about one kind of party is sourced to a sentence
    about its negation only — "Ph.D.-granting" and "Non-Ph.D.-granting
    institutions", "U.S." and "non-U.S. institutions", "profit" and
    "non-profit organizations". The kind is the list item or table row the
    statement sits under, or the statement itself. Seen in the MRI
    solicitation: "Accredited colleges and universities", a criterion of
    Ph.D.-granting institutions, was linked to "Non-Ph.D.-granting
    institutions of higher education are accredited colleges and
    universities…"; a separate check said yes, twice."""
    have = _letters(sentence)
    row = st.label.split(" — ")[0] if " — " in (st.label or "") else ""
    for subject in (st.context[-1] if st.context else "", row, st.text):
        kind = _letters(" ".join(re.findall(r"[A-Za-z][\w.'-]*", subject)[:3]))
        if len(kind) < 6 or kind.startswith("non"):
            continue
        if "non" + kind in have and have.replace("non" + kind, "").find(kind) == -1:
            return True
    return False


# The stages of a submission, each with its own deadline and rules.
_STAGES = (
    ("loi", re.compile(r"\b(?i:letters? of intent)\b|\bLOIs?\b")),
    ("preliminary", re.compile(r"\bpre-?proposals?\b|\bpreliminary proposals?\b|\bpre-?applications?\b"
                               r"|\bconcept (?:papers?|notes?)\b", re.I)),
    ("full", re.compile(r"\bfull (?:proposals?|applications?)\b", re.I)),
)


def _stages(text: str) -> set[str]:
    return {name for name, rx in _STAGES if rx.search(text or "")}


def stage_differs(st: Statement, excerpt: str) -> bool:
    """Whether a statement about one stage of a submission (the letter of
    intent, a preliminary or the full proposal) is sourced to an excerpt
    about another only. Seen in the NSF NHERI run: the full proposal
    deadline's "Due by 5 p.m. proposer's local time" linked to "Letter of
    Intent Due Date(s) (required) (due by 5 p.m. proposer's local time):
    October 16, 2015"; a separate check said yes, twice."""
    mine = _stages(st.text) or _stages(" ".join([field_label(st), *st.context[-1:]]))
    theirs = _stages(excerpt)
    return bool(mine and theirs) and not (mine & theirs)


# A part of a program the report scopes a row to, in brackets: "By end of
# sixth month of award (EF)", "(Rapid Facility)". An acronym of the words
# before it is the row's own name — "Collaborators & Other Affiliations
# (COA)" — not a scope.
_SCOPE_RE = re.compile(r"([^()]*)\(([A-Z][A-Za-z0-9&/ -]{0,40})\)")


# Words a scope shares with every part of a program: "(Rapid Facility)" is
# told from "(EF)" by "Rapid".
_SCOPE_COMMON = frozenset(stem(w) for w in (
    "facility", "facilities", "deadline", "deadlines", "date", "dates", "award", "awards", "program",
    "proposal", "proposals", "component", "center", "office", "track", "phase", "round", "cycle",
))


def _scopes(label: str) -> list[set[str]]:
    """The parts of a program a label's brackets name: an acronym ("EF")
    or a name in capitals ("Rapid Facility") — not a description
    ("September recurring") nor the label's own abbreviation ("PUIs")."""
    out = []
    for m in _SCOPE_RE.finditer(label or ""):
        inner = m.group(2).strip()
        acronym = re.fullmatch(r"([A-Z&]{2,8})s?", inner)
        if acronym:
            before = re.findall(r"[A-Za-z]+", m.group(1))
            initials = ("".join(w[0] for w in before), "".join(w[0] for w in before if w[0].isupper()))
            if any(i.upper().endswith(acronym.group(1).replace("&", "")) for i in initials if i):
                continue
            out.append({acronym.group(1)})
            continue
        if not all(w[0].isupper() for w in re.findall(r"[A-Za-z]+", inner)):
            continue
        words = stems(inner) - _GENERIC_LABEL_WORDS - _SCOPE_COMMON
        if words:
            out.append(words)
    return out


def _around(text: str, start: int, end: int) -> str:
    """The excerpt with its sentence and the one before it."""
    first = _sentence_start(text, start)
    lo = _sentence_start(text, first - 1) if first > 0 else 0
    stop = [i for i in (text.find(". ", end), text.find("\n", end)) if i != -1]
    return text[lo:min(stop) + 1 if stop else len(text)]


# Words that only place a statement in time: "by end of sixth month of
# award" says when, not which component's milestone.
_TIME_WORDS = frozenset(stem(w) for w in (
    "end", "start", "beginning", "within", "month", "months", "year", "years", "week", "weeks", "day", "days",
    "award", "milestone", "milestones", "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
    "eighth", "ninth", "tenth", "eleventh", "twelfth", "date", "deadline", "due",
))


def row_missing(st: Statement, text: str, start: int, end: int) -> bool:
    """Whether a short cell of a table row ("PDF format" under "RUI Impact
    Statement — Special Requirements") is sourced to text that does not
    name most of its row — the excerpt, its sentence and the one before.
    The cell says nothing of what it belongs to; the row does. Seen in the
    NSF RUI solicitation: the RUI Impact Statement's "PDF format" was
    linked to the Certification of RUI/ROA Eligibility's "scanned and
    included as a searchable PDF file"; a separate check said yes, twice.
    Only a Markdown table's cell has a row then a column; a JSON leaf's
    label is its list, its item and its key ("dates and deadlines — item")."""
    parts = [p for p in field_label(st).split(" — ") if p.strip()]
    if st.path is not None or len(parts) < 2:
        return False
    row = stems(parts[-2]) - _GENERIC_LABEL_WORDS - stems(st.text)
    if len(row) < 2:
        return False
    return len(row & stems(_around(text, start, end))) < math.ceil(2 * len(row) / 3)


def scope_missing(st: Statement, text: str, start: int, end: int, places: int) -> bool:
    """Whether a row the report scopes to one part of a program ("By end of
    sixth month of award (EF)") is sourced to text that does not name that
    part — the excerpt, its sentence and the one before it — when nothing
    else ties the row to this place: its own words only say when, or the
    excerpt is written in ``places`` > 1 places. Seen in the NSF NHERI run:
    the RFA lists each component's milestones in the same words, and the
    EF's "by end of sixth month of award" was linked to "By end of sixth
    month of award, Scheduling process implemented with the NCO" — the
    RAPID Facility's."""
    # The row's label, or the statement itself ("By end of year one (NCO)").
    scopes = _scopes(field_label(st)) + _scopes(st.text)
    if not scopes:
        return False
    if places < 2 and len(stems(st.text) - _TIME_WORDS - _GENERIC_LABEL_WORDS) >= 3:
        return False
    near = _around(text, start, end)
    found_words = stems(near)
    found_caps = set(re.findall(r"\b[A-Z]{2,8}\b", near))
    return not all((s & found_caps) if all(w.isupper() for w in s) else (s <= found_words) for s in scopes)


# Abbreviations every funding announcement uses — agencies, roles, forms,
# time zones, section numbers — none of which names one part of a program.
_COMMON_ACRONYMS = frozenset("""
NSF NIH NASA DOE DOD DHS USDA NIFA NOAA EPA NIST NEH NEA HHS FDA ED US USA UK EU UN FFAR
PI PIS PD PDS PM AOR SPO OSP SRO GPG PAPPG FAQ CFR OMB UEI SAM DUNS EIN TIN FAR IRB IACUC
LOI LOIS NOFO FOA RFA RFP RFI FY ID CV PDF URL HTML XML API ET EST EDT PT PST PDT CT CST CDT MT MST MDT
AM GPS IT IP NA TBD IDC MTDC TDC TBA COI COA DMP DMSP NCE CFDA NAICS SF RR OK F&A R&R R&D S&T STEM
I II III IV V VI VII VIII IX X XI XII
""".split())


_ABBREV_RE = re.compile(r"\b([A-Z][A-Z&]{1,7})s?\b")


@functools.lru_cache(maxsize=16)
def _defined_abbreviations(text: str) -> frozenset:
    """The abbreviations a document defines in brackets: "Experimental
    Facilities (EF)", "Post-Disaster, Rapid Response Research (RAPID)
    Facility". Capitals it does not define ("NOTE", "RED FLAGS") name
    nothing."""
    return frozenset(m.group(1) for m in re.finditer(r"\(([A-Z][A-Z&]{1,7})s?\)", text))


def part_missing(st: Statement, text: str, start: int, end: int, places: list[tuple[int, int]]) -> bool:
    """Whether a statement that names one part of a program by the
    abbreviation the document defines ("RAPID Facility certification…",
    "… updated for EF") is sourced to text that names neither it nor the
    words it stands for — the excerpt, its sentence and the one before —
    while that text names another part, or another of the ``places`` the
    excerpt is written in names this one. Seen in the NSF NHERI run:
    "Milestone: RAPID Facility certification of operational resources and
    fee schedule" was linked to the EF Awardee's certification, which a
    separate check confirmed; "… updated for EF" to the RAPID Facility's
    milestone, written in the same words as the EF's."""
    defined = _defined_abbreviations(text)
    named = {a for a in _ABBREV_RE.findall(st.text or "") if a in defined} - _COMMON_ACRONYMS
    if not named:
        return False
    near = _around(text, start, end)
    have = set(_ABBREV_RE.findall(near))
    # The words an abbreviation stands for: "Broadening Participation in
    # Computing" for BPC.
    initials = "".join(w[0] for w in re.findall(r"[A-Za-z][\w'-]*", near) if w[0].isupper())
    if all(a in have or a.replace("&", "") in initials for a in named):
        return False
    if (have & defined) - named - _COMMON_ACRONYMS:
        return True
    return any(
        named & set(_ABBREV_RE.findall(_around(text, a, b)))
        for a, b in places if not (a < end and start < b)
    )


# ---------------------------------------------------------------------------
# A part of a submission, named in the report's list of them
# ---------------------------------------------------------------------------

# A report list of what a submission is made of: "APPLICATION COMPONENTS",
# "Subaward Documents (if applicable)", "required components — name",
# "mandated structure — mandated sections — name" — or of who may take
# part: "Eligible Individuals" over "Principal Investigator", which was
# linked to "An individual may appear as Principal Investigator (PI) or
# co-PI in no more than one full proposal".
_PARTS_RE = re.compile(
    r"\b(?:components?|documents?|documentation|attachments?|forms|appendix|appendices|supplementary|sections"
    r"|(?:required|mandated) (?:sections?|items?|materials?|structure)|proposal (?:sections?|parts?|contents?)"
    r"|eligible (?:institutions?|individuals?|organi[sz]ations?|applicants?|entities)|who may (?:submit|serve))\b",
    re.I,
)
# Label words that only say what kind of list a name is in. "Subaward",
# in "Subaward Documents", says whose; the passage must be about that too.
_PART_WORDS = frozenset(stem(w) for w in (
    "component", "components", "document", "documents", "documentation", "attachment", "attachments",
    "form", "forms", "appendix", "appendices", "supplementary", "section", "sections", "structure",
    "mandated", "material", "materials", "part", "parts", "content", "contents", "proposal", "application",
    "submission", "eligible", "eligibility", "institution", "institutions", "individual", "individuals",
    "organization", "organizations", "organisation", "organisations", "applicant", "applicants", "entity",
    "entities", "submit", "serve",
))
# What a name may end with that is no part of it.
_ITEM_QUALIFIER_RE = re.compile(
    r"\s*(?:\((?:if|as|when) (?:applicable|required|needed|requested)\)"
    r"|\b(?:if|as|when) (?:applicable|required|needed|requested)|\((?:optional|required)\))\W*$",
    re.I,
)
# Words that make a statement say something, not just name a thing.
_SAYS_RE = re.compile(
    r"\b(?:must|shall|should|will|cannot|can|is|are|was|were|be|been|includ\w*|provid\w*|submit\w*"
    r"|describ\w*|requir\w*|attach\w*|upload\w*|contain\w*)\b|\bmay\b(?!\s*\d)",
    re.I,
)
# Two words of one name sit in one phrase, not across a list or a sentence.
_ITEM_BREAK_RE = re.compile(r"[;:|\n.]")
# A list mark at the start of a line: "-", "o" (Docling's hollow bullet),
# "2.", "a.", "(iii)".
_LINE_MARK_RE = re.compile(
    r"^\s*(?:(?:[-–—*+•·o]|\d{1,3}[.)]|[a-z][.)]|[ivx]{1,4}[.)]|\([a-z0-9]{1,4}\)"
    r"|\((?:required|optional|if applicable)\))\s+)*",
    re.I,
)
# What puts a name in a list: a list mark or separator before it — Docling
# writes sub-bullets inline as " o " ("… o Budget Form o P.I. and Key
# Personnel Biosketch: …"); "/" joins alternatives ("Program
# Director(s)/Principal Investigator(s)") …
_LIST_BEFORE_RE = re.compile(
    r"(?:[:;,|(\[/•·▪◦\"“‘']|[,;]\s*(?:and|or)|(?:^|\s)(?:\d{1,3}|[a-z]|[ivx]{1,4})[.)]|(?:^|\s)[o\-–—])\s*$",
    re.I,
)
# …and the end of the item after it.
_LIST_AFTER_RE = re.compile(
    r"\s*(?:$|[;,.:)|\]\"”’'(—–•·▪◦-]|(?:and|or|sections?|documents?|forms?)\b|o\s)", re.I,
)
# Initials and small words a name's own words do not count, and "a list
# of" before a list's name ("1. (required) A list of Project Personnel and
# Partner Institutions").
_NAME_FILLER_RE = re.compile(
    r"(?:\b(?:[A-Z]\.){1,4}\s*|\b(?:and|of|the|a|an|list)\s+|&\s*|\b(?:co|sub)[-‐‑])+$", re.I,
)
# An abbreviation in brackets.
_ACRONYM_RE = re.compile(r"\s*\([A-Z&]{2,8}s?\)")
# A bullet Docling writes inside a line: "… o Graphics, Figures, Equations,
# and Tables not included in the Project Description: …".
_INLINE_BULLET_RE = re.compile(r"(?:^|\s)[o•·▪◦]\s+$")
# A heading set off in bold or italics: "**2. Budget and Budget Justification.**".
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1")
# The end of a sentence just before a name ("…sections. Data Management
# Plan…"); "p.m." and "e.g." are not one.
_SENTENCE_END_RE = re.compile(r"(?<![.\s][a-z])(?<!\b[A-Z])[.!?:]\s+$")
# One or two capitalised words that open a longer name ("Postdoctoral").
_NAME_LEAD_RE = re.compile(r"(?:\b[A-Z][A-Za-z'’-]*\s+){1,2}$")
# A name asked for: "must include a budget", "Proposers should prepare annual budgets".
_ASKED_BEFORE_RE = re.compile(
    r"\b(?:includ(?:e|es|ed|ing)|submi(?:t|ts|tted|tting|ssion of)|provid(?:e|es|ed|ing)|attach(?:es|ed|ing)?"
    r"|upload(?:s|ed|ing)?|prepar(?:e|es|ed|ing)|contain(?:s|ed|ing)?|requir(?:e|es|ed|ing))\s+"
    r"(?:(?:a|an|the|one|two|three|separate|single|brief|short|detailed|complete|signed|annual|current"
    r"|[a-z]+-page)\s+){0,2}$",
    re.I,
)
# "A Data Management Plan (DMP) is required", "… must be submitted",
# "Universities and colleges are eligible".
_ASKED_AFTER_RE = re.compile(
    r"\W{0,3}\s*(?:\([^)]{0,60}\)\s*)?(?:is|are|must|shall|should|will)\s+(?:also\s+)?(?:be\s+)?"
    r"(?:required|included|submitted|provided|attached|uploaded|prepared|eligible)\b",
    re.I,
)


def item_name(st: Statement) -> list[str]:
    """The words of a statement that only names a part of a submission in
    the report's list of them ("Data Management Plan" among the required
    components, "Budget Justification" among a subaward's documents), or
    [] for any other statement."""
    if values_in(st.text) or not _PARTS_RE.search(" ".join([field_label(st), *st.context])):
        return []
    # Its abbreviation is no part of how a passage writes it: "Transition to
    # Education (TTE) Plan" is labelled "Transition to Education Plan".
    name = _ACRONYM_RE.sub(" ", _ITEM_QUALIFIER_RE.sub(" ", st.text))
    if _SAYS_RE.search(name):
        return []
    words = word_positions(name)
    if not 1 <= len(words) <= ITEM_MAX_WORDS or not all(name[a].isupper() for _, a, _ in words):
        return []
    return [s for s, _, _ in words]


def presented_as_item(name: list[str], text: str, start: int, end: int) -> bool:
    """Whether ``text[start:end]`` gives the name as a part of a submission:
    an item of a list ("…; Budget; Budget Justification; Current and
    Pending Support; …"), a heading or the subject at the start of a line,
    or the thing a sentence asks for ("must include a budget"). Seen in the
    NSF NHERI run: "Data Management Plan", a required component, was linked
    to "Implement a facility data management plan…", a facility's duty;
    "Budget Justification", a subaward's document, to "In the budget
    justification, provide a list of all organizations…". The lines
    around the excerpt are read, so an excerpt that only starts at the name
    does not make it a heading."""
    lo = text.rfind("\n", 0, start) + 1
    hi = text.find("\n", end)
    hi = len(text) if hi == -1 else hi
    raw = text[lo:hi]
    # Formatting marks and abbreviations ("Broadening Participation in
    # Computing (BPC) Plan") become spaces, so offsets stay put.
    line = _ACRONYM_RE.sub(lambda m: " " * len(m.group()), _MARKUP_RE.sub(lambda m: " " * len(m.group()), raw))
    words = word_positions(line)
    n = len(name)
    for i in range(len(words) - n + 1):
        if [s for s, _, _ in words[i:i + n]] != name:
            continue
        a, b = words[i][1], words[i + n - 1][2]
        if lo + a < start or lo + b > end:
            continue
        if any(_ITEM_BREAK_RE.search(line[words[j][2]:words[j + 1][1]]) for j in range(i, i + n - 1)):
            continue
        line_start = line.rfind("\n", 0, a) + 1
        line_end = line.find("\n", b)
        before, after = line[line_start:a], line[b:len(line) if line_end == -1 else line_end]
        # What may stand before the name inside the same item: a longer name
        # of the same part ("…; and Postdoctoral Mentoring Plan" lists the
        # "Mentoring Plan"; a verb is no part of a name), an article ("…; a
        # Certification of RUI/ROA Eligibility"), or initials the name's
        # words do not count ("P.I. and Key Personnel Biosketch").
        cores = [before]
        lead_in = _NAME_LEAD_RE.search(before)
        if lead_in and lead_in.group().split()[0].lower() not in _ACTION_VERBS:
            cores.append(before[:lead_in.start()])
        cores.append(_NAME_FILLER_RE.sub("", before))
        nxt = re.match(r"[ \t]+([a-z]+)\b", after)
        # "Data management plan costs are allowable": the name of something else.
        modifies = bool(nxt and nxt.group(1) not in _STOP and nxt.group(1) not in ("section", "sections")
                        and not re.search(r"(?:ed|ing)$", nxt.group(1)))

        def marked(pre: str) -> bool:
            # A list mark opens the item: "- …", "2. …", "o …" inside a line.
            mark = _LINE_MARK_RE.match(pre).end()
            return (bool(pre[:mark].strip()) and not pre[mark:].strip()) or bool(_INLINE_BULLET_RE.search(pre))

        def opens(pre: str) -> bool:
            return not pre.strip() or bool(_SENTENCE_END_RE.search(pre))

        # A list item, or a heading that opens a line or sentence and ends
        # where the name does ("Statements of Commitment. The proposal…",
        # "Goal and Context: Does the plan…"). The subject of a sentence is
        # not one: "Principal Investigator or organization that makes
        # financial … commitments … does so at their own risk".
        # A heading may run on a word or two: "Collaborators and Other
        # Affiliations Information:".
        heading_end = bool(re.match(r"\s*(?:[A-Z][\w'-]*\s*){0,2}(?:$|[:.\-—–(]|(?i:sections?)\b)", after))
        if not modifies and any(marked(pre) or (opens(pre) and heading_end) for pre in cores):
            return True
        if re.search(r"\beligible\s+$", before, re.I):
            return True   # "Eligible predominantly undergraduate institutions (PUIs) are …"
        if any(
            m.start(2) <= a and b <= m.end(2) and len(m.group(2)) <= 100 and not _CLAUSE_RE.search(m.group(2))
            for m in _EMPHASIS_RE.finditer(raw, line_start)
            if not _LINE_MARK_RE.sub("", raw[line_start:m.start()]).strip()
            or _SENTENCE_END_RE.search(raw[line_start:m.start()])
        ):
            # Inside a bold or italic heading that opens the line or a
            # sentence: Docling runs "…Documentation sections. **FACILITIES,
            # EQUIPMENT, AND OTHER RESOURCES** In this section…" on one line.
            # A whole sentence in bold is emphasis, not a heading.
            return True
        if _ASKED_BEFORE_RE.search(before) or _ASKED_AFTER_RE.match(after):
            return True
        if re.match(r"\W{0,3}\s*sections?\b", after, re.I):
            return True   # "In the Supplementary Documents Section, upload …"
        if any(_LIST_BEFORE_RE.search(pre) for pre in cores) and _LIST_AFTER_RE.match(after):
            return True
    return False


def obligation(text: str) -> tuple[bool, bool, bool]:
    """``(required, forbidden, optional)``: whether ``text`` says something
    must be done, must not be, or may be (or should be)."""
    t = text or ""
    optional = bool(_NOT_REQUIRED_RE.search(t))
    t = _NOT_REQUIRED_RE.sub(" ", t)
    forbidden = bool(_FORBIDDEN_RE.search(t))
    t = _FORBIDDEN_RE.sub(" ", t)
    required = bool(_REQUIRED_RE.search(t))
    optional = optional or bool(_PERMITTED_RE.search(t) or _ADVISED_RE.search(t))
    return required, forbidden, optional


def obligation_differs(statement: str, quote: str) -> bool:
    """Whether the excerpt asks less, or more, than the statement says: a
    statement that something must (or must not) be done, sourced to an
    excerpt that only says it may or should be, or the reverse. Only a
    statement and an excerpt that each speak one way are compared; an
    excerpt that says both, or states a limit, is left to the judge."""
    s_req, s_forbid, s_opt = obligation(statement)
    q_req, q_forbid, q_opt = obligation(quote)
    if _LIMIT_RE.search(quote) or _LIMIT_RE.search(statement):
        return False
    s_strong, q_strong = s_req or s_forbid, q_req or q_forbid
    if s_strong and not s_opt:
        return q_opt and not q_strong
    if s_opt and not s_strong:
        return q_req and not q_opt and not q_forbid
    return False


# Which way a limit points: a floor ("at least 2 pages") or a ceiling ("up to
# two pages").
_FLOOR_RE = re.compile(
    r"≥|>=|\bat\s+least\b|\bminimum\b|\bmin\.|\bno\s+(?:less|fewer)\s+than\b|\bnot\s+(?:less|fewer)\s+than\b"
    r"|\bor\s+(?:more|greater|longer)\b",
    re.I,
)
_CEILING_RE = re.compile(
    r"≤|<=|\bup\s+to\b|\bmaximum\b|\bmax\.|\bat\s+most\b|\bno\s+(?:more|greater|longer)\s+than\b"
    r"|\bnot\s+(?:to\s+)?exceed(?:ing)?\b|\bmust\s+not\s+exceed\b|\bor\s+(?:less|fewer|shorter)\b",
    re.I,
)


def limit_direction_differs(statement: str, quote: str) -> bool:
    """Whether the statement turns the excerpt's limit around: "(≥1 page)"
    sourced to "(all proposals, up to one page)", or a cap read as a floor.
    A model rewriting "≤" in a deliverable wrote "≥" for every section page
    limit of an NSF solicitation, and the words and figures still matched.
    Only a statement and an excerpt that each point one way are compared."""
    s_floor, s_ceiling = bool(_FLOOR_RE.search(statement)), bool(_CEILING_RE.search(statement))
    q_floor, q_ceiling = bool(_FLOOR_RE.search(quote)), bool(_CEILING_RE.search(quote))
    return (s_floor and not s_ceiling and q_ceiling and not q_floor) or (
        s_ceiling and not s_floor and q_floor and not q_ceiling
    )


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
        label_words = stems(field_label(st)) - words
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
    # A figure the excerpt writes in words ("more than one PI", "$5
    # million") has no digits to compare; its value already matched.
    worded = {q.key for q in quote_values if q.kind == "num" and not q.literal_check}
    for v in st_values:
        if v.key not in keys:
            return False
        if v.literal_check and v.key not in worded:
            ok, _ = value_supported_by_quote(v.raw.strip(), quote)
            if ok is not True:
                return False
    return True


def _breaks(text: str) -> int:
    """Line breaks in ``text``, a blank line counting as none: Docling writes
    "**… (CFDA) Number(s):**", a blank line, then "47.041" — the next line."""
    return re.sub(r"\n[ \t]*(?=\n)", "", text).count("\n")


# Between the two ends of one range: "January 16, 2023 - February 21, 2023".
_RANGE_SEP_RE = re.compile(r"[ \t]*(?:-{1,2}|[–—]|to|through|thru|until)[ \t]*", re.I)


def _range_partner(text: str, a: Value, b: Value) -> bool:
    """Whether two values of one kind are the two ends of a range."""
    x, y = (a, b) if a.start < b.start else (b, a)
    return x.kind == y.kind and bool(_RANGE_SEP_RE.fullmatch(text[x.end:y.start]))


# A heading over a list of values: it ends in ":" and names a plural
# ("Submission Window Date(s) (due by 5 p.m. submitter's local time):").
_LIST_HEAD_RE = re.compile(r"(?:\(s\)|\b[A-Za-z]*[a-hj-rt-z]s\b)[^:\n]{0,80}:\s*$")


def _listed_under(text: str, head_at: int, q: Value, values: list[Value]) -> bool:
    """Whether value ``q`` is in a list of values of its kind headed by the
    words at ``head_at``: a heading that names a plural and ends in ":",
    followed by nothing but values of that kind up to ``q``. Seen in the MRI
    solicitation: "Submission Window Date(s) (due by 5 p.m. submitter's
    local time): January 16, 2023 - February 21, 2023 October 16, 2023 -
    November 15, 2023 …" — the second window's start has the first window's
    dates before it."""
    line_end = text.find("\n", head_at)
    colon = text.find(":", head_at, len(text) if line_end == -1 else line_end)
    if colon == -1 or colon >= q.start or q.start - colon > BIND_LIST_MAX_CHARS:
        return False
    head = _MARKUP_RE.sub("", text[text.rfind("\n", 0, head_at) + 1:colon + 1]).strip()
    if not _LIST_HEAD_RE.search(head):
        return False
    rest = list(_MARKUP_RE.sub(lambda m: " " * len(m.group()), text[colon + 1:q.start]))
    for o in values:
        if o.kind == q.kind and o.start > colon and o.end <= q.start:
            rest[o.start - colon - 1:o.end - colon - 1] = " " * (o.end - o.start)
    return not word_positions("".join(rest))


def _bound(st_values: list[Value], shared: set[str], quote: str, quote_values: list[Value]) -> bool:
    """Each value in the statement sits beside a word it shares with the
    excerpt: on the same line or the one before, close by, with no other
    figure of the same kind between them that the statement does not name
    (the other end of a range is not another figure). A value may also sit
    in a list its label heads (``_listed_under``), or beside another value
    the statement names that does sit by the label — "47.041 ---
    Engineering", "47.049 --- Mathematical and Physical Sciences", … under
    "CFDA Number(s):"."""
    st_keys = {v.key for v in st_values}
    words = [(a, b) for s, a, b in word_positions(quote) if s in shared]
    if not words:
        return False

    def spots(v: Value) -> list[Value]:
        return [q for q in quote_values if q.key == v.key or v.key in _quote_keys([q])]

    def beside(a: int, b: int, q: Value) -> bool:
        if b <= q.start:
            lo, hi = b, q.start
        elif q.end <= a:
            lo, hi = q.end, a
        else:
            return True   # the word is part of the value's own text
        between = quote[lo:hi]
        if len(between) > BIND_MAX_CHARS or _breaks(between) > 1:
            return False
        return not any(
            o.kind == q.kind and o.start >= lo and o.end <= hi
            and o.key not in st_keys and not (_quote_keys([o]) & st_keys)
            and not _range_partner(quote, o, q)
            for o in quote_values
        )

    placed: dict[int, list[Value]] = {}
    for i, v in enumerate(st_values):
        found = [
            q for q in spots(v)
            if any(beside(a, b, q) or (b <= q.start and _listed_under(quote, a, q, quote_values)) for a, b in words)
        ]
        if found:
            placed[i] = found
    grew = True
    while grew and len(placed) < len(st_values):
        grew = False
        for i, v in enumerate(st_values):
            if i in placed:
                continue
            found = [q for q in spots(v) if any(beside(p.start, p.end, q) for ps in placed.values() for p in ps)]
            if found:
                placed[i] = found
                grew = True
    return len(placed) == len(st_values)


@dataclass
class Verdict:
    link: dict | None
    reason: str
    # (source, start, end) of the excerpt checked, when it was found: a
    # second look after a refusal goes past it.
    where: tuple[int, int, int] | None = None


def field_label(st: Statement) -> str:
    """What a statement is, for the checks that read its label: its own
    label, or for a statement with none, the heading or list item it sits
    directly under ("Eligible Individuals" over "Co‑Principal
    Investigator")."""
    return st.label or (st.context[-1] if st.context else "")


# An ellipsis at either end of an excerpt only says the passage goes on;
# one inside it skips words, and is refused by the verbatim check.
_EDGE_ELLIPSIS_RE = re.compile(r"^\s*(?:\.{3}|…)\s*|\s*(?:\.{3}|…)\s*$")


def clean_quote(quote: str) -> str:
    return _EDGE_ELLIPSIS_RE.sub("", (quote or "").strip()).strip()


_INNER_ELLIPSIS_RE = re.compile(r"\s*(?:\.{3}|…)\s*")


def _find_pieces(src: _Source, quote: str, start: int, end: int) -> tuple[tuple[int, int], list] | None:
    """Where an excerpt the judge cut with ellipses sits: every piece word
    for word, in order, inside ``src.text[start:end]``, the first piece to
    the last no longer than ``PIECED_MAX_CHARS``. Returns ``(span, pieces)``.
    Seen in the NSF NHERI run: "Each Awardee will operate with a Science
    Plan that supports the NHERI vision ... The Science Plan should outline:
    …" — what the deliverable condensed runs over several sentences."""
    parts = [p for p in _INNER_ELLIPSIS_RE.split(quote) if p.strip()]
    if len(parts) < 2 or any(len(fold(p)[0].split()) < PIECE_MIN_WORDS for p in parts):
        return None
    at, found = start, []
    for p in parts:
        hits = _find_all(src, p, at, end)
        if not hits:
            return None
        found.append(hits[0])
        at = hits[0][1]
    span = (found[0][0], found[-1][1])
    if span[1] - span[0] > PIECED_MAX_CHARS:
        return None
    return span, found


def _label_above(text: str, start: int, lo: int, words: set[str]) -> int | None:
    """Where the label line over an excerpt of bare values begins, when the
    judge copied the figures but not the line they sit under ("47.041 ---
    Engineering" under "**Applicable Catalog of Federal Domestic Assistance
    (CFDA) Number(s):**"; the third submission window under "Submission
    Window Date(s) …:"): the nearest line above with words, past lines of
    values only, inside the passage the judge read — and only when it has a
    word of the statement or its label."""
    line_start = text.rfind("\n", 0, start) + 1
    if line_start < lo or _MARKUP_RE.sub("", text[line_start:start]).strip():
        return None   # the excerpt does not open its line
    pos = line_start
    for _ in range(LABEL_ABOVE_LINES):
        if pos - 1 <= lo:
            return None
        above = text.rfind("\n", 0, pos - 1) + 1
        if above < lo:
            return None
        line = text[above:pos - 1]
        rest = list(line)
        for v in values_in(line):
            rest[v.start:v.end] = " " * (v.end - v.start)
        found = stems("".join(rest))
        if found & words:
            return above
        if found:
            return None   # a line of other words: no label over these values
        pos = above
    return None


def verify(st: Statement, corpus: Corpus, wi: int, quote: str) -> Verdict:
    """Whether the judge's ``quote`` from window ``wi`` may source ``st``;
    when it may, the source entry the UI shows."""
    quote = clean_quote(quote)
    if len(quote) > MAX_QUOTE_CHARS:
        return Verdict(None, "quote_too_long")
    nq, _ = fold(quote)
    if len(nq) < MIN_QUOTE_CHARS or len(nq.split()) < 2:
        return Verdict(None, "quote_too_short")
    w = corpus.windows[wi]
    src = corpus.sources[w.src]
    spots = _find_all(src, quote, w.start, w.end)
    # An excerpt cut with "…" is checked piece by piece, and shown whole.
    pieces: list[tuple[int, int]] = []
    if not spots:
        found = _find_pieces(src, quote, w.start, w.end)
        if found is not None:
            spots, pieces = [found[0]], found[1]
    if not spots:
        # A passage is a window cut from the text, and a sentence can run
        # past its edge: "Two-page biographical sketches, following the NSF
        # GPG format, for up to ten additional project personnel" — the
        # window ended at "project". Mostly inside it, the rest word for word.
        lo, hi = max(0, w.start - EDGE_CHARS), min(len(src.text), w.end + EDGE_CHARS)
        spots = [(a, b) for a, b in _find_all(src, quote, lo, hi) if 2 * (min(b, w.end) - max(a, w.start)) >= b - a]
        if not spots:
            found = _find_pieces(src, quote, lo, hi)
            if found is not None and 2 * (min(found[0][1], w.end) - max(found[0][0], w.start)) >= found[0][1] - found[0][0]:
                spots, pieces = [found[0]], found[1]
    if not spots:
        return Verdict(None, "quote_not_in_passage")
    start, end = spots[0]

    st_values = values_in(st.text)
    text_words = stems(st.text)
    words = text_words | stems(st.label)

    def cited_text() -> str:
        return " ".join(src.text[a:b] for a, b in pieces) if pieces else src.text[start:end]

    cited = cited_text()
    # Bare figures the judge copied without the label line they sit under:
    # a value statement ("47.041", "2024-10-15") whose label says what it is.
    if (
        st_values and len(text_words) <= 2 and not (words & stems(cited))
        and _values_supported(st_values, cited, values_in(cited))
    ):
        top = _label_above(src.text, start, w.start, words)
        if top is not None:
            start = top
            spots = [(start, end)]
            if pieces:
                pieces[0] = (start, pieces[0][1])
            cited = cited_text()
    exact = src.text[start:end]
    where = (w.src, start, end)

    q_values = values_in(cited)
    if not _values_supported(st_values, cited, q_values):
        return Verdict(None, "value_not_in_quote", where)
    quote_words = stems(cited)
    shared = words & quote_words
    if not shared:
        return Verdict(None, "no_shared_word", where)
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
        # "two" in the statement is the excerpt's "2".
        keys = _quote_keys(q_values)
        covered = (text_words & quote_words) | {
            s for s in text_words if s in _NUMBER_STEMS and f"num:{_NUMBER_STEMS[s]}" in keys
        }
        if len(covered) / len(text_words) < need_text and len(shared) / len(words) < need_all:
            return Verdict(None, "quote_covers_too_little", where)
    # A one- or two-word statement ("USD", "Travel") says little on its own;
    # its label says what it is about ("Expense Record — currency",
    # "approved budget categories"). The passage the judge read must be
    # about that too, or "ALL AMOUNTS ARE SHOWN IN USD" on the award would
    # source the expense's currency. A part of a submission is checked
    # for how the excerpt gives it instead (``presented_as_item``); its list
    # ("required components") need not be named, but whose list it is
    # ("Subaward Documents") must be.
    passage = corpus.window_text(wi)
    label_only = stems(field_label(st)) - text_words - _GENERIC_LABEL_WORDS
    name = item_name(st)
    if name:
        owner = label_only - _PART_WORDS
        if owner and not (owner & stems(passage)):
            return Verdict(None, "label_not_in_passage", where)
        if not any(presented_as_item(name, src.text, a, b) for a, b in (pieces or [(start, end)])):
            return Verdict(None, "not_an_item", where)
    elif (
        len(text_words) <= 2 and label_only and not (label_only & stems(passage))
        and not _named_otherwise(label_only, passage)
    ) or (len(text_words) <= 3 and row_missing(st, src.text, start, end)):
        return Verdict(None, "label_not_in_passage", where)
    # A statement the report copied word for word from a source came from
    # where those words are. "A facility with any resources that can only be
    # accessed or used outside the United States" is in the RAPID list on
    # p. 21; the judge linked "A facility with any equipment that…" from
    # another component's list on p. 28.
    if len(text_words) >= VERBATIM_MIN_WORDS:
        copies = [
            (si, a, b) for si, s in enumerate(corpus.sources) for a, b in _find_all(s, st.text, 0, len(s.text))
        ]
        if copies and not any(si == w.src and a < end and start < b for si, a, b in copies):
            return Verdict(None, "statement_is_elsewhere", where)
    # Every word of "subawards over $50,000 must include this clause" is in
    # "The recipient may include the substance of this clause … in subawards
    # … over $50,000", and the judge said so. "Must" is not "may" or
    # "should"; only the statement's own words count, not its label's. The
    # sentence is read too: "Full proposal must be received by FastLane no
    # later than 4:59 p.m." was linked to the clause "…to receive a FastLane
    # submittal stamped time no later than … 4:59 pm" of a sentence that
    # says proposers are "strongly encouraged" to. An excerpt in pieces is
    # read both as cut and whole.
    sentence = sentence_around(src.text, start, end)
    if (
        obligation_differs(st.text, cited) or obligation_differs(st.text, sentence)
        or (pieces and obligation_differs(st.text, exact))
    ):
        return Verdict(None, "obligation_differs", where)
    if limit_direction_differs(st.text, cited) or limit_direction_differs(st.text, sentence):
        return Verdict(None, "limit_differs", where)
    # Advice for this case ("Obtain vendor quotations…") sourced to a rule
    # that applies only in some cases ("If simplified acquisition procedures
    # are used, price or rate quotations must be obtained…") says the case
    # needs it; the report has not shown the condition holds, and here it
    # did not (a $1,240 purchase is under the micro-purchase threshold). The
    # judge quotes the main clause, so the whole sentence is read.
    if is_action(st) and not _CONDITION_RE.search(st.text) and _CONDITION_RE.search(sentence):
        return Verdict(None, "rule_applies_only_if", where)
    # Likewise a requirement the statement states outright: "Mandatory
    # BLM‑approved safety and training courses" was linked to "Recipient
    # staff will be required to complete a BLM-approved … safety and training
    # program if using Government-furnished ATVs". Only the excerpt is read:
    # a case elsewhere in its sentence may belong to another clause ("…will
    # not accept the proposal if a required section is missing"), so it is
    # left to the separate confirmation (``narrows``). Another passage may
    # state the requirement without the case. "Requirement to complete DOI
    # Federal Information Systems Security Awareness training" shares only
    # "Federal" and "system" with "Before the recipient … are granted access
    # to the BLM Federal computer system": words a BLM award uses throughout.
    if condition_dropped(st, cited, common_words(src.text)):
        return Verdict(None, "condition_dropped", where)
    if st_values and not _bound(st_values, shared, exact, values_in(exact)):
        return Verdict(None, "value_not_bound_to_label", where)
    if subject_differs(st, sentence) or negation_differs(st, sentence):
        return Verdict(None, "subject_differs", where)
    if party_unbound(st, sentence):
        return Verdict(None, "party_not_bound", where)
    if stage_differs(st, cited):
        return Verdict(None, "stage_differs", where)
    places = _find_all(src, exact, 0, len(src.text)) if not pieces else [(start, end)]
    if part_missing(st, src.text, start, end, places) or scope_missing(st, src.text, start, end, len(places)):
        return Verdict(None, "scope_missing", where)

    if src.kind == "document":
        pages = set()
        approx = False
        # A cut excerpt must start and end on one page, like a whole one.
        for a in [a for a, _ in spots] + ([end - 1] if pieces else []):
            marker = page_marker_for_offset(a, src.markers or [])
            pages.add(marker.get("value") if marker else None)
            approx = approx or bool(marker and marker.get("approximate"))
        if len(pages) > 1:
            return Verdict(None, "quote_on_several_pages", where)
        first = page_marker_for_offset(start, src.markers or [])
        shown = widen_to_statement(
            src.text, start, end, w.start, w.end, text_words,
            same_page=lambda a: page_marker_for_offset(a, src.markers or []) == first,
        )
        link = _document_link(src, *shown, pages.pop(), approx)
    else:
        if len(spots) > 1 and len({_kb_page(src, a) for a, _ in spots}) > 1:
            return Verdict(None, "quote_on_several_pages", where)
        page = _kb_page(src, start)
        if pieces and _kb_page(src, end - 1) != page:
            return Verdict(None, "quote_on_several_pages", where)
        shown = widen_to_statement(
            src.text, start, end, w.start, w.end, text_words, same_page=lambda a: _kb_page(src, a) == page,
        )
        link = _kb_link(src, *shown)
    link["judge_quote"] = cited
    if pieces:
        # The judge skipped words: a separate call must confirm the whole.
        link["pieced"] = True
    return Verdict(link, "ok", where)


def widen_to_statement(
    text: str, start: int, end: int, lo: int, hi: int, words: set[str], same_page: Callable[[int], bool],
) -> tuple[int, int]:
    """``[start, end)`` grown, inside ``[lo, hi)`` and on its page, by the
    sentences next to it that hold words of the statement the excerpt does
    not: the highlight then covers what the statement rests on. Seen in the
    MRI solicitation: "Data management plan incremental costs" highlighted
    "…share with other researchers, at no more than incremental cost…",
    while the next sentence says "MRI budgets may include incremental costs
    associated with the implementation of this plan". Shown only — every
    check has already passed on the judge's excerpt."""
    if not words:
        return start, end
    for _ in range(3):
        have = stems(text[start:end]) & words
        if len(have) / len(words) >= CONFIRM_BELOW:
            break
        best, gain = None, 0
        # The rest of the excerpt's sentence and the one after it.
        a = end
        stops = [i for i in (text.find(". ", a), text.find("\n", a)) if i != -1 and i < hi]
        b = min(stops) + 1 if stops else hi
        if b > a and b - start <= MAX_QUOTE_CHARS:
            g = len((stems(text[a:b]) & words) - have)
            if g > gain:
                best, gain = (start, b), g
        # The start of its sentence and the one before it. On a tie, the
        # label an excerpt sits under ("Limit on Number of Proposals per
        # Organization:" over "There are no restrictions or limits.") wins
        # over the next field's.
        b = start
        a = _sentence_start(text, max(lo, b - 1), lo)
        if b > a and end - a <= MAX_QUOTE_CHARS and same_page(a):
            g = len((stems(text[a:b]) & words) - have)
            label = _MARKUP_RE.sub("", text[a:b]).rstrip().endswith(":")
            if g > gain or (g == gain and g > 0 and label):
                best, gain = (a, end), g
        if best is None:
            break
        start, end = best
    # Never end on the space or line break a sentence was cut at.
    while end > start and text[end - 1] in " \t\r\n":
        end -= 1
    while start < end and text[start] in " \t\r\n":
        start += 1
    return start, end


def verify_offered(st: Statement, corpus: Corpus, wi: int, offered: list[int], quote: str) -> Verdict:
    """``verify`` against the passage the judge named, or — when the excerpt
    is not in it but is, word for word, in exactly one place among the
    other passages the statement was offered — against that one. The judge
    read every offered passage and sometimes names the wrong id; the
    excerpt is still checked in full where it is."""
    v = verify(st, corpus, wi, quote)
    if v.reason != "quote_not_in_passage":
        return v
    q = clean_quote(quote)
    places: dict[tuple[int, int], int] = {}
    for other in offered:
        if other == wi:
            continue
        w = corpus.windows[other]
        src = corpus.sources[w.src]
        hits = _find_all(src, q, w.start, w.end)
        if not hits:
            pieced = _find_pieces(src, q, w.start, w.end)
            hits = [pieced[0]] if pieced else []
        for a, _ in hits:
            places.setdefault((w.src, a), other)
    if len(places) != 1:
        return v
    return verify(st, corpus, next(iter(places.values())), quote)


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
        item = {"id": n, "label": st.label}
        if st.context:
            item["context"] = " — ".join(st.context)
        item.update({"statement": st.text, "passages": [ids[wi] for wi in cands]})
        parts.append(json.dumps(item, ensure_ascii=False))
    return "\n\n".join(parts), {v: k for k, v in ids.items()}


def _escape_raw_controls(text: str) -> str:
    """``text`` with the line breaks and tabs that sit inside JSON strings
    escaped. Models copying a passage that runs over lines often write the
    break itself into the quote — invalid JSON, and a whole batch lost."""
    out: list[str] = []
    inside = escaped = False
    for ch in text:
        if inside and not escaped and ch in "\n\r\t":
            out.append({"\n": "\\n", "\r": "\\r", "\t": "\\t"}[ch])
            continue
        if ch == '"' and not escaped:
            inside = not inside
        escaped = ch == "\\" and not escaped
        out.append(ch)
    return "".join(out)


def _parse(reply: str) -> dict[int, dict]:
    from app.services.workflow_validator import _extract_json

    try:
        data = _extract_json(reply)
    except ValueError:
        data = _extract_json(_escape_raw_controls(reply))
    items = data.get("items") if isinstance(data, dict) else data
    out: dict[int, dict] = {}
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and isinstance(it.get("id"), int) and not isinstance(it.get("id"), bool):
            out[it["id"]] = it
    return out


def _judge_batch(
    batch: list[tuple[str, Statement, list[int]]], corpus: Corpus, ask: Callable[[str, str], str],
    instructions: str = JUDGE_INSTRUCTIONS,
) -> dict[str, Verdict]:
    items = [(n, st, cands) for n, (_, st, cands) in enumerate(batch, 1)]
    prompt, by_id = _judge_prompt(items, corpus)
    verdicts = _parse(ask(instructions, prompt))
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
            out[key] = verify_offered(st, corpus, wi, cands, q if isinstance(q, str) else "")
        except Exception as e:  # noqa: BLE001 — a check that cannot run links nothing
            logger.warning("Source check failed for one statement: %s", e)
            out[key] = Verdict(None, "check_error")
    return out


def _batches(jobs: list[tuple[str, Statement, list[int]]], corpus: Corpus, ordered: bool = False) -> list[list]:
    """Judge calls of up to ``BATCH_STATEMENTS`` statements and
    ``BATCH_CHARS`` of passages: grouped by where their passages are, so a
    call reads each once, or — ``ordered`` — in the order given, so the top
    of a report is checked first."""
    if not ordered:
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


def says_more(st: Statement, link: dict | None) -> bool:
    """Whether a statement of several words has much the excerpt does not:
    then a separate call must confirm the excerpt states all of it. Seen in
    the NSF run: "Include the required single-copy PDFs (List of
    Participating Organizations and List of Project Personnel) and adhere to
    file-format and naming rules of the chosen system", linked to an excerpt
    that says nothing of formats or names."""
    words = stems(st.text)
    if len(words) < COVERAGE_MIN_WORDS:
        return False
    quote = (link or {}).get("judge_quote") or (link or {}).get("quote") or ""
    return len(words & stems(quote)) / len(words) < CONFIRM_BELOW


def label_names_role(st: Statement) -> bool:
    """Whether a statement of a few words takes what it is from its label,
    in words it does not have itself ("sponsor" over a name, "due date"
    over a date): then the passage must give it that role, not just its
    words. A longer statement says what it means itself; its label is only
    where it sits ("Consistent Cost Treatment — rationale"). So does a
    sentence: "Proposals may be submitted via Research.gov or Grants.gov"
    under "SUBMISSION DETAILS" is not a submission detail by its label."""
    words = stems(st.text)
    if len(words) >= 3 and _CLAUSE_RE.search(st.text):
        return False
    return len(words) <= ROLE_MAX_WORDS and bool(stems(field_label(st)) - words - _GENERIC_LABEL_WORDS)


# A verb that makes a statement a sentence ("May 11" is a date).
_CLAUSE_RE = re.compile(r"\b(?:must|shall|should|will|cannot|can|is|are|was|were|be|been)\b|\bmay\b(?!\s*\d)", re.I)


def _role_prompt(items: list[tuple[int, Statement, dict]]) -> str:
    parts = ["STATEMENTS"]
    for n, st, link in items:
        item = {"id": n, "label": field_label(st), "statement": st.text}
        if st.context:
            item["context"] = " — ".join(st.context)
        item.update({
            "source": link.get("document_title") or link.get("label") or "",
            "excerpt": link.get("quote"), "passage": link.get("excerpt"),
        })
        parts.append(json.dumps(item, ensure_ascii=False))
    return "\n\n".join(parts)


def _role_vote(
    batch: list[tuple[str, Statement, Verdict]], vote: int, ask: Callable[[str, str], str],
) -> dict[tuple[str, int], bool]:
    """One reading of a batch: whether each statement's passage gives it
    the role its label names. Later votes read the batch in reverse, so no
    two see the same order."""
    items = batch if vote % 2 == 0 else batch[::-1]
    answers = _parse(ask(ROLE_INSTRUCTIONS, _role_prompt([(n, st, v.link) for n, (_, st, v) in enumerate(items, 1)])))
    return {(key, vote): (answers.get(n) or {}).get("shown") is True for n, (key, _, _) in enumerate(items, 1)}


def _reordered(batch: list, vote: int) -> list:
    """The batch as reading ``vote`` sees it: reversed, then turned halfway,
    so no two readings put a link beside the same ones in the same place."""
    if vote % 2:
        return batch[::-1]
    half = len(batch) // 2
    return batch[half:] + batch[:half]


def _confirm_vote(
    batch: list[tuple[str, Statement, Verdict]], ask: Callable[[str, str], str],
) -> dict[str, bool]:
    """Whether each excerpt, read in its passage, states its statement:
    asked only of links a second look found."""
    answers = _parse(ask(CONFIRM_INSTRUCTIONS, _role_prompt([(n, st, v.link) for n, (_, st, v) in enumerate(batch, 1)])))
    return {key: (answers.get(n) or {}).get("stated") is True for n, (key, _, _) in enumerate(batch, 1)}


@dataclass
class _Job:
    rank: int                  # lower runs first
    seq: int
    run: Callable[[], object]
    done: Callable[[object], None]
    failed: Callable[[], None]


class _Scheduler:
    """Model calls on a few threads, at most ``workers`` at once, the
    lowest rank first, until ``deadline``. A finished job may queue more
    (a judged batch queues its role checks); ``tick`` runs between results,
    on the calling thread, as do every job's callbacks."""

    def __init__(self, workers: int, deadline: float | None, clock: Callable[[], float]) -> None:
        self.workers = max(1, workers)
        self.deadline = deadline
        self.clock = clock
        self.queue: list[_Job] = []
        self.seq = 0
        self.errors = 0

    def add(self, rank: int, run, done, failed) -> None:
        self.seq += 1
        self.queue.append(_Job(rank, self.seq, run, done, failed))

    def _late(self) -> bool:
        return self.deadline is not None and self.clock() >= self.deadline

    def run(self, tick: Callable[[], None] | None = None) -> list[_Job]:
        """Run everything queued, and everything it queues. Returns the
        jobs that never ran or never finished, out of time."""
        pool = ThreadPoolExecutor(max_workers=self.workers)
        flying: dict = {}
        try:
            while True:
                while self.queue and len(flying) < self.workers and not self._late():
                    self.queue.sort(key=lambda j: (j.rank, j.seq))
                    job = self.queue.pop(0)
                    flying[pool.submit(contextvars.copy_context().run, job.run)] = job
                if not flying:
                    # Nothing out: ``tick`` may start the next stage.
                    if tick and not self._late():
                        tick()
                        if self.queue:
                            continue
                    break
                remaining = None if self.deadline is None else max(0.0, self.deadline - self.clock())
                finished, _ = wait(flying, timeout=remaining, return_when=FIRST_COMPLETED)
                if not finished:
                    break   # out of time with calls still out
                for f in sorted(finished, key=lambda f: (flying[f].rank, flying[f].seq)):
                    job = flying.pop(f)
                    try:
                        result = f.result()
                    except Exception as e:  # noqa: BLE001 — a failed call links nothing
                        logger.warning("Source check call failed: %s", e)
                        self.errors += 1
                        job.failed()
                        continue
                    job.done(result)
                if tick:
                    tick()
        finally:
            for f in flying:
                f.cancel()
            pool.shutdown(wait=False, cancel_futures=True)
        left = list(flying.values()) + self.queue
        self.queue = []
        return left


# ---------------------------------------------------------------------------
# A run's sourcing
# ---------------------------------------------------------------------------

def statement_key(st: Statement) -> str:
    """Statements judged once: the same words under the same label and the
    same headings. "Criteria: Must be a full-time employee…" under the PI
    and under the co-PI are two statements."""
    return json.dumps(
        [st.text.strip().lower(), st.label.strip().lower(), [c.strip().lower() for c in st.context]],
        ensure_ascii=False,
    )


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
            self.sources.append({k: v for k, v in link.items() if k not in ("offset", "judge_quote", "pieced")})
        return self.index[key]


# A first look that ends in one of these may have missed a passage that
# states the statement, or copied it badly: it gets a second look. A link
# refused by a check on what the excerpt says (a value, a rule's condition,
# how strongly it asks) does not: the same excerpt would be found again.
RETRY_REASONS = frozenset({
    "judge_unsupported", "judge_named_no_passage", "quote_not_in_passage", "quote_too_short",
    "quote_too_long", "no_shared_word", "quote_covers_too_little", "value_not_in_quote",
    "check_error", "judge_call_failed",
})
# A link refused because the passage is about something else — a
# component's name in a facility's duty, a sponsor in the agency's account
# of itself, the PI's rule for a co-PI — may still be stated elsewhere: its
# second look is offered other passages, never the one refused.
RETRY_ELSEWHERE_REASONS = frozenset({
    "not_an_item", "label_not_in_passage", "party_not_bound", "subject_differs", "role_not_shown",
    "statement_is_elsewhere", "stage_differs", "scope_missing", "condition_dropped",
})
# What a second look that finds nothing ends in: then the first look's
# reason stands.
_NOTHING_FOUND = frozenset({"judge_unsupported", "judge_named_no_passage", "judge_call_failed"})


def trace_sources(
    targets: dict,
    documents: list[dict],
    passages: list[dict],
    *,
    ask: Callable[[str, str], str],
    deadline: float | None = None,
    workers: int = WORKERS,
    max_judged: int = MAX_JUDGED,
    max_retried: int = MAX_RETRIED,
    clock: Callable[[], float] = time.monotonic,
    first: set[str] | None = None,
    publish: Callable[[dict], None] | None = None,
) -> dict:
    """Source every statement of every output in ``targets`` (key → value).

    Returns the sidecar the UI draws from::

        {"version", "status": "done", "sources": [link, …],
         "targets": {key: {"format", "statements": [{"s", "e", "p"?, "src"?, "t"?, "w"?}],
                           "summary": {"statements", "traced"}}},
         "judged", "retried", "rescued", "unchecked", "errors", "reasons"}

    ``s``/``e`` are offsets into a text output (``format: text``) or into
    the leaf string at path ``p`` (``format: json``; absent for a whole
    number leaf). A text output that is JSON also gives each statement's
    path ``p`` and its offsets inside that leaf, ``ls``/``le``. Offsets
    count code points. ``src`` indexes ``sources``; ``t`` marks an
    ``absent`` or ``verdict`` statement. The outputs themselves are only read.

    The statements of the ``first`` targets (all of them when not given)
    are checked first, in the order they are written, so the top of a
    report is underlined first; then their second looks; then the other
    targets'. ``publish`` receives the sidecar so far, ``status:
    "running"``, as links are settled — ``w`` marks a statement still being
    checked — and a source's index never changes once given.
    """
    corpus = Corpus(documents, passages)
    first_keys = [k for k in targets if first is None or k in first]
    keys_in_order = first_keys + [k for k in targets if k not in first_keys]
    split: dict[str, tuple[str, list[Statement]]] = {}
    unique: dict[str, Statement] = {}
    lead: dict[str, int] = {}   # 0: in a first target, 1: not
    for key in keys_in_order:
        fmt, stmts = split_output(targets[key])
        split[key] = (fmt, stmts)
        for st in stmts:
            if st.kind == "claim":
                skey = statement_key(st)
                unique.setdefault(skey, st)
                lead[skey] = min(lead.get(skey, 1), 0 if key in first_keys else 1)

    settled: dict[str, Verdict] = {}
    open_keys: set[str] = set()        # still being checked: shown as waiting
    retry_due: dict[str, Statement] = {}
    awaiting: dict[str, str] = {}      # a link waiting on a check: what it becomes if cut off
    stats: Counter = Counter()
    sched = _Scheduler(workers, deadline, clock)
    first_out: Counter = Counter()     # first-look judge calls not yet back, per class
    retried_class: set[int] = set()
    avoid: dict[str, list[tuple[int, int, int]]] = {}   # excerpts a second look must go past
    run = _Run()

    def settle(skey: str, verdict: Verdict, *, may_retry: bool) -> None:
        if verdict.link is None and verdict.reason in _NOTHING_FOUND and skey in avoid:
            verdict = settled.get(skey, verdict)   # a second look found nothing else
        settled[skey] = verdict
        awaiting.pop(skey, None)
        elsewhere = verdict.reason in RETRY_ELSEWHERE_REASONS and verdict.where is not None
        if may_retry and verdict.link is None and (verdict.reason in RETRY_REASONS or elsewhere):
            if elsewhere:
                avoid.setdefault(skey, []).append(verdict.where)
            retry_due[skey] = unique[skey]
        else:
            retry_due.pop(skey, None)
            open_keys.discard(skey)

    def checks(items: list[tuple[str, Statement, Verdict]], *, retry: bool) -> None:
        """Queue the separate calls a link still needs — a confirmation for
        one a second look found, whose statement says more than its
        excerpt's words or whose excerpt may say less (``narrows``), role
        checks for a short statement — and settle each when they are back.

        A link confirmed only because its excerpt may say less is asked
        ``NARROWING_VOTES`` times, in different orders, and refused on a
        majority: that check reaches about a third of all links, and one
        reading of a borderline link flips with the links it is batched with
        (of 740 stored links, one reading refused 20, three readings 48
        between them, a majority 18 — 13 of them wrong links, 3 right ones).
        A confirmation for any other reason stays a single reading that must
        say yes."""
        needs: dict[str, tuple[int, bool]] = {}   # confirmations to read, role check
        waiting = []
        for skey, st, v in items:
            if retry or says_more(st, v.link) or (v.link or {}).get("pieced"):
                confirm = 1
            else:
                confirm = NARROWING_VOTES if narrows(st, v.link) else 0
            role = label_names_role(st)
            if confirm or role:
                needs[skey] = (confirm, role)
                waiting.append((skey, st, v))
            else:
                settle(skey, v, may_retry=False)
        for i in range(0, len(waiting), ROLE_BATCH):
            chunk = waiting[i:i + ROLE_BATCH]
            to_confirm = [it for it in chunk if needs[it[0]][0]]
            again = [it for it in to_confirm if needs[it[0]][0] > 1]
            roles = [it for it in chunk if needs[it[0]][1]]
            answers: dict = {"confirm": [None] * NARROWING_VOTES, "roles": [None] * ROLE_VOTES}
            jobs: list[tuple] = []
            if to_confirm:
                jobs.append(("confirm", 0, lambda c=to_confirm: _confirm_vote(c, ask)))
            if again:
                jobs.extend(
                    ("confirm", n, (lambda c=again, n=n: _confirm_vote(_reordered(c, n), ask)))
                    for n in range(1, NARROWING_VOTES)
                )
            if roles:
                jobs.extend(("role", n, (lambda r=roles, n=n: _role_vote(r, n, ask))) for n in range(ROLE_VOTES))
            for skey, _, _ in chunk:
                awaiting[skey] = "confirm_unchecked" if needs[skey][0] else "role_unchecked"
            left = {"n": len(jobs)}

            def decide(chunk=chunk, answers=answers) -> None:
                for skey, _, v in chunk:
                    confirm, role = needs[skey]
                    if confirm:
                        said = [(answers["confirm"][n] or {}).get(skey) for n in range(confirm)]
                        if said.count(False) * 2 > confirm:
                            settle(skey, Verdict(None, "not_confirmed"), may_retry=False)
                            continue
                        if said.count(True) * 2 <= confirm:
                            stats["unchecked"] += 1
                            settle(skey, Verdict(None, "confirm_unchecked"), may_retry=False)
                            continue
                    if role:
                        votes = [(r or {}).get((skey, n)) for n, r in enumerate(answers["roles"])]
                        if False in votes:
                            settle(skey, Verdict(None, "role_not_shown", v.where), may_retry=not retry)
                            continue
                        if None in votes:
                            stats["unchecked"] += 1
                            settle(skey, Verdict(None, "role_unchecked"), may_retry=False)
                            continue
                    if retry:
                        stats["rescued"] += 1
                    settle(skey, v, may_retry=False)

            for kind, n, call in jobs:
                def done(result, kind=kind, n=n, answers=answers, left=left, decide=decide) -> None:
                    if kind == "confirm":
                        answers["confirm"][n] = result
                    else:
                        answers["roles"][n] = result
                    left["n"] -= 1
                    if left["n"] == 0:
                        decide()

                def failed(left=left, decide=decide) -> None:
                    left["n"] -= 1
                    if left["n"] == 0:
                        decide()

                sched.add(0, call, done, failed)

    def look(batch: list, cls: int, *, retry: bool) -> None:
        """A judge call on ``batch``: a first look, or a second one with more
        passages and a reminder to copy exactly."""
        instructions = JUDGE_INSTRUCTIONS + RETRY_NOTE if retry else JUDGE_INSTRUCTIONS
        if not retry:
            first_out[cls] += 1

        def done(result: dict) -> None:
            if not retry:
                first_out[cls] -= 1
            linked = []
            for skey, st, _ in batch:
                v = result.get(skey) or Verdict(None, "judge_unsupported")
                if v.link is not None:
                    linked.append((skey, st, v))
                else:
                    settle(skey, v, may_retry=not retry)
            checks(linked, retry=retry)

        def failed() -> None:
            if not retry:
                first_out[cls] -= 1
            for skey, _, _ in batch:
                settle(skey, Verdict(None, "judge_call_failed"), may_retry=not retry)

        sched.add(1 + 2 * cls + (1 if retry else 0),
                  lambda: _judge_batch(batch, corpus, ask, instructions), done, failed)

    # First looks: the first targets' statements in the order written, then
    # the rest; past the budget a statement stays plain.
    jobs: dict[int, list] = {0: [], 1: []}
    budget = max_judged
    for skey, st in unique.items():
        cands = corpus.candidates(st)
        if not cands:
            continue
        if budget <= 0:
            stats["unchecked"] += 1
            continue
        budget -= 1
        stats["judged"] += 1
        open_keys.add(skey)
        jobs[lead[skey]].append((skey, st, cands))
    for batch in _batches(jobs[0], corpus, ordered=True):
        look(batch, 0, retry=False)

    retry_left = {"n": max_retried}
    rest_started = {"yes": False}

    def past(wi: int, refused: list[tuple[int, int, int]]) -> bool:
        w = corpus.windows[wi]
        return not any(si == w.src and a < w.end and w.start < b for si, a, b in refused)

    def queue_retries(cls: int) -> None:
        retried_class.add(cls)
        todo = []
        for skey, st in [(k, s) for k, s in retry_due.items() if lead[k] == cls]:
            retry_due.pop(skey, None)
            cands = []
            if retry_left["n"] > 0:
                refused = avoid.get(skey, [])
                cands = [wi for wi in corpus.candidates(st, k=RETRY_CANDIDATES + 2 * len(refused)) if past(wi, refused)]
                cands = cands[:RETRY_CANDIDATES]
            if not cands:
                open_keys.discard(skey)
                continue
            retry_left["n"] -= 1
            stats["retried"] += 1
            todo.append((skey, st, cands))
        for batch in _batches(todo, corpus, ordered=True):
            look(batch, cls, retry=True)

    def advance() -> None:
        """The next stage, when the one before it is done: the first
        targets' second looks once all their first looks and the checks on
        what they found are back (a refused link may earn one); the other
        targets only once every first-target statement is settled, so they
        never slow the deliverable on a shared model server; then theirs."""
        if 0 not in retried_class and first_out[0] == 0 and not any(lead[k] == 0 for k in awaiting):
            queue_retries(0)
        if not rest_started["yes"] and not any(lead[k] == 0 for k in open_keys):
            rest_started["yes"] = True
            for batch in _batches(jobs[1], corpus):
                look(batch, 1, retry=False)
        if (
            rest_started["yes"] and 1 not in retried_class and first_out[1] == 0
            and not any(lead[k] == 1 for k in awaiting)
        ):
            queue_retries(1)

    def build(status: str) -> dict:
        out_targets: dict[str, dict] = {}
        for key in targets:
            fmt, stmts = split[key]
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
                    skey = statement_key(st)
                    v = settled.get(skey)
                    if skey in open_keys:
                        row["w"] = 1
                    elif v is not None and v.link is not None:
                        row["src"] = run.add(v.link)
                        traced += 1
                rows.append(row)
            out_targets[key] = {
                "format": fmt, "statements": rows,
                "summary": {"statements": len(rows), "traced": traced},
            }
        return {
            "version": VERSION,
            "status": status,
            "sources": list(run.sources),
            "targets": out_targets,
            "judged": stats["judged"],
            "retried": stats["retried"],
            "rescued": stats["rescued"],
            "unchecked": stats["unchecked"],
            "errors": sched.errors,
            "reasons": dict(Counter(v.reason for v in settled.values())),
        }

    shown = {"at": 0.0, "open": -1}

    def tick() -> None:
        advance()
        if publish is None:
            return
        now = time.monotonic()
        if len(open_keys) != shown["open"] and now - shown["at"] >= PUBLISH_EVERY:
            shown["at"], shown["open"] = now, len(open_keys)
            try:
                publish(build("running"))
            except Exception as e:  # noqa: BLE001 — a missed update only delays the underlines
                logger.warning("Could not publish partial sourcing: %s", e)

    advance()
    sched.run(tick)
    # Whatever a deadline cut off stays plain, and is counted.
    for skey in list(open_keys):
        stats["unchecked"] += 1
        if skey in awaiting:
            settled[skey] = Verdict(None, awaiting[skey])
        elif skey not in settled:
            settled[skey] = Verdict(None, "unchecked")
    open_keys.clear()
    return build("done")
