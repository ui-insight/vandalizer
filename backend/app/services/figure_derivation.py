"""Figures a reply calculated from figures its sources state.

Support ticket: asked to add up an NIH budget table and test its 52% indirect
rate, chat did the arithmetic correctly, but the source checks treated every
result as a figure no source states. "$131.6K" (52% × $253,000) was flagged
as possibly from "the model's general knowledge", and on a follow-up all 16
calculated values were. The page chip for the budget table said "passage not
found" although every input was on it.

A figure counts as calculated when, in the same sentence or table row, it is
a sum, difference, ratio or percentage of figures that are stated in the
sources or were themselves calculated earlier in the reply (or, in a table,
the sum of its column above it). Each one carries its formula, so the reader
sees "52% × $253,000 = $131,560" instead of a warning. Rounding is allowed to
the precision the reply wrote ("$131.6K" for $131,560, "20.2%" for 0.20158).

Only figures in the same sentence or row are combined. Combining any figures
anywhere would "derive" an invented number by coincidence.
"""

import itertools
import re
from dataclasses import dataclass

from app.services.kb_answer_grounding import _MONEY_RE, _PERCENT_RE, _SCALES

_MAX_OPERANDS = 10  # subset sums: 2**10 combinations per row at most
_PASSES = 4  # chains: a row's total feeds the next row's percentage


@dataclass(frozen=True)
class Figure:
    label: str
    value: float
    percent: bool
    tolerance: float


@dataclass(frozen=True)
class Derivation:
    label: str
    value: float
    percent: bool
    formula: str


def _decimals(text: str) -> int:
    m = re.search(r"\.(\d+)", text)
    return len(m.group(1)) if m else 0


def _figures(text: str) -> list[Figure]:
    out: list[tuple[int, Figure]] = []
    for m in _MONEY_RE.finditer(text):
        whole, frac, scale = m.group(1), m.group(2) or "", m.group(3)
        try:
            value = float(whole.replace(",", "") + frac)
        except ValueError:
            continue
        unit = _SCALES[scale.lower()] if scale else 1
        tolerance = max(0.51, 0.5 * unit * 10 ** -len(frac.lstrip(".")))
        out.append((m.start(), Figure(m.group(0).strip(), round(value * unit, 2), False, tolerance)))
    for m in _PERCENT_RE.finditer(text):
        value = float(m.group(1))
        out.append((m.start(), Figure(m.group(0).strip(), value, True, 0.5 * 10 ** -_decimals(m.group(1)) + 1e-9)))
    return [f for _, f in sorted(out, key=lambda pair: pair[0])]


# "625,000 ÷ 1,250,000 = 50.0%": working written without "$". Support
# ticket: "625,000 ÷ 1,250,000 = 50.0%" and "625,000 − 265,000 = $360,000"
# were flagged although every input was in the spreadsheet, because only "$"
# amounts were read as operands.
#
# Bare numbers are read only as the operands of working the reply writes out
# right before the figure ("a op b = figure"), and that working is evaluated
# exactly as written. A bare number anywhere else in the sentence is never an
# operand: with subset sums and a rounded figure's tolerance ("$1M" is ±$500K),
# a list of yearly totals would "derive" almost any invented round figure.
# A number must be comma-grouped (so a year such as "2026" is never one) and
# must not carry another currency or a unit word, which breaks the working.
_NUM = r"\$?\s?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$\s?\d+(?:\.\d+)?"
_OP = r"\s*(?:[-−–+×x*÷/]|plus|minus|times|divided\s+by)\s*"
_WORKING = re.compile(
    rf"(?<![\w€£¥.,$%])((?:[-−](?=[\d$]))?(?:{_NUM})(?:{_OP}(?:{_NUM}))+)"
    r"\s*(?:=|equals\b|is\b|comes\s+to\b|gives\b)\s*[*_]*\s*$",
    re.IGNORECASE,
)
_TOKEN = re.compile(rf"({_NUM})|(divided\s+by|plus|minus|times|[-−–+×x*÷/])", re.IGNORECASE)
_OPS = {"+": "+", "plus": "+", "-": "-", "−": "-", "–": "-", "minus": "-",
        "×": "*", "x": "*", "*": "*", "times": "*", "÷": "/", "/": "/"}


def _evaluate(tokens: list[tuple[float, str]]) -> float | None:
    """Evaluate "a op b op c" with the usual precedence (no parentheses)."""
    terms: list[float] = [tokens[0][0]]
    ops: list[str] = []
    for value, op in tokens[1:]:
        if op in "*/":
            if op == "/" and value == 0:
                return None
            terms[-1] = terms[-1] * value if op == "*" else terms[-1] / value
        else:
            terms.append(value)
            ops.append(op)
    total = terms[0]
    for op, term in zip(ops, terms[1:]):
        total = total + term if op == "+" else total - term
    return total


def _written_working(
    segment: str, target: Figure, money: set[float],
) -> str | None:
    """The formula when *segment* writes "a op b = target" over known amounts.

    Every operand must be stated in the sources (or calculated earlier), the
    working must evaluate to the target within the precision of its operands
    (a rounded target such as "$1M" does not widen it), and a percentage
    target must come from working that divides.
    """
    m = None
    at = segment.find(target.label)
    while at != -1 and m is None:
        m = _WORKING.search(segment[:at])
        # Only the whole working: "52% × 253,000 + 10,000" is not "253,000 + 10,000".
        before = segment[:m.start()].rstrip() if m else ""
        if m and not re.fullmatch(r"\s*[-*+•]", before) and re.search(
            r"(?:[-−–+×x*÷/%\d€£¥]|plus|minus|times|by)$", before, re.IGNORECASE,
        ):
            m = None
        at = segment.find(target.label, at + 1)
    if m is None:
        return None
    expr = m.group(1).strip()
    tokens: list[tuple[float, str]] = []
    pending = "+"
    sign = 1.0
    if expr[0] in "-−":
        sign, expr_body = -1.0, expr[1:]
    else:
        expr_body = expr
    for tok in _TOKEN.finditer(expr_body):
        if tok.group(1):
            value = float(re.sub(r"[$,\s]", "", tok.group(1)))
            if round(value, 2) not in money:
                return None
            tokens.append((sign * value if not tokens else value, pending))
            pending = ""
        else:
            if pending:
                return None
            word = tok.group(2).lower()
            pending = "/" if word.startswith("divided") else _OPS[word]
    if pending or len(tokens) < 2:
        return None
    result = _evaluate(tokens)
    if result is None:
        return None
    divides = any(op == "/" for _, op in tokens)
    if target.percent:
        if not divides:
            return None
        value, tolerance = result * 100, target.tolerance  # "625,000 ÷ 1,250,000 = 50.0%"
    else:
        # Close to the exact arithmetic, whatever precision the target was
        # written to: "304,000 + 240,000 = $1M" is not a rounding of $544,000.
        value, tolerance = result, min(target.tolerance, max(0.51, 0.005 * abs(result)))
    if abs(value - target.value) <= tolerance:
        return f"{m.group(1).strip()} = {target.label}"
    return None


def _segments(text: str) -> list[tuple[str, str]]:
    """(scope, extra operand text): sentences, and table rows with their header.

    A row's operands include its table's header row, where a column such as
    "52% of direct" states the rate the row applies.
    """
    parts: list[tuple[str, str]] = []
    header: str | None = None
    for line in text.split("\n"):
        if line.lstrip().startswith("|"):
            if header is None:
                header = line
                parts.append((line, ""))
            elif not re.fullmatch(r"[\s|:-]+", line):
                parts.append((line, header))
        else:
            header = None
            parts.extend((p, "") for p in re.split(r"(?<=[.!?])\s+(?=[A-Z(*_])", line) if p.strip())
    return parts


def _tables(text: str) -> list[list[list[str]]]:
    """Markdown tables as rows of cells, separator rows dropped."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in text.split("\n"):
        if line.lstrip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
                current.append(cells)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def _known(value: float, percent: bool, money: set[float], pct: set[float]) -> bool:
    pool = pct if percent else money
    if percent:
        return any(abs(value - p) <= 1e-6 for p in pool)
    return round(value, 2) in pool


def _match(target: Figure, candidates: list[tuple[float, str]]) -> str | None:
    for value, expr in candidates:
        if abs(value - target.value) <= target.tolerance:
            return f"{expr} = {target.label}"
    return None


def _candidates(target: Figure, money: list[Figure], pct: list[Figure]) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    ops = money[:_MAX_OPERANDS]
    sums: list[tuple[float, str]] = []
    for size in range(1, len(ops) + 1):
        for combo in itertools.combinations(ops, size):
            total = sum(f.value for f in combo)
            sums.append((total, " + ".join(f.label for f in combo)))
    if target.percent:
        for a, b in itertools.permutations(ops, 2):
            if b.value:
                out.append((100 * a.value / b.value, f"{a.label} ÷ {b.label}"))
        for (total, expr) in sums:
            for b in ops:
                if b.value and "+" in expr and b.label not in expr.split(" + "):
                    out.append((100 * total / b.value, f"({expr}) ÷ {b.label}"))
        return out
    out += [(total, expr) for total, expr in sums if "+" in expr]
    for a, b in itertools.permutations(ops, 2):
        out.append((a.value - b.value, f"{a.label} − {b.label}"))
    for p in pct:
        for total, expr in sums:
            wrapped = f"({expr})" if "+" in expr else expr
            out.append((p.value / 100 * total, f"{p.label} × {wrapped}"))
    return out


def derive_figures(answer: str, source_money: set[float], source_pct: set[float]) -> list[Derivation]:
    """Figures in *answer* calculated from stated (or earlier calculated) ones."""
    money = {round(v, 2) for v in source_money}
    pct = set(source_pct)
    found: dict[str, Derivation] = {}
    segments = _segments(answer or "")
    tables = _tables(answer or "")
    for _ in range(_PASSES):
        progress = False
        for segment, context in segments:
            figures = _figures(segment)
            extra = _figures(context)
            for target in figures:
                if target.label in found or _known(target.value, target.percent, money, pct):
                    continue
                operands = [
                    f for f in (*figures, *extra)
                    if f is not target and _known(f.value, f.percent, money, pct)
                ]
                formula = _match(target, _candidates(
                    target, [f for f in operands if not f.percent], [f for f in operands if f.percent],
                )) or _written_working(segment, target, money)
                if formula:
                    found[target.label] = Derivation(target.label, target.value, target.percent, formula)
                    (pct if target.percent else money).add(target.value if target.percent else round(target.value, 2))
                    progress = True
        # A table total: the sum of the known figures above it in its column.
        for table in tables:
            width = max(len(r) for r in table)
            for col in range(width):
                above: list[Figure] = []
                for row in table:
                    cell = row[col] if col < len(row) else ""
                    figs = [f for f in _figures(cell) if not f.percent]
                    if len(figs) != 1:
                        continue
                    target = figs[0]
                    if target.label not in found and not _known(target.value, False, money, pct) and len(above) >= 2:
                        total = sum(f.value for f in above)
                        if abs(total - target.value) <= target.tolerance:
                            formula = " + ".join(f.label for f in above) + f" = {target.label}"
                            found[target.label] = Derivation(target.label, target.value, False, formula)
                            money.add(round(target.value, 2))
                            progress = True
                    if _known(target.value, False, money, pct):
                        above.append(target)
        if not progress:
            break
    order = {label: (answer or "").find(label) for label in found}
    return sorted(found.values(), key=lambda d: order[d.label])
