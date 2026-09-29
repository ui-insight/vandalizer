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
