# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [5.0.0] — Fully Agentic

The biggest change since launch: chat now drives the entire platform. Documents, knowledge bases, extractions, and workflows are all reachable through one conversation — with quality scores, source citations, and confirmation flows built in.

### Added — Agentic chat
- **Agentic chat agent** (`create_agentic_chat_agent` in `llm_service.py`) — activates automatically whenever a request has a user and team context; falls back to plain chat otherwise
- **19 pydantic-ai tools** registered on the agentic agent across 5 categories:
  - **Read-only discovery** (8): `search_documents`, `list_documents`, `search_knowledge_base`, `list_knowledge_bases`, `list_extraction_sets`, `list_workflows`, `get_quality_info`, `search_library`
  - **Extraction** (2): `get_document_text`, `run_extraction`
  - **Knowledge-base writes** (3): `create_knowledge_base`, `add_documents_to_kb`, `add_url_to_kb` — all gated by 2-step confirmation
  - **Workflow orchestration** (2): `run_workflow` (async Celery dispatch), `get_workflow_status` (live polling)
  - **Validation & guided verification** (4): `list_test_cases`, `propose_test_case`, `run_validation`, `create_extraction_from_document`
- **Quality-signal sidecar** — tools that return validation metadata surface it via `deps.quality_annotations` (never polluting the LLM context); frontend renders `QualityBadge` with tier, accuracy, consistency, test-case count, and active alerts
- **Streaming tool-call UX** — `chat_service.py` emits `tool_call` and `tool_result` events; `ToolStatusLine` renders live spinners and result summaries; rich content blocks for extraction tables, KB passages, workflow output, and guided-verification launchers
- **Confirmation flow for writes** — KB creation, URL ingestion, extraction-set creation, workflow dispatch, and validation runs all preview first, then execute only after user confirmation
- **Landing page rewrite** — hero, feature sections, and demo flow reframed around agentic chat and quality signals; added certification callout
- **Demo-request form** — new landing-page form posting to `POST /api/demo/request-contact` with confirmation and admin-notification emails
- **v5.0 launch email funnel**:
  - One-time launch announcement email, triggerable by admins via `POST /api/admin/announcements/v5-launch`
  - 5-step agentic-chat tutorial drip (Celery beat: daily 10:15am)
  - Certification-complete celebration email (fires once per user when all 11 modules are done)
  - Idempotent send tracking via `v5_announcement_sent_at`, `agentic_drip_step`, `certification_complete_sent_at` on `User`
- **Chat milestone tracking** — `first_chat_workflow_at`, `chat_workflow_count`, `powerup_milestone_sent_at` on `User`, recorded when `run_workflow` succeeds
- **Role segmentation** — `role_segment` field on `User` for future cohort-targeted drips
- **Certification curriculum updated for v5** — Module 1 ("AI Literacy") reframed to position agentic chat as the professional answer rather than a problem; Foundations, Extraction, Multi-Step, Advanced Nodes, Output Delivery, Validation & QA, Batch, and Governance exercises rewritten to drive from chat prompts
- **Docs**: `AGENTIC_CHAT_PLAN.md` (implementation plan, all phases shipped); user and quality-signal guides in `docs/`

### Changed — v5.0
- Chat activation logic: plain chat is now a fallback; agentic agent is the default when a team context is available
- `email_preferences` gains an `announcements` key (defaults to opted-in)
- Inactivity-nudge copy updated to speak to chat usage instead of "extractions and knowledge bases ready to use"

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
