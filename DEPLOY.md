# Deploying Vandalizer (FastAPI + React)

## Recommended: the interactive setup wizard

`./setup.sh` is the supported install path for **both** local evaluation and production deployments on a real server. It handles environment configuration, secret generation (`JWT_SECRET_KEY`, `CONFIG_ENCRYPTION_KEY`), Docker builds, service startup, admin account creation, and verified-catalog seeding in one session. When you run it on a server, choose the **production** profile when prompted and give it your public URL and web port — everything else is filled in for you.

```bash
git clone https://github.com/ui-insight/vandalizer.git
cd vandalizer
./setup.sh
```

After the first run, the same script is the entry point for ongoing operations: `./setup.sh --repair`, `--upgrade`, `--redeploy`. See the [README](README.md#interactive-setup-recommended) for the full menu of maintenance commands.

The frontend is available at the URL you configured (defaults to `http://localhost`) and the API at `http://localhost:8001` when setup completes.

### Escape hatch: manual Docker Compose

This path exists for operators who need to script each step themselves (CI builds, golden images, configuration-management tools). The interactive wizard above is the supported path for everyone else.

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

**Install path:** use `./setup.sh` from the project root and select the **production** profile when prompted. It will ask for your public URL (e.g. `https://vandalizer.example.edu`) and web port, then generate `JWT_SECRET_KEY` and `CONFIG_ENCRYPTION_KEY`, build images, bring up Mongo / Redis / ChromaDB / API / Celery / frontend, create your admin account, and seed the verified catalog. The remaining subsections here cover production-specific decisions (sizing, optional self-hosted LLM/OCR, TLS termination, scaling) that sit *around* setup.sh — they don't replace it.

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

### Branding your deployment

Vandalizer white-labels to your institution. Sign in as an admin and open **System Config → UI Theme & Branding** (`/admin`) to set:

- **Organization name** — replaces "Vandalizer" in the header, sign-in page, browser tab, and chat greeting.
- **Logo** — a wordmark image (PNG with transparency works best) shown in the header, sign-in page, and the public landing page.
- **Icon / mascot** — a small square mark shown beside the logo and used as the browser-tab favicon. Leave it blank on a branded deployment to hide the default Joe Vandal mark, or upload your own.
- **Brand color** — the highlight color used throughout the UI, and in the styling of outgoing email.

All of these are stored in the `SystemConfig` document in MongoDB and applied at runtime — **no rebuild or redeploy is needed**; changes take effect as soon as you save. Logos and icons are stored inline (as data URLs), so there is no separate asset bucket to provision or back up beyond the MongoDB volume you already back up.

Because the project is open source under GPL v3, the footer keeps a small "Powered by Vandalizer" credit and the NSF GRANTED acknowledgement whenever custom branding is in effect, so creator and funder lineage stay visible.

### Anonymous usage telemetry (optional)

Vandalizer can send the maintainers an **opt-in, anonymous** daily heartbeat
(deployment count, version, and coarse usage buckets — never document content,
names, or emails). It is **off by default**; `./setup.sh` asks before enabling
it, and you can optionally self-identify or point it at your own collector. See
[docs/telemetry.md](docs/telemetry.md) for the full disclosure and the
`TELEMETRY_*` variables.

### Production Configuration (reference)

`./setup.sh` writes the production `backend/.env` for you. This subsection is a **reference** for what those variables mean — useful when you need to edit `.env` later, externalize a database, or rebuild the file by hand on the manual path.

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
- **Protocol** — `openai`, `anthropic`, `openrouter`, `ollama`, or `vllm` (or leave blank for auto-detect)
- **Context Window** — the model's real serving token limit. Use the **Probe endpoint** button to read it from the configured endpoint (`max_model_len` for vLLM, `context_length` for OpenRouter, `model_info` for Ollama). Anthropic and plain-OpenAI endpoints do not expose this — set it by hand. The chat and workflow context-budget planner trims against this value, so a value larger than what the endpoint was actually started with (e.g. vLLM `--max-model-len`) causes mid-workflow `400` errors.

The `anthropic` protocol uses Anthropic's native Messages API for first-class
support of Claude models (tool use, streaming, native thinking). The
`openrouter` protocol routes through OpenRouter's OpenAI-compatible gateway
with automatic app attribution. The other three (`openai`, `ollama`, `vllm`)
all speak OpenAI-compatible HTTP, so any provider that exposes that interface
works.

#### Provider compatibility

The rule of thumb: if a provider exposes an OpenAI-compatible endpoint (the
`/chat/completions` shape with a bearer API key), it works. Popular options:

| Provider | Protocol | Endpoint URL | Status / notes |
| --- | --- | --- | --- |
| **OpenAI** | `openai` | leave blank (default) | Fully supported. |
| **Azure OpenAI** | `openai` | your Azure resource base URL (e.g. `https://<resource>.openai.azure.com/openai/v1/`) | Supported. The newer Azure `v1` endpoint works directly; the older per-deployment URL with an `api-version` query param may need attention. |
| **Anthropic (Claude)** | `anthropic` | leave blank (defaults to `https://api.anthropic.com`) | Native Messages API — first-class tool use, streaming, and thinking. |
| **OpenRouter** | `openrouter` | leave blank (defaults to `https://openrouter.ai/api/v1`) | Native gateway with app attribution. Reaches many models through one key, including Gemini via `google/gemini-...`. |
| **Google Gemini (direct)** | `openai` | `https://generativelanguage.googleapis.com/v1beta/openai/` | Works through Gemini's OpenAI-compatibility layer (not its native API). Smoke-test structured extraction before relying on it. |
| **Ollama (local)** | `ollama` | `http://<host>:11434` | Local models; air-gap friendly. |
| **vLLM (self-hosted)** | `vllm` | `http://<host>:<port>` | Set Context Window to match the server's `--max-model-len`. |
| **Any OpenAI-compatible server** | `openai` | provider base URL | Works if it speaks `/chat/completions` with bearer-token auth. |
| **Microsoft 365 Copilot** | — | — | **Not supported.** This is an end-user product (the assistant in Word/Teams/Outlook), not a developer model API — there is no endpoint or key to point Vandalizer at. For Microsoft-hosted models, use **Azure OpenAI** instead. |

Notes that apply across providers:

- **Custom HTTP headers** beyond the API key are not configurable in the UI. Providers needing only a bearer key (the common case) are unaffected.
- **Structured output / tool calling** is exercised heavily by extractions and workflows. Native `openai`/`anthropic`/`openrouter` paths are well-proven; for other OpenAI-compatibility layers (e.g. Gemini), run a real extraction as a smoke test before calling them production-ready.

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
