# Deploying Vandalizer Next (FastAPI) Over the Flask App

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

**On the production server, from `vandalizer-next/backend/`:**

```bash
# Install dependencies (pymongo is the only requirement)
uv sync

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
cd vandalizer-next/frontend

npm install
npm run build
```

This produces a `dist/` directory with static assets. In production, these will be served by a reverse proxy (nginx) or by the FastAPI app itself.

## Step 3: Configure the FastAPI Backend

Create `vandalizer-next/backend/.env` based on your production environment:

```env
MONGO_HOST=mongodb://mongo:27017/
MONGO_DB=osp
REDIS_HOST=redis
JWT_SECRET_KEY=<generate-a-strong-random-secret>
UPLOAD_DIR=/app/static/uploads
FRONTEND_URL=https://vandalizer.uidaho.edu
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

Create `vandalizer-next/backend/Dockerfile`:

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
    env_file: ./vandalizer-next/backend/.env
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
      - ./vandalizer-next/frontend/dist:/usr/share/nginx/html:ro
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
    server_name vandalizer.uidaho.edu;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name vandalizer.uidaho.edu;

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
cd vandalizer-next/frontend && npm install && npm run build && cd ../..
docker compose build api
docker compose up -d api nginx

# 3. Verify
curl -k https://vandalizer.uidaho.edu/api/health
# → {"status":"ok"}
```

### Option B: Blue-green (zero downtime)

```bash
# 1. Build everything while Flask is still running
cd vandalizer-next/frontend && npm install && npm run build && cd ../..
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

- [ ] `GET /api/health` returns `{"status":"ok"}`
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
