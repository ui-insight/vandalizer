# Contributing to Vandalizer

Thank you for your interest in contributing to Vandalizer! This guide will help you get started.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Prerequisites

- Python >= 3.11, < 3.13
- Node.js >= 20
- Docker & Docker Compose
- [`uv`](https://docs.astral.sh/uv/) for Python package management
- `npm` for frontend package management

## Development Setup

### 1. Infrastructure

Start Redis, MongoDB, and ChromaDB:

```bash
docker compose up -d redis mongo chromadb
```

### 2. Backend

```bash
cd backend

# Install Python dependencies (including test tools)
uv sync --extra dev

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings (OPENAI_API_KEY, JWT_SECRET_KEY, etc.)

# Run the FastAPI dev server (port 8001)
uvicorn app.main:app --reload --port 8001
```

### 3. Celery Workers

```bash
cd backend
./run_celery.sh
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server runs on `http://localhost:5173` and proxies API requests to the backend.

## Coding Conventions

### Python

- Use `uv` for package management (never `pip install` directly)
- Celery tasks use `bind=True` and `autoretry_for` patterns
- Beanie ODM for all MongoDB access (async, Pydantic v2 models)
- MongoDB database name: `osp`

### TypeScript / Frontend

- React 19 with functional components and hooks
- Tailwind CSS v4 for styling
- TanStack Router for routing
- Lucide icons

### Commit Messages

Use clear, descriptive commit messages. Prefer the format:

```
<type>: <short summary>

<optional longer description>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`

## Pull Request Process

1. Fork the repository and create a feature branch from `main`
2. Make your changes with clear, descriptive commits
3. Ensure backend tests pass: `cd backend && uv run pytest`
4. Ensure the frontend builds cleanly: `cd frontend && npx tsc --noEmit && npm run build`
5. Submit a pull request against the `main` branch
6. Fill out the PR template with a description, changes, and test plan

## Testing

```bash
# Backend tests (requires dev deps: uv sync --extra dev)
cd backend
uv run pytest

# Frontend type check
cd frontend
npx tsc --noEmit
```

Tests run without any infrastructure (no MongoDB/Redis needed). The test suite covers
config validation, JWT token handling, file validation, and a health endpoint smoke test.

## Reporting Issues

- Use [GitHub Issues](https://github.com/ui-insight/vandalizer/issues) for bug reports and feature requests
- Include steps to reproduce, expected behavior, and actual behavior for bugs
- For security vulnerabilities, please report privately via GitHub Security Advisories
