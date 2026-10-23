"""Find figures in a knowledge-base answer that no retrieved snippet states.

Support ticket (2 CFR 200 KB): "What is the single audit threshold?" retrieved
Subpart F passages about single-audit *oversight* rather than § 200.501, and
the model filled the gap with $750,000 — the threshold before the 2024
revision — confidently and without the "_Beyond the retrieved sources:_"
marker its prompt asks for. The current $1,000,000 was in the KB the whole
time; asking about § 200.501 by number returned it.

A prompt can ask the model not to recall figures, but it cannot make it
comply, so the check runs on the finished answer: every dollar amount and
percentage in it must appear, as the same value and unit, somewhere in the
snippets the model was shown. Anything that doesn't is reported, and chat
shows it under the answer. Regulatory dollar thresholds and rates are the
figures that change between revisions, and the ones a stale memory gets
wrong while sounding right.

Scope is deliberately narrow — money and percentages only. Section numbers,
dates, counts and list numbering are left alone: they are either copied from
the question or too common to check without drowning the real signal.
"""

import json
import re

_SCALES = {
    "k": 1_000,
    "thousand": 1_000,
    "m": 1_000_000,
    "mm": 1_000_000,
    "million": 1_000_000,
    "b": 1_000_000_000,
    "bn": 1_000_000_000,
    "billion": 1_000_000_000,
}

# "$1,000,000", "$1 million", "$750K", "$34.5 million". The scale word must
# end at a word boundary so "$5 more" never reads as five million.
_MONEY_RE = re.compile(
    r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?"
    r"(?:\s?(thousand|million|billion|mm|bn|k|m|b)\b)?",
    re.IGNORECASE,
)

# "15%", "15 %", "15 percent", "15.5 per cent". A digit or separator before
# the number means it is the tail of something longer ("200.15%" is not 15%).
_PERCENT_RE = re.compile(
    r"(?<![\d.,])(\d+(?:\.\d+)?)\s?(?:%|per\s?cent\b)",
    re.IGNORECASE,
)


def _money_values(text: str) -> dict[float, str]:
    out: dict[float, str] = {}
    for m in _MONEY_RE.finditer(text):
        whole, frac, scale = m.group(1), m.group(2) or "", m.group(3)
        try:
            value = float(whole.replace(",", "") + frac)
        except ValueError:
            continue
        if scale:
            value *= _SCALES[scale.lower()]
        out.setdefault(round(value, 2), m.group(0).strip())
    return out


# A bare amount in structured tool output: "1250000", "1,250,000.00". Four or
# more digits, or comma groups, so short counts and list numbers are skipped.
# A digit, "$" or separator before it means it is the tail of something longer.
_BARE_AMOUNT_RE = re.compile(r"(?<![\d$.,])(\d{1,3}(?:,\d{3})+|\d{4,})(\.\d+)?(?!\d|,\d)")


def bare_amounts_as_money(text: str) -> str:
    """*text* with bare amounts written as dollars, for use as a source.

    Extraction and other tool results store a budget as "1250000"; the
    answer reports it as "$1,250,000". Treating the bare number as support
    keeps a real extracted value from being flagged, while a figure that no
    tool returned in any form still is.
    """
    return _BARE_AMOUNT_RE.sub(lambda m: "$" + m.group(1) + (m.group(2) or ""), text or "")


# Field names whose numbers a reply reports as a percentage or in dollars.
# Matched against the underscore-separated words of a JSON key, so
# "aggregate_accuracy", "score_percent" and "estimated_cost_usd" all count
# while "tokens_used" and "num_runs" do not.
_PERCENT_KEY_WORDS = frozenset({
    "score", "accuracy", "consistency", "percent", "pct", "rate",
    "confidence", "precision", "recall", "f1", "coverage",
})
_MONEY_KEY_WORDS = frozenset({"cost", "usd", "price", "dollars", "spend"})


def _key_words(key: str) -> set[str]:
    return set(re.split(r"[^a-z0-9]+", key.lower()))


def _number_forms(value: float, unit: str) -> list[str]:
    """*value* as a reply would quote it: whole, one and two decimals."""
    return [
        f"${round(value, d):,.{d}f}" if unit == "$" else f"{round(value, d):.{d}f}%"
        for d in (0, 1, 2)
    ]


def _keyed_figures(node, key: str = "") -> list[str]:
    """Percent and dollar forms of the numbers under score- and cost-like keys."""
    if isinstance(node, dict):
        return [f for k, v in node.items() for f in _keyed_figures(v, str(k))]
    if isinstance(node, list):
        return [f for item in node for f in _keyed_figures(item, key)]
    if isinstance(node, bool) or not isinstance(node, (int, float)):
        return []
    words = _key_words(key)
    if words & _PERCENT_KEY_WORDS:
        forms = _number_forms(node, "%")
        # Validation and optimizer scores are stored on a 0..1 scale and
        # reported as percents: 0.82 is "82%".
        if 0 <= node <= 1:
            forms += _number_forms(node * 100, "%")
        return forms
    if words & _MONEY_KEY_WORDS:
        return _number_forms(node, "$")
    return []


def tool_output_as_source(text: str) -> str:
    """A tool result, as the text a reply's figures are checked against.

    Bare amounts read as dollars (see ``bare_amounts_as_money``). A JSON
    result also gets each score- or cost-like field written the way a reply
    states it: ``"accuracy": 0.82`` supports "82%", ``"score_percent": 91``
    supports "91%", and ``"estimated_cost_usd": 1.37`` supports "$1.37" and
    "$1". Support ticket: chat repeated a validation run's accuracy and
    consistency and an optimizer's score straight from the tool result, and
    every one was flagged as possibly recalled.
    """
    text = text or ""
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    extra = _keyed_figures(parsed) if isinstance(parsed, (dict, list)) else []
    return "\n".join([bare_amounts_as_money(text), *extra])


def _percent_values(text: str) -> dict[float, str]:
    out: dict[float, str] = {}
    for m in _PERCENT_RE.finditer(text):
        out.setdefault(round(float(m.group(1)), 4), m.group(0).strip())
    return out


def unsupported_figures(answer: str, snippets: str) -> list[str]:
    """Dollar amounts and percentages in *answer* that *snippets* never state.

    Values are compared, not strings: "$1 million" in the answer is supported
    by "$1,000,000" in a snippet, and "15%" by "15 percent". A percentage is
    never supported by a dollar amount of the same number, or the reverse.
    Returned in the answer's own wording, first occurrence, in order.
    """
    if not answer or not answer.strip():
        return []
    snippet_money = set(_money_values(snippets or ""))
    snippet_pct = set(_percent_values(snippets or ""))
    missing = [
        label for value, label in _money_values(answer).items()
        if value not in snippet_money
    ]
    missing += [
        label for value, label in _percent_values(answer).items()
        if value not in snippet_pct
    ]
    order = {label: answer.find(label) for label in missing}
    return sorted(missing, key=lambda label: order[label])


# ---------------------------------------------------------------------------
# Citations whose source doesn't say what the answer attributes to it.
#
# Support ticket ("Subaward Policies" KB): asked what 2 CFR 200.332 requires of
# a pass-through entity, chat gave a detailed answer labelled
# "[Source: 2 CFR 200.332 — Requirements for pass-through entities.]". That
# source was a scraped eCFR page holding the title and site chrome but no rule
# text, so all of the answer came from the model's memory. The figure check
# above saw nothing, because the answer contained no figures. The prompt already
# says never to attribute a claim to a source that doesn't support it, and it
# wasn't followed.
#
# So the citation is checked against the source it names. The text an answer
# attributes to a citation is everything since the previous citation. Its
# content words, less the ones the question already supplied, must mostly
# appear in the snippets retrieved from that source. Paraphrase loses some
# words, so the bar is low: a faithful answer keeps most of the source's
# vocabulary ("subrecipient", "monitoring", "single audit", "management
# decision"), and one written from memory against a page title keeps almost
# none of it. A citation naming a source that wasn't retrieved has no text
# behind it, so it is flagged once it attributes enough words.
# ---------------------------------------------------------------------------

_CITATION_RE = re.compile(r"\[Source:\s*([^\]]+)\]", re.IGNORECASE)
_LOCATOR_RE = re.compile(r"\([^)]*\)")
# Text the model has already marked as general knowledge isn't attributed to
# the citation that follows it.
_BEYOND_RE = re.compile(r"_?Beyond the retrieved sources:_?[^\n]*", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z][a-z0-9'-]*[a-z0-9]|\d+(?:\.\d+)*", re.IGNORECASE)

# A span this short is a sentence fragment. Too few words to judge.
_MIN_CLAIM_WORDS = 6
# Share of a span's content words that the cited source must contain. Measured
# on 52 answers written by a separate model from real 2 CFR 200 snippets:
# faithful answers, heavy paraphrase included, scored 0.31 or higher; answers
# written from memory against a page title scored 0.07 or lower; answers citing
# a real but off-topic snippet scored 0.29 or lower. The bar sits below the
# paraphrase floor. A wrong-but-related snippet can clear it, which costs
# two of those twelve cases, and a false alarm on a good answer costs more.
_MIN_SUPPORT = 0.25

_STOPWORDS = frozenset(
    """
    a about above after again against all also although among an and any are as
    at be because been before being below between both but by can could did do
    does doing down during each either else etc even ever every for from further
    had has have having here how however if in into is it its itself just least
    less may might more most much must neither no nor not of off often on once
    one only or other otherwise our out over own per rather same shall should
    since so some such than that the their them then there these they this those
    though through thus to too under until up upon very via was were what when
    where whether which while who whom whose why will with within without would
    yet you your source sources beyond retrieved
    """.split()
)


def _stem(word: str) -> str:
    # Crude, but symmetric: answer and source go through the same function, so
    # "monitoring" meets "monitor" and "subrecipients" meets "subrecipient".
    for suffix in ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if len(word) - len(suffix) >= 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _content_words(text: str) -> set[str]:
    words = set()
    for raw in _WORD_RE.findall(text.lower()):
        for part in raw.split("-"):
            part = part.strip("'")
            if len(part) >= 3 and part not in _STOPWORDS:
                words.add(_stem(part))
            elif part[:1].isdigit():
                words.add(part)
    return words


def _normalize_name(name: str) -> str:
    # Page and sheet locators — "(p. 4)", "(pp. 2–3)", "(Sheet1)" — are not
    # part of the name.
    return " ".join(_WORD_RE.findall(_LOCATOR_RE.sub(" ", name).lower()))


def _matching_sources(cited: str, names: list[str]) -> list[str]:
    """The retrieved sources a citation names.

    The model writes "X (p. 4)" or "X — Policies KB" for a snippet shown as
    "X", shortens "2 CFR 200.308 — Revision of budget" to "2 CFR 200.308",
    and drops trailing periods. A source matches when either name, locators
    removed, starts with the other. A citation short enough to match several
    sources is judged against all of them, so ambiguity never raises a flag.
    """
    c = _normalize_name(cited)
    if not c:
        return []
    out = []
    for name in names:
        n = _normalize_name(name)
        if n and (c.startswith(n) or n.startswith(c)):
            out.append(name)
    return out


def unsupported_citations(
    answer: str,
    source_texts: dict[str, str],
    question: str = "",
) -> list[str]:
    """Source names cited in *answer* for text those sources don't contain.

    *source_texts* maps each retrieved source's name to the text of the snippets
    retrieved from it. Citations in a row (``[Source: A] [Source: B]``) share
    the span before them and are judged against the union of their sources.
    Returned as the answer cites them, first occurrence, in order.
    """
    if not answer or not answer.strip():
        return []
    answer = _BEYOND_RE.sub(" ", answer)
    names = list(source_texts)
    vocab = {name: _content_words(text) for name, text in source_texts.items()}
    given = _content_words(question)

    # Group adjacent citations, each group with the text it closes.
    groups: list[tuple[str, list[str]]] = []
    span_start = 0
    for m in _CITATION_RE.finditer(answer):
        between = answer[span_start:m.start()]
        cited = [c.strip() for c in m.group(1).split(";") if c.strip()]
        if groups and not _content_words(between):
            groups[-1][1].extend(cited)
        else:
            groups.append((between, cited))
        span_start = m.end()

    flagged: list[str] = []
    for span, cited in groups:
        claim = _content_words(span) - given
        if len(claim) < _MIN_CLAIM_WORDS:
            continue
        support: set[str] = set()
        for c in cited:
            for name in _matching_sources(c, names):
                support |= vocab[name]
        if len(claim & support) / len(claim) < _MIN_SUPPORT:
            flagged.extend(c for c in cited if c not in flagged)
    return flagged


# --- Which retrieved snippets an answer used --------------------------------
#
# Support ticket: a KB answer saying "QA Smoke doesn't contain the DOE travel
# rules" was shown with 7–10 PAPPG.pdf source chips under it, because every
# snippet retrieval returned was listed as a source whether or not the answer
# drew on it. Retrieval ranks by similarity, so a question the KB doesn't
# cover still returns its nearest passages, and listing them all made an
# honest "not found" look sourced. A filename alone can't settle which chunk
# was used either — one PAPPG.pdf contributes many — so each snippet is
# numbered in the prompt and the model cites the numbers it drew on. Only
# those are the answer's sources; the rest were searched but not used.

# "[S3]", "[S1, S3]", "[S1; S3]" or "[S1, 3]". Adjacent "[S1][S3]" are two
# matches.
_SNIPPET_REF_RE = re.compile(r"\[\s*S\d+(?:\s*[,;]\s*S?\d+)*\s*\]")
_DIGITS_RE = re.compile(r"\d+")
# The filename form the prompt asked for before snippets were numbered, which
# a model can still fall back on, e.g. after seeing it in earlier turns.
_FILENAME_CITATION_RE = re.compile(r"\[Source:\s*([^\]]+)\]", re.IGNORECASE)
_CITED_PAGE_RE = re.compile(r"\bp(?:age|p)?\.?\s*~?\s*(\d+)", re.IGNORECASE)


def _by_ref(sources: list[dict]) -> dict[int, dict]:
    return {
        s["ref"]: s
        for s in sources
        if isinstance(s.get("ref"), int) and not isinstance(s.get("ref"), bool)
    }


def _covers_page(source: dict, pages: set[int]) -> bool:
    start = source.get("page")
    if not isinstance(start, int):
        # A sheet or a web page has no page to disagree with.
        return True
    end = source.get("page_end") if isinstance(source.get("page_end"), int) else start
    return any(start <= p <= end for p in pages)


def used_snippet_refs(answer: str, sources: list[dict]) -> list[int]:
    """The numbers of the snippets ``answer`` cites, in order.

    A number no snippet carries is ignored. A citation by filename counts for
    that file's snippets on the page it names, or all of them when it names
    none: less precise than a number, but it is still the model saying it
    used the file. An answer that cites nothing used nothing — which is what
    "the sources don't cover this" should look like.
    """
    from app.services.kb_grounding import _locator, _norm_citation

    by_ref = _by_ref(sources)
    used: set[int] = set()
    for m in _SNIPPET_REF_RE.finditer(answer):
        used.update(n for n in map(int, _DIGITS_RE.findall(m.group(0))) if n in by_ref)
    for m in _FILENAME_CITATION_RE.finditer(answer):
        for one in m.group(1).split(";"):
            cited = one.lower()
            pages = {int(p) for p in _CITED_PAGE_RE.findall(cited)}
            # A page-less source's passages are told apart by where they sit
            # ("§ 200.307 · part 2"): such a citation used that passage only.
            where = _locator(_norm_citation(one))
            for ref, s in by_ref.items():
                title = (s.get("document_title") or "").lower()
                if not title or title not in cited:
                    continue
                if where is not None:
                    if _locator(_norm_citation(s.get("label") or "")) == where:
                        used.add(ref)
                elif not pages or _covers_page(s, pages):
                    used.add(ref)
    return sorted(used)


def expand_snippet_refs(answer: str, sources: list[dict]) -> str:
    """Replace ``[S3]`` with the readable ``[Source: PAPPG.pdf, p. 54]``.

    The numbers mean something only within the turn that showed them, so the
    stored answer must not keep them: the next turn numbers its own snippets
    from 1 and reads this one back as history. A reference to a number no
    snippet carries is left as written rather than silently erased.
    """
    by_ref = _by_ref(sources)

    def expand(m: re.Match) -> str:
        labels: list[str] = []
        for n in map(int, _DIGITS_RE.findall(m.group(0))):
            s = by_ref.get(n)
            if s is None:
                return m.group(0)
            labels.append(s.get("cite_label") or s.get("document_title") or f"S{n}")
        return f"[Source: {'; '.join(dict.fromkeys(labels))}]"

    return _SNIPPET_REF_RE.sub(expand, answer)
