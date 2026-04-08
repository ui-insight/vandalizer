# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vandalizer is an AI-powered document intelligence platform for research administration, built at the University of Idaho. Users upload documents, run LLM-powered extraction workflows, chat with documents via RAG, and collaborate in teams.

**Stack**: FastAPI + Beanie (backend), React 19 + Vite (frontend), Celery (task queues), MongoDB, Redis, ChromaDB.

## Development Commands

```bash
# Backend
cd backend
uv sync
uvicorn app.main:app --reload --port 8001

# Celery workers
cd backend
./run_celery.sh

# Frontend
cd frontend
npm install
npm run dev

# Reset database, uploads, and ChromaDB (development only)
./scripts/reset_db.sh          # interactive
./scripts/reset_db.sh --force  # skip confirmation

# Production
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 4
```

## CI / Testing (Makefile)

```bash
make backend-ci        # Unit tests (50% coverage gate) + tier-1 integration tests
make backend-static    # Ruff lint + Bandit security scan
make backend-backlog   # Mypy typecheck + pip-audit (non-blocking)
make frontend-ci       # Typecheck, lint, audit, Vitest (35% line coverage gate), build
make ci                # backend-ci + frontend-ci
make release-check     # ci + backend-static + Docker builds

# Integration test tiers (run individually)
make backend-test-integration-t1   # Engine tests (no external deps)
make backend-test-integration-t2   # MongoDB integration (needs INTEGRATION_MONGODB=1)
make backend-test-integration-t3   # LLM integration (needs INTEGRATION_LLM=1)
```

## Architecture

### Backend (`backend/`)

**FastAPI application** with Beanie ODM (async MongoDB driver built on Motor).

- **`app/main.py`** — FastAPI app creation, middleware, router registration, Beanie initialization
- **`app/config.py`** — Pydantic `Settings` (reads `.env`)
- **`app/database.py`** — MongoDB/Beanie connection setup
- **`app/dependencies.py`** — FastAPI dependency injection (current user, DB sessions)

### Routers (`backend/app/routers/`)
`activity`, `admin`, `approvals`, `audit`, `auth`, `automations`, `browser_automation`, `certification`, `chat`, `config`, `demo`, `documents`, `extractions`, `feedback`, `feedback_prompt`, `files`, `folders`, `graph_webhooks`, `knowledge`, `library`, `notifications`, `office`, `organizations`, `spaces`, `support`, `teams`, `verification`, `workflows`

### Data Models (`backend/app/models/`)
Beanie `Document` classes: `User`, `Team`/`TeamMembership`, `SmartDocument`, `SmartFolder`, `Space`, `Workflow`/`WorkflowStep`/`WorkflowResult`, `ChatConversation`, `Library`/`LibraryItem`, `SystemConfig`, `SearchSet`, `Group`, `QualityAlert`, `ValidationRun`, and more.

### Services (`backend/app/services/`)
Business logic layer. Key services:
- **`llm_service.py`** — pydantic-ai agent creation, model resolution, LLM caching
- **`extraction_engine.py`** — Core extraction logic (one-pass and two-pass strategies)
- **`chat_service.py`** — Streaming chat with RAG
- **`workflow_engine.py`** — Workflow execution with dependency resolution
- **`document_manager.py`** — Document processing pipeline, ChromaDB ingestion
- **`document_readers.py`** — Multi-format text extraction (PDF, DOCX, XLSX, HTML)

### Celery Tasks (`backend/app/tasks/`)
Task modules: `activity_tasks`, `classification_tasks`, `demo_tasks`, `document_tasks`, `engagement_tasks`, `evaluation_tasks`, `extraction_tasks`, `knowledge_base_tasks`, `m365_tasks`, `passive_tasks`, `quality_tasks`, `retention_tasks`, `upload_tasks`, `upload_validation_tasks`, `workflow_tasks`

### Frontend (`frontend/`)
React 19, Vite, TypeScript, Tailwind CSS v4, TanStack Router. Source in `frontend/src/`.

### Multi-Tenancy
Documents, workflows, and folders are scoped by `space` and `team_id`. Users have a `current_team` and `TeamMembership` records with role-based access (owner/admin/member).

## Key Environment Variables

Copy `.env.example` to `.env`. Key variables: `redis_host`, `ENVIRONMENT` (development/staging/production), `CONFIG_ENCRYPTION_KEY` (Fernet, for encrypting LLM API keys in MongoDB), `GRAPH_TOKEN_KEY` / `GRAPH_NOTIFICATION_URL` / `GRAPH_CLIENT_STATE_SECRET` (M365 integration), `VANDALIZER_BASE_URL`. LLM API keys and endpoints are configured per-model via System Config in the admin UI.

## Conventions

- Python >=3.11,<3.13 required
- `uv` is the Python package manager; `npm` for frontend
- Beanie ODM for MongoDB (async, Pydantic v2 models)
- Celery tasks use `bind=True` and `autoretry_for` patterns
- MongoDB database name: `vandalizer` (configurable via `MONGO_DB`)
- Docker builds via `docker build -t vandalizer-backend ./backend` and `docker build -t vandalizer-frontend ./frontend` (or `make docker-build`)
