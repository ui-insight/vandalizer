#!/usr/bin/env sh

celery -A app.celery.celery_app worker --loglevel INFO
