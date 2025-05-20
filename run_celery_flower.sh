#!/usr/bin/env sh

celery -A app.celery_worker.celery_app \
    flower \
    --port=5555 \
    --address=0.0.0.0 \
    --loglevel=INFO
