"""Correlate a requested check with its worker and its persisted result.

The receipt is inserted before publishing. A lost response or uncertain publish
must never republish the same request: recovery reads the original task instead.
"""
import datetime
import logging
from uuid import UUID, uuid4

from celery.result import AsyncResult
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from starlette.concurrency import run_in_threadpool

from app.celery_app import celery
from app.models.kb_validation_task import KBValidationTask
from app.models.validation_run import ValidationRun

logger = logging.getLogger(__name__)


def task_reference(receipt, *, resumed=False):
    return {"task_id": receipt.uuid, "status": "queued", "options": receipt.options, "resumed": resumed}


async def active_validation(kb_uuid: str, user_id: str):
    receipt = await KBValidationTask.find_one({"kb_uuid": kb_uuid, "user_id": user_id, "active": True})
    if receipt is None:
        recent = await KBValidationTask.find({"kb_uuid": kb_uuid, "user_id": user_id}).sort("-created_at").limit(1).to_list()
        receipt = recent[0] if recent else None
    if receipt is None:
        return {"task": None}
    outcome = await validation_status(kb_uuid, user_id, receipt.uuid)
    return {"task": {**outcome, "options": receipt.options}}


async def finish_receipt(receipt, status):
    if receipt.active or receipt.terminal_status != status:
        await receipt.set({"active": False, "terminal_status": status})


async def existing_validation(kb_uuid: str, user_id: str, options: dict, request_id: str | None):
    if not request_id:
        return None
    try:
        task_id = str(UUID(request_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, "request_id must be a UUID")
    prior = await KBValidationTask.find_one({"uuid": task_id})
    if prior is None:
        return None
    if (prior.kb_uuid, prior.user_id, prior.options) != (kb_uuid, user_id, options):
        raise HTTPException(409, "This request ID cannot be reused for another check")
    return task_reference(prior)


async def start_validation(kb_uuid: str, user_id: str, options: dict, request_id: str | None):
    try:
        task_id = str(UUID(request_id)) if request_id else str(uuid4())
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, "request_id must be a UUID")
    receipt = KBValidationTask(uuid=task_id, kb_uuid=kb_uuid, user_id=user_id, options=options)
    try:
        await receipt.insert()
    except DuplicateKeyError:
        prior = await KBValidationTask.find_one({"uuid": task_id})
        if prior:
            if (prior.kb_uuid, prior.user_id, prior.options) != (kb_uuid, user_id, options):
                raise HTTPException(409, "This request ID cannot be reused for another check")
            return task_reference(prior)
        # Another window may have inserted a different request first. Resume
        # that active check rather than publishing a second paid operation.
        active = await KBValidationTask.find_one({"kb_uuid": kb_uuid, "user_id": user_id, "active": True})
        if active:
            return task_reference(active, resumed=True)
        raise HTTPException(409, "Check state changed. Reconnect before starting another check.")
    from app.tasks.kb_validation_tasks import validate_kb_task
    try:
        # No publish retry: if acknowledgement is lost, status recovery decides
        # what happened. Re-publishing could execute the same paid check twice.
        await run_in_threadpool(
            validate_kb_task.apply_async,
            args=[kb_uuid, user_id, options["mode"], options["skip_judge"], options["query_uuids"]],
            task_id=task_id, retry=False,
        )
    except Exception:
        logger.exception("Validation dispatch acknowledgement lost for %s", task_id)
        receipt.dispatch_uncertain = True
        await receipt.save()
    return task_reference(receipt)


async def validation_status(kb_uuid: str, user_id: str, task_id: str):
    receipt = await KBValidationTask.find_one({"uuid": task_id, "kb_uuid": kb_uuid, "user_id": user_id})
    if receipt is None:
        raise HTTPException(404, "Validation task not found")
    # Persisted results outlive Celery's one-day result expiry. Never infer
    # completion from another user's or another concurrent check's history.
    saved = await ValidationRun.find_one({
        "item_kind": "knowledge_base", "item_id": kb_uuid, "user_id": user_id,
        "result_snapshot.validation_task_id": task_id,
    })
    if saved is not None:
        await finish_receipt(receipt, "completed")
        return {"task_id": task_id, "status": "completed", "run_uuid": saved.uuid,
                "result": {**saved.result_snapshot, "score": saved.score, "score_breakdown": saved.score_breakdown}}
    if receipt.terminal_status == "failed":
        return {"task_id": task_id, "status": "failed", "message": "This check could not finish. Review your questions and sources, then start a new check."}
    state = await run_in_threadpool(lambda: AsyncResult(task_id, app=celery).state)
    created = receipt.created_at.replace(tzinfo=datetime.timezone.utc) if receipt.created_at.tzinfo is None else receipt.created_at
    age = (datetime.datetime.now(datetime.timezone.utc) - created).total_seconds()
    if state in ("FAILURE", "REVOKED"):
        await finish_receipt(receipt, "failed")
        # Do not expose worker exception strings (provider credentials/context).
        status, message = "failed", "This check could not finish. Review your questions and sources, then start a new check."
    elif state == "STARTED":
        status, message = "running", "Checking answers…"
    elif state == "RETRY":
        status, message = "retrying", "The worker is retrying a temporary error. No new check is needed."
    elif state == "SUCCESS" or receipt.dispatch_uncertain or age > 86400:
        status, message = "unknown", "The check's status could not be confirmed. Check status again or review History before starting another check."
    else:
        status, message = "queued", "Waiting for a validation worker…"
    return {"task_id": task_id, "status": status, "message": message, "delayed": age >= 600}
