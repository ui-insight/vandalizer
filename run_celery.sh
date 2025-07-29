#!/usr/bin/env sh

# # on macos celery has some issues pandoc on macos with the default pool, use solo pool to fix it
# # celery -A app.celery_worker.celery_app worker --pool=solo --loglevel INFO
# celery -A app.celery_worker.celery_app worker -l info -P threads --concurrency=8


# # nohup celery -A app.celery_worker:celery_app worker --loglevel INFO > celery.log 2>&1 &

#!/usr/bin/env sh

# kill_and_start_workers_with_flower.sh

#!/usr/bin/env sh

# run_celery.sh - Fixed version

CELERY_APP="app.celery_worker.celery_app"
LOG_LEVEL="info"
WORKER_COUNT=10
CONCURRENCY=4
FLOWER_PORT=5555

# Create local directories for logs and pids
mkdir -p logs pids

# Function to stop flower
stop_flower() {
    echo "Stopping existing Flower instances..."
    FLOWER_PIDS=$(ps aux | grep "[f]lower" | grep -v grep | awk '{print $2}')

    if [ -n "$FLOWER_PIDS" ]; then
        echo "Found Flower with PIDs: $FLOWER_PIDS"
        echo $FLOWER_PIDS | xargs kill -TERM
        sleep 3

        # Force kill if still running
        REMAINING=$(ps aux | grep "[f]lower" | grep -v grep | awk '{print $2}')
        if [ -n "$REMAINING" ]; then
            echo $REMAINING | xargs kill -KILL
        fi
    fi

    rm -f pids/flower.pid
}

# Function to start flower
start_flower() {
    echo "Starting Flower monitoring..."
    nohup celery -A $CELERY_APP \
        flower \
        --port=$FLOWER_PORT \
        --address=0.0.0.0 \
        --loglevel=INFO \
        --pidfile=pids/flower.pid \
        > logs/flower.log 2>&1 &

    sleep 2
    echo "Flower started on http://0.0.0.0:$FLOWER_PORT"
}

# Stop any existing workers gracefully
echo "Stopping existing workers..."
celery -A $CELERY_APP multi stopwait 1-$WORKER_COUNT \
    --pidfile=pids/celery_%n.pid \
    --logfile=logs/celery_%n%I.log

# Stop flower
stop_flower

# Clean up any stale pid files
rm -f pids/celery_worker*.pid logs/celery_worker*.log

# Start new workers with LOCAL log and pid directories
echo "Starting new workers..."
celery -A $CELERY_APP multi restart $WORKER_COUNT \
    --pidfile=pids/celery_%n.pid \
    --logfile=logs/celery_%n%I.log \
    --loglevel=$LOG_LEVEL \
    --pool=threads \
    --concurrency=$CONCURRENCY \
    -Q:1-2 uploads \
    -Q:3-5 documents \
    -Q:6-9 workflows \
    -Q default


# Start flower
start_flower

echo "Workers and Flower started successfully!"

# Show worker status
celery -A $CELERY_APP multi show \
    -Q:1-2 uploads \
    -Q:3-5 documents \
    -Q:6-9 workflows \
    -Q default \
    --pidfile=pids/celery_%n.pid --logfile=logs/celery_%n%I.log

echo "=== Services Running ==="
echo "Flower Web UI: http://localhost:$FLOWER_PORT"
echo "Worker logs: ./logs/"
echo "PID files: ./pids/"
