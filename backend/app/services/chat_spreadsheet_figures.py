"""Check a reply's yearly figures against the spreadsheet row and year they name.

Support ticket (NIH_R01_Budget_Clean.xlsx, "Summarize this budget"): the reply
showed Year 4's total, $246,000, for Years 1 to 4, beside a grand total the
years did not add up to, and no warning appeared. Every figure it wrote is in
the file somewhere, so the check that asks "does a source state this number"
(``kb_answer_grounding``) had nothing to flag.

This check is about position. A spreadsheet's text is a grid of labelled rows
and year columns, so a reply that says "Total, Year 1: $246,000" can be held
against the Total row's Year 1 cell. A table is also checked against itself:
the years it shows must add up to the total it shows.

A reply that fails is sent back once with the cells to correct
(``require_spreadsheet_figures``). If the reply still disagrees, the
differences are listed under it (``spreadsheet_figures_note``) so a wrong
figure never reaches the user unmarked.

Only an exact label match is checked. A row the reply words differently from
the spreadsheet is left alone rather than guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from pydantic_ai import ModelRetry, RunContext

from app.services.chat_budget_tables import _amount, _key as _budget_key, _plain, _subtotal

if TYPE_CHECKING:
    from app.services.chat_deps import AgenticChatDeps

TOTAL = "total"
MAX_DOCUMENTS = 20
_SHOWN = 8

_YEAR_CELL = re.compile(r"^(?:year|yr|y)\s*(\d{1,2})\b", re.I)
_SEPARATOR = re.compile(r"^:?-{3,}:?$")
_SCALES = {"k": 1_000, "thousand": 1_000, "m": 1_000_000, "mm": 1_000_000, "million": 1_000_000}
_MONEY = r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:thousand|million|mm|k|m)\b)?"
_YEAR = r"(?:year|yr|y)\s?(\d{1,2})\b"
# "$8k in Y4", "$53,000 (Year 1)".
_AMOUNT_THEN_YEAR = re.compile(rf"({_MONEY})\s*(?:\(|in\s+|for\s+|during\s+)?\s*{_YEAR}", re.I)
# "Year 1: $8,000", "Y4 $12k".
_YEAR_THEN_AMOUNT = re.compile(rf"\b{_YEAR}\s*(?::|=|–|—|-|is|was|of)?\s*({_MONEY})", re.I)
# A sentence about a change pairs a year with a difference, not with a cell.
# Whole words: a bare prefix here ("per", "over", "up") would also match
# Personnel, overhead and update, and skip the very sentences worth checking.
_CHANGE = re.compile(
    r"\b(?:increas\w*|decreas\w*|ris(?:e|es|ing)|rose|drop\w*|fell|falls?|grow\w*|grew|more|less|"
    r"higher|lower|differ\w*|chang\w*|up|down|by|over|under|short|above|below|exceed\w*|averag\w*|per)\b",
    re.I,
)
# Rows whose years are not meant to add up to their total column.
_NON_ADDITIVE = re.compile(
    r"\b(?:average|avg|mean|median|rate|ratio|percent\w*|pct|fte|effort|headcount|months?|"
    r"cumulative|running|balance|per)\b|%",
    re.I,
)
# Row labels too general to tie a sentence to one row ("among other things").
_VAGUE_LABELS = frozenset({"other", "others", "misc", "miscellaneous"})
#: Above this many labelled rows the sentence check is skipped: it compares
#: every sentence with every row.
MAX_PROSE_ROWS = 500


@dataclass(frozen=True)
class _Stated:
    """An amount as written: its value and how far rounding may put it off."""

    value: Decimal
    tolerance: Decimal = Decimal(0)
    # The unit of the last digit written: "$53,045" for a cell holding
    # 53,045.27 is the same figure, shown without its cents.
    unit: Decimal = Decimal(1)

    def matches(self, cell: Decimal) -> bool:
        difference = abs(self.value - cell)
        return difference <= self.tolerance or difference < self.unit


def _stated(text: str) -> _Stated | None:
    """A cell or phrase as an amount. "$304k" may stand for 303,500 to 304,499."""
    raw = _plain(text).replace("\\", "").strip()
    match = re.fullmatch(
        r"\(?-?\$?\s?(\d[\d,]*)(\.\d+)?\s?(thousand|million|mm|k|m)?\)?", raw, re.I,
    )
    if not match:
        return None
    whole, fraction, scale = match.group(1), match.group(2) or "", match.group(3)
    try:
        value = Decimal(whole.replace(",", "") + fraction)
    except InvalidOperation:
        return None
    if raw.startswith(("-", "(")):
        value = -value
    if not scale:
        return _Stated(value, unit=Decimal(1) / (Decimal(10) ** (len(fraction) - 1 if fraction else 0)))
    unit = Decimal(_SCALES[scale.lower()])
    places = len(fraction) - 1 if fraction else 0
    return _Stated(value * unit, unit / (Decimal(10) ** places) / 2)


def _key(label: str) -> str:
    """A row label for matching: no parenthetical, markdown, or year."""
    return _budget_key(re.sub(r"\([^)]*\)", " ", label))


def _period(cell: str) -> str | None:
    text = _plain(cell)
    year = _YEAR_CELL.match(text)
    if year:
        return str(int(year.group(1)))
    # "Cumulative Total", "Running total", "Subtotal" and "% of total" are
    # not the sum of the year columns beside them.
    if re.search(r"\btotal\b", text, re.I) and not re.search(
        r"\b(?:cumulative|running|average|avg|mean|sub\s?total|to\s+date|percent\w*)\b|%", text, re.I,
    ):
        return TOTAL
    return None


def _pipe_tables(text: str) -> list[list[list[str]]]:
    """Each run of pipe-table lines as rows of cells, separator rows dropped."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in [*(text or "").splitlines(), ""]:
        line = line.strip()
        if line.startswith("|") and line.endswith("|") and len(line) > 1:
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", line[1:-1])]
            if not all(_SEPARATOR.fullmatch(c) for c in cells):
                current.append(cells)
        elif current:
            tables.append(current)
            current = []
    return tables


@dataclass
class Cell:
    label: str
    key: str
    period: str
    stated: _Stated
    text: str


def _year_column_cells(table: list[list[str]]) -> list[Cell] | None:
    """Rows are categories, columns are years: | Category | Year 1 | Year 2 | Total |."""
    for index, header in enumerate(table):
        periods = [None, *(_period(c) for c in header[1:])]
        years = [p for p in periods if p and p != TOTAL]
        if len(years) < 2 or len(set(years)) != len(years):
            continue
        first = next(i for i, p in enumerate(periods) if p)
        cells = []
        for row in table[index + 1:]:
            if len(row) != len(header):
                continue
            # The label is the first text before the year columns; a
            # spreadsheet may keep an empty or numbered column ahead of it.
            label = next((_plain(c) for c in row[:first] if _plain(c) and _stated(c) is None), "")
            if not label:
                continue
            for period, text in zip(periods[first:], row[first:]):
                stated = _stated(text)
                if period and stated:
                    cells.append(Cell(label, _key(label), period, stated, _plain(text)))
        return cells
    return None


def _year_row_cells(table: list[list[str]]) -> list[Cell] | None:
    """Rows are years, columns are categories: | Year | Total Costs |."""
    if len(table) < 3:
        return None
    header = table[0]
    bare_years = _key(header[0]) in {"year", "years", "budget year", "period", "budget period"}
    cells: list[Cell] = []
    years = 0
    for row in table[1:]:
        if len(row) != len(header):
            continue
        first = _plain(row[0])
        period = _period(first) or (str(int(first)) if bare_years and re.fullmatch(r"\d{1,2}", first) else None)
        if not period:
            continue
        years += period != TOTAL
        for label, text in zip(header[1:], row[1:]):
            stated = _stated(text)
            label = _plain(label)
            if label and stated:
                cells.append(Cell(label, _key(label), period, stated, _plain(text)))
    return cells if years >= 2 else None


def _table_cells(table: list[list[str]]) -> list[Cell]:
    return _year_column_cells(table) or _year_row_cells(table) or []


@dataclass
class Sheet:
    """What the attached spreadsheets state, by row label and year."""

    values: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    ambiguous: set[str] = field(default_factory=set)
    _patterns: "list[tuple[str, str, str, re.Pattern[str]]] | None" = field(default=None, repr=False)

    def add(self, cell: Cell) -> None:
        if cell.key in self.ambiguous or cell.stated.tolerance:
            return
        row = self.values.setdefault(cell.key, {})
        if cell.period in row and row[cell.period] != cell.stated.value:
            # Two rows with one label (two sheets, two sections): no telling
            # which the reply means.
            self.ambiguous.add(cell.key)
            del self.values[cell.key]
            self.labels.pop(cell.key, None)
            return
        row[cell.period] = cell.stated.value
        self.labels.setdefault(cell.key, cell.label)

    def cell(self, key: str, period: str) -> Decimal | None:
        return self.values.get(key, {}).get(period)

    def years(self, key: str) -> set[str]:
        return {p for p in self.values.get(key, {}) if p != TOTAL}

    def has_cents(self, keys: "set[str] | list[str]") -> bool:
        """Whether any of these rows holds a figure that isn't a whole number."""
        return any(
            value != value.to_integral_value()
            for key in keys for value in self.values.get(key, {}).values()
        )

    def label_patterns(self) -> list[tuple[str, str, str, "re.Pattern[str]"]]:
        """(key, label, normalised label, whole-phrase pattern) per row, built once."""
        if self._patterns is None:
            built = []
            for key, label in self.labels.items():
                norm = re.sub(r"[^a-z0-9&]+", " ", _plain(label).lower()).strip()
                if norm and norm not in _VAGUE_LABELS:
                    built.append((key, label, norm, re.compile(rf"(?<![a-z0-9]){re.escape(norm)}(?![a-z0-9])")))
            self._patterns = built
        return self._patterns


def read_sheet(texts: list[str]) -> Sheet:
    """The labelled yearly rows in spreadsheet (or other pipe-table) text."""
    sheet = Sheet()
    for text in texts:
        for table in _pipe_tables(text):
            for cell in _table_cells(table):
                if cell.key:
                    sheet.add(cell)
    return sheet


@dataclass(frozen=True)
class Issue:
    kind: str  # "cell" | "sum" | "prose"
    text: str


def _year_label(period: str) -> str:
    return "Total" if period == TOTAL else f"Year {period}"


def _table_issues(answer: str, sheet: Sheet, *, across_categories: bool) -> list[Issue]:
    issues: list[Issue] = []
    for table in _pipe_tables(answer):
        cells = _table_cells(table)
        rows: dict[str, dict[str, Cell]] = {}
        # Two rows of this table that reduce to one label ("Personnel (PI)",
        # "Personnel (Postdoc)"): which one a sum should use can't be told.
        collided: set[str] = set()
        for cell in cells:
            row = rows.setdefault(cell.key, {})
            if cell.period in row and row[cell.period].label != cell.label:
                collided.add(cell.key)
            row[cell.period] = cell
            expected = sheet.cell(cell.key, cell.period)
            if expected is not None and not cell.stated.matches(expected):
                issues.append(Issue("cell", (
                    f"{cell.label}, {_year_label(cell.period)}: the reply shows {cell.text}; "
                    f"the spreadsheet has {_amount(expected)}."
                )))
        # The years shown for a row must add up to the total shown for it.
        for key, row in rows.items():
            years = sorted((p for p in row if p != TOTAL), key=int)
            if TOTAL not in row or len(years) < 2:
                continue
            if key in collided or _NON_ADDITIVE.search(row[TOTAL].label):
                continue  # An average, a rate, a running balance: not a sum of its years.
            if any(cell.stated.tolerance for cell in row.values()):
                continue  # "$1.2M" is a rounding, not a sum to hold to the dollar.
            if sheet.years(key) - set(years):
                continue  # The table shows some years; its total covers them all.
            shown = sum((row[p].stated.value for p in years), Decimal(0))
            # Whole dollars shown for cells that hold cents can each be off by
            # under a dollar, and so can their sum.
            allowed = Decimal(len(years)) if sheet.has_cents([key]) else Decimal(0)
            if abs(shown - row[TOTAL].stated.value) > allowed:
                issues.append(Issue("sum", (
                    f"{row[TOTAL].label}: Year {years[0]} to Year {years[-1]} as shown add up to "
                    f"{_amount(shown)}, not the {row[TOTAL].text} total shown."
                )))
        if not across_categories or TOTAL not in rows or collided:
            continue
        # The categories shown for a year must add up to the Total row.
        detail_keys = [
            key for key, row in rows.items()
            if key != TOTAL and not _subtotal(key) and not _NON_ADDITIVE.search(next(iter(row.values())).label)
        ]
        details = [rows[key] for key in detail_keys]
        if len(details) < 2:
            continue
        allowed = Decimal(len(details)) if sheet.has_cents([*detail_keys, TOTAL]) else Decimal(0)
        for period, total in rows[TOTAL].items():
            # A table of the main categories is not a full breakdown: the
            # spreadsheet has rows it leaves out, so they need not reach the total.
            if any(key not in rows and key != TOTAL and not _subtotal(key) and period in row
                   for key, row in sheet.values.items()):
                continue
            parts = [row.get(period) for row in details]
            if any(part is None or part.stated.tolerance for part in parts) or total.stated.tolerance:
                continue
            shown = sum((part.stated.value for part in parts if part), Decimal(0))
            if abs(shown - total.stated.value) > allowed:
                issues.append(Issue("sum", (
                    f"{_year_label(period)}: the categories shown add up to {_amount(shown)}, "
                    f"not the {total.text} in the Total row."
                )))
    return issues


def _sentences(answer: str) -> list[str]:
    out = []
    for line in (answer or "").splitlines():
        if line.strip().startswith("|"):
            continue
        out += [part for part in re.split(r"(?<=[.;!?])\s+", line) if part.strip()]
    return out


def _named_row(sentence: str, sheet: Sheet) -> str | None:
    """The one spreadsheet row a sentence names, or None when it names several."""
    lowered = re.sub(r"[^a-z0-9&]+", " ", sentence.lower())
    named = [
        (key, label) for key, label, norm, pattern in sheet.label_patterns()
        # The plain substring test is cheap and rules out almost every row.
        if norm in lowered and pattern.search(lowered)
    ]
    # "Total Direct Costs" also contains "Total": keep the longest label.
    named = [
        (key, label) for key, label in named
        if not any(other != label and label.lower() in other.lower() for _, other in named)
    ]
    return named[0][0] if len(named) == 1 else None


def _year_amount_pairs(sentence: str) -> list[tuple[str, str]]:
    """(amount, year) pairs a sentence states.

    "$8,000 in Year 1 - $6,000 in Year 2" reads amount-then-year twice. The
    year-then-amount pattern would also find "Year 1 - $6,000" there, so it
    is only used for amounts and years the first reading left unpaired.
    """
    pairs: list[tuple[str, str]] = []
    used: list[tuple[int, int]] = []
    for match in _AMOUNT_THEN_YEAR.finditer(sentence):
        pairs.append((match.group(1), match.group(2)))
        used.append(match.span())
    for match in _YEAR_THEN_AMOUNT.finditer(sentence):
        start, end = match.span()
        if any(start < used_end and used_start < end for used_start, used_end in used):
            continue
        pairs.append((match.group(2), match.group(1)))
    return pairs


def _prose_issues(answer: str, sheet: Sheet) -> list[Issue]:
    """"Travel … $8k in Y4" when the Travel row's Year 4 cell says otherwise."""
    issues: list[Issue] = []
    if len(sheet.labels) > MAX_PROSE_ROWS:
        return issues
    for sentence in _sentences(answer):
        if _CHANGE.search(sentence):
            continue
        # Most sentences state no figure for a year: skip them before
        # looking for a row, which is the expensive part.
        pairs = _year_amount_pairs(sentence)
        if not pairs:
            continue
        key = _named_row(sentence, sheet)
        if key is None:
            continue
        for text, year in pairs:
            stated = _stated(text)
            expected = sheet.cell(key, str(int(year)))
            if stated and expected is not None and not stated.matches(expected):
                issues.append(Issue("prose", (
                    f"{sheet.labels[key]}, Year {int(year)}: the reply says {text.strip()}; "
                    f"the spreadsheet has {_amount(expected)}."
                )))
    return issues


def _unique(issues: list[Issue]) -> list[Issue]:
    return list({issue.text: issue for issue in issues}.values())


def spreadsheet_figure_issues(answer: str, texts: list[str], *, for_note: bool = False) -> list[Issue]:
    """Where *answer* disagrees with the spreadsheet text, or with its own totals.

    ``for_note`` keeps only what is safe to print under a reply: table cells
    and year sums. A sentence is matched to a row more loosely, which is good
    enough to ask the model to look again and not to tell the user it is
    wrong; and a Total row the categories don't reach is already marked by
    ``chat_budget_tables.reconcile_budget_tables``.
    """
    if not answer or "$" not in answer and "|" not in answer:
        return []
    sheet = read_sheet(texts)
    issues = _table_issues(answer, sheet, across_categories=not for_note)
    if not for_note and sheet.values:
        issues += _prose_issues(answer, sheet)
    return _unique(issues)


RETRY_INSTRUCTION = (
    "Your reply does not match the attached spreadsheet, or its own totals:\n{issues}\n"
    "Read the spreadsheet again row by row. Copy each figure from its own row and its own "
    "year column: never repeat one year's figure for another year. Use the calculate tool "
    "for any total the spreadsheet does not state. Correct every figure listed, then check "
    "the rest of the reply the same way, including any sentence that describes these "
    "figures. State only what the spreadsheet contains; remove salaries, effort, rates or "
    "items it does not list. Do not repeat your previous reply."
)

NOTE_HEADING = "**Check these figures before using them.**"


def _bullets(issues: list[Issue]) -> str:
    lines = [f"- {issue.text}" for issue in issues[:_SHOWN]]
    if len(issues) > _SHOWN:
        lines.append(f"- …and {len(issues) - _SHOWN} more.")
    return "\n".join(lines)


def spreadsheet_figures_note(answer: str, texts: list[str]) -> str:
    """A note for under a reply that still disagrees with the spreadsheet; "" if none."""
    issues = spreadsheet_figure_issues(answer, texts, for_note=True)
    if not issues:
        return ""
    return (
        f"\n\n{NOTE_HEADING} This reply does not match the spreadsheet, or its own totals:\n"
        f"{_bullets(issues)}"
    )


async def _document_texts(uuids: list[str]) -> list[str]:
    from app.models.document import SmartDocument

    docs = await SmartDocument.find({"uuid": {"$in": uuids[:MAX_DOCUMENTS]}}).to_list()
    return [doc.raw_text or "" for doc in docs]


async def require_spreadsheet_figures(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send back, once per turn, figures the spreadsheet contradicts."""
    deps = ctx.deps
    if ctx.partial_output or deps is None or getattr(deps, "spreadsheet_retry_used", False):
        return output
    if not isinstance(output, str) or "$" not in output:
        return output
    uuids = list(dict.fromkeys([*(getattr(deps, "context_document_uuids", None) or []),
                                *(getattr(deps, "documents_read", None) or [])]))
    # Files attached to the chat itself count too: the note under the reply
    # reads them, so the retry must see the same spreadsheet.
    texts = [*(await _document_texts(uuids) if uuids else []), *(getattr(deps, "attachment_texts", None) or [])]
    issues = spreadsheet_figure_issues(output, texts)
    if not issues:
        return output
    deps.spreadsheet_retry_used = True
    raise ModelRetry(RETRY_INSTRUCTION.format(issues=_bullets(issues)))
