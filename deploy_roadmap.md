# Deploy Roadmap

## Purpose

This document turns the current deployment-readiness review into an actionable roadmap for making Vandalizer safe and supportable as an open source package that universities can install themselves.

Current readiness grade for the scanned worktree: `D+`

Target outcome: a release that an outside university can install, operate, upgrade, and secure without direct help from the original developers.

## Current Status

As of `2026-03-19`, the roadmap status is:

- `In progress`: P0 item 1, tenant isolation and object-level authorization
- `In progress`: P0 item 2, document governance authorization
- `Completed locally`: P0 item 3, frontend production build
- `Partially complete`: P1 item 4, backend test cleanup
- `In progress`: P1 items 5-7
- `In progress`: P2 items 8 and 10, global stats/admin-style scoping plus backup/restore operations
- `Not started`: remaining P2/P3 items

Recent completed work:

- Added shared backend access-control helpers and applied them to file, folder, document, breadcrumb, move, rename, delete, poll-status, classification, and retention-hold flows.
- Added a formal authorization matrix in docs and normalized shared helper checks across mixed team UUID / team ObjectId storage.
- Extended helper-based authorization into library, library-folder, and library-item flows.
- Extended helper-based authorization into search-set CRUD, validation, export, and document-selection flows.
- Added verified-library and team-library backed access checks for workflows and search sets.
- Stopped trusting caller-supplied `space` for the active file-browser/document-list path.
- Removed `space` from the active frontend file browser, upload, folder-create, and document-picker request path.
- Removed active `space` parameters from search-set creation/import and workflow import in the frontend API layer.
- Added reviewer/admin-gated verified-catalog export, preview-import, and import routes in the backend to match the existing frontend flows.
- Hardened verification queue, request-detail, collection mutation, submission-target, and trial-run routes so they no longer rely on frontend-only gating.
- Scoped `/api/config/automation-stats` to the caller's visible workflows instead of installation-wide workflow/run data.
- Scoped team-admin analytics drill-down routes so document counts reflect team-visible documents rather than all documents owned by team members.
- Redacted installation-wide `is_admin` and `is_examiner` user flags from team-scoped analytics views.
- Tightened approval visibility/action so only assigned reviewers, workflow managers, or admins can review a given approval.
- Locked the legacy `spaces` API to owner-scoped list, update, and delete behavior instead of installation-wide visibility and mutation.
- Bound office manual triage/process routes to owned work items on the owned intake, and required authorized workflow binding when an intake references a default workflow.
- Removed the active frontend `space` parameter from catalog import.
- Verified the documented backend test command locally: `cd backend && uv run pytest -q` now passes at `538 passed`.
- Restored the frontend production build locally: `npm run build` passes.
- Restored the frontend test suite locally: `59 passed`.
- Updated the package-publish workflow to build backend and frontend images from the same contexts used by local compose.
- Added a canonical `bootstrap_install.py` path for first admin plus optional default-team setup.
- Updated the main install docs to include the bootstrap flow, first-login behavior, persistence locations, and verified local test/build commands.
- Added a current-compose [OPERATIONS.md](OPERATIONS.md) runbook for health checks, backups, restore, upgrades, and rollback.
- Updated the image-publish workflow so container pushes happen only after a successful `CI` run on `main` (or manual dispatch).
- Added focused auth regression coverage for the new search-set and library-backed authorization paths.

Still open before the related roadmap items can be closed:

- The authorization model now has a formal matrix, but a manual adversarial audit and the remaining broader analytics/admin-surface review are still open.
- Legacy `space` usage is materially reduced, but it still exists in automation/workflow metadata paths and stale product copy.
- Install/bootstrap docs are materially better and a current operations guide now exists, but restore drills, S3 guidance, and release-specific upgrade/rollback notes are still open.
- CI and release automation still need to enforce the now-green local frontend/backend checks.

## Release Gates

Do not market this as broadly deployable until all of the following are true:

- Multi-tenant access control has been audited and fixed across all data-bearing endpoints.
- Frontend production build is green.
- Backend and frontend CI are green on `main`.
- First-boot install docs are complete and reproducible on a clean machine.
- Backup, restore, upgrade, and rollback paths are documented and tested.
- Admin bootstrap, auth configuration, and default-team setup are documented in the main install path.

## Priority Scale

- `P0`: stop-ship blocker
- `P1`: must be fixed before external deployments
- `P2`: should be fixed before broad multi-campus rollout
- `P3`: important maturity work for long-term adoption

## P0 Stop-Ship Blockers

### 1. Fix tenant isolation and object-level authorization

Status: `In progress`

Problem:

- Several folder and document flows are scoped by UUID or caller-supplied fields without consistently verifying ownership, team membership, or organization visibility.
- Current file and folder code mixes personal and team data models in ways that can leak metadata or allow unauthorized mutation.

Observed examples:

- `backend/app/routers/documents.py`
- `backend/app/services/document_service.py`
- `backend/app/services/file_service.py`
- `backend/app/services/folder_service.py`

Required improvements:

- Define one canonical authorization model for:
  - personal resources
  - team-shared resources
  - organization-scoped resources
  - admin-only resources
- Add shared authorization helpers instead of per-route ad hoc checks.
- Require every read, write, delete, rename, move, classify, retention, and poll-status action to prove access to the target object.
- Stop trusting caller-supplied `space` or resource IDs without authorization checks.
- Audit every route and service that accepts `uuid`, `folder_uuid`, `doc_uuid`, `team_uuid`, `organization_id`, or similar identifiers.
- Ensure team-shared documents are consistently accessible to authorized teammates for list, download, rename, move, delete, workflow use, chat use, and audit visibility.
- Ensure personal data cannot be surfaced through team folder navigation.
- Ensure breadcrumb, rename, delete, and status endpoints enforce the same authorization rules as list endpoints.

Exit criteria:

- A full authorization matrix exists in docs.
- All object-level endpoints use shared authorization helpers.
- New tests cover unauthorized read and unauthorized mutation attempts across personal, team, and admin boundaries.
- A manual adversarial test pass confirms no cross-user or cross-team leakage.

Progress so far:

- Added shared access-control helpers and routed document, file, and folder access through them.
- Added a formal authorization matrix in `AUTHORIZATION_MATRIX.md`.
- Normalized helper-based team access checks to handle both team UUIDs and Mongo ObjectId-style team identifiers.
- Tightened authorization for list, poll-status, rename, delete, move, breadcrumbs, classification, and retention-hold flows.
- Tightened workflow result polling/download, workflow run/test document selection, automation access, knowledge-base access, and chat document/folder/knowledge-base selection flows.
- Added helper-based authorization for libraries, library folders, library items, and verified-library org scoping.
- Added helper-based authorization for search-set CRUD, item CRUD, validation/test-case paths, and extraction document selection.
- Added library-backed workflow/search-set access so verified items and team-shared search sets can be opened through authorized library paths.
- Added reviewer/admin enforcement for verification queue, collection mutation, and verified-catalog export/import routes.
- Added route-level authorization for verification submission targets and request-detail visibility.
- Added verified-item metadata visibility checks so direct metadata lookup no longer bypasses org-scoped verified-item access.
- Added approval authorization checks based on assignment or manage access to the parent workflow.
- Locked legacy space list/update/delete operations to the owning user.
- Hardened office intake/work-item routes so manual actions cannot target foreign work items and intake workflow binding cannot point at an unauthorized workflow.
- Scoped automation dashboard stats to the caller's visible workflows rather than installation-wide counts.
- Removed active dependence on caller-supplied `space` in the file browser path.
- Focused backend authorization tests covering the touched paths are passing (`98 passed` across access-control, extraction-auth, verification-route, config-route, and workflow-auth suites).
- Follow-up approval, verification, and legacy-space auth suites are also passing (`40 passed` across approval-route, verification-route, space-route, config-route, extraction-auth, and workflow-auth suites).
- Office/approval/verification/space route follow-up coverage is also passing (`25 passed` across office-route, approval-route, verification-route, and space-route suites).

### 2. Fix document governance endpoints to honor ownership and tenant scope

Status: `In progress`

Problem:

- Classification and retention-hold endpoints currently locate documents by UUID alone before mutating sensitive state.

Required improvements:

- Require ownership, team role, or admin privilege before changing classification or legal-hold state.
- Define which roles may:
  - classify documents
  - place retention holds
  - remove retention holds
  - view retention metadata
- Add audit events for authorization failures on protected governance endpoints if desired.

Exit criteria:

- Governance endpoints reject unauthorized users.
- Tests cover classification and retention actions on another user's document, another team's document, and a valid in-scope document.

Progress so far:

- Classification and retention-hold routes now resolve documents through shared authorization helpers instead of raw UUID lookup.
- Admin-only retention endpoints still need dedicated authorization tests across ownership and team boundaries before this item can be closed.

### 3. Get the frontend production build green

Status: `Completed locally`

Problem:

- `npm run build` currently fails with a large TypeScript error set.
- This alone prevents a shippable frontend artifact.

Required improvements:

- Fix TanStack Router search-param typing errors.
- Remove or use unused imports and dead code where lint/type failures are triggered.
- Fix type mismatches in chart formatters, state shapes, and component props.
- Ensure `npm run build`, `npx tsc --noEmit`, and `npx eslint .` all pass.
- Add a release check that blocks merging if the production build fails.

Exit criteria:

- Frontend CI is green.
- Production build works from a clean checkout with `npm ci && npm run build`.

Current state:

- `npm run build` now passes locally.
- `npm test` now passes locally.
- Remaining non-blocking warning: the frontend build emits large-chunk warnings and should be revisited for chunking/code-splitting before release.

## P1 Must-Fix Before External Deployment

### 4. Clean up failing backend tests and stale test contracts

Status: `Partially complete`

Problem:

- The backend CI-style pytest run is not fully green.
- Some tests are stale relative to current behavior; others reference removed helpers or outdated contracts.

Required improvements:

- Resolve failing tests instead of tolerating drift.
- Remove or replace tests that reference deleted internals.
- Align health endpoint tests with current response shape.
- Update organization-service tests to match current hierarchy rules and query approach.
- Update workflow-route tests to reflect current service signatures.
- Improve mocks to represent real runtime objects rather than permissive `MagicMock` defaults that hide auth and expiry bugs.

Exit criteria:

- `uv sync --frozen --extra dev && uv run pytest -q` passes cleanly.
- Coverage remains at or above the intended threshold after test cleanup.

Progress so far:

- The documented backend suite command now passes locally at `538 passed` via `cd backend && uv run pytest -q`.
- The remaining gap for closing this item is to confirm the exact CI command path, keep it green on `main`, and verify coverage expectations.

### 5. Make install/bootstrap reproducible from one canonical path

Status: `In progress`

Problem:

- Admin creation and default-team setup live in `deploy.sh`, while the main README quickstart only describes env setup and `docker compose up`.
- Outside operators need one documented path, not multiple competing bootstrap flows.

Required improvements:

- Decide on one supported install path for external operators:
  - interactive `deploy.sh`
  - scripted Docker Compose bootstrap
  - Helm or another production installer later
- Update the README and deployment guide to include:
  - admin creation
  - first login
  - default team setup
  - optional auth setup
  - data persistence locations
  - how to restart services
- Ensure the documented path works from a clean machine without tribal knowledge.

Exit criteria:

- A fresh operator can follow one doc from clone to first admin login.
- The documented path is exercised in CI or a release checklist.

Progress so far:

- The README and deployment guide now include first-admin creation in the main Docker Compose flow.
- The backend runtime image now includes `bootstrap_install.py`, `create_admin.py`, and `setup_default_team.py`, so the documented bootstrap flow is available inside the shipped container.
- Added `bootstrap_install.py` as the canonical compose-native bootstrap command for first admin plus optional default-team setup.
- Default-team setup now reuses only teams actually owned by the bootstrap admin instead of any matching team name.
- The README and deployment guide now document first-login behavior, persistence volumes, and operator restart/log commands.
- The remaining gap is to exercise the documented path from a clean machine or CI/release checklist instead of relying on local validation alone.

### 6. Tighten release engineering and artifact generation

Status: `In progress`

Problem:

- The repo has CI, image build workflows, and Dockerfiles, but the current tree is not consistently release-ready.
- At least one image-publish workflow appears mismatched with the backend Docker build context.

Required improvements:

- Verify all GitHub Actions workflows against the actual directory structure.
- Ensure published backend and frontend images are buildable from the configured contexts.
- Add explicit release tags and changelog discipline.
- Make the release process deterministic:
  - dependency install
  - lint
  - typecheck
  - tests
  - image builds
  - signed or at least clearly versioned artifacts
- Decide whether to publish:
  - source-only releases
  - Docker images
  - both

Exit criteria:

- Release workflows build the same artifacts that operators are told to use.
- A tagged release can be reproduced from CI.

Progress so far:

- The container publish workflow now builds backend and frontend images from `./backend` and `./frontend`, matching the local compose setup and Dockerfiles.
- Container publishing now waits for a successful `CI` run on `main` before pushing images, instead of publishing from any direct workflow trigger.
- Release tagging, changelog discipline, and reproducible tagged releases still need work.

### 7. Normalize the backend dependency/test workflow

Status: `In progress`

Problem:

- The intended backend dev/test path is `uv sync --extra dev`, but this is easy to miss and not mirrored clearly in all documentation.

Required improvements:

- Make the backend README or main README explicitly document:
  - local install
  - dev extras
  - test command
  - lint command
  - typecheck command
- Consider adding `make` targets or a justfile for common tasks.
- Avoid ambiguous commands that appear to work but omit required test dependencies.

Exit criteria:

- A contributor can run all backend checks without reading CI YAML.

Progress so far:

- The README now documents `uv sync --extra dev`, backend pytest, and frontend test/build commands.
- The docs still need one concise contributor/operator path that includes lint, typecheck, and release checks without requiring CI spelunking.

## P2 Should-Fix Before Broad Rollout

### 8. Scope global stats, analytics, and admin-style surfaces correctly

Status: `In progress`

Problem:

- Some endpoints aggregate installation-wide data for any authenticated user or without sufficient tenant scoping.

Required improvements:

- Audit config, workflow stats, quality stats, and admin dashboards for over-broad queries.
- Decide which data is:
  - per-user
  - per-team
  - per-organization
  - global admin only
- Enforce those boundaries consistently in backend queries and frontend UI.

Exit criteria:

- Non-admin users cannot infer other teams' or the whole installation's usage patterns.

Progress so far:

- `/api/config/automation-stats` is now scoped to the caller's visible workflows instead of installation-wide data.
- Verified-catalog export/preview-import/import is now explicitly reviewer/admin gated in the backend instead of depending on frontend-only access control.
- Team-admin user and team drill-down routes now scope document counts to team-visible documents instead of installation-wide personal-document totals.
- Team-scoped analytics views now redact installation-wide `is_admin` and `is_examiner` flags for member records.
- Targeted route coverage for the new analytics scoping is passing in `backend/tests/test_admin_routes.py`.
- The broader audit of analytics, quality dashboards, and admin-style summary endpoints is still open.

### 9. Formalize the data model for universities and organizations

Problem:

- Organizations, teams, and default-team behavior exist, but the model still feels mid-transition.
- The hierarchy and visibility rules are not yet fully productized.

Required improvements:

- Document the intended hierarchy model:
  - university
  - college
  - department
  - unit
  - team
  - personal workspace
- Define inheritance and visibility rules.
- Define how SAML/OAuth-mapped departments become organizations.
- Define whether one deployment is meant for:
  - one university
  - a university system
  - many unrelated institutions
- Ensure schema and UI support the chosen scope cleanly.

Exit criteria:

- Outside operators can tell how to model their institution before importing users.

### 10. Improve backup, restore, and disaster recovery

Status: `In progress`

Problem:

- There is backup scripting, but the operator story is not yet complete enough for risk-averse universities.

Required improvements:

- Document backup and restore for:
  - MongoDB
  - ChromaDB
  - uploaded files
  - S3-backed storage if used
  - environment/config secrets
- Add restore drills and document expected recovery time.
- Define retention for backups and encrypted storage expectations.
- Define how to migrate between local storage and S3 if supported.

Exit criteria:

- An operator can restore a failed deployment into a new environment.

Progress so far:

- The repo now includes a current-compose [OPERATIONS.md](OPERATIONS.md) runbook instead of relying only on the older migration-oriented deployment guide.
- The operations guide now documents the actual persistent data set for the default install path: MongoDB, uploads, ChromaDB, and `backend/.env`.
- The operations guide now includes concrete backup commands for MongoDB, uploads, and ChromaDB using the running Compose services.
- The operations guide now includes a restore order, smoke checks, and basic upgrade/rollback procedures for the current package.
- Restore drills, S3-backed storage guidance, and release-by-release migration notes are still open.

### 11. Strengthen observability and production operations

Problem:

- The app has health checks, JSON logging, Sentry hooks, and Prometheus instrumentation, but this is still a baseline rather than a mature production package.

Required improvements:

- Document metrics and alert recommendations.
- Add dashboards or example queries for:
  - API errors
  - worker failures
  - queue depth
  - document-processing latency
  - OCR failures
  - LLM failures
  - auth failures
- Add structured audit and operational logs for critical flows.
- Ensure Celery queues can be monitored individually.

Exit criteria:

- Operators have a documented observability baseline for production.

### 12. Harden secrets and configuration management

Problem:

- Env-based configuration is acceptable, but universities often require stronger secret handling and clearer rotation guidance.

Required improvements:

- Document secret rotation for:
  - JWT secret
  - API keys
  - SMTP credentials
  - S3 credentials
  - OAuth/SAML secrets
- Support secret injection from managed stores if desired.
- Clarify which settings are safe to edit live versus requiring restarts.

Exit criteria:

- Security reviewers can see a clear secrets-management story.

### 13. Harden identity provider setup and production auth guidance

Problem:

- Password auth, OAuth, and SAML exist, but production operator guidance is still light.

Required improvements:

- Publish explicit setup guides for:
  - password-only deployments
  - Microsoft Entra / Azure OAuth
  - SAML
- Document callback URLs, reverse-proxy requirements, forwarded headers, and HTTPS requirements.
- Clarify user provisioning behavior and role mapping.
- Add tests for common auth misconfiguration cases.

Exit criteria:

- A university IAM admin can configure SSO without reading code.

### 14. Finish compliance-oriented governance features

Problem:

- The product already includes classification, retention, approvals, and audit features, but those need stronger policy design before institutional rollout.

Required improvements:

- Define official support boundaries for FERPA, CUI, ITAR, and similar labels.
- Clarify whether labels are:
  - informational
  - enforcement-backed
  - both
- Add enforcement wherever policy labels imply technical restrictions.
- Document audit-log retention and tamper-resistance expectations.

Exit criteria:

- Governance features are described accurately and defensibly in docs.

## P3 Maturity and Ecosystem Work

### 15. Improve open source packaging and adoption materials

Required improvements:

- Add architecture diagrams for operators.
- Add a support matrix:
  - supported OSes
  - supported Docker versions
  - supported browsers
  - supported auth providers
  - supported storage backends
- Add sample production topologies.
- Add a real upgrade guide for each release.
- Add a troubleshooting guide.
- Add a secure example `.env` for production with commentary.
- Add a "what is optional vs required" matrix.

Exit criteria:

- A university IT team can evaluate the package before installing it.

### 16. Improve contributor experience

Required improvements:

- Add `make test`, `make lint`, `make build`, or equivalent task runners.
- Add pre-commit hooks if desired.
- Separate generated/demo artifacts from core developer flows.
- Clarify branch/review/release expectations in contributor docs.

Exit criteria:

- External contributors can submit fixes without reverse-engineering the workflow.

### 17. Add realistic end-to-end installation and regression tests

Required improvements:

- Add a smoke test that brings up the stack in Docker Compose.
- Add end-to-end coverage for:
  - login
  - admin bootstrap
  - upload
  - extraction
  - chat
  - workflow run
  - team sharing
  - org-scoped access
- Add a release test that validates fresh-install bootstrap.

Exit criteria:

- The package can prove a clean install works before release.

### 18. Clarify demo/sample data boundaries

Required improvements:

- Keep demo assets clearly separated from production/operator materials.
- Ensure no sample data is mistaken for required runtime state.
- Document which demo containers and demo data are safe to ignore for production.

Exit criteria:

- Operators can tell immediately what is demo-only.

## Recommended Execution Order

### Phase 1: Safety and ship blockers

- Fix authorization model and tenant isolation.
- Fix governance endpoint authorization.
- Get frontend production build green.
- Get backend and frontend CI green.

### Phase 2: External installability

- Consolidate bootstrap docs.
- Verify published Docker artifacts.
- Document admin bootstrap and default-team setup.
- Add clean-install smoke tests.

### Phase 3: Institutional operations

- Backup/restore docs and drills.
- Observability baseline.
- Auth provider setup guides.
- Secret rotation guidance.

### Phase 4: Broad adoption

- Improve contributor workflow.
- Improve packaging docs and topology guidance.
- Expand E2E regression coverage.

## Suggested Owners

- Platform/security: authorization audit, governance enforcement, secrets, tenant boundaries
- Frontend: build failures, route typing, production artifact stability
- Backend: failing tests, service-layer authorization, org/team model cleanup
- DevOps/release: CI alignment, image publishing, install docs, smoke tests
- Product/docs: university topology guidance, auth setup guides, governance language

## Definition of "Ready for Universities"

Vandalizer should only be described as ready for broad university deployment when:

- it passes clean CI,
- it builds production artifacts without manual fixes,
- its tenant boundaries are explicitly designed and tested,
- its install and upgrade path is documented end-to-end,
- its operational runbook is sufficient for independent IT teams,
- and its governance features are described with claims that match the actual enforcement in code.
