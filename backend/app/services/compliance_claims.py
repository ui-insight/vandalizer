"""Keep chat's compliance language to what was actually checked.

Support ticket: asked whether a subaward complies with 2 CFR 200 and the NIH
Grants Policy, chat said correctly that no compliance rules were defined, then
produced a "Pass/Fail Compliance Check" table with 16 green "✅ Pass" marks.
Each mark meant only that the document mentions the item. The same reply told
the user to check the Single Audit clause against "$750K", the threshold the
2024 Uniform Guidance revision raised to $1,000,000.

A prompt can't enforce either, so both are checked after the reply is written:

- ``relabel_presence_checks``: when no compliance rules were evaluated this
  turn, Pass/Fail cells in a compliance table become "Stated in document" /
  "Not confirmed", and the reply says it is not a compliance determination.
- ``superseded_threshold_note``: a 2 CFR 200 figure the October 2024 revision
  replaced, stated in that rule's context without the current figure, gets a
  note with the current figure and a pointer to verify it in the eCFR.
"""

import re
from dataclasses import dataclass

from app.services.kb_answer_grounding import _money_values, _percent_values

# ---------------------------------------------------------------------------
# Presence checks presented as compliance results
# ---------------------------------------------------------------------------

_COMPLIANCE_TOPIC = re.compile(
    r"complian|\bCFR\b|grants policy|uniform guidance|\bFAR\b|\bGPS\b", re.IGNORECASE,
)
_MARKS = r"[\s*_`✅❌✔️✓✗✘❎☑️🟢🔴]*"
# A status cell: the mark alone, or the mark then its reason ("✅ Pass — cited").
_REST = r"(?P<rest>(?:\s*[—–:(-].*)?)$"
_PASS_CELL = re.compile(rf"^{_MARKS}(?:pass(?:ed)?|compliant|met|✅|✔️|✓){_MARKS}{_REST}", re.IGNORECASE)
_FAIL_CELL = re.compile(
    rf"^{_MARKS}(?:fail(?:ed)?|non-?compliant|not met|❌|✗|✘){_MARKS}{_REST}", re.IGNORECASE,
)
_PASS_FAIL_PHRASE = re.compile(
    r"pass\s*/\s*fail(?:\s+compliance)?(?:\s+(?:check(?:list)?|list|review|table|summary|results?))?",
    re.IGNORECASE,
)
_HEADER_CELL = re.compile(r"^[\s*_`]*(?:pass\s*/\s*fail|compliance(?: status| result)?)[\s*_`]*$", re.IGNORECASE)

PRESENCE_NOTE = (
    "**This is not a compliance determination.** No compliance rules were evaluated: "
    "✓ means the document states the item, ✗ means it wasn't confirmed in the document. "
    "Whether the terms satisfy 2 CFR 200 or the sponsor's policy still needs review "
    "against the current regulation."
)


def _rules_evaluated(tool_results: list[dict]) -> bool:
    for result in tool_results or []:
        content = result.get("content")
        if result.get("tool_name") == "check_compliance" and isinstance(content, dict):
            if (content.get("rules_checked") or 0) > 0:
                return True
    return False


def _relabel_cell(cell: str, header: bool) -> str:
    stripped = cell.strip()
    if not stripped:
        return cell
    if header:
        return " Stated in document? " if _HEADER_CELL.match(stripped) else cell
    for pattern, label in ((_PASS_CELL, "✓ Stated in document"), (_FAIL_CELL, "✗ Not confirmed")):
        match = pattern.match(stripped)
        if match:
            rest = match.group("rest").strip()
            return f" {label} {rest} " if rest else f" {label} "
    return cell


_SEPARATOR_ROW = re.compile(r"^\s*\|?\s*:?-{3,}")


def relabel_presence_checks(answer: str, tool_results: list[dict]) -> str:
    """Pass/Fail cells in a compliance table, relabelled as presence marks.

    Only when no compliance rules ran this turn: a check_compliance result
    with evaluated rules is a real pass/fail and is left alone.
    """
    if not answer or _rules_evaluated(tool_results) or not _COMPLIANCE_TOPIC.search(answer):
        return answer
    lines = answer.split("\n")
    changed = False
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        header = i + 1 < len(lines) and bool(_SEPARATOR_ROW.match(lines[i + 1]))
        cells = line.split("|")
        relabelled = [cells[0], *(_relabel_cell(c, header) for c in cells[1:-1]), cells[-1]] if len(cells) > 2 else cells
        new_line = "|".join(relabelled)
        if new_line != line:
            lines[i] = new_line
            changed = True
    if not changed:
        return answer
    text = "\n".join(lines)
    text = _PASS_FAIL_PHRASE.sub("Document review (stated / not stated)", text)
    return f"{text}\n\n{PRESENCE_NOTE}"


# ---------------------------------------------------------------------------
# Thresholds the 2024 Uniform Guidance revision replaced
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Superseded:
    old: float
    current: float
    percent: bool
    context: re.Pattern[str]
    note: str


_SUPERSEDED = [
    _Superseded(750_000, 1_000_000, False, re.compile(r"single audit|subpart f|200\.501|audit threshold", re.I),
                "2 CFR 200.501 requires a Single Audit at $1,000,000 or more in federal expenditures "
                "for fiscal years beginning on or after October 1, 2024 ($750,000 before)."),
    _Superseded(5_000, 10_000, False, re.compile(r"\bequipment\b|200\.313|capital asset", re.I),
                "Under 2 CFR 200.1 equipment is $10,000 or more per unit (or a lower entity threshold) "
                "for awards made on or after October 1, 2024 ($5,000 before)."),
    _Superseded(5_000, 10_000, False, re.compile(r"(?:unused|residual) supplies|200\.314", re.I),
                "2 CFR 200.314 sets the residual-supplies threshold at $10,000 for awards made on or "
                "after October 1, 2024 ($5,000 before)."),
    _Superseded(25_000, 50_000, False, re.compile(r"\bMTDC\b|modified total direct|200\.1\b", re.I),
                "Modified total direct costs (2 CFR 200.1) include up to the first $50,000 of each "
                "subaward for awards made on or after October 1, 2024 ($25,000 before)."),
    _Superseded(250_000, 500_000, False, re.compile(r"fixed[- ]amount|200\.333", re.I),
                "2 CFR 200.333 allows fixed amount subawards up to $500,000 for awards made on or after "
                "October 1, 2024 ($250,000 before)."),
    _Superseded(10, 15, True, re.compile(r"de minimis|200\.414", re.I),
                "The de minimis indirect cost rate in 2 CFR 200.414(f) is up to 15% of modified total "
                "direct costs for awards made on or after October 1, 2024 (10% before)."),
]

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n")
NOTE_PREFIX = "**Check the current rule:** "


def superseded_threshold_note(answer: str) -> str:
    """A note for each replaced 2 CFR 200 figure the reply states as current.

    A figure counts when a sentence (or table row) states it next to its
    rule's words and doesn't also state the current figure, so "raised from
    $750,000 to $1,000,000" is fine. Returns "" when there is nothing to note.
    """
    if not answer:
        return ""
    notes: list[str] = []
    for sentence in _SENTENCE_BREAK.split(answer):
        if not sentence.strip():
            continue
        money = set(_money_values(sentence))
        percents = set(_percent_values(sentence))
        for rule in _SUPERSEDED:
            values = percents if rule.percent else money
            if rule.old in values and rule.current not in values and rule.context.search(sentence):
                if rule.note not in notes:
                    notes.append(rule.note)
    if not notes:
        return ""
    return NOTE_PREFIX + " ".join(notes) + " Verify figures against the current eCFR text."
