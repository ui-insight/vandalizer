from celery import Celery
from celery.schedules import crontab

from app.config import Settings

settings = Settings()

celery = Celery(
    "vandalizer",
    broker=f"redis://{settings.redis_host}:6379/0",
    backend=f"redis://{settings.redis_host}:6379/1",
)

celery.conf.timezone = settings.celery_timezone
celery.conf.task_soft_time_limit = 3600
celery.conf.task_time_limit = 3660
# Required by acks_late on the workflow tasks: the Redis transport redelivers
# any message left unacked past this window, and its DEFAULT (3600s) is
# SHORTER than the hard time limit above — a 61-minute run would be handed to
# a second worker while the first was still executing it, and prefetched
# messages waiting behind long runs age against the same clock. 12 hours makes
# a live-duplicate delivery practically impossible; recovery from a silently
# dead worker does not wait on it (the stale-run reaper fails the run within
# ~2h, and the eventual redelivery hits the terminal-status guard and no-ops).
celery.conf.broker_transport_options = {"visibility_timeout": 43200}
celery.conf.result_expires = 86400
celery.conf.task_default_queue = "default"
celery.conf.task_routes = {
    "tasks.document.*": {"queue": "documents"},
    "tasks.documents.*": {"queue": "documents"},
    "tasks.workflow.*": {"queue": "workflows"},
    "tasks.workflow_next.*": {"queue": "workflows"},
    "tasks.upload.*": {"queue": "uploads"},
    "tasks.extraction.*": {"queue": "workflows"},
    "tasks.kb.*": {"queue": "workflows"},
    "tasks.passive.*": {"queue": "passive"},
    "tasks.activity.*": {"queue": "default"},
    "tasks.demo.*": {"queue": "default"},
    "tasks.retention.*": {"queue": "default"},
    "tasks.approvals.*": {"queue": "default"},
    "tasks.project.*": {"queue": "documents"},
}

celery.conf.beat_schedule = {
    # Trial token lifecycle: running-low warnings, then exhaustion. Hourly is
    # for the *emails* only — the spend gate itself is enforced live at the
    # metering chokepoint, so nothing overspends between sweeps.
    "demo-sweep-budgets": {
        "task": "tasks.demo.sweep_budgets",
        "schedule": crontab(minute=0),  # every hour
    },
    "demo-recapture-drips": {
        "task": "tasks.demo.process_recapture",
        "schedule": crontab(hour=11, minute=0),  # daily at 11am
    },
    # Passive workflow triggers
    "passive-process-pending-triggers": {
        "task": "tasks.passive.process_pending_triggers",
        "schedule": 60.0,  # every 60 seconds
    },
    "passive-process-scheduled-automations": {
        "task": "tasks.passive.process_scheduled_automations",
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
    # Approval timeouts
    "approvals-expire-overdue": {
        "task": "tasks.approvals.expire_overdue",
        "schedule": 300.0,  # every 5 minutes
    },
    # Reap activity rail items stuck in running/queued (dead workers, dropped streams)
    "activity-reap-stale-running": {
        "task": "tasks.activity.reap_stale_running",
        "schedule": 120.0,  # every 2 minutes
    },
    # Reap WorkflowResult rows a dead worker left at "running"/"pending_approval".
    # Named tasks.activity.* so it routes to the default queue — on the
    # workflows queue, the worker outage it detects would also silence it.
    "activity-reap-stale-workflow-runs": {
        "task": "tasks.activity.reap_stale_workflow_runs",
        "schedule": 600.0,  # every 10 minutes; its strictest threshold is ~2h
    },
    # Self-heal documents whose task_status got stranded in an in-progress stage
    "document-reap-stuck": {
        "task": "tasks.document.reap_stuck",
        "schedule": 300.0,  # every 5 minutes
    },
    # User engagement
    "engagement-onboarding-drips": {
        "task": "tasks.engagement.process_onboarding_drips",
        "schedule": crontab(hour=10, minute=0),  # daily at 10am
    },
    "engagement-inactivity-nudges": {
        "task": "tasks.engagement.process_inactivity_nudges",
        "schedule": crontab(hour=10, minute=30),  # daily at 10:30am
    },
    # Orphan-run reaper for all three optimizer run types (KB, workflow,
    # extraction) — a hard-limit-killed run otherwise blocks re-optimizing
    # its subject forever via the start paths' active-run 409.
    "optimization-janitor": {
        "task": "tasks.passive.optimization_janitor",
        "schedule": crontab(minute=0),  # hourly
    },
    # Monthly re-judge of KBs with an applied optimization config — catches
    # quiet regressions after Apply (KB content drifts, retrieval pipeline
    # shifts). Emits a QualityAlert when the current blended score has fallen
    # >10pts vs the originally applied run's optimized_score.
    "kb-revalidate-applied-monthly": {
        "task": "tasks.passive.kb_revalidate_applied",
        "schedule": crontab(day_of_month=1, hour=2, minute=0),  # 1st of month, 2am
    },
}

if not settings.enable_trial_system:
    for _key in ("demo-sweep-budgets",):
        celery.conf.beat_schedule.pop(_key, None)

# Anonymous deployment heartbeat — always scheduled; the task resolves the
# effective opt-in decision (SystemConfig DB + env default) at run time and
# no-ops when telemetry is disabled. Always-scheduling is what lets the in-app
# opt-in banner enable telemetry without a worker restart.
celery.conf.beat_schedule["telemetry-daily-heartbeat"] = {
    "task": "tasks.telemetry.send_heartbeat",
    "schedule": crontab(hour=7, minute=23),  # daily, off-peak, non-round minute
}

# Alias for import convenience
celery_app = celery
