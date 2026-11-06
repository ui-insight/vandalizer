"""Award snapshot: merging facts across documents, the shared Page, the chat tool."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.award_snapshot import fingerprint, merge_entities, page_html
from app.services.extraction_sources import SOURCE_KEY


def _src(doc, page, quote, support):
    return {"document_uuid": doc, "document_title": f"{doc}.pdf", "page": page, "quote": quote, "support": support}


def test_best_supported_value_wins_and_not_found_is_skipped():
    award = {
        "Sponsor": "National Institutes of Health",
        "Total award amount": "$243,200",
        "F&A rate": "Not found",
        "Budget period 1 amount": "$121,600",
        SOURCE_KEY: {
            "Sponsor": _src("subaward", 1, "Prime sponsor: National Institutes of Health", "supported"),
            "Total award amount": _src("subaward", 2, "the total amount of", "quote_unsupported"),
            "Budget period 1 amount": _src("subaward", 5, "Year 1 $121,600", "supported"),
        },
    }
    budget = {
        "Total award amount": "$243,200",
        "F&A rate": "52% MTDC",
        SOURCE_KEY: {
            "Total award amount": _src("budget", 1, "Total: $243,200", "supported"),
            "F&A rate": _src("budget", 1, "F&A at 52% MTDC", "supported"),
        },
    }
    facts, years = merge_entities([award, budget])
    by_label = {f.label: f for f in facts}
    assert [f.label for f in facts] == ["Sponsor", "Total amount", "F&A rate"], "in the snapshot's order"
    # The budget document's confirmed value beats the award's unconfirmed one.
    assert by_label["Total amount"].document_uuid == "budget" and by_label["Total amount"].support == "supported"
    assert by_label["F&A rate"].value == "52% MTDC"
    assert [(y.label, y.value, y.page) for y in years] == [("Year 1", "$121,600", 5)]


def test_unconfirmed_value_is_kept_and_marked():
    facts, _ = merge_entities([{"Award number": "R01AI123456", SOURCE_KEY: {}}])
    assert facts[0].value == "R01AI123456" and facts[0].support == "unverified"


def test_fingerprint_changes_when_a_document_is_added_or_reread():
    a = [{"uuid": "d1", "token_count": 10, "updated_at": "t1"}]
    assert fingerprint(a) == fingerprint(list(a))
    assert fingerprint(a) != fingerprint(a + [{"uuid": "d2", "token_count": 5, "updated_at": "t1"}])
    assert fingerprint(a) != fingerprint([{"uuid": "d1", "token_count": 11, "updated_at": "t2"}])


def _view(**over):
    v = {
        "project": {"uuid": "p", "title": "NIH Subaward <WSU>", "state": "awarded"},
        "facts": [
            {"label": "Total amount", "value": "$243,200", "support": "supported", "document_title": "Subaward.pdf", "page": 2},
            {"label": "Award number", "value": "R01", "support": "unverified", "document_title": None, "page": None},
        ],
        "budget_years": [{"label": "Year 1", "value": "$121,600", "support": "supported", "document_title": "Subaward.pdf", "page": 5}],
        "deadlines": {
            "overdue": [{"title": "Validated qPCR assay protocol", "due_at": "2026-07-03T00:00:00", "due_text": None,
                         "sources": [{"document_title": "Subaward.pdf", "page": 4}]}],
            "upcoming": [], "done": [], "needed": [],
        },
        "last_run": None, "pages": [], "built_at": "2026-11-01T10:00:00+00:00",
        "generated_at": "2026-11-03T10:00:00+00:00",
    }
    v.update(over)
    return v


def test_page_says_what_it_is_and_escapes_text():
    page = page_html(_view())
    assert "NIH Subaward &lt;WSU&gt;: award snapshot" in page
    assert "As of Nov 3, 2026. This page is a copy" in page
    assert "deadlines come from the project&#x27;s RA inbox" in page or "deadlines come from the project's RA inbox" in page
    assert "$243,200</td><td>Subaward.pdf, p. 2" in page
    assert "R01 (source not found)" in page
    assert "Validated qPCR assay protocol</strong> · Jul 3, 2026 · Subaward.pdf, p. 4" in page
    assert "Budget by year" in page and "Year 1" in page
    assert "No upcoming deadlines in the inbox." in page


@pytest.mark.asyncio
async def test_chat_tool_reports_sources_inbox_and_notes():
    from app.services import chat_snapshot_tools

    deps = SimpleNamespace(user=SimpleNamespace(user_id="u"), active_project_uuid="p", inbox_read=False)
    ctx = SimpleNamespace(deps=deps)
    project = SimpleNamespace(uuid="p", title="NIH Subaward")
    v = _view(status="ready", out_of_date=True)
    v["deadlines"]["overdue"][0]["days_until"] = -121
    with patch("app.services.chat_tools._resolve_active_project", new=AsyncMock(return_value=project)), \
         patch("app.services.award_snapshot.view", new=AsyncMock(return_value=v)):
        out = await chat_snapshot_tools.get_award_snapshot(ctx)
    assert deps.inbox_read is True, "its deadlines were read from the RA inbox"
    assert out["facts_read_from_documents"][0] == {
        "label": "Total amount", "value": "$243,200", "source": "Subaward.pdf, p. 2", "confirmed": "confirmed on the page",
    }
    assert out["facts_read_from_documents"][1]["confirmed"] == "source passage not found"
    assert out["ra_inbox_deadlines"]["overdue"][0]["days_until"] == -121
    assert out["notes"] == ["The project's documents changed after these facts were read."]


@pytest.mark.asyncio
async def test_chat_tool_without_a_project():
    from app.services import chat_snapshot_tools

    ctx = SimpleNamespace(deps=SimpleNamespace(user=SimpleNamespace(user_id="u"), active_project_uuid=None, inbox_read=False))
    out = await chat_snapshot_tools.get_award_snapshot(ctx)
    assert "No project is open" in out["error"]
