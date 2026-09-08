"""Regression suite: deduped sweep, model forwarding, aggregate mean, job doc.

The suite is the one surface that answers "how does model X do over the
verified catalog" — these pin the properties that make the answer usable:
each item validated once, the requested model actually forwarded to the
kinds that can honor it, a catalog-wide mean, and progress persisted on the
RegressionSuiteRun document instead of vanishing with the HTTP request.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.quality_service import run_regression_suite


def _library_item(kind: str, item_id: str):
    return SimpleNamespace(kind=kind, item_id=item_id)


def _find_returning(items):
    m = MagicMock()
    m.to_list = AsyncMock(return_value=items)
    return MagicMock(return_value=m)


def _extraction_result(accuracy=1.0, consistency=1.0):
    return {"aggregate_accuracy": accuracy, "aggregate_consistency": consistency, "grade": None}


@pytest.mark.asyncio
async def test_duplicate_library_rows_validate_once_and_model_is_forwarded():
    # The same search set added by two users appears as two LibraryItem rows;
    # the sweep must validate it once, under the requested model.
    items = [
        _library_item("search_set", "ss-1"),
        _library_item("search_set", "ss-1"),
    ]
    ss = SimpleNamespace(uuid="ss-uuid-1", title="Grant Fields")

    with (
        patch("app.models.library.LibraryItem.find", _find_returning(items)),
        patch("app.models.search_set.SearchSet.get", new_callable=AsyncMock, return_value=ss),
        patch(
            "app.services.extraction_validation_service.run_validation",
            new_callable=AsyncMock, return_value=_extraction_result(),
        ) as mock_rv,
        patch(
            "app.services.quality_service.get_latest_validation",
            new_callable=AsyncMock, return_value=None,
        ),
    ):
        summary = await run_regression_suite("admin-1", model="req-model")

    assert mock_rv.await_count == 1
    assert mock_rv.await_args.kwargs["model"] == "req-model"
    assert summary["total_items"] == 1
    assert summary["results"][0]["name"] == "Grant Fields"
    assert summary["model"] == "req-model"


@pytest.mark.asyncio
async def test_kb_branch_receives_the_model_and_mean_covers_ok_items_only():
    items = [
        _library_item("search_set", "ss-1"),
        _library_item("knowledge_base", "kb-1"),
        _library_item("workflow", "wf-1"),
    ]
    ss = SimpleNamespace(uuid="ss-uuid-1", title="Grant Fields")
    kb = SimpleNamespace(uuid="kb-uuid-1", title="NSF PAPPG")

    with (
        patch("app.models.library.LibraryItem.find", _find_returning(items)),
        patch("app.models.search_set.SearchSet.get", new_callable=AsyncMock, return_value=ss),
        patch(
            "app.services.extraction_validation_service.run_validation",
            new_callable=AsyncMock, return_value=_extraction_result(1.0, 1.0),  # 100
        ),
        patch("app.models.knowledge.KnowledgeBase.get", new_callable=AsyncMock, return_value=kb),
        patch(
            "app.services.kb_validation_service.run_kb_validation",
            new_callable=AsyncMock, return_value={"raw_score": 80.0, "grade": None},
        ) as mock_kb,
        patch("app.models.workflow.Workflow.get", new_callable=AsyncMock, return_value=None),
        patch(
            "app.services.workflow_service.validate_workflow",
            new_callable=AsyncMock, side_effect=RuntimeError("no completed runs"),
        ),
        patch(
            "app.services.quality_service.get_latest_validation",
            new_callable=AsyncMock, return_value=None,
        ),
    ):
        summary = await run_regression_suite("admin-1", model="req-model")

    assert mock_kb.await_args.kwargs["model"] == "req-model"
    assert summary["succeeded"] == 2
    assert summary["failed"] == 1
    # Mean over the two items that validated: (100 + 80) / 2 — the failed
    # workflow must not drag a fabricated zero into the catalog mean.
    assert summary["mean_score"] == 90.0
    kb_row = next(r for r in summary["results"] if r["kind"] == "knowledge_base")
    assert kb_row["name"] == "NSF PAPPG"


@pytest.mark.asyncio
async def test_suite_run_document_receives_progress_and_results():
    items = [_library_item("search_set", "ss-1")]
    ss = SimpleNamespace(uuid="ss-uuid-1", title="Grant Fields")
    suite = MagicMock()
    suite.save = AsyncMock()

    with (
        patch("app.models.library.LibraryItem.find", _find_returning(items)),
        patch("app.models.search_set.SearchSet.get", new_callable=AsyncMock, return_value=ss),
        patch(
            "app.services.extraction_validation_service.run_validation",
            new_callable=AsyncMock, return_value=_extraction_result(),
        ),
        patch(
            "app.services.quality_service.get_latest_validation",
            new_callable=AsyncMock, return_value=None,
        ),
    ):
        await run_regression_suite("admin-1", model=None, suite_run=suite)

    assert suite.total_items == 1
    assert suite.completed_items == 1
    assert suite.succeeded == 1
    assert suite.results and suite.results[0]["status"] == "ok"
    # Saved at least twice: once for total_items, once per completed item.
    assert suite.save.await_count >= 2


@pytest.mark.asyncio
async def test_task_marks_suite_failed_on_exception():
    from app.tasks.quality_tasks import _regression_suite_async

    suite = MagicMock()
    suite.user_id = "admin-1"
    suite.model = "req-model"
    suite.save = AsyncMock()

    # Patch the whole Document class: field expressions like
    # ``RegressionSuiteRun.uuid == x`` only work after init_beanie.
    mock_cls = MagicMock()
    mock_cls.find_one = AsyncMock(return_value=suite)

    with (
        patch("app.database.init_db", new_callable=AsyncMock),
        patch("app.models.regression_suite_run.RegressionSuiteRun", mock_cls),
        patch(
            "app.services.quality_service.run_regression_suite",
            new_callable=AsyncMock, side_effect=RuntimeError("mongo down"),
        ),
    ):
        await _regression_suite_async("suite-1")

    assert suite.status == "failed"
    assert "mongo down" in suite.error
    assert suite.finished_at is not None
    suite.save.assert_awaited_once()
