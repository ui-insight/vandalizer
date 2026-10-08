"""Check a page the model cited against the text actually on that page (#998).

``derive_document_citations`` turns every "p. N" in an attached-document
answer into a citation chip. It only knew that page N existed, and the chip
previewed the first 400 characters of the page, so a made-up claim with a
real page number got a chip that looked exactly like a retrieved source.

This compares the sentence that carries the reference with the cited page:

* **Anchors** — dollar amounts, percentages, other numbers (digits, or
  "one" to "twelve"), month-day dates and quoted phrases — must all appear on
  the page. These are the parts of a claim an RA acts on, and the parts a
  model gets wrong while sounding right ("limited to 3 pages" when the notice
  sets no limit).
* With no anchors, at least 60% of the sentence's content words must appear
  on the page, compared by their first five letters so "required" matches
  "requires" and a paraphrase isn't failed for its grammar. The bar leans
  toward flagging: a false "not found" sends the reader to check the page; a
  false "found" vouches for an invented detail.

The result is ``found`` (with the best-matching passage on the page),
``not_found``, or ``unchecked`` when the sentence carries nothing to compare,
such as "See p. 4." Only ``found`` is shown as an ordinary source.

Deliberately lexical: it catches wrong figures, dates and pages, and claims
with nothing in common with the page. It cannot tell that a sentence using the
page's own words says the opposite of it.
"""

import re

from app.services.kb_answer_grounding import _money_values, _percent_values

FOUND = "found"
NOT_FOUND = "not_found"
UNCHECKED = "unchecked"

_MIN_CONTENT_WORDS = 2
_MIN_OVERLAP = 0.6
_STEM = 5
_PREVIEW_CHARS = 240

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_DATE_RE = re.compile(
    r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?\s+(\d{1,2})\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"(?<![\w.,$])(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w%])")
_NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
}
_NUMBER_WORD_RE = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b", re.IGNORECASE)
_QUOTE_RE = re.compile(r"[\"“”]([^\"“”]{12,200})[\"“”]")
_WORD_RE = re.compile(r"[a-z][a-z'-]{3,}")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[*_A-Z0-9-])|\n+")
_ABBREVIATION_RE = re.compile(
    r"\b(?:[ap]\.m|e\.g|i\.e|u\.s|no|nos|sec|secs|vs|etc|approx|dr|mr|ms|mrs|st|inc|corp|fig|vol)\.",
    re.IGNORECASE,
)
_STOPWORDS = frozenset("""
    about above after again also although among another because been before
    being below between both cannot could does doing down during each either
    from further have having here into itself just less more most must neither
    only other over page pages same should since some such than that their them
    then there these they this those through under until upon very were what
    when where which while whom whose will with within without would your
    document documents according states stated says said shows listed section
    only whether doesn't isn't aren't don't didn't wasn't every also
""".split())


def _norm(text: str) -> str:
    text = text.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    text = re.sub(r"[*_`#>|]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_page_refs(text: str, page_ref_re: re.Pattern) -> str:
    return page_ref_re.sub(" ", text)


def _dates(text: str) -> set[tuple[int, int]]:
    return {(_MONTHS[m.group(1).lower()], int(m.group(2))) for m in _DATE_RE.finditer(text)}


def _numbers(text: str) -> set[str]:
    without_money = re.sub(r"\$\s?[\d,]+(?:\.\d+)?", " ", text)
    without_dates = _DATE_RE.sub(" ", without_money)
    digits = {m.group(1).replace(",", "") for m in _NUMBER_RE.finditer(without_dates)}
    return digits | {_NUMBER_WORDS[m.group(1).lower()] for m in _NUMBER_WORD_RE.finditer(without_dates)}


def _content_stems(text: str) -> set[str]:
    return {
        w[:_STEM] for w in _WORD_RE.findall(_norm(text))
        if w not in _STOPWORDS and w not in _MONTHS
    }


def _missing_anchors(claim: str, page: str) -> tuple[int, int]:
    """(anchors in the claim, anchors missing from the page)."""
    page_n = _norm(page)
    total = missing = 0

    page_money, page_pct = set(_money_values(page)), set(_percent_values(page))
    for value in _money_values(claim):
        total += 1
        missing += value not in page_money
    for value in _percent_values(claim):
        total += 1
        missing += value not in page_pct

    page_dates = _dates(page)
    for date in _dates(claim):
        total += 1
        missing += date not in page_dates

    page_numbers = _numbers(page)
    for number in _numbers(claim):
        total += 1
        missing += number not in page_numbers

    for m in _QUOTE_RE.finditer(claim):
        total += 1
        missing += _norm(m.group(1)) not in page_n
    return total, missing


def _judge(claim: str, page: str) -> str:
    anchors, missing = _missing_anchors(claim, page)
    if missing:
        return NOT_FOUND
    if anchors:
        return FOUND
    words = _content_stems(claim)
    if len(words) < _MIN_CONTENT_WORDS:
        return UNCHECKED
    page_words = _content_stems(page)
    overlap = len(words & page_words) / len(words)
    return FOUND if overlap >= _MIN_OVERLAP else NOT_FOUND


def _mask_dots(text: str, page_ref_re: re.Pattern | None = None) -> str:
    """*text* with the periods of page references and abbreviations blanked.

    Same length, so sentence spans found in it index the original. Without
    this "(p. 3)" splits after "p." and the reference loses its sentence."""
    chars = list(text)
    spans = [m.span() for m in _ABBREVIATION_RE.finditer(text)]
    if page_ref_re is not None:
        spans += [m.span() for m in page_ref_re.finditer(text)]
    for start, end in spans:
        for i in range(start, end):
            if chars[i] == ".":
                chars[i] = " "
    return "".join(chars)


def _sentences(text: str, page_ref_re: re.Pattern | None = None) -> list[tuple[int, int]]:
    masked = _mask_dots(text, page_ref_re)
    spans, start = [], 0
    for m in _SENTENCE_END_RE.finditer(masked):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def _has_substance(text: str) -> bool:
    """Whether *text* carries something to check: an anchor or two content words."""
    anchors, _missing = _missing_anchors(text, "")
    return anchors > 0 or len(_content_stems(text)) >= _MIN_CONTENT_WORDS


def _claim_for_ref(answer: str, ref: tuple[int, int], page_ref_re: re.Pattern) -> str:
    """The part of the answer a page reference at *ref* (start, end) supports.

    Normally the clause leading up to it, back to the previous reference in the
    same sentence. In "the $200,000 draft (proposal, p. 2) exceeds the $180,000
    cap (notice, p. 3)" each page is checked against its own figure, not both.
    A reference that opens its clause ("Per p. 3, the cap is …") takes the
    text after it; one with neither takes the whole sentence; a reference
    standing alone ("… is $180,000. (p. 3)") takes the sentence before.
    """
    spans = _sentences(answer, page_ref_re)
    for i, (start, end) in enumerate(spans):
        if not start <= ref[0] < end:
            continue
        sentence = answer[start:end]
        refs = [(m.start() + start, m.end() + start) for m in page_ref_re.finditer(sentence)]
        before_end = max((e for s_, e in refs if e <= ref[0]), default=start)
        after_start = min((s_ for s_, e in refs if s_ >= ref[1]), default=end)
        before = _without_file_names(_strip_page_refs(answer[before_end:ref[0]], page_ref_re))
        after = _without_file_names(_strip_page_refs(answer[ref[1]:after_start], page_ref_re))
        # A figure, date or quote is what a page has to support, wherever it
        # sits; "The proposal draft (file, p. 1) lists … Nov 12" puts it after.
        for candidate in (before, after):
            if _missing_anchors(candidate, "")[0]:
                return candidate
        for candidate in (before, after):
            if _has_substance(candidate):
                return candidate
        claim = _without_file_names(_strip_page_refs(sentence, page_ref_re))
        if not re.search(r"[A-Za-z0-9]{2,}", claim) and i > 0:
            prev_start, prev_end = spans[i - 1]
            claim = _without_file_names(_strip_page_refs(answer[prev_start:prev_end], page_ref_re))
        return claim
    return ""


_FILE_NAME = re.compile(r"[\w.\u2010-\u2015-]+\.(?:pdf|docx?|xlsx?|pptx?|txt|csv|html?|md)\b", re.IGNORECASE)


def _without_file_names(text: str) -> str:
    """A claim without the file names that attribute it: the page doesn't
    contain "sponsor-notice.pdf", and that must not count against it."""
    return _FILE_NAME.sub(" ", text)


def _ref_page(match: re.Match) -> int | None:
    try:
        return int(match.group(1))
    except (IndexError, ValueError):
        return None


def _best_passage(claims: list[str], page: str) -> str:
    """The sentence on the page that shares the most with the claims."""
    want_stems = set().union(*(_content_stems(c) for c in claims)) if claims else set()
    want_money = set().union(*(set(_money_values(c)) for c in claims)) if claims else set()
    want_numbers = set().union(*(_numbers(c) for c in claims)) if claims else set()
    want_dates = set().union(*(_dates(c) for c in claims)) if claims else set()

    best, best_score = "", -1.0
    for start, end in _sentences(page):
        sentence = " ".join(page[start:end].split())
        if not sentence:
            continue
        score = (
            3 * len(want_money & set(_money_values(sentence)))
            + 3 * len(want_numbers & _numbers(sentence))
            + 3 * len(want_dates & _dates(sentence))
            + len(want_stems & _content_stems(sentence))
        )
        if score > best_score:
            best, best_score = sentence, score
    return best[:_PREVIEW_CHARS]


def ground_citation(
    answer: str,
    refs: list[tuple[int, int]],
    page_text: str,
    page_ref_re: re.Pattern,
    joint_text: str = "",
) -> tuple[str, str | None]:
    """Whether the page references at *refs* (start, end) are supported by *page_text*.

    Returns ``(status, passage)``. ``passage`` is the best-matching sentence on
    the page when the status is ``found``, else None. One supported claim is
    enough; otherwise any unsupported one makes the citation ``not_found``.

    *joint_text* is the text of pages cited right alongside this one ("$50,000
    on $200,000 = 25% (proposal, p. 2) (notice, p. 3)"): the claim is judged
    against them together, as long as this page itself supplies part of it.
    """
    claims = [c for c in (_claim_for_ref(answer, r, page_ref_re) for r in refs) if c]
    verdicts = []
    for claim in claims:
        verdict = _judge(claim, page_text)
        if verdict == NOT_FOUND and joint_text and _contributes(claim, page_text):
            verdict = _judge(claim, page_text + "\n" + joint_text)
        verdicts.append(verdict)
    if FOUND in verdicts:
        supported = [c for c, v in zip(claims, verdicts) if v == FOUND]
        return FOUND, _best_passage(supported, page_text) or None
    if NOT_FOUND in verdicts:
        return NOT_FOUND, None
    return UNCHECKED, None


def _contributes(claim: str, page: str) -> bool:
    """Whether *page* states at least one of the claim's anchors."""
    total, missing = _missing_anchors(claim, page)
    return total > missing


def ground_page_citation(
    answer: str, page: int, page_text: str, page_ref_re: re.Pattern,
) -> tuple[str, str | None]:
    """``ground_citation`` for every reference to *page* in *answer*."""
    refs = [m.span() for m in page_ref_re.finditer(answer) if _ref_page(m) == page]
    return ground_citation(answer, refs, page_text, page_ref_re)


# gpt-oss writes citations in its own syntax: 【p. 1】, 【sponsor-notice.pdf†p. 2】,
# 【Source: budget.pdf】, and search-result anchors like 【3†L4-L10】 (#1011).
# The chat shows them as raw text, and the file name inside them is how a
# multi-document answer says whose page it means.
_FULLWIDTH_CITATION = re.compile(r"\s*【([^】]{1,200})】")
_RESULT_ANCHOR = re.compile(r"^\d+†L\d+(?:-L\d+)?$")


def normalize_citation_markup(text: str) -> str:
    """Rewrite 【…】 citations as the app's own "(…)" / "[Source: …]" text."""
    if not text or "【" not in text:
        return text

    def repl(m: re.Match) -> str:
        inner = m.group(1).strip()
        if _RESULT_ANCHOR.match(inner):
            return ""
        inner = re.sub(r"\s*†\s*", ", ", inner)
        if inner.lower().startswith("source:"):
            return f" [{inner}]"
        return f" ({inner})"

    return _FULLWIDTH_CITATION.sub(repl, text)
