# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vandalizer is a Flask-based document intelligence platform for AI-powered document review, extraction, and chat. Built at the University of Idaho. Users upload documents, run LLM-powered extraction workflows, chat with documents via RAG, and collaborate in teams.

## Development Commands

```bash
# Start infrastructure (Redis, MongoDB, ChromaDB)
docker compose up redis mongo chromadb

# Install dependencies
uv sync

# Run Flask dev server (port 5003)
python run.py

# Celery workers
./run_celery.sh start       # Start all workers + Flower
./run_celery.sh stop        # Stop all
./run_celery.sh status      # Check status
./run_celery.sh logs        # Tail all logs
./run_celery.sh logs uploads  # Tail specific queue logs

# Tests (E2E via Selenium against dev server)
tox run                     # Headless Firefox + Chrome
pytest                      # Run locally

# Production
gunicorn wsgi_app           # Configured in gunicorn.conf.py, port 8000
```

## Architecture

### App Factory Pattern
`app/__init__.py` — `create_app()` initializes Flask, Celery, config, blueprints, and auth. Config is selected by `FLASK_ENV` (development/testing/production).

### Three-Level Configuration
1. **`app/configuration.py`** — Python config classes per environment (`DevelopmentConfig`, `TestingConfig`, `ProductionConfig`)
2. **`app/utilities/config.py`** — `Settings` (Pydantic BaseSettings, reads `.env`) + DB-backed helpers
3. **`SystemConfig` model** — MongoDB singleton for runtime-editable settings (models, auth, extraction, UI theme). Admins change these at runtime.

### Blueprints (in `app/`)
`auth`, `home`, `workflows`, `files`, `spaces`, `library`, `tasks`, `office`, `admin`, `teams`, `feedback`, `activity` — each has its own `routes.py` with a URL prefix.

### Data Models
`app/models.py` — All MongoEngine documents. Key models: `SystemConfig`, `User`, `Team`/`TeamMembership`, `SmartDocument`, `SmartFolder`, `Space`, `Workflow`/`WorkflowStep`/`WorkflowResult`, `ChatConversation`, `Library`/`LibraryItem`.

### LLM / AI Layer (`app/utilities/`)
- **`agents.py`** — pydantic-ai `Agent` creation, model resolution, OpenAI-compatible protocol detection, Redis-backed LLM caching. Agents are cached in module-level dicts.
- **`extraction_manager_nontyped.py`** — Core extraction logic. Strategies: `one_pass` (single structured extraction) and `two_pass` (thinking draft → structured final). Configurable via `SystemConfig.extraction_config`.
- **`chat_manager.py`** — Streaming chat with RAG, conversation persistence
- **`workflow.py`** — Workflow execution engine using ThreadPoolExecutor parallelism and graphlib-based dependency resolution

### Document Processing (`app/utilities/`)
- **`document_manager.py`** — Document processing pipeline, ChromaDB ingestion, PDF text extraction
- **`document_readers.py`** — Multi-format text extraction (PDF, DOCX, XLSX, HTML) via PyMuPDF, pypandoc, markitdown
- **`upload_manager.py`** — Celery chord-based parallel document validation

### Celery Task Queues
Defined in `app/celery_worker.py`. Four named queues: `uploads` (2 workers), `documents` (3 workers), `workflows` (2 workers), `default` (1 worker). Tasks are named as `tasks.<queue>.<name>`.

### Multi-Tenancy
Documents, workflows, and folders are scoped by `space` and `team_id`. Users have a `current_team` and `TeamMembership` records with role-based access (owner/admin/member).

### Frontend
Jinja2 templates in `app/templates/`, Tailwind CSS, vanilla JS + jQuery. Core workspace UI is in `index.html` and `index_scripts.html`. Uses Lucide icons, Marked.js for markdown, Socket.IO for real-time features.

## Key Environment Variables

Copy `.env.example` to `.env`. Required: `OPENAI_API_KEY`, `FLASK_ENV`, `SECRET_KEY`, `SECURITY_PASSWORD_SALT`, `MONGO_HOST`, `redis_host`. See `.env.example` for full list.

## Conventions

- Uses `devtools.debug()` instead of `print()` for dev output
- Python >=3.11,<3.12 required
- `uv` is the package manager (used in Dockerfile and for local dev)
- Celery tasks use `bind=True` and `autoretry_for` patterns
- MongoDB database name: `osp` (prod/dev), `osp-staging` (testing)
