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

## Quickstart

### Option A: Docker Compose (recommended)

```bash
git clone https://github.com/ui-insight/vandalizer.git
cd vandalizer

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env — set JWT_SECRET_KEY (LLM keys are configured in the admin UI)

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

The frontend is available at `http://localhost` and the API at `http://localhost:8001`.

Bootstrap notes:

- The bootstrap script also seeds the **verified catalog** — pre-built workflows and extraction templates for common grant types (NSF, NIH, DOD, DOE) — so they're available immediately in the Explore system.
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
# Edit backend/.env — set JWT_SECRET_KEY (LLM keys are configured in the admin UI)

# Install and run the backend
make backend-install
cd backend
uv run uvicorn app.main:app --reload --port 8001

# In another terminal — start the frontend
make frontend-install
cd frontend
npm run dev

# In another terminal — start Celery workers
cd backend
./run_celery.sh

# Check that everything is running and seed data is in place
./status.sh
```

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

Copy `.env.example` to `.env`. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGO_HOST` | Yes | MongoDB connection host |
| `MONGO_DB` | Yes | MongoDB database name (default: `osp`) |
| `REDIS_HOST` | Yes | Redis connection host |
| `JWT_SECRET_KEY` | Yes | Secret key for JWT authentication |

See `.env.example` for the full list.

## LLM Configuration

LLM models are configured at runtime through the admin UI — no environment variables or server restarts required.

Navigate to **Admin → System Config → Models** to add LLM providers. Each model entry includes:

- **Name** — model identifier (e.g., `gpt-4o`, `claude-sonnet-4-20250514`, `llama3.1:70b`)
- **API Key** — provider API key (stored encrypted in the database)
- **Endpoint** — API URL (leave empty for OpenAI-hosted models)
- **Protocol** — `openai`, `ollama`, or `vllm`

Vandalizer supports any OpenAI-compatible API including OpenAI, Azure OpenAI, Ollama (local models), vLLM, and OpenRouter.

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
