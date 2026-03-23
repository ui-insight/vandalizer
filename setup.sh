#!/usr/bin/env bash
# ============================================================================
#  Vandalizer — Interactive Setup Wizard
#  AI-powered document intelligence for research administration
#
#  Run from the project root:  ./setup.sh
# ============================================================================

set -uo pipefail

# ---------------------------------------------------------------------------
# Colors & styles
# ---------------------------------------------------------------------------
BOLD='\033[1m'
DIM='\033[2m'
ITALIC='\033[3m'
RESET='\033[0m'
GREEN='\033[38;5;114m'
RED='\033[38;5;203m'
YELLOW='\033[38;5;221m'
BLUE='\033[38;5;111m'
CYAN='\033[38;5;117m'
MAGENTA='\033[38;5;183m'
GRAY='\033[38;5;245m'
WHITE='\033[38;5;255m'
DEEP_CYAN='\033[38;5;44m'
VIOLET='\033[38;5;141m'
BRIGHT_GREEN='\033[38;5;82m'
ORANGE='\033[38;5;208m'

# Nerd symbols
SYM_CHECK="${GREEN}✓${RESET}"
SYM_CROSS="${RED}✗${RESET}"
SYM_WARN="${YELLOW}⚠${RESET}"
SYM_ARROW="${CYAN}▸${RESET}"
SYM_DOT="${MAGENTA}●${RESET}"
SYM_NEURAL="${VIOLET}◆${RESET}"
SYM_PULSE="${DEEP_CYAN}⟐${RESET}"

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
ENV_FILE="backend/.env"
ENV_EXAMPLE="backend/.env.example"
COMPOSE_CMD="docker compose"
SETUP_LOG=".setup.log"
ERRORS=()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { echo "$@" >> "$SETUP_LOG"; }

die() {
  echo ""
  echo -e "  ${RED}${BOLD}Fatal:${RESET} $1"
  echo ""
  exit 1
}

# Typewriter effect — prints text one character at a time
typewriter() {
  local text="$1"
  local delay="${2:-0.02}"
  for (( i=0; i<${#text}; i++ )); do
    printf '%s' "${text:$i:1}"
    sleep "$delay"
  done
}

# Animated spinner while a background process runs
spin() {
  local pid=$1
  local label="${2:-Processing}"
  local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
  local i=0

  while kill -0 "$pid" 2>/dev/null; do
    printf "\r  ${CYAN}${frames[$i]}${RESET}  ${DIM}%s${RESET}  " "$label"
    i=$(( (i + 1) % ${#frames[@]} ))
    sleep 0.08
  done
  wait "$pid"
  return $?
}

# Run a command with a spinner, show pass/fail
run_step() {
  local label="$1"
  shift
  "$@" >> "$SETUP_LOG" 2>&1 &
  local pid=$!
  spin "$pid" "$label"
  if wait "$pid"; then
    printf "\r  ${SYM_CHECK}  %s\n" "$label"
    return 0
  else
    printf "\r  ${SYM_CROSS}  %s\n" "$label"
    ERRORS+=("$label")
    return 1
  fi
}

# Prompt for input with a default value
prompt() {
  local label="$1"
  local default="$2"
  local var_name="$3"
  local is_secret="${4:-false}"

  if [[ -n "$default" ]]; then
    echo -ne "  ${SYM_ARROW}  ${label} ${DIM}[${default}]${RESET}: "
  else
    echo -ne "  ${SYM_ARROW}  ${label}: "
  fi

  local value
  if [[ "$is_secret" == "true" ]]; then
    read -rs value
    echo ""
  else
    read -r value
  fi

  value="${value:-$default}"
  eval "$var_name=\$value"
}

# Prompt yes/no
confirm() {
  local label="$1"
  local default="${2:-y}"
  local hint
  if [[ "$default" == "y" ]]; then hint="Y/n"; else hint="y/N"; fi

  echo -ne "  ${SYM_ARROW}  ${label} ${DIM}[${hint}]${RESET}: "
  local answer
  read -r answer
  answer="${answer:-$default}"
  [[ "$answer" =~ ^[Yy] ]]
}

# Section header with neural-net decoration
section() {
  local num="$1"
  local title="$2"
  echo ""
  echo -e "  ${VIOLET}┌─${RESET} ${BOLD}${WHITE}PHASE ${num}${RESET} ${DIM}─────────────────────────────────────${RESET}"
  echo -e "  ${VIOLET}│${RESET}  ${BOLD}${CYAN}${title}${RESET}"
  echo -e "  ${VIOLET}└──────────────────────────────────────────────${RESET}"
  echo ""
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
show_banner() {
  clear 2>/dev/null || true
  echo ""
  echo -e "${MAGENTA}"
  cat << 'BANNER'
         ██╗   ██╗ █████╗ ███╗   ██╗██████╗  █████╗ ██╗     ██╗███████╗███████╗██████╗
         ██║   ██║██╔══██╗████╗  ██║██╔══██╗██╔══██╗██║     ██║╚══███╔╝██╔════╝██╔══██╗
         ██║   ██║███████║██╔██╗ ██║██║  ██║███████║██║     ██║  ███╔╝ █████╗  ██████╔╝
         ╚██╗ ██╔╝██╔══██║██║╚██╗██║██║  ██║██╔══██║██║     ██║ ███╔╝  ██╔══╝  ██╔══██╗
          ╚████╔╝ ██║  ██║██║ ╚████║██████╔╝██║  ██║███████╗██║███████╗███████╗██║  ██║
           ╚═══╝  ╚═╝  ╚═╝╚═╝  ╚═══╝╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝╚══════╝╚══════╝╚═╝  ╚═╝
BANNER
  echo -e "${RESET}"
  echo -e "  ${DIM}──────────────────────────────────────────────────────────────────────────────${RESET}"
  echo -e "  ${BOLD}${WHITE}  AI-Powered Document Intelligence${RESET}  ${DIM}│${RESET}  ${CYAN}Interactive Setup Wizard${RESET}"
  echo -e "  ${DIM}──────────────────────────────────────────────────────────────────────────────${RESET}"
  echo ""
  echo -ne "  "
  typewriter "Initializing deployment sequence..." 0.03
  echo ""
  sleep 0.5
}

# ---------------------------------------------------------------------------
# Phase 0: Pre-flight checks
# ---------------------------------------------------------------------------
preflight() {
  section "0" "Pre-Flight Diagnostics"

  # Docker
  if command -v docker &>/dev/null; then
    local docker_version
    docker_version=$(docker --version 2>/dev/null | head -1)
    echo -e "  ${SYM_CHECK}  Docker detected ${DIM}(${docker_version})${RESET}"
  else
    die "Docker is not installed. Get it at https://docs.docker.com/get-docker/"
  fi

  # Docker Compose
  if ! $COMPOSE_CMD version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
    if ! $COMPOSE_CMD version &>/dev/null 2>&1; then
      die "Docker Compose is not installed. Get it at https://docs.docker.com/compose/install/"
    fi
  fi
  local compose_version
  compose_version=$($COMPOSE_CMD version --short 2>/dev/null || $COMPOSE_CMD version 2>/dev/null | head -1)
  echo -e "  ${SYM_CHECK}  Docker Compose detected ${DIM}(${compose_version})${RESET}"

  # Docker daemon
  if docker info &>/dev/null 2>&1; then
    echo -e "  ${SYM_CHECK}  Docker daemon is running"
  else
    die "Docker daemon is not running. Start Docker Desktop or the Docker service."
  fi

  # compose.yaml
  if [[ -f "compose.yaml" ]] || [[ -f "docker-compose.yml" ]] || [[ -f "docker-compose.yaml" ]]; then
    echo -e "  ${SYM_CHECK}  Compose file found"
  else
    die "No compose.yaml found. Run this script from the vandalizer project root."
  fi

  # .env.example
  if [[ -f "$ENV_EXAMPLE" ]]; then
    echo -e "  ${SYM_CHECK}  Environment template found"
  else
    die "Missing ${ENV_EXAMPLE}. Are you in the vandalizer project root?"
  fi

  echo ""
  echo -e "  ${BRIGHT_GREEN}${BOLD}Systems nominal.${RESET} ${DIM}All pre-flight checks passed.${RESET}"
}

# ---------------------------------------------------------------------------
# Phase 1: Environment configuration
# ---------------------------------------------------------------------------
configure_env() {
  section "1" "Environment Configuration"

  # Check for existing .env
  if [[ -f "$ENV_FILE" ]]; then
    echo -e "  ${SYM_WARN}  Existing ${BOLD}backend/.env${RESET} detected."
    echo ""
    if ! confirm "Overwrite and reconfigure?"; then
      echo -e "  ${DIM}  Keeping existing configuration.${RESET}"
      # Still check if JWT_SECRET_KEY needs to be set
      local existing_jwt
      existing_jwt=$(grep -E "^JWT_SECRET_KEY=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
      if [[ -z "$existing_jwt" || "$existing_jwt" == "change-me-to-a-random-secret" ]]; then
        echo ""
        echo -e "  ${SYM_WARN}  ${YELLOW}JWT_SECRET_KEY is not set or still the default placeholder.${RESET}"
        echo -e "  ${DIM}     Generating a secure key...${RESET}"
        local jwt_key
        jwt_key=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))" 2>/dev/null || openssl rand -base64 48 2>/dev/null)
        sed -i.bak "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${jwt_key}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
        echo -e "  ${SYM_CHECK}  JWT_SECRET_KEY generated and saved"
      fi
      check_encryption_key
      return
    fi
    echo ""
  fi

  # Copy template
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo -e "  ${SYM_CHECK}  Created ${BOLD}backend/.env${RESET} from template"

  # --- Generate JWT secret ---
  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Generating cryptographic secrets...${RESET}"
  echo ""

  local jwt_key
  jwt_key=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))" 2>/dev/null || openssl rand -base64 48 2>/dev/null)
  if [[ -z "$jwt_key" ]]; then
    die "Could not generate JWT secret. Ensure Python 3 or OpenSSL is available."
  fi
  sed -i.bak "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${jwt_key}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
  echo -e "  ${SYM_CHECK}  JWT_SECRET_KEY ${DIM}— authentication token signing key${RESET}"

  # --- Generate encryption key ---
  local enc_key
  enc_key=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || true)
  if [[ -n "$enc_key" ]]; then
    sed -i.bak "s|^CONFIG_ENCRYPTION_KEY=.*|CONFIG_ENCRYPTION_KEY=${enc_key}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
    echo -e "  ${SYM_CHECK}  CONFIG_ENCRYPTION_KEY ${DIM}— LLM API key encryption${RESET}"
  else
    echo -e "  ${SYM_WARN}  CONFIG_ENCRYPTION_KEY skipped ${DIM}(cryptography package not found locally — bootstrap will auto-generate)${RESET}"
  fi

  # --- Environment mode ---
  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Deployment profile${RESET}"
  echo ""
  echo -e "  ${DIM}  1)${RESET} ${CYAN}development${RESET}  ${DIM}— local dev with hot-reload${RESET}"
  echo -e "  ${DIM}  2)${RESET} ${CYAN}production${RESET}   ${DIM}— optimized for real users${RESET}"
  echo ""
  echo -ne "  ${SYM_ARROW}  Select profile ${DIM}[1]${RESET}: "
  local env_choice
  read -r env_choice
  env_choice="${env_choice:-1}"

  if [[ "$env_choice" == "2" ]]; then
    sed -i.bak "s|^ENVIRONMENT=.*|ENVIRONMENT=production|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
    echo -e "  ${SYM_CHECK}  Environment set to ${BOLD}production${RESET}"

    echo ""
    prompt "Public URL (e.g. https://vandalizer.example.edu)" "http://localhost" FRONTEND_URL
    sed -i.bak "s|^FRONTEND_URL=.*|FRONTEND_URL=${FRONTEND_URL}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
    echo -e "  ${SYM_CHECK}  Frontend URL set to ${BOLD}${FRONTEND_URL}${RESET}"
  else
    echo -e "  ${SYM_CHECK}  Environment set to ${BOLD}development${RESET}"
  fi

  # --- SMTP (optional) ---
  echo ""
  if confirm "Configure email notifications (SMTP)?" "n"; then
    echo ""
    prompt "SMTP host" "" SMTP_HOST
    prompt "SMTP port" "587" SMTP_PORT
    prompt "SMTP username" "" SMTP_USER
    prompt "SMTP password" "" SMTP_PASSWORD true
    prompt "From email" "" SMTP_FROM
    prompt "From name" "Vandalizer" SMTP_FROM_NAME

    sed -i.bak "s|^SMTP_HOST=.*|SMTP_HOST=${SMTP_HOST}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
    sed -i.bak "s|^SMTP_PORT=.*|SMTP_PORT=${SMTP_PORT}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
    sed -i.bak "s|^SMTP_USER=.*|SMTP_USER=${SMTP_USER}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
    sed -i.bak "s|^SMTP_PASSWORD=.*|SMTP_PASSWORD=${SMTP_PASSWORD}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
    sed -i.bak "s|^SMTP_FROM_EMAIL=.*|SMTP_FROM_EMAIL=${SMTP_FROM}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
    sed -i.bak "s|^SMTP_FROM_NAME=.*|SMTP_FROM_NAME=${SMTP_FROM_NAME}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
    echo -e "  ${SYM_CHECK}  SMTP configured"
  else
    echo -e "  ${DIM}     Email notifications disabled. You can configure SMTP later in backend/.env.${RESET}"
  fi

  echo ""
  echo -e "  ${BRIGHT_GREEN}${BOLD}Environment locked in.${RESET}"
}

check_encryption_key() {
  local existing_enc
  existing_enc=$(grep -E "^CONFIG_ENCRYPTION_KEY=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
  if [[ -z "$existing_enc" ]]; then
    local enc_key
    enc_key=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || true)
    if [[ -n "$enc_key" ]]; then
      sed -i.bak "s|^CONFIG_ENCRYPTION_KEY=.*|CONFIG_ENCRYPTION_KEY=${enc_key}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
      echo -e "  ${SYM_CHECK}  CONFIG_ENCRYPTION_KEY generated and saved"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Phase 2: Build & launch containers
# ---------------------------------------------------------------------------
launch_services() {
  section "2" "Launching Services"

  echo -e "  ${SYM_NEURAL}  ${BOLD}Building container images...${RESET}"
  echo -e "  ${DIM}     This may take a few minutes on first run.${RESET}"
  echo ""

  # Build
  run_step "Building backend image" $COMPOSE_CMD build api || true
  run_step "Building frontend image" $COMPOSE_CMD build frontend || true

  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Starting infrastructure layer...${RESET}"
  echo ""

  # Start infra first
  run_step "Starting Redis" $COMPOSE_CMD up -d redis
  run_step "Starting MongoDB" $COMPOSE_CMD up -d mongo
  run_step "Starting ChromaDB" $COMPOSE_CMD up -d chromadb

  # Wait for infra to be healthy
  echo ""
  echo -e "  ${SYM_PULSE}  ${DIM}Waiting for infrastructure health checks...${RESET}"
  echo ""

  wait_healthy "redis" "Redis" 30
  wait_healthy "mongo" "MongoDB" 30
  wait_healthy "chromadb" "ChromaDB" 45

  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Starting application layer...${RESET}"
  echo ""

  run_step "Starting API server" $COMPOSE_CMD up -d api
  run_step "Starting Celery workers" $COMPOSE_CMD up -d celery
  run_step "Starting Flower monitor" $COMPOSE_CMD up -d flower
  run_step "Starting frontend" $COMPOSE_CMD up -d frontend

  echo ""
  echo -e "  ${SYM_PULSE}  ${DIM}Waiting for API to come online...${RESET}"
  echo ""

  wait_healthy "api" "API server" 60
  wait_for_api 60

  echo ""
  echo -e "  ${BRIGHT_GREEN}${BOLD}All systems online.${RESET}"
}

wait_healthy() {
  local service="$1"
  local label="$2"
  local timeout="$3"
  local elapsed=0

  local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
  local i=0

  while [[ $elapsed -lt $timeout ]]; do
    local health
    health=$($COMPOSE_CMD ps --format '{{.Service}} {{.Health}}' 2>/dev/null | grep "^${service} " | awk '{print $2}' || true)

    if [[ "$health" == "healthy" || "$health" == "(healthy)" ]]; then
      printf "\r  ${SYM_CHECK}  %-20s ${GREEN}healthy${RESET}          \n" "$label"
      return 0
    fi

    printf "\r  ${CYAN}${frames[$i]}${RESET}  %-20s ${DIM}waiting... (%ds)${RESET}  " "$label" "$elapsed"
    i=$(( (i + 1) % ${#frames[@]} ))
    sleep 1
    elapsed=$((elapsed + 1))
  done

  printf "\r  ${SYM_WARN}  %-20s ${YELLOW}timeout after %ds${RESET}  \n" "$label" "$timeout"
  ERRORS+=("$label health check timed out")
  return 1
}

wait_for_api() {
  local timeout="$1"
  local elapsed=0
  local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
  local i=0

  while [[ $elapsed -lt $timeout ]]; do
    if curl -sf "http://localhost:8001/api/health" -o /dev/null 2>/dev/null; then
      printf "\r  ${SYM_CHECK}  %-20s ${GREEN}responding${RESET}          \n" "Health endpoint"
      return 0
    fi
    printf "\r  ${CYAN}${frames[$i]}${RESET}  %-20s ${DIM}connecting... (%ds)${RESET}  " "Health endpoint" "$elapsed"
    i=$(( (i + 1) % ${#frames[@]} ))
    sleep 1
    elapsed=$((elapsed + 1))
  done

  printf "\r  ${SYM_WARN}  %-20s ${YELLOW}timeout${RESET}          \n" "Health endpoint"
  return 1
}

# ---------------------------------------------------------------------------
# Phase 3: Bootstrap admin & seed data
# ---------------------------------------------------------------------------
bootstrap() {
  section "3" "Bootstrap & Identity"

  echo -e "  ${SYM_NEURAL}  ${BOLD}Create your admin account${RESET}"
  echo -e "  ${DIM}     This will be the first user with full system access.${RESET}"
  echo ""

  prompt "Admin email" "" ADMIN_EMAIL
  while [[ -z "$ADMIN_EMAIL" ]]; do
    echo -e "  ${SYM_WARN}  ${YELLOW}Email is required.${RESET}"
    prompt "Admin email" "" ADMIN_EMAIL
  done

  prompt "Admin password" "" ADMIN_PASSWORD true
  while [[ -z "$ADMIN_PASSWORD" ]]; do
    echo -e "  ${SYM_WARN}  ${YELLOW}Password is required.${RESET}"
    prompt "Admin password" "" ADMIN_PASSWORD true
  done

  prompt "Admin display name" "Admin" ADMIN_NAME

  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Team configuration${RESET}"
  echo -e "  ${DIM}     A default team gives all new users a shared workspace on signup.${RESET}"
  echo ""

  local DEFAULT_TEAM_NAME=""
  if confirm "Create a shared default team?" "y"; then
    prompt "Team name" "Research Administration" DEFAULT_TEAM_NAME
  fi

  echo ""
  echo -e "  ${SYM_PULSE}  ${DIM}Running bootstrap sequence...${RESET}"
  echo ""

  # Build the docker exec command
  local exec_cmd=("$COMPOSE_CMD" exec -T)
  exec_cmd+=(-e "ADMIN_EMAIL=${ADMIN_EMAIL}")
  exec_cmd+=(-e "ADMIN_PASSWORD=${ADMIN_PASSWORD}")
  exec_cmd+=(-e "ADMIN_NAME=${ADMIN_NAME}")
  if [[ -n "$DEFAULT_TEAM_NAME" ]]; then
    exec_cmd+=(-e "DEFAULT_TEAM_NAME=${DEFAULT_TEAM_NAME}")
  fi
  exec_cmd+=(api python bootstrap_install.py)

  # Capture output so we can show the encryption key if generated
  local bootstrap_output
  bootstrap_output=$("${exec_cmd[@]}" 2>&1) || true
  local bootstrap_exit=$?

  log "Bootstrap output:"
  log "$bootstrap_output"

  # Parse and display results
  if echo "$bootstrap_output" | grep -q "Admin user created"; then
    echo -e "  ${SYM_CHECK}  Admin account created ${DIM}(${ADMIN_EMAIL})${RESET}"
  elif echo "$bootstrap_output" | grep -q "Admin user updated"; then
    echo -e "  ${SYM_CHECK}  Admin account updated ${DIM}(${ADMIN_EMAIL})${RESET}"
  elif echo "$bootstrap_output" | grep -q "Admin user already ready"; then
    echo -e "  ${SYM_CHECK}  Admin account verified ${DIM}(${ADMIN_EMAIL})${RESET}"
  else
    echo -e "  ${SYM_WARN}  Admin account ${DIM}— check logs for details${RESET}"
  fi

  if [[ -n "$DEFAULT_TEAM_NAME" ]]; then
    if echo "$bootstrap_output" | grep -q "Default team created"; then
      echo -e "  ${SYM_CHECK}  Default team created ${DIM}(${DEFAULT_TEAM_NAME})${RESET}"
    elif echo "$bootstrap_output" | grep -q "Default team reused"; then
      echo -e "  ${SYM_CHECK}  Default team verified ${DIM}(${DEFAULT_TEAM_NAME})${RESET}"
    fi
  else
    echo -e "  ${DIM}     No default team — users will start in their personal workspace.${RESET}"
  fi

  # Check for catalog seeding
  if echo "$bootstrap_output" | grep -qi "seed\|catalog\|workflow\|verified"; then
    echo -e "  ${SYM_CHECK}  Verified catalog seeded ${DIM}(workflows, templates, collections)${RESET}"
  fi

  # Check if bootstrap generated an encryption key we need to save
  local gen_key
  gen_key=$(echo "$bootstrap_output" | grep "Generated CONFIG_ENCRYPTION_KEY" | sed 's/.*): //' || true)
  if [[ -n "$gen_key" ]]; then
    # Save it to .env
    local existing_enc
    existing_enc=$(grep -E "^CONFIG_ENCRYPTION_KEY=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
    if [[ -z "$existing_enc" ]]; then
      sed -i.bak "s|^CONFIG_ENCRYPTION_KEY=.*|CONFIG_ENCRYPTION_KEY=${gen_key}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
      echo -e "  ${SYM_CHECK}  CONFIG_ENCRYPTION_KEY captured and saved to .env"
    fi
  fi

  if [[ $bootstrap_exit -ne 0 ]]; then
    echo ""
    echo -e "  ${SYM_WARN}  ${YELLOW}Bootstrap exited with warnings. Check ${SETUP_LOG} for details.${RESET}"
    ERRORS+=("Bootstrap returned non-zero exit")
  fi

  echo ""
  echo -e "  ${BRIGHT_GREEN}${BOLD}Identity established.${RESET}"
}

# ---------------------------------------------------------------------------
# Phase 4: Verification
# ---------------------------------------------------------------------------
verify() {
  section "4" "System Verification"

  echo -e "  ${SYM_NEURAL}  ${BOLD}Running diagnostics...${RESET}"
  echo ""

  # API health
  local health_json
  health_json=$(curl -sf "http://localhost:8001/api/health" 2>/dev/null || echo '{}')

  local api_status
  api_status=$(echo "$health_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','error'))" 2>/dev/null || echo "error")

  if [[ "$api_status" == "ok" ]]; then
    echo -e "  ${SYM_CHECK}  API health              ${GREEN}operational${RESET}"
  else
    echo -e "  ${SYM_CROSS}  API health              ${RED}${api_status}${RESET}"
    ERRORS+=("API health check failed")
  fi

  # Individual services from health endpoint
  for svc in mongodb redis chromadb; do
    local svc_status
    svc_status=$(echo "$health_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('checks',{}).get('${svc}','unknown'))" 2>/dev/null || echo "unknown")
    local label
    label=$(echo "$svc" | sed 's/mongodb/MongoDB/;s/redis/Redis/;s/chromadb/ChromaDB/')

    if [[ "$svc_status" == "ok" ]]; then
      echo -e "  ${SYM_CHECK}  %-22s ${GREEN}connected${RESET}" "$label"
    else
      echo -e "  ${SYM_CROSS}  %-22s ${RED}${svc_status}${RESET}" "$label"
    fi
  done

  # Frontend
  if curl -sf "http://localhost/health" -o /dev/null 2>/dev/null; then
    echo -e "  ${SYM_CHECK}  Frontend               ${GREEN}serving${RESET}"
  elif curl -sf "http://localhost" -o /dev/null 2>/dev/null; then
    echo -e "  ${SYM_CHECK}  Frontend               ${GREEN}serving${RESET}"
  else
    echo -e "  ${SYM_WARN}  Frontend               ${YELLOW}not yet responding (may still be starting)${RESET}"
  fi

  # Celery
  local celery_state
  celery_state=$($COMPOSE_CMD ps --format '{{.Service}} {{.State}}' 2>/dev/null | grep "^celery " | awk '{print $2}' || true)
  if [[ "$celery_state" == "running" ]]; then
    echo -e "  ${SYM_CHECK}  Celery workers          ${GREEN}running${RESET}"
  else
    echo -e "  ${SYM_WARN}  Celery workers          ${YELLOW}${celery_state:-not found}${RESET}"
  fi

  # Seed data verification via mongo
  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Catalog integrity${RESET}"
  echo ""

  local MONGO_CONTAINER
  MONGO_CONTAINER=$($COMPOSE_CMD ps --format '{{.Service}} {{.Name}}' 2>/dev/null | awk '$1=="mongo"{print $2}' || true)

  local MONGO_DB="osp"
  if [[ -f "$ENV_FILE" ]]; then
    local env_db
    env_db=$(grep -E "^MONGO_DB=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
    [[ -n "$env_db" ]] && MONGO_DB="$env_db"
  fi

  if [[ -n "$MONGO_CONTAINER" ]]; then
    mongo_verify() {
      local collection="$1"
      local filter="$2"
      local label="$3"
      local expected="$4"

      local count
      count=$(docker exec "$MONGO_CONTAINER" mongosh --quiet --eval \
        "db.getSiblingDB('${MONGO_DB}').${collection}.countDocuments(${filter})" 2>/dev/null || echo "-1")

      if [[ "$count" == "-1" ]]; then
        echo -e "  ${DIM}  ○  ${label}: could not query${RESET}"
      elif [[ "$count" -ge "$expected" ]]; then
        echo -e "  ${SYM_CHECK}  ${label}: ${GREEN}${count}${RESET} ${DIM}(expected ≥${expected})${RESET}"
      elif [[ "$count" -gt 0 ]]; then
        echo -e "  ${SYM_WARN}  ${label}: ${YELLOW}${count}/${expected}${RESET}"
      else
        echo -e "  ${SYM_CROSS}  ${label}: ${RED}0${RESET}"
      fi
    }

    mongo_verify "user"                   '{"is_admin": true}'    "Admin accounts        " 1
    mongo_verify "workflow"               '{"verified": true}'    "Verified workflows     " 11
    mongo_verify "search_set"             '{"verified": true}'    "Extraction templates   " 4
    mongo_verify "verified_collection"    '{}'                    "Collections            " 5
    mongo_verify "verified_item_metadata" '{}'                    "Catalog metadata       " 15
  else
    echo -e "  ${DIM}  Skipping catalog checks — MongoDB container not reachable.${RESET}"
  fi

  # Docker volumes
  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Persistent storage${RESET}"
  echo ""

  for vol in mongo-data chroma-data uploads; do
    if docker volume inspect "vandalizer_${vol}" &>/dev/null 2>&1 || docker volume inspect "${vol}" &>/dev/null 2>&1; then
      echo -e "  ${SYM_CHECK}  ${vol}"
    else
      echo -e "  ${SYM_WARN}  ${vol} ${DIM}(not yet created)${RESET}"
    fi
  done

  echo ""
  echo -e "  ${BRIGHT_GREEN}${BOLD}Diagnostics complete.${RESET}"
}

# ---------------------------------------------------------------------------
# Finale
# ---------------------------------------------------------------------------
finale() {
  echo ""
  echo -e "  ${MAGENTA}${BOLD}╔══════════════════════════════════════════════════════════════╗${RESET}"

  if [[ ${#ERRORS[@]} -eq 0 ]]; then
    echo -e "  ${MAGENTA}${BOLD}║${RESET}                                                              ${MAGENTA}${BOLD}║${RESET}"
    echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${BRIGHT_GREEN}${BOLD}DEPLOYMENT SUCCESSFUL${RESET}                                     ${MAGENTA}${BOLD}║${RESET}"
    echo -e "  ${MAGENTA}${BOLD}║${RESET}                                                              ${MAGENTA}${BOLD}║${RESET}"
  else
    echo -e "  ${MAGENTA}${BOLD}║${RESET}                                                              ${MAGENTA}${BOLD}║${RESET}"
    echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${YELLOW}${BOLD}DEPLOYMENT COMPLETE WITH WARNINGS${RESET}                          ${MAGENTA}${BOLD}║${RESET}"
    echo -e "  ${MAGENTA}${BOLD}║${RESET}                                                              ${MAGENTA}${BOLD}║${RESET}"
  fi

  echo -e "  ${MAGENTA}${BOLD}╠══════════════════════════════════════════════════════════════╣${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}                                                              ${MAGENTA}${BOLD}║${RESET}"
  printf "  ${MAGENTA}${BOLD}║${RESET}   ${BOLD}${WHITE}Frontend${RESET}     ${CYAN}%-40s${RESET}${MAGENTA}${BOLD}║${RESET}\n" "http://localhost"
  printf "  ${MAGENTA}${BOLD}║${RESET}   ${BOLD}${WHITE}API${RESET}          ${CYAN}%-40s${RESET}${MAGENTA}${BOLD}║${RESET}\n" "http://localhost:8001"
  printf "  ${MAGENTA}${BOLD}║${RESET}   ${BOLD}${WHITE}API Health${RESET}   ${CYAN}%-40s${RESET}${MAGENTA}${BOLD}║${RESET}\n" "http://localhost:8001/api/health"
  printf "  ${MAGENTA}${BOLD}║${RESET}   ${BOLD}${WHITE}Flower${RESET}       ${CYAN}%-40s${RESET}${MAGENTA}${BOLD}║${RESET}\n" "http://localhost:5555"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}                                                              ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}╠══════════════════════════════════════════════════════════════╣${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}                                                              ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${BOLD}${WHITE}Next steps:${RESET}                                                ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}                                                              ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${DIM}1.${RESET} Open ${CYAN}http://localhost${RESET} and log in                    ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${DIM}2.${RESET} Go to ${BOLD}Admin → System Config → Models${RESET}               ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}      Add an LLM provider (OpenAI, Anthropic, etc.)           ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${DIM}3.${RESET} Go to ${BOLD}Admin → System Config → Endpoints${RESET}            ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}      Set an OCR endpoint for scanned PDF extraction          ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}      ${DIM}(optional — basic PDF text extraction works without)${RESET}  ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${DIM}4.${RESET} Upload a document and run your first extraction        ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}                                                              ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}╠══════════════════════════════════════════════════════════════╣${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}                                                              ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${DIM}Useful commands:${RESET}                                           ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${GRAY}./status.sh${RESET}                ${DIM}Full system status${RESET}          ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${GRAY}docker compose logs -f api${RESET} ${DIM}Stream API logs${RESET}            ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${GRAY}docker compose down${RESET}        ${DIM}Stop everything${RESET}            ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}                                                              ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}╚══════════════════════════════════════════════════════════════╝${RESET}"

  if [[ ${#ERRORS[@]} -gt 0 ]]; then
    echo ""
    echo -e "  ${YELLOW}${BOLD}Warnings:${RESET}"
    for err in "${ERRORS[@]}"; do
      echo -e "  ${SYM_WARN}  ${err}"
    done
    echo ""
    echo -e "  ${DIM}Check ${SETUP_LOG} for full logs, or run ./status.sh for a detailed health report.${RESET}"
  fi

  echo ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  # Reset log
  : > "$SETUP_LOG"

  show_banner
  preflight
  configure_env
  launch_services
  bootstrap
  verify
  finale
}

main "$@"
