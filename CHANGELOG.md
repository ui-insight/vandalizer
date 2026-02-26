# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Docker Compose stack with healthchecks for all services (Redis, MongoDB, ChromaDB, API, Celery, frontend)
- `backend/Dockerfile` — multi-stage build with non-root user and healthcheck
- `frontend/Dockerfile` — Node build stage with nginx runtime
- `frontend/nginx.conf` — SPA routing with API proxy and security headers
- GitHub Actions CI pipeline (`ci.yaml`) — runs pytest and TypeScript checks on every PR
- GitHub issue templates (bug report, feature request) and PR template
- Dependabot configuration for pip, npm, and GitHub Actions
- Rate limiting on auth endpoints (login, register, refresh) via slowapi
- Security headers middleware (X-Content-Type-Options, X-Frame-Options, Referrer-Policy)
- DOMPurify sanitization on all markdown-rendered HTML in the frontend
- Backend test suite: config validation, JWT tokens, file validation, health endpoint smoke test
- `CODE_OF_CONDUCT.md` referencing Contributor Covenant v2.1
- `CHANGELOG.md`

### Changed
- Tightened CORS to explicit methods and headers instead of wildcards
- `insight_endpoint` default changed from UIdaho-specific URL to empty string
- Celery hardened with task time limits (30 min soft / 31 min hard) and result expiry (24h)
- `CodeExecutionNode` `exec()` now runs in a thread with a 10-second timeout
- `compose.yaml` fully rewritten for the FastAPI + React stack
- `.dockerignore` expanded to exclude deprecated code, secrets, and build artifacts
- README quickstart updated with Docker Compose as the recommended path
- `CONTRIBUTING.md` rewritten with correct FastAPI paths and commands
- `DEPLOY.md` now includes a Quick Start with Docker Compose section
- `.env.example` files updated with comments and missing variables

### Security
- JWT secret validation: app refuses to start with the default `change-me` secret in non-development environments
- NoSQL injection fix: `re.escape()` applied to all `$regex` search parameters in admin routes
- XSS prevention: all `dangerouslySetInnerHTML` usage now wrapped with `DOMPurify.sanitize()`

### Removed
- Hardcoded UIdaho `insight_endpoint` default
