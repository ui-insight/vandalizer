"""Point an attached-document answer's page references at the pages that hold
what they cite, and give an uncited claim its page.

``derive_document_citations`` already checks every "p. N" an answer writes
against page N (``citation_grounding``) and shows a chip only when the page
holds the claim. The answer text kept the model's number regardless, and the
2026-11-02 attached-document eval put the cost of that at one cited claim in
ten pointing at the wrong page, almost always a page the document *does* state
the claim on — the model cites the page marker nearest the text it read, so
text at the foot of p. 5 is cited as p. 6 — and two claims in five carrying no
page at all.

This runs after the answer is final (the document check may have rewritten
it) and before the chips are derived, with the same lexical test the chips
use (anchors — figures, dates, quoted phrases — must all be on the page; a
claim without anchors needs 60% of its content words there):

* a reference whose page fails the test is **re-pointed** to a page of the
  same document that passes it: the cited page's neighbours first (the
  off-by-one case), else the page with the most of the claim on it, and only
  when one page wins outright;
* a sentence that cites no page and states something checkable is given the
  page that holds it, when exactly one page passes the test clearly;
* a reference that no page supports is left as it is: the chip already says
  "not found", and the lexical test fails a faithful paraphrase often enough
  that dropping the number would lose right pages too.

Nothing is changed in a document whose page boundaries were interpolated
(scanned copies): there a page number is an estimate either way. Behind
``chat_config.doc_page_citation_repair_enabled`` (default off), with
``doc_page_citation_attach_enabled`` (default on with it) for the second part.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Optional

from app.services import citation_grounding as cg
from app.services.kb_answer_grounding import _money_values, _percent_values

VERSION = 2
KIND = "page_citations"
MAX_ATTACH = 20
# A claim without anchors is attached to a page only when that page holds this
# much more of it than the runner-up: a sentence 60% on three pages is
# boilerplate, not a citation.
ATTACH_MARGIN = 0.15
MIN_ATTACH_STEMS = 4
# A page an answer did not cite is offered only when it also holds this share
# of the claim's words: a figure alone ("50%") is on too many pages to say
# where a claim came from. The page the answer did cite is judged as the
# chips judge it, anchors alone, so a reference the chips call found stays.
CANDIDATE_MIN_OVERLAP = 0.3

_HEADING_RE = re.compile(r"^\s*(#{1,6}\s|\*\*[^*]{1,80}\*\*\s*:?\s*$|[A-Z][^.!?]{0,60}:\s*$)")
_LEAD_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|>\s*)+")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")
_SKIP_START_RE = re.compile(
    r"^\s*(?:\*\*)?(?:note|notes|source|sources|see|summary|in short|in summary|in other words|bottom line|"
    r"overall|therefore|thus|so|hence|answer|short answer|tl;dr|yes|no|conclusion|conclusions|result|results|"
    r"recommendation|recommendations|takeaway|takeaways|this means|that means|implication|implications)\b",
    re.IGNORECASE,
)
# Any mention of a page, including the forms the chips' pattern does not read
# ("pages 1-2"): such a sentence has its citation, however it is written.
_ANY_PAGE_RE = re.compile(r"\b(?:p|pp|pg|page|pages)\.?\s*~?\s*\d{1,4}\b", re.IGNORECASE)
_NEGATIVE_RE = re.compile(
    r"\b(?:not|never|no|nothing|neither|nor|cannot|can't|unable|without)\b[^.]{0,60}?"
    r"\b(?:state|states|stated|specif\w*|mention\w*|provide[sd]?|includ\w*|say|says|said|list|lists|listed|"
    r"address\w*|give[sn]?|defin\w*|found|find|locat\w*|appear\w*|identif\w*|indicat\w*|show[sn]?|contain\w*|"
    r"cover\w*|discuss\w*|describ\w*|set[s]?\b|explain\w*)"
    r"|\b(?:silent|absent|unstated|unspecified|unclear|missing)\b"
    r"|\bno (?:mention|reference|information|detail|details|indication|explicit)\b",
    re.IGNORECASE,
)
_MARKUP_RE = re.compile(r"[*_`#>|]+")
# gpt-oss writes "50 %" and "$ 16,500" with a (narrow no-break) space; the
# anchor patterns read "50 %" as the bare number 50, which a page's "50%" then
# fails to supply. Closed up before anchors are read, on both sides.
_SPACED_PERCENT_RE = re.compile(r"(\d)[\s   ]+%")
_SPACED_MONEY_RE = re.compile(r"\$[\s   ]+(\d)")


def _prep(text: str) -> str:
    return _SPACED_MONEY_RE.sub(r"$\1", _SPACED_PERCENT_RE.sub(r"\1%", text))


@dataclass
class PageIndex:
    """One page of a document, with the features the lexical test reads,
    computed once so a whole answer can be checked against every page."""

    doc_uuid: str
    title: str
    page: int
    text: str
    norm: str = ""
    money: set = field(default_factory=set)
    percent: set = field(default_factory=set)
    dates: set = field(default_factory=set)
    numbers: set = field(default_factory=set)
    stems: set = field(default_factory=set)

    def __post_init__(self):
        text = _prep(self.text)
        self.norm = cg._norm(text)
        self.money = set(_money_values(text))
        self.percent = set(_percent_values(text))
        self.dates = cg._dates(text)
        self.numbers = cg._numbers(text)
        self.stems = cg._content_stems(text)


@dataclass
class Claim:
    text: str
    money: set
    percent: set
    dates: set
    numbers: set
    quotes: list
    stems: set

    @property
    def anchors(self) -> int:
        return len(self.money) + len(self.percent) + len(self.dates) + len(self.numbers) + len(self.quotes)


def _claim(text: str) -> Claim:
    text = _prep(text)
    return Claim(
        text=text,
        money=set(_money_values(text)),
        percent=set(_percent_values(text)),
        dates=cg._dates(text),
        numbers=cg._numbers(text),
        quotes=[cg._norm(m.group(1)) for m in cg._QUOTE_RE.finditer(text)],
        stems=cg._content_stems(text),
    )


def _score(claim: Claim, page: PageIndex, *, floor: float = 0.0) -> Optional[tuple[int, float]]:
    """``(anchors found, share of content words on the page)`` when the page
    passes ``citation_grounding``'s test for the claim, else None. The test:
    every anchor on the page; with no anchors, 60% of the content words. With
    *floor*, an anchored claim also needs that share of its words there."""
    missing = 0
    missing += sum(1 for v in claim.money if v not in page.money)
    missing += sum(1 for v in claim.percent if v not in page.percent)
    missing += sum(1 for v in claim.dates if v not in page.dates)
    missing += sum(1 for v in claim.numbers if v not in page.numbers)
    missing += sum(1 for q in claim.quotes if q not in page.norm)
    if missing:
        return None
    overlap = len(claim.stems & page.stems) / len(claim.stems) if claim.stems else 0.0
    if claim.anchors:
        if claim.stems and overlap < floor:
            return None
        return claim.anchors, overlap
    if len(claim.stems) < cg._MIN_CONTENT_WORDS or overlap < cg._MIN_OVERLAP:
        return None
    return 0, overlap


def index_documents(documents: list) -> dict[str, tuple[object, list[PageIndex]]]:
    """``{uuid: (document, pages)}`` for every attached document with measured
    page markers. Interpolated (scanned) boundaries are left out: a page
    number there is an estimate, and the chips hedge it already."""
    from app.services.chat_service import _page_positions

    out: dict[str, tuple[object, list[PageIndex]]] = {}
    for doc in documents or []:
        raw = getattr(doc, "raw_text", None) or ""
        positions = _page_positions(getattr(doc, "text_markers", None), len(raw))
        if not positions or any(approx for _off, _page, approx in positions):
            continue
        pages = []
        for i, (offset, page, _approx) in enumerate(positions):
            end = positions[i + 1][0] if i + 1 < len(positions) else len(raw)
            text = raw[offset:end]
            if text.strip():
                pages.append(PageIndex(doc.uuid, getattr(doc, "title", "") or "", page, text))
        if pages:
            out[doc.uuid] = (doc, pages)
    return out


def repair_config(sys_config_doc: Optional[dict]) -> Optional[dict]:
    """The settings in ``chat_config``, or None when the step is off."""
    cfg = (sys_config_doc or {}).get("chat_config") or {}
    if not bool(cfg.get("doc_page_citation_repair_enabled", False)):
        return None
    return {"attach": bool(cfg.get("doc_page_citation_attach_enabled", True))}


def _best_page(claim: Claim, pages: list[PageIndex], *, near: Optional[int] = None,
               margin: float = 0.0) -> Optional[PageIndex]:
    """The page that holds *claim* when one wins outright.

    With *near* (the page the answer cited), a passing neighbour of it wins
    first: the off-by-one miss. Otherwise the best score, and only when no
    other page ties it; with *margin*, an anchorless claim must also beat the
    runner-up's word share by that much."""
    scored = [(s, p) for p in pages if (s := _score(claim, p, floor=CANDIDATE_MIN_OVERLAP)) is not None]
    if not scored:
        return None
    if near is not None:
        neighbours = [(s, p) for s, p in scored if abs(p.page - near) == 1]
        if neighbours:
            neighbours.sort(key=lambda sp: (-sp[0][0], -sp[0][1], abs(sp[1].page - near)))
            best, runner = neighbours[0], neighbours[1] if len(neighbours) > 1 else None
            if runner is None or runner[0] != best[0]:
                return best[1]
            return None
    scored.sort(key=lambda sp: (-sp[0][0], -sp[0][1], abs(sp[1].page - near) if near is not None else 0))
    best = scored[0]
    if len(scored) > 1:
        runner = scored[1]
        if runner[0][0] == best[0][0] and (
            runner[0][1] == best[0][1] or (best[0][0] == 0 and best[0][1] - runner[0][1] < margin)
        ):
            return None
    return best[1]


def _alongside(answer: str, spans: list[tuple[int, int]]) -> set[int]:
    """Indexes of references written side by side with another ("(a, p. 2)
    (b, p. 3)"): they cite one claim together and are judged jointly by the
    chips, so they are left alone here."""
    out: set[int] = set()
    for i, ((_s0, e0), (s1, _e1)) in enumerate(zip(spans, spans[1:])):
        between = cg._FILE_NAME.sub(" ", answer[e0:s1])
        if not re.search(r"[A-Za-z0-9]{3,}", between):
            out.update((i, i + 1))
    return out


def repair_page_citations(answer: str, documents: list, *, attach: bool = True) -> tuple[str, dict]:
    """``(answer, record)``: the answer with its page references re-pointed
    and its uncited claims given pages, and what was done. The answer comes
    back unchanged when nothing applies; ``record["changed"]`` says."""
    from app.services.chat_service import _PAGE_REF_RE, _cited_document, _title_variants

    started = time.monotonic()
    record: dict = {"version": VERSION, "kind": KIND, "refs": 0, "checked": 0, "kept": 0, "repointed": [],
                    "unresolved": 0, "unattributed": 0, "attributed": [], "alongside": 0, "attached": [],
                    "considered": 0, "changed": False}

    def done(text: str) -> tuple[str, dict]:
        record["changed"] = text != answer
        record["seconds"] = round(time.monotonic() - started, 3)
        return text, record

    if not answer or not answer.strip():
        return done(answer)
    indexed = index_documents(documents)
    if not indexed:
        return done(answer)
    named = [(_title_variants(getattr(d, "title", "")), d) for d in documents]
    named = [(v, d) for v, d in named if v]
    only = next(iter(indexed.values()))[0] if len(indexed) == 1 else None

    # ---- references the answer wrote: re-point the ones their page fails
    matches = list(_PAGE_REF_RE.finditer(answer))
    record["refs"] = len(matches)
    spans = [m.span() for m in matches]
    joint = _alongside(answer, spans)
    edits: list[tuple[int, int, str]] = []
    for i, m in enumerate(matches):
        if i in joint:
            record["alongside"] += 1
            continue
        try:
            page = int(m.group(1))
        except ValueError:
            continue
        doc = _cited_document(answer, m.span(), named) or only
        claim_text = cg._claim_for_ref(answer, m.span(), _PAGE_REF_RE)
        if doc is None or doc.uuid not in indexed:
            # A bare "p. N" with several documents attached names none of
            # them, so the chips cannot check it and the reader cannot open
            # it. When exactly one attached document's page N holds the
            # claim, the reference is given that document's name, in the
            # form the chips read ("(award.pdf, p. 3)").
            if doc is None and len(indexed) > 1 and claim_text and cg._has_substance(claim_text):
                claim = _claim(claim_text)
                holders = [p for _d, pages in indexed.values() for p in pages
                           if p.page == page and _score(claim, p, floor=CANDIDATE_MIN_OVERLAP) is not None]
                if len(holders) == 1 and holders[0].title:
                    edits.append((m.start(), m.start(), f"{holders[0].title}, "))
                    record["attributed"].append({"page": page, "doc": holders[0].title})
                    continue
            record["unattributed"] += 1
            continue
        if not claim_text or not cg._has_substance(claim_text):
            continue
        record["checked"] += 1
        claim = _claim(claim_text)
        _doc, pages = indexed[doc.uuid]
        current = next((p for p in pages if p.page == page), None)
        if current is not None and _score(claim, current) is not None:
            record["kept"] += 1
            continue
        best = _best_page(claim, [p for p in pages if p.page != page], near=page)
        if best is None:
            record["unresolved"] += 1
            continue
        digits = m.group(1)
        start = m.start() + m.group(0).rfind(digits)
        edits.append((start, start + len(digits), str(best.page)))
        record["repointed"].append({"from": page, "to": best.page, "doc": best.title})
    text = answer
    for start, end, repl in sorted(edits, reverse=True):
        text = text[:start] + repl + text[end:]

    if not attach:
        return done(text)

    # ---- sentences that cite nothing: give the checkable ones their page
    all_pages = [p for _d, pages in indexed.values() for p in pages]
    multi = len(indexed) > 1 or len(documents or []) > 1
    inserts: list[tuple[int, str]] = []
    in_fence = False
    for start, end in cg._sentences(text, _PAGE_REF_RE):
        seg = text[start:end]
        if seg.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or _PAGE_REF_RE.search(seg) or _ANY_PAGE_RE.search(seg):
            continue
        body = seg.strip()
        if not body or _TABLE_SEP_RE.match(body) or _HEADING_RE.match(body) or "?" in body:
            continue
        plain = _MARKUP_RE.sub(" ", _LEAD_RE.sub("", body))
        plain = cg._without_file_names(plain)
        if _SKIP_START_RE.match(plain) or _NEGATIVE_RE.search(plain):
            continue
        claim = _claim(plain)
        if not claim.anchors and len(claim.stems) < MIN_ATTACH_STEMS:
            continue
        record["considered"] += 1
        best = _best_page(claim, all_pages, margin=ATTACH_MARGIN)
        if best is None:
            continue
        label = f"({best.title}, p. {best.page})" if multi else f"(p. {best.page})"
        inserts.append((_insertion_point(text, start, end), " " + label))
        record["attached"].append({"page": best.page, "doc": best.title, "sentence": " ".join(plain.split())[:120]})
        if len(inserts) >= MAX_ATTACH:
            break
    for at, label in sorted(inserts, reverse=True):
        text = text[:at] + label + text[at:]
    return done(text)


def _insertion_point(text: str, start: int, end: int) -> int:
    """Where "(p. N)" goes in the sentence at ``text[start:end]``: before the
    closing punctuation, or inside a table row's last cell."""
    seg = text[start:end]
    tail = len(seg) - len(seg.rstrip())
    at = end - tail
    core = seg[:len(seg) - tail]
    if core.endswith("|"):
        # a table row: inside the last cell
        at -= 1
        while at > start and text[at - 1] == " ":
            at -= 1
        return at
    while at > start and text[at - 1] in ".!;:,":
        at -= 1
    return at
