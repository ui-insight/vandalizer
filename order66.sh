### CONFIGURATION 
DB_NAME="osp-staging"                          # MongoDB database name
MONGO_HOST="localhost"
MONGO_PORT="27017"
BACKUP_DIR="demo-data"  # This is where the database backup lives

RESTORE_SOURCE_DIR="demo-data/files"     # This is where the files live
TARGET_DIR="app/static/uploads"       # Where we will put the files

CELERY_SCRIPT="run_celery.sh"      

restart_flask() {
  pkill -x flask
  FLASK_ENV=testing REDIS_HOST=localhost python run.py
}

echo "=== 2) Restoring MongoDB '${DB_NAME}' from ${BACKUP_DIR} ==="
mongorestore \
  --host "${MONGO_HOST}" \
  --port "${MONGO_PORT}" \
  --db "${DB_NAME}" \
  --drop \
  "${BACKUP_DIR}/${DB_NAME}"

echo "=== 3) Restoring files from ${RESTORE_SOURCE_DIR} to ${TARGET_DIR} ==="
cp -r "${RESTORE_SOURCE_DIR}/." "${TARGET_DIR}/"

echo "=== 4) Deleting old recommendations ===" # Deletes the semantic recommendation database
rm -rf "data/"*

echo "=== 5) Restarting Celery worker ==="
nohup "${CELERY_SCRIPT}" >& /dev/null &

echo "=== 6) Restarting Flask application ==="
restart_flask

echo "✅ Nuke complete!"
