"""A project file is deleted after deadlines were taken from it (support ticket).

The items stayed open, kept sending reminders and still cited the file; the
deleted file could be attached to chat, which then answered "Document not
found: <id>". No database: documents and obligations are stand-ins.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.obligation import Obligation, ObligationSource
from app.services import deadline_reminders, obligation_service
from tests.conftest import fake_model


def _ob(uuid: str, document_uuid: str, **kw) -> Obligation:
    # model_construct: a Beanie Document can't be built without init_beanie.
    return Obligation.model_construct(
        uuid=uuid, project_uuid="p", kind="deadline", title="Greenhouse dataset",
        due_at=datetime.datetime(2026, 12, 15), created_by="u", status="open",
        dismissed_by=[], kept_without_source=kw.pop("kept", False),
        deadline_type=None, due_text=None, deadline_calculation=None,
        limit_value=None, observed_value=None, unit=None, supersedes=None, superseded_by=None,
        sources=[ObligationSource(document_uuid=document_uuid, document_title="16-delete-test.pdf",
                                  page=1, quote="The dataset is due December 15, 2026.")],
        **kw,
    )


def _documents(*existing: str):
    """SmartDocument stand-in holding only *existing* uuids.

    ``find`` applies the query's ``uuid: {$in: [...]}`` filter, so a test fails
    if the code asks for the wrong documents, and supports the projection and
    count the real queries use.
    """
    model = MagicMock()

    def find(query):
        wanted = set((query.get("uuid") or {}).get("$in") or [])
        rows = [SimpleNamespace(uuid=u) for u in existing if u in wanted]
        result = MagicMock()
        result.project.return_value = result
        result.to_list = AsyncMock(return_value=rows)
        result.count = AsyncMock(return_value=len(rows))
        return result

    model.find = MagicMock(side_effect=find)
    return model


async def test_a_cited_file_that_no_longer_exists_is_reported_deleted():
    obligations = [_ob("o1", "gone"), _ob("o2", "kept-file")]
    with patch.object(obligation_service, "SmartDocument", _documents("kept-file")) as docs:
        deleted = await obligation_service.deleted_source_uuids(obligations)
    assert deleted == {"gone"}
    # Soft-deleted files count as gone too.
    query = docs.find.call_args.args[0]
    assert query["soft_deleted"] == {"$ne": True}
    assert set(query["uuid"]["$in"]) == {"gone", "kept-file"}


async def test_items_without_sources_cost_no_lookup():
    ob = _ob("o1", "x")
    ob.sources = []
    with patch.object(obligation_service, "SmartDocument", _documents()) as docs:
        assert await obligation_service.deleted_source_uuids([ob]) == set()
    docs.find.assert_not_called()


def test_the_inbox_row_says_which_source_is_gone():
    user = SimpleNamespace(user_id="u")
    row = obligation_service.serialize(_ob("o1", "gone"), user, "Project", {"gone"})
    assert row["source_deleted"] is True
    assert row["kept_without_source"] is False
    assert row["sources"][0]["deleted"] is True

    intact = obligation_service.serialize(_ob("o2", "here"), user, "Project", {"gone"})
    assert intact["source_deleted"] is False
    assert intact["sources"][0]["deleted"] is False


def test_an_item_waits_for_a_decision_until_someone_keeps_it():
    assert obligation_service.awaiting_source_decision(_ob("o1", "gone"), {"gone"})
    assert not obligation_service.awaiting_source_decision(_ob("o1", "gone", kept=True), {"gone"})
    assert not obligation_service.awaiting_source_decision(_ob("o1", "here"), {"gone"})


async def test_keeping_an_item_is_saved():
    # A plain stand-in: a Beanie Document won't take a mocked save().
    ob = SimpleNamespace(kept_without_source=False, updated_at=None, save=AsyncMock())
    await obligation_service.set_kept_without_source(ob, True)
    assert ob.kept_without_source is True
    ob.save.assert_awaited_once()


async def test_reminders_skip_a_deadline_whose_file_was_deleted_until_it_is_kept():
    undecided, kept, intact = _ob("o1", "gone"), _ob("o2", "gone", kept=True), _ob("o3", "here")
    with patch.object(deadline_reminders, "Obligation", fake_model([undecided, kept, intact])), \
         patch.object(obligation_service, "SmartDocument", _documents("here")):
        remind = await deadline_reminders._open_deadlines()
    assert [o.uuid for o in remind] == ["o2", "o3"]


async def test_chat_says_a_file_was_deleted_in_words_not_an_id():
    from app.routers import chat

    with patch("app.models.document.SmartDocument", _documents()):
        error = await chat._missing_documents_error(["81C2C334A9494C5C8854312DBCC8B8CF"])

    assert error.status_code == 404
    assert "81C2C334" not in error.detail
    assert error.detail == (
        "A file attached to this chat was deleted. Remove it from the chat, then send your message again."
    )
    # The client uses these to name the file, detach it and drop Retry.
    assert error.headers["X-Chat-Error"] == "document_missing"
    assert error.headers["X-Missing-Documents"] == "81C2C334A9494C5C8854312DBCC8B8CF"
    assert error.headers["X-Missing-Reason"] == "deleted"


async def test_chat_does_not_claim_deletion_when_the_file_still_exists():
    from app.routers import chat

    with patch("app.models.document.SmartDocument", _documents("someone-elses")):
        error = await chat._missing_documents_error(["someone-elses"])

    assert error.headers["X-Missing-Reason"] == "unavailable"
    assert "no longer available to you" in error.detail
