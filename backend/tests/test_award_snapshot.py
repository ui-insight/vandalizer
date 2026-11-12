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


# ---------------------------------------------------------------------------
# Support ticket: the snapshot cited a saved summary instead of the award.
# With the award PDF and a chat-saved "Award Snapshot — ….md" in one project,
# every key fact cited the summary; the PI read "Not confirmed by the passage".
# ---------------------------------------------------------------------------

from app.services.award_snapshot import is_generated, source_documents  # noqa: E402

PDF = {"uuid": "pdf", "title": "UI-OSU NIFA Subaward Agreement", "extension": "pdf", "token_count": 900, "updated_at": "t"}
SUMMARY = {"uuid": "md", "title": "Award Snapshot — UI-OSU-NIFA-2026-0412", "extension": "md",
           "generated_by": "chat", "token_count": 200, "updated_at": "t"}


def test_files_vandalizer_wrote_are_recognized():
    assert is_generated(SUMMARY)
    assert is_generated({"title": "Run output.csv", "extension": "csv", "origin_workflow_id": "wf"})
    assert is_generated({"title": "Report", "extension": "docx", "generated_by": "automation"})
    # Saved before generated_by existed: a summary's name in a text format.
    assert is_generated({"title": "Award Snapshot — UI-OSU-NIFA-2026-0412", "extension": "md"})
    assert not is_generated(PDF)
    assert not is_generated({"title": "Award Summary from sponsor", "extension": "pdf"})
    assert not is_generated({"title": "Budget justification", "extension": "md"})


def test_the_original_is_read_and_the_summary_skipped():
    # The summary's title is award-like too and sorts first alphabetically.
    read, skipped = source_documents([SUMMARY, PDF])
    assert [d["uuid"] for d in read] == ["pdf"]
    assert [d["uuid"] for d in skipped] == ["md"]


def test_only_summaries_are_read_when_there_is_no_original():
    read, skipped = source_documents([SUMMARY])
    assert [d["uuid"] for d in read] == ["md"] and skipped == []


def test_original_formats_are_read_before_text_files():
    notes = {"uuid": "txt", "title": "Award notes", "extension": "txt", "token_count": 5, "updated_at": "t"}
    read, _ = source_documents([notes, PDF])
    assert [d["uuid"] for d in read] == ["pdf", "txt"]


class _Coll:
    def __init__(self, rows=(), one=None):
        self.rows, self.one, self.updates = list(rows), one, []

    def find(self, *_a, **_k):
        return list(self.rows)

    def find_one(self, *_a, **_k):
        return self.one

    def update_one(self, flt, update):
        self.updates.append(update)
        return SimpleNamespace(matched_count=1)


def test_build_reads_only_the_award_pdf_and_records_the_skipped_summary():
    from contextlib import nullcontext

    from app.services import award_snapshot

    db = SimpleNamespace(
        award_snapshot=_Coll(one={"project_uuid": "p", "build_token": "tok", "requested_by": "u"}),
        project=_Coll(one={"uuid": "p", "root_folder_uuid": "f", "owner_user_id": "u", "team_id": None}),
        smart_document=_Coll(rows=[{**SUMMARY, "raw_text": "PI: someone"}, {**PDF, "raw_text": "PI: Dr. Lee"}]),
        system_config=_Coll(one={}),
    )
    engine = SimpleNamespace(extract=lambda *a, **k: engine.calls.append(k) or [{}])
    engine.calls = []
    with patch("app.tasks.get_sync_db", return_value=db), \
         patch("app.services.award_snapshot._folder_uuids_sync", return_value=["f"]), \
         patch("app.services.extraction_engine.ExtractionEngine", return_value=engine), \
         patch("app.services.metering.metered", return_value=nullcontext()), \
         patch("app.tasks.extraction_tasks._get_user_model_name", return_value="m"):
        assert award_snapshot.build_sync("p", "tok") == "ready"
    [call] = engine.calls
    assert call["doc_texts"] == ["PI: Dr. Lee"]
    assert [m["uuid"] for m in call["doc_metadata"]] == ["pdf"]
    saved = db.award_snapshot.updates[-1]["$set"]
    assert saved["documents"] == [{"uuid": "pdf", "title": PDF["title"], "generated": False}]
    assert saved["skipped_documents"] == [{"uuid": "md", "title": SUMMARY["title"]}]


def test_a_summary_saved_next_to_the_award_does_not_queue_a_rebuild():
    from app.services import award_snapshot

    db = SimpleNamespace(
        award_snapshot=_Coll(one={"built_at": "t"}),
        smart_document=_Coll(one={"_id": 1}),  # the project has an original
    )
    project = {"uuid": "p", "root_folder_uuid": "f"}
    with patch("app.tasks.document_tasks._find_project_for_folder", return_value=project), \
         patch("app.services.award_snapshot._folder_uuids_sync", return_value=["f"]), \
         patch("app.services.award_snapshot._dispatch") as dispatch:
        assert award_snapshot.queue_rebuild_for_document_sync(db, {**SUMMARY, "folder": "f"}) is False
        assert award_snapshot.queue_rebuild_for_document_sync(db, {**PDF, "folder": "f"}) is True
    dispatch.assert_called_once()


def test_page_says_which_facts_the_documents_do_not_state():
    page = page_html(_view(not_found=["PI(s)"]))
    assert "<th scope='row'>PI(s)</th><td>Not stated in the documents read</td>" in page


@pytest.mark.asyncio
async def test_chat_tool_says_which_facts_are_not_stated():
    from app.services import chat_snapshot_tools

    deps = SimpleNamespace(user=SimpleNamespace(user_id="u"), active_project_uuid="p", inbox_read=False)
    project = SimpleNamespace(uuid="p", title="NIH Subaward")
    with patch("app.services.chat_tools._resolve_active_project", new=AsyncMock(return_value=project)), \
         patch("app.services.award_snapshot.view", new=AsyncMock(return_value=_view(status="ready", not_found=["F&A rate"]))):
        out = await chat_snapshot_tools.get_award_snapshot(SimpleNamespace(deps=deps))
    assert out["not_stated_in_documents"] == ["F&A rate"]
