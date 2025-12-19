#!/bin/bash

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Cleanup function to stop both sets of workers when you Ctrl+C
cleanup() {
    echo -e "\n${YELLOW}Stopping all simulation workers...${NC}"
    
    # Stop Dev
    export INSTANCE_NAME="dev"
    ./run_celery.sh stop
    
    # Stop Prod
    export INSTANCE_NAME="prod"
    ./run_celery.sh stop
    
    exit
}

# Trap Ctrl+C
trap cleanup SIGINT

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}      Starting Celery Worker Simulation           ${NC}"
echo -e "${BLUE}=================================================${NC}"

# ---------------------------------------------------------
# 1. Start PROD Workers
# ---------------------------------------------------------
echo -e "${GREEN}[PROD] Starting Workers...${NC}"
echo -e "       DB: osp | Redis DB: 0 & 1"

(
  export FLASK_ENV=production
  export INSTANCE_NAME="prod"
  
  # Standard Redis DBs for Prod
  export CELERY_BROKER_URL="redis://localhost:6379/0"
  export CELERY_RESULT_BACKEND="redis://localhost:6379/1"
  
  ./run_celery.sh start
)

# ---------------------------------------------------------
# 2. Start DEV Workers
# ---------------------------------------------------------
echo -e "\n${GREEN}[DEV]  Starting Workers...${NC}"
echo -e "       DB: osp-staging | Redis DB: 2 & 3"

(
  export FLASK_ENV=testing
  export INSTANCE_NAME="dev"
  
  # Different Redis DBs to ensure queue isolation
  export CELERY_BROKER_URL="redis://localhost:6379/2"
  export CELERY_RESULT_BACKEND="redis://localhost:6379/3"
  
  ./run_celery.sh start
)

echo -e "\n${BLUE}=================================================${NC}"
echo -e "${GREEN}Simulation Running!${NC}"
echo -e "Logs are located in:"
echo -e "  - Prod: ./logs/prod/"
echo -e "  - Dev:  ./logs/dev/"
echo -e "${BLUE}=================================================${NC}"
echo -e "Press ${YELLOW}Ctrl+C${NC} to stop all workers."

# Keep script running to maintain the trap
while true; do sleep 1; done
