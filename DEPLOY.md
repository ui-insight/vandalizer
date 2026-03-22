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
#   JWT_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(64))">
# LLM API keys and endpoints are configured per-model via System Config in the admin UI.

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

## Production Deployment

This section covers what you need to know when deploying Vandalizer for real users in a university environment.

### Resource Requirements

Vandalizer's server-side workload is document processing, API serving, and background task execution. LLM inference happens externally via API calls (OpenAI, Azure, etc.), so the server does not need a GPU.

| Deployment size | CPU | RAM | Storage | Users |
|----------------|-----|-----|---------|-------|
| Small team | 4 cores | 8 GB | 50 GB | < 50 |
| Department / college | 8 cores | 16 GB | 100 GB+ | 50–500 |

Storage needs depend primarily on the volume and size of uploaded documents. Plan for growth if users will upload large PDFs or office files regularly.

### Database Name

The MongoDB database is named `osp` by default — short for Office of Sponsored Programs, the original use case at the University of Idaho. The name is configurable via the `MONGO_DB` environment variable and has no effect on functionality.

### Production Configuration

Create `backend/.env` with the following variables:

```env
MONGO_HOST=mongodb://mongo:27017/
MONGO_DB=osp
REDIS_HOST=redis
JWT_SECRET_KEY=<generate-a-strong-random-secret>
UPLOAD_DIR=/app/static/uploads
FRONTEND_URL=https://vandalizer.example.edu
ENVIRONMENT=production
CHROMADB_PERSIST_DIR=../app/static/db
```

Key notes:

- **`JWT_SECRET_KEY`**: Generate a strong secret with `python -c "import secrets; print(secrets.token_urlsafe(64))"`. This signs all authentication tokens — keep it secret and do not reuse across environments.
- **`MONGO_HOST`**: Use the Docker service name (`mongo`) if running in Docker Compose, or the hostname/IP of your MongoDB instance if externalized.
- **`UPLOAD_DIR`**: Directory where user-uploaded documents are stored. Must be a persistent volume.
- **`FRONTEND_URL`**: The public URL users will access. Used for CORS and redirect configuration.

### LLM Configuration

LLM models are not configured through environment variables. Instead, they are managed entirely through the admin UI under **System Config**.

Each model entry includes:

- **Name** — a display label (e.g., "GPT-4o", "Claude Sonnet")
- **API key** — the key for that provider
- **Endpoint URL** — the API base URL
- **Protocol** — `openai`, `ollama`, or `vllm`

This design supports any OpenAI-compatible API, including:

- OpenAI
- Azure OpenAI
- Ollama (local models)
- vLLM
- OpenRouter
- Any other provider exposing an OpenAI-compatible endpoint

Models can be added, removed, or rotated at any time without restarting the application.

### TLS / HTTPS

In production, place a reverse proxy in front of the application to terminate TLS. Nginx, Caddy, and Traefik all work well. The example below uses nginx:

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

### Post-Deploy Verification

After deployment, confirm these are working:

- [ ] `GET /api/health` returns `"status":"ok"` with populated health checks
- [ ] Login works with the bootstrap admin credentials
- [ ] Documents list loads in the UI
- [ ] File upload completes successfully
- [ ] Extraction workflow runs to completion (confirms Celery workers are connected)
- [ ] Chat with a document works (confirms RAG pipeline end-to-end)

### Scaling

- **Celery workers** can be scaled independently. Add more replicas or run separate containers per queue (e.g., `uploads`, `extraction`, `quality`) to isolate workloads.
- **FastAPI workers** are configured via the `--workers` flag in the uvicorn command. The default is 4; increase for higher API concurrency.
- **MongoDB and Redis** can be externalized to managed services (MongoDB Atlas, AWS ElastiCache, etc.) by updating `MONGO_HOST` and `REDIS_HOST`.

## Architecture

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
