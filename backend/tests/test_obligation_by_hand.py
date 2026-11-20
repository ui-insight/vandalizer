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
    ("Report", "0001-01-01", "between 1900 and 2999"),
    ("Report", "3000-01-01", "between 1900 and 2999"),
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


# --- A hand-added deadline and the checked ones (review of #1145) ----------

DAY = datetime.datetime(2027, 3, 31)
CITED = ObligationSource(document_uuid="subaward", document_title="Subaward.pdf", page=5,
                         quote="Final report and invention disclosure due March 31, 2027.")


def _checked(title: str) -> dict:
    return {"kind": "deadline", "title": title, "deadline_type": "other", "due_at": DAY,
            "due_text": None, "sources": [CITED]}


@pytest.fixture
def hand_env(monkeypatch):
    """An inbox holding one hand-added "Final report" (marked done, dismissed by
    a teammate), and proposals that pass the document check."""
    from tests.conftest import fake_model

    hand = _existing(uuid="hand", title="Final report", deadline_type="other", due_at=DAY, status="done",
                     dismissed_by=["teammate"], entered_by_hand=True, source_note="Sponsor email",
                     supersedes=None, superseded_by=None)
    inserted: list = []

    async def insert(self):
        inserted.append(self)

    model = fake_model([hand])
    model.__new__ = lambda cls, **values: Obligation.model_construct(**values)
    monkeypatch.setattr(service, "Obligation", model)
    monkeypatch.setattr(Obligation, "insert", insert)
    monkeypatch.setattr(Obligation, "save", AsyncMock())
    monkeypatch.setattr(service, "check_proposal",
                        AsyncMock(side_effect=lambda item, user, project: (_checked(item["title"]), None)))
    return hand, inserted


@pytest.mark.asyncio
async def test_a_hand_added_deadline_does_not_block_a_different_checked_one_that_day(hand_env):
    """Both "other" on the same date; only the title says which deadline each is."""
    hand, _ = hand_env
    checked = await service.propose(PROJECT, USER, [{"title": "Invention disclosure"}])
    assert checked["rejected"] == []
    assert [a["clean"]["title"] for a in checked["accepted"]] == ["Invention disclosure"]
    assert "confirms_hand_entered" not in checked["accepted"][0]


@pytest.mark.asyncio
async def test_the_checked_version_of_a_hand_added_deadline_replaces_it_in_place(hand_env):
    hand, inserted = hand_env
    checked = await service.propose(PROJECT, USER, [{"title": "Final report due"}])
    assert checked["rejected"] == []
    (row,) = checked["accepted"]
    assert row["confirms_hand_entered"] == "hand"
    saved = await service.save_checked(PROJECT, USER, row["clean"])
    assert saved is hand and inserted == []
    assert hand.entered_by_hand is False and hand.source_note is None
    assert hand.sources == [CITED] and hand.title == "Final report due"
    # Same item: done stays done, a teammate's dismissal stays.
    assert hand.status == "done" and hand.dismissed_by == ["teammate"] and hand.uuid == "hand"
    hand.save.assert_awaited()


@pytest.mark.asyncio
async def test_chat_adds_the_checked_deadlines_a_hand_added_one_would_have_hidden(project_env, hand_env):  # noqa: F811
    # project_env first: hand_env's inbox replaces its empty one.
    from unittest.mock import patch

    hand, inserted = hand_env
    project, user, _ = project_env
    ctx = _ctx(user)
    items = [{"title": "Final report"}, {"title": "Invention disclosure"}]
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=project)), \
         patch("app.services.project_service.can_manage_project", AsyncMock(return_value=True)):
        preview = await chat_tools.propose_obligations(ctx, items, confirmed=True)
        assert preview["needs_confirmation"] is True
        assert preview["rejected"] == [] and "if_still_refused" not in preview
        assert "Invention disclosure" in preview["preview"]
        assert "checks the deadline added by hand" in preview["preview"]
        ctx.deps.turn_marker += 2
        result = await chat_tools.propose_obligations(ctx, items, confirmed=True)
    assert [o["title"] for o in result["added"]] == ["Final report", "Invention disclosure"]
    assert [o.title for o in inserted] == ["Invention disclosure"]
    assert hand.entered_by_hand is False and hand.sources == [CITED]


@pytest.mark.asyncio
async def test_chat_offers_add_by_hand_only_when_something_was_refused(project_env):  # noqa: F811
    from unittest.mock import patch

    project, user, _ = project_env
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=project)), \
         patch("app.services.project_service.can_manage_project", AsyncMock(return_value=True)), \
         patch.object(service, "propose", AsyncMock(return_value={"accepted": [], "rejected": []})):
        result = await chat_tools.propose_obligations(_ctx(user), [{"kind": "deadline"}])
    assert "if_still_refused" not in result


def test_the_award_snapshot_labels_hand_added_deadlines():
    from app.services.award_snapshot import page_html
    from app.services.chat_snapshot_tools import _deadline

    row = {"title": "Final report", "due_at": "2027-03-31T00:00:00", "due_text": None, "sources": [],
           "entered_by_hand": True, "source_note": "Sponsor email"}
    told = _deadline(row)
    assert told["source"] == "Added by hand · not checked against a document"
    assert told["added_by_hand"] is True and told["source_note"] == "Sponsor email"
    cited = _deadline({**row, "entered_by_hand": False, "sources": [{"document_title": "Subaward.pdf", "page": 5}]})
    assert cited["source"] == "Subaward.pdf, p. 5" and "added_by_hand" not in cited

    view = {"project": {"uuid": "p", "title": "NIH", "state": "awarded"}, "facts": [], "budget_years": [],
            "deadlines": {"overdue": [], "upcoming": [row], "done": [], "needed": []},
            "last_run": None, "pages": [], "built_at": None, "generated_at": "2026-11-03T10:00:00+00:00"}
    assert ("Final report</strong> · Mar 31, 2027 · Added by hand · not checked against a document"
            " · Source: Sponsor email") in page_html(view)
