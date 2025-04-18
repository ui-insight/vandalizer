#!/usr/bin/env sh

#celery -A app.celery_worker.celery_app worker --loglevel INFO
nohup celery -A app.celery_worker.celery_app worker --loglevel INFO > celery.log 2>&1 &
