"""Chat reads the RA inbox when asked to use it, and doesn't write to it.

Support ticket: asked for a Page with "all upcoming deadlines from this
project's RA inbox", chat had no way to read the inbox. It proposed adding
items nobody asked for, retried a failing proposal five times, proposed the
4 semi-annual deadlines already in the inbox again (titled differently), and
built a Page saying its dates were "from the RA inbox" when they came from
the subaward.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.obligation import Obligation
from app.services import chat_artifact_tools, chat_tools, obligation_service as service
from app.services.inbox_provenance import PAGE_ERROR, REPLY_NOTE, credits_inbox
from tests import test_chat_output
from tests.conftest import fake_model
from tests.test_chat_tools import _make_context
from tests import test_relative_deadlines
from tests.test_relative_deadlines import SEMIANNUAL, proposal

project_env = test_relative_deadlines.project_env


def _ctx(user):
    ctx = _make_context(conversation=SimpleNamespace(pending_confirmations=[], save=AsyncMock(), uuid="conv"))
    ctx.deps.user = user
    return ctx


@pytest.mark.asyncio
async def test_list_project_inbox_reads_items_with_their_sources(project_env):
    project, user, _ = project_env
    rows = [
        {"title": "Semi-annual results", "kind": "deadline", "status": "open", "due_at": "2026-07-30T00:00:00",
         "due_text": None, "deadline_calculation": {"formula": "2026-06-30 + 30 calendar days = 2026-07-30"},
         "sources": [{"document_title": "Subaward.pdf", "page": 2, "quote": "q"}]},
        {"title": "Old date", "kind": "deadline", "status": "superseded", "due_at": "2026-01-01T00:00:00",
         "sources": []},
        {"title": "qPCR protocol", "kind": "required_material", "status": "done", "sources": []},
    ]
    ctx = _ctx(user)
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=project)), \
         patch.object(service, "project_obligations", AsyncMock(return_value=rows)):
        result = await chat_tools.list_project_inbox(ctx)
    assert ctx.deps.inbox_read is True
    assert result["count"] == 2  # replaced items left out
    first = result["items"][0]
    assert first["due"] == "2026-07-30" and first["formula"].endswith("2026-07-30")
    assert first["sources"] == [{"document_title": "Subaward.pdf", "page": 2}]
    assert result["items"][1]["status"] == "done"


@pytest.mark.asyncio
async def test_an_empty_inbox_says_so(project_env):
    project, user, _ = project_env
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=project)), \
         patch.object(service, "project_obligations", AsyncMock(return_value=[])):
        result = await chat_tools.list_project_inbox(_ctx(user))
    assert result["message"] == 'The RA inbox for "NIH Subaward" is empty.'


def test_reading_the_inbox_is_registered_and_parallel_safe():
    assert chat_tools.list_project_inbox in chat_tools.TOOLS
    assert "list_project_inbox" in chat_tools.PARALLEL_SAFE_TOOLS


@pytest.mark.asyncio
async def test_repeated_unverifiable_proposals_stop_and_explain(project_env):
    project, user, _ = project_env
    ctx = _ctx(user)
    nothing = {"accepted": [], "rejected": [{"title": "Invention disclosure", "reason": "the quote was not found"}]}
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=project)), \
         patch("app.services.project_service.can_manage_project", AsyncMock(return_value=True)), \
         patch.object(service, "propose", AsyncMock(return_value=nothing)) as propose:
        first = await chat_tools.propose_obligations(ctx, [{"kind": "deadline"}])
        second = await chat_tools.propose_obligations(ctx, [{"kind": "deadline"}])
        third = await chat_tools.propose_obligations(ctx, [{"kind": "deadline"}])
    assert "could be checked" in first["error"] and "could be checked" in second["error"]
    assert third["error"].startswith("Stopped")
    assert "Do not call propose_obligations again" in third["hint"]
    assert propose.await_count == 2


@pytest.mark.asyncio
async def test_a_recurring_deadline_already_in_the_inbox_is_not_proposed_again(project_env, monkeypatch):
    """The inbox's "Semi-annual results due" vs the new "Semi-annual results report"."""
    project, user, _ = project_env
    rows = [r["clean"] for r in (await service.propose(project, user, [proposal(SEMIANNUAL, "Semi-annual results due")]))["accepted"]]
    existing = [Obligation.model_construct(uuid=str(i), project_uuid=project.uuid, created_by=user.user_id, status="open", **r)
                for i, r in enumerate(rows)]
    monkeypatch.setattr(service, "Obligation", fake_model(existing))
    again = await service.propose(project, user, [proposal(SEMIANNUAL, "Semi-annual results report")])
    assert again["accepted"] == []
    assert len(again["rejected"]) == len(rows)
    assert all("already in" in r["reason"] for r in again["rejected"])


@pytest.mark.asyncio
async def test_a_differently_quoted_rule_with_the_same_calculation_is_the_same_deadline(project_env, monkeypatch):
    project, user, _ = project_env
    row = (await service.propose(project, user, [proposal(SEMIANNUAL, "Semi-annual results")]))["accepted"][0]["clean"]
    old = Obligation.model_construct(uuid="old", project_uuid=project.uuid, created_by=user.user_id, status="open", **row)
    monkeypatch.setattr(service, "Obligation", fake_model([old]))
    reworded = row["deadline_calculation"].model_copy(update={"rule": "Results are due 30 days after each June 30."})
    assert await service.is_duplicate(project.uuid, {**row, "title": "Semi-annual results report", "deadline_calculation": reworded})
    # A different deliverable on the same date stays separate.
    assert not await service.is_duplicate(project.uuid, {**row, "title": "Invention disclosure", "deadline_calculation": reworded})


@pytest.mark.parametrize("text", [
    "Upcoming deadlines from the RA inbox: semi-annual results, RPPR progress inputs.",
    "<h2>Deadlines (RA inbox)</h2>",
    "<p>Items listed in this project's RA inbox</p>",
])
def test_credits_inbox(text):
    assert credits_inbox(text)


@pytest.mark.parametrize("text", [
    "Deadlines from the subaward agreement, pp. 2-3.",
    "Want me to add these to the RA inbox?",
])
def test_does_not_credit_inbox(text):
    assert not credits_inbox(text)


@pytest.mark.asyncio
async def test_a_page_crediting_an_unread_inbox_is_sent_back():
    ctx = _ctx(SimpleNamespace(user_id="user1"))
    html = "<h1>Award Snapshot</h1><h2>Upcoming deadlines from the RA inbox</h2><ul><li>RPPR</li></ul>"
    with patch.object(chat_artifact_tools.chat_page_previews, "prepare", AsyncMock()) as prepare:
        result = await chat_artifact_tools.create_html_artifact(ctx, "Award Snapshot", html)
        assert result == {"error": PAGE_ERROR}
        prepare.assert_not_awaited()
    ctx.deps.inbox_read = True
    try:
        after_reading = await chat_artifact_tools.create_html_artifact(ctx, "Award Snapshot", html)
    except Exception:  # the preview pipeline isn't set up here; getting past the check is the point
        after_reading = None
    assert after_reading != {"error": PAGE_ERROR}


chat_harness = test_chat_output.chat_harness


@pytest.mark.asyncio
async def test_a_reply_crediting_an_unread_inbox_gets_a_source_note(chat_harness):
    from pydantic_ai import Agent
    from pydantic_ai.models.function import FunctionModel

    async def respond(messages, info):
        yield "Upcoming deadlines from the RA inbox: semi-annual results (Jul 30, 2026)."

    await chat_harness.run(Agent(FunctionModel(stream_function=respond)), message="Use the RA inbox deadlines.")
    assert chat_harness.finalize.call_args.args[1].endswith(REPLY_NOTE)


@pytest.mark.asyncio
async def test_inside_a_project_due_and_needed_lists_only_that_projects_open_items(monkeypatch):
    """Support ticket: the NIFA project's panel listed the NIH project's deadlines."""
    from app.routers import obligations as routes

    nifa = SimpleNamespace(uuid="nifa", title="NIFA Subaward")
    user = SimpleNamespace(user_id="ra", home_inbox_hidden=True)
    inbox = AsyncMock(return_value=[{"uuid": "greenhouse", "project_uuid": "nifa"}])
    monkeypatch.setattr(routes, "_project_for", AsyncMock(return_value=nifa))
    monkeypatch.setattr(service, "inbox", inbox)
    result = await routes.list_obligations(project_uuid="nifa", include_dismissed=False, user=user)
    assert result == {"items": [{"uuid": "greenhouse", "project_uuid": "nifa"}], "inbox_hidden": False, "project_count": 1}
    assert inbox.await_args.kwargs == {"include_dismissed": False, "projects": {"nifa": nifa}}


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"deadline_type": "other", "deadline_calculation": None},  # both stated, typed differently
    {"deadline_calculation": None},  # stated date vs timing rule
    {"title": "Validated qPCR assay protocol due."},  # wording around the same title
])
async def test_the_same_deadline_proposed_again_is_already_in_the_inbox(project_env, monkeypatch, change):
    """Support ticket: qPCR protocol, Jun 30 2026, appeared twice ("Limit" and "Timing rule" chips)."""
    project, user, _ = project_env
    row = (await service.propose(project, user, [proposal(title="Validated qPCR assay protocol")]))["accepted"][0]["clean"]
    stated = {**row, "deadline_calculation": None, "deadline_type": "report_due"}
    old = Obligation.model_construct(uuid="old", project_uuid=project.uuid, created_by=user.user_id, status="open", **stated)
    monkeypatch.setattr(service, "Obligation", fake_model([old]))
    assert await service.is_duplicate(project.uuid, {**row, **change})


@pytest.mark.asyncio
async def test_a_different_deliverable_on_the_same_date_is_not_a_duplicate(project_env, monkeypatch):
    project, user, _ = project_env
    row = (await service.propose(project, user, [proposal(title="Validated qPCR assay protocol")]))["accepted"][0]["clean"]
    old = Obligation.model_construct(uuid="old", project_uuid=project.uuid, created_by=user.user_id, status="open",
                                     **{**row, "deadline_calculation": None, "deadline_type": "report_due"})
    monkeypatch.setattr(service, "Obligation", fake_model([old]))
    assert not await service.is_duplicate(project.uuid, {**row, "title": "Invention disclosure", "deadline_type": "other"})


@pytest.mark.asyncio
async def test_a_rerun_that_finds_only_done_items_says_nothing_new_instead_of_failing(project_env):
    """Support ticket: after "Greenhouse trial dataset due" was marked Done,
    the same request offered it again. With it recognised, the tool must not
    answer "couldn't be checked" (which sends the model off to re-quote it)
    or count the call towards the retry stop."""
    project, user, _ = project_env
    ctx = _ctx(user)
    only_done = {"accepted": [], "rejected": [
        {"title": "Greenhouse trial dataset", "reason": "already in this project's inbox, marked done"},
    ]}
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=project)), \
         patch("app.services.project_service.can_manage_project", AsyncMock(return_value=True)), \
         patch.object(service, "propose", AsyncMock(return_value=only_done)):
        result = await chat_tools.propose_obligations(ctx, [{"kind": "deadline"}])
    assert "error" not in result and "needs_confirmation" not in result
    assert result["added"] == []
    assert result["already_in_inbox"] == [
        {"title": "Greenhouse trial dataset", "explanation": "Already marked done in this inbox."},
    ]
    assert "Nothing new to add" in result["message"]
    assert getattr(ctx.deps, "obligation_failures", 0) == 0
