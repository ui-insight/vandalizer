"""Tell people when a long run they started has finished (#994).

v5 belled a failed workflow or extraction (``failure_notifications``) but not
a finished one, so an RA who started a run over a folder of award documents
and moved on had no way to know it was done short of checking back. This is
the success half, under the same rules:

* Only runs that took at least ``MIN_SECONDS``: a run that finished while
  someone was still watching it needs no bell.
* Only runs a person started. Automation runs are skipped; each automation
  has its own delivery settings, and a folder watch finishing every few
  minutes would bury the bell.
* One notification per run. Runs in one batch collect into one entry
  ("Workflow finished 12×: …") through the bell's coalescing.
* Never raises: a run that completed must not fail because the bell entry
  could not be written.
"""

import datetime
import logging
from typing import Any

from app.services.notification_service import create_notification_sync

logger = logging.getLogger(__name__)

MIN_SECONDS = 30


def _elapsed_seconds(started_at: Any) -> float | None:
    if not isinstance(started_at, datetime.datetime):
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=datetime.timezone.utc)
    return (datetime.datetime.now(datetime.timezone.utc) - started_at).total_seconds()


def _long_enough(started_at: Any) -> bool:
    elapsed = _elapsed_seconds(started_at)
    return elapsed is not None and elapsed >= MIN_SECONDS


def notify_workflow_completed(
    db,
    *,
    user_id: str | None,
    workflow_doc: dict | None,
    result_doc: dict | None,
) -> None:
    """Bell the person who started a workflow run that has just completed."""
    try:
        result_doc = result_doc or {}
        workflow_doc = workflow_doc or {}
        if not user_id or user_id == "system":
            return
        if result_doc.get("status") != "completed":
            return
        if result_doc.get("is_passive") or result_doc.get("automation_id"):
            return
        if not _long_enough(result_doc.get("start_time")):
            return
        workflow_id = str(workflow_doc.get("_id") or result_doc.get("workflow") or "")
        result_id = str(result_doc.get("_id") or "")
        name = workflow_doc.get("name") or "Workflow"
        document = result_doc.get("document_title")
        batch_id = result_doc.get("batch_id")
        create_notification_sync(
            db,
            user_id=user_id,
            kind="workflow_completed",
            title=f"Workflow finished: {name}",
            body=f"Results are ready for {document}." if document else "Results are ready.",
            link=f"/?workflow={workflow_id}" if workflow_id else "/",
            item_kind="workflow",
            item_id=workflow_id or None,
            item_name=name,
            coalesce_key=f"workflow_completed:{batch_id or result_id or workflow_id}",
            group_title=f"Workflow finished {{count}}×: {name}",
        )
    except Exception:
        logger.exception("Failed to emit workflow completion notification")


def notify_extraction_completed(
    db,
    *,
    user_id: str | None,
    activity: dict | None,
    search_set_uuid: str | None,
    document_count: int,
) -> None:
    """Bell the person who started an extraction run that has just completed."""
    try:
        activity = activity or {}
        if not user_id or user_id == "system":
            return
        if activity.get("status") == "completed":
            return  # a retry of a run that already finished and belled
        if not _long_enough(activity.get("started_at")):
            return
        name = None
        if search_set_uuid:
            ss = db.search_set.find_one({"uuid": search_set_uuid}, {"title": 1})
            name = (ss or {}).get("title")
        name = name or "Extraction"
        docs = f"{document_count} document{'s' if document_count != 1 else ''}"
        create_notification_sync(
            db,
            user_id=user_id,
            kind="extraction_completed",
            title=f"Extraction finished: {name}",
            body=f"Values extracted from {docs} are ready.",
            link=f"/?extraction={search_set_uuid}" if search_set_uuid else "/",
            item_kind="search_set",
            item_id=search_set_uuid,
            item_name=name,
            coalesce_key=f"extraction_completed:{activity.get('_id') or search_set_uuid}",
            group_title=f"Extraction finished {{count}}×: {name}",
        )
    except Exception:
        logger.exception("Failed to emit extraction completion notification")
