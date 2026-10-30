"""Relative RA deadlines use source-bound calendar math and reviewed writes."""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.obligation import Obligation, ObligationSource
from app.services import chat_tools, obligation_service as service
from app.services.relative_deadlines import calculate_deadlines
from tests.conftest import fake_model
from tests.test_chat_tools import _make_context


def source(quote, role):
    return ObligationSource(document_uuid="subaward", document_title="Subaward.pdf", page=1, quote=quote, role=role)


PERFORMANCE = source("Period of Performance: January 1, 2025 through December 31, 2027.", "period_of_performance")
SEMIANNUAL = source("Semi-annual results are due within 30 days of each June 30 and December 31.", "timing")
RPPR = source("RPPR is due 45 days before the end of each budget period.", "timing")
FINAL = source("Final invoice and report are due within 60 days after the end of the Period of Performance.", "timing")
BUDGETS = [source(f"Budget period: January 1, {year} through December 31, {year}.", "budget_period") for year in (2025, 2026, 2027)]


def proposal(rule=FINAL, title="Final invoice and report", extra=()):
    return {"kind": "deadline", "deadline_type": "report_due", "title": title, "relative_deadline": True,
            "sources": [s.model_dump() for s in [rule, PERFORMANCE, *extra]]}


def test_final_report_includes_the_2028_leap_day():
    (row,) = calculate_deadlines([FINAL, PERFORMANCE])
    assert row["due_at"] == datetime.datetime(2028, 2, 29)
    assert row["deadline_calculation"].formula == "2027-12-31 + 60 calendar days = 2028-02-29"
    assert row["deadline_calculation"].rule == FINAL.quote


@pytest.mark.parametrize("year,expected", [(2026, "2027-03-01"), (2027, "2028-02-29")])
def test_an_explicit_end_date_supports_closeout_with_and_without_a_leap_year(year, expected):
    period = source(f"Period of Performance ends December 31, {year}.", "period_of_performance")
    (row,) = calculate_deadlines([FINAL, period])
    assert row["due_at"].date().isoformat() == expected


def test_rppr_subtracts_45_days_without_inclusive_counting():
    rows = calculate_deadlines([RPPR, PERFORMANCE, *BUDGETS])
    assert [r["due_at"].date().isoformat() for r in rows] == ["2025-11-16", "2026-11-16", "2027-11-16"]
    assert rows[1]["deadline_calculation"].formula == "2026-12-31 − 45 calendar days = 2026-11-16"


def test_semiannual_expands_every_anchor_and_keeps_dates_after_performance_end():
    rows = calculate_deadlines([SEMIANNUAL, PERFORMANCE])
    assert [r["due_at"].date().isoformat() for r in rows] == [
        "2025-07-30", "2026-01-30", "2026-07-30", "2027-01-30", "2027-07-30", "2028-01-30",
    ]
    assert len({r["deadline_calculation"].anchor_date for r in rows}) == 6


def test_partial_performance_year_does_not_generate_earlier_anchors():
    period = source("Period of Performance: July 1, 2026 through December 31, 2026.", "period_of_performance")
    assert [r["due_at"].date().isoformat() for r in calculate_deadlines([SEMIANNUAL, period])] == ["2027-01-30"]


@pytest.mark.parametrize("sources,reason", [
    ([RPPR, PERFORMANCE], "do not infer"),
    ([FINAL], "Period of Performance dates"),
    ([FINAL, source("Period of Performance starts December 31, 2027.", "period_of_performance")], "end date"),
    ([FINAL, source("Period of Performance: January 1 through December 31, 2027.", "period_of_performance")], "years"),
    ([FINAL, source("Period of Performance: December 31, 2027 through January 1, 2025.", "period_of_performance")], "precede"),
    ([FINAL, source("Period of Performance starts January 1, 2025. Agreement signed December 31, 2027.", "period_of_performance")], "unrelated dates"),
    ([FINAL, source("Period of Performance ends December 31, 2027 at noon.", "period_of_performance")], "time of day"),
    ([source("Due within 30 business days after the end of the Period of Performance.", "timing"), PERFORMANCE], "calendar-day"),
    ([source("Due within 30 days after the end of the Period of Performance unless extended.", "timing"), PERFORMANCE], "exceptions"),
    ([source("Due within 30 days of each June 30 and December 31, whichever is earlier.", "timing"), PERFORMANCE], "qualifier"),
    ([RPPR, PERFORMANCE, source("Budget period: January 1, 2028 through December 31, 2028.", "budget_period")], "outside"),
])
def test_unsupported_or_missing_evidence_needs_clarification(sources, reason):
    with pytest.raises(ValueError, match=reason):
        calculate_deadlines(sources)


@pytest.fixture
def project_env(monkeypatch):
    project = SimpleNamespace(uuid="project", title="NIH Subaward", team_id=None)
    user = SimpleNamespace(user_id="user1")
    text = "\n".join(s.quote for s in [PERFORMANCE, SEMIANNUAL, RPPR, FINAL, *BUDGETS])
    doc = SimpleNamespace(uuid="subaward", title="Subaward.pdf", raw_text=text, text_markers=None)
    read = AsyncMock(return_value=doc)
    monkeypatch.setattr(service, "_readable_document", read)
    monkeypatch.setattr(service, "Obligation", fake_model([]))
    return project, user, read


@pytest.mark.asyncio
async def test_full_proposal_checks_quotes_and_ignores_the_models_wrong_date(project_env):
    project, user, read = project_env
    checked = await service.propose(project, user, [
        {**proposal(), "due_at": "2028-03-01"},
        {**proposal(RPPR, "RPPR", BUDGETS), "due_at": "2026-11-17"},
        proposal(SEMIANNUAL, "Semi-annual results"),
    ])
    assert checked["rejected"] == []
    assert len(checked["accepted"]) == 10
    assert all(row["replaces"] is None for row in checked["accepted"])
    assert checked["accepted"][0]["clean"]["due_at"] == datetime.datetime(2028, 2, 29)
    assert checked["accepted"][2]["clean"]["due_at"] == datetime.datetime(2026, 11, 16)
    assert read.await_count == 9  # All passages, including each budget period.


@pytest.mark.asyncio
async def test_fabricated_or_inaccessible_anchor_is_rejected(project_env):
    project, user, read = project_env
    item = proposal()
    item["sources"][1]["quote"] = "Period of Performance: January 1, 2025 through December 31, 2028."
    checked = await service.propose(project, user, [item])
    assert checked["accepted"] == []
    assert "not found" in checked["rejected"][0]["reason"]
    read.return_value = None
    assert (await service.propose(project, user, [proposal()]))["accepted"] == []


@pytest.mark.asyncio
async def test_relative_anchor_cannot_be_saved_as_an_explicit_deadline(project_env):
    project, user, _ = project_env
    item = {**proposal(), "relative_deadline": False, "due_at": "2027-12-31"}
    checked = await service.propose(project, user, [item])
    assert checked["accepted"] == []
    assert "relative_deadline=true" in checked["rejected"][0]["reason"]


@pytest.mark.asyncio
async def test_occurrences_and_distinct_reports_do_not_replace_or_hide_each_other(project_env, monkeypatch):
    project, user, _ = project_env
    row = (await service.propose(project, user, [proposal()]))["accepted"][0]["clean"]
    old = Obligation.model_construct(uuid="old", project_uuid=project.uuid, created_by=user.user_id, **row)
    monkeypatch.setattr(service, "Obligation", fake_model([old]))
    assert await service.find_replaced(project.uuid, row) is None
    assert await service.is_duplicate(project.uuid, row)
    assert not await service.is_duplicate(project.uuid, {**row, "title": "A separate final report"})
    assert await service.find_replaced(project.uuid, {**row, "deadline_calculation": None,
                                                     "due_at": datetime.datetime(2028, 3, 1)}) is None
    result = service.serialize(old, user)
    assert result["deadline_calculation"]["formula"].endswith("2028-02-29")
    assert result["sources"][0]["quote"] == FINAL.quote


@pytest.mark.asyncio
async def test_saving_all_occurrences_keeps_each_open_and_preserves_the_formula(project_env, monkeypatch):
    project, user, _ = project_env
    checked = await service.propose(project, user, [proposal(SEMIANNUAL, "Semi-annual results")])
    saved = []

    async def insert(self):
        saved.append(self)

    model = fake_model(saved)
    model.__new__ = lambda cls, **values: Obligation.model_construct(**values)
    monkeypatch.setattr(service, "Obligation", model)
    monkeypatch.setattr(Obligation, "insert", insert)
    for row in checked["accepted"]:
        await service.save_checked(project, user, row["clean"])
    assert len(saved) == 6
    assert all(ob.status == "open" and ob.supersedes is None and ob.superseded_by is None for ob in saved)
    assert len({ob.due_at for ob in saved}) == 6
    assert all(service.serialize(ob, user)["deadline_calculation"]["rule"] == SEMIANNUAL.quote for ob in saved)


@pytest.mark.asyncio
async def test_calculated_preview_requires_next_turn_approval_before_saving(project_env):
    project, user, _ = project_env
    conv = SimpleNamespace(pending_confirmations=[], save=AsyncMock())
    ctx = _make_context(conversation=conv)
    ctx.deps.user = user
    saved = []

    async def save(project, user, clean):
        saved.append(clean)
        return Obligation.model_construct(uuid=str(len(saved)), project_uuid=project.uuid, created_by=user.user_id, **clean)

    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=project)), \
         patch("app.services.project_service.can_manage_project", AsyncMock(return_value=True)), \
         patch.object(service, "save_checked", side_effect=save) as write:
        items = [proposal(), proposal(SEMIANNUAL, "Semi-annual results")]
        preview = await chat_tools.propose_obligations(ctx, items, confirmed=True)
        assert preview["needs_confirmation"] is True
        assert "2027-12-31 + 60 calendar days = 2028-02-29" in preview["preview"]
        assert PERFORMANCE.quote in preview["preview"]
        assert FINAL.quote in preview["preview"]
        assert '"Add to inbox" button' in preview["assistant_instruction"]
        assert (await chat_tools.propose_obligations(ctx, items, confirmed=True))["needs_confirmation"]
        write.assert_not_called()
        ctx.deps.turn_marker += 2
        result = await chat_tools.propose_obligations(ctx, items, confirmed=True)
    assert len(result["added"]) == 7
    assert len(saved) == 7
    assert result["added"][0]["deadline_calculation"]["anchor_date"] == "2027-12-31"


@pytest.mark.asyncio
async def test_changed_calculation_requires_a_fresh_preview(project_env):
    project, user, _ = project_env
    ctx = _make_context(conversation=SimpleNamespace(pending_confirmations=[], save=AsyncMock()))
    ctx.deps.user = user
    with patch.object(chat_tools, "_resolve_active_project", AsyncMock(return_value=project)), \
         patch("app.services.project_service.can_manage_project", AsyncMock(return_value=True)), \
         patch.object(service, "save_checked", AsyncMock()) as write:
        await chat_tools.propose_obligations(ctx, [proposal()])
        ctx.deps.turn_marker += 2
        changed = await service.propose(project, user, [proposal()])
        changed["accepted"][0]["clean"]["due_at"] = datetime.datetime(2028, 3, 1)
        with patch.object(service, "propose", AsyncMock(return_value=changed)):
            result = await chat_tools.propose_obligations(ctx, [proposal()], confirmed=True)
        assert result["needs_confirmation"] is True
        write.assert_not_called()


@pytest.mark.asyncio
async def test_manual_endpoint_cannot_skip_calculation_review(project_env):
    from app.routers import obligations as routes

    project, user, _ = project_env
    with patch.object(routes, "_project_for", AsyncMock(return_value=project)), \
         patch.object(service, "save_checked", AsyncMock()) as write:
        response = await routes.create_obligations(routes.CreateObligationsRequest(project_uuid=project.uuid, items=[proposal()]), user)
    assert response["created"] == []
    assert "Review and approve" in response["rejected"][0]["reason"]
    write.assert_not_called()
