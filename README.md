# Vandalizer

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![NSF Award #2427549](https://img.shields.io/badge/NSF-2427549-blue.svg)](https://www.nsf.gov/awardsearch/showAward?AWD_ID=2427549)

**AI-powered document intelligence for research administration.**

Vandalizer is an open-source, self-hosted platform for AI-powered document review and data extraction, purpose-built for research administration offices at universities. It gives offices of sponsored programs, grants offices, compliance teams, and other university units a single tool for processing the large volumes of grant proposals, award documents, and regulatory filings that flow through every funding cycle.

These offices typically review hundreds of documents per cycle to extract deadlines, budgets, compliance requirements, PI information, and sponsor-specific terms. Much of this work is manual, repetitive, and error-prone. Vandalizer automates it with configurable LLM-powered extraction workflows that pull structured data from uploaded documents, chain tasks into repeatable pipelines, and let staff ask natural-language questions against their document collections with citation-backed answers.

The project was developed at the University of Idaho under the NSF GRANTED program (Award [#2427549](https://www.nsf.gov/awardsearch/showAward?AWD_ID=2427549)) and is designed to be adopted by other institutions. It is fully self-hosted, runs on commodity infrastructure, and supports any OpenAI-compatible LLM provider including local models via Ollama.

## Features

- **Structured Extraction** - Pull dates, budgets, requirements, and more from PDFs into clean structured data
- **Workflow Engine** - Chain extraction tasks into repeatable pipelines with dependency resolution
- **RAG Chat** - Ask questions against your document collection with citation-backed answers
- **Team Collaboration** - Multi-tenant workspaces with role-based access and shared libraries
- **Self-Hosted** - Run on your own infrastructure with full control over your data

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Docker & Docker Compose | Recent | [docs.docker.com/get-docker](https://docs.docker.com/get-docker/) |
| Python | >= 3.11, < 3.13 | [python.org](https://www.python.org/downloads/) (local dev only) |
| Node.js | >= 20 | [nodejs.org](https://nodejs.org/) (local dev only) |
| `uv` | Latest | [docs.astral.sh/uv](https://docs.astral.sh/uv/) (local dev only) |

Docker is required for both paths below. Python, Node.js, and `uv` are only needed for local development (Option B).

## Quickstart

### Interactive setup (recommended)

The setup wizard handles everything — environment configuration, secret generation, Docker builds, service startup, admin account creation, and database seeding — in a single interactive session:

```bash
git clone https://github.com/ui-insight/vandalizer.git
cd vandalizer
./setup.sh
```

The frontend is available at `http://localhost` and the API at `http://localhost:8001` when setup completes.

After initial setup, `./setup.sh` is the single entry point for all deployment operations:

| Command | What it does |
|---------|-------------|
| `./setup.sh` | First-time install, or re-run to choose repair/upgrade/redeploy |
| `./setup.sh --repair` | Diagnose and fix a broken deployment (restart crashed services, rebuild missing images, re-run bootstrap) |
| `./setup.sh --upgrade` | Pull latest code, take a backup, rebuild images, and redeploy |
| `./setup.sh --redeploy` | Rebuild and restart from current code (after local edits, no git pull) |
| `./status.sh` | Read-only health check and system status report |

### Manual setup: Docker Compose

If you prefer to run each step yourself:

```bash
git clone https://github.com/ui-insight/vandalizer.git
cd vandalizer

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env — at minimum, set JWT_SECRET_KEY:
#   python -c "import secrets; print(secrets.token_urlsafe(64))"
# LLM API keys are configured later in the admin UI, not in .env.

# Build and start everything
docker compose up --build -d

# Bootstrap the first admin account and optional shared default team
docker compose exec \
  -e ADMIN_EMAIL=admin@example.edu \
  -e ADMIN_PASSWORD='change-me-now' \
  -e ADMIN_NAME='Initial Admin' \
  -e DEFAULT_TEAM_NAME='Research Administration' \
  api python bootstrap_install.py

# Verify everything is set up correctly
./status.sh
```

The status script checks Docker services, API health, environment config, admin accounts, the verified catalog, and storage volumes — and gives actionable recommendations for anything that's missing or misconfigured.

Log in at `http://localhost` with the admin credentials you provided to the bootstrap command.

Bootstrap notes:

- The bootstrap script also seeds the **verified catalog** — pre-built workflows and extraction templates for common grant types (NSF, NIH, DOD, DOE) — so they're available immediately in the Explore system.
- If `CONFIG_ENCRYPTION_KEY` is not set in `.env`, the bootstrap script auto-generates one and prints it. Copy it into your `.env` to persist it across restarts — it is used to encrypt LLM API keys stored in MongoDB.
- `DEFAULT_TEAM_NAME` is optional. If omitted, users will start in their personal team only.
- New users always get a personal team. When a default team is configured, they also auto-join it on first registration or SSO login.
- The bootstrap admin also keeps a personal team. After the first login, switch to the shared default team in the UI if that should be the primary workspace.
- Persistent Docker volumes in the default compose setup:
  - `mongo-data`: MongoDB application data
  - `uploads`: uploaded source documents
  - `chroma-data`: ChromaDB embeddings and vector index
- Common operator commands:
  - `docker compose restart api celery frontend`
  - `docker compose logs -f api`
  - `docker compose down`

### Option B: Local development

```bash
git clone https://github.com/ui-insight/vandalizer.git
cd vandalizer

# Start infrastructure (Redis, MongoDB, ChromaDB)
docker compose up -d redis mongo chromadb

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env — at minimum, set JWT_SECRET_KEY:
#   python -c "import secrets; print(secrets.token_urlsafe(64))"

# Install and run the backend (terminal 1)
make backend-install
cd backend
uv run uvicorn app.main:app --reload --port 8001

# Start the frontend (terminal 2)
make frontend-install
cd frontend
npm run dev

# Start Celery workers (terminal 3)
cd backend
./run_celery.sh start

# Bootstrap the first admin account (terminal 4, from repo root)
cd backend
uv run python bootstrap_install.py
# Requires ADMIN_EMAIL and ADMIN_PASSWORD env vars. Example:
#   ADMIN_EMAIL=admin@example.edu ADMIN_PASSWORD=secret \
#     ADMIN_NAME='Initial Admin' DEFAULT_TEAM_NAME='Research Administration' \
#     uv run python bootstrap_install.py
```

The frontend dev server runs at `http://localhost:5173` and proxies API requests to the backend on port 8001.

> **Note:** MongoDB is mapped to host port **27018** (not the default 27017) to avoid conflicts with any local MongoDB instance. The `.env.example` defaults already account for this.

### Verification commands

```bash
make backend-install frontend-install
make ci

# Optional non-gating backend static analysis backlog
make backend-static

# Release-grade validation, including both Docker builds
make release-check
```

Before tagging an operator-facing release, walk through [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## Environment Variables

Copy `backend/.env.example` to `backend/.env`. Key variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JWT_SECRET_KEY` | **Yes** | *(none — must set)* | Secret key for JWT authentication. Generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `MONGO_HOST` | No | `mongodb://localhost:27018/` | MongoDB connection URI |
| `MONGO_DB` | No | `osp` | MongoDB database name |
| `REDIS_HOST` | No | `localhost` | Redis host |
| `CONFIG_ENCRYPTION_KEY` | No | *(auto-generated by bootstrap)* | Fernet key for encrypting LLM API keys in MongoDB. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. If omitted, `bootstrap_install.py` generates one — copy it into `.env` to persist across restarts. |

See `.env.example` for the full list including SMTP, ChromaDB, and upload directory settings.

## LLM Configuration

LLM models are configured at runtime through the admin UI — no environment variables or server restarts required.

Navigate to **Admin → System Config → Models** to add LLM providers. Each model entry includes:

- **Name** — model identifier (e.g., `gpt-4o`, `claude-sonnet-4-20250514`, `llama3.1:70b`)
- **API Key** — provider API key (stored encrypted in the database)
- **Endpoint** — API URL (leave empty for OpenAI-hosted models)
- **Protocol** — `openai`, `ollama`, or `vllm`

Vandalizer supports any OpenAI-compatible API including OpenAI, Azure OpenAI, Ollama (local models), vLLM, and OpenRouter.

## PDF Processing & OCR

Vandalizer offers two approaches for extracting text from PDF documents. Both are configured in the admin UI — no environment variables or restarts required.

### Option 1: OCR endpoint (recommended for scanned documents)

Navigate to **Admin → System Config → Endpoints** and set the **OCR Endpoint** URL. This should point to an HTTP service that accepts a multipart PDF file upload and returns extracted plain text. Any service that implements this interface will work — common choices include:

- A self-hosted [Marker](https://github.com/VikParuchuri/marker) instance
- A self-hosted [Surya](https://github.com/VikParuchuri/surya) instance
- A wrapper around [Tesseract](https://github.com/tesseract-ocr/tesseract)
- A wrapper around a cloud OCR API (Azure Document Intelligence, AWS Textract, Google Document AI)

When the OCR endpoint is configured, Vandalizer sends PDFs to it first and falls back to basic text extraction (PyPDF2) if the endpoint is unreachable or returns insufficient text.

When no OCR endpoint is configured, Vandalizer uses PyPDF2 for direct text extraction. This works well for digitally-created PDFs but will produce poor results on scanned documents.

### Option 2: Multimodal LLM (vision-based extraction)

For models that support vision (e.g., GPT-4o, Claude Sonnet), Vandalizer can bypass OCR entirely and send PDF pages as images directly to the LLM. Enable this under **Admin → System Config → Extraction** by toggling **Use Document Images (Multimodal)**.

This approach works well for visually complex documents (tables, forms, mixed layouts) but uses more LLM tokens than text-based extraction.

## Architecture

```
React Frontend  -->  FastAPI Backend  -->  MongoDB
                         |
                    Celery Workers
                         |
              Redis / ChromaDB / LLM APIs
```

- **Backend**: FastAPI with Beanie ODM, pydantic-ai agents (`backend/`)
- **Frontend**: React 19, Vite, Tailwind CSS v4, TanStack Router (`frontend/`)
- **Task Queues**: Celery with named queues (uploads, documents, workflows, etc.)
- **Vector Store**: ChromaDB for document embeddings and RAG
- **Package Manager**: `uv` (Python), `npm` (frontend)
- **Canonical checks**: root `make` targets (`make backend-ci`, `make frontend-ci`, `make backend-static`, `make release-check`)

## Documentation

- [Authorization Matrix](AUTHORIZATION_MATRIX.md)
- [Deployment Guide](DEPLOY.md)
- [Operations Guide](OPERATIONS.md)
- [Release Checklist](RELEASE_CHECKLIST.md)
- [Contributing Guide](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE.MD](LICENSE.MD) for details.

## Acknowledgments

This material is based upon work supported by the **National Science Foundation** under Award No. **2427549**. Any opinions, findings, and conclusions or recommendations expressed in this material are those of the author(s) and do not necessarily reflect the views of the National Science Foundation.

Developed by the [Artificial Intelligence for Research Administration (AI4RA)](https://ai4ra.uidaho.edu) team at the **University of Idaho**.
