"""Folder Watch → Run Extraction leaves a run in Run history (support ticket).

A new PDF in a watched folder used to run the extraction inline with no
record: Run history showed only Run now runs, the bell said nothing, and the
results were saved where nothing in the app reads them.

    INTEGRATION_MONGODB=1 uv run pytest tests/integration/test_folder_watch_extraction_history_mongodb.py
"""

import os
from unittest.mock import patch

import pytest

from app.models.automation import Automation
from app.models.notification import Notification
from app.services import automation_history
from app.services.extraction_engine import ExtractionEngine

pytestmark = [
    pytest.mark.skipif(not os.environ.get("INTEGRATION_MONGODB"), reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests"),
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture
def sync_db(sync_mongo):
    with patch("app.tasks.get_sync_db", return_value=sync_mongo), \
         patch("app.tasks.document_tasks.get_sync_db", return_value=sync_mongo), \
         patch("app.tasks.passive_tasks.get_sync_db", return_value=sync_mongo):
        yield sync_mongo


async def _setup(sync_db):
    auto = Automation(
        name="Certification Lab watch", user_id="owner", trigger_type="folder_watch",
        trigger_config={"folder_id": "cert-lab", "file_types": ["pdf"]},
        action_type="extraction", action_id="ss-subaward", enabled=True,
    )
    await auto.insert()
    sync_db.search_set.insert_one({"uuid": "ss-subaward", "title": "Subaward_extraction"})
    sync_db.search_set_item.insert_many([
        {"searchset": "ss-subaward", "searchtype": "extraction", "searchphrase": "Subaward number"},
        {"searchset": "ss-subaward", "searchtype": "extraction", "searchphrase": "Total amount"},
    ])
    sync_db.smart_document.insert_one({
        "uuid": "qa-pdf", "title": "QA_Citation_Test_5pages.pdf", "extension": "pdf", "folder": "cert-lab",
        "raw_text": "Subaward No. UI-2026-0412. Total amount $243,200.", "processing": False, "user_id": "owner",
    })
    return auto


async def test_a_new_file_shows_up_in_run_history_with_its_result(mongo_client, sync_db):
    from app.tasks.document_tasks import _check_folder_watch_automations
    from app.tasks.passive_tasks import process_extraction_outputs

    auto = await _setup(sync_db)
    queued = []
    with patch("app.celery_app.celery_app.send_task", side_effect=lambda name, **kw: queued.append((name, kw))):
        _check_folder_watch_automations(sync_db, "qa-pdf")

    # Queued, so Run history shows it right away.
    runs = (await automation_history.list_runs(str(auto.id), 20))["items"]
    assert [(r["action_type"], r["status"]) for r in runs] == [("extraction", "queued")]
    assert queued[0][0] == "tasks.passive.process_extraction_outputs"

    # The worker runs it (the model call is the only thing replaced).
    with patch.object(ExtractionEngine, "extract", return_value=[{"Subaward number": "UI-2026-0412", "Total amount": "$243,200"}]), \
         patch("app.services.search_set_service.effective_extraction_config", return_value={}):
        process_extraction_outputs.run(**queued[0][1]["kwargs"])

    runs = (await automation_history.list_runs(str(auto.id), 20))["items"]
    assert runs[0]["status"] == "completed" and runs[0]["completed_at"]
    assert runs[0]["trigger_type"] == "folder_watch" and runs[0]["document_title"] == "QA_Citation_Test_5pages.pdf"
    event = sync_db.extraction_trigger_event.find_one({"automation_id": str(auto.id)})
    assert event["result"] == [{"Subaward number": "UI-2026-0412", "Total amount": "$243,200", "document_id": "qa-pdf"}]

    bell = await Notification.find(Notification.user_id == "owner").to_list()
    assert [(n.kind, n.title) for n in bell] == [("automation_completed", "Automation finished: Certification Lab watch")]
    assert bell[0].body == "Ran on QA_Citation_Test_5pages.pdf. Open Run history to view the result."
    assert bell[0].link == f"/?mode=automations&automation={auto.id}"

    # A second file coalesces into the same unread entry instead of burying the bell.
    sync_db.smart_document.insert_one({"uuid": "qa-pdf-2", "title": "Second.pdf", "extension": "pdf", "folder": "cert-lab",
                                       "raw_text": "Subaward No. X.", "processing": False, "user_id": "owner"})
    queued.clear()
    with patch("app.celery_app.celery_app.send_task", side_effect=lambda name, **kw: queued.append((name, kw))):
        _check_folder_watch_automations(sync_db, "qa-pdf-2")
    with patch.object(ExtractionEngine, "extract", return_value=[{"Subaward number": "X"}]), \
         patch("app.services.search_set_service.effective_extraction_config", return_value={}):
        process_extraction_outputs.run(**queued[0][1]["kwargs"])
    bell = await Notification.find(Notification.user_id == "owner").to_list()
    assert len(bell) == 1 and bell[0].occurrences == 2 and bell[0].title == "Automation finished 2×: Certification Lab watch"
    assert len((await automation_history.list_runs(str(auto.id), 20))["items"]) == 2


async def test_run_now_needs_no_bell_and_a_failure_still_bells(mongo_client, sync_db):
    from bson import ObjectId

    from app.tasks.passive_tasks import process_extraction_outputs

    auto = await _setup(sync_db)
    manual = sync_db.extraction_trigger_event.insert_one({
        "automation_id": str(auto.id), "search_set_uuid": "ss-subaward", "user_id": "owner", "status": "queued",
        "document_uuids": ["qa-pdf"], "trigger_context": {"trigger_type": "manual"},
    }).inserted_id
    with patch.object(ExtractionEngine, "extract", return_value=[{"Subaward number": "UI-2026-0412"}]), \
         patch("app.services.search_set_service.effective_extraction_config", return_value={}):
        process_extraction_outputs.run(automation_id=str(auto.id), search_set_uuid="ss-subaward",
                                       document_uuids=["qa-pdf"], user_id="owner", extraction_event_id=str(manual))
    assert await Notification.find(Notification.user_id == "owner").count() == 0

    failed = sync_db.extraction_trigger_event.insert_one({
        "automation_id": str(auto.id), "search_set_uuid": "ss-subaward", "user_id": "owner", "status": "queued",
        "document_uuids": ["qa-pdf"], "trigger_context": {"trigger_type": "folder_watch"},
    }).inserted_id
    with patch.object(ExtractionEngine, "extract", side_effect=RuntimeError("model unavailable")), \
         patch("app.services.search_set_service.effective_extraction_config", return_value={}):
        process_extraction_outputs.run(automation_id=str(auto.id), search_set_uuid="ss-subaward",
                                       document_uuids=["qa-pdf"], user_id="owner", extraction_event_id=str(failed))
    assert sync_db.extraction_trigger_event.find_one({"_id": ObjectId(failed)})["status"] == "failed"
    kinds = [n.kind for n in await Notification.find(Notification.user_id == "owner").to_list()]
    assert kinds == ["automation_failed"], "a failed run bells the failure, not a completion"
