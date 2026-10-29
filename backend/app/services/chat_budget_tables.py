"""Reconcile chat's yearly budget tables against structured extraction results.

The chat model can omit rows while copying a correct total. Restore categories
from a uniquely matching extraction, then do the arithmetic in decimal dollars.
Never fill a gap with an invented category or change a source-reported total.
"""

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation


_YEAR = re.compile(r"\b(?:year|yr)\s*(\d+)\b", re.I)
_TABLE = re.compile(r"(?:^\|[^\n]+\|[ \t]*\n){2,}(?:^\|[^\n]+\|[ \t]*(?:\n|$))?", re.M)
_SEPARATOR = re.compile(r"^:?-{3,}:?$")
_EMPTY = {"", "—", "–", "-", "n/a", "none", "null", "not found", "not stated"}


def _plain(text: str) -> str:
    return re.sub(r"[*`_]", "", text).strip()


def _money(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = _plain(str(value)).replace(",", "").replace("$", "").strip()
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    if not re.fullmatch(r"-?\d+(?:\.\d{1,2})?", text):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _label(text: str) -> str:
    text = _YEAR.sub("", _plain(text))
    return re.sub(r"^budget\b[\s:–—-]*", "", text, flags=re.I).strip(" :-–—")


def _key(label: str) -> str:
    key = re.sub(r"[^a-z0-9]+", " ", _label(label).lower()).strip()
    aliases = {
        "salary": "salaries", "salaries and wages": "salaries", "salary and wages": "salaries",
        "fringe benefits": "fringe", "materials and supplies": "supplies",
        "f a": "indirect costs", "facilities and administrative costs": "indirect costs",
        "total budget": "total", "total costs": "total", "total project costs": "total",
        "grand total": "total", "total project budget": "total",
    }
    return aliases.get(key, key)


def _subtotal(label: str) -> bool:
    key = _key(label)
    return key != "total" and ("subtotal" in key or key.startswith("total ") or key == "direct costs")


def _amount(value: Decimal | None) -> str:
    if value is None:
        return "Not found"
    return f"${value:,.0f}" if value == value.to_integral() else f"${value:,.2f}"


@dataclass
class _Row:
    label: str
    values: dict[str, Decimal | None] = field(default_factory=dict)


def _leaves(value, path: str = ""):
    """Flat fields and JSON objects with category/year in either order."""
    if isinstance(value, str) and value.strip().startswith(("{", "[")):
        try:
            value = json.loads(value)
        except ValueError:
            pass
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaves(child, f"{path} {key}".strip())
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            label_key = next((key for key in item if key.lower() in {"category", "year"}), None)
            if label_key is None:
                continue  # Array positions are not evidence of which year a value belongs to.
            label = str(item[label_key])
            if label_key.lower() == "year" and label.isdigit():
                label = f"Year {label}"
            yield from _leaves({key: child for key, child in item.items() if key != label_key}, f"{path} {label}")
    else:
        yield path, value


def _extracted_rows(entity: dict) -> dict[str, _Row]:
    rows: dict[str, _Row] = {}
    for name, value in _leaves(entity):
        name = name.replace("_", " ")
        periods = _YEAR.findall(name)
        if len(periods) != 1 or re.search(
            r"\b(rate|percent|percentage|base|months|duration|date|fte|effort|count)\b", name, re.I,
        ):
            continue
        amount = _money(value)
        if amount is None and value is not None and str(value).strip().lower() not in _EMPTY:
            continue
        label = _label(name)
        if not label:
            continue
        key = _key(label)
        # A yearly numeric field need not be money (e.g. enrollment counts).
        # Explicit budget fields and currency values allow arbitrary categories;
        # familiar cost labels also accept bare numbers from extraction tools.
        if not (re.search(r"\bbudget\b", name, re.I) or "$" in str(value) or re.search(
            r"\b(salaries|wages|personnel|fringe|travel|supplies|materials|equipment|"
            r"costs|subaward|tuition|consultants|total)\b", key,
        )):
            continue
        row = rows.setdefault(key, _Row(label))
        period = periods[0]
        if period in row.values and row.values[period] != amount:
            # Ambiguous duplicate fields must not select a value arbitrarily.
            return {}
        row.values[period] = amount
    return rows


def _candidates(tool_results: list[dict]) -> list[dict[str, _Row]]:
    result = []
    for tool in tool_results:
        if tool.get("tool_name") not in {"run_extraction", "run_pin_on_project"}:
            continue
        content = tool.get("content")
        if not isinstance(content, dict) or content.get("error") or content.get("needs_confirmation"):
            continue
        for entity in content.get("entities") or []:
            if isinstance(entity, dict):
                rows = _extracted_rows(entity)
                if rows:
                    result.append(rows)
    return result


def reconcile_budget_tables(answer: str, tool_results: list[dict]) -> str:
    """Repair only an unambiguous yearly cost table; expose unresolved sums.

    Two matching detail rows identify an extraction. Multiple matching entities
    are ambiguous: never pool separate documents or pick one by list order.
    Unsupported table layouts remain unchanged.
    """
    candidates = _candidates(tool_results)

    def reconcile(match: re.Match) -> str:
        original = match.group()
        lines = [line.strip() for line in original.strip().splitlines()]
        cells = [[_plain(cell) for cell in line.strip("|").split("|")] for line in lines]
        if len(cells) < 4 or not all(_SEPARATOR.fullmatch(c) for c in cells[1]):
            return original
        header = cells[0]
        years = [_YEAR.fullmatch(c) for c in header[1:]]
        if not years or not all(years) or any(len(row) != len(header) for row in cells[2:]):
            return original
        periods = [year.group(1) for year in years]
        if len(set(periods)) != len(periods):
            return original
        rows = {
            _key(row[0]): _Row(row[0], dict(zip(periods, (_money(v) for v in row[1:]))))
            for row in cells[2:]
        }
        if "total" not in rows or len(rows) != len(cells) - 2:
            return original
        matches = []
        for candidate in candidates:
            shared = [key for key in rows if key in candidate and key != "total" and not _subtotal(key)]
            matching = sum(
                all(rows[key].values[p] is not None and rows[key].values[p] == candidate[key].values.get(p)
                    for p in periods)
                for key in shared
            )
            if matching >= 2:
                matches.append(candidate)
        if not matches and "$" not in original and not re.search(r"budget|cost", header[0], re.I):
            return original  # A year-by-year table of counts need not be a budget.
        repaired = False
        if len(matches) == 1:
            for key, row in matches[0].items():
                if not any(p in row.values for p in periods):
                    continue
                if key not in rows or any(rows[key].values[p] != row.values.get(p) for p in periods):
                    repaired = True
                rows[key] = _Row(row.label, {p: row.values.get(p) for p in periods})

        details = [row for key, row in rows.items() if key != "total" and not _subtotal(key)]
        if not details:
            return original
        sums = {
            p: sum((row.values[p] for row in details), Decimal(0))
            if all(row.values[p] is not None for row in details) else None
            for p in periods
        }
        differences = {
            p: rows["total"].values[p] - sums[p]
            if sums[p] is not None and rows["total"].values[p] is not None else None
            for p in periods
        }
        mismatch = any(difference is None or difference != 0 for difference in differences.values())
        if not repaired and not mismatch:
            return original
        output = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
        for key, row in rows.items():
            if key != "total":
                label = row.label + (" (subtotal; not added again)" if _subtotal(row.label) else "")
                output.append("| " + " | ".join([label, *(_amount(row.values[p]) for p in periods)]) + " |")
        output.append("| " + " | ".join([
            "Reported total" if mismatch else "Total", *(_amount(rows["total"].values[p]) for p in periods),
        ]) + " |")
        if mismatch:
            output.append("\nThe listed categories do not reconcile with the reported total. "
                          "Missing amounts are not treated as zero; check the source budget before using this breakdown.")
        return "\n".join(output) + ("\n" if original.endswith("\n") else "")

    return _TABLE.sub(reconcile, answer)
