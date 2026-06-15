#!/usr/bin/env bash
# ============================================================================
#  Vandalizer — Interactive Setup Wizard
#  AI-powered document intelligence for research administration
#
#  Run from the project root:
#    ./setup.sh                First-time setup (or re-run shows the main menu)
#    ./setup.sh --repair       Diagnose and fix a broken deployment
#    ./setup.sh --upgrade      Scan origin for new code & catalog, apply what's outdated
#    ./setup.sh --redeploy     Rebuild and restart from current code (no git pull)
#    ./setup.sh --seed         Update verified catalog (add/refresh, retire dropped items with your OK)
#    ./setup.sh --reset-catalog  Wipe catalog metadata and re-seed from current version
#    ./setup.sh --reingest     Re-ingest all knowledge base content into ChromaDB
#    ./setup.sh --reset-email  Reconfigure email provider (SMTP or Resend)
#    ./setup.sh --cron-setup   Schedule automated upgrades via crontab
#    ./setup.sh --cron-remove  Remove the scheduled auto-update entry
#    ./setup.sh --auto-update  Non-interactive upgrade for cron (logs to .auto_update.log)
#
#  Re-running with no flags on an existing deployment opens a 4-section menu:
#    Monitor   — system status, log tailing, version check, full diagnostics
#    Deploy    — repair, redeploy, upgrade, full setup, email reconfigure
#    Catalog   — update / reset / re-ingest knowledge bases
#    Auto update — schedule, remove, run-now, view log
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

# Version state — populated by show_versions(), reused by scan_and_upgrade().
CODE_VERSION_LOCAL=""
CODE_VERSION_LATEST=""
CATALOG_VERSION_LOCAL=""
CATALOG_VERSION_LATEST=""
SEEDS_VERSION_FILE="backend/seeds/VERSION"
CODE_VERSION_FILE=".vandalizer_version"          # written by upgrade.sh (image deploys)
CATALOG_VERSION_HOST_FILE=".vandalizer_catalog_version"  # written after a successful seed
# Use only compose.yaml — skip compose.override.yaml (dev port overrides).
# This keeps infrastructure ports off the host so Vandalizer can co-exist
# with other services (Mongo, Redis, etc.) on the same server.
export COMPOSE_FILE=compose.yaml

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

  show_versions
}

# ---------------------------------------------------------------------------
# Version detection — code (release tag) and information set (seed catalog)
# ---------------------------------------------------------------------------

# Strip a leading 'v' so sort -V can compare across mixed schemes.
_norm_ver() { echo "${1#v}"; }

# is_newer A B → 0 if A is strictly newer than B, 1 otherwise.
# Treats "" or "unknown" as oldest. Uses sort -V (handles semver and CalVer).
is_newer() {
  local a="${1:-}" b="${2:-}"
  [[ -z "$a" || "$a" == "unknown" ]] && return 1
  [[ -z "$b" || "$b" == "unknown" ]] && return 0
  [[ "$a" == "$b" ]] && return 1
  local na nb top
  na=$(_norm_ver "$a"); nb=$(_norm_ver "$b")
  top=$(printf '%s\n%s\n' "$na" "$nb" | sort -V | tail -1)
  [[ "$top" == "$na" ]]
}

# Code version installed locally.
# Prefers .vandalizer_version (written by upgrade.sh on image deploys),
# falls back to the most recent reachable git tag, then to a short SHA.
code_version_local() {
  if [[ -f "$CODE_VERSION_FILE" ]]; then
    tr -d '[:space:]' < "$CODE_VERSION_FILE"
    return
  fi
  local tag sha
  tag=$(git describe --tags --abbrev=0 2>/dev/null || true)
  if [[ -n "$tag" ]]; then echo "$tag"; return; fi
  sha=$(git rev-parse --short HEAD 2>/dev/null || true)
  echo "${sha:-unknown}"
}

# Latest code version published as a git tag on origin.
# Empty on network failure — caller decides how to render.
code_version_latest() {
  local tags
  tags=$(git ls-remote --tags --refs origin 'v*' 2>/dev/null \
           | awk '{print $2}' | sed 's|^refs/tags/||' | sort -V | tail -1 || true)
  echo "$tags"
}

# Query the running deployment for the applied catalog version. Returns 0
# and prints the version on success; returns 1 (no output) if Mongo is not
# reachable or no catalog_version is recorded.
_catalog_version_from_db() {
  local container
  container=$($COMPOSE_CMD ps --format '{{.Service}} {{.Name}}' 2>/dev/null \
    | awk '$1=="mongo"{print $2}' || true)
  [[ -z "$container" ]] && return 1

  local db="vandalizer"
  if [[ -f "$ENV_FILE" ]]; then
    local env_db
    env_db=$(grep -E "^MONGO_DB=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
    [[ -n "$env_db" ]] && db="$env_db"
  fi

  local v
  v=$(docker exec "$container" mongosh --quiet --eval \
    "var c = db.getSiblingDB('${db}').system_config.findOne({}, {catalog_version: 1}); print(c && c.catalog_version ? c.catalog_version : '');" \
    2>/dev/null | tr -d '[:space:]')

  [[ -n "$v" ]] || return 1
  echo "$v"
}

# Catalog version installed locally. Source of truth is SystemConfig in Mongo
# (written by scripts/seed_catalog.py on every successful seed); the host-side
# file is just a cache so non-Mongo paths (cron pre-flight, etc.) still work.
catalog_version_local() {
  local from_db
  if from_db=$(_catalog_version_from_db) && [[ -n "$from_db" ]]; then
    echo "$from_db" > "$CATALOG_VERSION_HOST_FILE" 2>/dev/null || true
    echo "$from_db"
    return
  fi
  [[ -f "$CATALOG_VERSION_HOST_FILE" ]] || { echo "unknown"; return; }
  tr -d '[:space:]' < "$CATALOG_VERSION_HOST_FILE"
}

# Latest catalog version on origin's default branch.
# Uses a cached git fetch; empty on network failure.
catalog_version_latest() {
  if [[ -d .git ]]; then
    git fetch --quiet origin 2>/dev/null || true
    # Try common default-branch refs in order.
    for ref in origin/HEAD origin/main origin/master; do
      local v
      v=$(git show "$ref:$SEEDS_VERSION_FILE" 2>/dev/null | head -1 | tr -d '[:space:]' || true)
      if [[ -n "$v" ]]; then echo "$v"; return; fi
    done
  fi
  echo ""
}

# Render one version row with a status marker.
_render_version_row() {
  local label="$1" current="$2" latest="$3"
  local status
  if [[ -z "$latest" ]]; then
    status="${DIM}? could not check remote${RESET}"
  elif is_newer "$latest" "$current"; then
    status="${ORANGE}⟐ update available — ${latest}${RESET}"
  else
    status="${GREEN}✓ up to date${RESET}"
  fi
  printf "  ${SYM_NEURAL}  ${BOLD}%-8s${RESET} ${CYAN}%-14s${RESET}  %b\n" \
    "$label" "$current" "$status"
}

# Print code + catalog versions. Caches results in module-level vars so
# scan_and_upgrade() can reuse them without re-fetching.
show_versions() {
  CODE_VERSION_LOCAL=$(code_version_local)
  CODE_VERSION_LATEST=$(code_version_latest)
  CATALOG_VERSION_LOCAL=$(catalog_version_local)
  CATALOG_VERSION_LATEST=$(catalog_version_latest)

  echo ""
  _render_version_row "Code"    "$CODE_VERSION_LOCAL"    "$CODE_VERSION_LATEST"
  _render_version_row "Catalog" "$CATALOG_VERSION_LOCAL" "$CATALOG_VERSION_LATEST"
  echo ""
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
# Set or add a key=value in the backend .env file
# ---------------------------------------------------------------------------
set_env() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}

# ---------------------------------------------------------------------------
# Email configuration (shared by first-time setup and --reset-email)
# ---------------------------------------------------------------------------
configure_email() {
  echo ""
  echo -e "  ${DIM}  1)${RESET} ${CYAN}SMTP${RESET}     ${DIM}— traditional mail server${RESET}"
  echo -e "  ${DIM}  2)${RESET} ${CYAN}Resend${RESET}   ${DIM}— API-based email (resend.com)${RESET}"
  echo ""
  echo -ne "  ${SYM_ARROW}  Email provider ${DIM}[1]${RESET}: "
  local provider_choice
  read -r provider_choice
  provider_choice="${provider_choice:-1}"

  if [[ "$provider_choice" == "2" ]]; then
    # --- Resend ---
    set_env "EMAIL_PROVIDER" "resend"
    echo ""
    prompt "Resend API key" "" RESEND_API_KEY true
    prompt "From email (must be verified in Resend)" "" RESEND_FROM
    prompt "From name" "Vandalizer" RESEND_FROM_NAME

    set_env "RESEND_API_KEY" "$RESEND_API_KEY"
    set_env "RESEND_FROM_EMAIL" "$RESEND_FROM"
    set_env "RESEND_FROM_NAME" "$RESEND_FROM_NAME"
    echo -e "  ${SYM_CHECK}  Resend configured"
  else
    # --- SMTP ---
    set_env "EMAIL_PROVIDER" "smtp"
    echo ""
    prompt "SMTP host" "" SMTP_HOST
    prompt "SMTP port" "587" SMTP_PORT
    prompt "SMTP username" "" SMTP_USER
    prompt "SMTP password" "" SMTP_PASSWORD true
    prompt "From email" "" SMTP_FROM
    prompt "From name" "Vandalizer" SMTP_FROM_NAME

    set_env "SMTP_HOST" "$SMTP_HOST"
    set_env "SMTP_PORT" "$SMTP_PORT"
    set_env "SMTP_USER" "$SMTP_USER"
    set_env "SMTP_PASSWORD" "$SMTP_PASSWORD"
    set_env "SMTP_FROM_EMAIL" "$SMTP_FROM"
    set_env "SMTP_FROM_NAME" "$SMTP_FROM_NAME"
    echo -e "  ${SYM_CHECK}  SMTP configured"
  fi
}

# ---------------------------------------------------------------------------
# Standalone email reset (./setup.sh --reset-email)
# ---------------------------------------------------------------------------
reset_email() {
  section "⚡" "Email Configuration"

  if [[ ! -f "$ENV_FILE" ]]; then
    die "No backend/.env found. Run ./setup.sh first to create the environment."
  fi

  configure_email

  echo ""
  echo -e "  ${BRIGHT_GREEN}${BOLD}Email settings updated.${RESET}"
  echo -e "  ${DIM}     Restart the backend for changes to take effect.${RESET}"
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

  # --- Web server port ---
  echo ""
  prompt "Web server port" "80" WEB_PORT
  # Write WEB_PORT to root .env so docker compose picks it up
  local root_env=".env"
  if [[ -f "$root_env" ]] && grep -q "^WEB_PORT=" "$root_env" 2>/dev/null; then
    sed -i.bak "s|^WEB_PORT=.*|WEB_PORT=${WEB_PORT}|" "$root_env" && rm -f "${root_env}.bak"
  else
    echo "WEB_PORT=${WEB_PORT}" >> "$root_env"
  fi
  echo -e "  ${SYM_CHECK}  Web server will listen on port ${BOLD}${WEB_PORT}${RESET}"

  # --- Email (optional) ---
  echo ""
  if confirm "Configure email notifications?" "n"; then
    configure_email
  else
    echo -e "  ${DIM}     Email notifications disabled. You can configure email later via: ./setup.sh --reset-email${RESET}"
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

  # Stamp the image with a real version on EVERY build path (full setup,
  # redeploy, and upgrade all funnel through build_image). compose passes
  # ${VERSION} as the backend build-arg -> /app/VERSION -> /api/config/version,
  # shown in the account-menu footer. Computed once; the export persists in this
  # shell for sibling builds (e.g. the direct `compose build celery`).
  # Precedence: explicit VERSION env > .vandalizer_version (image deploys) >
  # git describe > "dev" when none are available (tarball / no git).
  if [[ -z "${VERSION:-}" ]]; then
    if [[ -f "$CODE_VERSION_FILE" ]]; then
      VERSION=$(tr -d '[:space:]' < "$CODE_VERSION_FILE")
    else
      VERSION=$(git describe --tags --always 2>/dev/null || echo dev)
    fi
    export VERSION
    echo -e "  ${SYM_CHECK}  Build version: ${BOLD}${VERSION}${RESET}"
  fi

  echo -e "  ${SYM_NEURAL}  ${BOLD}Building ${label}...${RESET}"

  # Run build in background, tee to logfile
  $COMPOSE_CMD build "$service" > "$logfile" 2>&1 &
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

  # Celery shares the same Dockerfile — build its image too
  echo -e "  ${DIM}     Building Celery from same backend image...${RESET}"
  $COMPOSE_CMD build celery >> "$SETUP_LOG" 2>&1 || true

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
  run_step "Starting frontend" $COMPOSE_CMD up -d frontend

  # Clean up dangling images from the build
  docker image prune -f >> "$SETUP_LOG" 2>&1 || true

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
    if $COMPOSE_CMD exec -T api python -c \
      "import urllib.request; urllib.request.urlopen('http://localhost:8001/api/health')" \
      2>/dev/null; then
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
  echo -e "  ${SYM_NEURAL}  ${BOLD}Institution${RESET}"
  echo -e "  ${DIM}     Used for deployment branding and as the default institution on${RESET}"
  echo -e "  ${DIM}     creator credits (\"by Jane Doe at <institution>\") when items are${RESET}"
  echo -e "  ${DIM}     verified into the catalog. Leave blank to skip.${RESET}"
  echo ""
  local ORG_NAME=""
  prompt "Institution / organization name" "" ORG_NAME

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
    bootstrap_output=$(printf '%s\n' "$ADMIN_EMAIL" "$ADMIN_PASSWORD" "$ADMIN_NAME" "$DEFAULT_TEAM_NAME" "$ORG_NAME" | \
      docker exec -i "$container_name" python -c "
import sys, os, runpy
lines = sys.stdin.read().split('\n')
os.environ['ADMIN_EMAIL'] = lines[0] if len(lines) > 0 else ''
os.environ['ADMIN_PASSWORD'] = lines[1] if len(lines) > 1 else ''
os.environ['ADMIN_NAME'] = lines[2] if len(lines) > 2 else ''
os.environ['DEFAULT_TEAM_NAME'] = lines[3] if len(lines) > 3 else ''
os.environ['ORG_NAME'] = lines[4] if len(lines) > 4 else ''
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
    health_json=$($COMPOSE_CMD exec -T api python -c \
      "import urllib.request; print(urllib.request.urlopen('http://localhost:8001/api/health').read().decode())" \
      2>/dev/null || true)
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
  local _wp="${WEB_PORT:-80}"
  local _base_url="http://localhost"
  [[ "$_wp" != "80" ]] && _base_url="http://localhost:${_wp}"
  printf "  ${MAGENTA}${BOLD}║${RESET}   ${BOLD}${WHITE}Frontend${RESET}     ${CYAN}%-40s${RESET}${MAGENTA}${BOLD}║${RESET}\n" "${_base_url}"
  printf "  ${MAGENTA}${BOLD}║${RESET}   ${BOLD}${WHITE}API Health${RESET}   ${CYAN}%-40s${RESET}${MAGENTA}${BOLD}║${RESET}\n" "${_base_url}/api/health"
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
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${GRAY}./setup.sh --cron-setup${RESET}    ${DIM}Schedule auto-updates${RESET}      ${MAGENTA}${BOLD}║${RESET}"
  echo -e "  ${MAGENTA}${BOLD}║${RESET}   ${GRAY}./setup.sh --reset-email${RESET}   ${DIM}Reconfigure email${RESET}        ${MAGENTA}${BOLD}║${RESET}"
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
    $COMPOSE_CMD build celery >> "$SETUP_LOG" 2>&1 || true
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
  for svc in api celery frontend; do
    local label
    case "$svc" in
      api)      label="API server" ;;
      celery)   label="Celery workers" ;;
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
    if $COMPOSE_CMD exec -T api python -c \
      "import urllib.request; urllib.request.urlopen('http://localhost:8001/api/health')" \
      2>/dev/null; then
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

# Capture the institution/org name during redeploy ONLY when it was never set
# (e.g. the operator skipped it at first install). org_name lives in the DB
# (SystemConfig.org_name) and survives rebuilds, so we never re-ask once it's set,
# and we never prompt non-interactively (auto-update/cron must not block).
prompt_org_name_if_unset() {
  [[ -t 0 ]] || return 0   # non-interactive (e.g. auto-update) — skip silently

  local mongo_container api_container mongo_db current_org
  mongo_container=$($COMPOSE_CMD ps --format '{{.Service}} {{.Name}}' 2>/dev/null | awk '$1=="mongo"{print $2}' || true)
  api_container=$($COMPOSE_CMD ps --format '{{.Service}} {{.Name}}' 2>/dev/null | awk '$1=="api"{print $2}' || true)
  [[ -n "$mongo_container" && -n "$api_container" ]] || return 0

  mongo_db="vandalizer"
  if [[ -f "$ENV_FILE" ]]; then
    local env_db
    env_db=$(grep -E "^MONGO_DB=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-)
    [[ -n "$env_db" ]] && mongo_db="$env_db"
  fi

  # Read the current org name. On any query error, skip — better to stay quiet
  # than nag on a transient DB hiccup.
  current_org=$(docker exec "$mongo_container" mongosh --quiet --eval \
    "print(((db.getSiblingDB('${mongo_db}').system_config.findOne()||{}).org_name)||'')" 2>/dev/null | tr -d '\r' || echo "__ERR__")
  [[ "$current_org" == "__ERR__" ]] && return 0
  [[ -n "${current_org// /}" ]] && return 0   # already set — nothing to do

  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Institution${RESET}"
  echo -e "  ${DIM}     No institution/organization name is set for this deployment.${RESET}"
  echo -e "  ${DIM}     Used for branding and creator credit on verified catalog items.${RESET}"
  echo -e "  ${DIM}     Leave blank to skip (set it later in Admin → Theme).${RESET}"
  echo ""
  local ORG_NAME=""
  prompt "Institution / organization name" "" ORG_NAME
  if [[ -z "${ORG_NAME// /}" ]]; then
    echo -e "  ${DIM}     Skipped — no institution name set.${RESET}"
    return 0
  fi

  # Persist through the app's own code: get_config() creates/defaults the
  # singleton safely and never overwrites an already-set value.
  local out
  out=$(printf '%s' "$ORG_NAME" | docker exec -i "$api_container" python -c "
import sys, os, asyncio
os.environ['ORG_NAME'] = sys.stdin.read().strip()
from app.config import Settings
from app.database import init_db
async def main():
    org = os.environ['ORG_NAME'].strip()
    if not org:
        return
    await init_db(Settings())
    from app.models.system_config import SystemConfig
    cfg = await SystemConfig.get_config()
    if not (cfg.org_name or '').strip():
        cfg.org_name = org
        await cfg.save()
        print('ORG_SET:' + org)
    else:
        print('ORG_KEPT:' + cfg.org_name)
asyncio.run(main())
" 2>&1 || true)

  if echo "$out" | grep -q "ORG_SET:"; then
    echo -e "  ${SYM_CHECK}  Institution recorded: ${BOLD}${ORG_NAME}${RESET}"
  elif echo "$out" | grep -q "ORG_KEPT:"; then
    echo -e "  ${SYM_CHECK}  Institution already set; left as is."
  else
    echo -e "  ${SYM_WARN}  ${YELLOW}Could not record institution name (set it later in Admin → Theme).${RESET}"
    log "prompt_org_name_if_unset output:"
    log "$out"
  fi
}

# Shared rebuild+restart logic used by upgrade and redeploy
do_redeploy() {
  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Rebuilding images...${RESET}"
  echo ""

  local build_ok=true
  build_image "api" "Backend image (API + Celery)" || build_ok=false
  $COMPOSE_CMD build celery >> "$SETUP_LOG" 2>&1 || true
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
  run_step "Restarting frontend" $COMPOSE_CMD up -d --force-recreate --no-deps frontend

  echo ""
  echo -e "  ${SYM_PULSE}  ${DIM}Waiting for services...${RESET}"
  echo ""

  wait_healthy "api" "API server" 90
  wait_for_api 90
  wait_healthy "frontend" "Frontend" 60

  # One-time: capture the institution name if this deployment never set one.
  prompt_org_name_if_unset

  # Clean up dangling images and build cache to reclaim disk space
  echo ""
  echo -e "  ${SYM_PULSE}  ${DIM}Cleaning up old Docker images...${RESET}"
  docker image prune -f >> "$SETUP_LOG" 2>&1 || true
}

# ---------------------------------------------------------------------------
# Scan & upgrade: compare local vs origin for both code and information set,
# then offer to apply whichever is outdated. Replaces the old "Upgrade" mode.
# ---------------------------------------------------------------------------
scan_and_upgrade() {
  section "U" "Scan & Upgrade"

  # show_banner already populated CODE_VERSION_* / CATALOG_VERSION_*; if a
  # caller invoked us without a banner (defensive), re-scan now.
  if [[ -z "${CODE_VERSION_LOCAL:-}" ]]; then
    show_versions
  fi

  local code_outdated=0 cat_outdated=0
  is_newer "$CODE_VERSION_LATEST"    "$CODE_VERSION_LOCAL"    && code_outdated=1
  is_newer "$CATALOG_VERSION_LATEST" "$CATALOG_VERSION_LOCAL" && cat_outdated=1

  if [[ $code_outdated -eq 0 && $cat_outdated -eq 0 ]]; then
    echo -e "  ${SYM_CHECK}  ${BRIGHT_GREEN}${BOLD}Everything is up to date.${RESET}"
    echo -e "  ${DIM}     Nothing to upgrade.${RESET}"
    return 0
  fi

  echo -e "  ${SYM_NEURAL}  ${BOLD}Updates available${RESET}"
  [[ $code_outdated -eq 1 ]] && echo -e "  ${DIM}     Code:    ${RESET}${CODE_VERSION_LOCAL} ${DIM}→${RESET} ${ORANGE}${CODE_VERSION_LATEST}${RESET}"
  [[ $cat_outdated  -eq 1 ]] && echo -e "  ${DIM}     Catalog: ${RESET}${CATALOG_VERSION_LOCAL} ${DIM}→${RESET} ${ORANGE}${CATALOG_VERSION_LATEST}${RESET}"
  echo ""

  # Build the menu dynamically — only offer what's actually outdated.
  local options=() actions=()
  if [[ $code_outdated -eq 1 && $cat_outdated -eq 1 ]]; then
    options+=("Upgrade both"); actions+=("both")
    options+=("Upgrade code only"); actions+=("code")
    options+=("Upgrade catalog only"); actions+=("catalog")
  elif [[ $code_outdated -eq 1 ]]; then
    options+=("Upgrade code"); actions+=("code")
  elif [[ $cat_outdated -eq 1 ]]; then
    options+=("Upgrade catalog"); actions+=("catalog")
  fi
  options+=("Skip"); actions+=("skip")

  local i=1
  for opt in "${options[@]}"; do
    echo -e "  ${DIM}  ${i})${RESET} ${CYAN}${opt}${RESET}"
    ((i++))
  done
  echo ""
  echo -ne "  ${SYM_ARROW}  Select ${DIM}[1]${RESET}: "
  local choice
  read -r choice
  choice="${choice:-1}"

  local idx=$((choice - 1))
  if [[ $idx -lt 0 || $idx -ge ${#actions[@]} ]]; then
    echo -e "  ${SYM_WARN}  ${YELLOW}Invalid selection — skipping.${RESET}"
    return 0
  fi
  local action="${actions[$idx]}"

  case "$action" in
    skip)
      echo -e "  ${DIM}     No changes made.${RESET}"
      ;;
    code)
      upgrade
      ;;
    catalog)
      update_catalog
      ;;
    both)
      # Code first — a code upgrade may ship new seed files that the catalog
      # step then applies.
      upgrade && update_catalog
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Update verified catalog: re-run seed script against running deployment
# ---------------------------------------------------------------------------
update_catalog() {
  section "S" "Update Verified Catalog"

  echo -e "  ${DIM}     Re-seeding verified workflows, extractions, and knowledge bases.${RESET}"
  echo -e "  ${DIM}     New items are added and existing ones refreshed. Items dropped from${RESET}"
  echo -e "  ${DIM}     the catalog can be retired (removed from explore) with your OK.${RESET}"
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

  # --- Guard: seeding runs INSIDE the container, against the seed files baked
  # into its image — not the files in this checkout. If the running container
  # was built before the checkout's catalog version, seeding would silently
  # re-apply the old catalog, record the old version, and the upgrade prompt
  # would come back on every run. Require a rebuild first.
  local checkout_catalog container_catalog remote_catalog
  checkout_catalog=$(tr -d '[:space:]' < "$SEEDS_VERSION_FILE" 2>/dev/null || echo "")
  remote_catalog=$(catalog_version_latest)
  if is_newer "$remote_catalog" "$checkout_catalog"; then
    echo -e "  ${SYM_CROSS}  ${RED}${BOLD}Your checkout is older than the latest catalog.${RESET}"
    echo -e "  ${DIM}     Checkout catalog: ${checkout_catalog:-unknown}   Latest on origin: ${remote_catalog}${RESET}"
    echo -e "  ${DIM}     Pull the latest code (which carries the catalog files) first:${RESET}"
    echo -e "  ${GRAY}       ./setup.sh --upgrade${RESET}"
    return 1
  fi
  container_catalog=$(docker exec "$container_name" cat seeds/VERSION 2>/dev/null | tr -d '[:space:]' || echo "")
  if [[ -n "$checkout_catalog" ]] && is_newer "$checkout_catalog" "$container_catalog"; then
    echo -e "  ${SYM_CROSS}  ${RED}${BOLD}The running container is older than your checkout.${RESET}"
    echo -e "  ${DIM}     Container catalog: ${container_catalog:-unknown}   Checkout catalog: ${checkout_catalog}${RESET}"
    echo -e "  ${DIM}     The container only knows the catalog its image was built with, so${RESET}"
    echo -e "  ${DIM}     updating now would re-apply the old catalog. Rebuild first:${RESET}"
    echo -e "  ${GRAY}       ./setup.sh --redeploy${RESET}  ${DIM}then${RESET}  ${GRAY}./setup.sh --seed${RESET}"
    return 1
  fi

  # --- Step 1: preview retirements (items dropped from the catalog) ---
  # Dry run makes no changes; it just lists verified items whose seed_id is gone.
  local prune_flag=""
  local preview
  if preview=$(docker exec "$container_name" python -m scripts.seed_catalog --prune --dry-run 2>&1); then
    local retire_count
    retire_count=$(echo "$preview" | grep -E '^Retiring [0-9]+ item' | head -1 | sed -E 's/^Retiring ([0-9]+) item.*/\1/' || echo "0")
    if [[ -n "$retire_count" && "$retire_count" -gt 0 ]]; then
      echo -e "  ${SYM_WARN}  ${YELLOW}${BOLD}${retire_count} item(s) were dropped from the catalog and can be retired:${RESET}"
      # Show the bullet list of items the prune pass identified.
      echo "$preview" | grep -E '^  - \[' | while IFS= read -r line; do
        echo -e "  ${DIM}    ${line}${RESET}"
      done
      echo ""
      echo -e "  ${DIM}     Retiring soft-archives them (verified=False, removed from explore).${RESET}"
      echo -e "  ${DIM}     The underlying rows are kept, so this is reversible.${RESET}"
      echo ""
      echo -ne "  ${SYM_ARROW}  Retire these ${retire_count} item(s) during the update? [y/N]: "
      local confirm
      read -r confirm
      if [[ "$confirm" =~ ^[Yy] ]]; then
        prune_flag="--prune"
      else
        echo -e "  ${DIM}     Keeping them — running an additive update only.${RESET}"
      fi
      echo ""
    fi
  fi

  # --- Step 2: seed (with --prune only if the user confirmed retirements) ---
  local seed_output
  if seed_output=$(docker exec "$container_name" python -m scripts.seed_catalog $prune_flag 2>&1); then
    # Display the output with indentation
    while IFS= read -r line; do
      echo -e "  ${DIM}     ${line}${RESET}"
    done <<< "$seed_output"
    echo ""
    # Capture the applied version from the seeder's first line for host-side
    # version tracking (so scan_and_upgrade can compare without exec'ing into
    # the container or hitting Mongo).
    local applied
    applied=$(echo "$seed_output" | grep -E '^Catalog version: ' | head -1 | sed 's/^Catalog version: //' | tr -d '[:space:]')
    if [[ -n "$applied" ]]; then
      echo "$applied" > "$CATALOG_VERSION_HOST_FILE"
      echo -e "  ${SYM_CHECK}  ${BRIGHT_GREEN}${BOLD}Verified catalog updated to ${applied}.${RESET}"
    else
      echo -e "  ${SYM_CHECK}  ${BRIGHT_GREEN}${BOLD}Verified catalog updated.${RESET}"
    fi
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
# Re-ingest knowledge bases: rebuild ChromaDB chunks from stored content
# ---------------------------------------------------------------------------
reingest_knowledge_bases() {
  section "K" "Re-ingest Knowledge Bases"

  echo -e "  ${DIM}     Re-ingesting all knowledge base sources into ChromaDB.${RESET}"
  echo -e "  ${DIM}     Sources with stored content are re-chunked directly (no re-fetch).${RESET}"
  echo -e "  ${DIM}     Sources without content will be re-fetched from their URLs.${RESET}"
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

  local reingest_output
  if reingest_output=$(docker exec "$container_name" python -m scripts.reingest_knowledge_bases 2>&1); then
    while IFS= read -r line; do
      echo -e "  ${DIM}     ${line}${RESET}"
    done <<< "$reingest_output"
    echo ""
    echo -e "  ${SYM_CHECK}  ${BRIGHT_GREEN}${BOLD}Knowledge bases re-ingested.${RESET}"
  else
    while IFS= read -r line; do
      echo -e "  ${DIM}     ${line}${RESET}"
    done <<< "$reingest_output"
    echo ""
    echo -e "  ${SYM_CROSS}  ${RED}Re-ingestion failed. Check output above.${RESET}"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Auto-update: non-interactive scan + upgrade + catalog refresh, suitable
# for cron. Skips if nothing is outdated; logs every run to .auto_update.log.
# ---------------------------------------------------------------------------
AUTO_UPDATE_LOG=".auto_update.log"
CRON_MARKER="# vandalizer-auto-update"

auto_update() {
  local stamp
  stamp=$(date '+%Y-%m-%d %H:%M:%S')

  {
    echo ""
    echo "=========================================="
    echo "[${stamp}] Auto-update run"
    echo "=========================================="
  } >> "$AUTO_UPDATE_LOG"

  if ! command -v docker &>/dev/null; then
    echo "[${stamp}] ERROR: docker not found in PATH" >> "$AUTO_UPDATE_LOG"
    return 1
  fi

  CODE_VERSION_LOCAL=$(code_version_local)
  CODE_VERSION_LATEST=$(code_version_latest)
  CATALOG_VERSION_LOCAL=$(catalog_version_local)
  CATALOG_VERSION_LATEST=$(catalog_version_latest)

  {
    echo "Code:    ${CODE_VERSION_LOCAL} -> ${CODE_VERSION_LATEST:-(unreachable)}"
    echo "Catalog: ${CATALOG_VERSION_LOCAL} -> ${CATALOG_VERSION_LATEST:-(unreachable)}"
  } >> "$AUTO_UPDATE_LOG"

  local code_outdated=0 cat_outdated=0
  is_newer "$CODE_VERSION_LATEST"    "$CODE_VERSION_LOCAL"    && code_outdated=1
  is_newer "$CATALOG_VERSION_LATEST" "$CATALOG_VERSION_LOCAL" && cat_outdated=1

  if [[ $code_outdated -eq 0 && $cat_outdated -eq 0 ]]; then
    echo "[${stamp}] Already up to date." >> "$AUTO_UPDATE_LOG"
    return 0
  fi

  if [[ $code_outdated -eq 1 ]]; then
    echo "[${stamp}] Pulling latest code on $(git branch --show-current 2>/dev/null)..." >> "$AUTO_UPDATE_LOG"
    git fetch --tags --quiet >> "$AUTO_UPDATE_LOG" 2>&1 || true
    if ! git pull --ff-only >> "$AUTO_UPDATE_LOG" 2>&1; then
      echo "[${stamp}] ERROR: git pull --ff-only failed (manual merge needed). Aborting." >> "$AUTO_UPDATE_LOG"
      return 1
    fi
    echo "[${stamp}] Backing up..." >> "$AUTO_UPDATE_LOG"
    take_backup >> "$AUTO_UPDATE_LOG" 2>&1 || true
    echo "[${stamp}] Rebuilding and restarting services..." >> "$AUTO_UPDATE_LOG"
    if ! do_redeploy >> "$AUTO_UPDATE_LOG" 2>&1; then
      echo "[${stamp}] ERROR: rebuild/restart failed." >> "$AUTO_UPDATE_LOG"
      return 1
    fi
    echo "[${stamp}] Code upgrade complete." >> "$AUTO_UPDATE_LOG"
  fi

  if [[ $cat_outdated -eq 1 ]]; then
    echo "[${stamp}] Updating verified catalog..." >> "$AUTO_UPDATE_LOG"
    if ! update_catalog >> "$AUTO_UPDATE_LOG" 2>&1; then
      echo "[${stamp}] ERROR: catalog update failed." >> "$AUTO_UPDATE_LOG"
      return 1
    fi
    echo "[${stamp}] Catalog update complete." >> "$AUTO_UPDATE_LOG"
  fi

  echo "[${stamp}] Auto-update finished successfully." >> "$AUTO_UPDATE_LOG"
  return 0
}

# ---------------------------------------------------------------------------
# Cron management: schedule (or remove) periodic auto-updates
# ---------------------------------------------------------------------------
_cron_project_dir() {
  cd "$(dirname "${BASH_SOURCE[0]}")" && pwd
}

setup_cron() {
  section "C" "Schedule Automated Updates"

  if ! command -v crontab &>/dev/null; then
    echo -e "  ${SYM_CROSS}  ${RED}'crontab' command not available on this system.${RESET}"
    echo -e "  ${DIM}     Install cron (e.g. 'apt install cron') and try again.${RESET}"
    return 1
  fi

  echo -e "  ${DIM}     A cron job will check origin for new code & catalog,${RESET}"
  echo -e "  ${DIM}     pull updates, take a backup, rebuild, and restart services.${RESET}"
  echo -e "  ${DIM}     If nothing is outdated the run is a no-op.${RESET}"
  echo ""

  local project_dir script_path
  project_dir=$(_cron_project_dir)
  script_path="${project_dir}/setup.sh"

  if crontab -l 2>/dev/null | grep -Fq "$CRON_MARKER"; then
    local existing
    existing=$(crontab -l 2>/dev/null | grep -F "$CRON_MARKER" | head -1)
    echo -e "  ${SYM_WARN}  ${YELLOW}An auto-update schedule already exists:${RESET}"
    echo -e "  ${DIM}     ${existing}${RESET}"
    echo ""
    if ! confirm "Replace it?" "y"; then
      echo -e "  ${DIM}     Keeping existing schedule.${RESET}"
      return 0
    fi
    echo ""
  fi

  echo -e "  ${DIM}  1)${RESET} ${CYAN}Daily${RESET}      ${DIM}— every day at a chosen time${RESET}"
  echo -e "  ${DIM}  2)${RESET} ${CYAN}Weekly${RESET}     ${DIM}— once a week on a chosen day${RESET}"
  echo -e "  ${DIM}  3)${RESET} ${CYAN}Monthly${RESET}    ${DIM}— once a month on day 1${RESET}"
  echo -e "  ${DIM}  4)${RESET} ${CYAN}Custom${RESET}     ${DIM}— enter your own cron expression${RESET}"
  echo ""
  echo -ne "  ${SYM_ARROW}  Select ${DIM}[1]${RESET}: "
  local sched_choice
  read -r sched_choice
  sched_choice="${sched_choice:-1}"

  local cron_expr=""
  local sched_time hh mm sched_dow

  case "$sched_choice" in
    1)
      prompt "Time of day (HH:MM, 24-hour)" "02:00" sched_time
      hh=${sched_time%:*}; mm=${sched_time#*:}
      hh=$((10#${hh:-2})); mm=$((10#${mm:-0}))
      cron_expr="${mm} ${hh} * * *"
      ;;
    2)
      echo ""
      echo -e "  ${DIM}     0=Sun  1=Mon  2=Tue  3=Wed  4=Thu  5=Fri  6=Sat${RESET}"
      prompt "Day of week (0-6)" "0" sched_dow
      prompt "Time of day (HH:MM, 24-hour)" "02:00" sched_time
      hh=${sched_time%:*}; mm=${sched_time#*:}
      hh=$((10#${hh:-2})); mm=$((10#${mm:-0}))
      cron_expr="${mm} ${hh} * * ${sched_dow}"
      ;;
    3)
      prompt "Time of day (HH:MM, 24-hour)" "02:00" sched_time
      hh=${sched_time%:*}; mm=${sched_time#*:}
      hh=$((10#${hh:-2})); mm=$((10#${mm:-0}))
      cron_expr="${mm} ${hh} 1 * *"
      ;;
    4)
      echo ""
      echo -e "  ${DIM}     Format: minute hour day_of_month month day_of_week${RESET}"
      echo -e "  ${DIM}     Example: 0 3 * * 0  (every Sunday at 3:00 AM)${RESET}"
      prompt "Cron expression" "0 2 * * *" cron_expr
      ;;
    *)
      echo -e "  ${SYM_WARN}  ${YELLOW}Invalid selection — aborting.${RESET}"
      return 1
      ;;
  esac

  local cron_line="${cron_expr} cd ${project_dir} && ${script_path} --auto-update >> ${project_dir}/${AUTO_UPDATE_LOG} 2>&1 ${CRON_MARKER}"

  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}New cron entry:${RESET}"
  echo -e "  ${DIM}     ${cron_line}${RESET}"
  echo ""

  if ! confirm "Install this schedule?" "y"; then
    echo -e "  ${DIM}     Cancelled — no changes made.${RESET}"
    return 0
  fi

  local tmp
  tmp=$(mktemp)
  crontab -l 2>/dev/null | grep -Fv "$CRON_MARKER" > "$tmp" || true
  echo "$cron_line" >> "$tmp"
  if crontab "$tmp"; then
    rm -f "$tmp"
    echo ""
    echo -e "  ${SYM_CHECK}  ${BRIGHT_GREEN}${BOLD}Auto-update scheduled.${RESET}"
    echo -e "  ${DIM}     Logs:   ${project_dir}/${AUTO_UPDATE_LOG}${RESET}"
    echo -e "  ${DIM}     Verify: crontab -l | grep vandalizer-auto-update${RESET}"
    echo -e "  ${DIM}     Remove: ./setup.sh --cron-remove${RESET}"
  else
    rm -f "$tmp"
    echo -e "  ${SYM_CROSS}  ${RED}Failed to install crontab. Check permissions.${RESET}"
    return 1
  fi
}

remove_cron() {
  section "C" "Remove Auto-Update Schedule"

  if ! command -v crontab &>/dev/null; then
    echo -e "  ${SYM_CROSS}  ${RED}'crontab' command not available on this system.${RESET}"
    return 1
  fi

  if ! crontab -l 2>/dev/null | grep -Fq "$CRON_MARKER"; then
    echo -e "  ${SYM_CHECK}  No auto-update schedule found — nothing to remove."
    return 0
  fi

  local existing
  existing=$(crontab -l 2>/dev/null | grep -F "$CRON_MARKER" | head -1)
  echo -e "  ${SYM_NEURAL}  ${BOLD}Existing entry:${RESET}"
  echo -e "  ${DIM}     ${existing}${RESET}"
  echo ""

  if ! confirm "Remove it?" "y"; then
    echo -e "  ${DIM}     Cancelled — schedule kept.${RESET}"
    return 0
  fi

  local tmp
  tmp=$(mktemp)
  crontab -l 2>/dev/null | grep -Fv "$CRON_MARKER" > "$tmp" || true
  if crontab "$tmp"; then
    rm -f "$tmp"
    echo -e "  ${SYM_CHECK}  ${BRIGHT_GREEN}${BOLD}Auto-update schedule removed.${RESET}"
  else
    rm -f "$tmp"
    echo -e "  ${SYM_CROSS}  ${RED}Failed to update crontab.${RESET}"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Reset verified catalog: wipe catalog metadata (preserving underlying
# Workflow/SearchSet/KnowledgeBase rows), then re-seed from current version.
# ---------------------------------------------------------------------------
reset_catalog() {
  section "X" "Reset Verified Catalog"

  local current_version
  current_version=$(catalog_version_local)
  [[ -z "$current_version" || "$current_version" == "unknown" ]] && current_version="(seed files in working tree)"

  echo -e "  ${SYM_WARN}  ${YELLOW}${BOLD}This is a destructive operation.${RESET}"
  echo ""
  echo -e "  ${DIM}     Removes from MongoDB:${RESET}"
  echo -e "  ${DIM}       •  All verified collections${RESET}"
  echo -e "  ${DIM}       •  All verified item metadata (display names, quality scores)${RESET}"
  echo -e "  ${DIM}       •  All verified library items${RESET}"
  echo -e "  ${DIM}       •  The verified library container${RESET}"
  echo ""
  echo -e "  ${DIM}     Preserves:${RESET}"
  echo -e "  ${DIM}       •  Underlying workflows, search sets, knowledge bases${RESET}"
  echo -e "  ${DIM}       •  User bookmarks (personal/team library items)${RESET}"
  echo -e "  ${DIM}       •  Workflow run history${RESET}"
  echo ""
  echo -e "  ${DIM}     After reset, the catalog is re-seeded from version ${BOLD}${current_version}${RESET}."
  echo ""

  echo -ne "  ${SYM_ARROW}  Type ${BOLD}RESET${RESET} to confirm (anything else cancels): "
  local confirm
  read -r confirm
  if [[ "$confirm" != "RESET" ]]; then
    echo ""
    echo -e "  ${DIM}     Cancelled — no changes made.${RESET}"
    return 0
  fi

  # Backup first — gives the user a rollback path.
  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Taking safety backup...${RESET}"
  echo ""
  take_backup

  # Locate API container.
  local container_name
  container_name=$(_find_api_container)
  if [[ -z "$container_name" ]]; then
    echo ""
    echo -e "  ${SYM_CROSS}  ${RED}API container is not running.${RESET}"
    echo -e "  ${DIM}     Start services first: docker compose up -d${RESET}"
    return 1
  fi

  echo ""
  echo -e "  ${SYM_NEURAL}  ${BOLD}Resetting and re-seeding catalog...${RESET}"
  echo -e "  ${DIM}     Using container: ${container_name}${RESET}"
  echo ""

  local seed_output
  if seed_output=$(docker exec "$container_name" python -m scripts.seed_catalog --reset 2>&1); then
    while IFS= read -r line; do
      echo -e "  ${DIM}     ${line}${RESET}"
    done <<< "$seed_output"
    echo ""
    local applied
    applied=$(echo "$seed_output" | grep -E '^Catalog version: ' | head -1 | sed 's/^Catalog version: //' | tr -d '[:space:]')
    if [[ -n "$applied" ]]; then
      echo "$applied" > "$CATALOG_VERSION_HOST_FILE"
      echo -e "  ${SYM_CHECK}  ${BRIGHT_GREEN}${BOLD}Verified catalog reset to ${applied}.${RESET}"
    else
      echo -e "  ${SYM_CHECK}  ${BRIGHT_GREEN}${BOLD}Verified catalog reset.${RESET}"
    fi
    echo -e "  ${DIM}     Backup at: ${LAST_BACKUP_DIR:-backups/}${RESET}"
  else
    while IFS= read -r line; do
      echo -e "  ${DIM}     ${line}${RESET}"
    done <<< "$seed_output"
    echo ""
    echo -e "  ${SYM_CROSS}  ${RED}Reset failed. Restore from backup if needed:${RESET}"
    echo -e "  ${DIM}     ${LAST_BACKUP_DIR:-backups/}${RESET}"
    return 1
  fi
}

# Helper — locate the running api container by service name.
_find_api_container() {
  $COMPOSE_CMD ps --format '{{.Service}} {{.Name}}' 2>/dev/null \
    | awk '$1=="api"{print $2}' | head -1
}

# ---------------------------------------------------------------------------
# Monitor helpers
# ---------------------------------------------------------------------------
show_status() {
  section "M" "System Status"

  if [[ -x "./status.sh" ]]; then
    ./status.sh
  else
    echo -e "  ${SYM_WARN}  ${YELLOW}./status.sh not found or not executable — falling back to compose ps.${RESET}"
    echo ""
    $COMPOSE_CMD ps
  fi
}

tail_logs_menu() {
  section "L" "Tail Service Logs"

  echo -e "  ${DIM}     Press Ctrl-C to stop tailing and return to the menu.${RESET}"
  echo ""
  echo -e "  ${DIM}  1)${RESET} ${CYAN}api${RESET}        ${DIM}— FastAPI backend${RESET}"
  echo -e "  ${DIM}  2)${RESET} ${CYAN}celery${RESET}     ${DIM}— task workers${RESET}"
  echo -e "  ${DIM}  3)${RESET} ${CYAN}frontend${RESET}   ${DIM}— React/Nginx${RESET}"
  echo -e "  ${DIM}  4)${RESET} ${CYAN}mongo${RESET}      ${DIM}— MongoDB${RESET}"
  echo -e "  ${DIM}  5)${RESET} ${CYAN}redis${RESET}      ${DIM}— Redis${RESET}"
  echo -e "  ${DIM}  6)${RESET} ${CYAN}chromadb${RESET}   ${DIM}— ChromaDB${RESET}"
  echo -e "  ${DIM}  7)${RESET} ${CYAN}all${RESET}        ${DIM}— every service${RESET}"
  echo -e "  ${DIM}  0)${RESET} ${CYAN}Back${RESET}"
  echo ""
  echo -ne "  ${SYM_ARROW}  Select ${DIM}[1]${RESET}: "
  local svc_choice
  read -r svc_choice
  svc_choice="${svc_choice:-1}"

  local svc=""
  case "$svc_choice" in
    1) svc="api" ;;
    2) svc="celery" ;;
    3) svc="frontend" ;;
    4) svc="mongo" ;;
    5) svc="redis" ;;
    6) svc="chromadb" ;;
    7) svc="" ;;  # all
    0) return 0 ;;
    *) echo -e "  ${SYM_WARN}  ${YELLOW}Invalid selection.${RESET}"; return 0 ;;
  esac

  echo ""
  if [[ -z "$svc" ]]; then
    $COMPOSE_CMD logs -f --tail=50
  else
    $COMPOSE_CMD logs -f --tail=100 "$svc"
  fi
}

check_for_updates() {
  section "V" "Version Check"
  show_versions

  local code_outdated=0 cat_outdated=0
  is_newer "$CODE_VERSION_LATEST"    "$CODE_VERSION_LOCAL"    && code_outdated=1
  is_newer "$CATALOG_VERSION_LATEST" "$CATALOG_VERSION_LOCAL" && cat_outdated=1

  if [[ $code_outdated -eq 0 && $cat_outdated -eq 0 ]]; then
    echo -e "  ${BRIGHT_GREEN}${BOLD}Everything is up to date.${RESET}"
  else
    echo -e "  ${ORANGE}${BOLD}Updates are available.${RESET}"
    echo -e "  ${DIM}     Use ${BOLD}Deploy → Upgrade${RESET}${DIM} (or ${BOLD}./setup.sh --upgrade${RESET}${DIM}) to apply.${RESET}"
  fi
}

# ---------------------------------------------------------------------------
# Auto-update helpers
# ---------------------------------------------------------------------------
view_auto_update_log() {
  section "L" "Auto-Update Log"

  if [[ ! -f "$AUTO_UPDATE_LOG" ]]; then
    echo -e "  ${DIM}     No auto-update log yet (${AUTO_UPDATE_LOG} not found).${RESET}"
    echo -e "  ${DIM}     Schedule auto-updates from the Auto Update menu first.${RESET}"
    return 0
  fi

  local lines
  lines=$(wc -l < "$AUTO_UPDATE_LOG" | tr -d '[:space:]')
  echo -e "  ${DIM}     Showing last 80 lines of ${AUTO_UPDATE_LOG} (${lines} lines total).${RESET}"
  echo ""
  tail -80 "$AUTO_UPDATE_LOG" | while IFS= read -r line; do
    echo -e "  ${DIM}${line}${RESET}"
  done
}

run_auto_update_now() {
  section "A" "Run Auto-Update Now"

  echo -e "  ${DIM}     Runs the same non-interactive flow that cron uses.${RESET}"
  echo -e "  ${DIM}     Output is appended to ${AUTO_UPDATE_LOG}.${RESET}"
  echo ""

  if auto_update; then
    echo -e "  ${SYM_CHECK}  ${BRIGHT_GREEN}${BOLD}Auto-update finished.${RESET}"
  else
    echo -e "  ${SYM_CROSS}  ${RED}Auto-update reported errors.${RESET}"
  fi

  if [[ -f "$AUTO_UPDATE_LOG" ]]; then
    echo ""
    echo -e "  ${DIM}     Last 20 lines of ${AUTO_UPDATE_LOG}:${RESET}"
    echo ""
    tail -20 "$AUTO_UPDATE_LOG" | while IFS= read -r line; do
      echo -e "  ${DIM}${line}${RESET}"
    done
  fi
}

# ---------------------------------------------------------------------------
# Submenus
# ---------------------------------------------------------------------------
_submenu_prompt() {
  echo ""
  echo -ne "  ${SYM_ARROW}  Select ${DIM}[0]${RESET}: "
}

monitor_menu() {
  while true; do
    echo ""
    echo -e "  ${VIOLET}┌─${RESET} ${BOLD}${WHITE}MONITOR${RESET} ${DIM}─────────────────────────────────────────${RESET}"
    echo -e "  ${VIOLET}└──────────────────────────────────────────────${RESET}"
    echo ""
    echo -e "  ${DIM}  1)${RESET} ${CYAN}System status${RESET}        ${DIM}— containers, health, disk usage${RESET}"
    echo -e "  ${DIM}  2)${RESET} ${CYAN}Tail logs${RESET}            ${DIM}— stream a service's log output${RESET}"
    echo -e "  ${DIM}  3)${RESET} ${CYAN}Check for updates${RESET}    ${DIM}— compare local vs origin versions${RESET}"
    echo -e "  ${DIM}  4)${RESET} ${CYAN}Run diagnostics${RESET}      ${DIM}— full health/integrity sweep${RESET}"
    echo -e "  ${DIM}  0)${RESET} ${CYAN}Back${RESET}"
    _submenu_prompt
    local c; read -r c; c="${c:-0}"
    case "$c" in
      1) show_status ;;
      2) tail_logs_menu ;;
      3) check_for_updates ;;
      4) verify ;;
      0) return 0 ;;
      *) echo -e "  ${SYM_WARN}  ${YELLOW}Invalid selection.${RESET}" ;;
    esac
  done
}

deploy_menu() {
  while true; do
    echo ""
    echo -e "  ${VIOLET}┌─${RESET} ${BOLD}${WHITE}DEPLOY${RESET} ${DIM}──────────────────────────────────────────${RESET}"
    echo -e "  ${VIOLET}└──────────────────────────────────────────────${RESET}"
    echo ""
    echo -e "  ${DIM}  1)${RESET} ${CYAN}Repair${RESET}              ${DIM}— diagnose and fix what's broken${RESET}"
    echo -e "  ${DIM}  2)${RESET} ${CYAN}Redeploy${RESET}            ${DIM}— rebuild and restart from current code${RESET}"
    echo -e "  ${DIM}  3)${RESET} ${CYAN}Upgrade${RESET}             ${DIM}— scan origin for new code & apply${RESET}"
    echo -e "  ${DIM}  4)${RESET} ${CYAN}Full setup${RESET}          ${DIM}— reconfigure environment from scratch${RESET}"
    echo -e "  ${DIM}  5)${RESET} ${CYAN}Reconfigure email${RESET}   ${DIM}— change SMTP / Resend settings${RESET}"
    echo -e "  ${DIM}  0)${RESET} ${CYAN}Back${RESET}"
    _submenu_prompt
    local c; read -r c; c="${c:-0}"
    case "$c" in
      1) repair ;;
      2) redeploy ;;
      3) scan_and_upgrade ;;
      4)
        # Full setup is a multi-phase flow that exits the menu loop on completion.
        configure_env
        launch_services
        bootstrap
        verify
        finale
        return 0
        ;;
      5) reset_email ;;
      0) return 0 ;;
      *) echo -e "  ${SYM_WARN}  ${YELLOW}Invalid selection.${RESET}" ;;
    esac
  done
}

catalog_menu() {
  while true; do
    echo ""
    echo -e "  ${VIOLET}┌─${RESET} ${BOLD}${WHITE}CATALOG${RESET} ${DIM}─────────────────────────────────────────${RESET}"
    echo -e "  ${VIOLET}└──────────────────────────────────────────────${RESET}"
    echo ""
    echo -e "  ${DIM}  1)${RESET} ${CYAN}Update verified catalog${RESET}    ${DIM}— additive seed, keeps modifications${RESET}"
    echo -e "  ${DIM}  2)${RESET} ${CYAN}Reset verified catalog${RESET}     ${YELLOW}⚠ destructive${RESET} ${DIM}— wipe catalog & re-seed${RESET}"
    echo -e "  ${DIM}  3)${RESET} ${CYAN}Re-ingest knowledge bases${RESET}  ${DIM}— rebuild ChromaDB chunks${RESET}"
    echo -e "  ${DIM}  0)${RESET} ${CYAN}Back${RESET}"
    _submenu_prompt
    local c; read -r c; c="${c:-0}"
    case "$c" in
      1) update_catalog ;;
      2) reset_catalog ;;
      3) reingest_knowledge_bases ;;
      0) return 0 ;;
      *) echo -e "  ${SYM_WARN}  ${YELLOW}Invalid selection.${RESET}" ;;
    esac
  done
}

auto_update_menu() {
  while true; do
    echo ""
    echo -e "  ${VIOLET}┌─${RESET} ${BOLD}${WHITE}AUTO UPDATE${RESET} ${DIM}─────────────────────────────────────${RESET}"
    echo -e "  ${VIOLET}└──────────────────────────────────────────────${RESET}"
    echo ""

    # Show current schedule inline so the user knows what's installed.
    if command -v crontab &>/dev/null && crontab -l 2>/dev/null | grep -Fq "$CRON_MARKER"; then
      local entry
      entry=$(crontab -l 2>/dev/null | grep -F "$CRON_MARKER" | head -1 | awk '{print $1, $2, $3, $4, $5}')
      echo -e "  ${SYM_CHECK}  ${DIM}Active schedule:${RESET} ${CYAN}${entry}${RESET}"
    else
      echo -e "  ${DIM}     No auto-update schedule installed.${RESET}"
    fi
    echo ""

    echo -e "  ${DIM}  1)${RESET} ${CYAN}Schedule auto-updates${RESET}   ${DIM}— install/replace cron entry${RESET}"
    echo -e "  ${DIM}  2)${RESET} ${CYAN}Remove schedule${RESET}         ${DIM}— delete the cron entry${RESET}"
    echo -e "  ${DIM}  3)${RESET} ${CYAN}Run auto-update now${RESET}     ${DIM}— execute the cron flow once${RESET}"
    echo -e "  ${DIM}  4)${RESET} ${CYAN}View auto-update log${RESET}    ${DIM}— last 80 lines of ${AUTO_UPDATE_LOG}${RESET}"
    echo -e "  ${DIM}  0)${RESET} ${CYAN}Back${RESET}"
    _submenu_prompt
    local c; read -r c; c="${c:-0}"
    case "$c" in
      1) setup_cron ;;
      2) remove_cron ;;
      3) run_auto_update_now ;;
      4) view_auto_update_log ;;
      0) return 0 ;;
      *) echo -e "  ${SYM_WARN}  ${YELLOW}Invalid selection.${RESET}" ;;
    esac
  done
}

main_menu() {
  while true; do
    echo ""
    echo -e "  ${SYM_NEURAL}  ${BOLD}${WHITE}Main Menu${RESET}"
    echo ""
    echo -e "  ${DIM}  1)${RESET} ${CYAN}Monitor${RESET}       ${DIM}— status, logs, diagnostics${RESET}"
    echo -e "  ${DIM}  2)${RESET} ${CYAN}Deploy${RESET}        ${DIM}— repair, redeploy, upgrade, setup${RESET}"
    echo -e "  ${DIM}  3)${RESET} ${CYAN}Catalog${RESET}       ${DIM}— update, reset, re-ingest${RESET}"
    echo -e "  ${DIM}  4)${RESET} ${CYAN}Auto update${RESET}   ${DIM}— schedule and run cron updates${RESET}"
    echo -e "  ${DIM}  0)${RESET} ${CYAN}Exit${RESET}"
    echo ""
    echo -ne "  ${SYM_ARROW}  Select ${DIM}[0]${RESET}: "
    local c; read -r c; c="${c:-0}"
    case "$c" in
      1) monitor_menu ;;
      2) deploy_menu ;;
      3) catalog_menu ;;
      4) auto_update_menu ;;
      0) echo ""; return 0 ;;
      *) echo -e "  ${SYM_WARN}  ${YELLOW}Invalid selection.${RESET}" ;;
    esac
  done
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
      scan_and_upgrade
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
    --reset-catalog|reset-catalog)
      show_banner
      preflight
      reset_catalog
      echo ""
      exit 0
      ;;
    --reingest|reingest)
      show_banner
      preflight
      reingest_knowledge_bases
      echo ""
      exit 0
      ;;
    --reset-email|reset-email)
      show_banner
      reset_email
      echo ""
      exit 0
      ;;
    --cron-setup|cron-setup)
      show_banner
      preflight
      setup_cron
      echo ""
      exit 0
      ;;
    --cron-remove|cron-remove)
      show_banner
      remove_cron
      echo ""
      exit 0
      ;;
    --auto-update|auto-update)
      # Non-interactive: no banner, no preflight section noise — log-only.
      auto_update
      exit $?
      ;;
    --help|-h|help)
      echo ""
      echo -e "  ${BOLD}Usage:${RESET} ./setup.sh [command]"
      echo ""
      echo -e "  ${BOLD}With no arguments:${RESET}"
      echo -e "    First run launches interactive setup. On an existing deployment,"
      echo -e "    re-running opens a menu with 4 sections — Monitor, Deploy,"
      echo -e "    Catalog, Auto update."
      echo ""
      echo -e "  ${BOLD}Direct shortcuts (skip the menu):${RESET}"
      echo -e "    ${CYAN}--repair${RESET}         Diagnose and fix a broken deployment"
      echo -e "    ${CYAN}--upgrade${RESET}        Scan origin for new code & catalog, apply what's outdated"
      echo -e "    ${CYAN}--redeploy${RESET}       Rebuild and restart from current code (no git pull)"
      echo -e "    ${CYAN}--seed${RESET}           Update verified catalog with new seed data"
      echo -e "    ${CYAN}--reset-catalog${RESET}  Wipe catalog metadata and re-seed (preserves underlying entities)"
      echo -e "    ${CYAN}--reingest${RESET}       Re-ingest all knowledge base content into ChromaDB"
      echo -e "    ${CYAN}--reset-email${RESET}    Reconfigure email provider (SMTP or Resend)"
      echo -e "    ${CYAN}--cron-setup${RESET}     Schedule automated upgrades via crontab"
      echo -e "    ${CYAN}--cron-remove${RESET}    Remove the scheduled auto-update entry"
      echo -e "    ${CYAN}--auto-update${RESET}    Non-interactive upgrade (used by cron, logs to .auto_update.log)"
      echo -e "    ${CYAN}--help${RESET}           Show this help"
      echo ""
      exit 0
      ;;
  esac

  show_banner
  preflight

  # If there's an existing deployment, offer mode selection
  if detect_deployment; then
    # show_banner already populated CODE_VERSION_* / CATALOG_VERSION_*. If
    # anything's outdated, prompt right here so the user doesn't have to
    # navigate a menu to discover what they already saw at the top.
    local code_outdated=0 cat_outdated=0
    is_newer "$CODE_VERSION_LATEST"    "$CODE_VERSION_LOCAL"    && code_outdated=1
    is_newer "$CATALOG_VERSION_LATEST" "$CATALOG_VERSION_LOCAL" && cat_outdated=1

    if [[ $code_outdated -eq 1 || $cat_outdated -eq 1 ]]; then
      echo ""
      local what
      if [[ $code_outdated -eq 1 && $cat_outdated -eq 1 ]]; then
        what="Code and catalog are out of date"
      elif [[ $code_outdated -eq 1 ]]; then
        what="Code is out of date"
      else
        what="Catalog is out of date"
      fi
      echo -e "  ${SYM_NEURAL}  ${BOLD}${what}.${RESET}"
      echo -ne "  ${SYM_ARROW}  Upgrade now? ${DIM}[Y/n]${RESET}: "
      local upgrade_ans
      read -r upgrade_ans
      if [[ ! "$upgrade_ans" =~ ^[Nn] ]]; then
        scan_and_upgrade
        echo ""
        exit 0
      fi
    fi

    echo ""
    echo -e "  ${SYM_NEURAL}  ${BOLD}Existing deployment detected.${RESET}"
    main_menu
    exit 0
  fi

  configure_env
  launch_services
  bootstrap
  verify
  finale
}

main "$@"
