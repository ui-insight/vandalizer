# Vandalizer

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![NSF Award #2427549](https://img.shields.io/badge/NSF-2427549-blue.svg)](https://www.nsf.gov/awardsearch/showAward?AWD_ID=2427549)

**AI-powered document intelligence for research administration.**

Vandalizer is an open-source platform built at the University of Idaho for AI-powered document review, extraction, and chat. Upload documents, run LLM-powered extraction workflows, chat with your documents via RAG, and collaborate in teams.

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
# Edit backend/.env — set OPENAI_API_KEY and JWT_SECRET_KEY

# Build and start everything
docker compose up --build -d

# Verify
curl http://localhost:8001/api/health
# → {"status":"ok"}
```

The frontend is available at `http://localhost` and the API at `http://localhost:8001`.

### Option B: Local development

```bash
git clone https://github.com/ui-insight/vandalizer.git
cd vandalizer

# Start infrastructure (Redis, MongoDB, ChromaDB)
docker compose up -d redis mongo chromadb

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env — set OPENAI_API_KEY

# Install and run the backend
cd backend
uv sync
uvicorn app.main:app --reload --port 8001

# In another terminal — start the frontend
cd frontend
npm install
npm run dev

# In another terminal — start Celery workers
cd backend
./run_celery.sh
```

## Environment Variables

Copy `.env.example` to `.env`. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | API key for LLM provider |
| `MONGO_HOST` | Yes | MongoDB connection host |
| `MONGO_DB` | Yes | MongoDB database name (default: `osp`) |
| `REDIS_HOST` | Yes | Redis connection host |
| `JWT_SECRET_KEY` | Yes | Secret key for JWT authentication |

See `.env.example` for the full list.

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

## Documentation

- [Deployment Guide](DEPLOY.md)
- [Contributing Guide](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE.MD](LICENSE.MD) for details.

## Acknowledgments

This material is based upon work supported by the **National Science Foundation** under Award No. **2427549**. Any opinions, findings, and conclusions or recommendations expressed in this material are those of the author(s) and do not necessarily reflect the views of the National Science Foundation.

Developed by the [Artificial Intelligence for Research Administration (AI4RA)](https://ai4ra.uidaho.edu) team at the **University of Idaho**.
