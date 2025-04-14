#!/usr/bin/env sh

celery -A app.celery_worker.celery_app worker --loglevel INFO
