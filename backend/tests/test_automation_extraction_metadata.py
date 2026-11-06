"""Folder-watch extraction automations (#1057, and the run-history ticket).

#1057: the folder-watch path built field metadata as a dict keyed by field
name; the engine reads a list of ``{"key": ...}`` entries. The run-history
ticket: that path ran inline and recorded nothing — no run, no bell, results
saved where nothing reads them. It now queues the same run Run now does, so
the metadata check moves to the shared task.
"""

from unittest.mock import MagicMock, patch

from bson import ObjectId

from app.services.extraction_engine import ExtractionEngine
from app.tasks.document_tasks import _run_automation_extraction


def test_a_new_file_queues_a_recorded_run_like_run_now():
    db = MagicMock()
    db.extraction_trigger_event.insert_one.return_value.inserted_id = ObjectId()
    auto = {"_id": ObjectId(), "name": "watch", "user_id": "owner", "trigger_type": "folder_watch"}
    with patch("app.celery_app.celery_app.send_task") as send:
        _run_automation_extraction(db, auto, "ss-1", {"_id": "d1", "uuid": "d1", "title": "QA_Citation_Test_5pages.pdf"})

    event = db.extraction_trigger_event.insert_one.call_args.args[0]
    assert event["automation_id"] == str(auto["_id"]) and event["status"] == "queued"
    assert event["document_uuids"] == ["d1"] and event["user_id"] == "owner"
    assert event["trigger_context"] == {"trigger_type": "folder_watch", "document_title": "QA_Citation_Test_5pages.pdf"}
    assert send.call_args.args[0] == "tasks.passive.process_extraction_outputs"
    assert send.call_args.kwargs["kwargs"]["extraction_event_id"] == str(db.extraction_trigger_event.insert_one.return_value.inserted_id)
    # Nothing is extracted inline any more.
    db.smart_document.update_one.assert_not_called()


def test_metadata_reaches_the_engine_as_a_list_with_descriptions():
    from app.tasks.passive_tasks import process_extraction_outputs

    items = [
        {"searchphrase": "Status", "enum_values": ["Open", "Closed"], "is_optional": True},
        {"searchphrase": "Total Direct Costs", "description": "Also labelled Direct-cost total."},
    ]
    captured = {}

    def fake_extract(self, **kwargs):
        captured.update(kwargs)
        {m["key"]: m for m in kwargs["field_metadata"]}  # the engine's own first step
        return [{"Status": "Open"}]

    db = MagicMock()
    db.automation.find_one.return_value = {"_id": ObjectId(), "name": "watch", "user_id": "owner"}
    db.search_set_item.find.return_value = items
    db.search_set.find_one.return_value = {"uuid": "ss-1"}
    db.smart_document.count_documents.return_value = 0
    db.smart_document.find_one.return_value = {"uuid": "d1", "raw_text": "text"}
    db.extraction_trigger_event.find_one.return_value = {"trigger_context": {"trigger_type": "folder_watch"}}
    with (
        patch("app.tasks.passive_tasks.get_sync_db", return_value=db),
        patch.object(ExtractionEngine, "__init__", lambda self, **kw: None),
        patch.object(ExtractionEngine, "extract", fake_extract),
        patch("app.services.search_set_service.effective_extraction_config", return_value={}),
        patch("app.services.run_notifications.create_notification_sync"),
    ):
        process_extraction_outputs.run(
            automation_id=str(ObjectId()), search_set_uuid="ss-1", document_uuids=["d1"],
            user_id="owner", extraction_event_id=str(ObjectId()),
        )

    assert captured["field_metadata"] == [
        {"key": "Status", "is_optional": True, "enum_values": ["Open", "Closed"], "description": None},
        {"key": "Total Direct Costs", "is_optional": False, "enum_values": [], "description": "Also labelled Direct-cost total."},
    ]
