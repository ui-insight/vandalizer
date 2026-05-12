"""Unit tests for Sprint 2 notification triggers — quality alerts + workflow completion.

Covers:
- _resolve_item_owner returns the correct user_id per item_kind
- _create_alert_and_notify fires a notification when an owner resolves
- _create_alert_and_notify is a no-op (for notifications) for system alerts
- _notify_workflow_completed_sync skips trivial runs and unowned workflows
- _notify_workflow_completed_sync builds the right notification document
"""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _resolve_item_owner
# ---------------------------------------------------------------------------

async def test_resolve_owner_system_kind_returns_none():
    from app.tasks.quality_tasks import _resolve_item_owner

    assert await _resolve_item_owner("system", "x") is None
    assert await _resolve_item_owner("", "x") is None
    assert await _resolve_item_owner("workflow", "") is None


async def test_resolve_owner_workflow_uses_created_by():
    from app.tasks.quality_tasks import _resolve_item_owner

    wf = MagicMock()
    wf.created_by_user_id = "alice"
    wf.user_id = "alice-fallback"

    with patch("app.models.workflow.Workflow.get", new=AsyncMock(return_value=wf)):
        owner = await _resolve_item_owner("workflow", "507f1f77bcf86cd799439011")
    assert owner == "alice"


async def test_resolve_owner_workflow_falls_back_to_user_id():
    from app.tasks.quality_tasks import _resolve_item_owner

    wf = MagicMock()
    wf.created_by_user_id = None
    wf.user_id = "bob"

    with patch("app.models.workflow.Workflow.get", new=AsyncMock(return_value=wf)):
        owner = await _resolve_item_owner("workflow", "507f1f77bcf86cd799439011")
    assert owner == "bob"


async def test_resolve_owner_skips_system_user():
    """The auto-revalidation submitter is 'system' — skip those."""
    from app.tasks.quality_tasks import _resolve_item_owner

    wf = MagicMock()
    wf.created_by_user_id = "system"
    wf.user_id = None

    with patch("app.models.workflow.Workflow.get", new=AsyncMock(return_value=wf)):
        owner = await _resolve_item_owner("workflow", "507f1f77bcf86cd799439011")
    assert owner is None


async def test_resolve_owner_missing_item_returns_none():
    from app.tasks.quality_tasks import _resolve_item_owner

    with patch("app.models.workflow.Workflow.get", new=AsyncMock(return_value=None)):
        owner = await _resolve_item_owner("workflow", "507f1f77bcf86cd799439011")
    assert owner is None


async def test_resolve_owner_unknown_kind_returns_none():
    from app.tasks.quality_tasks import _resolve_item_owner

    owner = await _resolve_item_owner("widget", "anything")
    assert owner is None


# ---------------------------------------------------------------------------
# _create_alert_and_notify
# ---------------------------------------------------------------------------

def _patch_alert_insert():
    """Patch QualityAlert in quality_tasks so insertion is a no-op (we only
    care about the notification side-effect)."""
    klass = MagicMock()

    def _ctor(**kwargs):
        inst = MagicMock()
        for k, v in kwargs.items():
            setattr(inst, k, v)
        inst.insert = AsyncMock()
        return inst

    klass.side_effect = _ctor
    return patch("app.models.quality_alert.QualityAlert", new=klass)


async def test_create_alert_and_notify_skips_system_kind():
    """System alerts have no owner — should not fire a notification."""
    from app.tasks.quality_tasks import _create_alert_and_notify

    create_notif = AsyncMock(return_value={})
    stack = ExitStack()
    stack.enter_context(_patch_alert_insert())
    stack.enter_context(patch(
        "app.services.notification_service.create_notification",
        new=create_notif,
    ))
    with stack:
        await _create_alert_and_notify(
            alert_type="config_changed",
            item_kind="system",
            item_id="extraction_config",
            item_name="System Extraction Config",
            severity="warning",
            message="cfg changed",
        )

    create_notif.assert_not_called()


async def test_create_alert_and_notify_fires_for_owned_workflow():
    from app.tasks.quality_tasks import _create_alert_and_notify

    create_notif = AsyncMock(return_value={})
    stack = ExitStack()
    stack.enter_context(_patch_alert_insert())
    stack.enter_context(patch(
        "app.tasks.quality_tasks._resolve_item_owner",
        new=AsyncMock(return_value="alice"),
    ))
    stack.enter_context(patch(
        "app.services.notification_service.create_notification",
        new=create_notif,
    ))
    with stack:
        await _create_alert_and_notify(
            alert_type="regression",
            item_kind="workflow",
            item_id="wf-1",
            item_name="My Workflow",
            severity="critical",
            message="Quality dropped 25 points",
        )

    create_notif.assert_awaited_once()
    kwargs = create_notif.call_args.kwargs
    assert kwargs["user_id"] == "alice"
    assert kwargs["kind"] == "quality_alert"
    assert "My Workflow" in kwargs["title"]
    assert "Quality alert" in kwargs["title"]  # severity=critical → "Quality alert"
    assert kwargs["body"] == "Quality dropped 25 points"
    assert kwargs["link"] == "/library?tab=catalog&item=wf-1"
    assert kwargs["item_kind"] == "workflow"


async def test_create_alert_and_notify_severity_labels_vary():
    from app.tasks.quality_tasks import _create_alert_and_notify

    captured = []

    async def _capture(**kwargs):
        captured.append(kwargs)
        return {}

    stack = ExitStack()
    stack.enter_context(_patch_alert_insert())
    stack.enter_context(patch(
        "app.tasks.quality_tasks._resolve_item_owner",
        new=AsyncMock(return_value="alice"),
    ))
    stack.enter_context(patch(
        "app.services.notification_service.create_notification",
        new=_capture,
    ))
    with stack:
        for sev in ["critical", "warning", "info"]:
            await _create_alert_and_notify(
                alert_type="regression",
                item_kind="workflow",
                item_id=f"wf-{sev}",
                item_name="W",
                severity=sev,
                message="x",
            )

    assert "Quality alert" in captured[0]["title"]
    assert "Quality warning" in captured[1]["title"]
    assert "Quality notice" in captured[2]["title"]


# ---------------------------------------------------------------------------
# _notify_workflow_completed_sync
# ---------------------------------------------------------------------------

def test_notify_workflow_completed_skips_trivial_run():
    from app.tasks.workflow_tasks import _notify_workflow_completed_sync

    db = MagicMock()
    workflow_doc = {"_id": "wf1", "name": "Quick Workflow", "user_id": "alice"}

    _notify_workflow_completed_sync(
        db, workflow_doc, "result-1",
        num_steps_completed=1, num_steps_total=1,
        duration_seconds=12.0,  # under threshold
    )

    db.notification.insert_one.assert_not_called()


def test_notify_workflow_completed_skips_no_owner():
    from app.tasks.workflow_tasks import _notify_workflow_completed_sync

    db = MagicMock()
    workflow_doc = {"_id": "wf1", "name": "W", "user_id": None, "created_by_user_id": None}

    _notify_workflow_completed_sync(
        db, workflow_doc, "result-1",
        num_steps_completed=3, num_steps_total=3,
        duration_seconds=120.0,
    )

    db.notification.insert_one.assert_not_called()


def test_notify_workflow_completed_skips_system_owner():
    from app.tasks.workflow_tasks import _notify_workflow_completed_sync

    db = MagicMock()
    workflow_doc = {"_id": "wf1", "name": "W", "created_by_user_id": "system"}

    _notify_workflow_completed_sync(
        db, workflow_doc, "result-1",
        num_steps_completed=3, num_steps_total=3,
        duration_seconds=120.0,
    )

    db.notification.insert_one.assert_not_called()


def test_notify_workflow_completed_fires_for_long_run():
    from app.tasks.workflow_tasks import _notify_workflow_completed_sync

    db = MagicMock()
    workflow_doc = {
        "_id": "wf1",
        "name": "NSF Budget Extraction",
        "created_by_user_id": "alice",
    }

    _notify_workflow_completed_sync(
        db, workflow_doc, "result-7",
        num_steps_completed=4, num_steps_total=4,
        duration_seconds=180.5,
    )

    db.notification.insert_one.assert_called_once()
    doc = db.notification.insert_one.call_args.args[0]
    assert doc["user_id"] == "alice"
    assert doc["kind"] == "workflow_completed"
    assert "NSF Budget Extraction" in doc["title"]
    assert doc["link"] == "/workflows/results/result-7"
    assert doc["item_kind"] == "workflow"
    assert doc["read"] is False
    assert "4/4 steps" in doc["body"]
    assert "180s" in doc["body"]


def test_notify_workflow_completed_fires_when_duration_unknown():
    """If duration can't be computed, fire anyway — better to over-notify than miss."""
    from app.tasks.workflow_tasks import _notify_workflow_completed_sync

    db = MagicMock()
    workflow_doc = {"_id": "wf1", "name": "W", "created_by_user_id": "alice"}

    _notify_workflow_completed_sync(
        db, workflow_doc, "result-1",
        num_steps_completed=2, num_steps_total=2,
        duration_seconds=None,
    )

    db.notification.insert_one.assert_called_once()
