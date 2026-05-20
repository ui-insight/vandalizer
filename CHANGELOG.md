# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [v4.3.0] - 2026-05-15

### Added
- **Workflow approval / review system, end-to-end.** The Approval node is now reachable from the editor with a full config panel (review instructions, assignee role, SLA in days, timeout action, escalation reviewers). New `/reviews` inbox with My / Team queues, status filter, and type-aware artifact rendering (text, markdown, JSON, extraction table, document download). Reviewers can edit text / markdown / JSON / single-row tables before approving — the edited artifact flows back into downstream workflow steps. Assignee roles: `workflow_owner`, `team_admins`, `specific_users`. SLA enforcement runs on a 5-minute Celery beat sweep (`tasks.approvals.expire_overdue`) that fires the configured timeout action (auto-approve / auto-reject / escalate / mark expired). `/api/approvals` is replaced by `/api/reviews`; the old `/approvals` route redirects.
- **Scoped management API at `/api/mgmt/v1`** for service consumers and agentic tools. New `ApiKey` model with named, scoped, revocable keys (`vk_live_…`), per-key rate limiting, and audit-log entries on every call. Read endpoints cover stats, users, teams, workflows, documents, activity, audit, config (secrets redacted), and the full validation domain (runs, test cases, plans, cross-field rules). Write endpoints support test cases (incl. bulk upload), cross-field rules, and validation plans. Run endpoints (validation, workflows, extractions) gated on separate scopes since they spend tokens. Issuance + revocation now open to all staff via the in-app API Keys tab, with `docs/mgmt-api.md` linked alongside.
- **Convert-to-Knowledge-Base flow for oversized documents.** Workflow and chat now pre-flight document size against the model's input budget; oversized refs trigger a structured error with an inline "Convert to Knowledge Base" action that wraps the docs in a fresh KB and activates it in workspace context. Page-level (PDF) and per-sheet (XLSX) citation offsets are now generated end-to-end, including for OCR-routed PDFs. Document ingest writes `chromadb_ready` / `chunk_count` / `ingest_error`; the file browser shows a distinct amber icon for retrieval-broken docs (separate from upload-validation failures).
- **LLM endpoint context-window probe.** System Config → Models gains a "Context Window" field and a "Probe endpoint" button that queries the configured endpoint for its real serving limit — `max_model_len` (vLLM), `context_length` (OpenRouter), or `model_info.<arch>.context_length` (Ollama). Anthropic and plain-OpenAI endpoints that do not expose the value report that, so admins know to fill it in by hand. The chat and workflow context-budget planner now trims against the real number instead of an inflated substring-table default, so compaction no longer undertrims into a mid-workflow `400`.
- **Credentials store + OAuth `client_credentials` on API Node.** New team-scoped `Credential` collection with per-field Fernet encryption and Redis-cached bearer tokens. API Node grows an `auth_strategy` selector (`none` / `static_header` / `oauth_client_credentials`). Secrets never round-trip back to the client (redacted as `"<set>"`). New Credentials management page and credential picker in the API Node config panel.
- **Public team join links.** Owners and admins can mint shareable join URLs that bypass the trial waitlist; invite acceptance has a proper OAuth + redirect flow.
- **Workflow output as chainable artifacts.** Run output saves as a `SmartDocument` that downstream steps can ingest, or as a real file in a SmartFolder of the user's choosing. Markdown output renders as a beautifully formatted PDF (with Unicode-hyphen normalization to avoid encoding crashes), a real `.docx` is generated alongside, and multi-step deliverables bundle as a ZIP. Download filenames are now unique per session.
- **Retention and classification dashboards in the Admin panel**, plus a Retention Policy admin UI for configuring rules.
- **Team notifications when content is shared** (bell + email). Activity rail auto-fails items stuck in `processing` so users do not stare at zombie spinners.
- **LLM tasks can combine multiple input sources** in a single step (previously: one source per task).
- **Auto-clone from Explore** when running a verified workflow, with linked extraction fields preserved.
- **Workflow editor polish**: "Add selected documents" shortcut for fixed-doc inputs, hover tooltips with descriptions on each task type in the picker, explainer overlays in empty Automations and Knowledge Bases tabs, Combined-vs-per-doc tooltips on Run, original author shown on workflow cards (Workflows, Library, Explore).
- **Confirm-before-delete** dialogs across workflows, extractions, Library panel, and the workspace Library tab. File-browser bulk selection clears even when a delete throws.
- **API Keys tab** offers a downloadable Claude Code skill for users wired up against the mgmt API.
- **OCR rerun script** (`scripts/re_ocr_old_documents.py`) to re-OCR documents older than N days.
- **Workflow JSON upload-from-creation-modal** entry point.
- **Test Step** is now honest about failures and its (limited) scope.
- **Certification panel** is mounted app-wide so it opens from any page; the Foundations lesson no longer misroutes users below the action button.
- **Trial check-in tickets** move out of Support Center into the Demo tab.
- **`setup.sh` menu restructured** with a catalog reset entry.

### Changed
- **M365 config setup is replaced by a Document Compliance activation flow** in the admin UI. The new path is the supported way to wire Microsoft Graph integration; the old config-driven setup is gone.
- **Workflow output "save" semantics:** "Save to folder" now means a SmartFolder file in the user's folder tree, not a Library bookmark. Add-to-Library dialog is trimmed from Explore; the dialog now drops the unmanaged note/tags fields and splits share errors so the user can tell what failed.
- **Verified items save to the Library by reference**, not by silently cloning the underlying document.
- **Workflow runner treats `pending_approval` as paused** (not running), so polling state matches what the user sees.
- **Workflow activity-rail polling resumes** when the user opens a running workflow from the rail.
- **Any team member** can now share items and create folders in the team Library (previously: owners/admins only).
- **API Node** surfaces header JSON parse errors instead of silently dropping them; OAuth-authenticated API Node calls use the new credentials store rather than inline static headers.
- **Login error messages** now explain why a login was rejected (locked, unverified, bad credentials) instead of a generic "Invalid credentials".
- **Workflow run button** muted state shows a "Select a document to run" hint; clearer errors when adding a workflow task fails.
- **Activity rail** shimmers in AI-generated titles as they stream in.
- **Library / Explore UI polish**: "more options" icon unified across file browser and library; verified-catalog "system" author renders as "Verified Catalog"; library row title takes full width with actions floating over `last used` on hover; same for file/folder rows; Library type filter "All Types" shortened to "All"; chat input restored to full width; assistant chat constrained to match input width; in-progress KB convert button dropped from the workflow editor panel; Add Document task search boxes now surface files; API Key scopes picker has Select all / Clear shortcuts.
- **Workflow / extraction inputs** can be uploaded from a JSON file at creation time; "Add selected documents" works from the library context menu.
- **Extraction validations decoupled from their source documents** — validation plans persist independently and can be downloaded as a zip of the setup. Extraction Tools tab orders import/export at the top; saved sets no longer silently drop manual extraction fields.
- **XLSX document viewer** renders formulas; markdown step output explains how input sources combine.
- **Extract API uploads default to ephemeral cleanup** so test runs don't litter the workspace.
- **Pause/resume flow**: `ApprovalNode` honors the new approval record fields; the workflow editor pending-approval banner links to the full review screen.
- **Module 4 certification content** renames "enum values" to "Allowed values"; cert module stays on the Challenge tab after completion.
- **`seed_catalog`** behavior already shipped in v4.2.0; this release continues the catalog reset entry in `setup.sh`.
- **System Config sticky header** gets horizontal padding so the gear icon and Save button no longer hug the panel edges.

### Fixed
- **Doubled workflow LLM latency** from cross-event-loop agent caches.
- **Workflow PDF crash** on triple-asterisk markdown sequences.
- **Folder-watch automations** dropping storage + notifications.
- **`/api/mgmt/v1/stats`** choking on legacy stub `SmartDocument` records.
- **Upload validation crash** when `langchain-text-splitters` was not installed (dep is now declared in `pyproject.toml`).
- **Approval flow** leaving the existing `LibraryItem` unverified after an approve.
- **Convert-to-KB setter calls** for non-Dispatch workspaces.
- **Invisible role dropdown options** on trial signup.
- **Re-OCR script** for old documents (operator tooling).
- **Pending-task leaks** from custom HTTP middlewares (`SecurityHeadersMiddleware` rewritten as pure ASGI middleware so client disconnects mid-response don't strand asyncio tasks).
- **Switching an automation's trigger type back to `folder_watch`** no longer errors.
- **Activity-rail items stuck in `processing`** auto-fail after the watchdog window instead of hanging the rail.
- **"Documents ready for analysis" banner, file-list polling, and the row spinner** flipped to "ready" the moment text extraction finished, while RAG indexing was still running in the background. All three now key off `isDocReady` and treat the `readying` / `extracting` task states as not-yet-ready, so the UI stays honest across the full upload pipeline.
- **Silent OCR / extraction failures** (image-only PDFs, OCR endpoint down, encrypted files) were recorded as a successful `complete` with empty text — the extracted-text modal rendered blank and chat silently skipped the document. Extraction now marks the document errored with a specific reason, `poll_status` surfaces it, and the modal offers a **Retry extraction** button that re-dispatches the upload pipeline.
- **Star / set-default button on System Config models** — `PUT /config/models/default` was registered after `PUT /config/models/{index}`, so FastAPI tried to parse `default` as an integer index and rejected the request. The literal route is now registered first.
- **Workflow pre-flight oversize check** read `llm_models` from `SystemConfig` when the field is `available_models`, so any `context_window` override was silently ignored.
- **Frontend errors never reached Sentry.** `VITE_SENTRY_DSN` is a Vite compile-time variable but was missing from every Docker build path, so `initSentry()` short-circuited in production and the Sentry dashboard stayed empty. The DSN, environment, and release are now passed as build args through `frontend/Dockerfile`, the Makefile `docker-build` target, and the release / build-container GitHub workflows.

### Security
- **Default extract-API uploads to ephemeral cleanup** so transient uploads do not persist in shared storage.
- **Mgmt API keys**: per-key scope, per-key rate limit, audit log on every call; secrets redacted in all read responses.
- **Credentials store** uses per-field Fernet encryption; `payload` is never echoed back to clients.

### Operator Notes
- **New backend Python dependency**: `langchain-text-splitters>=0.3,<1`. `./setup.sh --redeploy` and `docker compose up -d --build` pick it up automatically via `uv sync`. Manual installs must rerun `uv sync` in `backend/`.
- **New Celery beat job**: `tasks.approvals.expire_overdue` runs every 5 minutes to expire SLA-overdue reviews. No operator action — runs out of the standard worker pool.
- **Three new routers** mounted: `credentials` (`/api/credentials`), `reviews` (`/api/reviews`), `mgmt` (`/api/mgmt/v1`). The old `/api/approvals` is removed; the frontend `/approvals` URL redirects to `/reviews`.
- **New GitHub Actions secret for frontend error reporting**: add `VITE_SENTRY_DSN` as a repository secret (Settings → Secrets and variables → Actions) so released frontend images report to Sentry. `build-container.yaml` also reads an optional `vars.VITE_SENTRY_ENVIRONMENT` repository variable to label non-tag builds (e.g. "staging"). This is a CI-only setting — no `.env` or `compose.yaml` change.
- **No drift** in `.env.example`, `compose.yaml`, `DEPLOY.md`, `OPERATIONS.md`, or `README.md` since v4.2.0.

## [v4.2.0] - 2026-05-04

### Added
- Native `anthropic` and `openrouter` protocol options in System Config → Models. Anthropic uses pydantic-ai's `AnthropicModel` for first-class Messages API / native thinking / tool use. OpenRouter uses `OpenRouterProvider` with default `https://openrouter.ai/api/v1` and `Vandalizer` app attribution; honors a custom endpoint for self-hosted gateways. `claude-*` model names still auto-detect to `openai` for back-compat — opt in to native Anthropic by selecting it explicitly in the dropdown.
- Admins can now pick the default LLM model from System Config
- Cmd/Ctrl+F find-in-document search for PDF, DOCX, and spreadsheet viewers
- Knowledge base export and import in the UI; file uploads and folder filtering when adding to a KB
- Workflow JSON import on the Workflows page, with a toast on import success
- LLM-powered "Improve" button in the Prompt task editor
- Real Word (.docx) download for workflow results; multi-step workflow deliverables bundled as ZIP at download
- API tab on the extraction editor with ready-to-copy curl and Python snippets; `/extractions/run-integrated` accepts raw text input
- Context-budget planner and compaction for chat requests; auto-grow chat input textarea with highlight focus ring; uploaded documents attach to the chat context immediately
- Admin Certifications panel showing user progress with a debug unlock; fullscreen mode in the certification panel
- Demo program admin: Applications / Surveys subtabs, plus `credentials_sent_at` and `last_login_at` tracking in CSV export
- Analytics: time range extended to 2 years and CSV export coverage broadened
- Support Center promoted to a true agent workspace under the Teams dropdown — agent ticket filing, support-agent tags, default open filter, attachments on ticket creation, shareable ticket URLs, and email notifications to other agents on tag changes
- In-app trial check-in card for users approaching trial expiration
- `setup.sh`: cron-based auto-update option, auto-prompt for upgrade when running an outdated version, and code + catalog versions shown on setup with `Scan & upgrade` replacing `Upgrade`
- `seed_catalog`: `--only` flag and upsert semantics for safer reseeding
- `docs/api.md` external API reference, linked from the README
- Backend test coverage: +11 test files in the first installment, plus tightened CI gates for stability

### Changed
- `compose.yaml`: backend and Celery services now set `nofile` ulimits to 8192 soft/hard. **Operator action: rebuild and restart the stack** (`./setup.sh --redeploy` or `docker compose up -d`) to pick up the new limits — required to avoid `EMFILE` under heavy KB ingest load
- `DEPLOY.md`: Models section now documents the `anthropic` and `openrouter` protocols alongside `openai`/`ollama`/`vllm`
- KB ingest pipeline shares a single ONNX embedder and Chroma client to avoid file-descriptor exhaustion
- Compact extraction editor tabs with icons and responsive collapse; the API tab is folded into Advanced
- PDFs open inline in a new tab instead of triggering a download
- Document validation surfaces its reason in a tooltip on the file warning icon
- Workflow run button shows a "Select a document to run" hint when muted; clearer errors when adding a workflow task fails
- Folder breadcrumb navigation made more discoverable; file-browser checkbox hit target now spans the whole cell
- Library and extraction list sidebars refresh their cache after a workflow or extraction import
- Move Support Center to the Teams dropdown for support agents; support notifications open the ticket directly, and ticket clicks open in the chat panel
- Removed em dashes and double em dashes from user-visible UI text and messages
- Removed the admin "Debugging" tab from the Admin panel
- Pass document text into `ResearchNode` and `FormFillerNode` on a Document trigger
- Aggregate extraction fields across all tasks in certification validators
- Send a set-password email to SSO-only users who hit "forgot password"
- Respect `thinking=false` in LLM requests; route Qwen thinking toggles through `chat_template_kwargs`
- Deeper XLSX, DOCX, and PDF extraction tuned for research-admin documents; CSV parser and OCR improvements
- Sanitize PDF download text for fpdf core-font latin-1 encoding
- Allow `.txt` / `.md` files through upload validation and the secondary picker
- Capture selected docs when launching a prompt task from the library
- Library: surface unprocessed chat docs; fix `last used` timezone, sorting, and highlighting; "Move to folder" label no longer opens the item
- Stop long document titles from squeezing out the reveal-markdown button
- Portal the verified-workflow preview modal to escape its panel stacking context
- Make Import Definition replace the open workflow; Advanced tab UI cleanup
- Move extraction import/export cards to the top of the Tools tab; import extraction definitions into the open SearchSet

### Fixed
- `EMFILE: too many open files` errors on KB ingest under load
- KB collection deletion is now idempotent when the collection is already absent
- Endless spinner and missing OAuth flow on team-invite acceptance
- Workflow Document-trigger input handling and Input-tab drop zone
- Automation wizard "Importing a module script failed" error
- "Add Document" task search boxes not surfacing files
- `500` on `GET /api/workflows/{id}` when dict fields held raw ObjectIds
- Library share crash from an invalid `SearchSetItem.space_id` access
- `admin.py` use of `get_agent_model`
- Chat: persist a placeholder assistant turn when the stream fails so the conversation does not appear to silently drop
- Several unresolved Sentry errors in `vandalizer-backend`
- Clear the extraction-result highlight when the viewed document changes

### Security
- Gate automation editing on the `can_manage` permission so non-managers cannot mutate automation configs
- Only notify configured support contacts on new tickets and messages, not all admins

## [v4.1.0] - 2026-04-20

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
