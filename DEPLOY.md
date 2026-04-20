# Deploying Vandalizer (FastAPI + React)

## Quick Start

The fastest way to get Vandalizer running locally is the interactive setup wizard. It walks you through environment configuration, secret generation, service startup, admin account creation, and database seeding:

```bash
git clone https://github.com/ui-insight/vandalizer.git
cd vandalizer
./setup.sh
```

### Manual Docker Compose Setup

If you prefer to run each step yourself:

```bash
# 1. Clone the repository
git clone https://github.com/ui-insight/vandalizer.git
cd vandalizer

# 2. Configure the backend environment
cp backend/.env.example backend/.env
# Edit backend/.env — at minimum set:
#   JWT_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(64))">
# LLM API keys and endpoints are configured per-model via the admin UI, not in .env.

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

The frontend is available at `http://localhost` (port 80) and the API at `http://localhost:8001`. Log in with the admin credentials you provided to the bootstrap command.

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

Vandalizer is designed to be lightweight. The application itself (all Docker services plus the OS) consumes roughly **8 GB of RAM** in production. A machine with **16 GB of RAM** comfortably handles a departmental deployment; smaller teams can run on as little as **10 GB**.

These requirements cover the Vandalizer application only — they assume LLM inference and OCR happen via external API calls (OpenAI, Azure, Ollama on a separate host, etc.). The server does **not** need a GPU when using external LLM providers.

| Deployment size | CPU | RAM | Storage | Users |
|----------------|-----|-----|---------|-------|
| Small team | 4 cores | 8–10 GB | 50 GB | < 50 |
| Department / college | 8 cores | 16 GB | 100 GB+ | 50–500 |

Storage needs depend primarily on the volume and size of uploaded documents. Plan for growth if users will upload large PDFs or office files regularly.

### Local LLM & OCR Hosting (Optional)

If you want a fully self-contained installation with no external API dependencies, you can host your own LLM and OCR services alongside Vandalizer. This is a separate infrastructure concern with significantly different hardware requirements.

**What this gives you:** Complete data sovereignty — no document content or prompts leave your network. Required for institutions with strict data-handling policies or air-gapped environments.

**Hardware requirements for local LLM hosting:**

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU | NVIDIA GPU with 16+ GB VRAM | NVIDIA GPU with 24–80 GB VRAM |
| System RAM | 32 GB | 64 GB+ |
| Storage | 100 GB SSD (for model weights) | 500 GB+ NVMe SSD |

The exact requirements depend on the model size and concurrency you need. A 7B-parameter model can run on a single consumer GPU; 70B+ models need high-VRAM GPUs or multi-GPU setups.

**Supported hardware configurations:**

- **Apple Mac Mini / Mac Studio** (M-series) — Good for small teams. Unified memory architecture makes these surprisingly capable for local inference. 64 GB+ unified memory recommended.
- **Workstation with NVIDIA GPU** — A single RTX 4090 (24 GB VRAM) or A6000 (48 GB VRAM) handles most models.
- **NVIDIA DGX / multi-GPU servers** — For high-concurrency deployments or very large models (70B+).
- **Rack-mounted GPU servers** — Standard enterprise option. Any server with one or more NVIDIA datacenter GPUs (A100, H100, L40S).

**Software stack for local inference:**

Vandalizer connects to local LLMs through its standard model configuration (Admin → System Config → Models). Common local inference servers include:

- [**Ollama**](https://ollama.ai) — Simplest setup. Install, pull a model, point Vandalizer at the Ollama endpoint. Protocol: `ollama`.
- [**vLLM**](https://docs.vllm.ai) — Higher throughput for concurrent users. Exposes an OpenAI-compatible API. Protocol: `openai` or `vllm`.
- [**llama.cpp server**](https://github.com/ggerganov/llama.cpp) — Lightweight, runs on CPU or GPU. OpenAI-compatible API.

For OCR, self-hosted options include [Marker](https://github.com/VikParuchuri/marker), [Surya](https://github.com/VikParuchuri/surya), or a Tesseract wrapper. These can run on the same GPU server or on a separate machine. See the [PDF Processing & OCR](#pdf-processing--ocr) section for configuration details.

**Deployment topology:** The local LLM/OCR server does **not** need to be the same machine as Vandalizer. A common setup is two servers — one lightweight machine for Vandalizer (16 GB RAM, no GPU) and one GPU-equipped machine for inference — connected over the local network.

### Database Name

The MongoDB database is named `vandalizer` by default. The name is configurable via the `MONGO_DB` environment variable and has no effect on functionality.

### Production Configuration

Create `backend/.env` with the following variables:

```env
MONGO_HOST=mongodb://mongo:27017/
MONGO_DB=vandalizer
REDIS_HOST=redis
JWT_SECRET_KEY=<generate-a-strong-random-secret>
CONFIG_ENCRYPTION_KEY=<generate-a-fernet-key>
UPLOAD_DIR=/app/static/uploads
FRONTEND_URL=https://vandalizer.example.edu
ENVIRONMENT=production
CHROMADB_HOST=chromadb:8000
CHROMADB_PERSIST_DIR=../app/static/db
```

Key notes:

- **`JWT_SECRET_KEY`**: Generate a strong secret with `python -c "import secrets; print(secrets.token_urlsafe(64))"`. This signs all authentication tokens — keep it secret and do not reuse across environments.
- **`CONFIG_ENCRYPTION_KEY`**: Fernet key used to encrypt LLM API keys and OAuth secrets stored in MongoDB. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. If omitted, `bootstrap_install.py` auto-generates one and prints it — copy it into `.env` to persist across restarts. Without this key, secrets are stored in plaintext.
- **`MONGO_HOST`**: Use the Docker service name (`mongo`) if running in Docker Compose, or the hostname/IP of your MongoDB instance if externalized.
- **`UPLOAD_DIR`**: Directory where user-uploaded documents are stored. Must be a persistent volume.
- **`FRONTEND_URL`**: The public URL users will access. Used for CORS and redirect configuration.
- **`CHROMADB_HOST`**: Hostname:port of the Chroma server. Required for any multi-process deployment — the Python `PersistentClient` is not process-safe for concurrent writers, so FastAPI workers + Celery workers sharing a persist directory will hit "attempt to write a readonly database" errors. Leave unset only for single-process local development.

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

### PDF Processing & OCR

Vandalizer extracts text from PDFs using one of two approaches, both configured in the admin UI:

**OCR endpoint** — Navigate to **Admin → System Config → Endpoints** and set the **OCR Endpoint** URL. This should point to an HTTP service that accepts a multipart PDF file upload and returns extracted plain text. This is the recommended approach for scanned documents. Any service implementing this interface works — self-hosted Marker, Surya, a Tesseract wrapper, or a wrapper around a cloud OCR API (Azure Document Intelligence, AWS Textract, Google Document AI).

Without an OCR endpoint, Vandalizer falls back to direct text extraction via PyPDF2. This works for digitally-created PDFs but produces poor results on scanned documents.

**Multimodal LLM (alternative)** — For models that support vision (e.g., GPT-4o, Claude), Vandalizer can send PDF pages as images directly to the LLM instead of using OCR. Enable this under **Admin → System Config → Extraction** by toggling **Use Document Images (Multimodal)**. This works well for visually complex documents but uses more LLM tokens.

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

Run the status script to check all services, health, and seed data:

```bash
./status.sh
```

Then confirm these manually:

- [ ] Login works with the bootstrap admin credentials
- [ ] At least one LLM provider is configured under Admin → System Config → Models
- [ ] OCR endpoint is configured under Admin → System Config → Endpoints (if processing scanned PDFs)
- [ ] File upload completes successfully
- [ ] Extraction workflow runs to completion (confirms Celery workers are connected)
- [ ] Chat with a document works (confirms RAG pipeline end-to-end)

If anything is broken, run `./setup.sh --repair` to diagnose and fix.

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

mongodump --uri="$MONGO_HOST" --db=vandalizer --gzip --out="$BACKUP_DIR/$TIMESTAMP"

# Prune old backups
find "$BACKUP_DIR" -type d -mtime +$RETENTION_DAYS -exec rm -rf {} +
```

Restore:

```bash
mongorestore --uri="$MONGO_HOST" --db=vandalizer --gzip "$BACKUP_DIR/$TIMESTAMP/vandalizer"
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
