#!/usr/bin/env bash
# ============================================================================
#  Vandalizer — Interactive Setup Wizard
#  AI-powered document intelligence for research administration
#
#  Run from the project root:
#    ./setup.sh             First-time setup (or re-run detects existing deployment)
#    ./setup.sh --repair    Diagnose and fix a broken deployment
#    ./setup.sh --upgrade   Pull latest code, backup, rebuild, and redeploy
#    ./setup.sh --redeploy  Rebuild and restart from current code (no git pull)
#    ./setup.sh --seed      Update verified catalog (add new seed data)
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
  printf -v "$var_name" '%s' "$value"
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

# Stream a docker compose build with a live progress tail
build_image() {
  local service="$1"
  local label="$2"
  local logfile="${SETUP_LOG}.${service}"

  echo -e "  ${SYM_NEURAL}  ${BOLD}Building ${label}...${RESET}"

  # Run build in background, tee to logfile (--no-cache ensures code changes are picked up)
  $COMPOSE_CMD build --no-cache "$service" > "$logfile" 2>&1 &
  local pid=$!

  # Show a tail of the build output so the user sees progress
  local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
  local i=0
  local last_line=""

  while kill -0 "$pid" 2>/dev/null; do
    local line
    line=$(tail -1 "$logfile" 2>/dev/null | head -c 70 || true)
    if [[ -n "$line" ]]; then
      last_line="$line"
    fi
    printf "\r  ${CYAN}${frames[$i]}${RESET}  ${DIM}%-72s${RESET}" "$last_line"
    i=$(( (i + 1) % ${#frames[@]} ))
    sleep 0.15
  done

  if wait "$pid"; then
    printf "\r  ${SYM_CHECK}  %-74s\n" "${label} built successfully"
    cat "$logfile" >> "$SETUP_LOG"
  else
    printf "\r  ${SYM_CROSS}  %-74s\n" "${label} build failed"
    echo ""
    echo -e "  ${DIM}     Last 10 lines of build output:${RESET}"
    echo -e "  ${DIM}     ------${RESET}"
    tail -10 "$logfile" | while IFS= read -r errline; do
      echo -e "  ${DIM}     ${errline}${RESET}"
    done
    echo -e "  ${DIM}     ------${RESET}"
    cat "$logfile" >> "$SETUP_LOG"
    ERRORS+=("${label} build failed — check ${SETUP_LOG}")
    rm -f "$logfile"
    return 1
  fi
  rm -f "$logfile"
}

launch_services() {
  section "2" "Launching Services"

  # --- Build phase: show streaming progress ---
  echo -e "  ${DIM}     First build may take several minutes (downloading dependencies).${RESET}"
  echo -e "  ${DIM}     Subsequent builds use Docker layer cache and are much faster.${RESET}"
  echo ""

  local build_ok=true
  build_image "api" "Backend image (API + Celery)" || build_ok=false

  # Celery and Flower share the same Dockerfile — build their images too
  echo -e "  ${DIM}     Building Celery/Flower from same backend image...${RESET}"
  $COMPOSE_CMD build celery flower >> "$SETUP_LOG" 2>&1 || true

  echo ""
  build_image "frontend" "Frontend image (React + Nginx)" || build_ok=false

  if [[ "$build_ok" == false ]]; then
    echo ""
    echo -e "  ${SYM_CROSS}  ${RED}${BOLD}One or more image builds failed. Cannot start services.${RESET}"
    echo -e "  ${DIM}     Check the build log: ${SETUP_LOG}${RESET}"
    echo ""
    echo -e "  ${DIM}     Last 20 lines of build output:${RESET}"
    tail -20 "$SETUP_LOG" | while IFS= read -r errline; do
      echo -e "  ${DIM}     ${errline}${RESET}"
    done
    echo ""
    return 1
  fi

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

  local infra_ok=true
  wait_healthy "redis" "Redis" 30 || infra_ok=false
  wait_healthy "mongo" "MongoDB" 90 || infra_ok=false
  wait_healthy "chromadb" "ChromaDB" 60 || infra_ok=false

  if [[ "$infra_ok" == false ]]; then
    echo ""
    echo -e "  ${SYM_WARN}  ${YELLOW}Infrastructure not fully healthy. Retrying unhealthy services...${RESET}"
    echo ""

    # Restart any unhealthy infra containers and wait again
    for svc in redis mongo chromadb; do
      local health
      health=$($COMPOSE_CMD ps --format '{{.Service}} {{.Health}}' 2>/dev/null | grep "^${svc} " | awk '{print $2}' || true)
      if [[ "$health" != "healthy" && "$health" != "(healthy)" ]]; then
        $COMPOSE_CMD restart "$svc" >> "$SETUP_LOG" 2>&1
      fi
    done

    infra_ok=true
    wait_healthy "redis" "Redis" 30 || infra_ok=false
    wait_healthy "mongo" "MongoDB" 90 || infra_ok=false
    wait_healthy "chromadb" "ChromaDB" 60 || infra_ok=false
  fi

  if [[ "$infra_ok" == false ]]; then
    echo ""
    echo -e "  ${SYM_CROSS}  ${RED}${BOLD}Infrastructure services are not healthy. Cannot start application layer.${RESET}"
    echo -e "  ${DIM}     Check logs: docker compose logs redis mongo chromadb${RESET}"
    echo -e "  ${DIM}     Then re-run: ./setup.sh --repair${RESET}"
    echo ""
    return 1
  fi

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

  wait_healthy "api" "API server" 120
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
  echo -e "  ${SYM_NEURAL}  ${BOLD}Verified catalog${RESET}"
  echo -e "  ${DIM}     The bootstrap will also seed research administration content:${RESET}"
  echo -e "  ${DIM}       •  Verified workflows (e.g. proposal review, compliance checks)${RESET}"
  echo -e "  ${DIM}       •  Extraction templates (structured data extraction configs)${RESET}"
  echo -e "  ${DIM}       •  Knowledge bases (source definitions — content is ingested separately)${RESET}"
  echo -e "  ${DIM}       •  Curated collections to organize the above${RESET}"
  echo ""
  echo -e "  ${SYM_PULSE}  ${DIM}Running bootstrap sequence...${RESET}"
  echo ""

  # Pipe credentials into the container to avoid shell expansion issues with
  # special characters in passwords (e.g. $, !, \, `)
  local container_name
  container_name=$($COMPOSE_CMD ps --format '{{.Service}} {{.Name}}' 2>/dev/null | awk '$1=="api"{print $2}')

  local bootstrap_output=""
  local bootstrap_exit=1

  if [[ -n "$container_name" ]]; then
    # Pass credentials via stdin to Python — no shell expansion, no temp files
    bootstrap_output=$(printf '%s\n' "$ADMIN_EMAIL" "$ADMIN_PASSWORD" "$ADMIN_NAME" "$DEFAULT_TEAM_NAME" | \
      docker exec -i "$container_name" python -c "
import sys, os, runpy
lines = sys.stdin.read().split('\n')
os.environ['ADMIN_EMAIL'] = lines[0] if len(lines) > 0 else ''
os.environ['ADMIN_PASSWORD'] = lines[1] if len(lines) > 1 else ''
os.environ['ADMIN_NAME'] = lines[2] if len(lines) > 2 else ''
os.environ['DEFAULT_TEAM_NAME'] = lines[3] if len(lines) > 3 else ''
runpy.run_path('bootstrap_install.py', run_name='__main__')
" 2>&1)
    bootstrap_exit=$?
  else
    echo -e "  ${SYM_CROSS}  ${RED}API container not found — cannot run bootstrap${RESET}"
  fi

  log "Bootstrap output:"
  log "$bootstrap_output"

  if [[ $bootstrap_exit -ne 0 ]]; then
    echo -e "  ${SYM_WARN}  ${YELLOW}Bootstrap exited with errors:${RESET}"
    echo "$bootstrap_output" | tail -5 | while IFS= read -r errline; do
      echo -e "  ${DIM}     ${errline}${RESET}"
    done
  fi

  # Parse and display results
  if echo "$bootstrap_output" | grep -q "Admin user created"; then
    echo -e "  ${SYM_CHECK}  Admin account created ${DIM}(${ADMIN_EMAIL})${RESET}"
  elif echo "$bootstrap_output" | grep -q "Admin user updated"; then
    echo -e "  ${SYM_CHECK}  Admin account updated ${DIM}(${ADMIN_EMAIL})${RESET}"
  elif echo "$bootstrap_output" | grep -q "Admin user already ready"; then
    echo -e "  ${SYM_CHECK}  Admin account verified ${DIM}(${ADMIN_EMAIL})${RESET}"
  else
    echo -e "  ${SYM_CROSS}  ${RED}Admin account was NOT created${RESET}"
    ERRORS+=("Admin account creation failed — re-run ./setup.sh --repair")
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
    echo -e "  ${SYM_CHECK}  Verified catalog seeded"

    # Extract counts from bootstrap output if available
    local wf_created ss_created kb_created
    wf_created=$(echo "$bootstrap_output" | grep -oi '[0-9]* workflow' | head -1 | grep -o '[0-9]*' || true)
    ss_created=$(echo "$bootstrap_output" | grep -oi '[0-9]* search.set\|[0-9]* template' | head -1 | grep -o '[0-9]*' || true)
    kb_created=$(echo "$bootstrap_output" | grep -oi '[0-9]* knowledge' | head -1 | grep -o '[0-9]*' || true)

    [[ -n "$wf_created" ]] && echo -e "  ${DIM}     Workflows: ${wf_created} seeded${RESET}"
    [[ -n "$ss_created" ]] && echo -e "  ${DIM}     Extraction templates: ${ss_created} seeded${RESET}"
    [[ -n "$kb_created" ]] && echo -e "  ${DIM}     Knowledge bases: ${kb_created} seeded (content not yet ingested)${RESET}"

    echo -e "  ${DIM}     Manage these in the Explore tab or Admin panel after login.${RESET}"
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

  # API health — give the API a moment to settle after bootstrap
  local health_json=''
  local attempt
  for attempt in 1 2 3; do
    health_json=$(curl -sf "http://localhost:8001/api/health" 2>/dev/null || true)
    if [[ "$health_json" == *'"status":"ok"'* ]]; then
      break
    fi
    sleep 5
  done

  if [[ "$health_json" == *'"status":"ok"'* ]]; then
    echo -e "  ${SYM_CHECK}  API health              ${GREEN}operational${RESET}"
  else
    echo -e "  ${SYM_CROSS}  API health              ${RED}not responding${RESET}"
    ERRORS+=("API health check failed")
  fi

  # Individual services from health endpoint
  for svc in mongodb redis chromadb; do
    local label
    label=$(echo "$svc" | sed 's/mongodb/MongoDB/;s/redis/Redis/;s/chromadb/ChromaDB/')

    if [[ "$health_json" == *"\"${svc}\":\"ok\""* ]]; then
      printf "  ${SYM_CHECK}  %-22s ${GREEN}connected${RESET}\n" "$label"
    else
      printf "  ${SYM_CROSS}  %-22s ${RED}unreachable${RESET}\n" "$label"
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

  local MONGO_DB="vandalizer"
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
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${DIM}4.${RESET} Go to ${BOLD}Explore → Knowledge Bases${RESET} and ingest          ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}      content for the seeded knowledge bases                  ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}      ${DIM}(sources are defined but not yet ingested)${RESET}             ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${DIM}5.${RESET} Upload a document and run your first extraction        ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}                                                              ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}╠══════════════════════════════════════════════════════════════╣${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}                                                              ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${DIM}Useful commands:${RESET}                                           ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${GRAY}./setup.sh --repair${RESET}        ${DIM}Diagnose & fix issues${RESET}      ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${GRAY}./setup.sh --upgrade${RESET}       ${DIM}Pull, backup, rebuild${RESET}      ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${GRAY}./setup.sh --redeploy${RESET}      ${DIM}Rebuild current code${RESET}       ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${GRAY}./setup.sh --seed${RESET}          ${DIM}Update verified catalog${RESET}    ${MAGENTA}${BOLD}║${RESET}"
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
# Repair mode: diagnose and fix what's broken
# ---------------------------------------------------------------------------
repair() {
  section "R" "Repair & Self-Heal"

  echo -e "  ${SYM_NEURAL}  ${BOLD}Scanning deployment state...${RESET}"
  echo ""

  local actions_taken=0

  # ── .env health ──────────────────────────────────────────────────────
  if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "  ${SYM_CROSS}  backend/.env is missing"
    echo -e "  ${SYM_ARROW}  ${DIM}Restoring from template...${RESET}"
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo -e "  ${SYM_CHECK}  Created backend/.env from template"
    actions_taken=$((actions_taken + 1))
  else
    echo -e "  ${SYM_CHECK}  backend/.env exists"
  fi

  local jwt_val
  jwt_val=$(grep -E "^JWT_SECRET_KEY=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
  if [[ -z "$jwt_val" || "$jwt_val" == "change-me-to-a-random-secret" ]]; then
    echo -e "  ${SYM_CROSS}  JWT_SECRET_KEY is not set"
    local jwt_key
    jwt_key=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))" 2>/dev/null || openssl rand -base64 48 2>/dev/null)
    sed -i.bak "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${jwt_key}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
    echo -e "  ${SYM_CHECK}  Generated and saved JWT_SECRET_KEY"
    actions_taken=$((actions_taken + 1))
  else
    echo -e "  ${SYM_CHECK}  JWT_SECRET_KEY is configured"
  fi

  local enc_val
  enc_val=$(grep -E "^CONFIG_ENCRYPTION_KEY=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
  if [[ -z "$enc_val" ]]; then
    local enc_key
    enc_key=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || true)
    if [[ -n "$enc_key" ]]; then
      sed -i.bak "s|^CONFIG_ENCRYPTION_KEY=.*|CONFIG_ENCRYPTION_KEY=${enc_key}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
      echo -e "  ${SYM_CHECK}  Generated and saved CONFIG_ENCRYPTION_KEY"
      actions_taken=$((actions_taken + 1))
    fi
  else
    echo -e "  ${SYM_CHECK}  CONFIG_ENCRYPTION_KEY is configured"
  fi

  # ── Docker images ────────────────────────────────────────────────────
  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Checking container images...${RESET}"
  echo ""

  # Determine the compose project name to find images
  local project_name
  project_name=$($COMPOSE_CMD config --format json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('name',''))" 2>/dev/null || true)

  local need_backend_build=false
  local need_frontend_build=false

  if [[ -n "$project_name" ]]; then
    if docker image inspect "${project_name}-api" &>/dev/null 2>&1; then
      echo -e "  ${SYM_CHECK}  Backend image exists"
    else
      echo -e "  ${SYM_CROSS}  Backend image not found"
      need_backend_build=true
    fi

    if docker image inspect "${project_name}-frontend" &>/dev/null 2>&1; then
      echo -e "  ${SYM_CHECK}  Frontend image exists"
    else
      echo -e "  ${SYM_CROSS}  Frontend image not found"
      need_frontend_build=true
    fi
  else
    # Can't determine project name — build both to be safe
    need_backend_build=true
    need_frontend_build=true
  fi

  local build_ok=true

  if [[ "$need_backend_build" == true ]]; then
    echo ""
    build_image "api" "Backend image (API + Celery)" || build_ok=false
    $COMPOSE_CMD build celery flower >> "$SETUP_LOG" 2>&1 || true
    actions_taken=$((actions_taken + 1))
  fi

  if [[ "$need_frontend_build" == true ]]; then
    echo ""
    build_image "frontend" "Frontend image (React + Nginx)" || build_ok=false
    actions_taken=$((actions_taken + 1))
  fi

  if [[ "$build_ok" == false ]]; then
    echo ""
    echo -e "  ${SYM_CROSS}  ${RED}${BOLD}Image build failed. Check the build log: ${SETUP_LOG}${RESET}"
    echo ""
    return 1
  fi

  # ── Service health ───────────────────────────────────────────────────
  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Checking service health...${RESET}"
  echo ""

  # Infrastructure services — start if not running/healthy
  for svc in redis mongo chromadb; do
    local label
    label=$(echo "$svc" | sed 's/redis/Redis/;s/mongo/MongoDB/;s/chromadb/ChromaDB/')
    local state health
    state=$($COMPOSE_CMD ps --format '{{.Service}} {{.State}}' 2>/dev/null | grep "^${svc} " | awk '{print $2}' || true)
    health=$($COMPOSE_CMD ps --format '{{.Service}} {{.Health}}' 2>/dev/null | grep "^${svc} " | awk '{print $2}' || true)

    if [[ "$state" == "running" && ("$health" == "healthy" || "$health" == "(healthy)") ]]; then
      echo -e "  ${SYM_CHECK}  ${label} is healthy"
    elif [[ "$state" == "running" ]]; then
      echo -e "  ${SYM_WARN}  ${label} is running but ${YELLOW}${health:-unknown}${RESET}"
      echo -e "  ${SYM_ARROW}  ${DIM}Restarting...${RESET}"
      $COMPOSE_CMD restart "$svc" >> "$SETUP_LOG" 2>&1
      actions_taken=$((actions_taken + 1))
    else
      echo -e "  ${SYM_CROSS}  ${label} is ${RED}${state:-not running}${RESET}"
      echo -e "  ${SYM_ARROW}  ${DIM}Starting...${RESET}"
      $COMPOSE_CMD up -d "$svc" >> "$SETUP_LOG" 2>&1
      actions_taken=$((actions_taken + 1))
    fi
  done

  # Wait for infra if we started anything
  if [[ $actions_taken -gt 0 ]]; then
    echo ""
    echo -e "  ${SYM_PULSE}  ${DIM}Waiting for infrastructure...${RESET}"
    echo ""
    wait_healthy "redis" "Redis" 30
    wait_healthy "mongo" "MongoDB" 90
    wait_healthy "chromadb" "ChromaDB" 60
  fi

  # Application services
  echo ""
  for svc in api celery flower frontend; do
    local label
    case "$svc" in
      api)      label="API server" ;;
      celery)   label="Celery workers" ;;
      flower)   label="Flower monitor" ;;
      frontend) label="Frontend" ;;
    esac

    local state
    state=$($COMPOSE_CMD ps --format '{{.Service}} {{.State}}' 2>/dev/null | grep "^${svc} " | awk '{print $2}' || true)

    if [[ "$state" == "running" ]]; then
      echo -e "  ${SYM_CHECK}  ${label} is running"
    elif [[ "$state" == "restarting" ]]; then
      echo -e "  ${SYM_CROSS}  ${label} is ${RED}restarting (crash loop)${RESET}"
      echo -e "  ${SYM_ARROW}  ${DIM}Recreating...${RESET}"
      $COMPOSE_CMD up -d --force-recreate "$svc" >> "$SETUP_LOG" 2>&1
      actions_taken=$((actions_taken + 1))
    else
      echo -e "  ${SYM_CROSS}  ${label} is ${RED}${state:-not running}${RESET}"
      echo -e "  ${SYM_ARROW}  ${DIM}Starting...${RESET}"
      $COMPOSE_CMD up -d "$svc" >> "$SETUP_LOG" 2>&1
      actions_taken=$((actions_taken + 1))
    fi
  done

  # Wait for API
  echo ""
  echo -e "  ${SYM_PULSE}  ${DIM}Waiting for API...${RESET}"
  echo ""
  wait_for_api 60

  # ── Seed data ────────────────────────────────────────────────────────
  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Checking bootstrap state...${RESET}"
  echo ""

  local MONGO_CONTAINER
  MONGO_CONTAINER=$($COMPOSE_CMD ps --format '{{.Service}} {{.Name}}' 2>/dev/null | awk '$1=="mongo"{print $2}' || true)

  local MONGO_DB="vandalizer"
  if [[ -f "$ENV_FILE" ]]; then
    local env_db
    env_db=$(grep -E "^MONGO_DB=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
    [[ -n "$env_db" ]] && MONGO_DB="$env_db"
  fi

  local need_bootstrap=false

  if [[ -n "$MONGO_CONTAINER" ]]; then
    local admin_count
    admin_count=$(docker exec "$MONGO_CONTAINER" mongosh --quiet --eval \
      "db.getSiblingDB('${MONGO_DB}').user.countDocuments({is_admin: true})" 2>/dev/null || echo "-1")

    if [[ "$admin_count" == "-1" ]]; then
      echo -e "  ${SYM_WARN}  Could not query MongoDB"
    elif [[ "$admin_count" -ge 1 ]]; then
      echo -e "  ${SYM_CHECK}  Admin account exists"
    else
      echo -e "  ${SYM_CROSS}  No admin account found"
      need_bootstrap=true
    fi

    local wf_count
    wf_count=$(docker exec "$MONGO_CONTAINER" mongosh --quiet --eval \
      "db.getSiblingDB('${MONGO_DB}').workflow.countDocuments({verified: true})" 2>/dev/null || echo "-1")

    if [[ "$wf_count" -ge 11 ]]; then
      echo -e "  ${SYM_CHECK}  Verified catalog is seeded"
    elif [[ "$wf_count" -ge 0 ]]; then
      echo -e "  ${SYM_CROSS}  Verified catalog is incomplete or missing"
      need_bootstrap=true
    fi
  fi

  if [[ "$need_bootstrap" == true ]]; then
    echo ""
    echo -e "  ${SYM_NEURAL}  ${BOLD}Bootstrap needed${RESET}"
    echo ""

    # Check if API is actually reachable before trying bootstrap
    if curl -sf "http://localhost:8001/api/health" -o /dev/null 2>/dev/null; then
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

      local DEFAULT_TEAM_NAME=""
      if confirm "Create a shared default team?" "y"; then
        prompt "Team name" "Research Administration" DEFAULT_TEAM_NAME
      fi

      echo ""

      local container_name
      container_name=$($COMPOSE_CMD ps --format '{{.Service}} {{.Name}}' 2>/dev/null | awk '$1=="api"{print $2}')

      local bootstrap_output=""
      if [[ -n "$container_name" ]]; then
        bootstrap_output=$(printf '%s\n' "$ADMIN_EMAIL" "$ADMIN_PASSWORD" "$ADMIN_NAME" "$DEFAULT_TEAM_NAME" | \
          docker exec -i "$container_name" python -c "
import sys, os, runpy
lines = sys.stdin.read().split('\n')
os.environ['ADMIN_EMAIL'] = lines[0] if len(lines) > 0 else ''
os.environ['ADMIN_PASSWORD'] = lines[1] if len(lines) > 1 else ''
os.environ['ADMIN_NAME'] = lines[2] if len(lines) > 2 else ''
os.environ['DEFAULT_TEAM_NAME'] = lines[3] if len(lines) > 3 else ''
runpy.run_path('bootstrap_install.py', run_name='__main__')
" 2>&1)
      fi

      log "Repair bootstrap output:"
      log "$bootstrap_output"

      # Capture encryption key if generated
      local gen_key
      gen_key=$(echo "$bootstrap_output" | grep "Generated CONFIG_ENCRYPTION_KEY" | sed 's/.*): //' || true)
      if [[ -n "$gen_key" ]]; then
        local existing_enc
        existing_enc=$(grep -E "^CONFIG_ENCRYPTION_KEY=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
        if [[ -z "$existing_enc" ]]; then
          sed -i.bak "s|^CONFIG_ENCRYPTION_KEY=.*|CONFIG_ENCRYPTION_KEY=${gen_key}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
        fi
      fi

      echo -e "  ${SYM_CHECK}  Bootstrap complete"
      actions_taken=$((actions_taken + 1))
    else
      echo -e "  ${SYM_CROSS}  API is not reachable — cannot run bootstrap"
      echo -e "  ${DIM}     Fix the API first, then re-run: ./setup.sh --repair${RESET}"
    fi
  fi

  # ── Summary ──────────────────────────────────────────────────────────
  echo ""
  if [[ $actions_taken -eq 0 ]]; then
    echo -e "  ${BRIGHT_GREEN}${BOLD}Everything looks healthy. No repairs needed.${RESET}"
  else
    echo -e "  ${BRIGHT_GREEN}${BOLD}Repair complete.${RESET} ${DIM}${actions_taken} action(s) taken.${RESET}"
    echo -e "  ${DIM}Run ./status.sh for a full health report.${RESET}"
  fi
}

# ---------------------------------------------------------------------------
# Backup helper (used by upgrade)
# ---------------------------------------------------------------------------
take_backup() {
  local stamp
  stamp=$(date +%Y%m%d_%H%M%S)
  local backup_dir="backups/${stamp}"
  mkdir -p "$backup_dir"

  echo -e "  ${SYM_NEURAL}  ${BOLD}Backing up to ${backup_dir}/${RESET}"
  echo ""

  # Git revision
  git rev-parse HEAD > "$backup_dir/git-revision.txt" 2>/dev/null || true
  echo -e "  ${SYM_CHECK}  Recorded git revision"

  # .env
  if [[ -f "$ENV_FILE" ]]; then
    cp "$ENV_FILE" "$backup_dir/backend.env"
    echo -e "  ${SYM_CHECK}  Backed up backend/.env"
  fi

  # Compose config
  $COMPOSE_CMD config > "$backup_dir/compose.resolved.yaml" 2>/dev/null || true

  # MongoDB
  local mongo_ok=false
  if $COMPOSE_CMD exec -T mongo sh -lc 'mongodump --archive --gzip --db="${MONGO_DB:-vandalizer}"' > "$backup_dir/mongo.archive.gz" 2>/dev/null; then
    local size
    size=$(ls -lh "$backup_dir/mongo.archive.gz" 2>/dev/null | awk '{print $5}')
    echo -e "  ${SYM_CHECK}  MongoDB dump ${DIM}(${size})${RESET}"
    mongo_ok=true
  else
    echo -e "  ${SYM_WARN}  MongoDB dump skipped ${DIM}(container not reachable)${RESET}"
  fi

  # Uploads
  if $COMPOSE_CMD exec -T api sh -lc 'tar czf - -C /app/static/uploads .' > "$backup_dir/uploads.tgz" 2>/dev/null; then
    local size
    size=$(ls -lh "$backup_dir/uploads.tgz" 2>/dev/null | awk '{print $5}')
    echo -e "  ${SYM_CHECK}  Uploads archive ${DIM}(${size})${RESET}"
  else
    echo -e "  ${SYM_WARN}  Uploads backup skipped ${DIM}(container not reachable)${RESET}"
  fi

  # ChromaDB
  if $COMPOSE_CMD exec -T api sh -lc 'tar czf - -C /app/static/db .' > "$backup_dir/chroma.tgz" 2>/dev/null; then
    local size
    size=$(ls -lh "$backup_dir/chroma.tgz" 2>/dev/null | awk '{print $5}')
    echo -e "  ${SYM_CHECK}  ChromaDB archive ${DIM}(${size})${RESET}"
  else
    echo -e "  ${SYM_WARN}  ChromaDB backup skipped ${DIM}(container not reachable)${RESET}"
  fi

  echo ""
  echo -e "  ${DIM}     Backup saved to ${BOLD}${backup_dir}/${RESET}"
  LAST_BACKUP_DIR="$backup_dir"
}

# ---------------------------------------------------------------------------
# Upgrade mode: pull new code, backup, rebuild, redeploy
# ---------------------------------------------------------------------------
upgrade() {
  section "U" "Upgrade"

  # Show current state
  local current_rev
  current_rev=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
  local current_branch
  current_branch=$(git branch --show-current 2>/dev/null || echo "detached")
  echo -e "  ${SYM_NEURAL}  ${BOLD}Current state${RESET}"
  echo -e "  ${DIM}     Branch: ${current_branch}  Commit: ${current_rev}${RESET}"
  echo ""

  # Check remote URL — HTTPS repos need a credential helper or SSH switch
  local remote_url
  remote_url=$(git remote get-url origin 2>/dev/null || echo "")

  if [[ "$remote_url" == https://* ]]; then
    # Test if we can actually authenticate before wasting time
    echo -e "  ${SYM_PULSE}  ${DIM}Checking remote access...${RESET}"
    if ! git ls-remote --heads origin >/dev/null 2>&1; then
      echo -e "  ${SYM_WARN}  ${YELLOW}Cannot authenticate to remote via HTTPS${RESET}"
      echo -e "  ${DIM}     GitHub no longer supports password auth for HTTPS.${RESET}"
      echo ""
      echo -e "  ${DIM}  1)${RESET} ${CYAN}Switch to SSH${RESET}        ${DIM}— use git@github.com:... (requires SSH key)${RESET}"
      echo -e "  ${DIM}  2)${RESET} ${CYAN}Enter a token${RESET}        ${DIM}— use a Personal Access Token for HTTPS${RESET}"
      echo -e "  ${DIM}  3)${RESET} ${CYAN}Skip pull${RESET}            ${DIM}— just rebuild and redeploy current code${RESET}"
      echo ""
      echo -ne "  ${SYM_ARROW}  Select ${DIM}[1]${RESET}: "
      local auth_choice
      read -r auth_choice
      auth_choice="${auth_choice:-1}"

      case "$auth_choice" in
        1)
          # Convert https://github.com/org/repo.git → git@github.com:org/repo.git
          local ssh_url
          ssh_url=$(echo "$remote_url" | sed -E 's|https://github\.com/(.+)|git@github.com:\1|')
          echo ""
          echo -e "  ${SYM_NEURAL}  Switching origin to: ${CYAN}${ssh_url}${RESET}"
          git remote set-url origin "$ssh_url"
          # Verify SSH works
          if git ls-remote --heads origin >/dev/null 2>&1; then
            echo -e "  ${SYM_CHECK}  SSH connection works"
          else
            echo -e "  ${SYM_CROSS}  ${RED}SSH connection failed${RESET}"
            echo -e "  ${DIM}     Make sure your SSH key is added to GitHub:${RESET}"
            echo -e "  ${GRAY}       ssh-keygen -t ed25519 -C \"your-email\"${RESET}"
            echo -e "  ${GRAY}       cat ~/.ssh/id_ed25519.pub  # add this to GitHub → Settings → SSH keys${RESET}"
            echo -e "  ${DIM}     Then re-run: ${GRAY}./setup.sh --upgrade${RESET}"
            # Revert
            git remote set-url origin "$remote_url"
            return 1
          fi
          ;;
        2)
          echo ""
          echo -e "  ${DIM}     Create a token at: https://github.com/settings/tokens${RESET}"
          echo -e "  ${DIM}     Scopes needed: ${BOLD}repo${RESET}"
          echo -ne "  ${SYM_ARROW}  Paste token: "
          local pat
          read -rs pat
          echo ""
          if [[ -z "$pat" ]]; then
            echo -e "  ${SYM_CROSS}  ${RED}No token provided${RESET}"
            return 1
          fi
          # Rewrite URL with token: https://TOKEN@github.com/org/repo.git
          local token_url
          token_url=$(echo "$remote_url" | sed -E "s|https://|https://${pat}@|")
          git remote set-url origin "$token_url"
          if git ls-remote --heads origin >/dev/null 2>&1; then
            echo -e "  ${SYM_CHECK}  Token authentication works"
          else
            echo -e "  ${SYM_CROSS}  ${RED}Token authentication failed — check the token scopes${RESET}"
            git remote set-url origin "$remote_url"
            return 1
          fi
          ;;
        3)
          echo ""
          echo -e "  ${DIM}     Skipping pull — rebuilding from current code.${RESET}"
          # Backup and then jump straight to redeploy
          echo ""
          take_backup
          do_redeploy
          echo ""
          echo -e "  ${BRIGHT_GREEN}${BOLD}Redeploy complete.${RESET}"
          return 0
          ;;
      esac
      echo ""
    fi
  fi

  # Fetch and show what's available
  echo -e "  ${SYM_PULSE}  ${DIM}Fetching latest changes...${RESET}"
  git fetch --tags --quiet 2>/dev/null || true
  echo ""

  local behind
  behind=$(git rev-list --count HEAD..@{upstream} 2>/dev/null || echo "0")
  local latest_tag
  latest_tag=$(git describe --tags --abbrev=0 2>/dev/null || echo "none")

  if [[ "$behind" -gt 0 ]]; then
    echo -e "  ${SYM_ARROW}  ${BOLD}${behind} new commit(s)${RESET} available on ${CYAN}${current_branch}${RESET}"
  else
    echo -e "  ${SYM_CHECK}  Already up to date on ${CYAN}${current_branch}${RESET}"
  fi
  echo -e "  ${DIM}     Latest tag: ${latest_tag}${RESET}"
  echo ""

  # Ask how to upgrade
  echo -e "  ${DIM}  1)${RESET} ${CYAN}Pull latest${RESET}      ${DIM}— git pull on current branch${RESET}"
  echo -e "  ${DIM}  2)${RESET} ${CYAN}Checkout tag${RESET}     ${DIM}— switch to a specific release tag${RESET}"
  echo -e "  ${DIM}  3)${RESET} ${CYAN}Skip pull${RESET}        ${DIM}— just rebuild and redeploy current code${RESET}"
  echo ""
  echo -ne "  ${SYM_ARROW}  Select ${DIM}[1]${RESET}: "
  local pull_choice
  read -r pull_choice
  pull_choice="${pull_choice:-1}"

  # Backup before changing anything
  echo ""
  take_backup

  local pull_ok=true

  case "$pull_choice" in
    1)
      echo ""
      echo -e "  ${SYM_NEURAL}  ${BOLD}Pulling latest changes...${RESET}"
      echo ""
      if git pull 2>&1 | tee -a "$SETUP_LOG" | head -5 | while IFS= read -r line; do
        echo -e "  ${DIM}     ${line}${RESET}"
      done; then
        local new_rev
        new_rev=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
        echo -e "  ${SYM_CHECK}  Updated to ${BOLD}${new_rev}${RESET}"
      else
        echo -e "  ${SYM_CROSS}  ${RED}Git pull failed${RESET}"
        echo -e "  ${DIM}     Resolve conflicts or check ${SETUP_LOG}, then re-run.${RESET}"
        pull_ok=false
      fi
      ;;
    2)
      echo ""
      prompt "Tag to checkout (e.g. v1.2.0)" "$latest_tag" TARGET_TAG
      echo ""
      echo -e "  ${SYM_NEURAL}  ${BOLD}Checking out ${TARGET_TAG}...${RESET}"
      if git checkout "$TARGET_TAG" >> "$SETUP_LOG" 2>&1; then
        echo -e "  ${SYM_CHECK}  Switched to ${BOLD}${TARGET_TAG}${RESET}"
      else
        echo -e "  ${SYM_CROSS}  ${RED}Checkout failed${RESET}"
        echo -e "  ${DIM}     Check ${SETUP_LOG} for details.${RESET}"
        pull_ok=false
      fi
      ;;
    3)
      echo ""
      echo -e "  ${DIM}     Skipping pull — rebuilding from current code.${RESET}"
      ;;
  esac

  if [[ "$pull_ok" != true ]]; then
    echo ""
    echo -e "  ${YELLOW}${BOLD}Upgrade aborted.${RESET} ${DIM}Your backup is at ${LAST_BACKUP_DIR:-backups/}${RESET}"
    return 1
  fi

  # Check for config drift
  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Checking for configuration changes...${RESET}"
  echo ""

  local env_diff
  env_diff=$(git diff "${current_rev}..HEAD" -- backend/.env.example 2>/dev/null || true)
  if [[ -n "$env_diff" ]]; then
    echo -e "  ${SYM_WARN}  ${YELLOW}backend/.env.example has changed${RESET}"
    echo -e "  ${DIM}     Review new variables: git diff ${current_rev}..HEAD -- backend/.env.example${RESET}"
    echo -e "  ${DIM}     Update your backend/.env accordingly.${RESET}"
    echo ""
    if ! confirm "Continue with rebuild?" "y"; then
      echo -e "  ${DIM}     Update backend/.env first, then re-run: ./setup.sh --upgrade${RESET}"
      return 0
    fi
  else
    echo -e "  ${SYM_CHECK}  No config changes detected"
  fi

  # Rebuild and redeploy
  do_redeploy

  echo ""
  echo -e "  ${BRIGHT_GREEN}${BOLD}Upgrade complete.${RESET}"
  echo -e "  ${DIM}Previous code: ${current_rev}  Backup: ${LAST_BACKUP_DIR:-backups/}${RESET}"
  echo ""
  echo -e "  ${DIM}If something is wrong, rollback with:${RESET}"
  echo -e "  ${GRAY}  git checkout ${current_rev} && ./setup.sh --redeploy${RESET}"
}

# ---------------------------------------------------------------------------
# Redeploy: rebuild and restart from current code (no git operations)
# ---------------------------------------------------------------------------
redeploy() {
  section "D" "Redeploy"

  local current_rev
  current_rev=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
  echo -e "  ${DIM}     Rebuilding from commit ${BOLD}${current_rev}${RESET}"
  echo ""

  do_redeploy

  echo ""
  echo -e "  ${BRIGHT_GREEN}${BOLD}Redeploy complete.${RESET}"
}

# Shared rebuild+restart logic used by upgrade and redeploy
do_redeploy() {
  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Rebuilding images...${RESET}"
  echo ""

  local build_ok=true
  build_image "api" "Backend image (API + Celery)" || build_ok=false
  $COMPOSE_CMD build celery flower >> "$SETUP_LOG" 2>&1 || true
  echo ""
  build_image "frontend" "Frontend image (React + Nginx)" || build_ok=false

  if [[ "$build_ok" == false ]]; then
    echo ""
    echo -e "  ${SYM_CROSS}  ${RED}${BOLD}One or more image builds failed. Cannot restart services.${RESET}"
    echo -e "  ${DIM}     Check the build log: ${SETUP_LOG}${RESET}"
    echo ""
    return 1
  fi

  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Restarting services...${RESET}"
  echo ""

  # Recreate application containers with new images (infra stays untouched)
  run_step "Restarting API server" $COMPOSE_CMD up -d --force-recreate --no-deps api
  run_step "Restarting Celery workers" $COMPOSE_CMD up -d --force-recreate --no-deps celery
  run_step "Restarting Flower monitor" $COMPOSE_CMD up -d --force-recreate --no-deps flower
  run_step "Restarting frontend" $COMPOSE_CMD up -d --force-recreate --no-deps frontend

  echo ""
  echo -e "  ${SYM_PULSE}  ${DIM}Waiting for services...${RESET}"
  echo ""

  wait_healthy "api" "API server" 90
  wait_for_api 90
  wait_healthy "frontend" "Frontend" 60
}

# ---------------------------------------------------------------------------
# Update verified catalog: re-run seed script against running deployment
# ---------------------------------------------------------------------------
update_catalog() {
  section "S" "Update Verified Catalog"

  echo -e "  ${DIM}     Re-seeding verified workflows, extractions, and knowledge bases.${RESET}"
  echo -e "  ${DIM}     Existing items are skipped — only new seed data is added.${RESET}"
  echo ""

  # Find the API container
  local container_name
  container_name=$($COMPOSE_CMD ps --format '{{.Names}}' 2>/dev/null | grep -E '(api|backend)' | grep -v celery | head -1 || true)

  if [[ -z "$container_name" ]]; then
    echo -e "  ${SYM_CROSS}  ${RED}API container is not running.${RESET}"
    echo -e "  ${DIM}     Start services first: docker compose up -d${RESET}"
    return 1
  fi

  echo -e "  ${SYM_ARROW}  Using container: ${BOLD}${container_name}${RESET}"
  echo ""

  local seed_output
  if seed_output=$(docker exec "$container_name" python -m scripts.seed_catalog 2>&1); then
    # Display the output with indentation
    while IFS= read -r line; do
      echo -e "  ${DIM}     ${line}${RESET}"
    done <<< "$seed_output"
    echo ""
    echo -e "  ${SYM_CHECK}  ${BRIGHT_GREEN}${BOLD}Verified catalog updated.${RESET}"
  else
    while IFS= read -r line; do
      echo -e "  ${DIM}     ${line}${RESET}"
    done <<< "$seed_output"
    echo ""
    echo -e "  ${SYM_CROSS}  ${RED}Catalog seeding failed. Check output above.${RESET}"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Detect existing deployment
# ---------------------------------------------------------------------------
detect_deployment() {
  # Returns 0 if there's an existing deployment (any containers from this project)
  local running
  running=$($COMPOSE_CMD ps --format '{{.Service}}' 2>/dev/null | head -1 || true)
  [[ -n "$running" ]]
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  # Reset log
  : > "$SETUP_LOG"

  # Handle flags
  case "${1:-}" in
    --repair|-r|repair)
      show_banner
      preflight
      repair
      echo ""
      exit 0
      ;;
    --upgrade|-u|upgrade)
      show_banner
      preflight
      upgrade
      echo ""
      exit 0
      ;;
    --redeploy|-d|redeploy)
      show_banner
      preflight
      redeploy
      echo ""
      exit 0
      ;;
    --seed|-s|seed)
      show_banner
      preflight
      update_catalog
      echo ""
      exit 0
      ;;
    --help|-h|help)
      echo ""
      echo -e "  ${BOLD}Usage:${RESET} ./setup.sh [command]"
      echo ""
      echo -e "  ${BOLD}Commands:${RESET}"
      echo -e "    ${CYAN}(none)${RESET}       Interactive setup — first-time install or repair existing"
      echo -e "    ${CYAN}--repair${RESET}     Diagnose and fix a broken deployment"
      echo -e "    ${CYAN}--upgrade${RESET}    Pull new code, backup, rebuild, and redeploy"
      echo -e "    ${CYAN}--redeploy${RESET}   Rebuild and restart from current code (no git pull)"
      echo -e "    ${CYAN}--seed${RESET}       Update verified catalog with new seed data"
      echo -e "    ${CYAN}--help${RESET}       Show this help"
      echo ""
      exit 0
      ;;
  esac

  show_banner
  preflight

  # If there's an existing deployment, offer mode selection
  if detect_deployment; then
    echo ""
    echo -e "  ${SYM_NEURAL}  ${BOLD}Existing deployment detected.${RESET}"
    echo ""
    echo -e "  ${DIM}  1)${RESET} ${CYAN}Repair${RESET}       ${DIM}— diagnose and fix what's broken${RESET}"
    echo -e "  ${DIM}  2)${RESET} ${CYAN}Upgrade${RESET}      ${DIM}— pull new code, backup, rebuild, redeploy${RESET}"
    echo -e "  ${DIM}  3)${RESET} ${CYAN}Redeploy${RESET}     ${DIM}— rebuild and restart from current code${RESET}"
    echo -e "  ${DIM}  4)${RESET} ${CYAN}Full setup${RESET}   ${DIM}— reconfigure everything from scratch${RESET}"
    echo ""
    echo -ne "  ${SYM_ARROW}  Select mode ${DIM}[1]${RESET}: "
    local mode_choice
    read -r mode_choice
    mode_choice="${mode_choice:-1}"

    case "$mode_choice" in
      2) upgrade; echo ""; exit 0 ;;
      3) redeploy; echo ""; exit 0 ;;
      4) ;; # fall through to full setup
      *) repair; echo ""; exit 0 ;;
    esac
  fi

  configure_env
  launch_services
  bootstrap
  verify
  finale
}

main "$@"
