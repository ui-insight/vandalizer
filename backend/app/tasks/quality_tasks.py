"""Quality monitoring Celery tasks - detect regressions, staleness, config changes."""

import asyncio
import datetime
import logging

from app.celery_app import celery
from app.tasks import TRANSIENT_EXCEPTIONS

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from sync Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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
    from app.models.verification import VerifiedItemMetadata
    from app.services.quality_service import compute_config_hash, detect_stale_items

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
            QualityAlert.acknowledged == False,
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
            QualityAlert.acknowledged == False,
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
                except Exception as e:
                    logger.warning(
                        "Auto-revalidation failed for knowledge_base %s: %s",
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


