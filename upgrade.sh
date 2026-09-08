#!/usr/bin/env bash
# Upgrade a Vandalizer deployment to a specific release tag published to GHCR.
#
# Usage:
#   ./upgrade.sh v2026.04.1          # pull + restart api/celery/frontend at that tag
#   ./upgrade.sh v2026.04.1 --dry-run  # show what would happen, change nothing
#   ./upgrade.sh --rollback            # restore the previous version from .last_version
#
# Requires: a Compose implementation (docker compose v2, docker-compose, or
# podman-compose), a working .env in backend/ (created by setup.sh), and GHCR
# pull access (public images need no auth; private images need
# `docker login ghcr.io` first).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VERSION_FILE="${SCRIPT_DIR}/.vandalizer_version"
PREV_VERSION_FILE="${SCRIPT_DIR}/.vandalizer_version.prev"
COMPOSE_FILES=(-f compose.yaml -f compose.prod.yaml)
# CONTAINER_CLI and COMPOSE are resolved in preflight below.

die() { echo "error: $*" >&2; exit 1; }

usage() {
  sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

# --- parse args ---------------------------------------------------------------
DRY_RUN=0
ROLLBACK=0
TAG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)  DRY_RUN=1; shift ;;
    --rollback) ROLLBACK=1; shift ;;
    -h|--help)  usage 0 ;;
    v*.*.*)     TAG="$1"; shift ;;
    *)          die "unrecognized argument: $1 (expected a vX.Y.Z tag or --rollback)" ;;
  esac
done

if [[ $ROLLBACK -eq 1 ]]; then
  [[ -f "$PREV_VERSION_FILE" ]] || die "no previous version recorded at $PREV_VERSION_FILE"
  TAG="$(cat "$PREV_VERSION_FILE")"
  echo "Rolling back to $TAG"
fi

[[ -n "$TAG" ]] || { echo "error: no version tag given" >&2; usage 1; }

# --- preflight ----------------------------------------------------------------
if command -v docker >/dev/null 2>&1; then
  CONTAINER_CLI="docker"
elif command -v podman >/dev/null 2>&1; then
  CONTAINER_CLI="podman"
else
  die "no container engine found — install docker or podman"
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose "${COMPOSE_FILES[@]}")
elif docker-compose version >/dev/null 2>&1; then
  COMPOSE=(docker-compose "${COMPOSE_FILES[@]}")
elif podman-compose version >/dev/null 2>&1; then
  COMPOSE=(podman-compose "${COMPOSE_FILES[@]}")
else
  die "no Compose implementation found (docker compose v2, docker-compose, or podman-compose)"
fi
[[ -f compose.yaml ]]      || die "compose.yaml not found (run from repo root)"
[[ -f compose.prod.yaml ]] || die "compose.prod.yaml not found"
[[ -f backend/.env ]]      || die "backend/.env not found — run ./setup.sh first"

# Verify the tag's images actually exist in GHCR before touching anything.
for image in "ghcr.io/ui-insight/vandalizer-backend:${TAG}" \
             "ghcr.io/ui-insight/vandalizer-frontend:${TAG}"; do
  echo "Checking $image..."
  if ! $CONTAINER_CLI manifest inspect "$image" >/dev/null 2>&1; then
    die "image $image not found in registry (private registry? run '$CONTAINER_CLI login ghcr.io')"
  fi
done

current=""
[[ -f "$VERSION_FILE" ]] && current="$(cat "$VERSION_FILE")"
echo "Current version:  ${current:-<unknown>}"
echo "Target version:   ${TAG}"

if [[ "$current" == "$TAG" && $ROLLBACK -eq 0 ]]; then
  echo "Already at $TAG — nothing to do."
  exit 0
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo "--dry-run: would pull images and restart api, celery, frontend."
  exit 0
fi

# --- apply --------------------------------------------------------------------
export VANDALIZER_VERSION="$TAG"

# Record previous version for rollback before we change anything.
if [[ -n "$current" ]]; then
  cp "$VERSION_FILE" "$PREV_VERSION_FILE"
fi

echo "Pulling images..."
"${COMPOSE[@]}" pull api celery frontend

echo "Restarting services..."
"${COMPOSE[@]}" up -d --no-deps api celery frontend

echo "$TAG" > "$VERSION_FILE"

echo "Waiting for api health..."
for _ in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T api python -c \
      "import urllib.request; urllib.request.urlopen('http://localhost:8001/api/health')" \
      >/dev/null 2>&1; then
    echo "api is healthy."
    echo "Upgrade to $TAG complete."
    exit 0
  fi
  sleep 2
done

echo "warning: api did not pass health check within 60s — check '${COMPOSE[*]} logs api'" >&2
exit 1
