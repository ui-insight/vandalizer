"""Adding a deadline to the RA inbox by hand (support ticket).

Chat refuses a deadline it can't verify against the document and told the user
to add it "manually in the project's RA inbox panel", which had no way to add
an item. The inbox now has Add deadline: title, date and an optional note,
saved as added by hand. No database: the Obligation model is a stand-in.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.obligation import Obligation, ObligationSource
from app.routers import obligations as routes
from app.services import chat_tools, deadline_reminders, obligation_service as service
from tests.test_ra_inbox_chat import _ctx, project_env  # noqa: F401  (fixture)

PROJECT = SimpleNamespace(uuid="proj-1", title="NIH Subaward", team_id="team-1")
USER = SimpleNamespace(user_id="ra")


def _existing(**kw) -> Obligation:
    base = dict(
        uuid="old", project_uuid="proj-1", kind="deadline", title="Final financial report",
        deadline_type="report_due", due_at=datetime.datetime(2027, 3, 31), due_text=None,
        deadline_calculation=None, limit_value=None, observed_value=None, unit=None,
        sources=[], status="open", dismissed_by=[], created_by="ra",
    )
    return Obligation.model_construct(**{**base, **kw})


def _obligation_model(existing: list[Obligation]):
    """Obligation stand-in: ``find`` returns *existing*; new ones record their insert."""
    inserted: list = []

    class Fake(SimpleNamespace):
        async def insert(self):
            inserted.append(self)

    query = MagicMock()
    query.to_list = AsyncMock(return_value=existing)
    Fake.find = MagicMock(return_value=query)
    return Fake, inserted


@pytest.mark.asyncio
async def test_a_deadline_added_by_hand_is_saved_as_unchecked_with_its_note(monkeypatch):
    model, inserted = _obligation_model([])
    monkeypatch.setattr(service, "Obligation", model)
    ob, reason = await service.add_by_hand(
        PROJECT, USER, title="  Final   financial report ", due_date="2027-03-31",
        source_note="Subaward agreement,  section 5",
    )
    assert reason is None and inserted == [ob]
    assert ob.title == "Final financial report"
    assert ob.due_at == datetime.datetime(2027, 3, 31)
    assert ob.entered_by_hand is True and ob.sources == []
    assert ob.source_note == "Subaward agreement, section 5"
    # "other" never replaces a document-backed sponsor or report deadline.
    assert ob.deadline_type == "other" and ob.kind == "deadline"
    assert ob.project_uuid == "proj-1" and ob.team_id == "team-1" and ob.created_by == "ra"


@pytest.mark.asyncio
@pytest.mark.parametrize("title,due,reason", [
    ("", "2027-03-31", "title"),
    ("Report", "", "YYYY-MM-DD"),
    ("Report", "03/31/2027", "YYYY-MM-DD"),
    ("Report", "2027-02-30", "not a real date"),
])
async def test_a_title_and_a_real_date_are_required(monkeypatch, title, due, reason):
    model, inserted = _obligation_model([])
    monkeypatch.setattr(service, "Obligation", model)
    ob, why = await service.add_by_hand(PROJECT, USER, title=title, due_date=due)
    assert ob is None and reason in why and inserted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status,dismissed,where", [
    ("open", [], "(open)"), ("done", [], "(marked done)"), ("open", ["ra"], "(dismissed from your Home)"),
])
async def test_the_same_deadline_on_the_same_date_is_not_added_twice(monkeypatch, status, dismissed, where):
    model, inserted = _obligation_model([_existing(status=status, dismissed_by=dismissed)])
    monkeypatch.setattr(service, "Obligation", model)
    ob, why = await service.add_by_hand(PROJECT, USER, title="final financial report due", due_date="2027-03-31")
    assert ob is None and inserted == []
    assert "already in this project's inbox" in why and where in why


@pytest.mark.asyncio
async def test_a_different_deadline_on_the_same_day_is_added(monkeypatch):
    """Two "other" deadlines on one day are different if their titles are."""
    model, inserted = _obligation_model([_existing(deadline_type="other")])
    monkeypatch.setattr(service, "Obligation", model)
    ob, why = await service.add_by_hand(PROJECT, USER, title="Invention disclosure", due_date="2027-03-31")
    assert why is None and inserted == [ob]


def test_the_inbox_row_says_it_was_added_by_hand():
    row = service.serialize(_existing(entered_by_hand=True, source_note="Sponsor email"), USER, "NIH Subaward")
    assert row["entered_by_hand"] is True and row["source_note"] == "Sponsor email"
    found = service.serialize(_existing(sources=[ObligationSource(document_uuid="d", quote="q")]), USER)
    assert found["entered_by_hand"] is False and found["source_note"] is None


def test_reminders_and_calendar_files_say_it_was_added_by_hand():
    ob = _existing(entered_by_hand=True, source_note="Sponsor email")
    assert deadline_reminders._source_line(ob) == "Added by hand: Sponsor email."
    ics = deadline_reminders.calendar_file([(ob, "NIH Subaward")], frontend_url="https://x", alarm_days=[], name="d")
    assert "Added by hand" in ics.replace("\r\n ", "")


@pytest.mark.asyncio
async def test_the_endpoint_needs_edit_access_and_returns_the_reason(monkeypatch):
    monkeypatch.setattr(routes, "_project_for", AsyncMock(side_effect=HTTPException(status_code=403)))
    body = routes.AddByHandRequest(project_uuid="proj-1", title="Report", due_date="2027-03-31")
    with pytest.raises(HTTPException) as denied:
        await routes.add_by_hand(body, user=USER)
    assert denied.value.status_code == 403
    assert routes._project_for.await_args.kwargs == {"manage": True}

    monkeypatch.setattr(routes, "_project_for", AsyncMock(return_value=PROJECT))
    monkeypatch.setattr(service, "add_by_hand", AsyncMock(return_value=(None, "Give the due date as YYYY-MM-DD.")))
    with pytest.raises(HTTPException) as bad:
        await routes.add_by_hand(body, user=USER)
    assert bad.value.status_code == 422 and bad.value.detail == "Give the due date as YYYY-MM-DD."


@pytest.mark.asyncio
async def test_chat_points_refused_deadlines_at_add_deadline(project_env):  # noqa: F811
    from unittest.mock import patch

    project, user, _ = project_env
    nothing = {"accepted": [], "rejected": [{"title": "Final report", "reason": "the quote was not found"}]}
    ctx = _ctx(user)
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=project)), \
         patch("app.services.project_service.can_manage_project", AsyncMock(return_value=True)), \
         patch.object(service, "propose", AsyncMock(return_value=nothing)):
        first = await chat_tools.propose_obligations(ctx, [{"kind": "deadline"}])
        await chat_tools.propose_obligations(ctx, [{"kind": "deadline"}])
        stopped = await chat_tools.propose_obligations(ctx, [{"kind": "deadline"}])
    assert "Add deadline in the project's RA inbox" in first["if_still_refused"]
    assert "Add deadline in the project's RA inbox" in stopped["hint"]


@pytest.mark.asyncio
async def test_chat_reads_hand_added_items_as_not_from_a_document(project_env):  # noqa: F811
    from unittest.mock import patch

    project, user, _ = project_env
    rows = [{"title": "Final report", "kind": "deadline", "status": "open", "due_at": "2027-03-31T00:00:00",
             "due_text": None, "sources": [], "entered_by_hand": True, "source_note": "Sponsor email"}]
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=project)), \
         patch.object(service, "project_obligations", AsyncMock(return_value=rows)):
        result = await chat_tools.list_project_inbox(_ctx(user))
    assert result["items"][0]["added_by_hand"] is True
    assert result["items"][0]["source_note"] == "Sponsor email"
