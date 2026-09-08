"""Quality monitoring Celery tasks - detect regressions, staleness, config changes."""

import datetime
import logging

from app.celery_app import celery
from app.tasks import TRANSIENT_EXCEPTIONS, run_task_async

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from sync Celery task context, releasing the
    loop's pooled LLM HTTP client on teardown (see ``run_task_async``)."""
    return run_task_async(coro)


@celery.task(
    bind=True,
    name="tasks.passive.quality_monitor",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=10,
)
def quality_monitor(self):
    """Daily quality monitoring task.

    1. Detect config changes since last validation runs
    2. Detect stale verified items
    3. Auto-revalidate verified items with test cases (if enabled)
    4. Detect regressions and create alerts
    """
    _run_async(_quality_monitor_async())


async def _quality_monitor_async():
    from app.config import Settings
    from app.database import init_db

    settings = Settings()
    await init_db(settings)

    from app.models.quality_alert import QualityAlert
    from app.models.system_config import SystemConfig
    from app.models.validation_run import ValidationRun
    from app.models.verification import VerificationRequest, VerificationStatus, VerifiedItemMetadata
    from app.services.quality_service import (
        compute_config_hash,
        detect_stale_items,
        flag_quality_regression,
    )
    from beanie import PydanticObjectId

    sys_cfg = await SystemConfig.get_config()
    qc = sys_cfg.get_quality_config()
    monitoring = qc.get("monitoring", {})
    stale_days = monitoring.get("stale_threshold_days", 14)
    degradation_threshold = monitoring.get("degradation_alert_threshold", 10)
    auto_revalidate = monitoring.get("auto_revalidate", False)
    revalidate_days = monitoring.get("revalidate_interval_days", 7)
    now = datetime.datetime.now(datetime.timezone.utc)

    # 1. Detect config changes
    current_extraction_config = sys_cfg.get_extraction_config()
    current_hash = compute_config_hash(current_extraction_config)

    # Find the most recent validation run to compare config hash
    latest_runs = await ValidationRun.find_all().sort("-created_at").limit(1).to_list()
    if latest_runs and latest_runs[0].config_hash and latest_runs[0].config_hash != current_hash:
        # Check if we already have an unacknowledged config_changed alert
        existing = await QualityAlert.find_one(
            QualityAlert.alert_type == "config_changed",
            QualityAlert.acknowledged == False,  # noqa: E712
        )
        if not existing:
            await QualityAlert(
                alert_type="config_changed",
                item_kind="system",
                item_id="extraction_config",
                item_name="System Extraction Config",
                severity="warning",
                message="System extraction config has changed since the last validation run. Consider re-validating affected items.",
                created_at=now,
            ).insert()

    # 2. Detect stale items
    stale_items = await detect_stale_items(stale_days)
    for item in stale_items:
        existing = await QualityAlert.find_one(
            QualityAlert.alert_type == "stale",
            QualityAlert.item_kind == item["item_kind"],
            QualityAlert.item_id == item["item_id"],
            QualityAlert.acknowledged == False,  # noqa: E712
        )
        if not existing:
            await QualityAlert(
                alert_type="stale",
                item_kind=item["item_kind"],
                item_id=item["item_id"],
                item_name=item["display_name"],
                severity="info",
                message=f"Last validated {item['last_validated_at'] or 'never'}. Consider re-validating.",
                current_score=item["quality_score"],
                current_tier=item["quality_tier"],
                created_at=now,
            ).insert()

    # 3. Auto-revalidate verified items if enabled
    if auto_revalidate:
        cutoff = now - datetime.timedelta(days=revalidate_days)
        items_to_revalidate = await VerifiedItemMetadata.find(
            VerifiedItemMetadata.last_validated_at < cutoff,
        ).to_list()

        from app.models.extraction_test_case import ExtractionTestCase
        from app.models.kb_test_query import KBTestQuery
        from app.services import extraction_validation_service

        for meta in items_to_revalidate:
            if meta.item_kind == "knowledge_base":
                # Auto-revalidate knowledge bases
                test_queries = await KBTestQuery.find(
                    KBTestQuery.knowledge_base_uuid == meta.item_id,
                ).to_list()
                if not test_queries:
                    continue
                try:
                    prev_score = meta.quality_score
                    prev_tier = meta.quality_tier

                    from app.services import kb_validation_service
                    await kb_validation_service.run_kb_validation(
                        kb_uuid=meta.item_id,
                        user_id="system",
                    )

                    await meta.sync()
                    if prev_score is not None and meta.quality_score is not None:
                        delta = prev_score - meta.quality_score
                        if delta >= degradation_threshold:
                            await QualityAlert(
                                alert_type="regression",
                                item_kind=meta.item_kind,
                                item_id=meta.item_id,
                                item_name=meta.display_name or meta.item_id,
                                severity="critical" if delta >= 20 else "warning",
                                message=f"Quality dropped by {delta:.1f} points ({prev_score:.1f} -> {meta.quality_score:.1f})",
                                previous_score=prev_score,
                                current_score=meta.quality_score,
                                previous_tier=prev_tier,
                                current_tier=meta.quality_tier,
                                created_at=now,
                            ).insert()
                            await flag_quality_regression(
                                meta=meta,
                                severity="critical" if delta >= 20 else "warning",
                                previous_score=prev_score,
                                current_score=meta.quality_score,
                                detected_at=now,
                            )
                            # Phase 6: auto-enqueue a shadow KB optimizer so the
                            # candidate fix lands in the inbox alongside the alert.
                            try:
                                from app.services import optimizer_signal_service
                                await optimizer_signal_service.enqueue_kb_shadow_run(
                                    kb_uuid=meta.item_id,
                                    user_id="system",
                                    trigger="quality_alert",
                                    trigger_detail={
                                        "delta": round(float(delta), 2),
                                        "prev_score": round(float(prev_score), 2),
                                        "current_score": round(float(meta.quality_score), 2),
                                    },
                                )
                            except Exception:
                                logger.warning(
                                    "Phase 6 shadow KB run trigger failed for %s",
                                    meta.item_id, exc_info=True,
                                )
                except Exception as e:
                    logger.warning(
                        "Auto-revalidation failed for knowledge_base %s: %s",
                        meta.item_id, e,
                    )
                continue

            if meta.item_kind == "workflow":
                # Revalidate workflows that have a validation plan
                from app.models.workflow import Workflow
                from app.services import workflow_service
                from beanie import PydanticObjectId

                try:
                    wf = await Workflow.get(PydanticObjectId(meta.item_id))
                except Exception:
                    wf = None
                if not wf or not wf.validation_plan:
                    continue

                try:
                    prev_score = meta.quality_score
                    prev_tier = meta.quality_tier

                    await workflow_service.validate_workflow(str(wf.id))

                    await meta.sync()
                    if prev_score is not None and meta.quality_score is not None:
                        delta = prev_score - meta.quality_score
                        if delta >= degradation_threshold:
                            await QualityAlert(
                                alert_type="regression",
                                item_kind=meta.item_kind,
                                item_id=meta.item_id,
                                item_name=meta.display_name or meta.item_id,
                                severity="critical" if delta >= 20 else "warning",
                                message=f"Quality dropped by {delta:.1f} points ({prev_score:.1f} -> {meta.quality_score:.1f})",
                                previous_score=prev_score,
                                current_score=meta.quality_score,
                                previous_tier=prev_tier,
                                current_tier=meta.quality_tier,
                                created_at=now,
                            ).insert()
                            await flag_quality_regression(
                                meta=meta,
                                severity="critical" if delta >= 20 else "warning",
                                previous_score=prev_score,
                                current_score=meta.quality_score,
                                detected_at=now,
                            )

                            # Phase 6: shadow workflow optimizer.
                            try:
                                from app.services import optimizer_signal_service
                                await optimizer_signal_service.enqueue_workflow_shadow_run(
                                    workflow_id=meta.item_id,
                                    user_id="system",
                                    trigger="quality_alert",
                                    trigger_detail={
                                        "delta": round(float(delta), 2),
                                        "prev_score": round(float(prev_score), 2),
                                        "current_score": round(float(meta.quality_score), 2),
                                    },
                                )
                            except Exception:
                                logger.warning(
                                    "Phase 6 shadow workflow run trigger failed for %s",
                                    meta.item_id, exc_info=True,
                                )

                            if monitoring.get("auto_review_on_degradation", False):
                                from app.models.verification import VerificationRequest
                                await VerificationRequest(
                                    item_kind=meta.item_kind,
                                    item_id=meta.item_id,
                                    submitter_user_id="system",
                                    summary=f"Auto-review: quality degradation detected ({prev_score:.1f} -> {meta.quality_score:.1f})",
                                    submitted_at=now,
                                ).insert()
                except Exception as e:
                    logger.warning(
                        "Auto-revalidation failed for workflow %s: %s",
                        meta.item_id, e,
                    )
                continue

            if meta.item_kind != "search_set":
                continue
            # Only revalidate if test cases exist
            test_cases = await ExtractionTestCase.find(
                ExtractionTestCase.search_set_uuid == meta.item_id,
            ).to_list()
            if not test_cases:
                continue

            try:
                prev_score = meta.quality_score
                prev_tier = meta.quality_tier

                await extraction_validation_service.run_validation(
                    search_set_uuid=meta.item_id,
                    user_id="system",
                )

                # Reload metadata to check for regression
                await meta.sync()
                if prev_score is not None and meta.quality_score is not None:
                    delta = prev_score - meta.quality_score
                    if delta >= degradation_threshold:
                        await QualityAlert(
                            alert_type="regression",
                            item_kind=meta.item_kind,
                            item_id=meta.item_id,
                            item_name=meta.display_name or meta.item_id,
                            severity="critical" if delta >= 20 else "warning",
                            message=f"Quality dropped by {delta:.1f} points ({prev_score:.1f} -> {meta.quality_score:.1f})",
                            previous_score=prev_score,
                            current_score=meta.quality_score,
                            previous_tier=prev_tier,
                            current_tier=meta.quality_tier,
                            created_at=now,
                        ).insert()
                        await flag_quality_regression(
                            meta=meta,
                            severity="critical" if delta >= 20 else "warning",
                            previous_score=prev_score,
                            current_score=meta.quality_score,
                            detected_at=now,
                        )

                        # Phase 6: shadow extraction optimizer.
                        try:
                            from app.services import optimizer_signal_service
                            await optimizer_signal_service.enqueue_extraction_shadow_run(
                                search_set_uuid=meta.item_id,
                                user_id="system",
                                trigger="quality_alert",
                                trigger_detail={
                                    "delta": round(float(delta), 2),
                                    "prev_score": round(float(prev_score), 2),
                                    "current_score": round(float(meta.quality_score), 2),
                                },
                            )
                        except Exception:
                            logger.warning(
                                "Phase 6 shadow extraction run trigger failed for %s",
                                meta.item_id, exc_info=True,
                            )

                        # Auto-create verification request if configured
                        if monitoring.get("auto_review_on_degradation", False):
                            from app.models.verification import VerificationRequest
                            await VerificationRequest(
                                item_kind=meta.item_kind,
                                item_id=meta.item_id,
                                submitter_user_id="system",
                                summary=f"Auto-review: quality degradation detected ({prev_score:.1f} -> {meta.quality_score:.1f})",
                                submitted_at=now,
                            ).insert()

            except Exception as e:
                logger.warning(
                    "Auto-revalidation failed for %s %s: %s",
                    meta.item_kind, meta.item_id, e,
                )

    # 4. Phase E: Baseline drift monitoring.
    # For each verified item with a pinned official_baseline_score, measure the
    # live config against the pinned score. With baseline_reexecution enabled,
    # extraction baselines are actually re-run (LLM calls — that's why it's a
    # config gate, default off); otherwise, and for the kinds that can't be
    # replayed, the item's latest validation score stands in as a cheap proxy.
    # Either way last_drift_basis records which one was measured. Stamps
    # last_drift_check_at so the UI can show "checked X ago" even without drift.
    from app.services.quality_service import reexecute_official_baseline

    reexec_enabled = monitoring.get("baseline_reexecution", False)
    pinned_metas = await VerifiedItemMetadata.find(
        VerifiedItemMetadata.official_baseline_score != None,  # noqa: E711
    ).to_list()

    for meta in pinned_metas:
        try:
            current = meta.quality_score
            basis = "latest_validation_proxy"
            if reexec_enabled:
                reexec = await reexecute_official_baseline(meta)
                if reexec is not None:
                    # The re-execution persisted a ValidationRun and refreshed
                    # the quality metadata — reload before writing drift fields
                    # so the save below doesn't clobber the newer scores.
                    fresh = await VerifiedItemMetadata.get(meta.id)
                    if fresh is not None:
                        meta = fresh
                    current = reexec.get("score")
                    basis = "baseline_reexecution"
            pinned = meta.official_baseline_score
            meta.last_drift_check_at = now
            meta.last_drift_score = current
            meta.last_drift_basis = basis
            if current is not None and pinned is not None:
                drift = pinned - current
                if drift >= degradation_threshold:
                    existing = await QualityAlert.find_one(
                        QualityAlert.alert_type == "baseline_drift",
                        QualityAlert.item_kind == meta.item_kind,
                        QualityAlert.item_id == meta.item_id,
                        QualityAlert.acknowledged == False,  # noqa: E712
                    )
                    if not existing:
                        await QualityAlert(
                            alert_type="baseline_drift",
                            item_kind=meta.item_kind,
                            item_id=meta.item_id,
                            item_name=meta.display_name or meta.item_id,
                            severity="critical" if drift >= 20 else "warning",
                            message=(
                                f"Quality has drifted {drift:.1f} pts below the official baseline "
                                f"({pinned:.1f} pinned -> {current:.1f} now, "
                                + (
                                    "measured by re-running the pinned baseline)."
                                    if basis == "baseline_reexecution"
                                    else "latest-validation proxy — not a baseline re-run)."
                                )
                            ),
                            previous_score=pinned,
                            current_score=current,
                            previous_tier=None,
                            current_tier=meta.quality_tier,
                            created_at=now,
                        ).insert()

                        # Optional: auto-flag for re-review if configured.
                        # Does NOT un-verify — admin still has to act.
                        if monitoring.get("auto_review_on_degradation", False):
                            try:
                                item_obj_id = PydanticObjectId(meta.item_id)
                            except Exception:
                                item_obj_id = None
                            if item_obj_id is not None:
                                existing_req = await VerificationRequest.find_one(
                                    {
                                        "item_kind": meta.item_kind,
                                        "item_id": item_obj_id,
                                        "status": {"$in": [
                                            VerificationStatus.SUBMITTED.value,
                                            VerificationStatus.IN_REVIEW.value,
                                        ]},
                                    }
                                )
                                if not existing_req:
                                    await VerificationRequest(
                                        item_kind=meta.item_kind,
                                        item_id=item_obj_id,
                                        submitter_user_id="system",
                                        summary=(
                                            f"Auto re-review: baseline drift {drift:.1f} pts "
                                            f"({pinned:.1f} -> {current:.1f})"
                                        ),
                                        validation_origin="unvalidated_legacy",
                                        submitted_at=now,
                                    ).insert()
            await meta.save()
        except Exception as e:
            logger.warning(
                "Baseline drift check failed for %s %s: %s",
                meta.item_kind, meta.item_id, e,
            )


# ---------------------------------------------------------------------------
# Auto-validate after runs
# ---------------------------------------------------------------------------


@celery.task(
    name="tasks.passive.auto_validate_extraction",
    bind=True,
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=1,
    default_retry_delay=10,
)
def auto_validate_extraction(self, search_set_uuid, user_id, model=None):
    """Auto-run validation after extraction if test cases exist."""
    _run_async(_auto_validate_extraction_async(search_set_uuid, user_id, model))


async def _auto_validate_extraction_async(search_set_uuid, user_id, model=None):
    from app.config import Settings
    from app.database import init_db

    settings = Settings()
    await init_db(settings)

    from app.models.extraction_test_case import ExtractionTestCase
    from app.services import extraction_validation_service

    count = await ExtractionTestCase.find(
        ExtractionTestCase.search_set_uuid == search_set_uuid,
    ).count()
    if count > 0:
        await extraction_validation_service.run_validation(
            search_set_uuid=search_set_uuid,
            user_id=user_id,
            model=model,
        )


@celery.task(
    name="tasks.passive.auto_validate_workflow",
    bind=True,
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=1,
    default_retry_delay=10,
)
def auto_validate_workflow(self, workflow_id):
    """Auto-run workflow validation after execution if validation plan exists."""
    _run_async(_auto_validate_workflow_async(workflow_id))


async def _auto_validate_workflow_async(workflow_id):
    from app.config import Settings
    from app.database import init_db

    settings = Settings()
    await init_db(settings)

    from app.models.workflow import Workflow
    from app.services import workflow_service

    wf = await Workflow.get(workflow_id)
    if wf and wf.validation_plan:
        await workflow_service.validate_workflow(str(wf.id))




@celery.task(
    name="tasks.passive.regression_suite",
    bind=True,
    # No autoretry: a partial re-run would re-validate items that already
    # completed, double-spending LLM calls. The failure is recorded on the
    # RegressionSuiteRun document instead.
    max_retries=0,
)
def regression_suite_task(self, suite_uuid: str):
    """Run the admin regression suite (all verified items) in the background."""
    _run_async(_regression_suite_async(suite_uuid))


async def _regression_suite_async(suite_uuid: str):
    from app.config import Settings
    from app.database import init_db

    settings = Settings()
    await init_db(settings)

    from app.models.regression_suite_run import RegressionSuiteRun
    from app.services.quality_service import run_regression_suite

    suite = await RegressionSuiteRun.find_one(RegressionSuiteRun.uuid == suite_uuid)
    if suite is None:
        logger.warning("Regression suite %s not found; nothing to run", suite_uuid)
        return

    try:
        summary = await run_regression_suite(
            suite.user_id, suite.model, suite_run=suite,
        )
        suite.status = "completed"
        suite.total_items = summary["total_items"]
        suite.completed_items = summary["total_items"]
        suite.succeeded = summary["succeeded"]
        suite.failed = summary["failed"]
        suite.mean_score = summary["mean_score"]
        suite.results = summary["results"]
    except Exception as e:
        logger.exception("Regression suite %s failed", suite_uuid)
        suite.status = "failed"
        suite.error = str(e)
    suite.finished_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await suite.save()
