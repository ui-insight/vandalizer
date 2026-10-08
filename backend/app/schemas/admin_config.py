"""Validation for the processing settings exposed by the admin editor.

Keep optional/unknown configuration keys intact for compatibility with other
settings writers. Validate the effective tier ordering, including defaults.
"""
import math

from app.models.system_config import DEFAULT_QUALITY_CONFIG


def _number(value, label: str, minimum: float, maximum: float, *, integer=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not minimum <= value <= maximum or not math.isfinite(value)
            or (integer and int(value) != value)):
        kind = "a whole number" if integer else "a number"
        raise ValueError(f"{label} must be {kind} between {minimum} and {maximum}")


def validate_quality_config(value: dict | None) -> dict | None:
    if value is None:
        return value
    gates = value.get("verification_gates", {})
    tiers = value.get("quality_tiers", {})
    if not isinstance(gates, dict) or not isinstance(tiers, dict):
        raise ValueError("Quality gates and tiers must be objects")
    for key in ("min_extraction_accuracy", "min_extraction_consistency"):
        if key in gates:
            _number(gates[key], key, 0, 1)
    if "min_workflow_grade" in gates and gates["min_workflow_grade"] not in ("A", "B", "C", "D", "F"):
        raise ValueError("Minimum workflow grade must be A, B, C, D, or F")
    scores = []
    for key in ("excellent", "good", "fair"):
        tier = tiers.get(key, {})
        if not isinstance(tier, dict):
            raise ValueError(f"{key} tier must be an object")
        score = tier.get("min_score", DEFAULT_QUALITY_CONFIG["quality_tiers"][key]["min_score"])
        _number(score, f"{key} threshold", 0, 100)
        scores.append(score)
    if not scores[0] > scores[1] > scores[2]:
        raise ValueError("Thresholds must decrease: Excellent > Good > Fair")
    return value


def validate_extraction_config(value: dict | None) -> dict | None:
    if value is None:
        return value
    chunking = value.get("chunking", {})
    if not isinstance(chunking, dict):
        raise ValueError("Extraction chunking must be an object")
    if "max_keys_per_chunk" in chunking:
        _number(chunking["max_keys_per_chunk"], "Maximum fields per chunk", 1, 100, integer=True)
    return value


def validate_retention_config(value: dict | None) -> dict | None:
    if value is None:
        return value
    for key in ('activity_retention_days', 'chat_retention_days', 'workflow_result_retention_days', 'activity_stale_threshold_minutes'):
        if key in value:
            _number(value[key], key, 0, 2147483647, integer=True)
    policies = value.get('policies', {})
    if not isinstance(policies, dict):
        raise ValueError('Retention policies must be an object')
    for name, policy in policies.items():
        if not isinstance(policy, dict):
            raise ValueError(f'{name} retention policy must be an object')
        for key in ('retention_days', 'soft_delete_grace_days', 'warning_days_before'):
            if key in policy and policy[key] is not None:
                _number(policy[key], f'{name} {key}', 0, 2147483647, integer=True)
            elif key in policy and key != 'warning_days_before':
                raise ValueError(f'{name} {key} must be a whole number')
    return value


def validate_compliance_config(value: dict) -> dict:
    _number(value.get('chunk_size'), 'Compliance chunk size', 500, 2147483647, integer=True)
    _number(value.get('chunk_overlap'), 'Compliance chunk overlap', 0, 2147483647, integer=True)
    if value['chunk_overlap'] >= value['chunk_size']:
        raise ValueError('Compliance chunk overlap must be smaller than chunk size')
    return value


def validate_compliance_patch(value: dict | None) -> dict | None:
    if value is None:
        return value
    from app.models.system_config import DEFAULT_COMPLIANCE_CONFIG
    validate_compliance_config({**DEFAULT_COMPLIANCE_CONFIG, **value})
    return value
