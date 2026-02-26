# Deprecated — Flask App & Historical Docs

This directory contains the original Flask-based Vandalizer application and associated design documents, preserved for reference and rollback purposes.

## Contents

- **`flask-app/`** — The complete Flask application (app factory, blueprints, Celery workers, templates, tests, Dockerfile, etc.)
- **`docs/`** — Historical planning and design documents from the Flask era

## Why This Exists

All functionality has been ported to the new stack:
- **Backend**: FastAPI + Beanie (see `/backend/`)
- **Frontend**: React 19 + Vite + TanStack Router (see `/frontend/`)

The Flask app is kept here so the team can reference the original implementation or roll back if needed. Once the new stack is verified in production, this directory can be safely deleted.

## Do Not Run This Code

The Flask app in `flask-app/` is no longer maintained. Dependencies, configs, and paths may be stale. If you need to run it for comparison, restore it to the repo root and follow the instructions in `flask-app/run.py`.
