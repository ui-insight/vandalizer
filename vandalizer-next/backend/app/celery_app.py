from celery import Celery

from app.config import Settings

settings = Settings()

celery = Celery(
    "vandalizer",
    broker=f"redis://{settings.redis_host}:6379/0",
    backend=f"redis://{settings.redis_host}:6379/1",
)

celery.conf.task_default_queue = "default"
celery.conf.task_routes = {
    "tasks.document.*": {"queue": "documents"},
    "tasks.documents.*": {"queue": "documents"},
    "tasks.workflow.*": {"queue": "workflows"},
    "tasks.workflow_next.*": {"queue": "workflows"},
    "tasks.upload.*": {"queue": "uploads"},
    "tasks.evaluation.*": {"queue": "workflows"},
    "tasks.passive.*": {"queue": "passive"},
}

# Alias for import convenience
celery_app = celery
