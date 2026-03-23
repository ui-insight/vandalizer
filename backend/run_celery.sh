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

    # Clean stale PID files from previous container runs
    rm -f "$PID_DIR/$name.pid"

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

        # Clean all stale PID files (handles container restarts)
        rm -f "$PID_DIR"/*.pid

        start_worker "documents" "documents" 8
        start_worker "workflows" "workflows" 6
        start_worker "uploads"   "uploads"   4
        start_worker "passive"   "passive"   2
        start_worker "default"   "default"   2

        echo "Starting Celery Beat..."
        rm -f "$PID_DIR/beat.pid"
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

        echo "All workers started."

        # In Docker, keep the script alive so the container doesn't exit.
        # Detached workers run as child processes — wait for any to exit.
        if [ -f /.dockerenv ] || [ -f /proc/1/cgroup ] 2>/dev/null; then
            echo "Running in container — staying alive to keep container running."
            # Wait forever, monitoring worker health
            while true; do
                sleep 30
                # Check if at least one worker is still running
                alive=false
                for pidfile in "$PID_DIR"/*.pid; do
                    [ -f "$pidfile" ] || continue
                    pid=$(cat "$pidfile")
                    if kill -0 "$pid" 2>/dev/null; then
                        alive=true
                        break
                    fi
                done
                if [ "$alive" = false ]; then
                    echo "All workers have exited — restarting."
                    exec "$0" start
                fi
            done
        fi
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
