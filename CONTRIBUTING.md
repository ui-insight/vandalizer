# Contributing to Vandalizer

Thank you for your interest in contributing to Vandalizer! This guide will help you get started.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Prerequisites

- Python >= 3.11, < 3.12
- Node.js >= 20
- Docker & Docker Compose
- [`uv`](https://docs.astral.sh/uv/) package manager

## Development Setup

### Backend

```bash
# Install Python dependencies
uv sync

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings (OPENAI_API_KEY, etc.)

# Start infrastructure services
docker compose up -d redis mongo chromadb

# Run the Flask dev server (port 5003)
python run.py
```

### Frontend

```bash
cd vandalizer-next/frontend
npm install
npm run dev
```

### Celery Workers

```bash
./run_celery.sh start       # Start all workers + Flower
./run_celery.sh stop        # Stop all
./run_celery.sh status      # Check status
./run_celery.sh logs        # Tail all logs
```

## Coding Conventions

### Python

- Use `devtools.debug()` instead of `print()` for development output
- Use `uv` for package management
- Celery tasks use `bind=True` and `autoretry_for` patterns
- MongoDB database name: `osp` (prod/dev), `osp-staging` (testing)

### TypeScript / Frontend

- React 19 with functional components
- Tailwind CSS v4 for styling
- TanStack Router for routing
- Lucide icons

## Pull Request Process

1. Fork the repository and create a feature branch from `main`
2. Make your changes with clear, descriptive commits
3. Ensure tests pass: `tox run` (headless) or `pytest` (local)
4. Ensure the frontend builds cleanly: `npm run build && npx tsc --noEmit`
5. Submit a pull request against the `main` branch
6. Provide a clear description of the changes and their motivation

## Testing

End-to-end tests use pytest and Selenium:

```bash
# Headless browser tests (Firefox + Chrome)
tox run

# Local execution
pytest
```

## Reporting Issues

- Use [GitHub Issues](https://github.com/ui-insight/vandalizer/issues) for bug reports and feature requests
- Include steps to reproduce, expected behavior, and actual behavior for bugs
- For security vulnerabilities, see [SECURITY.md](SECURITY.md)
