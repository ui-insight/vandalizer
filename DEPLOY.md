# Deploying Vandalizer (FastAPI + React)

## Quick Start with Docker Compose

The fastest way to get Vandalizer running locally:

```bash
# 1. Clone the repository
git clone https://github.com/ui-insight/vandalizer.git
cd vandalizer

# 2. Configure the backend environment
cp backend/.env.example backend/.env
# Edit backend/.env — at minimum set:
#   OPENAI_API_KEY=your-key-here
#   JWT_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(64))">

# 3. Build and start everything
docker compose up --build -d

# 4. Bootstrap the first admin account and optional shared default team
docker compose exec \
  -e ADMIN_EMAIL=admin@example.edu \
  -e ADMIN_PASSWORD='change-me-now' \
  -e ADMIN_NAME='Initial Admin' \
  -e DEFAULT_TEAM_NAME='Research Administration' \
  api python bootstrap_install.py

# 5. Verify
curl http://localhost:8001/api/health
# → {"status":"ok","checks":{...}}
```

The frontend is available at `http://localhost:80` and proxies API requests to the backend on port 8001.

What the bootstrap command does:

- creates or updates the initial admin account
- optionally creates a shared default team and marks it as the auto-join team for new users
- reuses an existing default team only when it is already owned by the bootstrap admin

First-login behavior:

- every user gets a personal team
- if `DEFAULT_TEAM_NAME` is set, new users also auto-join that shared team on first registration or SSO login
- the bootstrap admin keeps both the personal team and the shared default team; switch teams in the UI if you want the shared team to be your active workspace

Persistence in the default compose setup:

- `mongo-data`: MongoDB records
- `uploads`: uploaded files
- `chroma-data`: vector index / embeddings

Common operator commands:

```bash
docker compose restart api celery frontend
docker compose logs -f api
docker compose down
```

For backup, restore, upgrade, and rollback of the current Docker Compose install path, use [OPERATIONS.md](OPERATIONS.md).

Before tagging or handing off an operator-facing release, use [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) to rehearse the bootstrap flow and curate the matching release notes.

To stop all services:
```bash
docker compose down
```

To start only the infrastructure (for local development):
```bash
docker compose up -d redis mongo chromadb
```

---

## Production Deployment Guide

This guide walks through replacing the Flask app with the FastAPI backend + React frontend in production. Both apps share the same MongoDB database, Redis, ChromaDB, Celery workers, and upload directory — so this is a code swap, not a data migration.

## Prerequisites

- Python 3.11–3.12 (`uv` for dependency management)
- Node.js >= 20 (for building the React frontend)
- Docker and Docker Compose (for infrastructure services)
- Access to the production server running the Flask app
- The data migration changes from the `experiment/react` branch (collection name fixes, `migrate.py`)

## What's Shared Between Flask and FastAPI

| Resource | Details |
|----------|---------|
| MongoDB | Same `osp` database, same collections |
| Redis | Same instance — broker `redis://host:6379/0`, backend `redis://host:6379/1` |
| ChromaDB | Same vector store (path now aligned to `../app/static/db`) |
| Celery workers | FastAPI dispatches tasks by name to the existing Flask workers — no new workers needed |
| File uploads | Same directory (`static/uploads/`) |
| Passwords | Both use `werkzeug.security` — existing credentials work |

## Step 1: Run the LibraryItem Migration

The Flask app stores `LibraryItem.obj` as a MongoEngine `GenericReferenceField`. The FastAPI app expects flat `item_id` and `kind` fields. A migration script handles this conversion.

**On the production server, from `backend/`:**

```bash
# Install dependencies (pymongo is the only requirement)
uv sync --extra dev

# Preview what will change
python migrate.py --dry-run --mongo-host mongodb://localhost:27017/ --db-name osp

# If the output looks correct, apply the migration
python migrate.py --mongo-host mongodb://localhost:27017/ --db-name osp
```

The script:
- Finds `library_item` documents where `obj` exists but `item_id` does not
- Extracts the ObjectId from the GenericReferenceField structure into `item_id`
- Maps the `_cls` field to the FastAPI `kind` enum (e.g. `"searchset"` → `"search_set"`)
- Does **not** remove the `obj` field — Flask continues to work during the transition

If using Docker Compose, the MongoDB host port is `27018`:
```bash
python migrate.py --mongo-host mongodb://localhost:27018/ --db-name osp
```

## Step 2: Build the React Frontend

```bash
cd frontend
npm ci
npm run build
```

This produces a `dist/` directory with static assets. In production, these will be served by a reverse proxy (nginx) or by the FastAPI app itself.

## Step 3: Configure the FastAPI Backend

Create `backend/.env` based on your production environment:

```env
MONGO_HOST=mongodb://mongo:27017/
MONGO_DB=osp
REDIS_HOST=redis
JWT_SECRET_KEY=<generate-a-strong-random-secret>
UPLOAD_DIR=/app/static/uploads
FRONTEND_URL=https://vandalizer.example.edu
ENVIRONMENT=production
OPENAI_API_KEY=<your-key>
CHROMADB_PERSIST_DIR=../app/static/db
```

Key settings:
- `JWT_SECRET_KEY`: Generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"`
- `UPLOAD_DIR`: Must point to the same upload directory the Flask app and Celery workers use
- `CHROMADB_PERSIST_DIR`: Points to the Flask app's existing ChromaDB data (`../app/static/db`)
- `MONGO_HOST`: Use the Docker service name (`mongo`) if running in Docker Compose, or `localhost:27018` if connecting from the host

## Step 4: Create a Dockerfile for the FastAPI Backend

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.12 AS builder

RUN pip install uv

WORKDIR /app

COPY pyproject.toml ./

RUN uv sync

FROM python:3.12-slim AS runtime

WORKDIR /app

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

COPY app ./app

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4"]
```

## Step 5: Update Docker Compose

Replace the Flask `web` service and add a `frontend` build step. Edit `compose.yaml`:

```yaml
services:
  redis:
    image: redis/redis-stack:latest
    ports:
      - "6379:6379"
    networks:
      - vandalizer

  mongo:
    image: mongo:latest
    ports:
      - "27018:27017"
    networks:
      - vandalizer

  chromadb:
    image: chromadb/chroma:latest
    ports:
      - "8000:8000"
    networks:
      - vandalizer
    volumes:
      - chroma-data:/chroma/chroma
    environment:
      - IS_PERSISTENT=TRUE
      - ANONYMIZED_TELEMETRY=FALSE

  # Celery workers — still runs from the Flask codebase
  celery:
    build:
      context: .
      dockerfile: Dockerfile
    depends_on:
      - redis
      - mongo
      - chromadb
    env_file: .env
    environment:
      - REDIS_HOST=redis
      - MONGO_HOST=mongodb://mongo:27017
      - CHROMA_HOST=chromadb
      - CHROMA_PORT=8000
      - USE_CHROMA_SERVER=true
    networks:
      - vandalizer
    volumes:
      - uploads:/app/static/uploads
    entrypoint: sh run_celery.sh

  # FastAPI backend (replaces the Flask "web" service)
  api:
    build:
      context: ./vandalizer-next/backend
      dockerfile: Dockerfile
    ports:
      - "8001:8001"
    depends_on:
      - redis
      - mongo
      - chromadb
    env_file: ./backend/.env
    environment:
      - REDIS_HOST=redis
      - MONGO_HOST=mongodb://mongo:27017
      - CHROMADB_PERSIST_DIR=/app/static/db
      - UPLOAD_DIR=/app/static/uploads
    networks:
      - vandalizer
    volumes:
      - uploads:/app/static/uploads
      - chroma-data:/app/static/db

  # Nginx serves the React frontend and proxies /api to FastAPI
  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
      - "80:80"
    depends_on:
      - api
    networks:
      - vandalizer
    volumes:
      - ./frontend/dist:/usr/share/nginx/html:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./certs:/etc/nginx/certs:ro

networks:
  vandalizer:
    external: false
    ipam:
      driver: default
      config:
        - subnet: 10.20.0.0/24

volumes:
  chroma-data:
    driver: local
  uploads:
    driver: local
```

## Step 6: Create Nginx Config

Create `nginx.conf` at the repo root:

```nginx
server {
    listen 80;
    server_name vandalizer.example.edu;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name vandalizer.example.edu;

    ssl_certificate     /etc/nginx/certs/cert.pem;
    ssl_certificate_key /etc/nginx/certs/key.pem;

    client_max_body_size 200M;

    # API requests → FastAPI backend
    location /api/ {
        proxy_pass http://api:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE/streaming support (for chat endpoints)
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }

    # Uploaded files (served directly by nginx)
    location /static/uploads/ {
        alias /app/static/uploads/;
    }

    # React SPA — serve index.html for all other routes
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
}
```

## Step 7: Deploy

### Option A: In-place cutover (brief downtime)

```bash
# 1. Stop the Flask app
docker compose down web

# 2. Build and start the new services
cd frontend && npm install && npm run build && cd ../..
docker compose build api
docker compose up -d api nginx

# 3. Verify
curl -k https://vandalizer.example.edu/api/health
# → {"status":"ok"}
```

### Option B: Blue-green (zero downtime)

```bash
# 1. Build everything while Flask is still running
cd frontend && npm install && npm run build && cd ../..
docker compose build api

# 2. Start FastAPI on a different port (it shares the DB safely)
docker compose up -d api

# 3. Test against the new backend directly
curl http://localhost:8001/api/health

# 4. Once verified, switch nginx upstream from Flask to FastAPI
#    (update nginx.conf proxy_pass, then reload)
docker compose exec nginx nginx -s reload

# 5. Stop the Flask web service
docker compose down web
```

## Step 8: Post-Deploy Verification

Run through this checklist after switching over:

- [ ] `GET /api/health` returns `"status":"ok"` and populated health checks
- [ ] Login works with an existing user's credentials
- [ ] Documents list loads (confirms MongoDB collection names match)
- [ ] Document search returns results (confirms ChromaDB path is correct)
- [ ] Library page shows items (confirms LibraryItem migration worked)
- [ ] File upload works (confirms upload directory is shared correctly)
- [ ] Extraction workflow runs to completion (confirms Celery task dispatch works)
- [ ] Chat with a document works (confirms RAG pipeline end-to-end)

## User Impact

- **Users must log in once** after the switch. Flask used server-side sessions; FastAPI uses JWT cookies. Existing passwords work — only the session is new.
- **No data loss**. Both apps read the same database. The LibraryItem migration adds new fields without removing old ones.

## Rollback

If something goes wrong, rolling back is straightforward:

1. **Stop FastAPI, restart Flask:**
   ```bash
   docker compose down api nginx
   docker compose up -d web
   ```

2. **No database rollback needed.** The collection name changes were in FastAPI code only — Flask still uses its own MongoEngine `meta` names. The LibraryItem migration added `item_id` fields but left the `obj` GenericReferenceField intact, so Flask reads its data normally.

3. **ChromaDB and uploads** were never moved — both apps point to the same paths.

## Architecture After Migration

```
                 ┌─────────┐
   Browser ──────│  nginx   │
                 │  :443    │
                 └────┬─────┘
                      │
            ┌─────────┴──────────┐
            │                    │
     /api/* │             /* (SPA)
            │                    │
     ┌──────▼──────┐    ┌───────▼────────┐
     │   FastAPI   │    │  React static  │
     │   :8001     │    │  (nginx files) │
     └──────┬──────┘    └────────────────┘
            │
   ┌────────┼─────────┬──────────┐
   │        │         │          │
┌──▼──┐ ┌──▼───┐ ┌───▼────┐ ┌──▼─────┐
│Mongo│ │Redis │ │ChromaDB│ │Celery  │
│:27017│ │:6379 │ │:8000   │ │workers │
└─────┘ └──────┘ └────────┘ └────────┘
```

---

## Backup and Recovery

### MongoDB

Daily backups using `mongodump` with 30-day retention:

```bash
#!/bin/bash
# /etc/cron.daily/vandalizer-mongo-backup
BACKUP_DIR="/backups/mongodb"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mongodump --uri="$MONGO_HOST" --db=osp --gzip --out="$BACKUP_DIR/$TIMESTAMP"

# Prune old backups
find "$BACKUP_DIR" -type d -mtime +$RETENTION_DAYS -exec rm -rf {} +
```

Restore:

```bash
mongorestore --uri="$MONGO_HOST" --db=osp --gzip "$BACKUP_DIR/$TIMESTAMP/osp"
```

### ChromaDB

Weekly rsync of the persistent directory:

```bash
#!/bin/bash
# /etc/cron.weekly/vandalizer-chromadb-backup
rsync -a --delete /app/static/db/ /backups/chromadb/
```

ChromaDB can be rebuilt from source documents if the backup is lost, but this is time-consuming.

### Uploaded Files

Daily rsync of the uploads directory:

```bash
#!/bin/bash
# /etc/cron.daily/vandalizer-uploads-backup
BACKUP_DIR="/backups/uploads"
rsync -a --delete /app/static/uploads/ "$BACKUP_DIR/"
```

### Redis

No backup needed. Redis is used as a transient Celery broker and result backend. All task state is ephemeral and will be regenerated on restart. Pending tasks in the queue will be lost on Redis failure but can be re-submitted.

### Recovery Order

1. Restore MongoDB first (contains all application state)
2. Restore uploaded files
3. Restore ChromaDB (or re-ingest documents to rebuild vector store)
4. Start Redis (no restore needed)
5. Start application services
