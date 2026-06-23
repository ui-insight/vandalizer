#!/usr/bin/env python3
"""Standalone Celery worker entry point for vandalizer-next.

This replaces the Flask-based celery_worker.py. All task modules are imported
here so that their @celery_app.task decorators register with the Celery app.

Usage:
    celery -A celery_worker.celery_app worker --queues=documents,workflows,uploads,passive,default --loglevel=info
    celery -A celery_worker.celery_app beat --loglevel=info
"""

from app.celery_app import celery_app  # noqa: F401
from app.config import Settings
from app.observability import init_sentry

# Import all task modules so their @celery_app.task decorators register.

from app.tasks import document_tasks  # noqa: F401  — tasks.document.*
from app.tasks import upload_tasks  # noqa: F401  — dispatch helper (no tasks, but imports matter)
from app.tasks import upload_validation_tasks  # noqa: F401  — tasks.upload.*
from app.tasks import extraction_tasks  # noqa: F401  — tasks.extraction.*
from app.tasks import knowledge_base_tasks  # noqa: F401  — tasks.documents.*
from app.tasks import activity_tasks  # noqa: F401  — tasks.activity.*
from app.tasks import workflow_tasks  # noqa: F401  — tasks.workflow_next.*
from app.tasks import workflow_optimization_tasks  # noqa: F401  — tasks.workflow.optimize
from app.tasks import quality_tasks  # noqa: F401  — tasks.workflow_next.quality_*
from app.tasks import kb_validation_tasks  # noqa: F401  — tasks.kb.*
from app.tasks import m365_tasks  # noqa: F401  — tasks.passive.ingest_*, triage, renew, digest
from app.tasks import passive_tasks  # noqa: F401  — tasks.passive.process_*, execute_*, cleanup
from app.tasks import classification_tasks  # noqa: F401  — tasks.document.classify
from app.tasks import demo_tasks  # noqa: F401  — tasks.demo.*
from app.tasks import approval_tasks  # noqa: F401  — tasks.approvals.*
from app.tasks import catalog_tasks  # noqa: F401  — tasks.catalog.upgrade
from app.tasks import engagement_tasks  # noqa: F401  — tasks.engagement.*
from app.tasks import retention_tasks  # noqa: F401  — tasks.retention.*

# Initialize Sentry in the worker process. Celery workers never import
# app.main, so without this call task crashes are never reported. Task imports
# above only register tasks (no execution), so init order relative to them is
# irrelevant for runtime crash capture.
init_sentry(Settings(), with_celery=True)
