# Vandalizer React + FastAPI Migration Plan

## Phase 1: Project Scaffold + Auth + File Browser — DONE

### Step 1: Backend Scaffold — DONE
- [x] `pyproject.toml` with all deps (fixed hatchling `packages = ["app"]`)
- [x] `app/config.py` — Pydantic Settings reading `.env`
- [x] `app/database.py` — Motor + Beanie init
- [x] `app/main.py` — FastAPI with lifespan, CORS, health endpoint
- [x] Verified: `GET /api/health` returns 200

### Step 2: Backend Models — DONE
- [x] `models/user.py` — User (collection: `user`)
- [x] `models/team.py` — Team + TeamMembership (collections: `team`, `team_membership`)
- [x] `models/document.py` — SmartDocument (collection: `smart_document`)
- [x] `models/folder.py` — SmartFolder (collection: `smart_folder`)
- [x] All use `PydanticObjectId` for refs, `Field(default_factory=...)` for datetimes
- [x] Verified: App starts, connects to shared `osp` database

### Step 3: Backend Auth — DONE
- [x] `utils/security.py` — JWT create/decode, werkzeug password hashing
- [x] `schemas/auth.py` — LoginRequest, RegisterRequest, UserResponse
- [x] `dependencies.py` — `get_current_user()` from httpOnly cookie
- [x] `services/auth_service.py` — authenticate, register (with team provisioning)
- [x] `routers/auth.py` — POST /login, /register, /logout, /refresh, GET /me
- [x] Verified: Register user, login, GET /me returns user

### Step 4: Backend File/Document/Folder Routes — DONE
- [x] `utils/file_validation.py` — `is_allowed_file()`, `is_valid_file_content()`
- [x] `services/file_service.py` — upload, download, delete, rename, move
- [x] `services/folder_service.py` — create, rename, delete (cascade), breadcrumbs
- [x] `services/document_service.py` — list contents, poll status
- [x] `routers/files.py` — POST upload, GET download, DELETE, PATCH rename/move
- [x] `routers/folders.py` — POST create, PATCH rename, DELETE, GET breadcrumbs
- [x] `routers/documents.py` — GET list, GET poll_status
- [x] Verified: Upload PDF, list documents, rename, delete, create/rename/delete folders

### Step 5: Backend Celery Integration — DONE
- [x] `celery_app.py` — Celery instance with shared Redis broker + task routing
- [x] `tasks/upload_tasks.py` — `dispatch_upload_tasks()` chains extraction → update, with cleanup on error, plus background validation. Uses exact Flask task names: `tasks.document.extraction`, `tasks.document.update`, `tasks.document.cleanup`, `tasks.upload.validation`
- [x] Wired into `file_service.upload_document()` — dispatches tasks after document insert, stores task_id on document

### Step 6: Frontend Scaffold — DONE
- [x] Vite + React 19 + TypeScript + Tailwind CSS v4
- [x] `vite.config.ts` — proxy `/api` → `http://localhost:8001`
- [x] Routing, types, `lib/cn.ts`
- [x] Verified: `npm run dev` serves at localhost:5173 (requires Node >= 20 via `nvm use 22`)

### Step 7: Frontend Auth — DONE
- [x] `api/client.ts`, `api/auth.ts`, `contexts/AuthContext.tsx`
- [x] `ProtectedRoute.tsx`, `Login.tsx`, `Register.tsx`
- [x] Verified: Login/register works, session persists on refresh

### Step 8: Frontend File Browser — DONE
- [x] All components: FileBrowser, FileList, Breadcrumbs, UploadZone, UploadProgress, ContextMenu, RenameDialog, CreateFolderDialog
- [x] Hooks: useDocuments (with auto-poll), useUpload, useFolders

### Phase 1 Remaining Work — ALL DONE
- [x] **Wire Celery dispatch** — `file_service.upload_document()` calls `dispatch_upload_tasks()` after document insert
- [x] **Fix UPLOAD_DIR** — `.env` points at absolute path to Flask's `app/static/uploads`
- [x] **Verified** — backend imports clean, task names match Flask's registered Celery tasks
- **Note**: Full end-to-end upload→process→complete requires Celery workers running (`./run_celery.sh start`)

---

## Phase 2: Teams + Spaces — NOT STARTED

Migrates: Flask blueprints `teams` (12 routes), `spaces` (2 routes), team-related models

### Backend
- [ ] **Model**: `TeamInvite` (collection: `team_invite`) — pending invitations
- [ ] **Model**: `Space` (collection: `space`) — collaborative workspace
- [ ] `schemas/teams.py` — TeamResponse, InviteRequest, MemberResponse
- [ ] `schemas/spaces.py` — SpaceResponse, CreateSpaceRequest
- [ ] `services/team_service.py` — list teams, switch team, invite member, remove member, update roles
- [ ] `services/space_service.py` — create space, list spaces
- [ ] `routers/teams.py` — GET /api/teams (list), POST /api/teams/switch, POST /api/teams/invite, DELETE /api/teams/members/:id, PATCH /api/teams/members/:id/role
- [ ] `routers/spaces.py` — GET /api/spaces, POST /api/spaces
- [ ] Update `dependencies.py` — add `get_current_team()` dependency
- [ ] Update document/folder queries to scope by `team_id` when in team context

### Frontend
- [ ] `types/team.ts` — Team, TeamMembership, TeamInvite types
- [ ] `api/teams.ts` — team CRUD + invite API calls
- [ ] `contexts/TeamContext.tsx` — current team state, team switching
- [ ] `hooks/useTeams.ts` — team list, invite, member management
- [ ] `components/layout/TeamsDropdown.tsx` — team switcher in header
- [ ] `pages/TeamSettings.tsx` — manage team members, invitations
- [ ] Update `FileBrowser.tsx` — scope document listing by current team's space
- [ ] Update `Sidebar.tsx` — show team-shared folders

---

## Phase 3: Extraction & Workflows — NOT STARTED

Migrates: Flask blueprints `workflows` (40+ routes), `tasks` (extraction/prompt management). This is the largest and most complex phase.

### Backend — Models (8 new models)
- [ ] `models/workflow.py` — Workflow, WorkflowStep, WorkflowStepTask, WorkflowResult, WorkflowAttachment, WorkflowArtifact
- [ ] `models/search_set.py` — SearchSet, SearchSetItem (extraction definitions)
- [ ] `models/user_config.py` — UserModelConfig (per-user LLM settings)
- [ ] `models/system_config.py` — SystemConfig (runtime-editable system settings)

### Backend — Extraction Engine
- [ ] `services/extraction_service.py` — port extraction logic from `utilities/extraction_manager_nontyped.py`. Strategies: `one_pass` (single structured extraction) and `two_pass` (thinking draft → structured final)
- [ ] `services/llm_service.py` — port agent creation from `utilities/agents.py`. Model resolution, OpenAI-compatible protocol, Redis-backed caching
- [ ] `routers/extractions.py` — CRUD for SearchSet/SearchSetItem (extraction definitions), run extraction on document
- [ ] `routers/user_config.py` — GET/PUT user model settings (temperature, model selection)

### Backend — Workflow Engine
- [ ] `services/workflow_service.py` — port workflow execution from `utilities/workflow.py`. ThreadPoolExecutor parallelism, graphlib dependency resolution
- [ ] `routers/workflows.py` — CRUD for workflows, steps, step tasks. Run workflow, check status, download results
- [ ] `tasks/workflow_tasks.py` — dispatch workflow execution and step testing to Celery

### Backend — Workflow Step Types
The Flask app supports these step types (each needs a handler):
- [ ] Extraction step — run SearchSet against documents
- [ ] Prompt step — run freeform LLM prompt
- [ ] Formatter step — transform/format extraction output
- [ ] Attachment step — include file attachments
- [ ] Document step — reference other documents
- [ ] Browser automation step — Chrome extension interaction
- [ ] Document renderer step — render output documents
- [ ] Form filler step — fill PDF forms from extraction data
- [ ] Data export step — export to external systems
- [ ] Package builder step — bundle outputs

### Frontend
- [ ] `types/workflow.ts` — Workflow, WorkflowStep, SearchSet, etc.
- [ ] `api/workflows.ts`, `api/extractions.ts` — CRUD + execution API calls
- [ ] `pages/WorkflowEditor.tsx` — workflow builder page (step configuration, dependencies, execution)
- [ ] `pages/ExtractionPanel.tsx` — extraction definition editor
- [ ] `components/workflows/WorkflowStepList.tsx` — ordered list of steps with dependency visualization
- [ ] `components/workflows/WorkflowStepEditor.tsx` — per-step configuration
- [ ] `components/workflows/WorkflowResults.tsx` — results viewer + download
- [ ] `components/workflows/WorkflowStatus.tsx` — execution progress tracking
- [ ] `components/extractions/ExtractionBuilder.tsx` — search set item editor
- [ ] `components/extractions/ExtractionResults.tsx` — extraction output viewer
- [ ] Add workflow panel to Workspace sidebar

---

## Phase 4: Chat & RAG — NOT STARTED

Migrates: Chat functionality from `home` blueprint (8 routes), `ChatConversation`/`ChatMessage` models

### Backend
- [ ] `models/chat.py` — ChatConversation, ChatMessage, FileAttachment, UrlAttachment
- [ ] `services/chat_service.py` — port streaming chat from `utilities/chat_manager.py`. RAG with ChromaDB vector search, conversation persistence, document context
- [ ] `routers/chat.py` — POST /api/chat (streaming SSE), GET /api/chat/history/:id, DELETE /api/chat/history/:id, POST /api/chat/add_document, POST /api/chat/add_link, DELETE /api/chat/remove_document/:id, POST /api/chat/download
- [ ] ChromaDB integration — query vectors for relevant document chunks
- [ ] SSE (Server-Sent Events) streaming for chat responses

### Frontend
- [ ] `types/chat.ts` — Conversation, Message, Attachment types
- [ ] `api/chat.ts` — chat API with SSE streaming support
- [ ] `hooks/useChat.ts` — message state, streaming, conversation management
- [ ] `pages/Chat.tsx` — or integrate chat panel into Workspace
- [ ] `components/chat/ChatPanel.tsx` — conversation UI
- [ ] `components/chat/MessageList.tsx` — message display with markdown rendering
- [ ] `components/chat/ChatInput.tsx` — message input with file/URL attachment
- [ ] `components/chat/ConversationList.tsx` — conversation history sidebar
- [ ] `components/chat/AttachmentBar.tsx` — show attached documents
- [ ] Add Marked.js or similar for markdown rendering in chat messages

---

## Phase 5: Admin & Settings — NOT STARTED

Migrates: Flask blueprints `admin` (usage dashboard, system config), user settings, `activity` (4 routes), `feedback` (1 route)

### Backend
- [ ] `models/system_config.py` — SystemConfig (if not done in Phase 3)
- [ ] `models/activity.py` — ActivityEvent, DailyUsageAggregate
- [ ] `models/feedback.py` — Feedback, FeedbackCounter, ExtractionQualityRecord
- [ ] `routers/admin.py` — GET /api/admin/usage (dashboard data), GET/PUT /api/admin/config (system settings), GET /api/admin/users, GET /api/admin/teams
- [ ] `routers/settings.py` — GET/PUT /api/settings (user settings), POST /api/settings/api-token, DELETE /api/settings/api-token
- [ ] `routers/activity.py` — GET /api/activity/runs, GET /api/activity/streams
- [ ] `services/admin_service.py` — usage aggregation, system config management
- [ ] `services/activity_service.py` — activity tracking, streams

### Frontend
- [ ] `pages/AdminDashboard.tsx` — usage analytics, charts
- [ ] `pages/AdminConfig.tsx` — system config editor (models, auth, extraction settings, UI theme)
- [ ] `pages/AdminUsers.tsx` — user management
- [ ] `pages/Settings.tsx` — user settings, API token management
- [ ] `components/admin/UsageChart.tsx` — usage visualizations
- [ ] `components/admin/ConfigEditor.tsx` — runtime config editing
- [ ] Add admin routes (protected by `is_admin` check)
- [ ] Add settings link in header/sidebar

---

## Phase 6: Library — NOT STARTED

Migrates: Flask blueprint `library` (multiple routes), Library/LibraryItem/verification models

### Backend
- [ ] `models/library.py` — Library, LibraryItem, LibraryFolder, VerificationRequest, VerifiedItemMetadata, VerifiedCollection
- [ ] `services/library_service.py` — library CRUD, item publishing, search, verification workflow
- [ ] `routers/library.py` — GET /api/library (list), POST /api/library/items, POST /api/library/publish, GET /api/library/search, POST /api/library/verify

### Frontend
- [ ] `pages/Library.tsx` — library browser
- [ ] `components/library/LibraryPanel.tsx` — browsable library with categories
- [ ] `components/library/LibraryItemCard.tsx` — item preview + import
- [ ] `components/library/VerificationQueue.tsx` — admin verification workflow
- [ ] Add library section to sidebar

---

## Phase 7: M365 / Office Integration — NOT STARTED (optional)

Migrates: Flask blueprint `office` (multiple routes), `automation` (2 routes). Only needed if M365 integration is required.

### Backend
- [ ] `models/m365.py` — WorkItem, GraphSubscription, IntakeConfig, M365AuditEntry
- [ ] `services/graph_service.py` — port Graph API client, token management, webhook handling
- [ ] `routers/office.py` — GET /api/office/status, POST /api/office/disconnect, GET /api/office/intakes, webhooks
- [ ] `tasks/m365_tasks.py` — dispatch M365 ingestion tasks

### Frontend
- [ ] `pages/Office.tsx` — M365 connection dashboard
- [ ] `components/office/IntakeConfig.tsx` — intake rule configuration

---

## Phase 8: Browser Automation — NOT STARTED (optional)

Migrates: Flask blueprint `browser_automation` (WebSocket + HTTP). Only needed if Chrome extension integration is required.

### Backend
- [ ] `models/browser_automation.py` — LocatorStrategy, BrowserActionStep
- [ ] WebSocket support (FastAPI WebSocket or Socket.IO via python-socketio)
- [ ] `routers/browser_automation.py` — WebSocket connect/disconnect/message handlers

### Frontend
- [ ] `components/browser_automation/RecordingPanel.tsx` — step recording UI

---

## Development Setup Reference

```bash
# Infrastructure
docker compose up redis mongo chromadb

# Existing Flask app (port 5003) — runs side-by-side
python run.py

# Existing Celery workers — shared by both apps
./run_celery.sh start

# New backend (port 8001)
cd vandalizer-next/backend
uv sync
cp .env.example .env  # set MONGO_HOST=mongodb://localhost:27018/
uvicorn app.main:app --port 8001

# New frontend (port 5173) — requires Node >= 20
cd vandalizer-next/frontend
nvm use 22
npm install
npm run dev
```

## Critical Compatibility Notes

1. **Shared database**: Both apps read/write `osp`. Beanie `Settings.name` must match MongoEngine collection names exactly.
2. **Password hashes**: Use werkzeug (not bcrypt/passlib) so existing passwords work.
3. **Upload paths**: Same structure `static/uploads/{user_id}/{uuid}.{ext}`. Point `UPLOAD_DIR` at the same directory.
4. **Celery tasks**: Dispatch by name to existing workers via shared Redis. No new workers needed.
5. **ObjectId references**: MongoEngine stores raw ObjectIds for ReferenceField. Use `PydanticObjectId` in Beanie, not `Link`.
6. **MongoDB port**: Docker Compose maps Mongo to `localhost:27018` (not 27017).
