"""Rule schema, normalization, counter updates, and suggestions for
cross-field validation.

Rules are persisted on `SearchSet.cross_field_rules` as plain dicts
(MongoDB-friendly, backward compatible with the legacy unstructured form).
This module is the single place that knows the rule shape.

Persisted shape:
    {
        "id": "<uuid>",                # stable identifier, used for FP marking
        "type": "<rule_type>",         # sum_equals | range_check | ...
        "enabled": True,
        "auto_disabled": False,        # set true when fp_rate crosses threshold
        "auto_disabled_reason": "...", # human-readable explanation
        "eval_count": 0,               # times the rule reached a pass/fail verdict
        "pass_count": 0,
        "fail_count": 0,
        "fp_count": 0,                 # user-marked false positives
        "source": "user" | "suggested" | "imported",
        # plus the type-specific params (source_fields, target_field, etc.)
    }
"""

from __future__ import annotations

import re
import uuid

from app.models.search_set import SearchSet

# Rule types known to the validator. Anything else falls through as unparseable.
RULE_TYPES = {
    "sum_equals",
    "conditional_required",
    "range_check",
    "cross_reference",
    "date_order",
    "custom_expression",
}

# Auto-demotion thresholds. A rule that the user has marked as a false positive
# at least FP_THRESHOLD_MIN_EVALS times AND whose fp_count/eval_count exceeds
# FP_THRESHOLD_RATE gets auto_disabled — it will stop being evaluated until the
# user fixes or re-enables it.
FP_THRESHOLD_MIN_EVALS = 5
FP_THRESHOLD_RATE = 0.3


def normalize_rule(rule: dict) -> dict:
    """Stamp defaults onto a rule dict so callers can rely on every counter
    field being present. Mutates and returns the input.

    Existing rules in MongoDB may lack id/counters — normalize_rule fills
    those in on load, and save() persists the result so future loads are
    no-ops.
    """
    if not rule.get("id"):
        rule["id"] = str(uuid.uuid4())
    rule.setdefault("enabled", True)
    rule.setdefault("auto_disabled", False)
    rule.setdefault("auto_disabled_reason", None)
    rule.setdefault("eval_count", 0)
    rule.setdefault("pass_count", 0)
    rule.setdefault("fail_count", 0)
    rule.setdefault("fp_count", 0)
    rule.setdefault("source", "user")
    return rule


def normalize_rules(rules: list[dict]) -> list[dict]:
    return [normalize_rule(dict(r)) for r in (rules or [])]


def validate_rule_shape(rule: dict) -> tuple[bool, str]:
    """Quick shape check before persisting. Returns (ok, error_message).

    Doesn't try to be exhaustive — the validator gracefully degrades on
    malformed rules at evaluation time — but rejects obviously bad inputs
    so the UI gets immediate feedback.
    """
    rule_type = rule.get("type")
    if rule_type not in RULE_TYPES:
        return False, f"Unknown rule type: {rule_type}"
    if rule_type == "sum_equals":
        if not rule.get("source_fields") or not rule.get("target_field"):
            return False, "sum_equals requires source_fields and target_field"
    elif rule_type == "conditional_required":
        if not rule.get("condition_field") or not rule.get("required_field"):
            return False, "conditional_required requires condition_field and required_field"
    elif rule_type == "range_check":
        if not rule.get("field"):
            return False, "range_check requires field"
        if rule.get("min") is None and rule.get("max") is None:
            return False, "range_check requires at least one of min or max"
    elif rule_type == "cross_reference":
        if not rule.get("field_a") or not rule.get("field_b"):
            return False, "cross_reference requires field_a and field_b"
    elif rule_type == "date_order":
        if not rule.get("field_a") or not rule.get("field_b"):
            return False, "date_order requires field_a and field_b"
    elif rule_type == "custom_expression":
        if not rule.get("expression"):
            return False, "custom_expression requires expression"
    return True, ""


def apply_evaluation_counters(rules: list[dict], results: list[dict]) -> bool:
    """Update eval/pass/fail counters in-place based on a list of result dicts.

    Returns True if any rule was modified (so the caller knows to persist).
    Results with status="unparseable" don't count — see cross_field_validation
    module docstring for rationale.
    """
    changed = False
    by_id = {r.get("id"): r for r in rules if r.get("id")}
    for res in results:
        rule_id = res.get("rule_id")
        if not rule_id or rule_id not in by_id:
            continue
        status = res.get("status")
        if status not in ("pass", "fail"):
            continue
        rule = by_id[rule_id]
        rule["eval_count"] = int(rule.get("eval_count", 0)) + 1
        if status == "pass":
            rule["pass_count"] = int(rule.get("pass_count", 0)) + 1
        else:
            rule["fail_count"] = int(rule.get("fail_count", 0)) + 1
        changed = True
    return changed


def apply_false_positive(rules: list[dict], rule_id: str) -> tuple[bool, dict | None]:
    """Increment fp_count for the named rule and auto-demote if the threshold
    is crossed. Returns (changed, rule_after).
    """
    for rule in rules:
        if rule.get("id") != rule_id:
            continue
        rule["fp_count"] = int(rule.get("fp_count", 0)) + 1
        evals = int(rule.get("eval_count", 0))
        fps = int(rule.get("fp_count", 0))
        if evals >= FP_THRESHOLD_MIN_EVALS and (fps / evals) > FP_THRESHOLD_RATE:
            rule["auto_disabled"] = True
            rule["auto_disabled_reason"] = (
                f"Marked as false positive {fps} of {evals} evaluations "
                f"({(fps / evals) * 100:.0f}%)"
            )
        return True, rule
    return False, None


async def persist_rules(ss: SearchSet, rules: list[dict]) -> None:
    """Save rules onto a SearchSet, ensuring every rule has been normalized."""
    ss.cross_field_rules = normalize_rules(rules)
    await ss.save()


# ---------------------------------------------------------------------------
# Rule suggester
# ---------------------------------------------------------------------------

_TOTAL_TOKENS = {"total", "sum", "amount", "subtotal"}
_PART_TOKENS = {"subtotal", "direct", "indirect", "labor", "materials", "supplies",
                "travel", "equipment", "fringe", "tax"}
# Tokens stripped when deriving a field's "category stem" — markers that
# distinguish line items of the same category (Year 1 / Year 2 / Total) without
# changing which category they belong to.
_STEM_STRIP_TOKENS = {"total", "sum", "amount", "subtotal", "grand", "gross", "net",
                      "year", "yr", "fy", "fiscal", "quarter", "qtr", "period"}
_NUMBER_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight",
                 "nine", "ten", "eleven", "twelve",
                 "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
                 "eighth", "ninth", "tenth"}
_DATE_PAIRS = [
    ({"start", "begin", "from"}, {"end", "finish", "to", "thru", "through"}),
    ({"effective"}, {"expiration", "expiry", "expire"}),
    ({"issue", "issued"}, {"due"}),
]
_PERCENT_TOKENS = {"percent", "percentage", "rate", "%"}
# Name tokens that mark a field as free-text / categorical, so it must never be
# pulled into a numeric sum_equals — even when another token in the name looks
# part-like. E.g. "Educational Materials Target Audience" matches the part token
# "materials" but is plainly text, caught here by "audience". This is the
# name-only fallback; a data-driven `is_numeric` signal (when present) wins.
_TEXT_TOKENS = {"audience", "name", "title", "description", "summary", "purpose",
                "objective", "scope", "comment", "comments", "note", "notes",
                "type", "category", "status", "address", "email", "phone",
                "narrative", "abstract", "keywords", "discipline", "department",
                "investigator", "contact", "institution", "sponsor", "program",
                "country", "state", "city", "url", "website"}


def _tokens(name: str) -> set[str]:
    return set(re.findall(r"[a-z]+", name.lower()))


def _is_numeric_field(field_meta: dict) -> bool:
    """Whether a field may participate in a numeric sum_equals rule.

    A text field summed into a numeric total can never be parsed, so every such
    evaluation is dropped as "unparseable" and silently erodes the pass rate —
    exactly the ticket symptom. We gate operands here instead of trusting field
    names alone.

    Prefers a data-driven signal: `is_numeric` is stamped onto the metadata by
    the caller from sampled extracted values (see
    ``search_set_service.infer_numeric_fields``). When that signal is absent
    (field never validated), fall back to name/enum heuristics so we still avoid
    the obvious mistakes — enumerated/categorical fields and text-named fields
    like "... Target Audience".
    """
    is_numeric = field_meta.get("is_numeric")
    if is_numeric is True:
        return True
    if is_numeric is False:
        return False
    # Unknown — fall back to heuristics.
    if field_meta.get("enum_values"):
        return False  # an enumerated/categorical field is not numeric
    return not (_tokens(field_meta.get("key", "")) & _TEXT_TOKENS)


def _is_total(name: str) -> bool:
    """A field whose name marks it as the sum of other fields (a total/subtotal)."""
    return bool(_tokens(name) & _TOTAL_TOKENS)


def _stem(name: str) -> str:
    """Category stem of a field name: the name with total/period markers and
    numbers stripped, so line items of the same category collapse together.

        "Budget Equipment Year 1" -> "budget equipment"
        "Budget Equipment Total"  -> "budget equipment"
        "Budget Travel Year 2"    -> "budget travel"

    This lets the suggester sum a category's components into *its own* total
    instead of mixing categories (and their totals) into one rule.
    """
    out: list[str] = []
    for raw in re.split(r"[^a-z0-9]+", name.lower()):
        if not raw:
            continue
        if raw.isdigit():
            continue
        # Drop a trailing index glued to a label, e.g. "q1" -> "q".
        tok = raw.rstrip("0123456789")
        if not tok or tok in _STEM_STRIP_TOKENS or tok in _NUMBER_WORDS:
            continue
        out.append(tok)
    return " ".join(out)


def suggest_rules(field_metadata: list[dict], existing_rules: list[dict]) -> list[dict]:
    """Propose cross-field rules from field names + enum_values.

    Heuristics — narrow on purpose, since false suggestions train users to
    ignore the suggester:
      1. sum_equals: a field whose name contains a total token AND ≥2 sibling
         fields whose names look like parts.
      2. date_order: pairs of date-named fields matching start/end semantics.
      3. range_check 0..100: fields whose names suggest a percentage.

    Returns rules with `source: "suggested"` and counters at zero. Caller is
    expected to dedupe against existing_rules (same type + same params).
    """
    suggestions: list[dict] = []
    field_names = [f.get("key", "") for f in field_metadata if f.get("key")]

    existing_keys = {_rule_dedupe_key(r) for r in existing_rules}

    # 1. sum_equals
    #
    # A "total" field sums its *own* category's components — never another
    # category's, and never another total. Mixing those double-counts (e.g.
    # Equipment Y1+Y2+Y3 already equals Equipment Total, so a rule that adds
    # both the yearly values and the total is mathematically wrong).
    #
    # Only numeric fields may take part in a sum. A text/categorical field
    # (e.g. "Educational Materials Target Audience") summed into a numeric total
    # produces unparseable evaluations that quietly drag down the pass rate.
    meta_by_name = {f.get("key"): f for f in field_metadata if f.get("key")}
    numeric_names = [n for n in field_names if _is_numeric_field(meta_by_name[n])]

    # Strategy A — structured families: group fields by category stem
    # ("Budget Equipment Year 1/2/3/Total" all share stem "budget equipment").
    # A family with exactly one total and >=2 non-total components yields a
    # clean per-category rule. This is what budget matrices look like.
    families: dict[str, dict[str, list[str]]] = {}
    for n in numeric_names:
        fam = families.setdefault(_stem(n), {"totals": [], "components": []})
        (fam["totals"] if _is_total(n) else fam["components"]).append(n)

    structured = False
    for fam in families.values():
        if len(fam["totals"]) == 1 and len(fam["components"]) >= 2:
            rule = normalize_rule({
                "type": "sum_equals",
                "source_fields": list(fam["components"]),
                "target_field": fam["totals"][0],
                "tolerance": 0.01,
                "source": "suggested",
            })
            if _rule_dedupe_key(rule) not in existing_keys:
                suggestions.append(rule)
                existing_keys.add(_rule_dedupe_key(rule))
                structured = True

    # Strategy B — flat fallback: a single grand total summed from
    # differently-named part fields (e.g. Total Budget = Direct + Indirect +
    # Equipment). Only when no structured families fired and exactly one total
    # exists, so we can't recreate the cross-category double-count above.
    # (Summing subtotals into a grand total is a deliberate non-goal: detecting
    # the hierarchy reliably is error-prone, and false suggestions train users
    # to ignore the suggester.)
    total_fields = [n for n in numeric_names if _is_total(n)]
    if not structured and len(total_fields) == 1:
        total_field = total_fields[0]
        parts = [
            n for n in numeric_names
            if n != total_field and not _is_total(n) and (_tokens(n) & _PART_TOKENS)
        ]
        if len(parts) >= 2:
            rule = normalize_rule({
                "type": "sum_equals",
                "source_fields": parts,
                "target_field": total_field,
                "tolerance": 0.01,
                "source": "suggested",
            })
            if _rule_dedupe_key(rule) not in existing_keys:
                suggestions.append(rule)
                existing_keys.add(_rule_dedupe_key(rule))

    # 2. date_order
    date_like = [n for n in field_names if "date" in n.lower() or _tokens(n) & {
        "start", "end", "begin", "finish", "from", "to",
        "issue", "issued", "due", "effective", "expiration", "expiry", "expire",
    }]
    for start_tokens, end_tokens in _DATE_PAIRS:
        starts = [n for n in date_like if _tokens(n) & start_tokens]
        ends = [n for n in date_like if _tokens(n) & end_tokens]
        for s in starts:
            for e in ends:
                if s == e:
                    continue
                rule = normalize_rule({
                    "type": "date_order",
                    "field_a": s,
                    "field_b": e,
                    "source": "suggested",
                })
                if _rule_dedupe_key(rule) not in existing_keys:
                    suggestions.append(rule)
                    existing_keys.add(_rule_dedupe_key(rule))

    # 3. range_check for percent-like fields
    for n in field_names:
        if _tokens(n) & _PERCENT_TOKENS or "%" in n:
            rule = normalize_rule({
                "type": "range_check",
                "field": n,
                "min": 0,
                "max": 100,
                "source": "suggested",
            })
            if _rule_dedupe_key(rule) not in existing_keys:
                suggestions.append(rule)
                existing_keys.add(_rule_dedupe_key(rule))

    return suggestions


def sanitize_sum_equals_rules(
    field_metadata: list[dict], rules: list[dict]
) -> tuple[list[dict], list[str]]:
    """Strip non-numeric operands from existing sum_equals rules.

    Repairs rules created before the suggester gained a numeric gate — e.g. a
    text field ("Educational Materials Target Audience") summed into a numeric
    total, where every evaluation is silently dropped as unparseable.

    Returns ``(cleaned_rules, notes)`` where ``notes`` is a human-readable list
    of what changed. A sum_equals rule whose target is non-numeric, or which
    drops below two numeric source fields, is removed entirely (a sum needs at
    least two operands). Non-sum rules pass through untouched.

    Fields absent from ``field_metadata`` (renamed/deleted) are left in place —
    we can't judge their type, and the validator already tolerates them.
    """
    meta_by_name = {f.get("key"): f for f in field_metadata if f.get("key")}

    def _numeric(name: str) -> bool:
        meta = meta_by_name.get(name)
        if meta is None:
            return True  # unknown field — don't touch
        return _is_numeric_field(meta)

    cleaned: list[dict] = []
    notes: list[str] = []
    for rule in rules:
        if rule.get("type") != "sum_equals":
            cleaned.append(rule)
            continue
        target = rule.get("target_field")
        sources = list(rule.get("source_fields") or [])
        if target and not _numeric(target):
            notes.append(f"dropped sum_equals (non-numeric target '{target}')")
            continue
        removed = [s for s in sources if not _numeric(s)]
        if not removed:
            cleaned.append(rule)
            continue
        kept = [s for s in sources if _numeric(s)]
        if len(kept) < 2:
            notes.append(
                f"dropped sum_equals -> '{target}' (only {len(kept)} numeric "
                f"operand(s) left after removing {removed})"
            )
            continue
        new_rule = dict(rule)
        new_rule["source_fields"] = kept
        cleaned.append(new_rule)
        notes.append(f"removed {removed} from sum_equals -> '{target}'")
    return cleaned, notes


def _rule_dedupe_key(rule: dict) -> tuple:
    """Stable identity for dedupe — same rule type + params, regardless of id."""
    t = rule.get("type")
    if t == "sum_equals":
        return (t, tuple(sorted(rule.get("source_fields", []))), rule.get("target_field"))
    if t == "conditional_required":
        return (t, rule.get("condition_field"), rule.get("condition_value"), rule.get("required_field"))
    if t == "range_check":
        return (t, rule.get("field"), rule.get("min"), rule.get("max"))
    if t == "cross_reference":
        a, b = rule.get("field_a"), rule.get("field_b")
        return (t,) + tuple(sorted([a or "", b or ""])) + (rule.get("match_type", "contains"),)
    if t == "date_order":
        return (t, rule.get("field_a"), rule.get("field_b"))
    if t == "custom_expression":
        return (t, rule.get("expression"))
    return (t, repr(sorted(rule.items())))
