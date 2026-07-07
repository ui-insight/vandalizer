"""Celery tasks for project operations.

Currently just background project duplication: the router creates the new
project's shell synchronously (so it appears in the list immediately) and
enqueues ``tasks.project.duplicate`` to deep-copy the folder subtree, files,
and knowledge-base ingestion, which can take a while for large projects.
"""

import logging

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS, run_task_async

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.project.duplicate",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def duplicate_project_task(
    self, source_project_uuid: str, new_project_uuid: str, user_id: str
) -> dict:
    """Deep-copy a project's folders + files + KB ingestion in the background."""

    async def _run():
        from app.config import Settings
        from app.database import init_db
        from app.services import project_service

        await init_db(Settings())
        return await project_service.copy_project_contents(
            source_project_uuid, new_project_uuid, user_id
        )

    result = run_task_async(_run())
    logger.info(
        "Duplicated project %s -> %s: %s",
        source_project_uuid, new_project_uuid, result,
    )
    return result
