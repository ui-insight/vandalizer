#!/usr/bin/env bash
# MongoDB backup script. Run via cron or manually.
#
# Usage:
#   ./scripts/backup_mongo.sh
#
# Environment variables:
#   MONGO_HOST     - MongoDB connection string (default: mongodb://localhost:27017)
#   MONGO_DB       - Database name (default: osp)
#   BACKUP_DIR     - Where to store backups (default: ./backups)
#   RETENTION_DAYS - Delete backups older than N days (default: 30)

set -euo pipefail

MONGO_HOST="${MONGO_HOST:-mongodb://localhost:27017}"
MONGO_DB="${MONGO_DB:-osp}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEST="${BACKUP_DIR}/${MONGO_DB}_${TIMESTAMP}"

mkdir -p "${BACKUP_DIR}"

echo "[$(date)] Starting backup of ${MONGO_DB} to ${DEST}"
mongodump --uri="${MONGO_HOST}" --db="${MONGO_DB}" --out="${DEST}" --gzip

# Prune old backups
if [ "${RETENTION_DAYS}" -gt 0 ]; then
  echo "[$(date)] Pruning backups older than ${RETENTION_DAYS} days"
  find "${BACKUP_DIR}" -maxdepth 1 -type d -name "${MONGO_DB}_*" -mtime +"${RETENTION_DAYS}" -exec rm -rf {} +
fi

echo "[$(date)] Backup complete: ${DEST}"
