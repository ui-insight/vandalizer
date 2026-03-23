#!/usr/bin/env bash
# Reset the Vandalizer development database, uploaded files, and ChromaDB.
#
# Usage:
#   ./scripts/reset_db.sh          # interactive (asks for confirmation)
#   ./scripts/reset_db.sh --force  # skip confirmation
#
# Environment variables (reads from backend/.env by default):
#   MONGO_HOST          - MongoDB connection string (default: mongodb://localhost:27017)
#   MONGO_DB            - Database name (default: vandalizer)
#   UPLOAD_DIR          - Upload directory (default: ../app/static/uploads, relative to backend/)
#   CHROMADB_PERSIST_DIR - ChromaDB directory (default: ../app/static/db, relative to backend/)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="${PROJECT_DIR}/backend"

# Load env from backend/.env if it exists
if [ -f "${BACKEND_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${BACKEND_DIR}/.env"
  set +a
fi

MONGO_HOST="${MONGO_HOST:-mongodb://localhost:27017/}"
MONGO_DB="${MONGO_DB:-vandalizer}"
UPLOAD_DIR="${UPLOAD_DIR:-../app/static/uploads}"
CHROMADB_PERSIST_DIR="${CHROMADB_PERSIST_DIR:-../app/static/db}"

# Resolve relative paths from backend/
if [[ "$UPLOAD_DIR" != /* ]]; then
  UPLOAD_DIR="$(cd "$BACKEND_DIR" && realpath -m "$UPLOAD_DIR")"
fi
if [[ "$CHROMADB_PERSIST_DIR" != /* ]]; then
  CHROMADB_PERSIST_DIR="$(cd "$BACKEND_DIR" && realpath -m "$CHROMADB_PERSIST_DIR")"
fi

echo "This will destroy:"
echo "  MongoDB database: ${MONGO_DB} (at ${MONGO_HOST})"
echo "  Uploads:          ${UPLOAD_DIR}"
echo "  ChromaDB:         ${CHROMADB_PERSIST_DIR}"
echo ""

if [ "${1:-}" != "--force" ]; then
  read -rp "Are you sure? [y/N] " confirm
  if [[ "$confirm" != [yY] ]]; then
    echo "Aborted."
    exit 0
  fi
fi

echo ""

# 1. Drop MongoDB database
echo "Dropping MongoDB database '${MONGO_DB}'..."
mongosh "${MONGO_HOST}" --quiet --eval "db.getSiblingDB('${MONGO_DB}').dropDatabase()" || {
  # Fall back to docker if mongosh isn't installed locally
  echo "  mongosh not found locally, trying via docker..."
  docker compose -f "${PROJECT_DIR}/docker-compose.yml" exec -T mongo \
    mongosh --quiet --eval "db.getSiblingDB('${MONGO_DB}').dropDatabase()"
}

# 2. Clear uploaded files
if [ -d "$UPLOAD_DIR" ]; then
  echo "Clearing uploads at ${UPLOAD_DIR}..."
  rm -rf "${UPLOAD_DIR:?}"/*
else
  echo "Upload dir not found, skipping: ${UPLOAD_DIR}"
fi

# 3. Clear ChromaDB
if [ -d "$CHROMADB_PERSIST_DIR" ]; then
  echo "Clearing ChromaDB at ${CHROMADB_PERSIST_DIR}..."
  rm -rf "${CHROMADB_PERSIST_DIR:?}"/*
else
  echo "ChromaDB dir not found, skipping: ${CHROMADB_PERSIST_DIR}"
fi

echo ""
echo "Reset complete. Restart the backend and Celery workers to reinitialize."
