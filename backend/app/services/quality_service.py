"""Quality service  - persist validation runs, compute tiers, history, regression."""

import datetime
import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

from app.models.system_config import SystemConfig
from app.models.validation_run import ValidationRun
from app.models.verification import VerifiedItemMetadata


# Grade-to-score mapping for workflow validation
_GRADE_SCORES = {"A": 95, "B": 85, "C": 75, "D": 55, "F": 30}


def _sample_size_factor(num_test_cases: int, num_runs: int) -> float:
    """Discount factor based on sample size. Returns 0.0-1.0.

    Reaches 1.0 at >=3 test cases with >=3 runs each.
    Penalizes single test case / single run configurations.
    """
    tc_factor = min(1.0, num_test_cases / 3.0)
    run_factor = min(1.0, num_runs / 3.0)
    return tc_factor * run_factor


def compute_config_hash(config: dict) -> str:
    """Deterministic SHA256 hash of a config dict."""
    return hashlib.sha256(json.dumps(config or {}, sort_keys=True).encode()).hexdigest()


async def persist_validation_run(
    item_kind: str,
    item_id: str,
    item_name: str,
    run_type: str,
    result: dict,
    user_id: str,
    model: Optional[str] = None,
    extraction_config: Optional[dict] = None,
) -> ValidationRun:
    """Create a ValidationRun from a validation result dict and update quality metadata."""
    # Compute unified score
    accuracy = result.get("aggregate_accuracy")
    consistency = result.get("aggregate_consistency")
    grade = result.get("grade")

    if run_type == "extraction":
        acc_val = accuracy if accuracy is not None else 0.0
        con_val = consistency if consistency is not None else 0.0
        # Cross-field compliance if present in result
        cf_score = result.get("cross_field_score")
        if cf_score is not None:
            score = min(100.0, max(0.0, acc_val * 50 + con_val * 30 + cf_score * 20))
        else:
            score = min(100.0, max(0.0, acc_val * 60 + con_val * 40))
    else:
        # Prefer continuous score from result if available (new multi-run system)
        result_score = result.get("score")
        if result_score is not None:
            score = float(result_score)
        else:
            # Fallback for old-style grade-only results
            score = float(_GRADE_SCORES.get(grade or "F", 30))

    # Apply sample size factor - low sample sizes reduce effective score
    raw_score = score
    num_tc = len(result.get("test_cases", result.get("sources", [])))
    num_runs_val = result.get("num_runs", 1)
    ssf = _sample_size_factor(num_tc, num_runs_val)
    if ssf < 1.0:
        # Blend toward 50 (neutral) based on how much confidence we lack
        score = score * ssf + 50.0 * (1.0 - ssf)

    # Store score breakdown so the UI can explain penalties
    score_breakdown = {
        "raw_score": round(raw_score, 1),
        "final_score": round(score, 1),
        "sample_size_factor": round(ssf, 3),
        "sample_size_penalty": round(raw_score - score, 1) if ssf < 1.0 else 0,
        "num_test_cases": num_tc,
        "num_runs": num_runs_val,
        "test_cases_needed": max(0, 3 - num_tc),
        "runs_needed": max(0, 3 - num_runs_val),
    }

    # Count checks for workflow validation
    checks = result.get("checks", [])
    num_checks = len(checks)
    checks_passed = sum(1 for c in checks if c.get("status") == "PASS")
    checks_failed = sum(1 for c in checks if c.get("status") == "FAIL")

    # Count test cases for extraction validation
    test_cases = result.get("test_cases", [])
    num_test_cases = len(test_cases)

    cfg_hash = compute_config_hash(extraction_config) if extraction_config else None

    vr = ValidationRun(
        item_kind=item_kind,
        item_id=item_id,
        item_name=item_name,
        run_type=run_type,
        accuracy=accuracy,
        consistency=consistency,
        grade=grade,
        score=score,
        score_breakdown=score_breakdown,
        model=model,
        num_runs=result.get("num_runs", 1),
        num_test_cases=num_test_cases,
        num_checks=num_checks,
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        result_snapshot=result,
        extraction_config=extraction_config or {},
        config_hash=cfg_hash,
        user_id=user_id,
        created_at=datetime.datetime.now(tz=datetime.timezone.utc),
    )
    await vr.insert()

    # Update quality metadata on verified item
    await update_quality_metadata(item_kind, item_id, item_name=item_name)

    return vr


async def update_quality_metadata(item_kind: str, item_id: str, item_name: str | None = None) -> None:
    """Find latest ValidationRun for item and upsert quality fields on VerifiedItemMetadata."""
    latest = await _get_latest_run(item_kind, item_id)
    if not latest:
        return

    sys_cfg = await SystemConfig.get_config()
    qc = sys_cfg.get_quality_config()
    tier = compute_quality_tier(latest.score, qc)

    now = datetime.datetime.now(datetime.timezone.utc)
    run_count = await ValidationRun.find(
        ValidationRun.item_kind == item_kind,
        ValidationRun.item_id == item_id,
    ).count()

    meta = await VerifiedItemMetadata.find_one(
        VerifiedItemMetadata.item_kind == item_kind,
        VerifiedItemMetadata.item_id == item_id,
    )
    if meta:
        meta.quality_score = latest.score
        meta.quality_tier = tier
        meta.quality_grade = latest.grade
        meta.last_validated_at = now
        meta.validation_run_count = run_count
        if item_name and not meta.display_name:
            meta.display_name = item_name
        await meta.save()
    else:
        meta = VerifiedItemMetadata(
            item_kind=item_kind,
            item_id=item_id,
            display_name=item_name,
            quality_score=latest.score,
            quality_tier=tier,
            quality_grade=latest.grade,
            last_validated_at=now,
            validation_run_count=run_count,
        )
        await meta.insert()


def compute_quality_tier(score: Optional[float], quality_config: dict) -> Optional[str]:
    """Map a numeric score to a quality tier string using config thresholds."""
    if score is None:
        return None
    tiers = quality_config.get("quality_tiers", {})
    # Check tiers in descending order of min_score
    for tier_name in ("excellent", "good", "fair"):
        tier_def = tiers.get(tier_name, {})
        if score >= tier_def.get("min_score", 999):
            return tier_name
    return None


async def get_quality_history(
    item_kind: str,
    item_id: str,
    limit: int = 50,
) -> list[dict]:
    """Query ValidationRun history for an item, sorted newest first."""
    runs = await (
        ValidationRun.find(
            ValidationRun.item_kind == item_kind,
            ValidationRun.item_id == item_id,
        )
        .sort("-created_at")
        .limit(limit)
        .to_list()
    )
    return [_run_to_dict(r) for r in runs]


async def get_latest_validation(
    item_kind: str,
    item_id: str,
) -> Optional[dict]:
    """Return the most recent ValidationRun as dict, or None."""
    run = await (
        ValidationRun.find(
            ValidationRun.item_kind == item_kind,
            ValidationRun.item_id == item_id,
        )
        .sort("-created_at")
        .limit(1)
        .to_list()
    )
    if not run:
        return None
    return _run_to_dict(run[0])


async def get_quality_summary() -> dict:
    """Aggregate stats: avg score, total runs, validated vs unvalidated items."""
    # Use aggregation to avoid loading all runs into memory
    pipeline = [
        {"$group": {
            "_id": {"item_kind": "$item_kind", "item_id": "$item_id"},
            "latest_score": {"$last": "$score"},
            "run_count": {"$sum": 1},
        }},
        {"$group": {
            "_id": None,
            "total_runs": {"$sum": "$run_count"},
            "items_validated": {"$sum": 1},
            "score_sum": {"$sum": "$latest_score"},
            "score_count": {"$sum": {"$cond": [{"$gt": ["$latest_score", None]}, 1, 0]}},
        }},
    ]
    agg_result = await ValidationRun.aggregate(pipeline).to_list()

    if agg_result:
        agg = agg_result[0]
        total_runs = agg.get("total_runs", 0)
        items_validated = agg.get("items_validated", 0)
        score_sum = agg.get("score_sum", 0)
        score_count = agg.get("score_count", 0)
        avg_score = score_sum / score_count if score_count > 0 else 0.0
    else:
        total_runs = 0
        items_validated = 0
        avg_score = 0.0

    # Count total verified items and below-threshold
    all_meta = await VerifiedItemMetadata.find_all().to_list()
    total_verified = len(all_meta)

    sys_cfg = await SystemConfig.get_config()
    qc = sys_cfg.get_quality_config()
    fair_min = qc.get("quality_tiers", {}).get("fair", {}).get("min_score", 50)
    below_threshold = sum(1 for m in all_meta if m.quality_score is not None and m.quality_score < fair_min)

    return {
        "avg_score": round(avg_score, 1),
        "total_runs": total_runs,
        "items_validated": items_validated,
        "total_verified": total_verified,
        "items_below_threshold": below_threshold,
    }


async def get_quality_timeline(
    days: int = 90,
    item_kind: Optional[str] = None,
    item_id: Optional[str] = None,
) -> list[dict]:
    """Aggregate ValidationRun by date for timeline charts."""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)

    query_filters = [ValidationRun.created_at >= cutoff]
    if item_kind:
        query_filters.append(ValidationRun.item_kind == item_kind)
    if item_id:
        query_filters.append(ValidationRun.item_id == item_id)

    runs = await ValidationRun.find(*query_filters).sort("created_at").to_list()

    # Group by date
    daily: dict[str, dict] = {}
    for r in runs:
        day = r.created_at.strftime("%Y-%m-%d")
        if day not in daily:
            daily[day] = {"scores": [], "items": set()}
        daily[day]["scores"].append(r.score)
        daily[day]["items"].add((r.item_kind, r.item_id))

    return [
        {
            "date": day,
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1),
            "run_count": len(d["scores"]),
            "items_validated": len(d["items"]),
        }
        for day, d in sorted(daily.items())
    ]


async def run_regression_suite(
    user_id: str,
    model: Optional[str] = None,
) -> dict:
    """Run validation on all verified items and return summary."""
    from app.models.library import LibraryItem
    from app.services import extraction_validation_service
    from app.services import workflow_service

    items = await LibraryItem.find({"verified": True}).to_list()

    results = []
    for item in items:
        item_id_str = str(item.item_id)
        kind = item.kind.value if hasattr(item.kind, "value") else str(item.kind)

        # Get previous score for delta
        prev = await get_latest_validation(kind, item_id_str)
        prev_score = prev["score"] if prev else None

        try:
            if kind == "search_set":
                # Need the search_set uuid from the SearchSet document
                from app.models.search_set import SearchSet
                ss = await SearchSet.get(item.item_id)
                if not ss:
                    continue
                result = await extraction_validation_service.run_validation(
                    search_set_uuid=ss.uuid,
                    user_id=user_id,
                    model=model,
                )
                current_score = result.get("aggregate_accuracy", 0) or 0
                current_score = min(100.0, max(0.0, current_score * 60 + (result.get("aggregate_consistency", 0) or 0) * 40))
            elif kind == "workflow":
                result = await workflow_service.validate_workflow(item_id_str)
                # Prefer continuous score from new multi-run system
                result_score = result.get("score")
                if result_score is not None:
                    current_score = float(result_score)
                else:
                    grade = result.get("grade", "F")
                    current_score = float(_GRADE_SCORES.get(grade, 30))
            else:
                continue

            delta = round(current_score - prev_score, 1) if prev_score is not None else None
            results.append({
                "item_id": item_id_str,
                "kind": kind,
                "name": getattr(item, "name", item_id_str),
                "score": round(current_score, 1),
                "grade": result.get("grade"),
                "prev_score": round(prev_score, 1) if prev_score is not None else None,
                "delta": delta,
                "status": "ok",
            })
        except Exception as e:
            results.append({
                "item_id": item_id_str,
                "kind": kind,
                "name": getattr(item, "name", item_id_str),
                "score": None,
                "grade": None,
                "prev_score": round(prev_score, 1) if prev_score is not None else None,
                "delta": None,
                "status": f"error: {e}",
            })

    return {
        "total_items": len(results),
        "succeeded": sum(1 for r in results if r["status"] == "ok"),
        "failed": sum(1 for r in results if r["status"] != "ok"),
        "results": results,
    }


# ---------------------------------------------------------------------------
# LLM Improvement Suggestions
# ---------------------------------------------------------------------------


async def generate_improvement_suggestions(
    item_kind: str,
    item_id: str,
    result: dict,
) -> str:
    """Use the LLM to suggest improvements when validation results fall below an A grade.

    For extractions: analyses accuracy/consistency weaknesses per field.
    For workflows: analyses failing/warning checks and suggests fixes.
    Returns a markdown string of suggestions.
    """
    from app.services.config_service import get_default_model_name
    from app.services.llm_service import create_chat_agent

    sys_cfg = await SystemConfig.get_config()
    sys_config_doc = sys_cfg.model_dump() if sys_cfg else {}

    # Use the same model resolution path as chat/extraction
    default_model = await get_default_model_name()
    if not default_model:
        default_model = "gpt-4o-mini"

    if item_kind == "search_set":
        prompt = _build_extraction_suggestion_prompt(result)
    else:
        prompt = _build_workflow_suggestion_prompt(result)

    agent = create_chat_agent(
        default_model,
        system_prompt=(
            "You are an expert at improving AI extraction and workflow configurations. "
            "Given validation results, provide concise, actionable suggestions to improve quality. "
            "Use markdown formatting. Keep suggestions practical and specific."
        ),
        system_config_doc=sys_config_doc,
    )
    try:
        res = await agent.run(prompt)
        return res.output
    except Exception as exc:
        logger.exception("Failed to generate improvement suggestions for %s %s", item_kind, item_id)
        return f"Unable to generate suggestions — {exc}"


def _build_extraction_suggestion_prompt(result: dict) -> str:
    acc = result.get("aggregate_accuracy")
    cons = result.get("aggregate_consistency")
    lines = [
        "## Extraction Validation Results",
        f"- Overall Accuracy: {round(acc * 100)}%" if acc is not None else "- Overall Accuracy: N/A",
        f"- Overall Consistency: {round(cons * 100)}%" if cons is not None else "- Overall Consistency: N/A",
        "",
        "### Per-Test-Case Breakdown:",
    ]
    for tc in result.get("test_cases", []):
        lines.append(f"\n**{tc.get('label', 'Unknown')}** — Accuracy: {_fmt_pct(tc.get('overall_accuracy'))}, Consistency: {_fmt_pct(tc.get('overall_consistency'))}")
        for f in tc.get("fields", []):
            flag = ""
            if f.get("accuracy") is not None and f["accuracy"] < 0.9:
                flag = " [LOW ACCURACY]"
            if f.get("consistency", 1) < 0.9:
                flag += " [LOW CONSISTENCY]"
            lines.append(
                f"  - {f.get('field_name')}: expected={f.get('expected', 'N/A')}, "
                f"extracted={f.get('most_common_value', 'null')}, "
                f"accuracy={_fmt_pct(f.get('accuracy'))}, consistency={_fmt_pct(f.get('consistency'))}{flag}"
            )

    lines.append("\n---\nBased on these results, suggest specific improvements to raise the extraction quality to an A grade (≥90% accuracy and consistency). Focus on:\n1. Fields with low accuracy — how to improve extraction prompts or field definitions\n2. Fields with low consistency — how to reduce variance across runs\n3. Any patterns you notice across test cases")
    return "\n".join(lines)


def _build_workflow_suggestion_prompt(result: dict) -> str:
    grade = result.get("grade", "?")
    summary = result.get("summary", "")
    lines = [
        "## Workflow Validation Results",
        f"- Grade: {grade}",
        f"- Summary: {summary}",
        "",
        "### Checks:",
    ]
    for c in result.get("checks", []):
        status = c.get("status", "?")
        flag = " [NEEDS FIX]" if status in ("FAIL", "WARN") else ""
        lines.append(f"  - [{status}] {c.get('name', 'Unknown')}: {c.get('detail', 'No detail')}{flag}")

    lines.append("\n---\nBased on these results, suggest specific improvements to raise the workflow quality to an A grade (all checks passing, no warnings). Focus on:\n1. Checks that failed — what might cause the failure and how to fix it\n2. Checks with warnings — how to address the concern\n3. General workflow structure improvements")
    return "\n".join(lines)


def _fmt_pct(val) -> str:
    if val is None:
        return "N/A"
    return f"{round(val * 100)}%"


# ---------------------------------------------------------------------------
# Stale / monitoring helpers
# ---------------------------------------------------------------------------


async def detect_stale_items(max_age_days: int = 14) -> list[dict]:
    """Find verified items whose last validation is older than max_age_days."""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)
    stale = await VerifiedItemMetadata.find(
        VerifiedItemMetadata.last_validated_at < cutoff,
    ).to_list()
    return [
        {
            "item_kind": m.item_kind,
            "item_id": m.item_id,
            "display_name": m.display_name or m.item_id,
            "quality_score": m.quality_score,
            "quality_tier": m.quality_tier,
            "last_validated_at": m.last_validated_at.isoformat() if m.last_validated_at else None,
        }
        for m in stale
    ]


async def get_quality_contract_status(item_kind: str, item_id: str) -> dict:
    """Return quality contract status for a verified item."""
    from app.models.quality_alert import QualityAlert

    sys_cfg = await SystemConfig.get_config()
    qc = sys_cfg.get_quality_config()
    monitoring = qc.get("monitoring", {})
    stale_days = monitoring.get("stale_threshold_days", 14)

    meta = await VerifiedItemMetadata.find_one(
        VerifiedItemMetadata.item_kind == item_kind,
        VerifiedItemMetadata.item_id == item_id,
    )
    if not meta:
        return {"status": "unmonitored", "tier": None, "score": None, "last_validated_at": None,
                "is_stale": False, "has_alerts": False, "monitored": False}

    is_stale = False
    if meta.last_validated_at:
        lv = meta.last_validated_at
        if lv.tzinfo is None:
            lv = lv.replace(tzinfo=datetime.timezone.utc)
        is_stale = (datetime.datetime.now(datetime.timezone.utc) - lv).days > stale_days

    has_alerts = await QualityAlert.find(
        QualityAlert.item_kind == item_kind,
        QualityAlert.item_id == item_id,
        QualityAlert.acknowledged == False,
    ).count() > 0

    monitored = monitoring.get("auto_revalidate", False)

    status = "stale" if is_stale else "monitored" if monitored else "unmonitored"

    return {
        "status": status,
        "tier": meta.quality_tier,
        "score": meta.quality_score,
        "last_validated_at": meta.last_validated_at.isoformat() if meta.last_validated_at else None,
        "is_stale": is_stale,
        "has_alerts": has_alerts,
        "monitored": monitored,
    }


async def check_verification_readiness(
    item_kind: str,
    item_id: str,
) -> dict:
    """Check if an item meets minimum thresholds for verification submission.

    Returns dict with 'ready' bool, 'issues' list, and 'recommendations' list.
    """
    sys_cfg = await SystemConfig.get_config()
    qc = sys_cfg.get_quality_config()
    gates = qc.get("verification_gates", {})

    min_test_cases = gates.get("min_test_cases", 3)
    min_runs = gates.get("min_runs", 3)
    min_score = gates.get("min_score", 70)

    issues: list[str] = []
    recommendations: list[str] = []

    # Check latest validation
    latest = await get_latest_validation(item_kind, item_id)
    if not latest:
        issues.append("No validation runs found. Run validation first.")
        return {"ready": False, "issues": issues, "recommendations": ["Run validation with at least 3 test cases and 3 runs per test case."]}

    result = latest.get("result_snapshot", {})
    num_tc = len(result.get("test_cases", result.get("sources", [])))
    num_runs = result.get("num_runs", 1)
    score = latest.get("score", 0)

    if num_tc < min_test_cases:
        issues.append(f"Only {num_tc} test case(s) used. Minimum is {min_test_cases}.")
        recommendations.append(f"Add at least {min_test_cases - num_tc} more test case(s) with diverse source documents.")

    if num_runs < min_runs:
        issues.append(f"Only {num_runs} run(s) per test case. Minimum is {min_runs}.")
        recommendations.append(f"Re-run validation with at least {min_runs} runs for reliable consistency measurement.")

    if score < min_score:
        issues.append(f"Quality score is {score:.0f}. Minimum for submission is {min_score}.")
        recommendations.append("Review challenging fields and improve extraction prompts or field definitions.")

    # Check cross-field rules if any exist
    if item_kind == "search_set":
        from app.models.search_set import SearchSet
        ss = await SearchSet.find_one(SearchSet.uuid == item_id)
        if ss and ss.cross_field_rules and result.get("cross_field_score") is None:
            recommendations.append("Cross-field rules are defined but haven't been validated. Consider running cross-field validation.")

    ready = len(issues) == 0
    return {"ready": ready, "issues": issues, "recommendations": recommendations}


async def get_quality_items(
    sort: str = "score",
    order: str = "asc",
    limit: int = 100,
) -> list[dict]:
    """Return per-item quality data for the admin dashboard."""
    all_meta = await VerifiedItemMetadata.find_all().to_list()
    sys_cfg = await SystemConfig.get_config()
    qc = sys_cfg.get_quality_config()
    stale_days = qc.get("monitoring", {}).get("stale_threshold_days", 14)
    now = datetime.datetime.now(datetime.timezone.utc)

    items = []
    for m in all_meta:
        # Determine trend from last 2 runs
        runs = await (
            ValidationRun.find(
                ValidationRun.item_kind == m.item_kind,
                ValidationRun.item_id == m.item_id,
            )
            .sort("-created_at")
            .limit(2)
            .to_list()
        )
        trend = "flat"
        if len(runs) >= 2:
            if runs[0].score > runs[1].score + 2:
                trend = "up"
            elif runs[0].score < runs[1].score - 2:
                trend = "down"

        is_stale = False
        if m.last_validated_at:
            lv = m.last_validated_at
            if lv.tzinfo is None:
                lv = lv.replace(tzinfo=datetime.timezone.utc)
            is_stale = (now - lv).days > stale_days

        items.append({
            "item_kind": m.item_kind,
            "item_id": m.item_id,
            "display_name": m.display_name or m.item_id,
            "quality_score": m.quality_score,
            "quality_tier": m.quality_tier,
            "last_validated_at": m.last_validated_at.isoformat() if m.last_validated_at else None,
            "validation_run_count": m.validation_run_count or 0,
            "trend": trend,
            "stale": is_stale,
        })

    # Sort
    reverse = order == "desc"
    if sort == "score":
        items.sort(key=lambda x: x.get("quality_score") or 0, reverse=reverse)
    elif sort == "name":
        items.sort(key=lambda x: (x.get("display_name") or "").lower(), reverse=reverse)
    elif sort == "last_validated":
        items.sort(key=lambda x: x.get("last_validated_at") or "", reverse=reverse)

    return items[:limit]


async def get_quality_item_detail(item_kind: str, item_id: str) -> dict:
    """Return detailed quality info for a single item including history and model comparison."""
    runs = await (
        ValidationRun.find(
            ValidationRun.item_kind == item_kind,
            ValidationRun.item_id == item_id,
        )
        .sort("-created_at")
        .to_list()
    )

    history = [_run_to_dict(r) for r in runs]

    # Model comparison: group runs by model, compute average score per model
    model_scores: dict[str, list[float]] = {}
    for r in runs:
        model_key = r.model or "default"
        model_scores.setdefault(model_key, []).append(r.score)

    model_comparison = [
        {"model": model, "avg_score": round(sum(scores) / len(scores), 1), "run_count": len(scores)}
        for model, scores in model_scores.items()
    ]

    return {
        "item_kind": item_kind,
        "item_id": item_id,
        "history": history,
        "model_comparison": model_comparison,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_latest_run(item_kind: str, item_id: str) -> Optional[ValidationRun]:
    runs = await (
        ValidationRun.find(
            ValidationRun.item_kind == item_kind,
            ValidationRun.item_id == item_id,
        )
        .sort("-created_at")
        .limit(1)
        .to_list()
    )
    return runs[0] if runs else None


def _run_to_dict(r: ValidationRun) -> dict:
    return {
        "uuid": r.uuid,
        "item_kind": r.item_kind,
        "item_id": r.item_id,
        "item_name": r.item_name,
        "run_type": r.run_type,
        "accuracy": r.accuracy,
        "consistency": r.consistency,
        "grade": r.grade,
        "score": r.score,
        "score_breakdown": r.score_breakdown if hasattr(r, 'score_breakdown') and r.score_breakdown else None,
        "model": r.model,
        "num_runs": r.num_runs,
        "num_test_cases": r.num_test_cases,
        "num_checks": r.num_checks,
        "checks_passed": r.checks_passed,
        "checks_failed": r.checks_failed,
        "result_snapshot": r.result_snapshot,
        "extraction_config": r.extraction_config,
        "user_id": r.user_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
