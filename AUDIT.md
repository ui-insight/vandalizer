# Vandalizer Platform — Open-Source Readiness Audit

**Date**: 2026-03-16
**Auditor**: Claude Code (Opus 4.6)
**Branch**: experiment/react
**Commit**: 5b44f68
**Scope**: Readiness for national deployment as an open-source project across U.S. universities

---

## Executive Summary

Vandalizer is a well-architected AI-powered document intelligence platform with genuinely impressive extraction and workflow capabilities. It has strong fundamentals: clean backend separation of concerns, production-grade Docker setup, solid security posture, and excellent deployment documentation.

However, deploying this as an open-source project adopted by universities nationwide requires clearing several additional bars: institutional branding must be decoupled, accessibility must meet federal standards, multi-tenancy needs hardening, and the test suite needs significant expansion.

**Overall Open-Source Readiness: 6.8 / 10**

| Category | Score | Verdict |
|----------|-------|---------|
| AI/ML Core | 9/10 | Best-in-class extraction pipeline. Ready. |
| Security | 7.5/10 | Solid auth & headers. Minor hardening needed. |
| Documentation & Onboarding | 8.5/10 | Excellent DEPLOY.md, CONTRIBUTING.md, Docker setup. |
| Code Quality & Architecture | 8/10 | Clean separation, consistent patterns. Large frontend files. |
| Testing & CI/CD | 5/10 | Backend tests exist. Frontend nearly untested. No E2E. |
| Multi-Institution Readiness | 4/10 | Hardcoded branding, no i18n, filesystem-only storage. |
| Accessibility & Compliance | 3/10 | Minimal ARIA, no i18n, no VPAT. Blocker for public universities. |
| DevOps & Scalability | 6.5/10 | Good Docker setup. No k8s, no cloud storage, basic monitoring. |

---

## Table of Contents

1. [AI/ML Core](#1-aiml-core--910)
2. [Security](#2-security--7510)
3. [Documentation & Onboarding](#3-documentation--onboarding--8510)
4. [Code Quality & Architecture](#4-code-quality--architecture--810)
5. [Testing & CI/CD](#5-testing--cicd--510)
6. [Multi-Institution Readiness](#6-multi-institution-readiness--410)
7. [Accessibility & Compliance](#7-accessibility--compliance--310)
8. [DevOps & Scalability](#8-devops--scalability--6510)
9. [Open-Source Governance](#9-open-source-governance)
10. [Priority Roadmap](#10-priority-roadmap)
11. [Production Checklist](#11-production-checklist)

---

## 1. AI/ML Core — 9/10

This is where Vandalizer shines. The engineering is genuinely sophisticated and ahead of most competitors in this space.

| Feature | Grade | Notes |
|---------|-------|-------|
| Extraction Engine | A | Two-pass strategy + 3-run majority voting + fallback cascade. Production-grade. |
| Workflow Engine | A- | Topological DAG resolution, 15+ node types, parallel execution. Lacks conditionals/rollback. |
| Quality/Validation | A | Test case framework with regression detection, per-field metrics, quality tiers. Rare in this space. |
| LLM Integration | A- | Multi-provider (OpenAI/Ollama/vLLM/OpenRouter), per-model config, agent caching. No cost controls. |
| RAG/Chat | B- | Streaming works, thinking traces supported. Fixed k=8 retrieval, no reranking. |
| Document Processing | B | Multi-format + OCR fallback. Fixed chunking, sparse metadata. |
| Knowledge Base | B | Web crawling + source lifecycle. No incremental updates. |

**Key strengths for open-source adoption:**
- Multi-provider LLM support means institutions can use OpenAI, self-hosted Ollama/vLLM, or OpenRouter — no vendor lock-in
- Per-model configuration via `SystemConfig.available_models` allows admin-controlled model selection
- Agent caching with invalidation allows hot-reloading model configs without restart

**Remaining gaps:**
- No LLM cost tracking or per-team usage quotas
- No confidence scoring per extracted field
- Code sandbox for workflow CodeNode is incomplete — documented as unsafe for untrusted input
- RAG retrieval uses fixed k=8 with no semantic reranking

---

## 2. Security — 7.5/10

### Strengths

| Area | Status | Details |
|------|--------|---------|
| Secret management | Strong | JWT validator enforces secret change in non-dev (`config.py:38-46`). `.env.example` has safe defaults. |
| Authentication | Good | JWT access + refresh tokens in HttpOnly cookies. `secure=True` in production. `SameSite=lax`. |
| Password hashing | Good | `werkzeug.security` (bcrypt-based) |
| CSRF protection | Good | Custom middleware with strict cookie. Token rotated per response. |
| CORS | Good | Restricted to `frontend_url`. No wildcard with credentials. Dev allows localhost:5173 only. |
| Security headers | Good | X-Content-Type-Options, X-Frame-Options: DENY, CSP, HSTS in production, Permissions-Policy. |
| NoSQL injection | Excellent | All queries use Beanie ODM. Regex searches use `re.escape()`. No raw query construction. |
| File uploads | Strong | Extension whitelist (pdf/docx/xlsx/xls/csv), magic byte validation, `secure_filename()`, UUID-based storage paths. |
| URL validation | Good | Outbound requests block private IPs (127.x, 10.x, 192.168.x, 172.16-31.x, ::1). |
| Rate limiting | Good | Auth endpoints rate-limited via slowapi (login 5/min, register 3/min, refresh 10/min). |
| Admin protection | Good | All admin routes guarded by `_require_admin()` or `_require_admin_or_team_admin()`. |
| Dependency scanning | Good | `pip-audit` and `bandit` in CI pipeline. |
| DOMPurify | Good | Frontend sanitizes markdown before `dangerouslySetInnerHTML` across all render points. |

### Issues to Fix

**High Priority:**

1. **User enumeration in registration** — `auth.py:115` returns "Email already registered" which lets attackers enumerate valid emails.
   - Fix: Return generic "Registration failed" regardless of reason.

2. **No API key expiry** — `user.py:16` `api_token` lives forever with no rotation mechanism.
   - Fix: Add `api_token_expires_at` field. Implement rotation policy.

3. **No audit logging for admin actions** — Admin can modify system config, manage users, clear caches with no trail.
   - Fix: Log all admin actions to a dedicated audit collection.

4. **Rate limiting gaps on expensive endpoints** — No rate limits on extraction, workflow execution, or document search.
   - Fix: Add per-user rate limits: search 30/min, extraction 10/min, workflow execution 5/min.

**Medium Priority:**

5. **Login rate limit too generous** — 5/minute = 300/hour. Insufficient for brute force protection.
   - Recommendation: Reduce to 3/minute with account lockout after 10 failed attempts.

6. **No server-side file size enforcement** — Nginx enforces 200MB but no Python-side check.
   - Fix: Add size validation in `file_service.upload_document()`.

7. **String length validation missing** — Many Pydantic model fields accept unlimited-length strings.
   - Fix: Add `max_length` constraints to model fields.

8. **Code sandbox incomplete** — Runs in-process with 10-second timeout. No memory limits. Potential escape via CPython internals.
   - For now: Document limitation clearly. Long-term: subprocess or container isolation.

9. **Graph API token encryption not implemented** — `.env.example` mentions `GRAPH_TOKEN_KEY` but it's unused in code.
   - Fix: Implement Fernet encryption for M365 tokens at rest, or remove the misleading env var.

---

## 3. Documentation & Onboarding — 8.5/10

This is a genuine strength. Vandalizer is better documented than most academic open-source projects.

| Document | Status | Quality |
|----------|--------|---------|
| README.md | Present | Excellent. Project description, feature list, dual quickstart (Docker + local), architecture diagram, badges. |
| LICENSE.MD | Present | GPLv3. Appropriate for NSF-funded academic software. Copyleft encourages community contribution. |
| CONTRIBUTING.md | Present | Excellent. Prerequisites, dev setup, coding conventions, PR process, testing instructions. |
| CODE_OF_CONDUCT.md | Present | Contributor Covenant v2.1. |
| SECURITY.md | Present | Private email reporting, 48h acknowledgment, 90-day coordinated disclosure. |
| DEPLOY.md | Present | Exceptional. 11KB. Docker Compose quickstart, production guide, nginx/SSL config, two deployment strategies, rollback procedures, verification checklists. |
| CHANGELOG.md | Present | Keep a Changelog format. "Unreleased" section populated. Needs version numbers. |
| .env.example | Present | Well-documented with comments and safe defaults (backend + frontend). |
| CLAUDE.md | Present | Complete architectural reference for AI-assisted development. |
| GitHub templates | Present | Bug report, feature request, PR templates. Dependabot configured. |

### Gaps

1. **Frontend README** — Still boilerplate Vite template. Needs project-specific architecture and component overview.
2. **No static API docs** — OpenAPI/Swagger auto-generated but disabled in production and not committed to repo.
   - Fix: Commit `openapi.json` to `docs/` or generate as CI artifact.
3. **No architecture diagrams** — Only ASCII art in README. Needs visual system diagram, data flow, service interaction map.
4. **No troubleshooting guide** — Common setup issues not documented.
5. **No Makefile** — Common tasks (dev, test, lint, build) require remembering multiple commands.
   - Quick win: Add `Makefile` with targets for dev, test, lint, build.
6. **No database schema reference** — Collections, indexes, relationships not documented outside code.

---

## 4. Code Quality & Architecture — 8/10

### Backend: Well-Structured

- Clean separation: routers (22 files) → services (20+ files) → models (15+ Beanie documents) → tasks (11 modules)
- All routers use `Depends(get_current_user)` for auth injection
- Centralized exception hierarchy (`AppError`, `NotFoundError`, `AuthorizationError`, `ValidationError`, `ConflictError`) with global handler
- Consistent Beanie ODM usage — no raw MongoDB queries anywhere
- No wildcard imports. All imports explicit and traceable.
- Proper connection pooling: Motor `maxPoolSize=50, minPoolSize=5`

### Frontend: Good Patterns, Some Large Files

- React 19 + TypeScript strict mode + TanStack Router + React Query
- Context-based state management split into Navigation, ChatState, UIState (good separation)
- React Query for server state, localStorage for preferences, URL params for navigation state
- DOMPurify integration for all markdown rendering

**Large files that need decomposition:**
- `WorkflowEditorPanel.tsx` — 3,930 lines
- `Admin.tsx` — 3,114 lines
- `ExtractionEditorPanel.tsx` — 2,939 lines
- Recommendation: Break into focused sub-components.

### API Design: Consistent

- RESTful: proper HTTP verbs, plural resource names, nested routes
- Typed response models on most endpoints
- Consistent pagination (skip/limit) and error responses
- CSRF token flow works correctly across frontend/backend

### Issues

1. **~9 console.log statements in frontend** — Should be removed before release.
2. **Minimal backend logging** — Only ~12 `logger.*` calls across all routers. Critical paths (auth failures, file uploads, extractions) lack structured logging.
3. **Admin router is 1,350 lines** — Mixes stats, leaderboards, config, user management. Candidate for splitting.

---

## 5. Testing & CI/CD — 5/10

This is the weakest area and the biggest risk for open-source credibility.

### Backend Tests: Solid Foundation

- **Framework**: pytest + pytest-asyncio
- **16 test files, ~2,152 lines** covering:
  - Auth (routes, helpers, password hashing, token generation)
  - Core services (extraction engine, workflow engine)
  - Security (code sandbox, URL validation, file validation, security headers)
  - Admin routes, document routes, file routes
  - Config validation, health endpoint
- **Pattern**: Mocked MongoDB via patched Beanie. No integration tests against real database.
- **CI threshold**: 70% coverage enforced via `--cov-fail-under=70`

### Frontend Tests: Nearly Absent

- **1 test file** (`src/api/client.test.ts`, 144 lines) — tests API client fetch/retry logic only
- **No component tests, no hook tests, no page tests, no routing tests**
- **CI threshold**: 60% lines but runs with `|| true` (non-blocking!)
- **TypeScript strict mode** partially compensates — catches type errors at build time

### CI/CD Pipeline

| Step | Backend | Frontend |
|------|---------|----------|
| Unit tests | pytest with coverage | vitest (non-blocking) |
| Type checking | None (no mypy) | `tsc --noEmit` |
| Security scan | bandit + pip-audit | None |
| Linting | None in CI | None in CI (eslint configured locally) |
| Docker build | Verified | Verified |
| SonarQube | Configured | Quality gate commented out |
| E2E tests | None | None |
| Pre-commit hooks | None | None |

### Critical Gaps

1. **No E2E tests** — No Playwright or Cypress. Critical user flows (upload → extract → review) are untested end-to-end.
2. **Frontend test coverage is essentially zero** — 1 file testing the API client. No UI component coverage.
3. **Frontend CI is non-blocking** — `|| true` means tests can fail and CI still passes.
4. **No Python type checking** — No mypy or pyright. Pydantic provides runtime validation but no static analysis.
5. **No linting enforced in CI** — ESLint configured locally but not run in CI. No ruff/black for Python.
6. **No pre-commit hooks** — No `.pre-commit-config.yaml`.
7. **No integration tests** — All backend tests mock the database. No tests against real MongoDB.
8. **SonarQube quality gate commented out** — Configured but not enforced.

### Recommendations

- **Immediate**: Remove `|| true` from frontend test step. Add ESLint to CI.
- **Short-term**: Add component tests for critical UI flows. Add mypy to CI.
- **Medium-term**: Add Playwright E2E tests for upload → extract → chat flow. Set up test MongoDB in CI.

---

## 6. Multi-Institution Readiness — 4/10

This is the core gap for national open-source deployment. Currently, Vandalizer is built as a single-institution tool.

### Branding: Heavily Hardcoded

| Location | Hardcoded Content |
|----------|-------------------|
| `main.py:80` | FastAPI title: "Vandalizer" |
| `llm_service.py:256-373` | System prompts reference "Vandalizer" by name |
| `Header.tsx:28-37` | Logo: `joevandal.png`, `Vandalizer_Wordmark_RGB.png` |
| `Landing.tsx:338` | "AI-powered knowledge extraction, built at the University of Idaho" |
| `Certification.tsx:326` | "University of Idaho" |
| `Certification.tsx:961` | "Vandal Workflow Architect (VWA)" credential name |
| `DemoFeedback.tsx` | "Vandalizer" branding throughout |
| `Header.tsx:45` | Help link hardcoded to GitHub |

**Fix required**: Extract all branding into a `SystemConfig`-driven theming API: app name, logo URL, institution name, help URL. The partial `highlight_color` + `ui_radius` config exists but doesn't cover identity.

### Multi-Tenancy: Partially Implemented

**What works:**
- Documents scoped by `user_id` + `space`
- Many resources have `team_id` field (KnowledgeBase, Automation, Activity)
- Team membership validated before access
- Composite indexes prevent cross-user data leaks

**What's missing:**
- `SmartDocument` model lacks `team_id` — team isolation relies on user-space combo, not explicit team scoping
- No database-level tenant isolation — single MongoDB instance stores all tenant data
- No per-team resource quotas (storage, API calls, users)

### Storage: Local Filesystem Only

- File storage: `Path(settings.upload_dir) / user_id / {uid}.{extension}` — local disk only
- ChromaDB: `PersistentClient` with local directory
- No S3, Azure Blob, or GCS support
- Celery workers must share filesystem (Docker volume in compose.yaml)
- Horizontal scaling requires NFS or shared storage

**Fix required**: Abstract file storage behind an interface. Support at minimum local + S3.

### Database Migrations: None

- No migration framework used (Beanie has one built-in but it's not configured)
- Schema changes rely on Beanie auto-indexing on startup
- No versioned migration history
- No documented upgrade path for deploying schema changes across instances

**Risk**: When a new version changes a model, institutions running older versions have no upgrade path.

### Feature Flags: None

- No per-institution feature toggles
- No way to enable/disable features per team
- No gradual rollout support
- No kill switches for expensive operations

### Internationalization: None

- No i18n framework (no react-i18next or similar)
- All UI strings hardcoded in English throughout components
- Error messages, labels, placeholders — all English-only
- Note: For U.S. university deployment, i18n is lower priority but still matters for inclusive access.

---

## 7. Accessibility & Compliance — 3/10

**This is a potential blocker for public university adoption.** Public universities receiving federal funding must comply with Section 508 and WCAG 2.1 AA.

### ARIA & Semantic HTML

- Only ~37 accessibility attributes (`alt=`, `aria-label`, `role=`) found across the entire frontend
- Expected: hundreds for a complex SPA
- Logo images lack meaningful alt text (`Header.tsx:28-37`)
- Checkboxes have no labels (`FileRow.tsx:40-49`)
- Interactive divs lack `role="button"`
- Tables in FileList lack proper `<th>` or roles

### Keyboard Navigation

- Partial: `FileRow.tsx` implements `tabIndex={0}` + `onKeyDown` for Enter/Space
- ChatInput handles Enter/Escape
- No visible focus indicators observed in most components
- No focus traps in modals
- No skip-to-content link

### Screen Reader Support

- Form labels present but inconsistently associated with inputs
- Links missing descriptive text (icon-only links in header)
- No live regions (`aria-live`) for dynamic content updates
- No semantic landmarks beyond basic HTML structure

### Color Contrast

- Dynamic color selection via `--highlight-color` CSS variable may fail WCAG AA contrast ratios
- `color.ts` has `getContrastTextColor()` but no WCAG contrast validation

### Responsive Design

- Tailwind v4 installed but most components use inline styles with fixed dimensions
- No responsive breakpoints (`sm:`, `md:`, `lg:`) found in component code
- Layout assumes desktop viewport (fixed widths, pixel-based spacing)
- Mobile experience is likely unusable

### What's Needed

1. **Accessibility audit with axe-core** — Add to CI as automated check
2. **VPAT (Voluntary Product Accessibility Template)** — Required by many university procurement offices
3. **ARIA labels on all interactive elements** — Systematic pass through all components
4. **Keyboard navigation** — Focus indicators, focus traps in modals, skip links
5. **Responsive layout** — Migrate inline styles to Tailwind with responsive variants
6. **Color contrast validation** — Ensure dynamic theming meets WCAG AA (4.5:1 text, 3:1 UI)

---

## 8. DevOps & Scalability — 6.5/10

### Docker: Production-Grade

- Multi-stage builds (builder + runtime) for both backend and frontend
- Non-root user (appuser, UID 1000) in backend container
- Healthchecks on all services (MongoDB, Redis, ChromaDB, API, frontend)
- Resource limits (memory/CPU) defined in compose.yaml
- Named volumes for persistent data
- Restart policy: `unless-stopped`

### Monitoring: Basic

- Sentry integration (optional, via `SENTRY_DSN`). `send_default_pii=False`.
- Structured JSON logging via `python-json-logger`
- Health endpoint (`/api/health`) checks MongoDB, Redis, ChromaDB — returns "ok" or "degraded"
- **Missing**: No Prometheus metrics, no OpenTelemetry, no Grafana dashboards
- **Missing**: No Celery task metrics, no LLM call metrics (tokens, cost, latency)

### Scalability

**Scales well:**
- FastAPI is stateless (JWT-based, no server sessions) — multiple API instances behind load balancer work
- Celery with queue separation (documents | workflows | uploads | passive | default)
- Motor connection pooling (maxPoolSize=50)

**Bottlenecks:**
- Shared filesystem for uploads — requires NFS or cloud storage for multi-node
- ChromaDB in `PersistentClient` mode — must use HTTP client mode for horizontal scaling
- No distributed locking — concurrent operations on same document may race

### Backup: Minimal

- `scripts/backup_mongo.sh` — mongodump with 30-day retention
- **Missing**: No backup of uploaded files or ChromaDB embeddings
- **Missing**: No restore procedure documented
- **Missing**: No automated scheduling (manual cron required)

### Missing for Production at Scale

- No Kubernetes manifests or Helm charts
- No Infrastructure-as-Code (Terraform/CloudFormation)
- No blue-green or canary deployment automation
- No on-call runbook or incident response documentation
- No capacity planning metrics

---

## 9. Open-Source Governance

### What's in Place

| Item | Status |
|------|--------|
| LICENSE (GPLv3) | Present |
| CONTRIBUTING.md | Present, comprehensive |
| CODE_OF_CONDUCT.md | Present (Contributor Covenant v2.1) |
| SECURITY.md | Present (private reporting, 90-day disclosure) |
| Issue templates | Present (bug report, feature request) |
| PR template | Present |
| Dependabot | Configured (pip, npm, GitHub Actions) |
| CHANGELOG | Present (Keep a Changelog format) |

### What's Missing

1. **No versioning/releases** — CHANGELOG has "Unreleased" only. No tags, no GitHub Releases.
   - Fix: Adopt semantic versioning. Tag v1.0.0 for open-source launch.

2. **No governance model** — Who approves PRs? How are architectural decisions made? What's the release cadence?
   - Fix: Add GOVERNANCE.md defining maintainer roles, decision process, release schedule.

3. **No roadmap** — Potential contributors can't see where the project is heading.
   - Fix: Add public roadmap (GitHub Projects or ROADMAP.md).

4. **No contributor license agreement (CLA)** — GPLv3 may be sufficient, but some institutions require explicit IP assignment.
   - Consider: CLA bot or DCO (Developer Certificate of Origin) sign-off.

5. **No community channels** — No Discord, Slack, or mailing list for adopters/contributors.

---

## 10. Priority Roadmap

### Phase 1: Open-Source Minimum (Blocks Public Release)

| Item | Effort | Impact |
|------|--------|--------|
| Fix user enumeration in registration | 30min | Security |
| Remove `|| true` from frontend CI test step | 5min | Quality gate |
| Add ESLint + ruff to CI | 1hr | Code quality |
| Extract branding to SystemConfig (app name, logo, institution) | 1-2 days | Multi-institution |
| Add semantic versioning + tag v1.0.0 | 1hr | Governance |
| Customize frontend README | 1hr | Onboarding |
| Add ARIA labels to all interactive elements (systematic pass) | 3-5 days | Accessibility / compliance |
| Add keyboard focus indicators and skip-to-content link | 1-2 days | Accessibility |
| Add `team_id` to SmartDocument, enforce in queries | 1 day | Multi-tenancy |

### Phase 2: Adoption Enablers (First 3 Months)

| Item | Effort | Impact |
|------|--------|--------|
| Abstract file storage (local + S3) | 3-5 days | Scalability |
| Add Playwright E2E tests for critical flows | 1 week | Quality |
| Frontend component tests (15-20 key components) | 1 week | Quality |
| Add mypy to CI | 1-2 days | Type safety |
| Implement API key expiry + rotation | 1 day | Security |
| Add admin audit logging | 2-3 days | Security / compliance |
| Beanie migration framework setup + documented upgrade path | 2-3 days | Multi-institution |
| Add rate limits to extraction/workflow/search endpoints | 1 day | Security |
| Commit static OpenAPI spec to docs/ | 1hr | Documentation |
| Add Makefile for common dev tasks | 1hr | DX |
| Responsive layout pass (migrate inline styles to Tailwind) | 1-2 weeks | Accessibility |
| VPAT document | 1 week | Compliance |

### Phase 3: Scale & Community (3-6 Months)

| Item | Effort | Impact |
|------|--------|--------|
| Kubernetes Helm chart | 1 week | Deployment |
| Prometheus metrics + Grafana dashboards | 1 week | Observability |
| Per-team resource quotas (storage, API calls) | 1 week | Multi-tenancy |
| Feature flag system (per-team toggles) | 1 week | Multi-institution |
| LLM cost tracking + usage dashboards | 1 week | Operations |
| Community channels (Discord/Slack) | 1 day | Community |
| GOVERNANCE.md + public roadmap | 1 day | Governance |
| i18n framework + initial translations | 2 weeks | Internationalization |
| ChromaDB HTTP client mode for horizontal scaling | 2-3 days | Scalability |
| Backup automation (files + ChromaDB + MongoDB) | 2-3 days | Operations |

---

## 11. Production Checklist

### Security (Pre-Release)

- [x] No hardcoded secrets in source code
- [x] JWT secret enforced non-default in production
- [x] HttpOnly + Secure + SameSite cookies
- [x] CSRF protection middleware
- [x] Security headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options)
- [x] File upload validation (whitelist + magic bytes)
- [x] SSRF protection (private IP blocking)
- [x] Rate limiting on auth endpoints
- [x] DOMPurify for rendered HTML
- [x] Dependency scanning (pip-audit + bandit) in CI
- [ ] Fix user enumeration in registration
- [ ] API key expiry mechanism
- [ ] Admin audit logging
- [ ] Rate limiting on expensive endpoints
- [ ] Code sandbox hardening or documentation

### Testing

- [x] Backend unit tests with 70% coverage gate
- [x] Frontend type checking in CI
- [ ] Frontend test coverage > 60% (currently ~0%, non-blocking)
- [ ] E2E tests for critical user flows
- [ ] Integration tests against real database
- [ ] Python type checking (mypy) in CI
- [ ] ESLint enforced in CI
- [ ] Pre-commit hooks configured
- [ ] SonarQube quality gate enforced

### Documentation

- [x] README with quickstart
- [x] CONTRIBUTING.md
- [x] DEPLOY.md with production guide
- [x] CODE_OF_CONDUCT.md
- [x] SECURITY.md
- [x] CHANGELOG.md
- [x] .env.example (backend + frontend)
- [x] GitHub issue/PR templates
- [x] Dependabot configured
- [ ] Frontend README (customized)
- [ ] Static API documentation
- [ ] Architecture diagrams
- [ ] Database schema reference
- [ ] Troubleshooting guide

### Multi-Institution

- [x] Multi-provider LLM support (OpenAI/Ollama/vLLM/OpenRouter)
- [x] Environment-driven configuration
- [x] Team-based access control
- [ ] Configurable branding (name, logo, institution)
- [ ] Cloud storage support (S3/Azure Blob)
- [ ] Database migration framework
- [ ] Per-team resource quotas
- [ ] Feature flag system
- [ ] Semantic versioning + releases

### Accessibility

- [ ] WCAG 2.1 AA compliance audit
- [ ] ARIA labels on all interactive elements
- [ ] Keyboard navigation complete
- [ ] Focus indicators visible
- [ ] Skip-to-content link
- [ ] Screen reader testing
- [ ] Color contrast validation (WCAG AA)
- [ ] Responsive layout (mobile-friendly)
- [ ] VPAT documentation

### Monitoring & Operations

- [x] Health endpoint with dependency checks
- [x] Structured JSON logging
- [x] Sentry integration (optional)
- [x] MongoDB backup script
- [ ] Prometheus metrics
- [ ] Celery task monitoring
- [ ] LLM usage/cost metrics
- [ ] Backup of uploaded files + ChromaDB
- [ ] Restore procedure documented
- [ ] On-call runbook

### Deployment

- [x] Docker Compose (production-ready)
- [x] Multi-stage Dockerfiles
- [x] Healthchecks on all services
- [x] Resource limits configured
- [x] Non-root container user
- [ ] Kubernetes manifests / Helm chart
- [ ] Infrastructure-as-Code
- [ ] Blue-green / canary deployment
- [ ] Automated deployments

---

## Final Verdict

**Vandalizer's core capabilities — the extraction engine, workflow DAG, and quality validation — are genuinely impressive and production-grade.** The architecture is modern and well-chosen. The documentation is better than most academic open-source projects. The security posture is solid.

**What separates Vandalizer from being ready for national open-source adoption is institutional flexibility.** The platform is currently built as a University of Idaho tool, not a configurable platform that any university can brand as their own. The three critical gaps are:

1. **Accessibility** — Public universities must meet Section 508/WCAG 2.1 AA. The current frontend would not pass an accessibility audit. This is a legal requirement, not a nice-to-have.

2. **Institutional identity** — Branding, logos, and institution names are hardcoded throughout. A university IT department evaluating this tool will immediately ask "can we make this ours?" The answer today is "not without forking."

3. **Testing confidence** — The frontend is essentially untested. No university IT department will adopt a tool where UI changes can't be validated by an automated test suite. Backend tests exist but mock the database entirely.

**The path forward is clear and achievable.** Phase 1 (2-3 weeks of focused work) addresses the release blockers. Phase 2 (3 months) makes the project genuinely attractive for adoption. Phase 3 (6 months) builds the community and scale infrastructure for widespread deployment.

**Vandalizer has the potential to be a transformative open-source tool for research administration. The foundation is strong — it needs the institutional polish to match.**
