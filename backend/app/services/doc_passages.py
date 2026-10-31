"""Passages inside a chat's attached documents, and the pages chat already holds.

An attached document goes with the question whole when it fits and is cut to
fit when it does not (context_budget). The 2026-10-29 eval found what that cost
on long solicitations: the answer page sat in the cut middle on 4 of 5
single-FOA items, and the agent had no way to reach it. Its only search,
``search_documents``, matches workspace file titles, so in-document phrases
found nothing, and it then guessed page ranges with ``get_document_text`` (up
to 26 calls on one turn) until a re-read overflowed the model's window.

Everything here is plain keyword ranking (BM25 with a bonus for query words
that appear side by side) over pages and page windows. No index and no model
call, so it runs inside the turn:

- the planner ranks a cut document's pages against the question and keeps the
  best of them inline (``context_budget``);
- ``search_attached_documents`` ranks windows of every page, cut or not;
- ``DocumentContext`` records which pages the model already holds, inline or
  from an earlier read this turn, so no tool sends them twice.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

# The page boundary chat writes into document text (chat_service.annotate_pages).
PAGE_MARK_RE = re.compile(r"\[p\. (~?)(\d{1,5})\]\n")

_WORD_RE = re.compile(r"[a-z0-9]+(?:[.\-/&][a-z0-9]+)*")
_PART_RE = re.compile(r"[.\-/&]")
_DOTTED_NUMBER_RE = re.compile(r"\d+(?:\.\d+)+")

# Function words, and the question words people put around what they want
# ("what's the most we could request for…"). A word in every page scores near
# zero anyway; these would only add noise to the side-by-side bonus.
_STOP = frozenset("""
a an the of to in on for and or by with from at as is are be been being was were it its this that these those
which who whom whose what when where why how can could may might must shall should will would do does did doing
done not no nor any all each our we us you your they them their there here than then so if into about over under
between per via vs versus also only just such other both either neither more most much many some very s t
i me my mine he she his her hers let lets ll re ve d m
tell show find give get got say says said please want need know think like looking look
""".split())


def _stem(word: str) -> str:
    """Plural and -ing/-ed endings off, the same light stemming KB search uses."""
    if len(word) <= 3 or word.isdigit():
        return word
    for suffix, repl in (("ies", "y"), ("sses", "ss"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            if suffix == "s" and word.endswith(("ss", "us", "is")):
                return word
            return word[: -len(suffix)] + repl
    return word


def terms(text: str) -> list[str]:
    """Search terms of ``text``, in order.

    Section numbers stay whole ("3.4" is not "3" and "4", which every page
    holds). Other joined words keep the whole and add their parts, so
    "MS-NE-3" matches both "ms-ne-3" and a page that writes "MS NE 3".
    """
    out: list[str] = []
    for word in _WORD_RE.findall((text or "").lower()):
        if _PART_RE.search(word) is None:
            if word not in _STOP and (len(word) > 1 or word.isdigit()):
                out.append(_stem(word))
            continue
        out.append(word)
        if _DOTTED_NUMBER_RE.fullmatch(word):
            continue
        out.extend(
            _stem(p) for p in _PART_RE.split(word)
            if p and p not in _STOP and (len(p) > 1 or p.isdigit())
        )
    return out


@dataclass
class Ranked:
    index: int
    score: float
    matched: int  # distinct query terms the unit holds
    of: int  # distinct query terms ranked on


class _Index:
    """BM25 over a list of texts, with a bonus for query terms side by side."""

    def __init__(self, texts: list[str], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [terms(t) for t in texts]
        self.counts = [Counter(d) for d in self.docs]
        self.pairs = [set(zip(d, d[1:])) for d in self.docs]
        self.n = len(self.docs)
        self.df: Counter = Counter()
        for c in self.counts:
            self.df.update(c.keys())
        self.avg = (sum(len(d) for d in self.docs) / self.n) if self.n else 0.0

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def rank(self, query: str) -> list[Ranked]:
        ordered = terms(query)
        q = list(dict.fromkeys(ordered))
        if not q or not self.n:
            return []
        # A word on most pages ("announcement", "project") tells pages apart
        # no better than a stopword; leave it out unless the query has nothing
        # else, so a vague question picks no pages instead of arbitrary ones.
        if self.n >= 4:
            rare = [t for t in q if self.df.get(t, 0) <= self.n / 2]
            if rare:
                q = rare
        bigrams = [(a, c) for a, c in zip(ordered, ordered[1:]) if a != c]
        out: list[Ranked] = []
        for i, counts in enumerate(self.counts):
            score, matched = 0.0, 0
            norm_len = 1 - self.b + self.b * len(self.docs[i]) / (self.avg or 1.0)
            for t in q:
                tf = counts.get(t, 0)
                if not tf:
                    continue
                matched += 1
                score += self.idf(t) * tf * (self.k1 + 1) / (tf + self.k1 * norm_len)
            if not matched:
                continue
            for a, c in bigrams:
                if (a, c) in self.pairs[i]:
                    score += min(self.idf(a), self.idf(c))
            out.append(Ranked(i, score, matched, len(q)))
        out.sort(key=lambda r: (-r.score, r.index))
        return out


def rank_texts(query: str, texts: list[str]) -> list[Ranked]:
    """Every text that holds a query term, best first."""
    return _Index(texts).rank(query)


def query_terms(query: str) -> list[str]:
    return list(dict.fromkeys(terms(query)))


def strong_matches(ranked: list[Ranked], query: str, *, share: float = 0.5) -> list[Ranked]:
    """The units worth showing for a query: within ``share`` of the best score,
    and holding at least two of its terms when it has three or more. One
    word of a long question ("cost", "period") is not a match."""
    if not ranked:
        return []
    need = 2 if ranked[0].of >= 3 else 1
    best = ranked[0].score
    return [r for r in ranked if r.matched >= need and r.score >= share * best]


# ---------------------------------------------------------------------------
# Pages of annotated segment text (what the planner trims)
# ---------------------------------------------------------------------------


@dataclass
class TextPage:
    page: int
    start: int
    end: int
    approximate: bool


def annotated_pages(text: str) -> list[TextPage]:
    """The ``[p. N]`` pages of document text as chat sends it, in order."""
    marks = list(PAGE_MARK_RE.finditer(text or ""))
    pages: list[TextPage] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        pages.append(TextPage(int(m.group(2)), m.start(), end, bool(m.group(1))))
    return pages


def page_runs(pages: list[int]) -> list[tuple[int, int]]:
    """``[1, 2, 3, 7, 9, 10]`` → ``[(1, 3), (7, 7), (9, 10)]``."""
    runs: list[tuple[int, int]] = []
    for p in sorted(set(pages)):
        if runs and p == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], p)
        else:
            runs.append((p, p))
    return runs


def format_pages(pages: list[int]) -> str:
    """``[1, 2, 3, 7]`` → ``"1–3, 7"``."""
    return ", ".join(f"{a}–{b}" if a != b else str(a) for a, b in page_runs(pages))


# ---------------------------------------------------------------------------
# What the model already holds
# ---------------------------------------------------------------------------


@dataclass
class DocumentContext:
    """What of one document is already in the model's context this turn.

    ``whole``: the document went with the question in full. ``pages``: pages
    that are there in full, inline or returned by a read this turn.
    ``spans``: character ranges a search already returned.
    """

    whole: bool = False
    pages: set[int] = field(default_factory=set)
    spans: set[tuple[int, int]] = field(default_factory=set)

    def holds_page(self, page: Optional[int]) -> bool:
        return self.whole or (page is not None and page in self.pages)

    def holds_span(self, start: int, end: int) -> bool:
        if self.whole:
            return True
        return any(s <= start and end <= e for s, e in self.spans)


def context_after_compaction(original: str, sent: str, cut_markers: tuple[str, ...]) -> DocumentContext:
    """Which pages of a document segment went with the question.

    ``original`` is the segment as built, ``sent`` the one the planner
    returned. Unchanged means whole. Otherwise a page counts only when its
    text is all there: pages the planner kept by page are whole, while a cut
    that falls mid-page (``cut_markers``: the head/tail cut and the last-ditch
    trim) leaves the page before it partial, and the text after it starts
    inside a page whose marker is gone.
    """
    if sent == original:
        return DocumentContext(whole=True)
    if not sent:
        return DocumentContext()
    pattern = "|".join(re.escape(m) for m in cut_markers if m)
    cuts = [m.start() for m in re.finditer(pattern, sent)] if pattern else []
    held: set[int] = set()
    marks = list(PAGE_MARK_RE.finditer(sent))
    for i, m in enumerate(marks):
        nxt = marks[i + 1].start() if i + 1 < len(marks) else len(sent)
        if any(m.start() < c < nxt for c in cuts):
            continue  # cut inside this page
        held.add(int(m.group(2)))
    return DocumentContext(pages=held)


# ---------------------------------------------------------------------------
# Windows of a stored document (what search_attached_documents ranks)
# ---------------------------------------------------------------------------

WINDOW_CHARS = 1600
WINDOW_STEP = 800


@dataclass
class Window:
    start: int
    end: int
    page: Optional[int]
    approximate: bool = False
    page_start: int = 0
    page_end: int = 0


def _snap(raw: str, pos: int, lo: int, hi: int, forward: bool) -> int:
    """Move ``pos`` to a nearby line break or space, staying within [lo, hi]."""
    if pos <= lo or pos >= hi:
        return max(lo, min(pos, hi))
    span = raw[pos:min(hi, pos + 120)] if forward else raw[max(lo, pos - 120):pos]
    for sep in ("\n", " "):
        i = span.find(sep) if forward else span.rfind(sep)
        if i >= 0:
            return pos + i + 1 if forward else max(lo, pos - 120) + i + 1
    return pos


def document_windows(raw: str, positions: list[tuple[int, int, bool]]) -> list[Window]:
    """Overlapping windows of ``raw``, each inside one page where there are pages."""
    raw = raw or ""
    spans: list[tuple[int, int, Optional[int], bool]]
    if positions:
        spans = []
        for i, (offset, page, approx) in enumerate(positions):
            end = positions[i + 1][0] if i + 1 < len(positions) else len(raw)
            if i == 0 and offset > 0:
                spans.append((0, offset, None, False))
            spans.append((offset, end, page, approx))
    else:
        spans = [(0, len(raw), None, False)]
    out: list[Window] = []
    for lo, hi, page, approx in spans:
        if hi <= lo or not raw[lo:hi].strip():
            continue
        start = lo
        while True:
            end = min(hi, start + WINDOW_CHARS)
            if end < hi:
                end = _snap(raw, end, start + WINDOW_STEP, hi, forward=False)
            out.append(Window(start, end, page, approx, lo, hi))
            if end >= hi:
                break
            start = _snap(raw, start + WINDOW_STEP, lo, hi, forward=True)
    return out


def snippet_around(text: str, query: str, width: int = 220) -> str:
    """A short stretch of ``text`` around its rarest-looking query term."""
    flat = " ".join((text or "").split())
    if len(flat) <= width:
        return flat
    lower = flat.lower()
    hits = [
        (len(t), lower.find(t)) for t in query_terms(query)
        if len(t) > 2 and lower.find(t) >= 0
    ]
    at = max(hits)[1] if hits else 0
    start = max(0, at - width // 3)
    piece = flat[start:start + width]
    return ("…" if start else "") + piece + ("…" if start + width < len(flat) else "")
