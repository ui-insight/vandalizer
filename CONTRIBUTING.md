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

> **Note:** MongoDB is mapped to host port **27018** (not the default 27017) to avoid conflicts with any local MongoDB instance. The `.env.example` defaults already account for this.

### 2. Backend

```bash
make backend-install

# Copy and configure environment
cd backend
cp .env.example .env
# Edit .env — at minimum, set JWT_SECRET_KEY:
#   python -c "import secrets; print(secrets.token_urlsafe(64))"
# LLM keys are configured in the admin UI, not in .env.

# Run the FastAPI dev server (port 8001)
uv run uvicorn app.main:app --reload --port 8001
```

### 3. Celery Workers

```bash
cd backend
./run_celery.sh start
```

### 4. Frontend

```bash
make frontend-install
cd frontend
npm run dev
```

The frontend dev server runs on `http://localhost:5173` and proxies API requests to the backend.

### 5. Bootstrap (first time only)

Create the initial admin account and seed the verified catalog:

```bash
cd backend
ADMIN_EMAIL=admin@example.edu ADMIN_PASSWORD=secret \
  ADMIN_NAME='Initial Admin' DEFAULT_TEAM_NAME='Research Administration' \
  uv run python bootstrap_install.py
```

If `CONFIG_ENCRYPTION_KEY` is not set, the bootstrap script auto-generates one and prints it. Copy it into your `.env` to persist across restarts.

## Coding Conventions

### Python

- Use `uv` for package management (never `pip install` directly)
- Celery tasks use `bind=True` and `autoretry_for` patterns
- Beanie ODM for all MongoDB access (async, Pydantic v2 models)
- MongoDB database name: `vandalizer`

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
3. Run the shared repo checks: `make ci`
4. For packaging or deployment changes, run `make release-check`
5. Submit a pull request against the `main` branch
6. Fill out the PR template with a description, changes, and test plan

## Testing

```bash
make backend-ci
make frontend-ci
make ci
make backend-static
```

Tests run without any infrastructure (no MongoDB/Redis needed). The test suite covers
config validation, JWT token handling, file validation, and a health endpoint smoke test.

## Canonical Check Commands

Use the repo-root `Makefile` so local commands, CI, and release validation stay aligned:

```bash
make backend-install
make backend-ci
make backend-static
make backend-backlog
make frontend-install
make frontend-ci
make release-check
```

`make backend-static` runs the backend release-gating lint and security checks.

`make backend-backlog` runs the current backend typecheck and dependency-audit backlog without gating releases.

`make release-check` runs the current release-gating checks plus the backend/frontend Docker builds that ship in releases.

## Reporting Issues

- Use [GitHub Issues](https://github.com/ui-insight/vandalizer/issues) for bug reports and feature requests
- Include steps to reproduce, expected behavior, and actual behavior for bugs
- For security vulnerabilities, please report privately via GitHub Security Advisories
