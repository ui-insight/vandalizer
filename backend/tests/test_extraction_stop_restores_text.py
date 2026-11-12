"""Stopping a re-read puts the previous text back.

Support ticket: Re-run OCR on a PDF whose text was fine, then Stop, left the
document with no text ("Text extraction was stopped. Retry to read this
document again.") until someone clicked Retry extraction. Chat and workflows
read an empty document in the meantime.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import document_service, extraction_snapshots


class _Snapshots:
    """An in-memory stand-in for the snapshot collection."""

    def __init__(self):
        self.rows = {}
        self.indexes = []

    async def create_index(self, field, **kwargs):
        self.indexes.append((field, kwargs))

    async def replace_one(self, query, row, upsert=False):
        self.rows[query["_id"]] = row

    async def find_one(self, query):
        return self.rows.get(query["_id"])

    async def delete_one(self, query):
        self.rows.pop(query["_id"], None)


def _doc(**stored):
    return SimpleNamespace(id="oid-1", uuid="doc-1", task_id="task-1", _extraction_restart_revision=4, **stored)


@pytest.fixture
def store(monkeypatch):
    snapshots = _Snapshots()
    monkeypatch.setattr(extraction_snapshots, "_collection", lambda: snapshots)
    monkeypatch.setattr(extraction_snapshots, "_index_ready", False)
    return snapshots


def _documents(raw):
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value=raw)
    collection.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    return collection


GOOD = {
    "raw_text": "Award No. 2026-0412. Period of performance ...", "token_count": 557,
    "text_markers": [{"page": 1, "offset": 0}], "extraction_nonletter_ratio": 0.01,
    "ingestion_warnings": [], "task_status": "complete", "validating": False,
    "error_message": None, "error_retryable": None, "text_layer_rejected": False,
}


async def test_a_reread_keeps_a_copy_of_the_text_it_is_about_to_clear(store):
    documents = _documents({"_id": "oid-1", **GOOD})
    with patch.object(extraction_snapshots.SmartDocument, "get_motor_collection", return_value=documents):
        assert await extraction_snapshots.save_previous_reading(_doc(), revision=5) is True

    saved = await extraction_snapshots.previous_reading("doc-1")
    assert saved["revision"] == 5
    assert saved["fields"] == GOOD
    # Copies expire on their own.
    assert store.indexes == [("saved_at", {"expireAfterSeconds": extraction_snapshots.KEEP_SECONDS})]


async def test_a_document_with_no_text_keeps_no_copy_and_drops_an_old_one(store):
    store.rows["doc-1"] = {"revision": 2, "fields": GOOD}
    documents = _documents({"_id": "oid-1", **GOOD, "raw_text": ""})
    with patch.object(extraction_snapshots.SmartDocument, "get_motor_collection", return_value=documents):
        assert await extraction_snapshots.save_previous_reading(_doc(), revision=5) is False
    assert await extraction_snapshots.previous_reading("doc-1") is None


async def test_a_failed_copy_never_blocks_the_reread(monkeypatch):
    def broken():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(extraction_snapshots, "_collection", broken)
    assert await extraction_snapshots.save_previous_reading(_doc(), revision=5) is False
    assert await extraction_snapshots.previous_reading("doc-1") is None
    await extraction_snapshots.discard("doc-1")


async def _stop(documents, doc):
    with patch.object(document_service.SmartDocument, "get_motor_collection", return_value=documents), \
         patch("app.celery_app.celery_app.control.revoke") as revoke:
        return await document_service.cancel_extraction(doc), revoke


async def test_stopping_a_reread_restores_the_previous_text(store):
    store.rows["doc-1"] = {"revision": 5, "fields": dict(GOOD)}
    documents = _documents(None)
    outcome, revoke = await _stop(documents, _doc())

    assert outcome == "restored"
    documents.update_one.assert_awaited_once()
    filter_, update = documents.update_one.call_args[0]
    # Only into the run the copy was taken for, and only while it has stored nothing.
    assert filter_["_extraction_restart_revision"] == 5
    assert filter_["raw_text"] == ""
    assert update["$set"]["raw_text"] == GOOD["raw_text"]
    assert update["$set"]["task_status"] == "complete"
    assert update["$set"]["token_count"] == 557
    assert update["$set"]["processing"] is False and update["$set"]["task_id"] is None
    # No "stopped" error is written over a document that reads fine.
    assert update["$set"]["error_message"] is None
    assert update["$inc"] == {"_extraction_restart_revision": 1}
    revoke.assert_called_once_with("task-1", terminate=True, signal="SIGTERM")
    # The copy is used once.
    assert await extraction_snapshots.previous_reading("doc-1") is None


async def test_a_run_that_already_stored_new_text_is_stopped_without_overwriting_it(store):
    """The restore is refused by its own filter (the run wrote text, or it is
    a different run); the stop then goes the ordinary way."""
    store.rows["doc-1"] = {"revision": 5, "fields": dict(GOOD)}
    documents = _documents(None)
    documents.update_one = AsyncMock(side_effect=[MagicMock(matched_count=0), MagicMock(matched_count=1)])
    outcome, _ = await _stop(documents, _doc())

    assert outcome == "stopped"
    _, update = documents.update_one.call_args_list[1][0]
    assert "raw_text" not in update["$set"]
    assert update["$set"]["task_status"] == "error"
    assert update["$set"]["error_message"] == document_service.EXTRACTION_STOPPED_MESSAGE


async def test_a_first_read_with_nothing_to_restore_is_stopped_as_before(store):
    documents = _documents(None)
    outcome, _ = await _stop(documents, _doc())
    assert outcome == "stopped"
    documents.update_one.assert_awaited_once()


async def test_nothing_in_flight_returns_none(store):
    documents = _documents(None)
    documents.update_one = AsyncMock(return_value=MagicMock(matched_count=0))
    outcome, revoke = await _stop(documents, _doc())
    assert outcome is None
    revoke.assert_not_called()


def test_a_stopped_document_is_told_apart_from_a_failed_one():
    stopped = SimpleNamespace(task_status="error", error_message=document_service.EXTRACTION_STOPPED_MESSAGE)
    failed = SimpleNamespace(task_status="error", error_message="OCR service returned no text")
    fine = SimpleNamespace(task_status="complete", error_message=None)
    assert document_service.extraction_stopped(stopped) is True
    assert document_service.extraction_stopped(failed) is False
    assert document_service.extraction_stopped(fine) is False
