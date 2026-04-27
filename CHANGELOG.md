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
- Root `Makefile` with canonical backend, frontend, and release validation targets
- Tagged GitHub release workflow that reruns release validation, publishes versioned GHCR images, and creates a GitHub release
- `RELEASE_CHECKLIST.md` covering changelog curation, release validation, bootstrap smoke checks, and rollback readiness

### Changed
- Tightened CORS to explicit methods and headers instead of wildcards
- `insight_endpoint` default changed from UIdaho-specific URL to empty string
- Celery hardened with task time limits (30 min soft / 31 min hard) and result expiry (24h)
- `CodeExecutionNode` now runs sandboxed code in a killable child process so timeout cases do not hang the worker or test process
- `compose.yaml` fully rewritten for the FastAPI + React stack
- `.dockerignore` expanded to exclude deprecated code, secrets, and build artifacts
- README quickstart updated with Docker Compose as the recommended path
- `CONTRIBUTING.md` rewritten with correct FastAPI paths and commands
- `DEPLOY.md` now includes a Quick Start with Docker Compose section
- `.env.example` files updated with comments and missing variables
- Backend dev tooling is now installed deterministically via `uv sync --frozen --extra dev`, without ad hoc CI `pip install` steps
- CI now uses shared `make` targets so local, PR, and release checks run the same commands
- Continuous image workflows now use sanitized branch tags plus explicit `sha-<short>` image tags
- Fixed a frontend production-build type regression in `ExtractionEditorPanel` so local and Docker builds pass again
- Fixed workflow approval pause propagation so `ApprovalNode` pauses execution even when wrapped in `MultiTaskNode`
- API-triggered automations now authorize caller-supplied existing document UUIDs before workflow or extraction execution
- Chat resume, add-link, and add-document routes now require the referenced activity to belong to the current user before reusing or mutating activity/conversation state
- Browser-automation session creation now verifies that the referenced workflow result belongs to a workflow visible to the current user before opening a session
- Knowledge-base suggestion creation now requires visibility on the target KB, and suggestion review is bound to the KB in the route instead of trusting a bare suggestion UUID
- Knowledge-base cloning now reuses the same KB visibility checks as the route layer instead of bypassing org/team scoping with a raw KB lookup
- Team-scoped admin analytics and workflow views now normalize mixed team UUID/ObjectId history, including same-team drill-downs opened by team UUID
- Extraction status polling now resolves caller-supplied activity IDs through `PydanticObjectId`, keeping API-key lookups aligned with the owned-activity path
- Added governance-route coverage for document classification and admin-only retention holds across personal, team, outsider, and admin cases
- Updated stale backend config/auth tests to match the production `openai_api_key` requirement
- Split backend release-gating tests from the current backend static-analysis backlog via `make backend-ci` and `make backend-static`
- The canonical `bootstrap_install.py` entrypoint is now covered directly in the backend test suite, not only through helper-level script tests
- Fix broken 'Test model' button in Admin Config UI

### Security
- JWT secret validation: app refuses to start with the default `change-me` secret in non-development environments
- NoSQL injection fix: `re.escape()` applied to all `$regex` search parameters in admin routes
- XSS prevention: all `dangerouslySetInnerHTML` usage now wrapped with `DOMPurify.sanitize()`

### Removed
- Hardcoded UIdaho `insight_endpoint` default
