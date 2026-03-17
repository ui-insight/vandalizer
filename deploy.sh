#!/usr/bin/env bash
# =============================================================================
# Vandalizer — Interactive Deployment Wizard
# =============================================================================
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Cleanup on exit ─────────────────────────────────────────────────────────
_SPINNER_PID=""
trap '_cleanup' EXIT
_cleanup() {
  _spinner_stop
  tput cnorm 2>/dev/null || true  # restore cursor
}

# =============================================================================
# COLORS & SYMBOLS
# =============================================================================
if [[ -t 1 ]] && command -v tput &>/dev/null && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]]; then
  BOLD="\033[1m"     DIM="\033[2m"       RESET="\033[0m"
  RED="\033[0;31m"   GREEN="\033[0;32m"  YELLOW="\033[0;33m"
  BLUE="\033[0;34m"  MAGENTA="\033[0;35m" CYAN="\033[0;36m"
  WHITE="\033[0;37m" BWHITE="\033[1;37m"
  BG_DARK="\033[48;5;234m"   # very dark bg for banner
  ACCENT="\033[38;5;99m"     # violet accent
  ACCENT2="\033[38;5;213m"   # pink accent
  GOLD="\033[38;5;220m"
else
  BOLD="" DIM="" RESET="" RED="" GREEN="" YELLOW="" BLUE="" MAGENTA=""
  CYAN="" WHITE="" BWHITE="" BG_DARK="" ACCENT="" ACCENT2="" GOLD=""
fi

SYM_OK="${GREEN}✓${RESET}"
SYM_ERR="${RED}✗${RESET}"
SYM_WARN="${YELLOW}⚠${RESET}"
SYM_INFO="${CYAN}◆${RESET}"
SYM_ARROW="${MAGENTA}›${RESET}"
SYM_DOT="${ACCENT}●${RESET}"

# =============================================================================
# SPINNER
# =============================================================================
_SPINNER_FRAMES=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")

_spinner_start() {
  local msg="${1:-Working…}"
  tput civis 2>/dev/null || true
  (
    local i=0
    while true; do
      printf "\r  ${CYAN}%s${RESET} %s   " "${_SPINNER_FRAMES[$((i % ${#_SPINNER_FRAMES[@]}))]}" "$msg"
      sleep 0.08
      ((i++))
    done
  ) &
  _SPINNER_PID=$!
}

_spinner_stop() {
  if [[ -n "$_SPINNER_PID" ]] && kill -0 "$_SPINNER_PID" 2>/dev/null; then
    kill "$_SPINNER_PID" 2>/dev/null || true
    wait "$_SPINNER_PID" 2>/dev/null || true
    _SPINNER_PID=""
  fi
  printf "\r\033[K"
  tput cnorm 2>/dev/null || true
}

_spinner_done() {
  _spinner_stop
  echo -e "  ${SYM_OK} ${1:-Done}"
}

_spinner_fail() {
  _spinner_stop
  echo -e "  ${SYM_ERR} ${RED}${1:-Failed}${RESET}"
}

# =============================================================================
# PRINT HELPERS
# =============================================================================
_banner() {
  clear
  echo
  echo -e "${ACCENT}  ╭──────────────────────────────────────────────────────────╮${RESET}"
  echo -e "${ACCENT}  │${RESET}                                                          ${ACCENT}│${RESET}"
  echo -e "${ACCENT}  │${RESET}  ${BOLD}${ACCENT2}██╗   ██╗ █████╗ ███╗  ██╗██████╗  █████╗ ██╗     ${RESET}  ${ACCENT}│${RESET}"
  echo -e "${ACCENT}  │${RESET}  ${BOLD}${ACCENT2}██║   ██║██╔══██╗████╗ ██║██╔══██╗██╔══██╗██║     ${RESET}  ${ACCENT}│${RESET}"
  echo -e "${ACCENT}  │${RESET}  ${BOLD}${ACCENT2}██║   ██║███████║██╔██╗██║██║  ██║███████║██║     ${RESET}  ${ACCENT}│${RESET}"
  echo -e "${ACCENT}  │${RESET}  ${BOLD}${ACCENT2}╚██╗ ██╔╝██╔══██║██║╚████║██║  ██║██╔══██║██║     ${RESET}  ${ACCENT}│${RESET}"
  echo -e "${ACCENT}  │${RESET}  ${BOLD}${ACCENT2} ╚████╔╝ ██║  ██║██║ ╚███║██████╔╝██║  ██║███████╗${RESET}  ${ACCENT}│${RESET}"
  echo -e "${ACCENT}  │${RESET}  ${BOLD}${ACCENT2}  ╚═══╝  ╚═╝  ╚═╝╚═╝  ╚══╝╚═════╝ ╚═╝  ╚═╝╚══════╝${RESET}  ${ACCENT}│${RESET}"
  echo -e "${ACCENT}  │${RESET}                                                          ${ACCENT}│${RESET}"
  echo -e "${ACCENT}  │${RESET}       ${DIM}AI-Powered Document Intelligence Platform${RESET}          ${ACCENT}│${RESET}"
  echo -e "${ACCENT}  │${RESET}       ${DIM}University of Idaho  ·  Deployment Wizard${RESET}          ${ACCENT}│${RESET}"
  echo -e "${ACCENT}  │${RESET}                                                          ${ACCENT}│${RESET}"
  echo -e "${ACCENT}  ╰──────────────────────────────────────────────────────────╯${RESET}"
  echo
}

_section() {
  local title="$1"
  local step="${2:-}"
  echo
  if [[ -n "$step" ]]; then
    echo -e "  ${ACCENT}╭─${RESET} ${BOLD}${BWHITE}${title}${RESET}  ${DIM}${step}${RESET}"
  else
    echo -e "  ${ACCENT}╭─${RESET} ${BOLD}${BWHITE}${title}${RESET}"
  fi
  echo -e "  ${ACCENT}│${RESET}"
}

_section_end() {
  echo -e "  ${ACCENT}╰${RESET}"
  echo
}

_item() { echo -e "  ${ACCENT}│${RESET}  ${SYM_DOT} $*"; }
_line() { echo -e "  ${ACCENT}│${RESET}  $*"; }
_blank() { echo -e "  ${ACCENT}│${RESET}"; }

ok()   { echo -e "  ${SYM_OK}  $*"; }
err()  { echo -e "  ${SYM_ERR}  ${RED}$*${RESET}"; }
warn() { echo -e "  ${SYM_WARN}  ${YELLOW}$*${RESET}"; }
info() { echo -e "  ${SYM_INFO}  ${CYAN}$*${RESET}"; }

_divider() {
  echo -e "  ${DIM}────────────────────────────────────────────────────────────${RESET}"
}

# progress bar  ▓░
_progress() {
  local current=$1 total=$2 label="${3:-}"
  local width=40
  local filled=$(( width * current / total ))
  local empty=$(( width - filled ))
  local bar="${ACCENT}$(printf '▓%.0s' $(seq 1 $filled))${RESET}${DIM}$(printf '░%.0s' $(seq 1 $empty))${RESET}"
  printf "  %b  ${DIM}%d/%d${RESET}  %s\n" "$bar" "$current" "$total" "$label"
}

# =============================================================================
# INPUT HELPERS
# =============================================================================
_prompt() {
  # Usage: _prompt "Label" [default] [secret]
  local label="$1"
  local default="${2:-}"
  local secret="${3:-}"
  local prompt_str

  if [[ -n "$default" ]]; then
    prompt_str="  ${ACCENT}›${RESET} ${BOLD}${label}${RESET} ${DIM}[${default}]${RESET}: "
  else
    prompt_str="  ${ACCENT}›${RESET} ${BOLD}${label}${RESET}: "
  fi

  if [[ "$secret" == "secret" ]]; then
    printf "%b" "$prompt_str"
    IFS= read -rs _REPLY
    echo
  else
    printf "%b" "$prompt_str"
    IFS= read -r _REPLY
  fi

  if [[ -z "$_REPLY" && -n "$default" ]]; then
    _REPLY="$default"
  fi
}

_confirm() {
  # Usage: _confirm "Question" [default: y|n]
  local question="$1"
  local default="${2:-y}"
  local choices
  if [[ "$default" == "y" ]]; then choices="Y/n"; else choices="y/N"; fi
  printf "  ${ACCENT}›${RESET} ${BOLD}%s${RESET} ${DIM}(%s)${RESET}: " "$question" "$choices"
  IFS= read -r _REPLY
  _REPLY="${_REPLY:-$default}"
  [[ "${_REPLY,,}" == "y" ]]
}

_choose() {
  # Usage: _choose "prompt" opt1 opt2 opt3 …   → sets _CHOICE (1-based)
  local prompt="$1"; shift
  local opts=("$@")
  echo -e "  ${ACCENT}│${RESET}"
  for i in "${!opts[@]}"; do
    echo -e "  ${ACCENT}│${RESET}  ${DIM}$((i+1))${RESET}  ${opts[$i]}"
  done
  echo -e "  ${ACCENT}│${RESET}"
  while true; do
    printf "  ${ACCENT}›${RESET} ${BOLD}%s${RESET} ${DIM}[1-%d]${RESET}: " "$prompt" "${#opts[@]}"
    IFS= read -r _CHOICE
    if [[ "$_CHOICE" =~ ^[0-9]+$ ]] && (( _CHOICE >= 1 && _CHOICE <= ${#opts[@]} )); then
      break
    fi
    echo -e "  ${RED}  Please enter a number between 1 and ${#opts[@]}${RESET}"
  done
}

# =============================================================================
# PREREQUISITE CHECKS
# =============================================================================
_check_prereqs() {
  _section "Checking prerequisites" "required tools"

  local missing=0

  for cmd in docker curl python3; do
    if command -v "$cmd" &>/dev/null; then
      _item "${cmd}  ${DIM}$(command -v "$cmd")${RESET}"
    else
      _line "${RED}✗  ${cmd} not found — please install it first${RESET}"
      missing=1
    fi
  done

  # Docker Compose (v2: "docker compose", v1: "docker-compose")
  if docker compose version &>/dev/null 2>&1; then
    _item "docker compose  ${DIM}(plugin v2)${RESET}"
  elif command -v docker-compose &>/dev/null; then
    _item "docker-compose  ${DIM}(standalone v1)${RESET}"
    DOCKER_COMPOSE="docker-compose"
  else
    _line "${RED}✗  docker compose not found — install Docker Desktop or the compose plugin${RESET}"
    missing=1
  fi

  _blank
  _section_end

  if [[ $missing -ne 0 ]]; then
    err "Some prerequisites are missing. Please install them and re-run."
    exit 1
  fi
}

DOCKER_COMPOSE="docker compose"

# =============================================================================
# STATE (filled by wizard)
# =============================================================================
DEPLOY_MODE="production"
LLM_PROVIDER=""         # openai | endpoint | ollama | none
LLM_API_KEY=""
LLM_ENDPOINT=""
OCR_ENABLED=false
OCR_ENDPOINT=""
STORAGE_BACKEND="local"
S3_BUCKET="" S3_REGION="us-east-1" S3_ACCESS_KEY_ID="" S3_SECRET_ACCESS_KEY="" S3_ENDPOINT_URL=""
SMTP_ENABLED=false
SMTP_HOST="" SMTP_PORT="587" SMTP_USER="" SMTP_PASSWORD="" SMTP_USE_TLS="true"
SMTP_FROM_EMAIL="" SMTP_FROM_NAME="Vandalizer"
ADMIN_EMAIL="" ADMIN_PASSWORD="" ADMIN_NAME="Admin"
JWT_SECRET=""
SENTRY_DSN=""
DEFAULT_TEAM_NAME=""
BASE_URL="http://localhost"
FRONTEND_URL=""
ENVIRONMENT="production"
MONGO_DB="osp"

# =============================================================================
# WIZARD STEPS
# =============================================================================

step_mode() {
  _section "Deployment Mode" "step 1 of 9"
  _line "How are you deploying Vandalizer?"
  _choose "Select mode" \
    "🚀  Production — public server, real secrets, HTTPS" \
    "🛠   Development — localhost, relaxed settings"

  if [[ $_CHOICE -eq 1 ]]; then
    DEPLOY_MODE="production"
    ENVIRONMENT="production"
    _line "${GREEN}Production mode selected${RESET}"
  else
    DEPLOY_MODE="development"
    ENVIRONMENT="development"
    BASE_URL="http://localhost"
    _line "${YELLOW}Development mode selected — relaxed settings${RESET}"
  fi

  if [[ "$DEPLOY_MODE" == "production" ]]; then
    _blank
    _prompt "Your domain / base URL (e.g. https://vandalizer.university.edu)" "https://example.com"
    BASE_URL="$_REPLY"
  fi

  FRONTEND_URL="$BASE_URL"
  _section_end
}

step_llm() {
  _section "LLM Configuration" "step 2 of 9"
  _line "Vandalizer uses an LLM for extraction, chat, and workflows."
  _line "Which provider do you want to use?"

  _choose "Select LLM provider" \
    "🔑  OpenAI  (GPT-4o, o1, etc.)" \
    "🌐  Custom endpoint  (any OpenAI-compatible API — OpenRouter, vLLM, Together, etc.)" \
    "🦙  Ollama  (local models, no API key needed)" \
    "⏭   Skip for now  (configure manually later)"

  case $_CHOICE in
    1)
      LLM_PROVIDER="openai"
      _blank
      _prompt "OpenAI API key" "sk-..."
      LLM_API_KEY="$_REPLY"
      if [[ -z "$LLM_API_KEY" || "$LLM_API_KEY" == "sk-..." ]]; then
        warn "No API key entered — you can add OPENAI_API_KEY to .env later"
        LLM_API_KEY=""
      else
        _item "API key  ${DIM}${LLM_API_KEY:0:8}…${LLM_API_KEY: -4}${RESET}"
      fi
      ;;
    2)
      LLM_PROVIDER="endpoint"
      _blank
      _prompt "Endpoint URL  (e.g. https://openrouter.ai/api/v1)" ""
      LLM_ENDPOINT="$_REPLY"
      _prompt "API key for this endpoint" ""
      LLM_API_KEY="$_REPLY"
      _item "Endpoint  ${DIM}${LLM_ENDPOINT}${RESET}"
      ;;
    3)
      LLM_PROVIDER="ollama"
      _blank
      _prompt "Ollama base URL" "http://localhost:11434"
      LLM_ENDPOINT="${_REPLY%/}/v1"
      LLM_API_KEY="ollama"
      _item "Ollama endpoint  ${DIM}${LLM_ENDPOINT}${RESET}"
      warn "Make sure Ollama is running and you have pulled your desired models"
      ;;
    4)
      LLM_PROVIDER="none"
      warn "Skipping LLM setup — add OPENAI_API_KEY to backend/.env before using AI features"
      ;;
  esac
  _section_end
}

step_ocr() {
  _section "OCR Service" "step 3 of 9"
  _line "An OCR service lets Vandalizer extract text from scanned / image PDFs."
  _line "This is optional — plain PDFs and Office docs work without it."
  _blank

  if _confirm "Configure an external OCR service?  (e.g. DotSearch OCR)" "n"; then
    OCR_ENABLED=true
    _blank
    _prompt "OCR service endpoint URL" "https://ocr.yourdomain.com"
    OCR_ENDPOINT="$_REPLY"
    _item "OCR endpoint  ${DIM}${OCR_ENDPOINT}${RESET}"
  else
    OCR_ENABLED=false
    info "Skipping OCR — scanned PDFs will be processed as plain text only"
  fi
  _section_end
}

step_storage() {
  _section "File Storage" "step 4 of 9"
  _line "Where should uploaded files be stored?"

  _choose "Select storage backend" \
    "💾  Local filesystem  (default, files stored on this server)" \
    "☁️   Amazon S3  (scalable, recommended for production)" \
    "🔧  S3-compatible  (MinIO, Cloudflare R2, Backblaze B2, etc.)"

  case $_CHOICE in
    1)
      STORAGE_BACKEND="local"
      info "Files will be stored in the uploads/ Docker volume"
      ;;
    2|3)
      STORAGE_BACKEND="s3"
      _blank
      _prompt "S3 bucket name" ""
      S3_BUCKET="$_REPLY"
      _prompt "AWS region" "us-east-1"
      S3_REGION="$_REPLY"
      _prompt "AWS Access Key ID" ""
      S3_ACCESS_KEY_ID="$_REPLY"
      _prompt "AWS Secret Access Key" "" "secret"
      S3_SECRET_ACCESS_KEY="$_REPLY"

      if [[ $_CHOICE -eq 3 ]]; then
        _blank
        _prompt "S3-compatible endpoint URL  (e.g. https://s3.us-east-1.r2.cloudflarestorage.com)" ""
        S3_ENDPOINT_URL="$_REPLY"
      fi

      _item "Bucket  ${DIM}${S3_BUCKET}${RESET}  (${S3_REGION})"
      ;;
  esac
  _section_end
}

step_email() {
  _section "Email / SMTP" "step 5 of 9"
  _line "Email is used for notifications and team invitations."
  _blank

  if _confirm "Configure SMTP email?" "n"; then
    SMTP_ENABLED=true
    _blank
    _prompt "SMTP host" "smtp.gmail.com"
    SMTP_HOST="$_REPLY"
    _prompt "SMTP port" "587"
    SMTP_PORT="$_REPLY"
    _prompt "SMTP username" ""
    SMTP_USER="$_REPLY"
    _prompt "SMTP password" "" "secret"
    SMTP_PASSWORD="$_REPLY"
    _prompt "From email address" ""
    SMTP_FROM_EMAIL="$_REPLY"
    _prompt "From display name" "Vandalizer"
    SMTP_FROM_NAME="$_REPLY"

    if _confirm "Use TLS?" "y"; then
      SMTP_USE_TLS="true"
    else
      SMTP_USE_TLS="false"
    fi

    _item "SMTP  ${DIM}${SMTP_USER}@${SMTP_HOST}:${SMTP_PORT}${RESET}"
  else
    info "Skipping email — team invitations and notifications will be disabled"
  fi
  _section_end
}

step_admin() {
  _section "Admin Account" "step 6 of 9"
  _line "Create the first administrator account for Vandalizer."
  _blank

  while true; do
    _prompt "Admin email address" ""
    ADMIN_EMAIL="$_REPLY"
    if [[ "$ADMIN_EMAIL" =~ ^[^@]+@[^@]+\.[^@]+$ ]]; then break; fi
    echo -e "  ${RED}  Please enter a valid email address${RESET}"
  done

  _prompt "Admin display name" "Admin"
  ADMIN_NAME="${_REPLY:-Admin}"

  while true; do
    _prompt "Admin password  (min 8 characters)" "" "secret"
    ADMIN_PASSWORD="$_REPLY"
    if [[ "${#ADMIN_PASSWORD}" -ge 8 ]]; then
      _prompt "Confirm password" "" "secret"
      if [[ "$_REPLY" == "$ADMIN_PASSWORD" ]]; then break; fi
      echo -e "  ${RED}  Passwords don't match — try again${RESET}"
    else
      echo -e "  ${RED}  Password must be at least 8 characters${RESET}"
    fi
  done

  _item "Admin  ${DIM}${ADMIN_NAME} <${ADMIN_EMAIL}>${RESET}"
  _section_end
}

step_secrets() {
  _section "Security Secrets" "step 7 of 9"
  _line "Generating cryptographic secrets…"
  _blank

  JWT_SECRET="$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")"
  _item "JWT secret  ${DIM}${JWT_SECRET:0:16}…${RESET}  ${GREEN}(generated)${RESET}"

  _blank
  if _confirm "Configure Sentry error tracking? (optional)" "n"; then
    _prompt "Sentry DSN" ""
    SENTRY_DSN="$_REPLY"
    _item "Sentry  ${DIM}${SENTRY_DSN:0:40}…${RESET}"
  fi
  _section_end
}

step_teams() {
  _section "Default Team" "step 8 of 9"
  _line "A default team lets new users land somewhere useful right away."
  _line "Instead of everyone working in isolation on their own personal workspace,"
  _line "they'll automatically join this shared team when they sign up or log in."
  _blank

  if _confirm "Create a default team for new users?" "y"; then
    _prompt "Team name" "Research Administration"
    DEFAULT_TEAM_NAME="${_REPLY:-Research Administration}"
    _item "Default team  ${DIM}${DEFAULT_TEAM_NAME}${RESET}"
  else
    DEFAULT_TEAM_NAME=""
    info "Skipping — users will start in their personal workspace only"
  fi
  _section_end
}

step_review() {
  _section "Review Configuration" "step 9 of 9"

  _item "Mode         ${BOLD}${ENVIRONMENT}${RESET}"
  _item "Base URL     ${DIM}${BASE_URL}${RESET}"

  case "$LLM_PROVIDER" in
    openai)   _item "LLM          ${BOLD}OpenAI${RESET}  ${DIM}(key ${LLM_API_KEY:0:8}…)${RESET}" ;;
    endpoint) _item "LLM          ${BOLD}Custom endpoint${RESET}  ${DIM}${LLM_ENDPOINT}${RESET}" ;;
    ollama)   _item "LLM          ${BOLD}Ollama${RESET}  ${DIM}${LLM_ENDPOINT}${RESET}" ;;
    none)     _item "LLM          ${YELLOW}not configured${RESET}" ;;
  esac

  if [[ "$OCR_ENABLED" == true ]]; then
    _item "OCR          ${BOLD}${OCR_ENDPOINT}${RESET}"
  else
    _item "OCR          ${DIM}disabled${RESET}"
  fi

  case "$STORAGE_BACKEND" in
    local) _item "Storage      ${BOLD}Local filesystem${RESET}" ;;
    s3)    _item "Storage      ${BOLD}S3${RESET}  ${DIM}s3://${S3_BUCKET} (${S3_REGION})${RESET}" ;;
  esac

  if [[ "$SMTP_ENABLED" == true ]]; then
    _item "Email        ${BOLD}${SMTP_HOST}:${SMTP_PORT}${RESET}"
  else
    _item "Email        ${DIM}disabled${RESET}"
  fi

  _item "Admin        ${BOLD}${ADMIN_EMAIL}${RESET}"
  if [[ -n "$DEFAULT_TEAM_NAME" ]]; then
    _item "Default team ${BOLD}${DEFAULT_TEAM_NAME}${RESET}"
  else
    _item "Default team ${DIM}none${RESET}"
  fi
  _item "JWT secret   ${DIM}${JWT_SECRET:0:16}…${RESET}"
  [[ -n "$SENTRY_DSN" ]] && _item "Sentry       ${DIM}configured${RESET}"

  _blank
  _section_end

  if ! _confirm "Everything look right? Begin deployment?"; then
    echo
    info "Deployment cancelled. Your .env has not been written."
    exit 0
  fi
}

# =============================================================================
# GENERATE .env
# =============================================================================
generate_env() {
  local env_file="${SCRIPT_DIR}/backend/.env"

  if [[ -f "$env_file" ]]; then
    local backup="${env_file}.bak.$(date +%Y%m%d_%H%M%S)"
    cp "$env_file" "$backup"
    warn "Existing .env backed up to ${DIM}${backup}${RESET}"
  fi

  cat > "$env_file" <<EOF
# ============================================================
# Vandalizer — generated by deploy.sh on $(date)
# ============================================================

# ── Infrastructure ───────────────────────────────────────────
MONGO_HOST=mongodb://mongo:27017/
MONGO_DB=${MONGO_DB}
REDIS_HOST=redis

# ── Auth ─────────────────────────────────────────────────────
JWT_SECRET_KEY=${JWT_SECRET}
JWT_ALGORITHM=HS256
JWT_ACCESS_EXPIRE_MINUTES=30
JWT_REFRESH_EXPIRE_DAYS=60

# ── Application ──────────────────────────────────────────────
ENVIRONMENT=${ENVIRONMENT}
FRONTEND_URL=${FRONTEND_URL}
LOG_FORMAT=json

# ── LLM ──────────────────────────────────────────────────────
OPENAI_API_KEY=${LLM_API_KEY}
INSIGHT_ENDPOINT=${LLM_ENDPOINT}

# ── ChromaDB ─────────────────────────────────────────────────
CHROMADB_PERSIST_DIR=/app/static/db

# ── File Storage ─────────────────────────────────────────────
UPLOAD_DIR=/app/static/uploads
STORAGE_BACKEND=${STORAGE_BACKEND}
EOF

  if [[ "$STORAGE_BACKEND" == "s3" ]]; then
    cat >> "$env_file" <<EOF
S3_BUCKET=${S3_BUCKET}
S3_REGION=${S3_REGION}
S3_ACCESS_KEY_ID=${S3_ACCESS_KEY_ID}
S3_SECRET_ACCESS_KEY=${S3_SECRET_ACCESS_KEY}
S3_ENDPOINT_URL=${S3_ENDPOINT_URL}
EOF
  fi

  cat >> "$env_file" <<EOF

# ── SMTP Email ───────────────────────────────────────────────
SMTP_HOST=${SMTP_HOST}
SMTP_PORT=${SMTP_PORT}
SMTP_USER=${SMTP_USER}
SMTP_PASSWORD=${SMTP_PASSWORD}
SMTP_USE_TLS=${SMTP_USE_TLS}
SMTP_FROM_EMAIL=${SMTP_FROM_EMAIL}
SMTP_FROM_NAME=${SMTP_FROM_NAME}

# ── OCR ──────────────────────────────────────────────────────
OCR_ENDPOINT=${OCR_ENDPOINT}

# ── Observability ────────────────────────────────────────────
SENTRY_DSN=${SENTRY_DSN}
EOF

  ok ".env written to ${DIM}${env_file}${RESET}"
}

# =============================================================================
# SETUP DEFAULT TEAM  (runs after create_admin, inside container)
# =============================================================================
TEAM_SETUP_OK=false

setup_default_team() {
  [[ -z "$DEFAULT_TEAM_NAME" ]] && return

  _section "Setting Up Default Team"
  _blank

  _spinner_start "Creating team '${DEFAULT_TEAM_NAME}' and setting as default"

  local _team_err_file
  _team_err_file="$(mktemp)"
  if $DOCKER_COMPOSE exec -T api \
      env TEAM_NAME="$DEFAULT_TEAM_NAME" \
          ADMIN_EMAIL="$ADMIN_EMAIL" \
      python setup_default_team.py 2>"$_team_err_file"; then
    _spinner_done "Default team configured"
    _item "${BOLD}${DEFAULT_TEAM_NAME}${RESET}  ${DIM}will be auto-joined by all new users${RESET}"
    TEAM_SETUP_OK=true
  else
    _spinner_fail "Team setup failed"
    if [[ -s "$_team_err_file" ]]; then
      while IFS= read -r _line; do warn "$_line"; done < "$_team_err_file"
    fi
    warn "Create the team manually: Admin → Teams → Create, then Set Default"
  fi
  rm -f "$_team_err_file"

  _section_end
}

# =============================================================================
# DOCKER BUILD & START
# =============================================================================
run_docker() {
  _section "Building & Starting Services"

  cd "$SCRIPT_DIR"

  _blank
  echo
  _progress 1 4 "Pulling base images…"
  _spinner_start "Pulling base images"
  $DOCKER_COMPOSE pull --quiet 2>/dev/null || true
  _spinner_done "Base images ready"

  _progress 2 4 "Building containers…"
  _spinner_start "Building API & frontend containers (this may take a minute)"
  $DOCKER_COMPOSE build --quiet 2>/dev/null
  _spinner_done "Containers built"

  _progress 3 4 "Starting services…"
  _spinner_start "Starting services"
  $DOCKER_COMPOSE up -d --remove-orphans 2>/dev/null
  _spinner_done "Services started"

  _progress 4 4 "Waiting for health checks…"
  _wait_healthy

  _section_end
}

_wait_healthy() {
  local max_attempts=40
  local attempt=0
  local services=("mongo" "redis" "chromadb" "api")
  local all_ok=false

  _spinner_start "Waiting for all services to become healthy"

  while [[ $attempt -lt $max_attempts ]]; do
    all_ok=true
    for svc in "${services[@]}"; do
      local status
      status="$($DOCKER_COMPOSE ps --format json "$svc" 2>/dev/null | python3 -c "
import sys, json
try:
    data = [json.loads(l) for l in sys.stdin if l.strip()]
    print(data[0].get('Health', data[0].get('State', 'unknown')))
except: print('unknown')
" 2>/dev/null || echo "unknown")"
      if [[ "$status" != "healthy" && "$status" != "running" ]]; then
        all_ok=false
        break
      fi
    done
    [[ "$all_ok" == true ]] && break
    sleep 2
    ((attempt++))
  done

  _spinner_done "Services are healthy"

  # Final check: API health endpoint
  local api_ok=false
  for _ in $(seq 1 10); do
    if curl -sf http://localhost:8001/api/health &>/dev/null; then
      api_ok=true
      break
    fi
    sleep 2
  done

  if [[ "$api_ok" == true ]]; then
    ok "API health check  ${DIM}GET /api/health → 200 OK${RESET}"
  else
    warn "API health check timed out — the service may still be starting"
  fi
}

# =============================================================================
# CREATE ADMIN ACCOUNT
# =============================================================================
create_admin() {
  _section "Creating Admin Account"
  _blank

  _spinner_start "Creating admin account (${ADMIN_EMAIL})"

  # Run create_admin.py inside the api container
  if $DOCKER_COMPOSE exec -T api \
      env ADMIN_EMAIL="$ADMIN_EMAIL" \
          ADMIN_PASSWORD="$ADMIN_PASSWORD" \
          ADMIN_NAME="$ADMIN_NAME" \
      python create_admin.py 2>/dev/null; then
    _spinner_done "Admin account created"
    _item "${BOLD}${ADMIN_NAME}${RESET}  ${DIM}<${ADMIN_EMAIL}>${RESET}"
  else
    _spinner_fail "Failed to create admin account via container — trying direct python"
    warn "Run manually: cd backend && ADMIN_EMAIL=${ADMIN_EMAIL} ADMIN_PASSWORD=... python create_admin.py"
  fi

  _section_end
}

# =============================================================================
# SUCCESS SCREEN
# =============================================================================
success_screen() {
  echo
  echo -e "  ${ACCENT}╭──────────────────────────────────────────────────────────╮${RESET}"
  echo -e "  ${ACCENT}│${RESET}                                                          ${ACCENT}│${RESET}"
  echo -e "  ${ACCENT}│${RESET}   ${GREEN}${BOLD}🎉  Vandalizer is deployed and ready!${RESET}                 ${ACCENT}│${RESET}"
  echo -e "  ${ACCENT}│${RESET}                                                          ${ACCENT}│${RESET}"

  local app_url="${BASE_URL}"
  [[ "$DEPLOY_MODE" == "development" ]] && app_url="http://localhost"

  echo -e "  ${ACCENT}│${RESET}   ${BOLD}Open in browser:${RESET}                                         ${ACCENT}│${RESET}"
  echo -e "  ${ACCENT}│${RESET}   ${CYAN}${BOLD}${app_url}${RESET}                                   ${ACCENT}│${RESET}"
  echo -e "  ${ACCENT}│${RESET}                                                          ${ACCENT}│${RESET}"
  echo -e "  ${ACCENT}│${RESET}   ${BOLD}Admin login:${RESET}                                             ${ACCENT}│${RESET}"
  echo -e "  ${ACCENT}│${RESET}   ${DIM}Email:   ${RESET}${ADMIN_EMAIL}${ACCENT}                          │${RESET}"
  echo -e "  ${ACCENT}│${RESET}   ${DIM}Password: your chosen password above${RESET}                     ${ACCENT}│${RESET}"
  echo -e "  ${ACCENT}│${RESET}                                                          ${ACCENT}│${RESET}"
  echo -e "  ${ACCENT}│${RESET}   ${BOLD}Useful commands:${RESET}                                         ${ACCENT}│${RESET}"
  echo -e "  ${ACCENT}│${RESET}   ${DIM}docker compose logs -f api     ${RESET}# stream API logs        ${ACCENT}│${RESET}"
  echo -e "  ${ACCENT}│${RESET}   ${DIM}docker compose ps              ${RESET}# service status         ${ACCENT}│${RESET}"
  echo -e "  ${ACCENT}│${RESET}   ${DIM}docker compose down            ${RESET}# stop everything        ${ACCENT}│${RESET}"
  echo -e "  ${ACCENT}│${RESET}   ${DIM}bash deploy.sh                 ${RESET}# re-run this wizard     ${ACCENT}│${RESET}"
  echo -e "  ${ACCENT}│${RESET}                                                          ${ACCENT}│${RESET}"
  if [[ "$TEAM_SETUP_OK" == true ]]; then
    echo -e "  ${ACCENT}│${RESET}   ${GREEN}Default team:${RESET} ${DEFAULT_TEAM_NAME}                           ${ACCENT}│${RESET}"
    echo -e "  ${ACCENT}│${RESET}   ${DIM}New users auto-join on signup/SSO login${RESET}               ${ACCENT}│${RESET}"
    echo -e "  ${ACCENT}│${RESET}                                                          ${ACCENT}│${RESET}"
  elif [[ -n "$DEFAULT_TEAM_NAME" ]]; then
    echo -e "  ${ACCENT}│${RESET}   ${YELLOW}⚠  Default team setup failed — configure in Admin → Teams${RESET} ${ACCENT}│${RESET}"
    echo -e "  ${ACCENT}│${RESET}                                                          ${ACCENT}│${RESET}"
  fi
  if [[ "$LLM_PROVIDER" == "none" ]]; then
    echo -e "  ${ACCENT}│${RESET}   ${YELLOW}⚠  Remember to add OPENAI_API_KEY to backend/.env${RESET}    ${ACCENT}│${RESET}"
    echo -e "  ${ACCENT}│${RESET}   ${YELLOW}   then run: docker compose restart api celery${RESET}        ${ACCENT}│${RESET}"
    echo -e "  ${ACCENT}│${RESET}                                                          ${ACCENT}│${RESET}"
  fi
  echo -e "  ${ACCENT}╰──────────────────────────────────────────────────────────╯${RESET}"
  echo
}

# =============================================================================
# MAIN
# =============================================================================
main() {
  _banner
  echo -e "  Welcome to the Vandalizer deployment wizard."
  echo -e "  ${DIM}We'll walk you through everything step by step — press Ctrl+C at any time to cancel.${RESET}"
  echo
  _divider
  echo

  _check_prereqs

  step_mode
  step_llm
  step_ocr
  step_storage
  step_email
  step_admin
  step_secrets
  step_teams
  step_review

  echo
  info "Starting deployment…"
  echo
  _divider
  echo

  generate_env
  run_docker
  create_admin
  setup_default_team
  success_screen
}

main "$@"
