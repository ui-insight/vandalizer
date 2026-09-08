#!/usr/bin/env bash
# ============================================================================
#  Vandalizer — Deployment Status Check
#  Run from the project root: ./status.sh
# ============================================================================

set -uo pipefail

# ---------------------------------------------------------------------------
# Colors & symbols
# ---------------------------------------------------------------------------
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'
GREEN='\033[38;5;114m'
RED='\033[38;5;203m'
YELLOW='\033[38;5;221m'
BLUE='\033[38;5;111m'
CYAN='\033[38;5;117m'
MAGENTA='\033[38;5;183m'
GRAY='\033[38;5;245m'

PASS="${GREEN}●${RESET}"
FAIL="${RED}●${RESET}"
WARN="${YELLOW}●${RESET}"
SKIP="${GRAY}○${RESET}"

# Counters
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNED=0
RECOMMENDATIONS=()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
header() {
  echo ""
  echo -e "  ${BOLD}${BLUE}$1${RESET}"
  echo -e "  ${DIM}$(printf '%.0s─' $(seq 1 ${#1}))${RESET}"
}

pass() {
  echo -e "  ${PASS}  $1"
  CHECKS_PASSED=$((CHECKS_PASSED + 1))
}

fail() {
  echo -e "  ${FAIL}  $1"
  CHECKS_FAILED=$((CHECKS_FAILED + 1))
  if [[ -n "${2:-}" ]]; then
    RECOMMENDATIONS+=("$2")
  fi
}

warn() {
  echo -e "  ${WARN}  $1"
  CHECKS_WARNED=$((CHECKS_WARNED + 1))
  if [[ -n "${2:-}" ]]; then
    RECOMMENDATIONS+=("$2")
  fi
}

skip() {
  echo -e "  ${SKIP}  ${DIM}$1${RESET}"
}

detail() {
  echo -e "      ${DIM}$1${RESET}"
}

# ---------------------------------------------------------------------------
# Container-engine compatibility layer
#
# The compose frontend may be Docker Compose v2, docker-compose v1, or
# podman-compose. Their `ps --format` templates differ (podman-compose
# forwards to `podman ps`, which has no .Service/.Health fields), so all
# container introspection goes through the engine CLI instead, keyed on the
# com.docker.compose.* labels that every compose implementation attaches.
# ---------------------------------------------------------------------------
CONTAINER_CLI=""
COMPOSE_CMD=""
if command -v docker &>/dev/null; then
  CONTAINER_CLI="docker"
elif command -v podman &>/dev/null; then
  CONTAINER_CLI="podman"
fi
if [[ -n "$CONTAINER_CLI" ]]; then
  COMPOSE_CMD="docker compose"
  if ! $COMPOSE_CMD version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
    if ! $COMPOSE_CMD version &>/dev/null 2>&1; then
      COMPOSE_CMD="podman-compose"
      if ! $COMPOSE_CMD version &>/dev/null 2>&1; then
        COMPOSE_CMD=""
      fi
    fi
  fi
fi

# Compose project name: explicit override, else the lowercased directory
# name — the default every compose implementation derives.
compose_project() {
  if [[ -n "${COMPOSE_PROJECT_NAME:-}" ]]; then
    echo "$COMPOSE_PROJECT_NAME"
  else
    basename "$PWD" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]//g'
  fi
}

# Name of the container backing a compose service; empty if none exists.
compose_container() {
  [[ -n "$CONTAINER_CLI" ]] || return 0
  local c
  # Prefer a running container: `ps -a` lists exited and one-off `compose run`
  # containers too, newest first, and an exec against one of those fails with
  # a confusing error instead of "the API container is not running".
  for flag in "" "-a"; do
    c=$($CONTAINER_CLI ps $flag \
      --filter "label=com.docker.compose.project=$(compose_project)" \
      --filter "label=com.docker.compose.service=$1" \
      --format '{{.Names}}' 2>/dev/null | head -1)
    [[ -n "$c" ]] && break
  done
  echo "$c"
}

# State (running/exited/restarting/...) of a service's container; empty if
# the container doesn't exist.
compose_state() {
  local c
  c=$(compose_container "$1")
  [[ -n "$c" ]] || return 0
  $CONTAINER_CLI inspect --format '{{.State.Status}}' "$c" 2>/dev/null
}

# Health (healthy/unhealthy/starting) of a service's container; empty when
# the container doesn't exist or defines no healthcheck.
compose_health() {
  local c
  c=$(compose_container "$1")
  [[ -n "$c" ]] || return 0
  $CONTAINER_CLI inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$c" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo -e "  ${BOLD}${MAGENTA}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${BOLD}${MAGENTA}║${RESET}  ${BOLD}Vandalizer${RESET} ${DIM}Deployment Status${RESET}           ${BOLD}${MAGENTA}║${RESET}"
echo -e "  ${BOLD}${MAGENTA}╚══════════════════════════════════════════╝${RESET}"

# ---------------------------------------------------------------------------
# 1. Environment file
# ---------------------------------------------------------------------------
header "Environment"

ENV_FILE="backend/.env"
if [[ -f "$ENV_FILE" ]]; then
  pass "backend/.env exists"

  # Check required vars
  check_env_var() {
    local var_name=$1
    local label=$2
    local recommendation=$3
    local value
    value=$(grep -E "^${var_name}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
    if [[ -z "$value" ]]; then
      fail "${label} is not set" "$recommendation"
    elif [[ "$value" == "change-me-to-a-random-secret" ]]; then
      fail "${label} is still the default placeholder" "$recommendation"
    else
      pass "${label} is configured"
    fi
  }

  check_env_var "JWT_SECRET_KEY" "JWT_SECRET_KEY" \
    "Generate a secure JWT secret: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
  check_env_var "MONGO_HOST" "MONGO_HOST" \
    "Set MONGO_HOST in backend/.env (default: mongodb://localhost:27018/)"
  check_env_var "REDIS_HOST" "REDIS_HOST" \
    "Set REDIS_HOST in backend/.env (default: localhost)"

  # Optional but useful
  SMTP_HOST=$(grep -E "^SMTP_HOST=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
  if [[ -z "$SMTP_HOST" ]]; then
    warn "SMTP is not configured ${DIM}(email notifications disabled)${RESET}" \
      "Configure SMTP_HOST, SMTP_USER, SMTP_PASSWORD in backend/.env to enable email notifications"
  else
    pass "SMTP is configured"
  fi
else
  fail "backend/.env does not exist" \
    "Run: cp backend/.env.example backend/.env && edit backend/.env"
fi

# ---------------------------------------------------------------------------
# 2. Containers
# ---------------------------------------------------------------------------
header "Container Services"

if [[ -z "$CONTAINER_CLI" ]]; then
  fail "No container engine found" \
    "Install Docker (https://docs.docker.com/get-docker/) or Podman (https://podman.io/docs/installation)"
elif [[ -z "$COMPOSE_CMD" ]]; then
  fail "No Compose implementation found" \
    "Install Docker Compose (https://docs.docker.com/compose/install/) or podman-compose"
else
  check_container() {
    local service=$1
    local label=$2
    local port=${3:-}

    local container
    container=$(compose_container "$service")

    if [[ -z "$container" ]]; then
      fail "${label} is not running" \
        "Run: $COMPOSE_CMD up -d ${service}"
      return
    fi

    local state health
    state=$(compose_state "$service")
    health=$(compose_health "$service")

    if [[ "$state" != "running" ]]; then
      fail "${label} is ${state}" \
        "Run: $COMPOSE_CMD up -d ${service} — then check logs: $COMPOSE_CMD logs ${service}"
    elif [[ -n "$health" && "$health" != "healthy" && "$health" != "(healthy)" ]]; then
      warn "${label} is running but ${YELLOW}${health}${RESET}" \
        "Check ${service} health: $COMPOSE_CMD logs ${service}"
    else
      if [[ -n "$port" ]]; then
        pass "${label} is ${GREEN}healthy${RESET} ${DIM}(:${port})${RESET}"
      else
        pass "${label} is ${GREEN}healthy${RESET}"
      fi
    fi
  }

  check_container "redis"    "Redis"
  check_container "mongo"    "MongoDB"
  check_container "chromadb" "ChromaDB"
  check_container "api"      "API"
  check_container "celery"   "Celery"
  check_container "frontend" "Frontend"
fi

# ---------------------------------------------------------------------------
# 3. API health
# ---------------------------------------------------------------------------
header "API Health"

# Check API health via exec in the container (port may not be exposed to the host)
API_CONTAINER=$(compose_container api)
API_HEALTH_OK=false
if [[ -n "$API_CONTAINER" ]]; then
  HEALTH_JSON=$($CONTAINER_CLI exec "$API_CONTAINER" python -c \
    "import urllib.request; print(urllib.request.urlopen('http://localhost:8001/api/health').read().decode())" \
    2>/dev/null || true)
  if [[ -n "$HEALTH_JSON" ]]; then
    echo "$HEALTH_JSON" > /tmp/vandalizer_health.json
    API_HEALTH_OK=true
  fi
fi

if [[ "$API_HEALTH_OK" == true ]]; then
  API_STATUS=$(python3 -c "import json; d=json.load(open('/tmp/vandalizer_health.json')); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")

  if [[ "$API_STATUS" == "ok" ]]; then
    pass "Health endpoint returned ${GREEN}ok${RESET}"
  else
    warn "Health endpoint returned ${YELLOW}${API_STATUS}${RESET}" \
      "Run: $COMPOSE_CMD exec api python -c \"import urllib.request; print(urllib.request.urlopen('http://localhost:8001/api/health').read().decode())\" — to see details"
  fi

  # Parse individual checks
  for svc in mongodb redis chromadb; do
    svc_status=$(python3 -c "import json; d=json.load(open('/tmp/vandalizer_health.json')); print(d.get('checks',{}).get('${svc}','unknown'))" 2>/dev/null || echo "unknown")
    label=$(echo "$svc" | sed 's/mongodb/MongoDB/;s/redis/Redis/;s/chromadb/ChromaDB/')
    if [[ "$svc_status" == "ok" ]]; then
      pass "${label} connection ${GREEN}ok${RESET}"
    else
      fail "${label} connection failed" \
        "Check ${label} container logs: $COMPOSE_CMD logs ${svc}"
    fi
  done

  rm -f /tmp/vandalizer_health.json
else
  fail "API is not responding" \
    "Start the stack: $COMPOSE_CMD up -d — then: $COMPOSE_CMD logs api"
  skip "MongoDB connection (API unavailable)"
  skip "Redis connection (API unavailable)"
  skip "ChromaDB connection (API unavailable)"
fi

# ---------------------------------------------------------------------------
# 4. Frontend
# ---------------------------------------------------------------------------
header "Frontend"

# Read WEB_PORT from root .env (defaults to 80)
_WEB_PORT=80
if [[ -f ".env" ]]; then
  _wp=$(grep -E "^WEB_PORT=" .env 2>/dev/null | head -1 | cut -d'=' -f2-)
  [[ -n "$_wp" ]] && _WEB_PORT="$_wp"
fi

if curl -sf "http://localhost:${_WEB_PORT}/health" -o /dev/null 2>/dev/null; then
  if [[ "$_WEB_PORT" == "80" ]]; then
    pass "Frontend is serving at ${CYAN}http://localhost${RESET}"
  else
    pass "Frontend is serving at ${CYAN}http://localhost:${_WEB_PORT}${RESET}"
  fi
elif curl -sf "http://localhost:5173" -o /dev/null 2>/dev/null; then
  pass "Frontend dev server at ${CYAN}http://localhost:5173${RESET}"
else
  fail "Frontend is not responding" \
    "Production: $COMPOSE_CMD up -d frontend — Dev: cd frontend && npm run dev"
fi

# ---------------------------------------------------------------------------
# 5. Bootstrap status (queries MongoDB directly)
# ---------------------------------------------------------------------------
header "Bootstrap & Seed Data"

# Resolve the mongo container by its compose labels
MONGO_CONTAINER=$(compose_container mongo)

# Read MONGO_DB from .env (default: osp)
MONGO_DB="osp"
if [[ -f "$ENV_FILE" ]]; then
  ENV_MONGO_DB=$(grep -E "^MONGO_DB=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
  if [[ -n "$ENV_MONGO_DB" ]]; then
    MONGO_DB="$ENV_MONGO_DB"
  fi
fi

mongo_count() {
  # Run a countDocuments query against a collection via the mongo container
  local collection=$1
  local filter=${2:-'{}'}
  $CONTAINER_CLI exec "$MONGO_CONTAINER" mongosh --quiet --eval \
    "db.getSiblingDB('${MONGO_DB}').${collection}.countDocuments(${filter})" 2>/dev/null || echo "-1"
}

if [[ -z "$MONGO_CONTAINER" ]]; then
  skip "Bootstrap checks (MongoDB container not found)"
  skip "Seed data checks (MongoDB container not found)"
else
  # --- Admin user ---
  ADMIN_COUNT=$(mongo_count "user" '{"is_admin": true}')
  if [[ "$ADMIN_COUNT" == "-1" ]]; then
    skip "Admin user (could not query MongoDB)"
  elif [[ "$ADMIN_COUNT" -ge 1 ]]; then
    pass "Admin user exists ${DIM}(${ADMIN_COUNT} admin account(s))${RESET}"
  else
    fail "No admin user found" \
      "Run: $COMPOSE_CMD exec -e ADMIN_EMAIL=you@example.edu -e ADMIN_PASSWORD=secret api python bootstrap_install.py"
  fi

  # --- Default team ---
  CONFIG_COUNT=$(mongo_count "system_config" '{"default_team_id": {"$exists": true, "$ne": null}}')
  if [[ "$CONFIG_COUNT" == "-1" ]]; then
    skip "Default team (could not query MongoDB)"
  elif [[ "$CONFIG_COUNT" -ge 1 ]]; then
    pass "Default team is configured"
  else
    warn "No default team configured ${DIM}(new users get personal team only)${RESET}" \
      "Set DEFAULT_TEAM_NAME when running bootstrap_install.py to auto-assign new users to a shared team"
  fi

  # --- Verified catalog ---
  echo ""
  echo -e "  ${BOLD}${BLUE}Verified Catalog${RESET}"
  echo -e "  ${DIM}────────────────${RESET}"

  SEED_PROBLEM=false
  BOOTSTRAP_CMD="$COMPOSE_CMD exec api python bootstrap_install.py"

  # Verified workflows
  VWF_COUNT=$(mongo_count "workflow" '{"verified": true}')
  EXPECTED_WF=11
  if [[ "$VWF_COUNT" == "-1" ]]; then
    skip "Verified workflows (could not query MongoDB)"
  elif [[ "$VWF_COUNT" -ge "$EXPECTED_WF" ]]; then
    pass "Verified workflows: ${GREEN}${VWF_COUNT}${RESET} ${DIM}(expected ${EXPECTED_WF})${RESET}"
  elif [[ "$VWF_COUNT" -gt 0 ]]; then
    warn "Verified workflows: ${YELLOW}${VWF_COUNT}/${EXPECTED_WF}${RESET} ${DIM}(some missing)${RESET}"
    SEED_PROBLEM=true
  else
    fail "Verified workflows: ${RED}0${RESET}" ""
    SEED_PROBLEM=true
  fi

  # Verified search sets (extraction templates)
  VSS_COUNT=$(mongo_count "search_set" '{"verified": true}')
  EXPECTED_SS=4
  if [[ "$VSS_COUNT" == "-1" ]]; then
    skip "Extraction templates (could not query MongoDB)"
  elif [[ "$VSS_COUNT" -ge "$EXPECTED_SS" ]]; then
    pass "Extraction templates: ${GREEN}${VSS_COUNT}${RESET} ${DIM}(expected ${EXPECTED_SS})${RESET}"
  elif [[ "$VSS_COUNT" -gt 0 ]]; then
    warn "Extraction templates: ${YELLOW}${VSS_COUNT}/${EXPECTED_SS}${RESET} ${DIM}(some missing)${RESET}"
    SEED_PROBLEM=true
  else
    fail "Extraction templates: ${RED}0${RESET}" ""
    SEED_PROBLEM=true
  fi

  # Verified collections
  VCOL_COUNT=$(mongo_count "verified_collection")
  EXPECTED_COL=5
  if [[ "$VCOL_COUNT" == "-1" ]]; then
    skip "Collections (could not query MongoDB)"
  elif [[ "$VCOL_COUNT" -ge "$EXPECTED_COL" ]]; then
    pass "Collections: ${GREEN}${VCOL_COUNT}${RESET} ${DIM}(expected ${EXPECTED_COL})${RESET}"
  elif [[ "$VCOL_COUNT" -gt 0 ]]; then
    warn "Collections: ${YELLOW}${VCOL_COUNT}/${EXPECTED_COL}${RESET} ${DIM}(some missing)${RESET}"
    SEED_PROBLEM=true
  else
    fail "Collections: ${RED}0${RESET}" ""
    SEED_PROBLEM=true
  fi

  # Verified metadata entries
  VMETA_COUNT=$(mongo_count "verified_item_metadata")
  EXPECTED_META=$((EXPECTED_WF + EXPECTED_SS))
  if [[ "$VMETA_COUNT" == "-1" ]]; then
    skip "Catalog metadata (could not query MongoDB)"
  elif [[ "$VMETA_COUNT" -ge "$EXPECTED_META" ]]; then
    pass "Catalog metadata: ${GREEN}${VMETA_COUNT}${RESET} ${DIM}(expected ${EXPECTED_META})${RESET}"
  elif [[ "$VMETA_COUNT" -gt 0 ]]; then
    warn "Catalog metadata: ${YELLOW}${VMETA_COUNT}/${EXPECTED_META}${RESET} ${DIM}(some missing)${RESET}"
    SEED_PROBLEM=true
  else
    fail "Catalog metadata: ${RED}0${RESET}" ""
    SEED_PROBLEM=true
  fi

  # Verified library
  VLIB_COUNT=$(mongo_count "library" '{"scope": "verified"}')
  if [[ "$VLIB_COUNT" == "-1" ]]; then
    skip "Verified library (could not query MongoDB)"
  elif [[ "$VLIB_COUNT" -ge 1 ]]; then
    pass "Verified library exists"
  else
    fail "Verified library: ${RED}not created${RESET}" ""
    SEED_PROBLEM=true
  fi

  # One combined recommendation if anything is missing
  if [[ "$SEED_PROBLEM" == true ]]; then
    RECOMMENDATIONS+=("Seed the verified catalog: ${BOOTSTRAP_CMD}")
    RECOMMENDATIONS+=("Or run standalone: $COMPOSE_CMD exec api python -m scripts.seed_catalog")
  fi
fi

# ---------------------------------------------------------------------------
# 6. Docker volumes
# ---------------------------------------------------------------------------
header "Storage"

check_volume() {
  local volume=$1
  local label=$2
  local inspect
  inspect=$($CONTAINER_CLI volume inspect "$(compose_project)_${volume}" 2>/dev/null || $CONTAINER_CLI volume inspect "${volume}" 2>/dev/null || echo "")
  if [[ -n "$inspect" ]]; then
    pass "${label} volume exists"
  else
    warn "${label} volume not found" \
      "Volume '${volume}' will be created on first $COMPOSE_CMD up"
  fi
}

if [[ -n "$CONTAINER_CLI" ]]; then
  check_volume "mongo-data"  "MongoDB data"
  check_volume "chroma-data" "ChromaDB data"
  check_volume "uploads"     "Uploads"
else
  skip "Volume checks (no container engine available)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL=$((CHECKS_PASSED + CHECKS_FAILED + CHECKS_WARNED))

echo ""
echo -e "  ${BOLD}${MAGENTA}╔══════════════════════════════════════════╗${RESET}"
if [[ $CHECKS_FAILED -eq 0 && $CHECKS_WARNED -eq 0 ]]; then
  echo -e "  ${BOLD}${MAGENTA}║${RESET}  ${GREEN}${BOLD}All ${TOTAL} checks passed${RESET}                   ${BOLD}${MAGENTA}║${RESET}"
elif [[ $CHECKS_FAILED -eq 0 ]]; then
  printf "  ${BOLD}${MAGENTA}║${RESET}  ${GREEN}${BOLD}%d passed${RESET}  ${YELLOW}${BOLD}%d warnings${RESET}%*s${BOLD}${MAGENTA}║${RESET}\n" \
    "$CHECKS_PASSED" "$CHECKS_WARNED" $((21 - ${#CHECKS_PASSED} - ${#CHECKS_WARNED})) ""
else
  printf "  ${BOLD}${MAGENTA}║${RESET}  ${GREEN}${BOLD}%d passed${RESET}  ${RED}${BOLD}%d failed${RESET}  ${YELLOW}${BOLD}%d warnings${RESET}%*s${BOLD}${MAGENTA}║${RESET}\n" \
    "$CHECKS_PASSED" "$CHECKS_FAILED" "$CHECKS_WARNED" $((9 - ${#CHECKS_PASSED} - ${#CHECKS_FAILED} - ${#CHECKS_WARNED})) ""
fi
echo -e "  ${BOLD}${MAGENTA}╚══════════════════════════════════════════╝${RESET}"

# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
if [[ ${#RECOMMENDATIONS[@]} -gt 0 ]]; then
  echo ""
  echo -e "  ${BOLD}${CYAN}Recommendations${RESET}"
  echo -e "  ${DIM}───────────────${RESET}"
  local_idx=1
  for rec in "${RECOMMENDATIONS[@]}"; do
    echo -e "  ${YELLOW}${local_idx}.${RESET} ${rec}"
    local_idx=$((local_idx + 1))
  done
fi

echo ""
