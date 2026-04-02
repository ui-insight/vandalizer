"""Cross-field validation rules for extraction results."""

import logging
import re
from datetime import datetime
from typing import Optional

from app.utils.code_sandbox import validate_sandbox_code
from app.utils.code_sandbox_runner import execute_sandboxed_code

logger = logging.getLogger(__name__)


def _try_parse_number(value: object) -> Optional[float]:
    """Try to parse a numeric value from various formats."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"[,$\s%]", "", value.strip())
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _try_parse_date(value: object) -> Optional[datetime]:
    """Try to parse a date from common formats."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    formats = [
        "%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y",
        "%B %d, %Y", "%b %d, %Y", "%Y-%m-%dT%H:%M:%S",
        "%m/%d/%y", "%d-%b-%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def _get_field_value(data: dict, field_name: str) -> object:
    """Get a field value from extraction results, checking nested structures."""
    if field_name in data:
        return data[field_name]
    # Check case-insensitive
    lower = field_name.lower()
    for key, val in data.items():
        if key.lower() == lower:
            return val
    return None


class CrossFieldValidator:
    """Validates cross-field rules against extraction results."""

    def validate(self, data: dict, rules: list[dict]) -> list[dict]:
        """Run all rules against data. Returns list of result dicts."""
        results = []
        for rule in rules:
            rule_type = rule.get("type", "")
            handler = getattr(self, f"_validate_{rule_type}", None)
            if not handler:
                results.append({
                    "rule": rule,
                    "passed": False,
                    "message": f"Unknown rule type: {rule_type}",
                })
                continue
            try:
                result = handler(data, rule)
                results.append(result)
            except Exception as e:
                results.append({
                    "rule": rule,
                    "passed": False,
                    "message": f"Rule evaluation error: {e}",
                })
        return results

    def _validate_sum_equals(self, data: dict, rule: dict) -> dict:
        """Check that source fields sum to target field value."""
        source_fields = rule.get("source_fields", [])
        target_field = rule.get("target_field", "")
        tolerance = float(rule.get("tolerance", 0.01))

        source_values = []
        for field in source_fields:
            val = _get_field_value(data, field)
            num = _try_parse_number(val)
            if num is None:
                return {
                    "rule": rule,
                    "passed": False,
                    "message": f"Cannot parse '{field}' as number: {val}",
                }
            source_values.append(num)

        target_val = _get_field_value(data, target_field)
        target_num = _try_parse_number(target_val)
        if target_num is None:
            return {
                "rule": rule,
                "passed": False,
                "message": f"Cannot parse target '{target_field}' as number: {target_val}",
            }

        total = sum(source_values)
        passed = abs(total - target_num) <= tolerance
        return {
            "rule": rule,
            "passed": passed,
            "message": f"Sum of {source_fields} = {total}, target '{target_field}' = {target_num}"
            + ("" if passed else f" (difference: {abs(total - target_num):.4f})"),
        }

    def _validate_conditional_required(self, data: dict, rule: dict) -> dict:
        """If field A = value, field B must exist."""
        condition_field = rule.get("condition_field", "")
        condition_value = rule.get("condition_value", "")
        required_field = rule.get("required_field", "")

        actual = _get_field_value(data, condition_field)
        if str(actual).lower().strip() == str(condition_value).lower().strip():
            required_val = _get_field_value(data, required_field)
            passed = required_val is not None and str(required_val).strip() != ""
            return {
                "rule": rule,
                "passed": passed,
                "message": f"'{condition_field}' = '{condition_value}', "
                + (f"'{required_field}' is present" if passed else f"'{required_field}' is missing"),
            }
        return {
            "rule": rule,
            "passed": True,
            "message": f"Condition not met ('{condition_field}' != '{condition_value}'), rule skipped",
        }

    def _validate_range_check(self, data: dict, rule: dict) -> dict:
        """Check that a numeric field is within min/max."""
        field = rule.get("field", "")
        min_val = rule.get("min")
        max_val = rule.get("max")

        val = _get_field_value(data, field)
        num = _try_parse_number(val)
        if num is None:
            return {
                "rule": rule,
                "passed": False,
                "message": f"Cannot parse '{field}' as number: {val}",
            }

        passed = True
        if min_val is not None and num < float(min_val):
            passed = False
        if max_val is not None and num > float(max_val):
            passed = False

        return {
            "rule": rule,
            "passed": passed,
            "message": f"'{field}' = {num}, range [{min_val}, {max_val}]"
            + ("" if passed else " — out of range"),
        }

    def _validate_cross_reference(self, data: dict, rule: dict) -> dict:
        """Check that field A matches/contains field B."""
        field_a = rule.get("field_a", "")
        field_b = rule.get("field_b", "")
        match_type = rule.get("match_type", "contains")  # contains | equals

        val_a = str(_get_field_value(data, field_a) or "").lower().strip()
        val_b = str(_get_field_value(data, field_b) or "").lower().strip()

        if match_type == "equals":
            passed = val_a == val_b
        else:
            passed = val_b in val_a or val_a in val_b

        return {
            "rule": rule,
            "passed": passed,
            "message": f"'{field_a}' vs '{field_b}': {match_type} check {'passed' if passed else 'failed'}",
        }

    def _validate_date_order(self, data: dict, rule: dict) -> dict:
        """Check that field A date is before field B date."""
        field_a = rule.get("field_a", "")
        field_b = rule.get("field_b", "")

        val_a = _get_field_value(data, field_a)
        val_b = _get_field_value(data, field_b)

        date_a = _try_parse_date(val_a)
        date_b = _try_parse_date(val_b)

        if date_a is None:
            return {"rule": rule, "passed": False, "message": f"Cannot parse '{field_a}' as date: {val_a}"}
        if date_b is None:
            return {"rule": rule, "passed": False, "message": f"Cannot parse '{field_b}' as date: {val_b}"}

        passed = date_a <= date_b
        return {
            "rule": rule,
            "passed": passed,
            "message": f"'{field_a}' ({date_a.date()}) {'<=' if passed else '>'} '{field_b}' ({date_b.date()})",
        }

    def _validate_custom_expression(self, data: dict, rule: dict) -> dict:
        """Evaluate a simple Python expression using the workflow sandbox."""
        expression = rule.get("expression", "")
        if not expression:
            return {"rule": rule, "passed": False, "message": "No expression provided"}

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
            return {"rule": rule, "passed": False, "message": f"Expression error: {e}"}

        result = execute_sandboxed_code(code, sandbox_data, timeout=5)
        if result.get("timed_out"):
            return {"rule": rule, "passed": False, "message": "Expression evaluation timed out (5s limit)"}
        if "error" in result:
            return {"rule": rule, "passed": False, "message": f"Expression error: {result['error']}"}

        passed = bool(result.get("result"))

        return {
            "rule": rule,
            "passed": passed,
            "message": f"Expression '{expression}' evaluated to {result.get('result')}",
        }
