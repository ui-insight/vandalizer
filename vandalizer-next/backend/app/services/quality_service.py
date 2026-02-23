"""Quality service  - persist validation runs, compute tiers, history, regression."""

import datetime
from typing import Optional

from app.models.system_config import SystemConfig
from app.models.validation_run import ValidationRun
from app.models.verification import VerifiedItemMetadata


# Grade-to-score mapping for workflow validation
_GRADE_SCORES = {"A": 95, "B": 85, "C": 75, "D": 55, "F": 30}


async def persist_validation_run(
    item_kind: str,
    item_id: str,
    item_name: str,
    run_type: str,
    result: dict,
    user_id: str,
    model: Optional[str] = None,
) -> ValidationRun:
    """Create a ValidationRun from a validation result dict and update quality metadata."""
    # Compute unified score
    accuracy = result.get("aggregate_accuracy")
    consistency = result.get("aggregate_consistency")
    grade = result.get("grade")

    if run_type == "extraction":
        acc_val = accuracy if accuracy is not None else 0.0
        con_val = consistency if consistency is not None else 0.0
        score = min(100.0, max(0.0, acc_val * 60 + con_val * 40))
    else:
        score = float(_GRADE_SCORES.get(grade or "F", 30))

    # Count checks for workflow validation
    checks = result.get("checks", [])
    num_checks = len(checks)
    checks_passed = sum(1 for c in checks if c.get("status") == "PASS")
    checks_failed = sum(1 for c in checks if c.get("status") == "FAIL")

    # Count test cases for extraction validation
    test_cases = result.get("test_cases", [])
    num_test_cases = len(test_cases)

    vr = ValidationRun(
        item_kind=item_kind,
        item_id=item_id,
        item_name=item_name,
        run_type=run_type,
        accuracy=accuracy,
        consistency=consistency,
        grade=grade,
        score=score,
        model=model,
        num_runs=result.get("num_runs", 1),
        num_test_cases=num_test_cases,
        num_checks=num_checks,
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        result_snapshot=result,
        user_id=user_id,
        created_at=datetime.datetime.now(tz=datetime.timezone.utc),
    )
    await vr.insert()

    # Update quality metadata on verified item
    await update_quality_metadata(item_kind, item_id)

    return vr


async def update_quality_metadata(item_kind: str, item_id: str) -> None:
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
        await meta.save()
    else:
        meta = VerifiedItemMetadata(
            item_kind=item_kind,
            item_id=item_id,
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
    all_runs = await ValidationRun.find_all().to_list()
    total_runs = len(all_runs)

    # Distinct items that have been validated
    validated_items = set()
    score_sum = 0.0
    score_count = 0
    for r in all_runs:
        validated_items.add((r.item_kind, r.item_id))
        score_sum += r.score
        score_count += 1

    avg_score = score_sum / score_count if score_count > 0 else 0.0

    # Count total verified items
    all_meta = await VerifiedItemMetadata.find_all().to_list()
    total_verified = len(all_meta)

    # Items below threshold
    sys_cfg = await SystemConfig.get_config()
    qc = sys_cfg.get_quality_config()
    fair_min = qc.get("quality_tiers", {}).get("fair", {}).get("min_score", 50)
    below_threshold = sum(1 for m in all_meta if m.quality_score is not None and m.quality_score < fair_min)

    return {
        "avg_score": round(avg_score, 1),
        "total_runs": total_runs,
        "items_validated": len(validated_items),
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
    from app.services.llm_service import create_chat_agent

    sys_cfg = await SystemConfig.get_config()
    sys_config_doc = {
        "available_models": sys_cfg.available_models,
        "llm_endpoint": sys_cfg.llm_endpoint,
    }

    # Pick the default model
    default_model = None
    for m in sys_cfg.available_models:
        if m.get("default"):
            default_model = m.get("model_id") or m.get("model_name")
            break
    if not default_model and sys_cfg.available_models:
        default_model = sys_cfg.available_models[0].get("model_id") or sys_cfg.available_models[0].get("model_name")
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
    res = await agent.run(prompt)
    return res.output


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
        "model": r.model,
        "num_runs": r.num_runs,
        "num_test_cases": r.num_test_cases,
        "num_checks": r.num_checks,
        "checks_passed": r.checks_passed,
        "checks_failed": r.checks_failed,
        "result_snapshot": r.result_snapshot,
        "user_id": r.user_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
