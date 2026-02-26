#!/bin/bash
# Celery worker management for vandalizer-next.
#
# Usage:
#   ./run_celery.sh start    — Start all workers, beat, and flower
#   ./run_celery.sh stop     — Stop all workers
#   ./run_celery.sh status   — Check status
#   ./run_celery.sh logs     — Tail all logs
#   ./run_celery.sh logs <queue>  — Tail logs for a specific queue

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LOG_DIR="$SCRIPT_DIR/logs/celery"
PID_DIR="$SCRIPT_DIR/pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

CELERY_APP="celery_worker.celery_app"

start_worker() {
    local name="$1"
    local queues="$2"
    local concurrency="$3"

    echo "Starting worker: $name (queues=$queues, concurrency=$concurrency)"
    celery -A "$CELERY_APP" worker \
        --queues="$queues" \
        --concurrency="$concurrency" \
        --hostname="$name@%h" \
        --loglevel=info \
        --logfile="$LOG_DIR/$name.log" \
        --pidfile="$PID_DIR/$name.pid" \
        --detach
}

case "${1:-help}" in
    start)
        echo "Starting Celery workers for vandalizer-next..."

        start_worker "documents" "documents" 3
        start_worker "workflows" "workflows" 2
        start_worker "uploads"   "uploads"   2
        start_worker "passive"   "passive"   1
        start_worker "default"   "default"   1

        echo "Starting Celery Beat..."
        celery -A "$CELERY_APP" beat \
            --loglevel=info \
            --logfile="$LOG_DIR/beat.log" \
            --pidfile="$PID_DIR/beat.pid" \
            --detach

        echo "Starting Flower..."
        celery -A "$CELERY_APP" flower \
            --port=5555 \
            --persistent=True \
            --db="$LOG_DIR/flower.db" \
            --logfile="$LOG_DIR/flower.log" \
            --detach 2>/dev/null || echo "Flower not installed or failed to start"

        echo "All workers started. Use '$0 status' to check."
        ;;

    stop)
        echo "Stopping all Celery workers..."
        for pidfile in "$PID_DIR"/*.pid; do
            [ -f "$pidfile" ] || continue
            pid=$(cat "$pidfile")
            name=$(basename "$pidfile" .pid)
            if kill -0 "$pid" 2>/dev/null; then
                echo "  Stopping $name (PID $pid)..."
                kill "$pid"
            else
                echo "  $name already stopped"
            fi
            rm -f "$pidfile"
        done
        echo "Done."
        ;;

    status)
        echo "Celery worker status:"
        for pidfile in "$PID_DIR"/*.pid; do
            [ -f "$pidfile" ] || continue
            pid=$(cat "$pidfile")
            name=$(basename "$pidfile" .pid)
            if kill -0 "$pid" 2>/dev/null; then
                echo "  ✓ $name (PID $pid) running"
            else
                echo "  ✗ $name (PID $pid) not running"
                rm -f "$pidfile"
            fi
        done
        [ ! "$(ls -A "$PID_DIR" 2>/dev/null)" ] && echo "  No workers running"
        ;;

    logs)
        queue="${2:-}"
        if [ -n "$queue" ]; then
            tail -f "$LOG_DIR/$queue.log"
        else
            tail -f "$LOG_DIR"/*.log
        fi
        ;;

    *)
        echo "Usage: $0 {start|stop|status|logs [queue]}"
        exit 1
        ;;
esac
