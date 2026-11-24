"""RA inbox deadline reminders, overdue alerts and calendar files, on MongoDB.

Support ticket: deadlines from a subaward reached the RA inbox and nowhere
else — no bell entry before a due date, nothing when one passed, no email, no
calendar file. The schedule below follows that subaward: semi-annual results
due within 30 days of each June 30 and December 31, one already-missed
deliverable, and the final report.

    INTEGRATION_MONGODB=1 uv run pytest tests/integration/test_deadline_reminders_mongodb.py
"""

import datetime
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.models.notification import Notification
from app.models.obligation import Obligation, ObligationReminder, ObligationSource
from app.models.project import Project, ProjectMembership
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.routers import obligations as obligations_router
from app.services import deadline_reminders, obligation_service

pytestmark = [
    pytest.mark.skipif(not os.environ.get("INTEGRATION_MONGODB"), reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests"),
    pytest.mark.asyncio(loop_scope="session"),
]

TODAY = datetime.date(2026, 7, 16)


def _at(day: datetime.date) -> datetime.datetime:
    return datetime.datetime(day.year, day.month, day.day)


async def _deadline(uuid, title, due, *, project="proj-1", status="open", dismissed_by=(), kind="deadline", due_text=None):
    ob = Obligation(
        uuid=uuid, project_uuid=project, kind=kind, title=title, deadline_type="report_due",
        due_at=_at(due) if due else None, due_text=due_text, status=status, dismissed_by=list(dismissed_by),
        created_by="ra-owner",
        sources=[ObligationSource(document_uuid="subaward", document_title="WSU-UI-2025-1132.pdf", page=4,
                                  quote="Semi-annual results are due within 30 days of each June 30 and December 31.")],
    )
    await ob.insert()
    return ob


async def _setup():
    owner = User(user_id="ra-owner", email="owner@example.test", name="RA Owner")
    viewer = User(user_id="pi-viewer", email="pi@example.test", name="PI")
    admin_in = User(user_id="team-admin-in", email="in@example.test", name="Admin In",
                    deadline_reminders={"team_projects": True})
    admin_out = User(user_id="team-admin-out", email="out@example.test", name="Admin Out")
    for u in (owner, viewer, admin_in, admin_out):
        await u.insert()
    team = Team(uuid="team-1", name="OSP", owner_user_id="team-admin-out")
    await team.insert()
    await TeamMembership(team=team.id, user_id="team-admin-in", role="admin").insert()
    await Project(uuid="proj-1", title="NIH Subaward WSU-UI-2025-1132", owner_user_id="ra-owner",
                  root_folder_uuid="root-1", team_id="team-1").insert()
    await ProjectMembership(project_uuid="proj-1", user_id="pi-viewer", role="viewer").insert()
    await Project(uuid="proj-old", title="Closed award", owner_user_id="ra-owner",
                  root_folder_uuid="root-2", state="archived").insert()

    d = datetime.timedelta
    await _deadline("results-1", "Semi-annual results", datetime.date(2026, 7, 30))  # 14 days out
    await _deadline("results-2", "Semi-annual results", datetime.date(2027, 1, 30))  # far out
    await _deadline("qpcr", "Validated qPCR assay protocol", TODAY - d(5))
    await _deadline("kickoff", "Kickoff memo", TODAY - d(121))
    await _deadline("budget", "Rebudget request", TODAY - d(90))
    await _deadline("today", "Invoice", TODAY, due_text="5:00 p.m. Pacific Time")
    await _deadline("soon", "Data sharing plan", TODAY + d(2), dismissed_by=["pi-viewer"])
    await _deadline("done", "Signed subaward", TODAY + d(3), status="done")
    await _deadline("archived", "Old report", TODAY + d(3), project="proj-old")
    await _deadline("material", "Signed partner letter", None, kind="required_material")


def _bell(user_id):
    return Notification.find(Notification.user_id == user_id).sort("+created_at").to_list()


async def test_reminders_overdue_alerts_and_who_gets_them(mongo_client):
    await _setup()
    with patch("app.services.email_service.send_email", new=AsyncMock(return_value=True)) as email:
        counts = await deadline_reminders.send_due_reminders(TODAY)
    email.assert_not_called()  # email is off by default

    owner = {n.item_id: n for n in await _bell("ra-owner") if n.item_id}
    assert set(owner) == {"results-1", "qpcr", "today", "soon"}
    assert owner["results-1"].title == "Due in 14 days: Semi-annual results"
    assert owner["results-1"].link == "/?deadline=results-1"
    assert "WSU-UI-2025-1132.pdf, p. 4" in owner["results-1"].body
    assert owner["today"].title == "Due today: Invoice"
    assert "5:00 p.m. Pacific Time" in owner["today"].body
    assert owner["qpcr"].title == "Past due: Validated qPCR assay protocol"
    assert owner["qpcr"].kind == "deadline_overdue"
    assert owner["soon"].title == "Due in 2 days: Data sharing plan"
    # The two deadlines long past due when reminders first saw them: one entry.
    bundled = [n for n in await _bell("ra-owner") if not n.item_id]
    assert len(bundled) == 1 and bundled[0].title == "2 older deadlines are past due"
    assert counts["bundled"] == 6, "two each for the owner, the PI and the opted-in admin"

    viewer = {n.item_id for n in await _bell("pi-viewer") if n.item_id}
    assert "soon" not in viewer, "dismissed from the PI's Home, so not reminded"
    assert {"results-1", "qpcr", "today"} <= viewer
    # A team admin who opted in to team projects is reminded; one who didn't isn't.
    assert {n.item_id for n in await _bell("team-admin-in") if n.item_id} >= {"results-1"}
    assert await _bell("team-admin-out") == []

    # Hourly reruns send nothing twice.
    before = await Notification.find_all().count()
    await deadline_reminders.send_due_reminders(TODAY)
    assert await Notification.find_all().count() == before

    # Next stage: three days later, results-1 is 11 days out — still the 14-day
    # stage, already sent. At 3 days out the 3-day reminder goes.
    await deadline_reminders.send_due_reminders(datetime.date(2026, 7, 27))
    titles = [n.title for n in await _bell("ra-owner")]
    assert "Due in 3 days: Semi-annual results" in titles
    assert titles.count("Due in 14 days: Semi-annual results") == 1

    # A moved due date is reminded on its new schedule.
    ob = await Obligation.find_one(Obligation.uuid == "results-2")
    ob.due_at = _at(datetime.date(2026, 7, 29))
    await ob.save()
    await deadline_reminders.send_due_reminders(datetime.date(2026, 7, 27))
    assert "Due in 2 days: Semi-annual results" in [n.title for n in await _bell("ra-owner")]

    # Marking it done clears its unread reminders from everyone's bell.
    owner_user = await User.find_one(User.user_id == "ra-owner")
    qpcr = await Obligation.find_one(Obligation.uuid == "qpcr")
    await obligation_service.set_done(qpcr, owner_user, True)
    unread = await Notification.find({"item_id": "qpcr", "read": False}).count()
    assert unread == 0


async def test_settings_turn_off_stages_and_email_batches_one_message(mongo_client):
    await _setup()
    owner = await User.find_one(User.user_id == "ra-owner")
    owner.deadline_reminders = {"bell": False, "email": True, "overdue": False, "days_before": [14]}
    await owner.save()
    with patch("app.services.email_service.send_email", new=AsyncMock(return_value=True)) as email:
        await deadline_reminders.send_due_reminders(TODAY)

    assert await _bell("ra-owner") == []
    sent = [c for c in email.await_args_list if c.args[0] == "owner@example.test"]
    assert len(sent) == 1, "one email per sweep, listing every reminder"
    subject, html = sent[0].args[1], sent[0].args[2]
    assert subject == "3 project deadlines need attention"
    assert "Semi-annual results" in html and "Invoice" in html and "Data sharing plan" in html
    assert "qPCR" not in html, "overdue alerts were turned off"
    assert "/?deadline=results-1" in html
    stages = {r.obligation_uuid: r.stage for r in await ObligationReminder.find({"user_id": "ra-owner"}).to_list()}
    # With only [14], two days out falls under the 14-day stage.
    assert stages["soon"] == "before_14" and stages["today"] == "due"


async def test_weekly_summary_once_a_week(mongo_client):
    await _setup()
    owner = await User.find_one(User.user_id == "ra-owner")
    owner.deadline_reminders = {"weekly_summary": True}
    await owner.save()
    with patch("app.services.email_service.send_email", new=AsyncMock(return_value=True)) as email:
        assert await deadline_reminders.send_weekly_summaries(TODAY) == 1
        assert await deadline_reminders.send_weekly_summaries(TODAY + datetime.timedelta(days=1)) == 0
    html = email.await_args.args[2]
    assert "Overdue" in html and "Due this week" in html and "Next 30 days" in html
    assert "Old report" not in html, "archived projects are left out"


def _client(user):
    app = FastAPI()
    app.include_router(obligations_router.router, prefix="/api/obligations")
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_calendar_files_and_settings_routes(mongo_client):
    await _setup()
    owner = await User.find_one(User.user_id == "ra-owner")
    async with _client(owner) as http:
        one = await http.get("/api/obligations/today/calendar.ics")
        assert one.status_code == 200 and one.headers["content-type"].startswith("text/calendar")
        assert 'filename="invoice.ics"' in one.headers["content-disposition"]
        assert "DTSTART;VALUE=DATE:20260716" in one.text and "DTEND;VALUE=DATE:20260717" in one.text
        assert "TRIGGER:-P14D" in one.text and "TRIGGER:-P3D" in one.text

        project = await http.get("/api/obligations/calendar.ics", params={"project_uuid": "proj-1"})
        events = project.text.count("BEGIN:VEVENT")
        assert events == 7, "every open, dated deadline in the project (not done, not the material)"
        assert "UID:results-1@vandalizer" in project.text

        assert (await http.get("/api/obligations/material/calendar.ics")).status_code == 400

        settings = (await http.get("/api/obligations/reminder-settings")).json()
        assert settings["settings"]["days_before"] == [14, 3] and settings["team_admin"] is False
        changed = await http.put("/api/obligations/reminder-settings", json={"days_before": [7, 30, 1], "email": True})
        assert changed.json()["settings"]["days_before"] == [30, 7, 1]
        assert (await http.put("/api/obligations/reminder-settings", json={"days_before": [0]})).status_code == 422
        assert (await http.put("/api/obligations/reminder-settings", json={"surprise": True})).status_code == 422

        item = (await http.get("/api/obligations/results-1")).json()
        assert item["title"] == "Semi-annual results" and item["project_title"].startswith("NIH Subaward")

    admin = await User.find_one(User.user_id == "team-admin-in")
    async with _client(admin) as http:
        assert (await http.get("/api/obligations/reminder-settings")).json()["team_admin"] is True
