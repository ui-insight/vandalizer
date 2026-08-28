# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vandalizer is an AI-powered document intelligence platform for research administration, built at the University of Idaho. Users upload documents, run LLM-powered extraction workflows, chat with documents via RAG, and collaborate in teams.

**Stack**: FastAPI + Beanie (backend), React 19 + Vite (frontend), Celery (task queues), MongoDB, Redis, ChromaDB.

## Development Commands

Full Dockerized install + admin account + catalog seed (the supported deploy path, for users asking how to deploy on a server): `./setup.sh` from the project root. See `DEPLOY.md`. The commands below are the hot-reload dev loop.

```bash
# Backend (port 8001)
cd backend && uv sync && uvicorn app.main:app --reload --port 8001

# Celery workers
cd backend && ./run_celery.sh start

# Reset database, uploads, and ChromaDB (development only)
./scripts/reset_db.sh          # interactive
./scripts/reset_db.sh --force  # skip confirmation
```

## CI / Testing

`make help` lists the targets. What it doesn't tell you:

- `make backend-ci` enforces a 50% coverage gate.
- `make frontend-ci`'s coverage gate spans the whole `src/` tree, currently ~6% lines — see `frontend/vitest.config.ts` before assuming a change broke it.
- `make backend-test-integration-t2` needs `INTEGRATION_MONGODB=1`; `-t3` needs `INTEGRATION_LLM=1`. Neither runs otherwise.
- The `security` targets need Trivy on PATH (`brew install trivy`).

## Architecture

FastAPI + Beanie ODM (async MongoDB, built on Motor) backend; React 19 + Vite frontend in `frontend/src/`.

### Services (`backend/app/services/`)
Business logic layer. Key services:
- **`llm_service.py`** — pydantic-ai agent creation, model resolution, LLM caching
- **`extraction_engine.py`** — Core extraction logic (one-pass and two-pass strategies)
- **`chat_service.py`** — Streaming chat with RAG
- **`workflow_engine.py`** — Workflow execution with dependency resolution
- **`document_manager.py`** — Document processing pipeline, ChromaDB ingestion
- **`document_readers.py`** — Multi-format text extraction (PDF, DOCX, XLSX, HTML); owns OCR config lookup, retries, and fallback to local PyMuPDF
- **`ocr_client.py`** — OCR provider request/response handling (plain-text services and Docling-Serve)
- **`extraction_sources.py`** — Resolves per-field supporting quotes to document pages for source tracking
- **`failure_notifications.py`** — Coalesced failure notifications emitted from Celery failure paths

### Multi-Tenancy
Documents, workflows, and folders are scoped by `space` and `team_id`. Users have a `current_team` and `TeamMembership` records with role-based access (owner/admin/member).

## Key Environment Variables

Copy `.env.example` to `.env`. Key variables: `redis_host`, `ENVIRONMENT` (development/staging/production), `CONFIG_ENCRYPTION_KEY` (Fernet, for encrypting LLM API keys in MongoDB), `GRAPH_TOKEN_KEY` / `GRAPH_NOTIFICATION_URL` / `GRAPH_CLIENT_STATE_SECRET` (M365 integration), `VANDALIZER_BASE_URL`. LLM API keys and endpoints are configured per-model via System Config in the admin UI — not via env.

## Conventions

- Python >=3.11,<3.13; `uv` is the Python package manager (never `pip`), `npm` for the frontend
- Celery tasks use `bind=True` and `autoretry_for` patterns
- When you add, remove, or rename a route in `backend/app/routers/` or a call in `frontend/src/api/*.ts`, run `make endpoint-map` and read the two orphan lists in `scripts/ui_endpoint_map.md` — a frontend call matching no route is a live 404. `make backend-static` gates this in CI.
