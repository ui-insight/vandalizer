#!/bin/bash
set -e

# Configuration
# Use a random number to avoid database name collisions if multiple tests run in parallel
RAND=$RANDOM
MAIN_DB="vandalizer_test_main_$RAND"
INSTANCE_DB="vandalizer_test_instance_$RAND"
MAIN_PORT=5005
SYNC_KEY="test-secret-key"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

cleanup() {
    echo -e "\n${BLUE}Cleaning up...${NC}"
    
    # Kill Flask
    if [ -n "$MAIN_PID" ]; then kill $MAIN_PID 2>/dev/null || true; fi
    
    # Drop Test Databases
    uv run python3 -c "
from pymongo import MongoClient
client = MongoClient('mongodb://localhost:27017/')
client.drop_database('$MAIN_DB')
client.drop_database('$INSTANCE_DB')
"
    echo -e "${GREEN}Cleanup complete.${NC}"
}
trap cleanup EXIT

echo -e "${BLUE}=== Global Telemetry Sync Test ===${NC}"
echo "Using DBs: $MAIN_DB and $INSTANCE_DB"

# 1. Reset Databases
echo -e "${BLUE}1. Resetting MongoDB databases...${NC}"
uv run python3 -c "
from pymongo import MongoClient
client = MongoClient('mongodb://localhost:27017/')
client.drop_database('$MAIN_DB')
client.drop_database('$INSTANCE_DB')
"

# 2. Start Main Server (Flask)
echo -e "${BLUE}2. Starting Main Server (Port $MAIN_PORT)...${NC}"
export FLASK_APP=run.py
export FLASK_ENV=testing
export FLASK_MONGO_DB="$MAIN_DB"
export IS_MAIN_SERVER=true
export INSTANCE_NAME="MainServer"
export SYNC_API_KEY="$SYNC_KEY"
export PORT=$MAIN_PORT
export CELERY_BROKER_URL="redis://localhost:6379/10"
export CELERY_RESULT_BACKEND="redis://localhost:6379/11"

# Run Flask in background
uv run flask run --port=$MAIN_PORT > logs/test_main_flask.log 2>&1 &
MAIN_PID=$!
sleep 5 # Wait for Flask to start

# 3. Seed Data into Instance DB
echo -e "${BLUE}3. Seeding Telemetry Data into Instance DB...${NC}"
export FLASK_MONGO_DB="$INSTANCE_DB"
export INSTANCE_NAME="TestClient"
export IS_MAIN_SERVER=false

uv run python3 -c "
from app import create_app
from app.models import DailyUsageAggregate
from datetime import datetime, timedelta

app = create_app()
with app.app_context():
    # Create yesterday's data
    yesterday = datetime.utcnow().date() - timedelta(days=1)
    
    # Seed a global aggregate record
    agg = DailyUsageAggregate(
        date=yesterday,
        scope='global',
        conversations=10,
        searches=5,
        workflows_completed=3,
        tokens_input=1000,
        tokens_output=500
    )
    agg.save()
"

# 4. Trigger Sync Task from Instance Context
echo -e "${BLUE}4. Triggering Push Telemetry Task...${NC}"
export MAIN_SERVER_URL="http://127.0.0.1:$MAIN_PORT"
export FLASK_MONGO_DB="$INSTANCE_DB"
export INSTANCE_NAME="TestClient"
export SYNC_API_KEY="$SYNC_KEY"

uv run python3 -c "
from app import create_app
from app.tasks.sync import push_telemetry

app = create_app()
with app.app_context():
    result = push_telemetry()
    print(f'Sync Result: {result}')
"

# 5. Verify Data on Main Server DB
echo -e "${BLUE}5. Verifying Data on Main Server...${NC}"
export FLASK_MONGO_DB="$MAIN_DB"
export IS_MAIN_SERVER=true

uv run python3 -c "
from app import create_app
from app.models import DailyUsageAggregate
import sys

app = create_app()
with app.app_context():
    # Verify the record exists and has correct instance_name and data
    agg = DailyUsageAggregate.objects(scope='global', instance_name='TestClient').first()
    if agg and agg.conversations == 10:
        print(f'SUCCESS: Found synced record from {agg.instance_name}')
        sys.exit(0)
    else:
        print('FAILURE: Synced record not found or data mismatch')
        sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}TEST PASSED${NC}"
else
    echo -e "${RED}TEST FAILED${NC}"
fi
