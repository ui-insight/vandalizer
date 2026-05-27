"""Tests for the monthly passive re-validation of applied KB tunings."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import kb_validation_tasks


def _make_kb(uuid="kb-1", user_id="u1", title="My KB", run_uuid="opt-1"):
    kb = MagicMock()
    kb.uuid = uuid
    kb.user_id = user_id
    kb.title = title
    kb.rag_config_override = {"k": 8}
    kb.rag_config_override_run_uuid = run_uuid
    return kb


def _make_run(uuid="opt-1", optimized_score=0.80):
    run = MagicMock()
    run.uuid = uuid
    run.optimized_score = optimized_score
    return run


def _patched(kbs, optimization_runs, validation_results):
    """Helper that wires the four model/service mocks into the task body."""
    kb_find = MagicMock()
    kb_find.to_list = AsyncMock(return_value=kbs)

    async def _find_one(query):
        # Beanie passes a comparison expression; we just look at our mapping.
        return optimization_runs.get(0)

    async def _run_kb_validation(kb_uuid, user_id, mode="judge"):
        return validation_results[kb_uuid]

    return (
        patch("app.database.init_db", new=AsyncMock()),
        patch("app.models.knowledge.KnowledgeBase.find", return_value=kb_find),
        patch(
            "app.models.kb_optimization_run.KBOptimizationRun.find_one",
            side_effect=lambda *a, **kw: AsyncMock(
                return_value=list(optimization_runs.values())[0]
                if optimization_runs else None,
            )(),
        ),
        patch(
            "app.services.kb_validation_service.run_kb_validation",
            new=AsyncMock(side_effect=_run_kb_validation),
        ),
        patch("app.models.validation_run.ValidationRun.insert", new=AsyncMock()),
        patch("app.models.quality_alert.QualityAlert.insert", new=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_passive_revalidate_emits_quality_alert_on_regression():
    """A KB whose blended score dropped >10pts since apply should get a
    regression QualityAlert with delta and previous/current scores."""
    kb = _make_kb()
    run = _make_run(optimized_score=0.80)

    # Current re-validation: 65% (raw_score is 0..100). Delta = 0.65 - 0.80 = -0.15.
    validation_results = {
        "kb-1": {
            "raw_score": 65.0,
            "retrieval_precision": {"num_queries_judged": 6},
        },
    }

    inserted_alerts: list = []

    class _Alert:
        def __init__(self, **kw):
            self.kw = kw
            inserted_alerts.append(kw)

        async def insert(self):
            return self

    with patch("app.database.init_db", new=AsyncMock()), \
         patch("app.models.knowledge.KnowledgeBase.find",
               return_value=MagicMock(to_list=AsyncMock(return_value=[kb]))), \
         patch("app.models.kb_optimization_run.KBOptimizationRun.find_one",
               new=AsyncMock(return_value=run)), \
         patch("app.services.kb_validation_service.run_kb_validation",
               new=AsyncMock(return_value=validation_results["kb-1"])), \
         patch("app.models.validation_run.ValidationRun") as VR, \
         patch("app.models.quality_alert.QualityAlert") as QA:
        VR.return_value.insert = AsyncMock()
        QA.side_effect = _Alert

        result = await kb_validation_tasks._kb_revalidate_applied_async()

    assert result == {"rechecked": 1, "regressions": 1, "scanned": 1}
    assert len(inserted_alerts) == 1
    alert = inserted_alerts[0]
    assert alert["alert_type"] == "regression"
    assert alert["item_kind"] == "knowledge_base"
    assert alert["item_id"] == "kb-1"
    # 15pts drop is warning (≥-20pts), not critical.
    assert alert["severity"] == "warning"
    assert alert["previous_score"] == 80.0
    assert alert["current_score"] == 65.0


@pytest.mark.asyncio
async def test_passive_revalidate_critical_on_large_drop():
    """A drop ≥20pts should classify as critical severity."""
    kb = _make_kb()
    run = _make_run(optimized_score=0.85)
    # Drop of 25pts: 0.85 → 0.60.
    validation_results = {
        "kb-1": {
            "raw_score": 60.0,
            "retrieval_precision": {"num_queries_judged": 8},
        },
    }
    inserted: list = []

    class _Alert:
        def __init__(self, **kw):
            inserted.append(kw)

        async def insert(self):
            return self

    with patch("app.database.init_db", new=AsyncMock()), \
         patch("app.models.knowledge.KnowledgeBase.find",
               return_value=MagicMock(to_list=AsyncMock(return_value=[kb]))), \
         patch("app.models.kb_optimization_run.KBOptimizationRun.find_one",
               new=AsyncMock(return_value=run)), \
         patch("app.services.kb_validation_service.run_kb_validation",
               new=AsyncMock(return_value=validation_results["kb-1"])), \
         patch("app.models.validation_run.ValidationRun") as VR, \
         patch("app.models.quality_alert.QualityAlert") as QA:
        VR.return_value.insert = AsyncMock()
        QA.side_effect = _Alert

        await kb_validation_tasks._kb_revalidate_applied_async()

    assert len(inserted) == 1
    assert inserted[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_passive_revalidate_no_alert_when_n_too_small():
    """Regression on n<5 queries is too noisy to alert on — silently skip."""
    kb = _make_kb()
    run = _make_run(optimized_score=0.80)
    validation_results = {
        "kb-1": {
            "raw_score": 50.0,
            "retrieval_precision": {"num_queries_judged": 3},  # < REGRESSION_MIN_QUERIES
        },
    }
    inserted_alerts: list = []

    class _Alert:
        def __init__(self, **kw):
            inserted_alerts.append(kw)

        async def insert(self):
            return self

    with patch("app.database.init_db", new=AsyncMock()), \
         patch("app.models.knowledge.KnowledgeBase.find",
               return_value=MagicMock(to_list=AsyncMock(return_value=[kb]))), \
         patch("app.models.kb_optimization_run.KBOptimizationRun.find_one",
               new=AsyncMock(return_value=run)), \
         patch("app.services.kb_validation_service.run_kb_validation",
               new=AsyncMock(return_value=validation_results["kb-1"])), \
         patch("app.models.validation_run.ValidationRun") as VR, \
         patch("app.models.quality_alert.QualityAlert") as QA:
        VR.return_value.insert = AsyncMock()
        QA.side_effect = _Alert

        result = await kb_validation_tasks._kb_revalidate_applied_async()

    assert result["regressions"] == 0
    assert inserted_alerts == []


@pytest.mark.asyncio
async def test_passive_revalidate_skips_kbs_without_applied_run():
    """KBs whose linked optimization run doesn't exist or has no
    optimized_score are silently skipped — neither a re-judge nor an alert."""
    kb = _make_kb(run_uuid="missing-run")

    with patch("app.database.init_db", new=AsyncMock()), \
         patch("app.models.knowledge.KnowledgeBase.find",
               return_value=MagicMock(to_list=AsyncMock(return_value=[kb]))), \
         patch("app.models.kb_optimization_run.KBOptimizationRun.find_one",
               new=AsyncMock(return_value=None)), \
         patch("app.services.kb_validation_service.run_kb_validation",
               new=AsyncMock(side_effect=AssertionError("should not be called"))):
        result = await kb_validation_tasks._kb_revalidate_applied_async()

    assert result == {"rechecked": 0, "regressions": 0, "scanned": 1}


def test_passive_revalidate_in_beat_schedule_and_registered():
    """Sanity check: monthly schedule wired to the registered task."""
    from app.celery_app import celery
    assert "tasks.passive.kb_revalidate_applied" in celery.tasks
    assert "kb-revalidate-applied-monthly" in celery.conf.beat_schedule
    schedule_entry = celery.conf.beat_schedule["kb-revalidate-applied-monthly"]
    assert schedule_entry["task"] == "tasks.passive.kb_revalidate_applied"
