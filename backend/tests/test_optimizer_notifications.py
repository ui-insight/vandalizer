"""Optimizer runs reach their owner through the bell.

Support ticket: auto-generated tuning suggestions (and failed tuning runs) were
visible only on /tuning, which nothing in the app links to for a non-admin.
Shadow runs announce themselves only when they leave something to act on;
runs a user started announce completion or failure; repeats coalesce per item.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import optimizer_notifications as on

NOW = datetime.datetime(2026, 9, 23, tzinfo=datetime.timezone.utc)


def _run(surface="workflow", *, status="completed", shadow=False, **fields):
    item = {"kb": "kb_uuid", "extraction": "search_set_uuid", "workflow": "workflow_id"}[surface]
    base = {
        "uuid": "run-1",
        item: "item-1",
        "user_id": "owner",
        "status": status,
        "options": {"shadow_trigger": "quality_alert"} if shadow else {},
        "best_config": {"model": "m"},
        "tied_with_baseline": False,
        "dismissed_at": None,
        "baseline_default_score": 0.6,
        "optimized_score": 0.75,
        "error_message": None,
    }
    base.update(fields)
    return SimpleNamespace(**base)


async def _emit(surface, run, *, owner="item-owner", **kw):
    create = AsyncMock()
    with patch("app.services.notification_service.create_notification", create), \
         patch.object(on, "_item_info", AsyncMock(return_value=("Award review", owner))):
        await on.notify_run_terminal(surface, run, item_name="Award review", **kw)
    return create


class TestShadowRuns:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("surface", ["kb", "extraction", "workflow"])
    async def test_candidate_notifies_owner_with_link_to_tuning(self, surface):
        # The quality sweep starts shadow runs as "system"; the owner hears.
        create = await _emit(surface, _run(surface, shadow=True, user_id="system"))
        create.assert_awaited_once()
        kw = create.await_args.kwargs
        assert kw["user_id"] == "item-owner"
        assert kw["kind"] == "tuning_suggestion"
        assert kw["link"] == "/tuning"
        assert kw["title"] == "Tuning suggestion: Award review"
        assert "60% → 75% (+15 pts)" in kw["body"]
        assert kw["coalesce_key"] == f"tuning_suggestion:{surface}:item-1"
        assert "{count}" in kw["group_title"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fields", [
        {"tied_with_baseline": True},
        {"best_config": None},
        {"dismissed_at": NOW},
    ])
    async def test_nothing_to_act_on_stays_quiet(self, fields):
        create = await _emit("workflow", _run(shadow=True, **fields))
        create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_applied_winner_stays_quiet(self):
        create = await _emit("workflow", _run(shadow=True), applied=True)
        create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failure_notifies_as_warning_with_error(self):
        create = await _emit("extraction", _run("extraction", status="failed", shadow=True, error_message="judge timeout"))
        kw = create.await_args.kwargs
        assert kw["kind"] == "extraction_optimization_failed"
        assert kw["severity"] == "warning"
        assert kw["body"] == "judge timeout"
        assert kw["link"] == "/tuning"
        assert kw["coalesce_key"] == "extraction_optimization_failed:extraction:item-1"


class TestUserRuns:
    @pytest.mark.asyncio
    async def test_completion_links_to_the_item(self):
        create = await _emit("extraction", _run("extraction"))
        kw = create.await_args.kwargs
        assert kw["kind"] == "extraction_optimization_completed"
        assert kw["link"] == "/?extraction=item-1"
        assert "Review and apply them from the extraction" in kw["body"]

    @pytest.mark.asyncio
    async def test_applied_and_no_change_bodies(self):
        applied = (await _emit("workflow", _run(), applied=True)).await_args.kwargs
        assert applied["body"].startswith("Better settings were found and applied.")
        tied = (await _emit("workflow", _run(tied_with_baseline=True))).await_args.kwargs
        assert tied["body"].startswith("No measurably better settings")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["cancelled", "running", "queued"])
    async def test_non_terminal_or_cancelled_is_silent(self, status):
        create = await _emit("workflow", _run(status=status))
        create.assert_not_awaited()


@pytest.mark.asyncio
async def test_never_raises():
    with patch("app.services.notification_service.create_notification", AsyncMock(side_effect=RuntimeError("db down"))):
        await on.notify_run_terminal("workflow", _run(), item_name="x")


@pytest.mark.asyncio
async def test_missing_owner_is_silent():
    create = await _emit("workflow", _run(user_id=None))
    create.assert_not_awaited()


class TestReapers:
    """A run whose worker died is a failure too — the reaper must announce it."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("module", ["workflow_optimizer", "extraction_optimizer", "kb_optimizer"])
    async def test_reaped_run_notifies(self, module):
        import importlib

        mod = importlib.import_module(f"app.services.{module}")
        run = _run(
            status="running",
            started_at=NOW - datetime.timedelta(days=1),
            cancel_requested=False,
            save=AsyncMock(),
        )
        with patch.object(mod, "notify_run_terminal", AsyncMock()) as notify, \
             patch.object(mod, "_revoke_task", lambda _r: None, create=True):
            await mod.reap_one(run)
        assert run.status == "failed"
        notify.assert_awaited_once()
        assert notify.await_args.args[1] is run


class TestRecipient:
    @pytest.mark.asyncio
    async def test_a_feedback_triggered_shadow_run_goes_to_the_owner_not_the_chat_user(self):
        create = await _emit("kb", _run("kb", shadow=True, user_id="chat-user"))
        assert create.await_args.kwargs["user_id"] == "item-owner"

    @pytest.mark.asyncio
    async def test_a_run_someone_started_goes_to_them(self):
        create = await _emit("workflow", _run(user_id="launcher"))
        assert create.await_args.kwargs["user_id"] == "launcher"

    @pytest.mark.asyncio
    async def test_an_ownerless_shadow_run_notifies_nobody(self):
        create = await _emit("workflow", _run(shadow=True, user_id="system"), owner=None)
        create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_system_owned_item_notifies_nobody(self):
        create = await _emit("workflow", _run(shadow=True), owner="system")
        create.assert_not_awaited()
