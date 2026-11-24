"""Cross-field validation rules for extraction results.

Validator returns a tri-state status per rule:
    "pass"        — rule's premise was satisfied by the data
    "fail"        — rule's premise was contradicted by the data (a real violation)
    "unparseable" — required field(s) couldn't be parsed; rule can't be evaluated

The optimizer and quality score treat "unparseable" as neutral (does not count
as a violation), because penalizing the model for our parser's blind spots
creates false-alarm pressure.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.utils.code_sandbox import validate_sandbox_code
from app.utils.code_sandbox_runner import execute_sandboxed_code

logger = logging.getLogger(__name__)


_PARENS_NEGATIVE_PATTERN = re.compile(r"^\((.+)\)$")

_SCALES = {
    "k": Decimal(1_000), "thousand": Decimal(1_000),
    "m": Decimal(1_000_000), "mm": Decimal(1_000_000),
    "mil": Decimal(1_000_000), "million": Decimal(1_000_000),
    "b": Decimal(1_000_000_000), "bn": Decimal(1_000_000_000),
    "billion": Decimal(1_000_000_000),
}

# One amount: optional sign/currency, digits (with or without thousands
# commas), optional scale word or letter, optional percent. The scale must end
# at a word boundary so "5 months" isn't read as five million.
_AMOUNT_PATTERN = re.compile(
    r"(?P<neg>[-−])?\s*(?P<cur>[$€£])?\s*(?P<neg2>[-−])?\s*"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
    r"(?:\s*(?P<scale>thousand|million|billion|mil|bn|mm|k|m|b)\b\.?)?"
    r"\s*(?P<pct>%|percent\b)?",
    re.IGNORECASE,
)
_RANGE_SEPARATOR = re.compile(r"^\s*(?:-|–|—|to|through)\s*$", re.IGNORECASE)
_CURRENCY_ALIASES = {
    "usd": "USD", "dollar": "USD", "dollars": "USD",
    "eur": "EUR", "euro": "EUR", "euros": "EUR",
    "gbp": "GBP", "pound": "GBP", "pounds": "GBP",
    "cad": "CAD", "aud": "AUD", "nzd": "NZD", "jpy": "JPY",
    "chf": "CHF", "cny": "CNY", "inr": "INR",
}
_CURRENCY_WORDS = re.compile(r"\b(?:" + "|".join(_CURRENCY_ALIASES) + r")\b", re.IGNORECASE)
_COUNT_UNITS = re.compile(r"\b(?:days?|weeks?|months?|years?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedNumber:
    """An exact amount and its unit ("currency", "percent" or None)."""

    value: Decimal
    unit: Optional[str] = None
    currency: Optional[str] = None


def parse_number(value: Any) -> tuple[Optional[ParsedNumber], Optional[str]]:
    """Parse one exact amount, or say why the value isn't one.

    Returns ``(parsed, None)`` or ``(None, reason)``. Handles ints/floats,
    "$1,200.50", "12%", accounting negatives "(1,200)", money scales ("$500K",
    "$1.2 million", "1.5M"). Approximate amounts, inequalities, unsupported
    qualifiers/scales, a range ("10-20%"), or several numbers are not
    one amount and is rejected rather than replaced by a guess such as the
    midpoint.
    """
    if isinstance(value, bool) or value is None:
        return None, None
    if isinstance(value, (int, float, Decimal)):
        try:
            number = Decimal(str(value))
            if not number.is_finite():
                return None, "is not a finite amount"
            return ParsedNumber(number), None
        except InvalidOperation:
            return None, None
    if not isinstance(value, str):
        return None, None
    s = value.strip()
    if not s:
        return None, None

    m = _PARENS_NEGATIVE_PATTERN.match(s)
    if m:
        inner, reason = parse_number(m.group(1))
        if inner is None:
            return None, reason
        if inner.value < 0:
            return None, "contains conflicting negative signs"
        return ParsedNumber(-inner.value, inner.unit, inner.currency), None

    matches = list(_AMOUNT_PATTERN.finditer(s))
    if not matches:
        return None, None
    if len(matches) > 1:
        # The second amount's sign group swallows a hyphen separator
        # ("10-15", "$100-$200"), so measure up to its currency or digits.
        second = matches[1]
        body_start = min(
            second.start(g) for g in ("cur", "neg2", "num") if second.group(g)
        )
        between = s[matches[0].end():body_start]
        if len(matches) == 2 and _RANGE_SEPARATOR.match(between):
            return None, "is a range, not a single amount"
        return None, "contains more than one number"

    match = matches[0]
    if match.group("neg") and match.group("neg2"):
        return None, "contains conflicting negative signs"
    currencies = {_CURRENCY_ALIASES[m.group(0).lower()] for m in _CURRENCY_WORDS.finditer(s)}
    symbol = match.group("cur")
    if symbol:
        # Written dollar codes qualify '$'; no implicit FX conversion.
        if symbol != "$" or not currencies:
            currencies.add({"$": "USD", "€": "EUR", "£": "GBP"}[symbol])
        elif not currencies <= {"USD", "CAD", "AUD", "NZD"}:
            return None, "contains conflicting currency labels"
    if len(currencies) > 1:
        return None, "contains conflicting currency labels"
    remainder = _CURRENCY_WORDS.sub("", s[:match.start()] + s[match.end():])
    count_units = {m.group(0).lower().rstrip("s") for m in _COUNT_UNITS.finditer(remainder)}
    remainder = _COUNT_UNITS.sub("", remainder)
    if remainder.strip(" \t\r\n."):
        return None, "contains an unsupported scale, unit, or qualifier; give one exact amount"
    if len(count_units) > 1 or (count_units and (currencies or match.group("pct"))):
        return None, "contains conflicting units"
    try:
        number = Decimal(match.group("num").replace(",", ""))
    except InvalidOperation:
        return None, None
    scale = match.group("scale")
    if scale:
        number *= _SCALES[scale.lower()]
    if match.group("neg") or match.group("neg2"):
        number = -number

    unit = None
    if match.group("pct"):
        if currencies:
            return None, "contains conflicting units"
        unit = "percent"
    elif currencies:
        unit = "currency"
    elif count_units:
        unit = next(iter(count_units))
    return ParsedNumber(number, unit, next(iter(currencies), None)), None


def _numeric_rule_error(data: dict, rule: dict) -> Optional[str]:
    """Reject invalid numeric configuration and implicit currency conversions."""
    field_keys = {
        "sum_equals": ("target_field",),
        "range_check": ("field",),
        "product_equals": ("base_field", "rate_field", "target_field"),
        "at_most_difference": ("field", "minuend_field"),
    }
    kind = rule.get("type")
    if kind not in field_keys:
        return None
    for key in ("tolerance", "min", "max"):
        value = rule.get(key)
        if value is None:
            continue
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            return f"Invalid {key}: {value!r}"
        if not number.is_finite() or (key == "tolerance" and number < 0):
            return f"Invalid {key}: must be finite" + (" and non-negative" if key == "tolerance" else "")
    fields = [rule.get(key) for key in field_keys[kind]]
    fields += list(rule.get("source_fields") or []) + list(rule.get("subtrahend_fields") or [])
    currencies = set()
    for field in fields:
        if not field:
            continue
        parsed, _ = parse_number(_get_field_value(data, field))
        if parsed and parsed.currency:
            currencies.add(parsed.currency)
    if len(currencies) > 1:
        return f"Fields mix currencies ({', '.join(sorted(currencies))}); provide amounts in one currency"
    return None


def _try_parse_number(value: Any) -> Optional[float]:
    """Float form of :func:`parse_number`, for callers that only compare."""
    parsed, _reason = parse_number(value)
    return float(parsed.value) if parsed is not None else None


def _unparseable_number(field: str, value: Any, reason: Optional[str]) -> str:
    if reason:
        return f"Cannot read '{field}' as one amount: {value!r} {reason}"
    return f"Cannot parse '{field}' as number: {value!r}"


def _fmt(d: Decimal) -> str:
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


_DATE_FORMATS = [
    "%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y",
    "%B %d, %Y", "%b %d, %Y", "%Y-%m-%dT%H:%M:%S",
    "%m/%d/%y", "%d-%b-%Y",
]


def _try_parse_date(value: Any) -> Optional[datetime]:
    """Try to parse a date from common formats, with dateutil as a fallback.

    The strict format list is tried first so behavior is predictable for
    canonical inputs. dateutil handles wider variants ("Jan 2026",
    "2026 Jan 15", etc.). Truly free-form values ("Q1 2026", "TBD") return
    None — caller should treat that as "unparseable", not as a violation.
    """
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        from dateutil import parser as dateutil_parser
        return dateutil_parser.parse(s, fuzzy=False)
    except (ValueError, OverflowError, ImportError):
        return None


def _get_field_value(data: dict, field_name: str) -> Any:
    """Get a field value from extraction results, checking case-insensitively."""
    if field_name in data:
        return data[field_name]
    lower = field_name.lower()
    for key, val in data.items():
        if key.lower() == lower:
            return val
    return None


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


_MISSING_WORDS = {"n/a", "na", "none", "not applicable", "not found", "-", "–", "—"}


def _assumed_zero_note(fields: list[str]) -> str:
    if not fields:
        return ""
    return f"; counted as 0 because not stated: {', '.join(fields)}"


def _result(rule: dict, status: str, message: str, **extra: object) -> dict:
    """Build a result dict. Includes `passed` for backward compatibility.

    ``extra`` carries optional detail: ``assumed_zero`` (fields counted as 0
    because the document didn't state them) and ``computed`` (the value the
    rule calculated), so a reader can see what the check rested on.
    """
    passed = status == "pass"
    extra = {k: v for k, v in extra.items() if v not in (None, [], "")}
    return {
        **extra,
        "rule": rule,
        "rule_id": rule.get("id"),
        "status": status,  # "pass" | "fail" | "unparseable"
        "passed": passed,
        "message": message,
    }


class CrossFieldValidator:
    """Validates cross-field rules against extraction results.

    Each rule returns {rule, rule_id, status, passed, message}. The optimizer
    and quality score should compute violation rate as fails / (pass + fail),
    excluding unparseable from both numerator and denominator.
    """

    def validate(self, data: dict, rules: list[dict]) -> list[dict]:
        """Run all rules against data. Returns list of result dicts.

        Skips disabled rules (rule.get("enabled") is False, or auto_disabled).
        """
        results = []
        for rule in rules:
            if rule.get("enabled") is False or rule.get("auto_disabled"):
                continue
            rule_type = rule.get("type", "")
            handler = getattr(self, f"_validate_{rule_type}", None)
            if not handler:
                results.append(_result(rule, "unparseable", f"Unknown rule type: {rule_type}"))
                continue
            try:
                numeric_error = _numeric_rule_error(data, rule)
                result = _result(rule, "unparseable", numeric_error) if numeric_error else handler(data, rule)
                results.append(result)
            except Exception as e:
                logger.warning("Cross-field rule %s evaluation error: %s", rule.get("id"), e)
                results.append(_result(rule, "unparseable", f"Rule evaluation error: {e}"))
        return results

    def _read_amounts(
        self, data: dict, rule: dict, fields: list[str], role: str,
    ) -> tuple[Optional[list[ParsedNumber]], list[str], Optional[dict]]:
        """Parse each field as one amount: ``(amounts, assumed_zero, None)`` or
        ``(None, [], unparseable_result)``.

        With ``missing_as_zero`` on the rule, a field that is empty or says
        "N/A"/"none" counts as 0 and is listed in ``assumed_zero`` so the
        result can say which zeros were assumed rather than read.
        """
        missing_as_zero = bool(rule.get("missing_as_zero"))
        amounts: list[ParsedNumber] = []
        assumed_zero: list[str] = []
        for field in fields:
            val = _get_field_value(data, field)
            if _is_empty(val) or (
                isinstance(val, str) and val.strip().lower() in _MISSING_WORDS
            ):
                if missing_as_zero:
                    assumed_zero.append(field)
                    amounts.append(ParsedNumber(Decimal(0)))
                    continue
                return None, [], _result(rule, "unparseable", f"{role} field '{field}' is empty")
            num, reason = parse_number(val)
            if num is None:
                return None, [], _result(rule, "unparseable", _unparseable_number(field, val, reason))
            amounts.append(num)
        return amounts, assumed_zero, None

    @staticmethod
    def _tolerance(rule: dict, default: str) -> Optional[Decimal]:
        try:
            return Decimal(str(rule.get("tolerance", default)))
        except InvalidOperation:
            return None

    @staticmethod
    def _mixed_units(rule: dict, amounts: list[ParsedNumber]) -> Optional[dict]:
        units = {p.unit for p in amounts if p.unit}
        if len(units) > 1:
            return _result(
                rule, "unparseable",
                f"Fields mix units ({', '.join(sorted(units))}); they can't be combined",
            )
        return None

    def _validate_sum_equals(self, data: dict, rule: dict) -> dict:
        """Check that source fields sum to target field value."""
        source_fields = list(rule.get("source_fields", []))
        target_field = rule.get("target_field", "")
        tolerance = self._tolerance(rule, "0.01")
        if tolerance is None:
            return _result(rule, "unparseable", f"Invalid tolerance: {rule.get('tolerance')!r}")

        parsed, assumed_zero, error = self._read_amounts(data, rule, source_fields, "Source")
        if error:
            return error
        assert parsed is not None
        target_val = _get_field_value(data, target_field)
        if _is_empty(target_val):
            return _result(rule, "unparseable", f"Target field '{target_field}' is empty")
        target, reason = parse_number(target_val)
        if target is None:
            return _result(rule, "unparseable", _unparseable_number(target_field, target_val, reason))
        error = self._mixed_units(rule, [*parsed, target])
        if error:
            return error

        total = sum((p.value for p in parsed), Decimal(0))
        difference = abs(total - target.value)
        detail = (
            f"Sum of {source_fields} = {_fmt(total)}, target '{target_field}' = "
            f"{_fmt(target.value)} (tolerance {_fmt(tolerance)})"
        )
        detail += _assumed_zero_note(assumed_zero)
        status = "pass" if difference <= tolerance else "fail"
        if status == "fail":
            detail += f"; difference {_fmt(difference)}"
        return _result(rule, status, detail, assumed_zero=assumed_zero, computed=_fmt(total))

    def _validate_product_equals(self, data: dict, rule: dict) -> dict:
        """Check that ``target_field`` equals ``base_field`` × ``rate_field``.

        For a rate applied to a base, such as indirect costs = F&A rate × MTDC
        base. A rate written with % (or a bare number over 1, e.g. "55.5") is a
        percentage; a bare number up to 1 is a fraction. The default tolerance
        is $1, for rounding to whole dollars.
        """
        base_field = rule.get("base_field", "")
        rate_field = rule.get("rate_field", "")
        target_field = rule.get("target_field", "")
        tolerance = self._tolerance(rule, "1")
        if tolerance is None:
            return _result(rule, "unparseable", f"Invalid tolerance: {rule.get('tolerance')!r}")
        amounts, _assumed, error = self._read_amounts(
            data, {**rule, "missing_as_zero": False},
            [base_field, rate_field, target_field], "Input",
        )
        if error:
            return error
        assert amounts is not None
        base, rate, target = amounts
        if rate.unit == "currency":
            return _result(rule, "unparseable", f"'{rate_field}' is a dollar amount, not a rate")
        error = self._mixed_units(rule, [base, target])
        if error:
            return error
        rate_note = ""
        if rate.unit == "percent":
            factor = rate.value / 100
        elif rate.value > 1:
            factor = rate.value / 100
            rate_note = f" ('{rate_field}' has no % sign; read as {_fmt(rate.value)}%)"
        else:
            factor = rate.value
        expected = base.value * factor
        difference = abs(expected - target.value)
        detail = (
            f"{_fmt(base.value)} × {_fmt(factor * 100)}% = {_fmt(expected.quantize(Decimal('0.01')))}, "
            f"target '{target_field}' = {_fmt(target.value)} (tolerance {_fmt(tolerance)}){rate_note}"
        )
        status = "pass" if difference <= tolerance else "fail"
        if status == "fail":
            detail += f"; difference {_fmt(difference.quantize(Decimal('0.01')))}"
        return _result(rule, status, detail, computed=_fmt(expected.quantize(Decimal("0.01"))))

    def _validate_at_most_difference(self, data: dict, rule: dict) -> dict:
        """Check that ``field`` ≤ ``minuend_field`` − sum(``subtrahend_fields``).

        An upper bound, not an equation: e.g. an MTDC base can be no more than
        total direct costs less equipment and participant support. Passing says
        the value is consistent with those exclusions, not that it is right.
        """
        field = rule.get("field", "")
        minuend_field = rule.get("minuend_field", "")
        subtrahends = list(rule.get("subtrahend_fields", []))
        tolerance = self._tolerance(rule, "0.01")
        if tolerance is None:
            return _result(rule, "unparseable", f"Invalid tolerance: {rule.get('tolerance')!r}")
        head, _a, error = self._read_amounts(
            data, {**rule, "missing_as_zero": False}, [field, minuend_field], "Input",
        )
        if error:
            return error
        assert head is not None
        minus, assumed_zero, error = self._read_amounts(data, rule, subtrahends, "Subtracted")
        if error:
            return error
        assert minus is not None
        value, minuend = head
        error = self._mixed_units(rule, [value, minuend, *minus])
        if error:
            return error
        bound = minuend.value - sum((p.value for p in minus), Decimal(0))
        detail = (
            f"'{field}' = {_fmt(value.value)}; '{minuend_field}' less "
            f"{subtrahends} = {_fmt(bound)}"
        )
        detail += _assumed_zero_note(assumed_zero)
        if value.value <= bound + tolerance:
            return _result(
                rule, "pass", detail + " (within the bound; this does not confirm the value)",
                assumed_zero=assumed_zero, computed=_fmt(bound),
            )
        return _result(
            rule, "fail", f"{detail}; exceeds the bound by {_fmt(value.value - bound)}",
            assumed_zero=assumed_zero, computed=_fmt(bound),
        )

    def _validate_conditional_required(self, data: dict, rule: dict) -> dict:
        """If field A = value, field B must exist."""
        condition_field = rule.get("condition_field", "")
        condition_value = rule.get("condition_value", "")
        required_field = rule.get("required_field", "")

        actual = _get_field_value(data, condition_field)
        if _is_empty(actual):
            return _result(rule, "unparseable", f"Condition field '{condition_field}' is empty")
        if str(actual).lower().strip() != str(condition_value).lower().strip():
            return _result(
                rule, "pass",
                f"Condition not met ('{condition_field}' != '{condition_value}'), rule skipped",
            )

        required_val = _get_field_value(data, required_field)
        if not _is_empty(required_val):
            return _result(
                rule, "pass",
                f"'{condition_field}' = '{condition_value}', '{required_field}' is present",
            )
        return _result(
            rule, "fail",
            f"'{condition_field}' = '{condition_value}', but '{required_field}' is missing",
        )

    def _validate_range_check(self, data: dict, rule: dict) -> dict:
        """Check that a numeric field is within min/max."""
        field = rule.get("field", "")
        min_val = rule.get("min")
        max_val = rule.get("max")

        val = _get_field_value(data, field)
        if _is_empty(val):
            return _result(rule, "unparseable", f"'{field}' is empty")
        parsed, reason = parse_number(val)
        if parsed is None:
            return _result(rule, "unparseable", _unparseable_number(field, val, reason))
        num = parsed.value

        if min_val is not None and num < Decimal(str(min_val)):
            return _result(rule, "fail", f"'{field}' = {_fmt(num)} below min {min_val}")
        if max_val is not None and num > Decimal(str(max_val)):
            return _result(rule, "fail", f"'{field}' = {_fmt(num)} above max {max_val}")
        return _result(rule, "pass", f"'{field}' = {_fmt(num)}, in range [{min_val}, {max_val}]")

    def _validate_cross_reference(self, data: dict, rule: dict) -> dict:
        """Check that field A matches/contains field B."""
        field_a = rule.get("field_a", "")
        field_b = rule.get("field_b", "")
        match_type = rule.get("match_type", "contains")  # contains | equals

        raw_a = _get_field_value(data, field_a)
        raw_b = _get_field_value(data, field_b)
        if _is_empty(raw_a) or _is_empty(raw_b):
            return _result(rule, "unparseable", f"'{field_a}' or '{field_b}' is empty")

        val_a = str(raw_a).lower().strip()
        val_b = str(raw_b).lower().strip()

        if match_type == "equals":
            passed = val_a == val_b
        else:
            passed = val_b in val_a or val_a in val_b

        if passed:
            return _result(rule, "pass", f"'{field_a}' vs '{field_b}': {match_type} check passed")
        return _result(rule, "fail", f"'{field_a}' vs '{field_b}': {match_type} check failed")

    def _validate_date_order(self, data: dict, rule: dict) -> dict:
        """Check that field A date is before field B date."""
        field_a = rule.get("field_a", "")
        field_b = rule.get("field_b", "")

        val_a = _get_field_value(data, field_a)
        val_b = _get_field_value(data, field_b)
        if _is_empty(val_a) or _is_empty(val_b):
            return _result(rule, "unparseable", f"'{field_a}' or '{field_b}' is empty")

        date_a = _try_parse_date(val_a)
        date_b = _try_parse_date(val_b)

        if date_a is None:
            return _result(rule, "unparseable", f"Cannot parse '{field_a}' as date: {val_a!r}")
        if date_b is None:
            return _result(rule, "unparseable", f"Cannot parse '{field_b}' as date: {val_b!r}")

        if date_a <= date_b:
            return _result(rule, "pass", f"'{field_a}' ({date_a.date()}) <= '{field_b}' ({date_b.date()})")
        return _result(rule, "fail", f"'{field_a}' ({date_a.date()}) > '{field_b}' ({date_b.date()})")

    def _validate_custom_expression(self, data: dict, rule: dict) -> dict:
        """Evaluate a simple Python expression using the workflow sandbox."""
        expression = rule.get("expression", "")
        if not expression:
            return _result(rule, "unparseable", "No expression provided")

        sandbox_data = {}
        variable_names = []
        for key, value in data.items():
            safe_key = re.sub(r"[^a-zA-Z0-9_]", "_", key)
            num = _try_parse_number(value)
            sandbox_data[safe_key] = num if num is not None else value
            variable_names.append(safe_key)

        prelude = "\n".join(f"{name} = data[{name!r}]" for name in variable_names)
        code = f"{prelude}\nresult = bool({expression})" if prelude else f"result = bool({expression})"

        try:
            validate_sandbox_code(code)
        except Exception as e:
            return _result(rule, "unparseable", f"Expression error: {e}")

        result = execute_sandboxed_code(code, sandbox_data, timeout=5)
        if result.get("timed_out"):
            return _result(rule, "unparseable", "Expression evaluation timed out (5s limit)")
        if "error" in result:
            return _result(rule, "unparseable", f"Expression error: {result['error']}")

        status = "pass" if bool(result.get("result")) else "fail"
        return _result(rule, status, f"Expression '{expression}' evaluated to {result.get('result')}")


def summarize_results(results: list[dict]) -> dict:
    """Roll up a list of per-rule results into pass/fail/unparseable counts
    and a `violation_rate` ∈ [0,1] suitable for plugging into a score.

    violation_rate = fail / (pass + fail). Unparseable results don't count in
    either direction, so a rule that the parser can't evaluate doesn't drag
    the score down.
    """
    counts = {"pass": 0, "fail": 0, "unparseable": 0}
    for r in results:
        counts[r.get("status", "unparseable")] = counts.get(r.get("status", "unparseable"), 0) + 1
    decisive = counts["pass"] + counts["fail"]
    violation_rate = counts["fail"] / decisive if decisive > 0 else 0.0
    pass_rate = counts["pass"] / decisive if decisive > 0 else None
    return {
        "pass": counts["pass"],
        "fail": counts["fail"],
        "unparseable": counts["unparseable"],
        "violation_rate": violation_rate,
        "pass_rate": pass_rate,
        "total": len(results),
    }
