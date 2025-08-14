#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

# # on macOS celery has some issues with pandoc and the default pool; use solo pool to fix it
# # celery -A app.celery_worker.celery_app worker --pool=solo --loglevel INFO
# celery -A app.celery_worker.celery_app worker -l info -P threads --concurrency=8
# # nohup celery -A app.celery_worker:celery_app worker --loglevel INFO > celery.log 2>&1 &

CELERY_APP="app.celery_worker.celery_app"
LOG_LEVEL="info"
FLOWER_PORT=5555

# Queue configuration: "queue_name:num_workers:concurrency:pool_type"
# Format: QUEUE_NAME:NUMBER_OF_WORKERS:CONCURRENCY_PER_WORKER:POOL_TYPE
# Pool type is optional (defaults to 'threads')
QUEUE_CONFIG=(
  "uploads:2:2:threads"      # 2 workers for uploads, 2 threads each
  "documents:3:2:threads"    # 3 workers for documents, 2 threads each
  "workflows:2:3:threads"    # 2 workers for workflows, 3 threads each
  "default:1:4:threads"      # 1 worker for default, 4 threads
)

# Use absolute paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
PID_DIR="$SCRIPT_DIR/pids"

# Colors for output (using printf-compatible format)
if [[ -t 1 ]]; then
  RED=$'\033[0;31m'
  GREEN=$'\033[0;32m'
  YELLOW=$'\033[1;33m'
  BLUE=$'\033[0;34m'
  NC=$'\033[0m' # No Color
else
  RED=''
  GREEN=''
  YELLOW=''
  BLUE=''
  NC=''
fi

# Find PIDs by regex pattern, works even if pgrep/procps isn't installed
find_pids() {
  local pattern=$1

  if command -v pgrep >/dev/null 2>&1; then
    pgrep -f -- "$pattern" || true
    return
  fi

  # Fallback: try ps -eo (procps); else ps aux (busybox)
  if ps -eo pid,command >/dev/null 2>&1; then
    ps -eo pid,command | awk -v pat="$pattern" '
      BEGIN{ IGNORECASE=1 }
      $0 ~ pat { print $1 }
    ' || true
  else
    ps aux | awk -v pat="$pattern" '
      BEGIN{ IGNORECASE=1 }
      NR>1 && $0 ~ pat { print $2 }
    ' || true
  fi
}

# Create directories
mkdir -p "$LOG_DIR" "$PID_DIR"

# Function to print colored output
print_color() {
  printf "%b%s%b\n" "$1" "$2" "$NC"
}

# Function to get queue info
get_queue_info() {
  local queue_name=$1
  local info_type=$2  # workers, concurrency, or pool

  for config in "${QUEUE_CONFIG[@]}"; do
    IFS=':' read -r queue workers concurrency pool <<<"$config"
    if [[ "$queue" == "$queue_name" ]]; then
      case "$info_type" in
        workers)     echo "${workers:-1}" ;;
        concurrency) echo "${concurrency:-2}" ;;
        pool)        echo "${pool:-threads}" ;;
      esac
      return
    fi
  done

  # Default values if queue not found
  case "$info_type" in
    workers)     echo "1" ;;
    concurrency) echo "2" ;;
    pool)        echo "threads" ;;
  esac
}

# Function to get all queue names
get_all_queues() {
  for config in "${QUEUE_CONFIG[@]}"; do
    IFS=':' read -r queue _ _ _ <<<"$config"
    echo "$queue"
  done
}

# Function to start workers for a specific queue
start_queue_workers() {
  local queue_name=$1
  local num_workers
  local concurrency
  local pool_type

  num_workers=$(get_queue_info "$queue_name" "workers")
  concurrency=$(get_queue_info "$queue_name" "concurrency")
  pool_type=$(get_queue_info "$queue_name" "pool")

  print_color "$BLUE" "Starting $num_workers worker(s) for queue '$queue_name' (pool: $pool_type, concurrency: $concurrency)"

  for ((i=1; i<=num_workers; i++)); do
    local worker_name="worker_${queue_name}_${i}"
    local pid_file="$PID_DIR/${worker_name}.pid"
    local log_file="$LOG_DIR/${worker_name}.log"

    # Start the worker in the background
    nohup celery -A "$CELERY_APP" worker \
      --hostname="${worker_name}@%h" \
      --queues="$queue_name" \
      --loglevel="$LOG_LEVEL" \
      --pool="$pool_type" \
      --concurrency="$concurrency" \
      >"$log_file" 2>&1 &

    # Save the PID
    local worker_pid=$!
    echo "$worker_pid" >"$pid_file"

    # Give it a moment to start
    sleep 0.5

    # Check if it's running
    if ps -p "$worker_pid" >/dev/null 2>&1; then
      printf "  %b✓%b Worker #%d started (PID: %d)\n" "$GREEN" "$NC" "$i" "$worker_pid"
    else
      printf "  %b✗%b Failed to start worker #%d\n" "$RED" "$NC" "$i"
      rm -f "$pid_file"
    fi
  done
}

# Function to stop workers for a specific queue
stop_queue_workers() {
  local queue_name=$1
  local num_workers
  local any_stopped=false

  num_workers=$(get_queue_info "$queue_name" "workers")

  for ((i=1; i<=num_workers; i++)); do
    local worker_name="worker_${queue_name}_${i}"
    local pid_file="$PID_DIR/${worker_name}.pid"

    if [[ -f "$pid_file" ]]; then
      local pid
      pid=$(cat "$pid_file")
      if ps -p "$pid" >/dev/null 2>&1; then
        printf "  Stopping %s (PID: %d)\n" "$worker_name" "$pid"
        kill -TERM "$pid"
        any_stopped=true

        # Wait for graceful shutdown
        local count=0
        while ps -p "$pid" >/dev/null 2>&1 && [[ $count -lt 5 ]]; do
          sleep 0.5
          count=$((count + 1))
        done

        # Force kill if still running
        if ps -p "$pid" >/dev/null 2>&1; then
          printf "    Force killing %s\n" "$worker_name"
          kill -KILL "$pid"
        fi
      fi
      rm -f "$pid_file"
    fi
  done

  if [[ "$any_stopped" == true ]]; then
    printf "  %b✓%b Queue '%s' workers stopped\n" "$GREEN" "$NC" "$queue_name"
  fi
}

# Function to stop all workers
stop_all_workers() {
  print_color "$YELLOW" "Stopping all workers..."

  # Stop workers for each configured queue
  while IFS= read -r queue; do
    stop_queue_workers "$queue"
  done < <(get_all_queues)

  # Clean up any remaining celery processes
  local remaining
  remaining=$(find_pids "celery.*worker")
  if [[ -n "${remaining}" ]]; then
    echo "Stopping remaining celery processes: $remaining"
    # shellcheck disable=SC2086
    echo $remaining | xargs kill -TERM 2>/dev/null || true
    sleep 2
    remaining=$(find_pids "celery.*worker")
    if [[ -n "${remaining}" ]]; then
      # shellcheck disable=SC2086
      echo $remaining | xargs kill -KILL 2>/dev/null || true
    fi
  fi
}

# Function to stop flower
stop_flower() {
  print_color "$YELLOW" "Stopping Flower..."

  if [[ -f "$PID_DIR/flower.pid" ]]; then
    local pid
    pid=$(cat "$PID_DIR/flower.pid")
    if ps -p "$pid" >/dev/null 2>&1; then
      kill -TERM "$pid"
      sleep 2
      if ps -p "$pid" >/dev/null 2>&1; then
        kill -KILL "$pid"
      fi
      printf "  %b✓%b Flower stopped\n" "$GREEN" "$NC"
    fi
    rm -f "$PID_DIR/flower.pid"
  fi

  # Clean up any remaining flower processes
  local flower_pids
  flower_pids=$(find_pids "celery.*flower")
  if [[ -n "${flower_pids}" ]]; then
    # shellcheck disable=SC2086
    echo $flower_pids | xargs kill -TERM 2>/dev/null || true
    sleep 1
    flower_pids=$(find_pids "celery.*flower")
    if [[ -n "${flower_pids}" ]]; then
      # shellcheck disable=SC2086
      echo $flower_pids | xargs kill -KILL 2>/dev/null || true
    fi
  fi
}

# Function to start flower
start_flower() {
  print_color "$YELLOW" "Starting Flower monitoring..."

  nohup celery -A "$CELERY_APP" flower \
    --port="$FLOWER_PORT" \
    --address=0.0.0.0 \
    --loglevel=INFO \
    >"$LOG_DIR/flower.log" 2>&1 &

  local flower_pid=$!
  echo "$flower_pid" >"$PID_DIR/flower.pid"

  sleep 2

  if ps -p "$flower_pid" >/dev/null 2>&1; then
    printf "%b✓%b Flower started on http://0.0.0.0:%d (PID: %d)\n" "$GREEN" "$NC" "$FLOWER_PORT" "$flower_pid"
    return 0
  else
    printf "%b✗%b Failed to start Flower\n" "$RED" "$NC"
    rm -f "$PID_DIR/flower.pid"
    return 1
  fi
}

# Function to check status
check_status() {
  printf "\n"
  print_color "$YELLOW" "=== Queue Configuration ==="
  for config in "${QUEUE_CONFIG[@]}"; do
    IFS=':' read -r queue workers concurrency pool <<<"$config"
    pool=${pool:-threads}
    printf "%b%s%b: %d worker(s), %d threads each, %s pool\n" "$BLUE" "$queue" "$NC" "$workers" "$concurrency" "$pool"
  done

  printf "\n"
  print_color "$YELLOW" "=== Worker Status ==="
  local total_expected=0
  local total_running=0

  while IFS= read -r queue; do
    local num_workers
    num_workers=$(get_queue_info "$queue" "workers")
    local queue_running=0

    printf "%b%s%b (expecting %d worker(s)):\n" "$BLUE" "$queue" "$NC" "$num_workers"

    for ((i=1; i<=num_workers; i++)); do
      local worker_name="worker_${queue}_${i}"
      local pid_file="$PID_DIR/${worker_name}.pid"
      total_expected=$((total_expected + 1))

      if [[ -f "$pid_file" ]]; then
        local pid
        pid=$(cat "$pid_file")
        if ps -p "$pid" >/dev/null 2>&1; then
          printf "  %b✓%b Worker #%d is running (PID: %d)\n" "$GREEN" "$NC" "$i" "$pid"
          queue_running=$((queue_running + 1))
          total_running=$((total_running + 1))
        else
          printf "  %b✗%b Worker #%d pid file exists but process not running\n" "$RED" "$NC" "$i"
        fi
      else
        printf "  %b✗%b Worker #%d is not running\n" "$RED" "$NC" "$i"
      fi
    done

    printf "  Summary: %d/%d workers running\n" "$queue_running" "$num_workers"
  done < <(get_all_queues)

  printf "\n"
  print_color "$YELLOW" "=== Overall Summary ==="
  printf "Total workers running: %d/%d\n" "$total_running" "$total_expected"

  printf "\n"
  print_color "$YELLOW" "=== Flower Status ==="
  if [[ -f "$PID_DIR/flower.pid" ]]; then
    local pid
    pid=$(cat "$PID_DIR/flower.pid")
    if ps -p "$pid" >/dev/null 2>&1; then
      printf "%b✓%b Flower is running (PID: %d)\n" "$GREEN" "$NC" "$pid"
      printf "   Web UI: http://localhost:%d\n" "$FLOWER_PORT"
    else
      printf "%b✗%b Flower pid file exists but process not running\n" "$RED" "$NC"
    fi
  else
    printf "%b✗%b Flower is not running\n" "$RED" "$NC"
  fi

  printf "\n"
  print_color "$YELLOW" "=== Log Files ==="
  if ls "$LOG_DIR"/*.log >/dev/null 2>&1; then
    # shellcheck disable=SC2012
    ls -lh "$LOG_DIR"/*.log | tail -10
  else
    echo "No log files found"
  fi

  printf "\n"
  print_color "$YELLOW" "=== PID Files ==="
  if ls "$PID_DIR"/*.pid >/dev/null 2>&1; then
    # shellcheck disable=SC2012
    ls -lh "$PID_DIR"/*.pid | tail -10
  else
    echo "No pid files found"
  fi
}

# Function to show configuration
show_config() {
  print_color "$YELLOW" "=== Current Configuration ==="
  echo "CELERY_APP: $CELERY_APP"
  echo "LOG_LEVEL: $LOG_LEVEL"
  echo "FLOWER_PORT: $FLOWER_PORT"
  echo ""
  print_color "$YELLOW" "Queue Configuration:"
  for config in "${QUEUE_CONFIG[@]}"; do
    IFS=':' read -r queue workers concurrency pool <<<"$config"
    pool=${pool:-threads}
    printf "  - %s: %d worker(s), %d concurrency, %s pool\n" "$queue" "$workers" "$concurrency" "$pool"
  done
  echo ""
  echo "LOG_DIR: $LOG_DIR"
  echo "PID_DIR: $PID_DIR"
}

# Main execution
case "${1:-start}" in
  start)
    # Stop any existing processes
    stop_all_workers
    stop_flower

    printf "\n"
    print_color "$YELLOW" "Starting Celery workers..."

    # Start workers for each configured queue
    while IFS= read -r queue; do
      start_queue_workers "$queue"
      sleep 0.5  # Small delay between queues
    done < <(get_all_queues)

    # Start Flower
    echo ""
    start_flower

    # Show status
    check_status

    printf "\n"
    print_color "$GREEN" "=== All services started ==="
    echo "To view logs: tail -f \"$LOG_DIR\"/*.log"
    echo "To check status: \"$0\" status"
    ;;
  stop)
    stop_all_workers
    stop_flower
    print_color "$GREEN" "All services stopped"
    ;;
  restart)
    "$0" stop
    sleep 2
    "$0" start
    ;;
  status)
    check_status

    printf "\n"
    print_color "$YELLOW" "=== Running Celery Processes ==="
    ps aux | grep "[c]elery" | grep -v grep || echo "No celery processes found"
    ;;
  config)
    show_config
    ;;
  logs)
    if [[ -z "${2:-}" ]]; then
      echo "Following all logs (Ctrl+C to stop)..."
      tail -f "$LOG_DIR"/*.log
    else
      # Check if it's a specific worker name (contains an underscore) or a queue
      if [[ "$2" == *"_"* ]]; then
        # Specific worker format: queue_number
        log_file="$LOG_DIR/worker_$2.log"
        if [[ -f "$log_file" ]]; then
          echo "Following $2 logs (Ctrl+C to stop)..."
          tail -f "$log_file"
        else
          printf "%bLog file not found: %s%b\n" "$RED" "$log_file" "$NC"
          echo "Available logs:"
          ls -1 "$LOG_DIR"/*.log 2>/dev/null | xargs -n1 basename | sed 's/\.log$//'
        fi
      else
        # Queue name - show all workers for that queue
        echo "Showing logs for all workers in queue: $2"
        tail -f "$LOG_DIR"/worker_"${2}"_*.log 2>/dev/null || {
          printf "%bNo logs found for queue: %s%b\n" "$RED" "$2" "$NC"
        }
      fi
    fi
    ;;
  help|--help|-h)
    echo "Usage: $0 {start|stop|restart|status|config|logs [queue_name|worker_name]}"
    echo ""
    echo "Commands:"
    echo "  start    - Start all workers and Flower"
    echo "  stop     - Stop all workers and Flower"
    echo "  restart  - Restart all services"
    echo "  status   - Show status of all services"
    echo "  config   - Show current configuration"
    echo "  logs     - Tail logs (all, by queue, or specific worker)"
    echo ""
    echo "Log examples:"
    echo "  $0 logs              # All logs"
    echo "  $0 logs uploads      # All upload workers"
    echo "  $0 logs uploads_1    # Specific worker"
    echo ""
    echo "Current configuration:"
    for config in "${QUEUE_CONFIG[@]}"; do
      IFS=':' read -r queue workers _ _ <<<"$config"
      printf "  - %s: %d worker(s)\n" "$queue" "$workers"
    done
    exit 0
    ;;
  *)
    echo "Unknown command: ${1}. Try '$0 help'."
    exit 1
    ;;
esac
