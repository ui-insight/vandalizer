from celery import Celery
from celery.schedules import crontab

from app.config import Settings

settings = Settings()

celery = Celery(
    "vandalizer",
    broker=f"redis://{settings.redis_host}:6379/0",
    backend=f"redis://{settings.redis_host}:6379/1",
)

celery.conf.task_soft_time_limit = 1800
celery.conf.task_time_limit = 1860
celery.conf.result_expires = 86400
celery.conf.task_default_queue = "default"
celery.conf.task_routes = {
    "tasks.document.*": {"queue": "documents"},
    "tasks.documents.*": {"queue": "documents"},
    "tasks.workflow.*": {"queue": "workflows"},
    "tasks.workflow_next.*": {"queue": "workflows"},
    "tasks.upload.*": {"queue": "uploads"},
    "tasks.extraction.*": {"queue": "workflows"},
    "tasks.evaluation.*": {"queue": "workflows"},
    "tasks.passive.*": {"queue": "passive"},
    "tasks.activity.*": {"queue": "default"},
    "tasks.demo.*": {"queue": "default"},
    "tasks.retention.*": {"queue": "default"},
}

celery.conf.beat_schedule = {
    "demo-process-waitlist": {
        "task": "tasks.demo.process_waitlist",
        "schedule": crontab(minute="*/5"),
    },
    "demo-check-expirations": {
        "task": "tasks.demo.check_expirations",
        "schedule": crontab(minute=0),  # every hour
    },
    "demo-send-expiry-warnings": {
        "task": "tasks.demo.send_expiry_warnings",
        "schedule": crontab(hour=9, minute=0),  # daily at 9am
    },
    # Passive workflow triggers
    "passive-process-pending-triggers": {
        "task": "tasks.passive.process_pending_triggers",
        "schedule": 60.0,  # every 60 seconds
    },
    "passive-renew-graph-subscriptions": {
        "task": "tasks.passive.renew_graph_subscriptions",
        "schedule": 43200.0,  # every 12 hours
    },
    "passive-send-daily-digest": {
        "task": "tasks.passive.send_daily_digest",
        "schedule": crontab(hour=8, minute=0),  # daily at 8am
    },
    "passive-cleanup-old-trigger-events": {
        "task": "tasks.passive.cleanup_old_trigger_events",
        "schedule": crontab(hour=3, minute=0),  # daily at 3am
    },
    "quality-monitor-daily": {
        "task": "tasks.passive.quality_monitor",
        "schedule": 86400.0,
    },
    # Data retention tasks
    "retention-schedule-deletions": {
        "task": "tasks.retention.schedule_deletions",
        "schedule": crontab(hour=2, minute=0),  # daily at 2am
    },
    "retention-execute-soft-deletes": {
        "task": "tasks.retention.execute_soft_deletes",
        "schedule": crontab(hour=3, minute=0),  # daily at 3am
    },
    "retention-execute-hard-deletes": {
        "task": "tasks.retention.execute_hard_deletes",
        "schedule": crontab(hour=4, minute=0),  # daily at 4am
    },
    "retention-cleanup-ancillary": {
        "task": "tasks.retention.cleanup_ancillary",
        "schedule": crontab(hour=5, minute=0),  # daily at 5am
    },
}

# Alias for import convenience
celery_app = celery
