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
