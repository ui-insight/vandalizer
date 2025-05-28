#!/usr/bin/env sh

# on macos celery has some issues pandoc on macos with the default pool, use solo pool to fix it
# celery -A app.celery_worker.celery_app worker --pool=solo --loglevel INFO
celery -A app.celery_worker.celery_app worker -l info -P threads --concurrency=8


# nohup celery -A app.celery_worker:celery_app worker --loglevel INFO > celery.log 2>&1 &
