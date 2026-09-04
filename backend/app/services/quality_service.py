"""Quality service  - persist validation runs, compute tiers, history, regression."""

import datetime
import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

from app.models.system_config import SystemConfig  # noqa: E402
from app.models.validation_run import ValidationRun  # noqa: E402
from app.models.verification import VerifiedItemMetadata  # noqa: E402


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
    model_settings: Optional[dict] = None,
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
    elif run_type == "kb_validation":
        # Knowledge base validation: score is pre-computed in kb_validation_service
        score = float(result.get("raw_score", 0))
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
    num_runs_val = result.get("num_runs", 1)

    if run_type == "workflow":
        # For workflows, the "test cases" concept doesn't apply — workflows
        # have checks, not test cases.  Use num_checks as the sample-size
        # proxy (a plan with >=4 checks is considered adequate).
        num_tc = len(result.get("checks", []))
        ssf = _sample_size_factor(min(num_tc, 3), num_runs_val)
        runs_needed = max(0, 3 - num_runs_val)
    elif run_type == "kb_validation":
        # KB validation is single-run by design (it never does replicates), so
        # judging it on run count would discount every KB ~3x for a config it
        # can't satisfy. Base confidence on test-query count alone.
        num_tc = int(result.get("num_test_queries", 0))
        ssf = min(1.0, num_tc / 3.0)
        runs_needed = 0
    else:
        num_tc = len(result.get("test_cases", result.get("sources", [])))
        ssf = _sample_size_factor(num_tc, num_runs_val)
        runs_needed = max(0, 3 - num_runs_val)

    if ssf < 1.0:
        # Low confidence pulls the score toward a neutral 50 — but only ever to
        # REDUCE it. A failing score stays visibly failing; we never inflate a
        # bad result to look mediocre just because the sample was small.
        blended = score * ssf + 50.0 * (1.0 - ssf)
        score = min(score, blended)

    # Store score breakdown so the UI can explain penalties
    score_breakdown = {
        "raw_score": round(raw_score, 1),
        "final_score": round(score, 1),
        "sample_size_factor": round(ssf, 3),
        "sample_size_penalty": round(raw_score - score, 1),
        "num_test_cases": num_tc,
        "num_runs": num_runs_val,
        "test_cases_needed": max(0, 3 - num_tc),
        "runs_needed": runs_needed,
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
        model_settings=model_settings,
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

    # Phase 5: when a workflow validation result shows elevated cross-field
    # failure, auto-enqueue a shadow workflow optimizer run so the user has
    # a candidate fix waiting next time they open the workflow. Best-effort
    # — never blocks the validation insert on a trigger failure.
    if item_kind == "workflow" and run_type == "workflow":
        try:
            await _maybe_trigger_workflow_shadow_run(
                workflow_id=item_id, user_id=user_id, result=result,
            )
        except Exception:
            logger.warning(
                "Workflow shadow-run trigger failed for workflow=%s",
                item_id, exc_info=True,
            )

    return vr


# Phase 5: workflow score threshold below which a cross-field-failure
# validation result auto-fires a shadow optimizer run. Tuned conservatively
# — only the runs that would clearly benefit from re-tuning.
WORKFLOW_SHADOW_TRIGGER_SCORE = 70.0


async def _maybe_trigger_workflow_shadow_run(
    *, workflow_id: str, user_id: str, result: dict,
) -> None:
    """Inspect a freshly-persisted workflow validation result; if it shows
    significant cross-field-style failure on a low overall score, fire a
    shadow workflow optimizer run."""
    score = result.get("score")
    checks = result.get("checks") or []
    if not isinstance(score, (int, float)) or score >= WORKFLOW_SHADOW_TRIGGER_SCORE:
        return
    if not checks:
        return
    fails = sum(1 for c in checks if str(c.get("status", "")).upper() == "FAIL")
    if fails == 0:
        return
    fail_rate = fails / len(checks)
    if fail_rate < 0.25:
        # Below the noise floor for "the workflow is broken vs the test
        # cases are flaky". Don't burn shadow runs on flaky inputs.
        return
    from app.services import optimizer_signal_service
    await optimizer_signal_service.enqueue_workflow_shadow_run(
        workflow_id=workflow_id,
        user_id=user_id,
        trigger="cross_field_failure",
        trigger_detail={
            "score": round(float(score), 1),
            "fail_rate": round(fail_rate, 3),
            "checks_failed": fails,
            "checks_total": len(checks),
        },
    )


async def record_optimizer_apply(
    *,
    item_kind: str,
    item_id: str,
    item_name: str,
    run_type: str,
    score: float,
    user_id: str,
    source_run_uuid: str,
    applied_config: dict | None = None,
    judge_model: str | None = None,
    judge_variance: float | None = None,
) -> ValidationRun:
    """Record a ``ValidationRun`` for an optimizer apply (Phase 4 unification).

    Each apply produces a timeline entry tagged ``source="optimizer_apply"``
    so the shared QualityTimeline can show "we applied a new config here"
    alongside the validation runs that *measured* quality. ``score`` is the
    optimizer's headline score for the winning config (0..100 scale to
    match validation runs).

    This is intentionally lightweight — it doesn't re-evaluate, just records
    the fact that an apply occurred and what the optimizer's measurement
    was at the time. The next real validation run will overwrite quality
    metadata; this row exists to make the apply visible in the timeline.
    """
    snapshot = {
        "source": "optimizer_apply",
        "source_run_uuid": source_run_uuid,
        "score": score,
        "applied_config": applied_config or {},
        "judge_model": judge_model,
        "judge_variance": judge_variance,
    }
    vr = ValidationRun(
        item_kind=item_kind,
        item_id=item_id,
        item_name=item_name,
        run_type=run_type,
        score=score,
        model=judge_model,
        result_snapshot=snapshot,
        user_id=user_id,
        source="optimizer_apply",
        source_run_uuid=source_run_uuid,
        created_at=datetime.datetime.now(tz=datetime.timezone.utc),
    )
    await vr.insert()
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
        # A run that recovers the pre-regression score clears the review flag
        # on its own — a transient dip shouldn't need a human to un-flag it.
        if (
            meta.regression_pending_review
            and meta.regression_baseline_score is not None
            and latest.score is not None
            and latest.score >= meta.regression_baseline_score
        ):
            _reset_regression_state(meta)
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


# ---------------------------------------------------------------------------
# Regression review state
# ---------------------------------------------------------------------------

def _reset_regression_state(meta: VerifiedItemMetadata) -> None:
    """Clear the pending-review flag and everything that explains it."""
    meta.regression_pending_review = False
    meta.regression_detected_at = None
    meta.regression_severity = None
    meta.regression_baseline_score = None


async def clear_regression_review(item_kind: str, item_id: str) -> bool:
    """A human looked at it. Returns True when a flag was actually cleared."""
    meta = await VerifiedItemMetadata.find_one(
        VerifiedItemMetadata.item_kind == item_kind,
        VerifiedItemMetadata.item_id == item_id,
    )
    if not meta or not meta.regression_pending_review:
        return False
    _reset_regression_state(meta)
    await meta.save()
    return True


async def _item_owner_user_id(item_kind: str, item_id: str) -> Optional[str]:
    """The user who owns the item behind a quality alert.

    ``item_id`` is the uuid for search sets and knowledge bases but the
    ObjectId string for workflows — that asymmetry is baked into the rest of
    the monitoring loop, so it is handled here rather than pushed onto callers.
    """
    try:
        if item_kind == "search_set":
            from app.models.search_set import SearchSet
            obj = await SearchSet.find_one(SearchSet.uuid == item_id)
            return getattr(obj, "user_id", None) if obj else None
        if item_kind == "knowledge_base":
            from app.models.knowledge import KnowledgeBase
            obj = await KnowledgeBase.find_one(KnowledgeBase.uuid == item_id)
            return getattr(obj, "user_id", None) if obj else None
        if item_kind == "workflow":
            from beanie import PydanticObjectId

            from app.models.workflow import Workflow
            obj = await Workflow.get(PydanticObjectId(item_id))
            return getattr(obj, "user_id", None) if obj else None
    except Exception:
        logger.warning(
            "Owner lookup failed for %s %s", item_kind, item_id, exc_info=True,
        )
    return None


async def flag_quality_regression(
    *,
    meta: VerifiedItemMetadata,
    severity: str,
    previous_score: float,
    current_score: float,
    detected_at: datetime.datetime,
) -> None:
    """Give a detected regression teeth and a route to a human.

    A regression used to write a ``QualityAlert`` — a row only the admin
    Quality tab renders — enqueue a shadow optimizer run, and leave the item
    advertising the tier it held before. The person who owns the item, and who
    will use it again tomorrow, was told nothing at all.

    Now: the item is flagged ``regression_pending_review`` so every surface
    that shows its quality shows that instead of a clean tier, the owner gets a
    notification, and a ``critical`` drop also gets an email — the difference
    between "there is a record of this somewhere" and "someone was told".

    Best-effort throughout: monitoring runs nightly in Celery and must not
    fail a whole pass because one owner has no email address.
    """
    meta.regression_pending_review = True
    meta.regression_detected_at = detected_at
    meta.regression_severity = severity
    # Only raise the bar, never lower it: a second, smaller drop while a review
    # is already pending must not make recovery easier than it was.
    if (
        meta.regression_baseline_score is None
        or previous_score > meta.regression_baseline_score
    ):
        meta.regression_baseline_score = previous_score
    await meta.save()

    try:
        await _notify_regression_owner(
            meta=meta, severity=severity,
            previous_score=previous_score, current_score=current_score,
        )
    except Exception:
        logger.warning(
            "Regression owner notification failed for %s %s",
            meta.item_kind, meta.item_id, exc_info=True,
        )


#: Deep links matching the ones ``failure_notifications`` already emits, so the
#: bell opens the item itself rather than a list the user has to search.
_ITEM_LINKS = {
    "search_set": "/?extraction={item_id}",
    "workflow": "/?workflow={item_id}",
    "knowledge_base": "/?kb={item_id}",
}


async def _notify_regression_owner(
    *,
    meta: VerifiedItemMetadata,
    severity: str,
    previous_score: float,
    current_score: float,
) -> None:
    owner_id = await _item_owner_user_id(meta.item_kind, meta.item_id)
    if not owner_id:
        logger.info(
            "No owner found for %s %s — regression stays admin-only",
            meta.item_kind, meta.item_id,
        )
        return

    from app.services import notification_service

    item_name = meta.display_name or meta.item_id
    kind_label = meta.item_kind.replace("_", " ")
    link = _ITEM_LINKS.get(meta.item_kind, "/library").format(item_id=meta.item_id)
    drop = previous_score - current_score

    await notification_service.create_notification(
        user_id=owner_id,
        kind="quality_regression",
        title=f'Quality dropped on "{item_name}"',
        body=(
            f"{previous_score:.0f} → {current_score:.0f} "
            f"({drop:.0f} points) on the last automatic revalidation."
        ),
        link=link,
        item_kind=meta.item_kind,
        item_id=meta.item_id,
        item_name=item_name,
        severity="error" if severity == "critical" else "warning",
        # One row per item: a nightly monitor that keeps finding the same
        # regression should keep it visible, not bury the rest of the bell.
        coalesce_key=f"quality_regression:{meta.item_kind}:{meta.item_id}",
        group_title=f'Quality dropped on "{item_name}" ({{count}} checks)',
    )

    if severity != "critical":
        return

    from app.models.user import User
    owner = await User.find_one(User.user_id == owner_id)
    if not owner or not owner.email:
        return

    from app.config import Settings
    from app.services.email_service import quality_regression_email, send_email

    settings = Settings()
    subject, html = quality_regression_email(
        owner_name=owner.name or owner.user_id,
        item_name=item_name,
        item_kind_label=kind_label,
        previous_score=previous_score,
        current_score=current_score,
        item_url=f"{settings.frontend_url}{link}",
    )
    await send_email(owner.email, subject, html, settings, email_type="quality_regression")


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


async def reexecute_official_baseline(meta) -> Optional[dict]:
    """Run the pinned official_baseline's test cases against the current config.

    Extraction (search_set) only — the one kind whose frozen baseline can be
    mechanically re-executed: a workflow baseline grades historical executions
    and a KB baseline needs the KB's live index, so neither can be replayed
    from the frozen dict alone. Returns the v2 validation result dict, or
    None when there is nothing executable (wrong kind, no baseline, or no
    baseline case with both a source text and expected values).
    """
    if getattr(meta, "item_kind", None) != "search_set" or not meta.official_baseline:
        return None

    from app.models.extraction_test_case import ExtractionTestCase
    from app.models.search_set import SearchSet
    from app.services.extraction_validation_service import run_validation_v2

    try:
        ss = await SearchSet.get(meta.item_id)
    except Exception:
        ss = None
    if not ss:
        return None

    baseline = meta.official_baseline
    sources: list[dict] = []
    for entry in baseline.get("test_cases") or []:
        if not isinstance(entry, dict):
            continue
        # Examiner-added cases carry expected_values inline; cases frozen from
        # a validation snapshot carry per-field result rows instead.
        expected = entry.get("expected_values")
        if not expected:
            expected = {
                f["field_name"]: f["expected"]
                for f in entry.get("fields") or []
                if isinstance(f, dict) and f.get("field_name")
                and f.get("expected") not in (None, "")
            }
        source_text = entry.get("source_text")
        if not source_text and entry.get("test_case_uuid"):
            tc = await ExtractionTestCase.find_one(
                ExtractionTestCase.uuid == entry["test_case_uuid"]
            )
            if tc and tc.source_text:
                source_text = tc.source_text
        if not source_text or not expected:
            continue
        sources.append({
            "label": entry.get("label") or "Baseline case",
            "source_type": "text",
            "source_text": source_text,
            "expected_values": {k: str(v) for k, v in expected.items()},
        })

    if not sources:
        return None

    # Replicate the baseline's own run count so the sample-size discount
    # matches — re-running with fewer replicates would read as false drift.
    num_runs = int(baseline.get("num_runs") or 3)
    return await run_validation_v2(ss.uuid, "system", sources, num_runs=num_runs)


async def get_quality_by_model(days: int = 90) -> list[dict]:
    """Fleet-wide validation quality grouped by the model that ran.

    The per-item version of this (``model_comparison`` in
    ``get_quality_item_detail``) answers "which model is best for THIS item";
    this answers "how does each model do across everything we measured".
    Runs with ``model=None`` are reported under their own row rather than
    dropped — pre-attribution history and workflow runs graded over mixed
    models are a visible coverage gap, not something to hide.
    """
    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=days)
    runs = await ValidationRun.find(ValidationRun.created_at >= cutoff).to_list()

    by_model: dict[Optional[str], dict] = {}
    for r in runs:
        entry = by_model.setdefault(r.model, {
            "scores": [], "items": set(), "kinds": {}, "last_run_at": None,
        })
        entry["scores"].append(r.score)
        entry["items"].add((r.item_kind, r.item_id))
        kind_entry = entry["kinds"].setdefault(r.item_kind, {"scores": []})
        kind_entry["scores"].append(r.score)
        if entry["last_run_at"] is None or (r.created_at and r.created_at > entry["last_run_at"]):
            entry["last_run_at"] = r.created_at

    rows = []
    for model_name, e in by_model.items():
        rows.append({
            "model": model_name,
            "run_count": len(e["scores"]),
            "items_validated": len(e["items"]),
            "avg_score": round(sum(e["scores"]) / len(e["scores"]), 1),
            "kinds": {
                kind: {
                    "run_count": len(k["scores"]),
                    "avg_score": round(sum(k["scores"]) / len(k["scores"]), 1),
                }
                for kind, k in e["kinds"].items()
            },
            "last_run_at": e["last_run_at"].isoformat() if e["last_run_at"] else None,
        })
    # Attributed models first, best average first; the unattributed bucket last.
    rows.sort(key=lambda r: (r["model"] is None, -(r["avg_score"] or 0)))
    return rows


async def run_regression_suite(
    user_id: str,
    model: Optional[str] = None,
    suite_run=None,
) -> dict:
    """Run validation on all verified items and return summary.

    ``model`` is forwarded to every item kind that can execute under an
    explicit model (extraction and KB validation; workflow validation grades
    historical executions, so a model cannot be forced onto it).

    ``suite_run`` is an optional RegressionSuiteRun document — when given,
    progress and per-item results are written onto it as the sweep advances,
    so a watcher sees a live count instead of silence until the end.
    """
    from app.models.library import LibraryItem
    from app.services import extraction_validation_service
    from app.services import workflow_service

    items = await LibraryItem.find({"verified": True}).to_list()

    # The same underlying item can appear as several LibraryItem rows (one
    # per user who added it). Validate each (kind, item_id) once.
    seen: set[tuple[str, str]] = set()
    unique_items = []
    for item in items:
        kind = item.kind.value if hasattr(item.kind, "value") else str(item.kind)
        key = (kind, str(item.item_id))
        if key in seen:
            continue
        seen.add(key)
        unique_items.append((item, kind))

    if suite_run is not None:
        suite_run.total_items = len(unique_items)
        await suite_run.save()

    results = []
    for item, kind in unique_items:
        item_id_str = str(item.item_id)

        # Get previous score for delta
        prev = await get_latest_validation(kind, item_id_str)
        prev_score = prev["score"] if prev else None

        name = item_id_str
        try:
            if kind == "search_set":
                # Need the search_set uuid from the SearchSet document
                from app.models.search_set import SearchSet
                ss = await SearchSet.get(item.item_id)
                if not ss:
                    continue
                name = ss.title or item_id_str
                result = await extraction_validation_service.run_validation(
                    search_set_uuid=ss.uuid,
                    user_id=user_id,
                    model=model,
                )
                current_score = result.get("aggregate_accuracy", 0) or 0
                current_score = min(100.0, max(0.0, current_score * 60 + (result.get("aggregate_consistency", 0) or 0) * 40))
            elif kind == "workflow":
                from app.models.workflow import Workflow
                wf = await Workflow.get(item.item_id)
                if wf is not None:
                    name = getattr(wf, "name", "") or item_id_str
                result = await workflow_service.validate_workflow(item_id_str)
                # Prefer continuous score from new multi-run system
                result_score = result.get("score")
                if result_score is not None:
                    current_score = float(result_score)
                else:
                    grade = result.get("grade", "F")
                    current_score = float(_GRADE_SCORES.get(grade, 30))
            elif kind == "knowledge_base":
                from app.models.knowledge import KnowledgeBase as KB
                kb = await KB.get(item.item_id)
                if not kb:
                    continue
                name = kb.title or item_id_str
                from app.services import kb_validation_service
                result = await kb_validation_service.run_kb_validation(
                    kb_uuid=kb.uuid,
                    user_id=user_id,
                    model=model,
                )
                current_score = float(result.get("raw_score", 0))
            else:
                continue

            delta = round(current_score - prev_score, 1) if prev_score is not None else None
            results.append({
                "item_id": item_id_str,
                "kind": kind,
                "name": name,
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
                "name": name,
                "score": None,
                "grade": None,
                "prev_score": round(prev_score, 1) if prev_score is not None else None,
                "delta": None,
                "status": f"error: {e}",
            })

        if suite_run is not None:
            suite_run.completed_items = len(results)
            suite_run.succeeded = sum(1 for r in results if r["status"] == "ok")
            suite_run.failed = sum(1 for r in results if r["status"] != "ok")
            suite_run.results = results
            await suite_run.save()

    scores = [r["score"] for r in results if r["status"] == "ok" and r["score"] is not None]
    mean_score = round(sum(scores) / len(scores), 1) if scores else None

    return {
        "total_items": len(results),
        "succeeded": sum(1 for r in results if r["status"] == "ok"),
        "failed": sum(1 for r in results if r["status"] != "ok"),
        "mean_score": mean_score,
        "model": model,
        "results": results,
    }


# ---------------------------------------------------------------------------
# LLM Improvement Suggestions
# ---------------------------------------------------------------------------


async def generate_improvement_suggestions(
    item_kind: str,
    item_id: str,
    result: dict,
    user_id: str | None = None,
) -> str:
    """Use the LLM to suggest improvements when validation results fall below an A grade.

    For extractions: analyses accuracy/consistency weaknesses per field.
    For workflows: analyses failing/warning checks and suggests fixes.
    Returns a markdown string of suggestions.
    """
    try:
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
        elif item_kind == "knowledge_base":
            prompt = _build_kb_suggestion_prompt(result)
        else:
            prompt = _build_workflow_suggestion_prompt(result)

        agent = create_chat_agent(
            default_model,
            system_prompt=(
                "You help users improve LLM-based document extraction results. "
                "The user configures extractions by defining field names (called 'extraction keys') "
                "and optionally constraining them with enum values. The system sends these keys to an LLM "
                "which reads a document and returns values for each key.\n\n"
                "The ONLY things a user can change to improve results are:\n"
                "- Rename extraction keys to be clearer or more specific (e.g. 'name' → 'PI Full Name')\n"
                "- Add enum values to constrain a field to specific allowed values\n"
                "- Mark fields as optional if they don't always appear\n"
                "- Switch between one-pass and two-pass extraction modes\n"
                "- Enable or disable 'thinking' mode for the LLM\n"
                "- Change the LLM model\n\n"
                "Rules: Maximum 3-5 bullet points. No headings, no preamble. "
                "Each bullet is one specific, actionable sentence referencing the actual field names from the results. "
                "NEVER suggest training data, fine-tuning, regex post-processing, or anything outside the above options."
            ),
            system_config_doc=sys_config_doc,
        )
        from app.services.metering import metered_async
        async with metered_async("quality_suggestion", user_id=user_id):
            res = await agent.run(prompt)
        return res.output
    except Exception as exc:
        logger.exception("Failed to generate improvement suggestions for %s %s", item_kind, item_id)
        return f"Unable to generate suggestions: {exc}"


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
        lines.append(f"\n**{tc.get('label', 'Unknown')}** - Accuracy: {_fmt_pct(tc.get('overall_accuracy'))}, Consistency: {_fmt_pct(tc.get('overall_consistency'))}")
        for f in tc.get("fields", []):
            flag = ""
            if f.get("accuracy") is not None and f["accuracy"] < 0.9:
                flag = " [LOW ACCURACY]"
            if f.get("consistency") is not None and f["consistency"] < 0.9:
                flag += " [LOW CONSISTENCY]"
            lines.append(
                f"  - {f.get('field_name')}: expected={f.get('expected', 'N/A')}, "
                f"extracted={f.get('most_common_value', 'null')}, "
                f"accuracy={_fmt_pct(f.get('accuracy'))}, consistency={_fmt_pct(f.get('consistency'))}{flag}"
            )

    lines.append(
        "\n---\nLooking at the fields with the lowest accuracy, suggest 3-5 specific changes "
        "the user could make (renaming keys, adding enum constraints, marking optional, changing mode). "
        "Reference actual field names and expected vs extracted values. One sentence per bullet."
    )
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

    lines.append("\n---\nBased on these results, suggest specific improvements to raise the workflow quality to an A grade (all checks passing, no warnings). Focus on:\n1. Checks that failed: what might cause the failure and how to fix it\n2. Checks with warnings: how to address the concern\n3. General workflow structure improvements")
    return "\n".join(lines)


def _build_kb_suggestion_prompt(result: dict) -> str:
    health = result.get("source_health", {})
    coverage = result.get("chunk_coverage", {})
    retrieval = result.get("retrieval_precision", {})
    lines = [
        "## Knowledge Base Validation Results",
        f"- Source Health: {health.get('healthy', 0)}/{health.get('total', 0)} sources healthy ({health.get('ratio', 0) * 100:.0f}%)",
        f"- Chunk Coverage: {coverage.get('with_chunks', 0)}/{coverage.get('total', 0)} sources with chunks ({coverage.get('ratio', 0) * 100:.0f}%)",
        f"- Total Chunks: {coverage.get('total_chunks', 0)}",
        f"- Retrieval Precision: {retrieval.get('avg_precision', 0) * 100:.0f}% ({retrieval.get('total_queries', 0)} test queries)",
        "",
    ]
    # Unhealthy sources
    unhealthy = [d for d in health.get("details", []) if d.get("status") == "unhealthy"]
    if unhealthy:
        lines.append("### Unhealthy Sources:")
        for s in unhealthy:
            lines.append(f"  - {s['name']}: {s.get('error', 'Unknown error')}")
        lines.append("")

    # Low precision queries
    low_precision = [d for d in retrieval.get("details", []) if d.get("precision", 1) < 0.5]
    if low_precision:
        lines.append("### Low Precision Queries:")
        for q in low_precision:
            lines.append(f"  - \"{q['query']}\": {q['precision'] * 100:.0f}% precision")
        lines.append("")

    lines.append("\n---\nBased on these results, suggest specific improvements to raise the knowledge base quality. Focus on:\n"
                 "1. Unhealthy or dead sources that should be replaced\n"
                 "2. Ways to improve retrieval precision (better source selection, chunk size)\n"
                 "3. Coverage gaps: topics that need more sources")
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
        QualityAlert.acknowledged == False,  # noqa: E712
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
    elif item_kind == "knowledge_base":
        # KB-specific readiness checks
        from app.models.knowledge import KnowledgeBase
        from app.models.kb_test_query import KBTestQuery
        kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == item_id)
        if kb:
            if kb.total_sources < 3:
                issues.append(f"Only {kb.total_sources} source(s). A strong knowledge base should have at least 3 sources.")
            if kb.total_chunks < 50:
                recommendations.append(f"Knowledge base has {kb.total_chunks} chunks. Consider adding more sources for better coverage.")
            test_query_count = await KBTestQuery.find(
                KBTestQuery.knowledge_base_uuid == item_id,
            ).count()
            if test_query_count < 3:
                recommendations.append(f"Add at least {3 - test_query_count} more test query/queries for reliable retrieval validation.")

            # Check source health from latest validation
            source_health = result.get("source_health", {})
            if source_health and source_health.get("ratio", 1.0) < 0.8:
                issues.append(f"Source health is {source_health['ratio'] * 100:.0f}%. Fix unhealthy sources before submitting.")

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


async def get_latest_validation_run(item_kind: str, item_id: str) -> Optional[ValidationRun]:
    """Public accessor for the most recent ValidationRun of an item."""
    return await _get_latest_run(item_kind, item_id)


def _run_to_dict(r: ValidationRun) -> dict:
    # Surface judge-side trust signals out of result_snapshot so the sparkline
    # tooltip and KB quality header don't need to peek inside the blob. These
    # mirror the fields KB validation now writes into retrieval_precision.
    rp = (r.result_snapshot or {}).get("retrieval_precision") if isinstance(r.result_snapshot, dict) else None
    judge_variance = rp.get("judge_variance") if isinstance(rp, dict) else None
    judge_variance_meta = rp.get("judge_variance_meta") if isinstance(rp, dict) else None
    num_queries_judged = rp.get("num_queries_judged") if isinstance(rp, dict) else None
    judge_model = (r.result_snapshot or {}).get("judge_model") if isinstance(r.result_snapshot, dict) else None
    eval_mode = (r.result_snapshot or {}).get("mode") if isinstance(r.result_snapshot, dict) else None
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
        # Surfaced trust signals (None when missing — older runs).
        "judge_model": judge_model,
        "judge_variance": judge_variance,
        "judge_variance_meta": judge_variance_meta,
        "num_queries_judged": num_queries_judged,
        "mode": eval_mode,
        # Provenance — Phase 4 unification. None for legacy runs.
        "source": getattr(r, "source", None),
        "source_run_uuid": getattr(r, "source_run_uuid", None),
    }
