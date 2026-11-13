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


def test_approval_card_evidence_drops_table_markup_but_keeps_the_stored_quote():
    """Support ticket: card evidence read "<td>Period of Performance</td><td>January 1, ..."."""
    quote = "<td>Period of Performance</td><td>January 1, 2026 through December 31, 2027</td>"
    period = source(quote, "period_of_performance")
    (row,) = calculate_deadlines([FINAL, period])
    line = chat_tools._describe_obligation({"kind": "deadline", "title": "Final report", **row, "sources": [FINAL, period]})
    assert 'period of performance: "Period of Performance January 1, 2026 through December 31, 2027"' in line
    assert "<td>" not in line
    assert period.quote == quote
    assert service.plain_quote("Costs &amp; fees<br/>\n  apply") == "Costs & fees apply"


# ── Period dates in a table (support ticket) ────────────────────────────────
# A NIFA subaward gave Start Date / End Date (Aug 31, 2027) in a page-1 table;
# both final reports, due 120 days after the End Date, were refused as
# "supporting passage could not be verified".

FINAL_120 = source("Final technical and financial reports are due 120 days after the End Date.", "timing")
CLOSEOUT = datetime.datetime(2027, 12, 29)


@pytest.mark.parametrize("quote", [
    # Markdown (pdf-inspector), header row over a value row.
    "| Award No. | Start Date | End Date |\n| --- | --- | --- |\n| 2025-67019 | Sep 1, 2025 | Aug 31, 2027 |",
    # Markdown key/value rows.
    "| Start Date | September 1, 2025 |\n| End Date | August 31, 2027 |",
    # HTML cells (OCR / Docling), header over values.
    "<table><tr><th>Start Date</th><th>End Date</th></tr><tr><td>09/01/2025</td><td>08/31/2027</td></tr></table>",
    # HTML, one row of label/value pairs.
    "<tr><td>Start Date</td><td>Sep 1, 2025</td><td>End Date</td><td>Aug 31, 2027</td></tr>",
    # PyMuPDF tab-joined row.
    "Subaward Period\tStart Date\tEnd Date\n\tSep 1, 2025\tAug 31, 2027",
    # PyMuPDF one cell per line.
    "Start Date\nEnd Date\nSeptember 1, 2025\nAugust 31, 2027",
    # A labeled cell holding its own date.
    "| Start Date: Sep 1, 2025 | End Date: Aug 31, 2027 |",
])
def test_end_date_in_a_table_anchors_the_final_reports(quote):
    (row,) = calculate_deadlines([FINAL_120, source(quote, "period_of_performance")])
    assert row["due_at"] == CLOSEOUT
    assert row["deadline_calculation"].anchor_date == "2027-08-31"


@pytest.mark.parametrize("quote,reason", [
    ("| Period | Start Date | End Date |\n| --- | --- | --- |\n| Year 1 | Sep 1, 2025 | Aug 31, 2026 |\n| Year 2 | Sep 1, 2026 | Aug 31, 2027 |",
     "more than one"),
    ("| Start Date | End Date |\n| --- | --- |\n| Aug 31, 2027 | Sep 1, 2025 |", "precede"),
    ("| Start Date | End Date |\n| --- | --- |\n| Sep 1, 2025 | Aug 31 |", "years"),
])
def test_a_table_period_still_needs_one_complete_row(quote, reason):
    with pytest.raises(ValueError, match=reason):
        calculate_deadlines([FINAL_120, source(quote, "period_of_performance")])


def test_a_cut_off_header_cannot_shift_columns():
    """"End Date |" over a full value row would pair End Date with the start."""
    quote = "End Date |\n| Sep 1, 2025 | Aug 31, 2027 |"
    with pytest.raises(ValueError):
        calculate_deadlines([FINAL_120, source(quote, "period_of_performance")])


def test_a_rule_quoted_from_a_reporting_table_keeps_its_anchor():
    rule = source("<td>Final technical report</td><td>120 days after the End Date</td>", "timing")
    period = source("| Start Date | End Date |\n| --- | --- |\n| Sep 1, 2025 | Aug 31, 2027 |", "period_of_performance")
    (row,) = calculate_deadlines([rule, period])
    assert row["due_at"] == CLOSEOUT


@pytest.mark.asyncio
@pytest.mark.parametrize("page_table,model_quote", [
    ("| Start Date | End Date |\n| --- | --- |\n| Sep 1, 2025 | Aug 31, 2027 |", "Start Date End Date Sep 1, 2025 Aug 31, 2027"),
    ("| Start Date | End Date |\n|---|---|\n| Sep 1, 2025 | Aug 31, 2027 |", "| Sep 1, 2025 | Aug 31, 2027 |\nEnd Date"),
    ("| Start Date | Sep 1, 2025 |\n| End Date | Aug 31, 2027 |", "End Date Aug 31, 2027"),
    ("<table><tr><td>Start Date</td><td>Sep 1, 2025</td><td>End Date</td><td>Aug 31, 2027</td></tr></table>", "End Date Aug 31, 2027"),
])
async def test_a_quote_read_from_a_table_verifies_and_stores_the_documents_text(monkeypatch, page_table, model_quote):
    project = SimpleNamespace(uuid="project", title="NIFA Subaward", team_id=None)
    user = SimpleNamespace(user_id="user1")
    text = f"SUBAWARD AGREEMENT\n{page_table}\nReporting\n{FINAL_120.quote}\n"
    doc = SimpleNamespace(uuid="subaward", title="Subaward.pdf", raw_text=text, text_markers=None)
    monkeypatch.setattr(service, "_readable_document", AsyncMock(return_value=doc))
    monkeypatch.setattr(service, "Obligation", fake_model([]))
    item = {"kind": "deadline", "deadline_type": "report_due", "title": "Final technical report",
            "relative_deadline": True, "sources": [
                FINAL_120.model_dump(),
                {**source(model_quote, "period_of_performance").model_dump(), "page": None},
            ]}
    if model_quote.startswith("| Sep"):
        # Not contiguous in the document, so it must not verify.
        checked = await service.propose(project, user, [item])
        assert checked["accepted"] == [] and "not found" in checked["rejected"][0]["reason"]
        return
    checked = await service.propose(project, user, [item])
    assert checked["rejected"] == []
    (accepted,) = checked["accepted"]
    assert accepted["clean"]["due_at"] == CLOSEOUT
    stored = accepted["clean"]["sources"][1].quote
    assert stored in text and "Aug 31, 2027" in stored


@pytest.mark.asyncio
async def test_a_table_quote_with_a_date_the_document_lacks_is_still_refused(monkeypatch):
    project = SimpleNamespace(uuid="project", title="NIFA Subaward", team_id=None)
    text = "| Start Date | End Date |\n| --- | --- |\n| Sep 1, 2025 | Aug 31, 2027 |\n" + FINAL_120.quote
    doc = SimpleNamespace(uuid="subaward", title="Subaward.pdf", raw_text=text, text_markers=None)
    monkeypatch.setattr(service, "_readable_document", AsyncMock(return_value=doc))
    monkeypatch.setattr(service, "Obligation", fake_model([]))
    item = {"kind": "deadline", "deadline_type": "report_due", "title": "Final report", "relative_deadline": True,
            "sources": [FINAL_120.model_dump(),
                        {**source("Start Date End Date Sep 1, 2025 Aug 31, 2028", "period_of_performance").model_dump(), "page": None}]}
    checked = await service.propose(project, SimpleNamespace(user_id="user1"), [item])
    assert checked["accepted"] == [] and "not found" in checked["rejected"][0]["reason"]


@pytest.mark.asyncio
async def test_a_deadline_marked_done_is_not_proposed_again(project_env, monkeypatch):
    """Support ticket: "Greenhouse trial dataset due", marked Done, came back
    as "1 item to add" on the next run because only open items were compared."""
    project, user, _ = project_env
    row = (await service.propose(project, user, [proposal()]))["accepted"][0]["clean"]
    done = Obligation.model_construct(uuid="done", project_uuid=project.uuid, created_by=user.user_id, status="done", **row)
    monkeypatch.setattr(service, "Obligation", fake_model([done]))

    assert (await service.find_existing(project.uuid, row)).uuid == "done"
    checked = await service.propose(project, user, [proposal()])
    assert checked["accepted"] == []
    assert checked["rejected"][0]["reason"] == "already in this project's inbox, marked done"

    # An item an amendment replaced is no longer in the inbox.
    superseded = Obligation.model_construct(uuid="old", project_uuid=project.uuid, created_by=user.user_id, status="superseded", **row)
    monkeypatch.setattr(service, "Obligation", fake_model([superseded]))
    assert await service.find_existing(project.uuid, row) is None


@pytest.mark.asyncio
async def test_a_dismissed_item_says_so_and_an_open_copy_wins(project_env, monkeypatch):
    project, user, _ = project_env
    row = (await service.propose(project, user, [proposal()]))["accepted"][0]["clean"]
    make = lambda uuid, **extra: Obligation.model_construct(uuid=uuid, project_uuid=project.uuid, created_by=user.user_id, **{**row, **extra})  # noqa: E731
    monkeypatch.setattr(service, "Obligation", fake_model([make("dismissed", dismissed_by=[user.user_id])]))
    checked = await service.propose(project, user, [proposal()])
    assert checked["rejected"][0]["reason"] == "already in this project's inbox, dismissed by you"

    monkeypatch.setattr(service, "Obligation", fake_model([make("done", status="done"), make("open")]))
    assert (await service.find_existing(project.uuid, row)).uuid == "open"


def test_the_card_says_already_done():
    from app.services.chat_tools import _obligation_review_reason

    assert _obligation_review_reason("already in this project's inbox, marked done") == "Already marked done in this inbox."
    assert _obligation_review_reason("already in this project's inbox, dismissed by you") == "Already in this inbox; you dismissed it."
    assert _obligation_review_reason("already in this project's inbox or proposal") == "Already included in this inbox or proposal."


# ── Retests on builds 718 and 825 (support ticket, reopened) ────────────────
# An End Date cell with a remark after the date, "(18 months)", wasn't read as
# a date; the NIFA file's stored text also ran two rows together, so the cell
# beside "End Date" was another label.

NIFA_MERGED = "End Date|Federal Funds Obligated|August 31, 2027 (18 months) $95,550"
SIMPLE_18 = "| Start Date: | January 15, 2027 |\n| End Date: | July 14, 2028 (18 months) |"


@pytest.mark.parametrize("quote,end", [
    (NIFA_MERGED, "2027-08-31"),
    ("| Start Date | March 1, 2026 |\n" + NIFA_MERGED, "2027-08-31"),
    (SIMPLE_18, "2028-07-14"),
    ("| Start Date | End Date |\n| --- | --- |\n| Sep 1, 2025 | Aug 31, 2027 (24 months) |", "2027-08-31"),
    ("<tr><td>End Date</td><td>August 31, 2027 (18 months).</td></tr>", "2027-08-31"),
    ("Start Date\nEnd Date\nMarch 1, 2026\nAugust 31, 2027 (18 months)", "2027-08-31"),
])
def test_an_end_date_with_a_remark_or_in_a_merged_row_is_read(quote, end):
    (row,) = calculate_deadlines([FINAL_120, source(quote, "period_of_performance")])
    anchor = datetime.date.fromisoformat(end)
    assert row["deadline_calculation"].anchor_date == end
    assert row["due_at"].date() == anchor + datetime.timedelta(days=120)


@pytest.mark.parametrize("quote", [
    # Words other than a bracketed remark: not a plain End Date.
    "| End Date | Aug 31, 2027 or upon termination |",
    # A bracketed remark holding another date.
    "| End Date | Aug 31, 2027 (extended from Feb 28, 2027) |",
    # A merged row with two dates: which one is the End Date is unknown.
    "End Date|Signed|August 31, 2027 March 1, 2026",
    # A merged row naming another period label.
    "End Date|Start Date|August 31, 2027",
])
def test_an_unclear_end_date_cell_is_still_refused(quote):
    with pytest.raises(ValueError):
        calculate_deadlines([FINAL_120, source(quote, "period_of_performance")])


START_90 = source("The Subrecipient Kickoff Plan is due 90 days after the Start Date.", "timing")


def test_a_deadline_counted_from_the_start_date_is_calculated():
    (row,) = calculate_deadlines([START_90, source(SIMPLE_18, "period_of_performance")])
    assert row["due_at"] == datetime.datetime(2027, 4, 15)
    calc = row["deadline_calculation"]
    assert calc.anchor_kind == "performance_period_start" and calc.anchor_date == "2027-01-15"
    assert calc.formula == "2027-01-15 + 90 calendar days = 2027-04-15"


@pytest.mark.parametrize("rule,quote,reason", [
    ("due 90 days after the Start Date.", "| End Date | Aug 31, 2027 |", "Start Date"),
    ("due within 90 days of the Start Date.", SIMPLE_18, "before or after"),
])
def test_a_start_date_rule_needs_the_start_date_and_a_direction(rule, quote, reason):
    with pytest.raises(ValueError, match=reason):
        calculate_deadlines([source(rule, "timing"), source(quote, "period_of_performance")])


@pytest.mark.asyncio
@pytest.mark.parametrize("model_quote", [
    "End Date August 31, 2027",
    "End Date Federal Funds Obligated August 31, 2027 (18 months) $95,550",
])
async def test_the_nifa_merged_row_adds_both_final_reports_with_a_page(monkeypatch, model_quote):
    """Chat and the workflow both go through propose: the same row gives Dec 29, 2027."""
    project = SimpleNamespace(uuid="project", title="NIFA Subaward", team_id=None)
    text = ("SUBAWARD AGREEMENT\nStart Date|March 1, 2026\n" + NIFA_MERGED + "\n"
            "ARTICLE 2\n3. Final technical and financial reports are due 120 days after the End Date.\n")
    doc = SimpleNamespace(uuid="subaward", title="sample-subaward-NIFA-UI-OSU-2026-0412.pdf",
                          raw_text=text, text_markers=None)
    monkeypatch.setattr(service, "_readable_document", AsyncMock(return_value=doc))
    monkeypatch.setattr(service, "Obligation", fake_model([]))
    items = [{"kind": "deadline", "deadline_type": "report_due", "title": title, "relative_deadline": True,
              "sources": [FINAL_120.model_dump(), {**source(model_quote, "period_of_performance").model_dump(), "page": None}]}
             for title in ("Final technical report and dataset", "Final financial report and final invoice")]
    checked = await service.propose(project, SimpleNamespace(user_id="user1"), items)
    assert checked["rejected"] == []
    assert [a["clean"]["due_at"] for a in checked["accepted"]] == [CLOSEOUT, CLOSEOUT]
    assert all("August 31, 2027" in a["clean"]["sources"][1].quote for a in checked["accepted"])


@pytest.mark.asyncio
@pytest.mark.parametrize("model_quote", [
    "End Date August 31, 2027 (18 months)",
    "End Date August 31, 2028",          # a date the row doesn't give
    "Final technical report August 31, 2027",  # words that aren't in the row
])
async def test_a_period_quote_skipping_cells_matches_only_a_real_row(monkeypatch, model_quote):
    project = SimpleNamespace(uuid="project", title="NIFA Subaward", team_id=None)
    text = "Start Date|March 1, 2026\n" + NIFA_MERGED + "\n" + FINAL_120.quote + "\n"
    doc = SimpleNamespace(uuid="subaward", title="Subaward.pdf", raw_text=text, text_markers=None)
    monkeypatch.setattr(service, "_readable_document", AsyncMock(return_value=doc))
    monkeypatch.setattr(service, "Obligation", fake_model([]))
    item = {"kind": "deadline", "deadline_type": "report_due", "title": "Final report", "relative_deadline": True,
            "sources": [FINAL_120.model_dump(), {**source(model_quote, "period_of_performance").model_dump(), "page": None}]}
    checked = await service.propose(project, SimpleNamespace(user_id="user1"), [item])
    if model_quote.endswith("(18 months)"):
        assert checked["rejected"] == []
        assert checked["accepted"][0]["clean"]["sources"][1].quote == NIFA_MERGED
    else:
        assert checked["accepted"] == [] and "not found" in checked["rejected"][0]["reason"]


@pytest.mark.asyncio
async def test_a_quote_matching_two_rows_is_not_guessed(monkeypatch):
    text = "End Date|Year 1|August 31, 2027\nEnd Date|Year 2|August 31, 2027 (revised)\n" + FINAL_120.quote
    assert service._row_holding(text, "End Date August 31, 2027") is None
    # A timing quote never gets this leeway.
    assert service._document_span(text, "Final reports due 120 days after the End Date", "timing") is None
