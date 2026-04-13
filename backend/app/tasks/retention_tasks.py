"""Celery beat tasks for data retention policy enforcement."""

import asyncio
import datetime
import logging

from app.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="tasks.retention.schedule_deletions", bind=True)
def schedule_deletions_task(self):
    """Find documents past retention period and schedule them for deletion."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_schedule_deletions())
    finally:
        loop.close()


async def _schedule_deletions():
    from app.database import init_db
    from app.config import Settings

    settings = Settings()
    await init_db(settings)

    from app.models.document import SmartDocument
    from app.models.system_config import SystemConfig

    config = await SystemConfig.get_config()
    retention_config = config.get_retention_config()

    if not retention_config.get("enabled"):
        return

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    policies = retention_config.get("policies", {})
    scheduled_count = 0

    for classification, policy in policies.items():
        retention_days = policy.get("retention_days")
        if not retention_days:
            continue

        cutoff = now - datetime.timedelta(days=retention_days)

        docs = await SmartDocument.find(
            SmartDocument.classification == classification,
            SmartDocument.created_at <= cutoff,
            SmartDocument.soft_deleted != True,  # noqa: E712
            SmartDocument.retention_hold != True,  # noqa: E712
            SmartDocument.scheduled_deletion_at == None,  # noqa: E711
        ).to_list()

        for doc in docs:
            doc.scheduled_deletion_at = now + datetime.timedelta(days=7)
            await doc.save()
            scheduled_count += 1

    logger.info("Scheduled %d documents for deletion", scheduled_count)


@celery.task(name="tasks.retention.execute_soft_deletes", bind=True)
def execute_soft_deletes_task(self):
    """Soft-delete documents past their scheduled deletion date."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_execute_soft_deletes())
    finally:
        loop.close()


async def _execute_soft_deletes():
    from app.database import init_db
    from app.config import Settings

    settings = Settings()
    await init_db(settings)

    from app.models.document import SmartDocument

    now = datetime.datetime.now(tz=datetime.timezone.utc)

    docs = await SmartDocument.find(
        SmartDocument.scheduled_deletion_at <= now,
        SmartDocument.soft_deleted != True,  # noqa: E712
        SmartDocument.retention_hold != True,  # noqa: E712
    ).to_list()

    for doc in docs:
        doc.soft_deleted = True
        doc.soft_deleted_at = now
        await doc.save()

    if docs:
        logger.info("Soft-deleted %d documents", len(docs))


@celery.task(name="tasks.retention.execute_hard_deletes", bind=True)
def execute_hard_deletes_task(self):
    """Permanently delete documents after grace period."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_execute_hard_deletes())
    finally:
        loop.close()


async def _execute_hard_deletes():
    import os

    from app.database import init_db
    from app.config import Settings

    settings = Settings()
    await init_db(settings)

    from app.models.document import SmartDocument
    from app.models.system_config import SystemConfig

    config = await SystemConfig.get_config()
    retention_config = config.get_retention_config()

    if not retention_config.get("enabled"):
        return

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    policies = retention_config.get("policies", {})
    deleted_count = 0

    docs = await SmartDocument.find(
        SmartDocument.soft_deleted == True,  # noqa: E712
        SmartDocument.retention_hold != True,  # noqa: E712
    ).to_list()

    for doc in docs:
        classification = doc.classification or "unrestricted"
        policy = policies.get(classification, {})
        grace_days = policy.get("soft_delete_grace_days", 30)

        if not doc.soft_deleted_at:
            continue

        grace_cutoff = doc.soft_deleted_at + datetime.timedelta(days=grace_days)
        if now < grace_cutoff:
            continue

        # Delete physical file
        if doc.path and os.path.exists(doc.path):
            try:
                os.remove(doc.path)
            except OSError:
                logger.warning("Failed to delete file %s", doc.path)

        # Delete from ChromaDB
        try:
            from app.services.document_manager import get_chroma_client
            chroma = get_chroma_client(settings.chromadb_persist_dir)
            collection = chroma.get_or_create_collection("documents")
            collection.delete(where={"document_uuid": doc.uuid})
        except Exception:
            logger.warning("Failed to delete ChromaDB entries for %s", doc.uuid)

        # Delete from MongoDB
        await doc.delete()
        deleted_count += 1

    if deleted_count:
        logger.info("Hard-deleted %d documents", deleted_count)


@celery.task(name="tasks.retention.cleanup_ancillary", bind=True)
def cleanup_ancillary_task(self):
    """Clean up old activity logs, chats, and workflow results."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_cleanup_ancillary())
    finally:
        loop.close()


async def _cleanup_ancillary():
    from app.database import init_db
    from app.config import Settings

    settings = Settings()
    await init_db(settings)

    from app.models.system_config import SystemConfig
    from app.models.activity import ActivityEvent
    from app.models.chat import ChatConversation
    from app.models.workflow import WorkflowResult

    config = await SystemConfig.get_config()
    retention_config = config.get_retention_config()

    if not retention_config.get("enabled"):
        return

    now = datetime.datetime.now(tz=datetime.timezone.utc)

    # Clean up old activity events
    activity_days = retention_config.get("activity_retention_days", 180)
    activity_cutoff = now - datetime.timedelta(days=activity_days)
    activity_result = await ActivityEvent.find(
        ActivityEvent.created_at <= activity_cutoff,
    ).delete()
    if activity_result and activity_result.deleted_count:
        logger.info("Deleted %d old activity events", activity_result.deleted_count)

    # Clean up old chat conversations
    chat_days = retention_config.get("chat_retention_days", 365)
    chat_cutoff = now - datetime.timedelta(days=chat_days)
    chat_result = await ChatConversation.find(
        ChatConversation.created_at <= chat_cutoff,
    ).delete()
    if chat_result and chat_result.deleted_count:
        logger.info("Deleted %d old chat conversations", chat_result.deleted_count)

    # Clean up old workflow results
    wf_days = retention_config.get("workflow_result_retention_days", 365)
    wf_cutoff = now - datetime.timedelta(days=wf_days)
    wf_result = await WorkflowResult.find(
        WorkflowResult.start_time <= wf_cutoff,
    ).delete()
    if wf_result and wf_result.deleted_count:
        logger.info("Deleted %d old workflow results", wf_result.deleted_count)
