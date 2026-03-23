# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vandalizer is an AI-powered document intelligence platform for research administration, built at the University of Idaho. Users upload documents, run LLM-powered extraction workflows, chat with documents via RAG, and collaborate in teams.

**Stack**: FastAPI + Beanie (backend), React 19 + Vite (frontend), Celery (task queues), MongoDB, Redis, ChromaDB.

## Development Commands

```bash
# Start infrastructure (Redis, MongoDB, ChromaDB)
docker compose up redis mongo chromadb

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

# Production
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 4
```

## Architecture

### Backend (`backend/`)

**FastAPI application** with Beanie ODM (async MongoDB driver built on Motor).

- **`app/main.py`** — FastAPI app creation, middleware, router registration, Beanie initialization
- **`app/config.py`** — Pydantic `Settings` (reads `.env`)
- **`app/database.py`** — MongoDB/Beanie connection setup
- **`app/dependencies.py`** — FastAPI dependency injection (current user, DB sessions)

### Routers (`backend/app/routers/`)
`auth`, `documents`, `files`, `folders`, `workflows`, `extractions`, `chat`, `spaces`, `library`, `knowledge`, `teams`, `admin`, `config`, `feedback`, `activity`, `office`, `automations`, `verification`, `demo`, `browser_automation`, `graph_webhooks`

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
Task modules: `upload_tasks`, `document_tasks`, `workflow_tasks`, `extraction_tasks`, `evaluation_tasks`, `quality_tasks`, `knowledge_base_tasks`, `activity_tasks`, `passive_tasks`, `m365_tasks`, `demo_tasks`, `upload_validation_tasks`

### Frontend (`frontend/`)
React 19, Vite, TypeScript, Tailwind CSS v4, TanStack Router. Source in `frontend/src/`.

### Multi-Tenancy
Documents, workflows, and folders are scoped by `space` and `team_id`. Users have a `current_team` and `TeamMembership` records with role-based access (owner/admin/member).

## Key Environment Variables

Copy `.env.example` to `.env`. Required: `MONGO_HOST`, `MONGO_DB`, `REDIS_HOST`, `JWT_SECRET_KEY`. LLM API keys and endpoints are configured per-model via System Config in the admin UI.

## Conventions

- Python >=3.11,<3.13 required
- `uv` is the Python package manager; `npm` for frontend
- Beanie ODM for MongoDB (async, Pydantic v2 models)
- Celery tasks use `bind=True` and `autoretry_for` patterns
- MongoDB database name: `vandalizer` (configurable via `MONGO_DB`)
- The old Flask app is preserved in `deprecated/flask-app/` for reference
