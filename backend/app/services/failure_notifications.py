"""Emitters for "your thing broke" notifications.

The notification system historically carried only successful events (approvals,
verification decisions, catalog updates, team shares), so a failed workflow, a
document that never finished processing, or a recurring automation that has been
erroring for weeks produced no signal at all — the only way to find out was to
go looking.

These helpers are the failure half. They run in Celery workers, which hold a raw
pymongo handle rather than a Beanie session, so everything here is sync and
routes through `notification_service.create_notification_sync`.

Two rules the call sites depend on:

* **Never raise.** A notification is a side channel; a task that did real work
  must not fail (or retry) because the bell entry could not be written.
* **Only fire on the final attempt.** Most of these tasks carry
  `autoretry_for=TRANSIENT_EXCEPTIONS`, so a mid-retry emit would tell the user
  a run failed while it is in fact about to succeed. Use `is_final_attempt`.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.notification_service import create_notification_sync
from app.tasks import TRANSIENT_EXCEPTIONS

logger = logging.getLogger(__name__)

# Failure bodies quote the underlying error. Keep it short enough to read in the
# bell dropdown — the full text is always on the run/document record.
_ERROR_SNIPPET = 200


def is_final_attempt(task: Any, exc: BaseException) -> bool:
    """True when Celery will not retry `exc` for `task` again.

    A non-transient exception is never retried, so the first raise is also the
    last. A transient one is final only once the retry budget is spent.
    """
    if not isinstance(exc, TRANSIENT_EXCEPTIONS):
        return True
    try:
        retries = task.request.retries or 0
        max_retries = task.max_retries
    except AttributeError:
        return True
    if max_retries is None:
        return False
    return retries >= max_retries


def _snippet(error: Any) -> str:
    text = str(error or "").strip()
    if not text:
        return "No error detail was recorded."
    return text[:_ERROR_SNIPPET]


def notify_workflow_failed(
    db,
    *,
    workflow_doc: dict | None,
    error: Any,
    user_id: str | None = None,
    automation_name: str | None = None,
) -> None:
    """Notify the owner that a workflow run failed.

    `automation_name` distinguishes "the workflow you just ran failed" from "the
    automation that runs this workflow on a schedule failed", which is the case
    the user has no other way to notice.
    """
    try:
        workflow_doc = workflow_doc or {}
        recipient = user_id or workflow_doc.get("user_id")
        if not recipient:
            return

        workflow_id = str(workflow_doc.get("_id") or "")
        name = workflow_doc.get("name") or "Workflow"

        if automation_name:
            title = f"Automation failed: {automation_name}"
            group_title = f"Automation failed {{count}}×: {automation_name}"
            body = f'Workflow "{name}" did not complete. {_snippet(error)}'
        else:
            title = f"Workflow failed: {name}"
            group_title = f"Workflow failed {{count}}×: {name}"
            body = _snippet(error)

        create_notification_sync(
            db,
            user_id=recipient,
            kind="workflow_failed",
            title=title,
            body=body,
            link=f"/?workflow={workflow_id}" if workflow_id else "/",
            item_kind="workflow",
            item_id=workflow_id or None,
            item_name=name,
            coalesce_key=f"workflow_failed:{workflow_id or name}",
            group_title=group_title,
        )
    except Exception:
        logger.exception("Failed to emit workflow failure notification")


def notify_extraction_failed(
    db,
    *,
    user_id: str | None,
    search_set_uuid: str | None,
    error: Any,
    search_set_name: str | None = None,
) -> None:
    """Notify the owner that an extraction run failed."""
    try:
        if not user_id:
            return

        name = search_set_name
        if not name and search_set_uuid:
            ss = db.search_set.find_one({"uuid": search_set_uuid}, {"title": 1})
            name = (ss or {}).get("title")
        name = name or "Extraction"

        create_notification_sync(
            db,
            user_id=user_id,
            kind="extraction_failed",
            title=f"Extraction failed: {name}",
            body=_snippet(error),
            link=f"/?extraction={search_set_uuid}" if search_set_uuid else "/",
            item_kind="search_set",
            item_id=search_set_uuid,
            item_name=name,
            coalesce_key=f"extraction_failed:{search_set_uuid or name}",
            group_title=f"Extraction failed {{count}}×: {name}",
        )
    except Exception:
        logger.exception("Failed to emit extraction failure notification")


def notify_document_failed(db, *, doc: dict | None, error: Any) -> None:
    """Notify the owner that a document could not be processed.

    Coalesced per user rather than per document: a 50-file upload where a dozen
    files are corrupt should read as "12 documents failed to process", not bury
    the bell.
    """
    try:
        doc = doc or {}
        recipient = doc.get("user_id")
        if not recipient:
            return

        title = doc.get("title") or "Document"
        create_notification_sync(
            db,
            user_id=recipient,
            kind="document_failed",
            title=f"Document failed to process: {title}",
            body=_snippet(error),
            link="/?mode=files",
            item_kind="document",
            item_id=doc.get("uuid"),
            item_name=title,
            coalesce_key=f"document_failed:{recipient}",
            group_title="{count} documents failed to process",
        )
    except Exception:
        logger.exception("Failed to emit document failure notification")


def notify_delivery_failed(
    db,
    *,
    workflow_doc: dict | None = None,
    automation: dict | None = None,
    detail: str,
    error: Any = None,
    user_id: str | None = None,
) -> None:
    """Notify the owner that a run COMPLETED but a configured output did not
    deliver (library write, notification, webhook).

    Deliberately not notify_workflow_failed / notify_automation_failed: the
    run's results exist and are viewable — "failed" would be wrong twice over,
    and coalescing onto the genuine-failure key would overwrite an unread real
    failure's detail. But a run whose configured deliverable never left the
    building is not done either, and until now the only trace was a log line.

    Pass ``workflow_doc`` for a manual run, ``automation`` for an automation's
    outputs; ``error`` (optional) is appended via the module's shared snippet
    rule so bell bodies stay readable.
    """
    try:
        workflow_doc = workflow_doc or {}
        automation = automation or {}
        recipient = user_id or workflow_doc.get("user_id") or automation.get("user_id")
        if not recipient:
            return
        if automation:
            subject_id = str(automation.get("_id") or "")
            name = automation.get("name") or "Automation"
            link = (
                f"/?mode=automations&automation={subject_id}"
                if subject_id else "/?mode=automations"
            )
            item_kind = "automation"
        else:
            subject_id = str(workflow_doc.get("_id") or "")
            name = workflow_doc.get("name") or "Workflow"
            link = f"/?workflow={subject_id}" if subject_id else "/"
            item_kind = "workflow"
        body = f"{detail} {_snippet(error)}" if error else detail

        create_notification_sync(
            db,
            user_id=recipient,
            kind="delivery_failed",
            title=f"Output not delivered: {name}",
            body=body,
            link=link,
            item_kind=item_kind,
            item_id=subject_id or None,
            item_name=name,
            coalesce_key=f"delivery_failed:{subject_id or name}",
            group_title=f"Outputs not delivered {{count}}×: {name}",
        )
    except Exception:
        logger.exception("Failed to emit delivery-failure notification")


def notify_document_not_searchable(db, *, doc: dict | None, error: Any) -> None:
    """Notify the owner that a document was SAVED but search indexing failed.

    Deliberately not notify_document_failed: that title ("failed to process")
    and per-user coalesce key would merge this with genuine processing
    failures and contradict the body — the document exists and is readable,
    chat/knowledge search just cannot see it.
    """
    try:
        doc = doc or {}
        recipient = doc.get("user_id")
        if not recipient:
            return
        title_doc = doc.get("title") or doc.get("uuid") or "A document"

        create_notification_sync(
            db,
            user_id=recipient,
            kind="document_unsearchable",
            title="Document saved, but not searchable",
            body=(
                f"\u201c{title_doc}\u201d was saved, but search indexing failed — "
                f"chat and knowledge search will not see it. {_snippet(error)}"
            ),
            link="/?mode=files",
            item_kind="document",
            item_id=doc.get("uuid"),
            item_name=title_doc,
            coalesce_key=f"document_unsearchable:{recipient}",
            group_title="{count} documents saved but not searchable",
        )
    except Exception:
        logger.exception("Failed to emit document-unsearchable notification")


def notify_kb_source_failed(db, *, kb_uuid: str, source_name: str | None, error: Any) -> None:
    """Notify the KB owner that a source could not be ingested.

    Without this, a knowledge base with quietly errored sources answered
    questions while looking perfectly healthy — the only trace was a status
    field on a row nobody was told to look at.
    """
    try:
        kb = db.knowledge_bases.find_one({"uuid": kb_uuid}, {"title": 1, "user_id": 1}) or {}
        recipient = kb.get("user_id")
        if not recipient:
            return
        kb_title = kb.get("title") or "Knowledge base"
        name = source_name or "A source"

        create_notification_sync(
            db,
            user_id=recipient,
            kind="kb_source_failed",
            title=f"Knowledge base source failed: {kb_title}",
            body=f"\u201c{name}\u201d could not be ingested. {_snippet(error)}",
            # /?kb= would be force-routed into chat mode by the frontend's
            # kb-param handler; plain mode=knowledge lands on the knowledge
            # screen where the errored source row lives.
            link="/?mode=knowledge",
            item_kind="knowledge_base",
            item_id=kb_uuid,
            item_name=kb_title,
            coalesce_key=f"kb_source_failed:{kb_uuid}",
            group_title=f"{{count}} sources failed in knowledge base: {kb_title}",
        )
    except Exception:
        logger.exception("Failed to emit KB source failure notification")


def notify_project_kb_sync_failed(db, *, doc: dict | None, project: dict | None, error: Any) -> None:
    """Notify the owner that a document never reached its project's KB.

    The mirror into a project's implicit knowledge base is best-effort by
    design, but its failure means "chat with this project" silently cannot
    see a file the user just watched land in the project — worth a bell.
    """
    try:
        doc = doc or {}
        project = project or {}
        recipient = doc.get("user_id") or project.get("owner_user_id")
        if not recipient:
            return
        doc_title = doc.get("title") or doc.get("uuid") or "A document"
        project_title = project.get("title") or "your project"
        project_uuid = project.get("uuid") or ""

        create_notification_sync(
            db,
            user_id=recipient,
            kind="project_kb_sync_failed",
            title=f"Document not searchable in project: {project_title}",
            body=(
                f"\u201c{doc_title}\u201d was saved, but could not be added to the "
                "project's knowledge base \u2014 chatting with this project will not "
                f"see it. {_snippet(error)}"
            ),
            link=f"/?project={project_uuid}" if project_uuid else "/",
            item_kind="project",
            item_id=project_uuid or None,
            item_name=project_title,
            coalesce_key=f"project_kb_sync_failed:{project_uuid}",
            group_title=f"{{count}} documents not searchable in project: {project_title}",
        )
    except Exception:
        logger.exception("Failed to emit project KB sync failure notification")


def notify_automation_failed(
    db,
    *,
    automation: dict | None,
    error: Any,
    detail: str | None = None,
) -> None:
    """Notify the owner that an automation could not be dispatched or run.

    This is the scheduler-side failure — the automation never got as far as a
    workflow run, so `notify_workflow_failed` would never fire for it.
    """
    try:
        automation = automation or {}
        recipient = automation.get("user_id")
        if not recipient:
            return

        automation_id = str(automation.get("_id") or "")
        name = automation.get("name") or "Automation"
        body = f"{detail} {_snippet(error)}" if detail else _snippet(error)

        create_notification_sync(
            db,
            user_id=recipient,
            kind="automation_failed",
            title=f"Automation failed: {name}",
            body=body,
            link=(
                f"/?mode=automations&automation={automation_id}"
                if automation_id else "/?mode=automations"
            ),
            item_kind="automation",
            item_id=automation_id or None,
            item_name=name,
            coalesce_key=f"automation_failed:{automation_id or name}",
            group_title=f"Automation failed {{count}}×: {name}",
        )
    except Exception:
        logger.exception("Failed to emit automation failure notification")
