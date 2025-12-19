#!/bin/bash

# --- Configuration ---
PROD_PORT=5002
DEV_PORT=5003
SYNC_KEY="secret-test-key-123"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Kill existing processes on these ports to avoid conflicts
echo -e "${YELLOW}Cleaning up old processes on ports $PROD_PORT and $DEV_PORT...${NC}"
lsof -ti:$PROD_PORT | xargs kill -9 2>/dev/null
lsof -ti:$DEV_PORT | xargs kill -9 2>/dev/null

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}      Starting Vandalizer Simulation Environment  ${NC}"
echo -e "${BLUE}=================================================${NC}"

# ---------------------------------------------------------
# 1. Start PROD Server (The "Main" Server)
# ---------------------------------------------------------
echo -e "${GREEN}[PROD] Starting Main Server on Port $PROD_PORT...${NC}"
echo -e "       Env: production"
echo -e "       DB:  osp (from ProductionConfig)"

(
  export FLASK_APP=run.py
  # Using 'production' loads ProductionConfig -> MONGO_DB = "osp"
  export FLASK_ENV=production
  export PORT=$PROD_PORT
  
  export IS_MAIN_SERVER=true
  export SYNC_API_KEY=$SYNC_KEY
  
  # Log to a file to keep console clean, run in background
  uv run run.py > logs/prod_server.log 2>&1
) &
PROD_PID=$!

# ---------------------------------------------------------
# 2. Start DEV Instance (The "Client" Instance)
# ---------------------------------------------------------
echo -e "${GREEN}[DEV]  Starting Dev Instance on Port $DEV_PORT...${NC}"
echo -e "       Env: testing"
echo -e "       DB:  osp-staging (from TestingConfig)"
echo -e "       Pointing to: http://localhost:$PROD_PORT"

(
  export FLASK_APP=run.py
  # Using 'testing' loads TestingConfig -> MONGO_DB = "osp-staging"
  # This ensures data isolation from the Prod server
  export FLASK_ENV=testing
  export PORT=$DEV_PORT
  
  export IS_MAIN_SERVER=false
  export MAIN_SERVER_URL=http://localhost:$PROD_PORT
  export SYNC_API_KEY=$SYNC_KEY
  
  # Log to a file
  uv run run.py > logs/dev_server.log 2>&1
) &
DEV_PID=$!

# ---------------------------------------------------------
# 3. Wait for boot and show status
# ---------------------------------------------------------
echo -e "${YELLOW}Waiting for servers to boot...${NC}"
sleep 5

if ps -p $PROD_PID > /dev/null; then
   echo -e "${GREEN}✓ PROD Server running (PID: $PROD_PID)${NC} -> http://localhost:$PROD_PORT"
else
   echo -e "${RED}✗ PROD Server failed to start. Check logs/prod_server.log${NC}"
fi

if ps -p $DEV_PID > /dev/null; then
   echo -e "${GREEN}✓ DEV Server running  (PID: $DEV_PID)${NC} -> http://localhost:$DEV_PORT"
else
   echo -e "${RED}✗ DEV Server failed to start. Check logs/dev_server.log${NC}"
fi

# Wait for user to exit
wait
