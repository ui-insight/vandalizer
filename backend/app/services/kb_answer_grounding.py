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
    by_ref = _by_ref(sources)
    used: set[int] = set()
    for m in _SNIPPET_REF_RE.finditer(answer):
        used.update(n for n in map(int, _DIGITS_RE.findall(m.group(0))) if n in by_ref)
    for m in _FILENAME_CITATION_RE.finditer(answer):
        cited = m.group(1).lower()
        pages = {int(p) for p in _CITED_PAGE_RE.findall(cited)}
        for ref, s in by_ref.items():
            title = (s.get("document_title") or "").lower()
            if title and title in cited and (not pages or _covers_page(s, pages)):
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
