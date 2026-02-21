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

```bash
# Clone the repository
git clone https://github.com/ui-insight/vandalizer.git
cd vandalizer

# Start infrastructure (Redis, MongoDB, ChromaDB)
docker compose up -d redis mongo chromadb

# Configure environment
cp .env.example .env
# Edit .env with your OPENAI_API_KEY and other settings

# Install backend dependencies and run
uv sync
python run.py

# In another terminal - start the frontend
cd vandalizer-next/frontend
npm install
npm run dev

# In another terminal - start Celery workers
./run_celery.sh start
```

## Environment Variables

Copy `.env.example` to `.env`. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | API key for LLM provider |
| `FLASK_ENV` | Yes | `development` / `testing` / `production` |
| `SECRET_KEY` | Yes | Flask secret key for sessions |
| `SECURITY_PASSWORD_SALT` | Yes | Salt for password hashing |
| `MONGO_HOST` | Yes | MongoDB connection host |
| `redis_host` | Yes | Redis connection host |

See `.env.example` for the full list.

## Architecture

```
React Frontend  -->  Flask Backend  -->  MongoDB
                         |
                    Celery Workers
                         |
              Redis / ChromaDB / LLM APIs
```

- **Backend**: Flask with app factory pattern, MongoEngine models, pydantic-ai agents
- **Frontend**: React 19, Tailwind CSS v4, TanStack Router
- **Task Queues**: Celery with 4 named queues (uploads, documents, workflows, default)
- **Vector Store**: ChromaDB for document embeddings and RAG
- **Package Manager**: `uv` (Python), `npm` (frontend)

## Documentation

- [Full Documentation](/docs) (when running locally)
- [Contributing Guide](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE.MD](LICENSE.MD) for details.

## Acknowledgments

This material is based upon work supported by the **National Science Foundation** under Award No. **2427549**. Any opinions, findings, and conclusions or recommendations expressed in this material are those of the author(s) and do not necessarily reflect the views of the National Science Foundation.

Developed by the [Artificial Intelligence for Research Administration (AI4RA)](https://ai4ra.uidaho.edu) team at the **University of Idaho**.
