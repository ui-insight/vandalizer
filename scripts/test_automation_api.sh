#!/usr/bin/env bash
# ============================================================================
#  Vandalizer — Automation API Test Harness
#  Interactive CLI for exercising the automation trigger pipeline
#
#  Usage:
#    ./scripts/test_automation_api.sh                  Interactive mode
#    ./scripts/test_automation_api.sh --url http://..   Custom server
#
#  Environment:
#    VANDALIZER_URL        Server URL      (default: http://localhost:8001)
#    VANDALIZER_API_KEY    API key for trigger endpoint
#    VANDALIZER_EMAIL      Login email     (for CRUD operations)
#    VANDALIZER_PASSWORD   Login password
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
VIOLET='\033[38;5;141m'
BRIGHT_GREEN='\033[38;5;82m'
ORANGE='\033[38;5;208m'
DEEP_CYAN='\033[38;5;44m'

# Symbols
SYM_CHECK="${GREEN}✓${RESET}"
SYM_CROSS="${RED}✗${RESET}"
SYM_WARN="${YELLOW}⚠${RESET}"
SYM_ARROW="${CYAN}▸${RESET}"
SYM_DOT="${MAGENTA}●${RESET}"
SYM_BOLT="${ORANGE}⚡${RESET}"
SYM_KEY="${YELLOW}⚿${RESET}"
SYM_SEND="${DEEP_CYAN}➤${RESET}"

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
BASE_URL="${VANDALIZER_URL:-http://localhost:8001}"
API_KEY="${VANDALIZER_API_KEY:-}"
COOKIE_JAR=""      # path to curl cookie jar file
CSRF_TOKEN=""
LAST_RESPONSE=""
LAST_STATUS=""
TMP_DIR=""

# ---------------------------------------------------------------------------
# Parse CLI args
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url|--base-url) BASE_URL="$2"; shift 2 ;;
    --api-key)        API_KEY="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: $0 [--url URL] [--api-key KEY]"
      echo ""
      echo "Environment: VANDALIZER_URL, VANDALIZER_API_KEY, VANDALIZER_EMAIL, VANDALIZER_PASSWORD"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
cleanup() {
  [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]] && rm -rf "$TMP_DIR"
}
trap cleanup EXIT
TMP_DIR=$(mktemp -d)

typewriter() {
  local text="$1"
  local delay="${2:-0.015}"
  for (( i=0; i<${#text}; i++ )); do
    printf '%s' "${text:$i:1}"
    sleep "$delay"
  done
}

spin() {
  local pid=$1
  local label="${2:-Working}"
  local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
  local i=0
  while kill -0 "$pid" 2>/dev/null; do
    printf "\r  ${CYAN}${frames[$i]}${RESET}  ${DIM}%s${RESET}  " "$label"
    i=$(( (i + 1) % ${#frames[@]} ))
    sleep 0.08
  done
  wait "$pid" 2>/dev/null
  return $?
}

# Execute a curl command with a spinner
api_call() {
  local label="$1"
  shift
  curl -s -w "\n%{http_code}" "$@" > "${TMP_DIR}/response" 2>/dev/null &
  local pid=$!
  spin "$pid" "$label"
  wait "$pid" 2>/dev/null

  LAST_STATUS=$(tail -1 "${TMP_DIR}/response")
  LAST_RESPONSE=$(sed '$d' "${TMP_DIR}/response")

  if [[ "$LAST_STATUS" -ge 200 && "$LAST_STATUS" -lt 300 ]]; then
    printf "\r  ${SYM_CHECK}  %s  ${DIM}%s${RESET}\n" "$label" "$LAST_STATUS"
    return 0
  else
    printf "\r  ${SYM_CROSS}  %s  ${RED}%s${RESET}\n" "$label" "$LAST_STATUS"
    return 1
  fi
}

# Pretty-print JSON response
show_json() {
  local label="${1:-}"
  if [[ -n "$label" ]]; then
    echo -e "\n  ${BOLD}${label}${RESET}"
    echo -e "  ${DIM}$(printf '%.0s─' $(seq 1 ${#label}))${RESET}"
  fi
  if command -v python3 &>/dev/null; then
    echo "$LAST_RESPONSE" | python3 -m json.tool 2>/dev/null | while IFS= read -r line; do
      echo -e "  ${DIM}│${RESET}  $line"
    done
  else
    echo -e "  ${DIM}│${RESET}  $LAST_RESPONSE"
  fi
  echo ""
}

# Show a compact table from automation list JSON
show_automations_table() {
  local json="$LAST_RESPONSE"
  local count
  count=$(echo "$json" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

  if [[ "$count" == "0" ]]; then
    echo -e "\n  ${DIM}No automations found.${RESET}\n"
    return
  fi

  echo ""
  printf "  ${BOLD}%-26s  %-7s  %-14s  %-12s  %s${RESET}\n" "ID" "Status" "Trigger" "Action" "Name"
  echo -e "  ${DIM}$(printf '%.0s─' $(seq 1 80))${RESET}"

  echo "$json" | python3 -c "
import sys, json
for a in json.load(sys.stdin):
    enabled = '\033[38;5;114mon \033[0m' if a['enabled'] else '\033[38;5;203moff\033[0m'
    print(f\"  {a['id']:<26}  {enabled:<16}  {a['trigger_type']:<14}  {a['action_type']:<12}  {a['name']}\")
" 2>/dev/null
  echo ""
}

# Extract a field from the last JSON response
json_field() {
  echo "$LAST_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('$1',''))" 2>/dev/null
}

# Check if we have a valid session
has_session() {
  [[ -n "$COOKIE_JAR" && -f "$COOKIE_JAR" ]]
}

# Authenticated api_call: wraps api_call with cookie jar + CSRF header
auth_api_call() {
  local label="$1"
  shift
  if ! has_session; then
    echo -e "\n  ${SYM_WARN}  ${YELLOW}Login required.${RESET}\n"
    return 1
  fi
  local -a args=("$label" -b "$COOKIE_JAR")
  [[ -n "$CSRF_TOKEN" ]] && args+=(-H "X-CSRF-Token: ${CSRF_TOKEN}")
  args+=("$@")
  api_call "${args[@]}"
}

# Mask a key for display
mask_key() {
  local key="$1"
  if [[ ${#key} -gt 12 ]]; then
    echo "${key:0:8}...${key: -4}"
  else
    echo "$key"
  fi
}

prompt_input() {
  local label="$1"
  local default="${2:-}"
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

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
show_banner() {
  clear 2>/dev/null || true
  echo ""
  echo -e "${ORANGE}"
  cat << 'BANNER'
       █████╗ ██╗   ██╗████████╗ ██████╗ ███╗   ███╗ █████╗ ████████╗██╗ ██████╗ ███╗   ██╗
      ██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗████╗ ████║██╔══██╗╚══██╔══╝██║██╔═══██╗████╗  ██║
      ███████║██║   ██║   ██║   ██║   ██║██╔████╔██║███████║   ██║   ██║██║   ██║██╔██╗ ██║
      ██╔══██║██║   ██║   ██║   ██║   ██║██║╚██╔╝██║██╔══██║   ██║   ██║██║   ██║██║╚██╗██║
      ██║  ██║╚██████╔╝   ██║   ╚██████╔╝██║ ╚═╝ ██║██║  ██║   ██║   ██║╚██████╔╝██║ ╚████║
      ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝
BANNER
  echo -e "${RESET}"
  echo -e "  ${DIM}──────────────────────────────────────────────────────────────────────────────────${RESET}"
  echo -e "    ${BOLD}${WHITE}Vandalizer${RESET}  ${DIM}│${RESET}  ${CYAN}API Automation Test Harness${RESET}"
  echo -e "  ${DIM}──────────────────────────────────────────────────────────────────────────────────${RESET}"
  echo ""
}

# ---------------------------------------------------------------------------
# Connection check
# ---------------------------------------------------------------------------
check_connection() {
  echo -e "  ${VIOLET}┌─${RESET} ${BOLD}${WHITE}PREFLIGHT${RESET} ${DIM}─────────────────────────────────────────${RESET}"
  echo -e "  ${VIOLET}│${RESET}  ${BOLD}${CYAN}Connection Check${RESET}"
  echo -e "  ${VIOLET}└──────────────────────────────────────────────────────${RESET}"
  echo ""

  if api_call "Reaching ${BASE_URL}" -X GET "${BASE_URL}/api/health"; then
    local status
    status=$(json_field "status")
    if [[ "$status" == "ok" ]]; then
      echo -e "  ${SYM_CHECK}  API health: ${GREEN}${BOLD}nominal${RESET}"
    else
      echo -e "  ${SYM_WARN}  API health: ${YELLOW}${status}${RESET}"
    fi
  else
    echo -e "  ${SYM_CROSS}  ${RED}Cannot reach server at ${BASE_URL}${RESET}"
    echo -e "  ${DIM}     Start the backend: cd backend && uvicorn app.main:app --reload --port 8001${RESET}"
  fi

  echo ""
  echo -e "  ${DIM}Server:${RESET}  ${BOLD}${BASE_URL}${RESET}"
  if [[ -n "$API_KEY" ]]; then
    echo -e "  ${DIM}API Key:${RESET} ${BOLD}$(mask_key "$API_KEY")${RESET}"
  else
    echo -e "  ${DIM}API Key:${RESET} ${YELLOW}not set${RESET}  ${DIM}(use 'gen-key' or export VANDALIZER_API_KEY)${RESET}"
  fi
  if [[ -n "$COOKIE_JAR" ]]; then
    echo -e "  ${DIM}Session:${RESET} ${GREEN}authenticated${RESET}"
  else
    echo -e "  ${DIM}Session:${RESET} ${GRAY}not logged in${RESET}"
  fi
  echo ""
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
do_login() {
  local email="${1:-${VANDALIZER_EMAIL:-}}"
  local password="${2:-${VANDALIZER_PASSWORD:-}}"

  if [[ -z "$email" ]]; then
    prompt_input "Email" "" email
  fi
  if [[ -z "$password" ]]; then
    prompt_input "Password" "" password true
  fi

  echo ""
  COOKIE_JAR="${TMP_DIR}/cookies"

  if curl -s -w "\n%{http_code}" \
       -X POST "${BASE_URL}/api/auth/login" \
       -H "Content-Type: application/json" \
       -d "{\"user_id\":\"${email}\",\"password\":\"${password}\"}" \
       -c "$COOKIE_JAR" \
       > "${TMP_DIR}/response" 2>/dev/null; then

    LAST_STATUS=$(tail -1 "${TMP_DIR}/response")
    LAST_RESPONSE=$(sed '$d' "${TMP_DIR}/response")

    if [[ "$LAST_STATUS" -ge 200 && "$LAST_STATUS" -lt 300 ]]; then
      CSRF_TOKEN=$(awk '$6 == "csrf_token" {print $7}' "$COOKIE_JAR" 2>/dev/null)
      echo -e "  ${SYM_CHECK}  Logged in as ${BOLD}${email}${RESET}"
      local name
      name=$(json_field "name" 2>/dev/null)
      [[ -n "$name" ]] && echo -e "  ${DIM}     Welcome back, ${name}${RESET}"
    else
      echo -e "  ${SYM_CROSS}  Login failed: ${RED}${LAST_STATUS}${RESET}"
      COOKIE_JAR=""
      local detail
      detail=$(json_field "detail" 2>/dev/null)
      [[ -n "$detail" ]] && echo -e "  ${DIM}     ${detail}${RESET}"
    fi
  else
    echo -e "  ${SYM_CROSS}  ${RED}Connection failed${RESET}"
  fi
  echo ""
}

do_gen_key() {
  echo ""
  if auth_api_call "Generating API key" \
       -X POST "${BASE_URL}/api/auth/api-token/generate"; then

    local token expires
    token=$(json_field "api_token")
    expires=$(json_field "expires_at")
    API_KEY="$token"

    echo ""
    echo -e "  ${VIOLET}┌──────────────────────────────────────────────────────${RESET}"
    echo -e "  ${VIOLET}│${RESET}  ${SYM_KEY}  ${BOLD}${WHITE}API Key Generated${RESET}"
    echo -e "  ${VIOLET}│${RESET}"
    echo -e "  ${VIOLET}│${RESET}  ${BOLD}${BRIGHT_GREEN}${token}${RESET}"
    echo -e "  ${VIOLET}│${RESET}"
    echo -e "  ${VIOLET}│${RESET}  ${DIM}Expires: ${expires}${RESET}"
    echo -e "  ${VIOLET}│${RESET}  ${DIM}Save this now — it won't be shown again.${RESET}"
    echo -e "  ${VIOLET}│${RESET}"
    echo -e "  ${VIOLET}│${RESET}  ${CYAN}export VANDALIZER_API_KEY=${token}${RESET}"
    echo -e "  ${VIOLET}└──────────────────────────────────────────────────────${RESET}"
  else
    show_json "Error"
  fi
  echo ""
}

do_key_status() {
  echo ""
  if auth_api_call "Checking API key status" \
       -X GET "${BASE_URL}/api/auth/api-token/status"; then
    local has_token expired
    has_token=$(json_field "has_token")
    expired=$(json_field "expired")
    if [[ "$has_token" == "True" || "$has_token" == "true" ]]; then
      if [[ "$expired" == "True" || "$expired" == "true" ]]; then
        echo -e "  ${SYM_WARN}  Key exists but is ${RED}expired${RESET}"
      else
        echo -e "  ${SYM_CHECK}  Key is ${GREEN}active${RESET}"
        local expires_at
        expires_at=$(json_field "expires_at")
        [[ -n "$expires_at" ]] && echo -e "  ${DIM}     Expires: ${expires_at}${RESET}"
      fi
    else
      echo -e "  ${SYM_CROSS}  No API key configured. Run ${BOLD}gen-key${RESET}"
    fi
  else
    show_json "Error"
  fi
  echo ""
}

do_list() {
  echo ""
  if auth_api_call "Fetching automations" \
       -X GET "${BASE_URL}/api/automations"; then
    show_automations_table
  else
    show_json "Error"
  fi
}

do_get() {
  local auto_id="${1:-}"
  if [[ -z "$auto_id" ]]; then
    prompt_input "Automation ID" "" auto_id
  fi
  echo ""
  if auth_api_call "Fetching automation ${auto_id}" \
       -X GET "${BASE_URL}/api/automations/${auto_id}"; then
    show_json "Automation Details"
  else
    show_json "Error"
  fi
}

do_create() {
  if ! has_session; then
    echo -e "\n  ${SYM_WARN}  ${YELLOW}Login required.${RESET}\n"
    return
  fi

  local name trigger_type action_type action_id

  echo ""
  echo -e "  ${VIOLET}┌─${RESET} ${BOLD}${WHITE}CREATE AUTOMATION${RESET}"
  echo -e "  ${VIOLET}└──────────────────────────────────────────────────────${RESET}"
  echo ""

  prompt_input "Name" "" name
  prompt_input "Trigger type" "api" trigger_type
  prompt_input "Action type" "workflow" action_type
  prompt_input "Action ID (workflow or search set)" "" action_id

  local body="{\"name\":\"${name}\",\"trigger_type\":\"${trigger_type}\",\"action_type\":\"${action_type}\""
  [[ -n "$action_id" ]] && body="${body},\"action_id\":\"${action_id}\""

  if [[ "$trigger_type" == "folder_watch" ]]; then
    local folder_id
    prompt_input "Folder ID" "" folder_id
    body="${body},\"trigger_config\":{\"folder_id\":\"${folder_id}\"}"
  elif [[ "$trigger_type" == "schedule" ]]; then
    local cron_expr
    prompt_input "Cron expression" "0 9 * * *" cron_expr
    body="${body},\"trigger_config\":{\"cron_expression\":\"${cron_expr}\"}"
  fi
  body="${body}}"

  echo ""
  if auth_api_call "Creating automation" \
       -X POST "${BASE_URL}/api/automations" \
       -H "Content-Type: application/json" \
       -d "$body"; then
    local new_id
    new_id=$(json_field "id")
    echo -e "  ${SYM_DOT}  Created: ${BOLD}${new_id}${RESET}"
    show_json
  else
    show_json "Error"
  fi
}

do_enable() {
  local auto_id="${1:-}"
  local enabled="${2:-true}"
  if [[ -z "$auto_id" ]]; then
    prompt_input "Automation ID" "" auto_id
  fi

  local label="Enabling"
  [[ "$enabled" == "false" ]] && label="Disabling"

  echo ""
  if auth_api_call "${label} automation" \
       -X PATCH "${BASE_URL}/api/automations/${auto_id}" \
       -H "Content-Type: application/json" \
       -d "{\"enabled\":${enabled}}"; then
    if [[ "$enabled" == "true" ]]; then
      echo -e "  ${SYM_BOLT}  Automation is now ${GREEN}${BOLD}enabled${RESET}"
    else
      echo -e "  ${SYM_DOT}  Automation is now ${GRAY}disabled${RESET}"
    fi
  else
    show_json "Error"
  fi
  echo ""
}

do_delete() {
  local auto_id="${1:-}"
  if [[ -z "$auto_id" ]]; then
    prompt_input "Automation ID" "" auto_id
  fi

  echo -ne "  ${SYM_ARROW}  Delete ${BOLD}${auto_id}${RESET}? ${DIM}[y/N]${RESET}: "
  local confirm
  read -r confirm
  if [[ ! "$confirm" =~ ^[Yy] ]]; then
    echo -e "  ${DIM}Cancelled.${RESET}"
    return
  fi

  echo ""
  if auth_api_call "Deleting automation" \
       -X DELETE "${BASE_URL}/api/automations/${auto_id}"; then
    echo -e "  ${SYM_CHECK}  Deleted."
  else
    show_json "Error"
  fi
  echo ""
}

do_active() {
  echo ""
  if auth_api_call "Checking active automations" \
       -X GET "${BASE_URL}/api/automations/active"; then

    local active_count recently_count
    active_count=$(echo "$LAST_RESPONSE" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('active_automation_ids',[])))" 2>/dev/null || echo "0")
    recently_count=$(echo "$LAST_RESPONSE" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('recently_completed',[])))" 2>/dev/null || echo "0")

    if [[ "$active_count" == "0" && "$recently_count" == "0" ]]; then
      echo -e "  ${DIM}No active or recently completed automations.${RESET}"
    else
      [[ "$active_count" != "0" ]] && echo -e "  ${SYM_BOLT}  ${BOLD}${active_count}${RESET} currently running"
      [[ "$recently_count" != "0" ]] && echo -e "  ${SYM_CHECK}  ${BOLD}${recently_count}${RESET} recently completed"
      show_json
    fi
  else
    show_json "Error"
  fi
  echo ""
}

do_trigger() {
  local auto_id="${1:-}"
  if [[ -z "$auto_id" ]]; then
    prompt_input "Automation ID" "" auto_id
  fi

  local key="${API_KEY}"
  if [[ -z "$key" ]]; then
    prompt_input "API key" "" key
  fi
  if [[ -z "$key" ]]; then
    echo -e "  ${SYM_CROSS}  ${RED}API key required.${RESET} Run ${BOLD}gen-key${RESET} or export ${BOLD}VANDALIZER_API_KEY${RESET}"
    return
  fi

  echo ""
  echo -e "  ${VIOLET}┌─${RESET} ${BOLD}${WHITE}TRIGGER AUTOMATION${RESET} ${DIM}${auto_id}${RESET}"
  echo -e "  ${VIOLET}└──────────────────────────────────────────────────────${RESET}"
  echo ""

  local text_input="" doc_uuids="" file_paths=""

  prompt_input "Text input ${DIM}(Enter to skip)${RESET}" "" text_input
  prompt_input "Document UUIDs ${DIM}(comma-separated, Enter to skip)${RESET}" "" doc_uuids
  prompt_input "File paths ${DIM}(comma-separated, Enter to skip)${RESET}" "" file_paths

  if [[ -z "$text_input" && -z "$doc_uuids" && -z "$file_paths" ]]; then
    echo -e "\n  ${SYM_WARN}  ${YELLOW}No input provided.${RESET} Need at least one of: text, doc UUIDs, or files.\n"
    return
  fi

  # Build curl args
  local -a curl_args=()
  curl_args+=(-X POST "${BASE_URL}/api/automations/${auto_id}/trigger")
  curl_args+=(-H "x-api-key: ${key}")

  [[ -n "$text_input" ]] && curl_args+=(-F "text=${text_input}")
  [[ -n "$doc_uuids" ]] && curl_args+=(-F "document_uuids=${doc_uuids}")

  if [[ -n "$file_paths" ]]; then
    IFS=',' read -ra files <<< "$file_paths"
    for f in "${files[@]}"; do
      f=$(echo "$f" | xargs)  # trim whitespace
      if [[ ! -f "$f" ]]; then
        echo -e "  ${SYM_CROSS}  File not found: ${RED}${f}${RESET}"
        return
      fi
      curl_args+=(-F "files=@${f}")
    done
  fi

  # Show what we're sending
  echo ""
  echo -e "  ${SYM_SEND}  ${BOLD}Sending trigger request${RESET}"
  [[ -n "$text_input" ]] && echo -e "  ${DIM}     Text: ${text_input:0:60}${RESET}"
  [[ -n "$doc_uuids" ]] && echo -e "  ${DIM}     Docs: ${doc_uuids}${RESET}"
  [[ -n "$file_paths" ]] && echo -e "  ${DIM}     Files: ${file_paths}${RESET}"
  echo ""

  if api_call "Triggering automation" "${curl_args[@]}"; then
    local status action_type doc_count
    status=$(json_field "status")
    action_type=$(json_field "action_type")
    doc_count=$(echo "$LAST_RESPONSE" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('documents',[])))" 2>/dev/null || echo "?")

    echo ""
    echo -e "  ${VIOLET}┌──────────────────────────────────────────────────────${RESET}"
    echo -e "  ${VIOLET}│${RESET}  ${SYM_BOLT}  ${BOLD}${WHITE}Trigger Accepted${RESET}"
    echo -e "  ${VIOLET}│${RESET}"
    echo -e "  ${VIOLET}│${RESET}  Status:     ${GREEN}${BOLD}${status}${RESET}"
    echo -e "  ${VIOLET}│${RESET}  Action:     ${CYAN}${action_type}${RESET}"
    echo -e "  ${VIOLET}│${RESET}  Documents:  ${BOLD}${doc_count}${RESET}"

    local trigger_id activity_id
    trigger_id=$(json_field "trigger_event_id")
    activity_id=$(json_field "activity_id")
    [[ -n "$trigger_id" ]] && echo -e "  ${VIOLET}│${RESET}  Trigger ID: ${DIM}${trigger_id}${RESET}"
    [[ -n "$activity_id" ]] && echo -e "  ${VIOLET}│${RESET}  Activity:   ${DIM}${activity_id}${RESET}"

    echo -e "  ${VIOLET}└──────────────────────────────────────────────────────${RESET}"
  else
    show_json "Trigger Failed"
  fi
  echo ""
}

do_poll() {
  local auto_id="${1:-}"
  local timeout="${2:-120}"
  local interval="${3:-5}"

  if [[ -z "$auto_id" ]]; then
    prompt_input "Automation ID" "" auto_id
  fi

  # First trigger it
  do_trigger "$auto_id"

  # Extract trigger_event_id from the trigger response
  local trigger_id
  trigger_id=$(echo "$LAST_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('trigger_event_id',''))" 2>/dev/null || echo "")

  if [[ -z "$trigger_id" ]]; then
    echo -e "  ${SYM_WARN}  ${YELLOW}No trigger_event_id in response. Cannot poll.${RESET}\n"
    return
  fi

  _poll_trigger_event "$trigger_id" "$timeout" "$interval"
}

do_poll_run() {
  local trigger_id="${1:-}"
  local timeout="${2:-120}"
  local interval="${3:-5}"

  if [[ -z "$trigger_id" ]]; then
    prompt_input "Trigger Event ID" "" trigger_id
  fi

  _poll_trigger_event "$trigger_id" "$timeout" "$interval"
}

_poll_trigger_event() {
  local trigger_id="$1"
  local timeout="$2"
  local interval="$3"

  local key="${API_KEY}"
  if [[ -z "$key" ]]; then
    echo -e "  ${SYM_CROSS}  ${RED}API key required for polling.${RESET} Export ${BOLD}VANDALIZER_API_KEY${RESET}"
    return
  fi

  echo -e "  ${DIM}Polling ${trigger_id} (timeout: ${timeout}s, interval: ${interval}s)...${RESET}"
  echo ""

  local elapsed=0
  local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
  local fi=0

  while [[ $elapsed -lt $timeout ]]; do
    sleep "$interval"
    elapsed=$((elapsed + interval))

    curl -s "${BASE_URL}/api/automations/runs/${trigger_id}" \
         -H "x-api-key: ${key}" \
         > "${TMP_DIR}/poll" 2>/dev/null

    local poll_status poll_output
    poll_status=$(python3 -c "import json; print(json.load(open('${TMP_DIR}/poll')).get('status',''))" 2>/dev/null || echo "")

    if [[ "$poll_status" == "completed" ]]; then
      printf "\r%-60s\n" ""
      echo -e "  ${SYM_CHECK}  ${GREEN}${BOLD}Completed${RESET} after ${elapsed}s"
      poll_output=$(python3 -c "
import json
data = json.load(open('${TMP_DIR}/poll'))
out = data.get('output')
if out:
    print(json.dumps(out, indent=2, default=str)[:500])
else:
    print('(no output)')
" 2>/dev/null || echo "(parse error)")
      echo -e "  ${DIM}Output:${RESET}"
      echo "$poll_output" | head -20
      echo ""
      return
    elif [[ "$poll_status" == "failed" ]]; then
      printf "\r%-60s\n" ""
      local poll_error
      poll_error=$(python3 -c "import json; print(json.load(open('${TMP_DIR}/poll')).get('error','unknown'))" 2>/dev/null || echo "unknown")
      echo -e "  ${SYM_CROSS}  ${RED}${BOLD}Failed${RESET} after ${elapsed}s"
      echo -e "  ${DIM}Error: ${poll_error}${RESET}"
      echo ""
      return
    fi

    printf "\r  ${CYAN}${frames[$fi]}${RESET}  ${DIM}Waiting... ${elapsed}s / ${timeout}s  (${poll_status:-pending})${RESET}  "
    fi=$(( (fi + 1) % ${#frames[@]} ))
  done

  printf "\r%-60s\n" ""
  echo -e "  ${SYM_WARN}  ${YELLOW}Timeout after ${timeout}s.${RESET} Poll manually: ${BOLD}poll-run ${trigger_id}${RESET}"
  echo ""
}

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
show_help() {
  echo ""
  echo -e "  ${BOLD}${WHITE}Commands${RESET}"
  echo -e "  ${DIM}────────${RESET}"
  echo ""
  echo -e "  ${BOLD}${CYAN}Session${RESET}"
  echo -e "    ${BOLD}login${RESET}  ${DIM}[email] [password]${RESET}     Log in (needed for CRUD and polling)"
  echo -e "    ${BOLD}gen-key${RESET}                        Generate a new API key"
  echo -e "    ${BOLD}key-status${RESET}                     Check current API key"
  echo ""
  echo -e "  ${BOLD}${CYAN}Automations${RESET}"
  echo -e "    ${BOLD}list${RESET}                           List all automations"
  echo -e "    ${BOLD}get${RESET}  ${DIM}<id>${RESET}                      Show automation details"
  echo -e "    ${BOLD}create${RESET}                         Create a new automation (interactive)"
  echo -e "    ${BOLD}enable${RESET}  ${DIM}<id>${RESET}                   Enable an automation"
  echo -e "    ${BOLD}disable${RESET}  ${DIM}<id>${RESET}                  Disable an automation"
  echo -e "    ${BOLD}delete${RESET}  ${DIM}<id>${RESET}                   Delete an automation"
  echo -e "    ${BOLD}active${RESET}                         Show running / recently completed"
  echo ""
  echo -e "  ${BOLD}${CYAN}Trigger & Poll${RESET}"
  echo -e "    ${BOLD}trigger${RESET}  ${DIM}<id>${RESET}                  Trigger an automation (interactive inputs)"
  echo -e "    ${BOLD}poll${RESET}  ${DIM}<id> [timeout] [interval]${RESET}  Trigger + poll for completion"
  echo -e "    ${BOLD}poll-run${RESET}  ${DIM}<trigger_event_id>${RESET}    Poll a trigger event by ID"
  echo ""
  echo -e "    ${BOLD}quit${RESET}                           Exit"
  echo ""
}

# ---------------------------------------------------------------------------
# Startup login
# ---------------------------------------------------------------------------
startup_login() {
  echo -e "  ${VIOLET}┌─${RESET} ${BOLD}${WHITE}AUTHENTICATE${RESET} ${DIM}──────────────────────────────────────${RESET}"
  echo -e "  ${VIOLET}│${RESET}  ${BOLD}${CYAN}Log in to access automation CRUD & polling${RESET}"
  echo -e "  ${VIOLET}└──────────────────────────────────────────────────────${RESET}"
  echo ""

  local email="${VANDALIZER_EMAIL:-}"
  local password="${VANDALIZER_PASSWORD:-}"

  if [[ -z "$email" ]]; then
    prompt_input "Email" "" email
  else
    echo -e "  ${SYM_ARROW}  Email ${DIM}[${email}]${RESET}"
  fi

  if [[ -z "$password" ]]; then
    prompt_input "Password" "" password true
  fi

  if [[ -z "$email" || -z "$password" ]]; then
    echo -e "\n  ${SYM_WARN}  ${YELLOW}Skipped.${RESET} ${DIM}You can run${RESET} ${BOLD}login${RESET} ${DIM}later.${RESET}\n"
    return
  fi

  echo ""
  COOKIE_JAR="${TMP_DIR}/cookies"

  curl -s -w "\n%{http_code}" \
    -X POST "${BASE_URL}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"${email}\",\"password\":\"${password}\"}" \
    -c "$COOKIE_JAR" \
    > "${TMP_DIR}/response" 2>/dev/null &
  local pid=$!
  spin "$pid" "Authenticating"
  wait "$pid" 2>/dev/null

  LAST_STATUS=$(tail -1 "${TMP_DIR}/response")
  LAST_RESPONSE=$(sed '$d' "${TMP_DIR}/response")

  if [[ "$LAST_STATUS" -ge 200 && "$LAST_STATUS" -lt 300 ]]; then
    CSRF_TOKEN=$(awk '$6 == "csrf_token" {print $7}' "$COOKIE_JAR" 2>/dev/null)
    local name
    name=$(json_field "name" 2>/dev/null)
    printf "\r  ${SYM_CHECK}  Logged in as ${BOLD}%s${RESET}" "$email"
    [[ -n "$name" ]] && printf "  ${DIM}(%s)${RESET}" "$name"
    echo ""

    # Check API key status while we're at it
    curl -s "${BASE_URL}/api/auth/api-token/status" \
         $(cookie_args) \
         > "${TMP_DIR}/keystatus" 2>/dev/null
    local has_token
    has_token=$(python3 -c "import json; print(json.load(open('${TMP_DIR}/keystatus')).get('has_token',False))" 2>/dev/null || echo "")
    if [[ "$has_token" == "True" || "$has_token" == "true" ]]; then
      echo -e "  ${SYM_CHECK}  API key is ${GREEN}active${RESET}"
      if [[ -z "$API_KEY" ]]; then
        echo -e "  ${DIM}     Tip: export VANDALIZER_API_KEY=<key> to use trigger/poll${RESET}"
      fi
    else
      echo -e "  ${SYM_WARN}  No API key configured  ${DIM}(run ${RESET}${BOLD}gen-key${RESET}${DIM} to create one)${RESET}"
    fi
  else
    printf "\r  ${SYM_CROSS}  Login failed: ${RED}%s${RESET}\n" "$LAST_STATUS"
    local detail
    detail=$(json_field "detail" 2>/dev/null)
    [[ -n "$detail" ]] && echo -e "  ${DIM}     ${detail}${RESET}"
    echo -e "\n  ${DIM}You can try again with${RESET} ${BOLD}login${RESET}"
  fi
  echo ""
}

# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------
repl() {
  show_banner
  check_connection
  startup_login
  show_help

  while true; do
    echo -ne "  ${ORANGE}automation ${RESET}${BOLD}▸${RESET} "
    local line
    read -r line || { echo -e "\n  ${DIM}Bye!${RESET}\n"; break; }
    line=$(echo "$line" | xargs)  # trim

    [[ -z "$line" ]] && continue

    local cmd arg1 arg2 arg3
    cmd=$(echo "$line" | awk '{print $1}')
    arg1=$(echo "$line" | awk '{print $2}')
    arg2=$(echo "$line" | awk '{print $3}')
    arg3=$(echo "$line" | awk '{print $4}')

    case "$cmd" in
      login)      do_login "$arg1" "$arg2" ;;
      gen-key)    do_gen_key ;;
      key-status) do_key_status ;;
      list|ls)    do_list ;;
      get)        do_get "$arg1" ;;
      create|new) do_create ;;
      enable)     do_enable "$arg1" "true" ;;
      disable)    do_enable "$arg1" "false" ;;
      delete|rm)  do_delete "$arg1" ;;
      active)     do_active ;;
      trigger|fire|run) do_trigger "$arg1" ;;
      poll|watch) do_poll "$arg1" "$arg2" "$arg3" ;;
      poll-run) do_poll_run "$arg1" "$arg2" "$arg3" ;;
      help|h|\?)  show_help ;;
      quit|exit|q) echo -e "\n  ${DIM}Bye!${RESET}\n"; break ;;
      status)     check_connection ;;
      clear|cls)  clear 2>/dev/null; show_banner ;;
      *)
        echo -e "  ${SYM_WARN}  Unknown command: ${BOLD}${cmd}${RESET}  ${DIM}(type 'help')${RESET}"
        ;;
    esac
  done
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
repl
