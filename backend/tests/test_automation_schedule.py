"""Schedule trigger: plain picks → cron, time zones, next run, and the scheduler.

Support ticket: Schedule as a third trigger in the automation wizard — a
daily/weekly/monthly picker with a time and time zone, a folder or specific
documents, the next run shown, and an "only documents added since the last
run" option.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId

from app.services import automation_schedule as sched

UTC = timezone.utc


class TestBuildCron:
    def test_daily_weekly_monthly(self):
        assert sched.build_cron({"frequency": "daily", "time": "09:30"}) == "30 9 * * *"
        # Monday = 0 in the config, 1 in cron; Sunday = 6 in the config, 0 in cron.
        assert sched.build_cron({"frequency": "weekly", "time": "17:00", "weekday": 0}) == "0 17 * * 1"
        assert sched.build_cron({"frequency": "weekly", "time": "17:00", "weekday": 6}) == "0 17 * * 0"
        assert sched.build_cron({"frequency": "monthly", "time": "08:05", "day_of_month": 28}) == "5 8 28 * *"

    @pytest.mark.parametrize("cfg, message", [
        ({"frequency": "hourly", "time": "09:00"}, "daily, weekly or monthly"),
        ({"frequency": "daily", "time": "9am"}, "HH:MM"),
        ({"frequency": "daily", "time": "24:00"}, "HH:MM"),
        ({"frequency": "weekly", "time": "09:00"}, "weekday"),
        ({"frequency": "weekly", "time": "09:00", "weekday": 7}, "weekday"),
        ({"frequency": "monthly", "time": "09:00", "day_of_month": 31}, "1 to 28"),
    ])
    def test_rejects_bad_picks(self, cfg, message):
        with pytest.raises(ValueError, match=message):
            sched.build_cron(cfg)


class TestNormalize:
    def test_derives_cron_and_defaults_zone(self):
        cfg = sched.normalize_schedule_config({"frequency": "daily", "time": "09:00", "cron_expression": "stale"})
        assert cfg["cron_expression"] == "0 9 * * *"
        assert cfg["timezone"] == "UTC"
        assert cfg["only_new"] is False

    def test_keeps_a_legacy_cron_expression(self):
        assert sched.normalize_schedule_config({"cron_expression": "*/15 * * * *"})["cron_expression"] == "*/15 * * * *"

    @pytest.mark.parametrize("cfg, message", [
        ({}, "frequency and time"),
        ({"cron_expression": "not a cron"}, "Invalid cron"),
        ({"frequency": "daily", "time": "09:00", "timezone": "Mars/Olympus"}, "Unknown time zone"),
        ({"frequency": "daily", "time": "09:00", "source": "inbox"}, "folder' or 'documents"),
    ])
    def test_rejects(self, cfg, message):
        with pytest.raises(ValueError, match=message):
            sched.normalize_schedule_config(cfg)


class TestNextRuns:
    def test_evaluated_in_the_schedules_zone_across_dst(self):
        # 9:00 in Boise is 15:00 UTC under MDT and 16:00 UTC under MST;
        # DST ends 2026-11-01.
        cfg = sched.normalize_schedule_config({"frequency": "daily", "time": "09:00", "timezone": "America/Boise"})
        runs = sched.next_runs(cfg, datetime(2026, 10, 31, 12, 0, tzinfo=UTC), count=2)
        assert runs == [datetime(2026, 10, 31, 15, 0, tzinfo=UTC), datetime(2026, 11, 1, 16, 0, tzinfo=UTC)]

    def test_spring_forward_keeps_the_wall_clock(self):
        # DST starts 2027-03-14: 9:00 Boise is 16:00 UTC before, 15:00 UTC after.
        cfg = sched.normalize_schedule_config({"frequency": "daily", "time": "09:00", "timezone": "America/Boise"})
        runs = sched.next_runs(cfg, datetime(2027, 3, 13, 12, 0, tzinfo=UTC), count=2)
        assert runs == [datetime(2027, 3, 13, 16, 0, tzinfo=UTC), datetime(2027, 3, 14, 15, 0, tzinfo=UTC)]

    def test_weekly_lands_on_the_weekday(self):
        cfg = sched.normalize_schedule_config({"frequency": "weekly", "time": "08:00", "weekday": 0})
        run = sched.next_runs(cfg, datetime(2026, 9, 23, tzinfo=UTC))[0]  # a Wednesday
        assert run == datetime(2026, 9, 28, 8, 0, tzinfo=UTC)
        assert run.weekday() == 0

    def test_last_run_base_is_the_latest_stamp(self):
        created = datetime(2026, 9, 1, tzinfo=UTC)
        armed = datetime(2026, 9, 20)  # naive — treated as UTC
        ran = datetime(2026, 9, 10, tzinfo=UTC)
        auto = {"created_at": created, "schedule_armed_at": armed, "last_scheduled_run_at": ran}
        assert sched.last_run_base(auto, datetime(2000, 1, 1, tzinfo=UTC)) == armed.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# The scheduler
# ---------------------------------------------------------------------------

NOW = datetime(2026, 9, 23, 15, 5, tzinfo=UTC)


def _auto(**cfg_overrides):
    cfg = sched.normalize_schedule_config({"frequency": "daily", "time": "15:00", **cfg_overrides})
    return {
        "_id": ObjectId(),
        "name": "Nightly awards",
        "enabled": True,
        "trigger_type": "schedule",
        "trigger_config": cfg,
        "action_type": "workflow",
        "action_id": str(ObjectId()),
        "user_id": "owner",
        "created_at": NOW - timedelta(days=3),
        "last_scheduled_run_at": NOW - timedelta(days=1),
    }


def _run(auto, docs=None, processing=(), last_event=None, claim_modified=1):
    from app.tasks import passive_tasks

    db = MagicMock()
    db.automation.find.return_value = [auto]
    db.automation.update_one.return_value = MagicMock(modified_count=claim_modified)
    db.workflow_trigger_event.find_one.return_value = last_event
    ready = docs if docs is not None else [{"_id": ObjectId(), "uuid": "d-ready"}]
    db.smart_document.find.side_effect = lambda q, *a, **k: (
        [{"uuid": u} for u in processing] if q.get("processing") is True else ready
    )
    with patch.object(passive_tasks, "get_sync_db", return_value=db), \
         patch.object(passive_tasks, "datetime") as dt:
        dt.now.return_value = NOW
        dt.side_effect = datetime
        result = passive_tasks.process_scheduled_automations()
    return db, result


class TestScheduler:
    def test_due_schedule_fires_once_and_records_the_run(self):
        db, result = _run(_auto(folder_id="f1"))
        assert result["processed"] == 1
        db.workflow_trigger_event.insert_one.assert_called_once()
        db.automation.update_one.assert_called_once()
        claim_filter, claim_update = db.automation.update_one.call_args.args
        assert claim_update == {"$set": {"last_scheduled_run_at": NOW}}
        # Conditional on the stamp this pass read — no double dispatch.
        assert claim_filter["last_scheduled_run_at"] == NOW - timedelta(days=1)

    def test_not_due_does_nothing(self):
        auto = _auto(folder_id="f1")
        auto["last_scheduled_run_at"] = NOW - timedelta(minutes=2)  # already ran today's 15:00
        db, result = _run(auto)
        assert result["processed"] == 0
        db.automation.update_one.assert_not_called()

    def test_zone_decides_when_it_is_due(self):
        # Last ran at 13:05 UTC. 15:00 UTC has passed; 15:00 in Boise is 21:00 UTC.
        utc, boise = _auto(folder_id="f1"), _auto(folder_id="f1", timezone="America/Boise")
        for auto in (utc, boise):
            auto["last_scheduled_run_at"] = NOW - timedelta(hours=2)
        assert _run(utc)[1]["processed"] == 1
        assert _run(boise)[1]["processed"] == 0

    def test_a_paused_schedule_does_not_fire_the_missed_slot_on_resume(self):
        auto = _auto(folder_id="f1")
        auto["last_scheduled_run_at"] = NOW - timedelta(days=10)
        auto["schedule_armed_at"] = NOW - timedelta(minutes=1)  # re-enabled just now
        db, result = _run(auto)
        assert result["processed"] == 0

    def test_only_new_takes_what_arrived_since_the_watermark_plus_carryover(self):
        auto = _auto(folder_id="f1", only_new=True)
        auto["schedule_docs_watermark"] = NOW - timedelta(days=1)
        auto["schedule_carryover_uuids"] = ["d-was-processing"]
        db, _ = _run(auto, processing=["d-still-processing"])
        ready_query = next(c.args[0] for c in db.smart_document.find.call_args_list if c.args[0].get("processing") is False)
        assert ready_query["folder"] == "f1" and ready_query["soft_deleted"] == {"$ne": True}
        assert ready_query["$or"] == [
            {"_id": {"$gte": ObjectId.from_datetime(auto["schedule_docs_watermark"])}},
            {"uuid": {"$in": ["d-was-processing"]}},
        ]
        # The next run starts from now and carries what is still processing.
        watermark_update = db.automation.update_one.call_args_list[1].args[1]
        assert watermark_update == {"$set": {"schedule_docs_watermark": NOW, "schedule_carryover_uuids": ["d-still-processing"]}}

    def test_only_new_first_run_takes_everything(self):
        auto = _auto(folder_id="f1", only_new=True)
        db, _ = _run(auto)
        ready_query = next(c.args[0] for c in db.smart_document.find.call_args_list if c.args[0].get("processing") is False)
        assert "$or" not in ready_query and "created_at" not in ready_query

    def test_a_legacy_schedule_counts_from_its_last_trigger_event(self):
        """No stamps yet: without the old lookup, every existing schedule would
        fire off-slot the moment this deploys."""
        auto = _auto(folder_id="f1")
        auto["last_scheduled_run_at"] = None
        auto["created_at"] = NOW - timedelta(days=90)
        db, result = _run(auto, last_event={"created_at": NOW - timedelta(minutes=3)})  # ran today's 15:00
        assert result["processed"] == 0

    def test_a_lost_claim_does_not_dispatch(self):
        db, result = _run(_auto(folder_id="f1"), claim_modified=0)
        assert result["processed"] == 0
        db.workflow_trigger_event.insert_one.assert_not_called()

    def test_nothing_to_run_on_skips_but_still_claims_the_slot(self):
        db, result = _run(_auto(folder_id="f1", only_new=True), docs=[])
        assert result["processed"] == 0
        db.workflow_trigger_event.insert_one.assert_not_called()
        assert db.automation.update_one.call_args_list[0].args[1] == {"$set": {"last_scheduled_run_at": NOW}}

    def test_a_picker_schedule_with_no_source_does_not_run(self):
        db, result = _run(_auto(source="documents"))
        assert result["processed"] == 0
        db.workflow_trigger_event.insert_one.assert_not_called()

    def test_extraction_schedule_records_its_run(self):
        """Extraction runs record no trigger event; before, the "last run" never
        advanced and a due extraction schedule fired every minute."""
        from app.tasks import passive_tasks

        auto = _auto(document_uuids=["d1"])
        auto["action_type"] = "extraction"
        with patch.object(passive_tasks.process_extraction_outputs, "delay") as delay:
            db, result = _run(auto, docs=[{"_id": ObjectId(), "uuid": "d1"}])
        assert result["processed"] == 1
        delay.assert_called_once()
        assert db.automation.update_one.call_args.args[1] == {"$set": {"last_scheduled_run_at": NOW}}


# ---------------------------------------------------------------------------
# Routes: preview, create/update normalization, source authorization
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock  # noqa: E402

from tests.test_automations_api_integration import (  # noqa: E402
    _auth_cookies,
    _make_automation,
    _make_user,
)


def _logged_in(user):
    return (
        patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
        patch("app.dependencies.User", **{"find_one": AsyncMock(return_value=user)}),
    )


class TestScheduleRoutes:
    @pytest.mark.asyncio
    async def test_preview_returns_three_future_runs(self, client):
        cookies, headers = _auth_cookies()
        a, b = _logged_in(_make_user())
        with a, b:
            resp = await client.post(
                "/api/automations/schedule/preview",
                json={"trigger_config": {"frequency": "weekly", "weekday": 4, "time": "16:30", "timezone": "America/Boise"}},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["cron_expression"] == "30 16 * * 5"
        assert body["timezone"] == "America/Boise"
        runs = [datetime.fromisoformat(r) for r in body["next_runs"]]
        assert len(runs) == 3 and runs == sorted(runs) and runs[0] > datetime.now(UTC)
        assert all(r.astimezone(sched._zone("America/Boise")).weekday() == 4 for r in runs)

    @pytest.mark.asyncio
    async def test_preview_rejects_a_bad_pick(self, client):
        cookies, headers = _auth_cookies()
        a, b = _logged_in(_make_user())
        with a, b:
            resp = await client.post(
                "/api/automations/schedule/preview",
                json={"trigger_config": {"frequency": "monthly", "time": "09:00", "day_of_month": 31}},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 422
        assert "1 to 28" in resp.text

    @pytest.mark.asyncio
    async def test_create_derives_cron_and_checks_the_folder(self, client):
        cookies, headers = _auth_cookies()
        auto = _make_automation(trigger_type="schedule")
        auto.trigger_config = {"cron_expression": "0 9 * * *", "timezone": "UTC"}
        auto.last_scheduled_run_at = None
        auto.schedule_armed_at = None
        a, b = _logged_in(_make_user())
        with a, b, \
             patch("app.routers.automations._validate_action_target", new_callable=AsyncMock), \
             patch("app.routers.automations.access_control.get_authorized_folder", AsyncMock(return_value=MagicMock())) as folder_ok, \
             patch("app.routers.automations.svc.create_automation", new_callable=AsyncMock, return_value=auto) as create:
            resp = await client.post(
                "/api/automations",
                json={"name": "Daily", "trigger_type": "schedule",
                      "trigger_config": {"frequency": "daily", "time": "09:00", "folder_id": "f1", "source": "folder"}},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200
        assert create.await_args.kwargs["trigger_config"]["cron_expression"] == "0 9 * * *"
        folder_ok.assert_awaited_once()
        assert resp.json()["next_run_at"] is not None

    @pytest.mark.asyncio
    async def test_create_refuses_a_folder_the_caller_cannot_open(self, client):
        cookies, headers = _auth_cookies()
        a, b = _logged_in(_make_user())
        with a, b, \
             patch("app.routers.automations._validate_action_target", new_callable=AsyncMock), \
             patch("app.routers.automations.access_control.get_authorized_folder", AsyncMock(return_value=None)), \
             patch("app.routers.automations.svc.create_automation", new_callable=AsyncMock) as create:
            resp = await client.post(
                "/api/automations",
                json={"name": "Daily", "trigger_type": "schedule",
                      "trigger_config": {"frequency": "daily", "time": "09:00", "folder_id": "someone-elses"}},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 404
        create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_normalizes_a_config_sent_without_trigger_type(self, client):
        """The editor saves a changed time without restating trigger_type."""
        cookies, headers = _auth_cookies()
        current = _make_automation(trigger_type="schedule")
        a, b = _logged_in(_make_user())
        with a, b, \
             patch("app.routers.automations._load_authorized_automation", AsyncMock(return_value=(current, None))), \
             patch("app.routers.automations._validate_action_target", new_callable=AsyncMock), \
             patch("app.routers.automations.svc.apply_automation_update", new_callable=AsyncMock, return_value=current) as apply, \
             patch("app.routers.automations._to_response", new_callable=AsyncMock, return_value={
                 "id": "auto-1", "name": "n", "enabled": True, "trigger_type": "schedule",
                 "trigger_config": {}, "action_type": "workflow", "user_id": "testuser",
                 "created_at": NOW.isoformat(), "updated_at": NOW.isoformat(),
             }):
            resp = await client.patch(
                "/api/automations/auto-1",
                json={"trigger_config": {"frequency": "daily", "time": "10:15", "cron_expression": "0 9 * * *"}},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200, resp.text
        assert apply.await_args.kwargs["trigger_config"]["cron_expression"] == "15 10 * * *"


class TestArming:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("kwargs, armed", [
        ({"enabled": True}, True),                       # switched on
        ({"trigger_config": {"x": 1}}, True),            # changed
        ({"name": "renamed"}, False),                    # unrelated edit
    ])
    async def test_apply_update_arms_a_schedule(self, kwargs, armed):
        from app.services import automation_service

        auto = MagicMock()
        auto.enabled = False
        auto.trigger_type = "schedule"
        auto.schedule_armed_at = None
        auto.save = AsyncMock()
        await automation_service.apply_automation_update(auto, **kwargs)
        assert (auto.schedule_armed_at is not None) is armed
