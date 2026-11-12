"""Celery task that reads a project's award facts (app.services.award_snapshot)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS

if TYPE_CHECKING:
    from celery import Task


@celery_app.task(
    bind=True,
    name="tasks.extraction.build_award_snapshot",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
)
def build_award_snapshot(self: Task, project_uuid: str, build_token: str) -> str:
    """Read the award's key facts and budget from the project's documents."""
    from app.services.award_snapshot import build_sync

    return build_sync(project_uuid, build_token)
