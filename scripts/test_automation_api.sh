#!/usr/bin/env bash
# ============================================================================
#  Vandalizer — Automation API Trigger
#  Simple wizard: pick an automation, provide input, run it.
#
#  Usage:
#    ./scripts/test_automation_api.sh
#    ./scripts/test_automation_api.sh --url http://...
#
#  Environment:
#    VANDALIZER_URL        Server URL      (default: http://localhost:8001)
#    VANDALIZER_API_KEY    API key for trigger endpoint
#    VANDALIZER_EMAIL      Login email
#    VANDALIZER_PASSWORD   Login password
# ============================================================================

set -uo pipefail

# Colors
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'
GREEN='\033[38;5;114m'
RED='\033[38;5;203m'
YELLOW='\033[38;5;221m'
CYAN='\033[38;5;117m'
ORANGE='\033[38;5;208m'
WHITE='\033[38;5;255m'

# State
BASE_URL="${VANDALIZER_URL:-http://localhost:8001}"
API_KEY="${VANDALIZER_API_KEY:-}"
COOKIE_JAR=""
CSRF_TOKEN=""
LAST_RESPONSE=""
LAST_STATUS=""
TMP_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url|--base-url) BASE_URL="$2"; shift 2 ;;
    --api-key)        API_KEY="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: $0 [--url URL] [--api-key KEY]"
      echo "Env: VANDALIZER_URL, VANDALIZER_API_KEY, VANDALIZER_EMAIL, VANDALIZER_PASSWORD"
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

cleanup() { [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]] && rm -rf "$TMP_DIR"; }
trap cleanup EXIT
TMP_DIR=$(mktemp -d)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
api_get() {
  LAST_RESPONSE=$(curl -s -w "\n%{http_code}" -b "$COOKIE_JAR" \
    -H "X-CSRF-Token: ${CSRF_TOKEN}" "$@" 2>/dev/null)
  LAST_STATUS=$(echo "$LAST_RESPONSE" | tail -1)
  LAST_RESPONSE=$(echo "$LAST_RESPONSE" | sed '$d')
  [[ "$LAST_STATUS" -ge 200 && "$LAST_STATUS" -lt 300 ]]
}

api_post() {
  LAST_RESPONSE=$(curl -s -w "\n%{http_code}" -b "$COOKIE_JAR" \
    -H "X-CSRF-Token: ${CSRF_TOKEN}" "$@" 2>/dev/null)
  LAST_STATUS=$(echo "$LAST_RESPONSE" | tail -1)
  LAST_RESPONSE=$(echo "$LAST_RESPONSE" | sed '$d')
  [[ "$LAST_STATUS" -ge 200 && "$LAST_STATUS" -lt 300 ]]
}

fail() { echo -e "\n  ${RED}✗  $1${RESET}\n"; exit 1; }

# ---------------------------------------------------------------------------
# Step 1: Connect & authenticate
# ---------------------------------------------------------------------------
echo ""
echo -e "  ${ORANGE}${BOLD}Vandalizer${RESET}  ${DIM}— Automation Trigger${RESET}"
echo -e "  ${DIM}$(printf '%.0s─' $(seq 1 44))${RESET}"
echo ""

# Health check
echo -ne "  Connecting to ${BOLD}${BASE_URL}${RESET}... "
if curl -sf "${BASE_URL}/api/health" > /dev/null 2>&1; then
  echo -e "${GREEN}ok${RESET}"
else
  echo -e "${RED}failed${RESET}"
  fail "Cannot reach server. Is the backend running?"
fi

# Login
email="${VANDALIZER_EMAIL:-}"
password="${VANDALIZER_PASSWORD:-}"
[[ -z "$email" ]] && { echo -ne "  User ID: "; read -r email; }
[[ -z "$password" ]] && { echo -ne "  Password: "; read -rs password; echo; }

COOKIE_JAR="${TMP_DIR}/cookies"
echo -ne "  Logging in... "

curl -s -w "\n%{http_code}" \
  -X POST "${BASE_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"${email}\",\"password\":\"${password}\"}" \
  -c "$COOKIE_JAR" \
  > "${TMP_DIR}/response" 2>/dev/null

LAST_STATUS=$(tail -1 "${TMP_DIR}/response")
LAST_RESPONSE=$(sed '$d' "${TMP_DIR}/response")

if [[ "$LAST_STATUS" -ge 200 && "$LAST_STATUS" -lt 300 ]]; then
  CSRF_TOKEN=$(awk '$6 == "csrf_token" {print $7}' "$COOKIE_JAR" 2>/dev/null)
  local_name=$(echo "$LAST_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('name',''))" 2>/dev/null || echo "")
  echo -e "${GREEN}ok${RESET}${DIM}${local_name:+ ($local_name)}${RESET}"
else
  echo -e "${RED}failed${RESET}"
  detail=$(echo "$LAST_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('detail',''))" 2>/dev/null || echo "")
  fail "Login failed${detail:+: $detail}"
fi

# API key check
if [[ -z "$API_KEY" ]]; then
  # Try to generate one automatically
  echo -ne "  API key not set. Generating... "
  if api_post -X POST "${BASE_URL}/api/auth/api-token/generate"; then
    API_KEY=$(echo "$LAST_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('api_token',''))" 2>/dev/null || echo "")
    if [[ -n "$API_KEY" ]]; then
      echo -e "${GREEN}ok${RESET}"
    else
      echo -e "${RED}failed${RESET}"
      fail "Could not generate API key. Generate one manually in Account settings."
    fi
  else
    echo -e "${RED}failed${RESET}"
    fail "Could not generate API key."
  fi
else
  echo -e "  API key: ${DIM}${API_KEY:0:8}...${RESET}"
fi

# ---------------------------------------------------------------------------
# Step 2: Pick an automation
# ---------------------------------------------------------------------------
echo ""
echo -ne "  Loading automations... "

if ! api_get "${BASE_URL}/api/automations"; then
  echo -e "${RED}failed${RESET}"
  fail "Could not fetch automations."
fi
echo -e "${GREEN}ok${RESET}"

# Parse automations into arrays
AUTO_COUNT=$(echo "$LAST_RESPONSE" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [[ "$AUTO_COUNT" == "0" ]]; then
  fail "No automations found. Create one in the Vandalizer UI first."
fi

# Filter to API-triggered automations only
AUTOMATIONS_JSON="$LAST_RESPONSE"

echo ""
echo -e "  ${BOLD}Your automations:${RESET}"
echo ""

# Display numbered list
echo "$AUTOMATIONS_JSON" | python3 -c "
import sys, json

autos = json.load(sys.stdin)
api_autos = [a for a in autos if a.get('trigger_type') == 'api']
other_autos = [a for a in autos if a.get('trigger_type') != 'api']

if api_autos:
    for i, a in enumerate(api_autos, 1):
        status = '\033[38;5;114m●\033[0m' if a['enabled'] else '\033[38;5;245m○\033[0m'
        action = a.get('action_name') or a.get('action_type', '?')
        print(f'    {status}  \033[1m{i}\033[0m  {a[\"name\"]}\033[2m  — {action}\033[0m')

if other_autos:
    if api_autos:
        print()
    print('  \033[2m  Not API-triggered:\033[0m')
    for a in other_autos:
        status = '\033[38;5;114m●\033[0m' if a['enabled'] else '\033[38;5;245m○\033[0m'
        print(f'    {status}  \033[2m-  {a[\"name\"]}  ({a[\"trigger_type\"]})\033[0m')

# Write count of api autos for the shell to read
with open('${TMP_DIR}/api_count', 'w') as f:
    f.write(str(len(api_autos)))
with open('${TMP_DIR}/api_autos', 'w') as f:
    json.dump(api_autos, f)
" 2>/dev/null

API_AUTO_COUNT=$(cat "${TMP_DIR}/api_count" 2>/dev/null || echo "0")

if [[ "$API_AUTO_COUNT" == "0" ]]; then
  echo ""
  fail "No API-triggered automations found. Create one with trigger type 'API' first."
fi

echo ""
echo -ne "  ${BOLD}Pick an automation${RESET} ${DIM}(1-${API_AUTO_COUNT})${RESET}: "
read -r choice

# Validate choice
if ! [[ "$choice" =~ ^[0-9]+$ ]] || [[ "$choice" -lt 1 || "$choice" -gt "$API_AUTO_COUNT" ]]; then
  fail "Invalid selection."
fi

# Get the selected automation
SELECTED=$(python3 -c "
import json
autos = json.load(open('${TMP_DIR}/api_autos'))
a = autos[${choice} - 1]
print(a['id'])
print(a['name'])
print(a.get('action_type', 'unknown'))
print(a.get('action_name') or a.get('action_type', ''))
" 2>/dev/null)

AUTO_ID=$(echo "$SELECTED" | sed -n '1p')
AUTO_NAME=$(echo "$SELECTED" | sed -n '2p')
AUTO_ACTION_TYPE=$(echo "$SELECTED" | sed -n '3p')
AUTO_ACTION_NAME=$(echo "$SELECTED" | sed -n '4p')

echo ""
echo -e "  ${GREEN}✓${RESET}  Selected: ${BOLD}${AUTO_NAME}${RESET}  ${DIM}(${AUTO_ACTION_NAME})${RESET}"

# ---------------------------------------------------------------------------
# Step 3: Choose input type
# ---------------------------------------------------------------------------
echo ""
echo -e "  ${BOLD}How do you want to provide input?${RESET}"
echo ""
echo -e "    ${BOLD}1${RESET}  Upload a file"
echo -e "    ${BOLD}2${RESET}  Enter text"
echo ""
echo -ne "  ${BOLD}Choice${RESET} ${DIM}(1 or 2)${RESET}: "
read -r input_choice

CURL_ARGS=(-X POST "${BASE_URL}/api/automations/${AUTO_ID}/trigger" -H "x-api-key: ${API_KEY}")

case "$input_choice" in
  1)
    echo -ne "  File path: "
    read -r file_path
    # Expand ~ to home directory
    file_path="${file_path/#\~/$HOME}"
    if [[ ! -f "$file_path" ]]; then
      fail "File not found: ${file_path}"
    fi
    CURL_ARGS+=(-F "files=@${file_path}")
    echo -e "  ${DIM}Sending: $(basename "$file_path")${RESET}"
    ;;
  2)
    echo -e "  ${DIM}Type or paste your text, then press Enter twice (blank line) to send:${RESET}"
    echo -ne "  > "
    text_input=""
    while IFS= read -r line; do
      [[ -z "$line" ]] && break
      [[ -n "$text_input" ]] && text_input="${text_input}"$'\n'
      text_input="${text_input}${line}"
      echo -ne "  > "
    done
    if [[ -z "$text_input" ]]; then
      fail "No text provided."
    fi
    printf '%s' "$text_input" > "${TMP_DIR}/input_text"
    CURL_ARGS+=(-F "text=<${TMP_DIR}/input_text")
    ;;
  *)
    fail "Invalid choice."
    ;;
esac

# ---------------------------------------------------------------------------
# Step 4: Trigger and poll
# ---------------------------------------------------------------------------
echo ""
echo -ne "  Triggering ${BOLD}${AUTO_NAME}${RESET}... "

LAST_RESPONSE=$(curl -s -w "\n%{http_code}" "${CURL_ARGS[@]}" 2>/dev/null)
LAST_STATUS=$(echo "$LAST_RESPONSE" | tail -1)
LAST_RESPONSE=$(echo "$LAST_RESPONSE" | sed '$d')

if [[ "$LAST_STATUS" -ge 200 && "$LAST_STATUS" -lt 300 ]]; then
  echo -e "${GREEN}ok${RESET}"
else
  echo -e "${RED}failed (${LAST_STATUS})${RESET}"
  detail=$(echo "$LAST_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('detail',''))" 2>/dev/null || echo "$LAST_RESPONSE")
  fail "Trigger failed: ${detail}"
fi

TRIGGER_ID=$(echo "$LAST_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('trigger_event_id',''))" 2>/dev/null || echo "")

if [[ -z "$TRIGGER_ID" ]]; then
  echo -e "  ${DIM}Response:${RESET}"
  echo "$LAST_RESPONSE" | python3 -m json.tool 2>/dev/null | head -20
  echo ""
  exit 0
fi

# Poll for result
echo ""
echo -e "  ${DIM}Waiting for result...${RESET}"

TIMEOUT=180
INTERVAL=3
elapsed=0
frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
fi=0

while [[ $elapsed -lt $TIMEOUT ]]; do
  sleep "$INTERVAL"
  elapsed=$((elapsed + INTERVAL))

  poll_response=$(curl -s "${BASE_URL}/api/automations/runs/${TRIGGER_ID}" \
    -H "x-api-key: ${API_KEY}" 2>/dev/null)

  poll_status=$(echo "$poll_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")

  if [[ "$poll_status" == "completed" ]]; then
    printf "\r%-60s\r" ""
    echo -e "  ${GREEN}${BOLD}✓  Done${RESET}  ${DIM}(${elapsed}s)${RESET}"
    echo ""

    # Show output
    echo "$poll_response" | python3 -c "
import sys, json

data = json.load(sys.stdin)
output = data.get('output')
if not output:
    print('  \033[2m(no output)\033[0m')
else:
    formatted = json.dumps(output, indent=2, default=str)
    for line in formatted.split('\n')[:40]:
        print(f'  {line}')
    lines = formatted.split('\n')
    if len(lines) > 40:
        print(f'  \033[2m... ({len(lines) - 40} more lines)\033[0m')
" 2>/dev/null
    echo ""
    exit 0
  fi

  if [[ "$poll_status" == "failed" ]]; then
    printf "\r%-60s\r" ""
    poll_error=$(echo "$poll_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','unknown error'))" 2>/dev/null || echo "unknown")
    echo -e "  ${RED}${BOLD}✗  Failed${RESET}  ${DIM}(${elapsed}s)${RESET}"
    echo -e "  ${DIM}${poll_error}${RESET}"
    echo ""
    exit 1
  fi

  printf "\r  ${CYAN}${frames[$fi]}${RESET}  ${DIM}${poll_status:-pending}... ${elapsed}s${RESET}  "
  fi=$(( (fi + 1) % ${#frames[@]} ))
done

printf "\r%-60s\r" ""
echo -e "  ${YELLOW}⚠  Timed out${RESET} after ${TIMEOUT}s"
echo -e "  ${DIM}The automation is still running. Check results in the UI.${RESET}"
echo ""
