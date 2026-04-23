# Agentic Chat — Tools Reference

*For developers, admins, and power users. A complete catalog of the 19 pydantic-ai tools the agentic chat can call, with parameters, return shapes, and authorization rules.*

All tools live in `backend/app/services/chat_tools.py` and are registered on the agentic chat agent via `@agent.tool` in `llm_service.py`. They receive a `RunContext[AgenticChatDeps]` carrying the current user, their team access, the active conversation, and a shared `quality_annotations` sidecar dict keyed by tool-call ID.

## Table of contents

1. [Authorization model](#authorization-model)
2. [Quality sidecar](#quality-sidecar)
3. [Read-only tools](#read-only-tools)
4. [Extraction tools](#extraction-tools)
5. [Knowledge-base write tools](#knowledge-base-write-tools)
6. [Workflow orchestration tools](#workflow-orchestration-tools)
7. [Validation & guided verification tools](#validation--guided-verification-tools)

---

## Authorization model

Every tool enforces both scopes:

- **User scope** — the caller must own the resource (`user_id` match) or the resource is global.
- **Team scope** — the caller must be a member of the resource's team. Resources with `team_id is None` are the caller's personal workspace.

Tools that write (KB creation, URL ingestion, workflow dispatch, extraction-set creation, validation runs) always require explicit confirmation. They accept a `confirmed: bool = False` flag; the first call returns a preview response with `needs_confirmation: true` in its payload, and the LLM re-calls with `confirmed=True` after the user approves.

Write operations also emit admin audit events (`AdminAuditLog`) with the acting user, operation name, and target IDs.

---

## Quality sidecar

Tools that return validation metadata embed it under a `quality` key in the response dict. `chat_service.py:718-722` strips this key before the LLM sees the payload, then yields it to the frontend as part of the `tool_result` chunk. The frontend renders the metadata via `QualityBadge` and related components.

Shape (see [QUALITY_SIGNALS_EXPLAINED.md](./QUALITY_SIGNALS_EXPLAINED.md) for the full breakdown):

```ts
{
  score: number | null          // 0–100 unified score
  tier: "excellent" | "good" | "fair" | "poor" | null
  grade: "A" | "B" | "C" | ... | null
  accuracy: number | null       // 0–1
  consistency: number | null    // 0–1
  last_validated_at: string | null
  num_test_cases: number | null
  num_runs: number | null
  active_alerts: Array<{type: string, severity: "critical" | "warning", message: string}>
}
```

---

## Read-only tools

### `search_documents`
Regex-matched document search across the caller's personal and team-accessible workspaces.

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | string | required | Free-text; tokenized and fuzzy-matched against title, content, and filename |
| `folder_id` | string? | null | Restrict to a folder |
| `limit` | int | 20 | Max results (1–50) |

**Returns:** list of `{uuid, title, extension, pages, classification, folder}` objects.

### `list_documents`
Enumerate a folder or the workspace root.

| Param | Type | Default | Notes |
|---|---|---|---|
| `folder_id` | string? | null | If null, returns personal + team root |
| `limit` | int | 50 | Max docs (1–200) |

**Returns:** `{folders: [...], documents: [...]}`.

### `search_knowledge_base`
Semantic search against a single KB via ChromaDB.

| Param | Type | Default | Notes |
|---|---|---|---|
| `kb_uuid` | string | required | Must be in the caller's team access |
| `query` | string | required | Natural-language query |
| `limit` | int | 5 | Max chunks (1–10) |

**Returns:** list of `{content, source_name, source_type, document_uuid, url}` chunks.

### `list_knowledge_bases`
List KBs the caller can read.

| Param | Type | Default | Notes |
|---|---|---|---|
| `limit` | int | 20 | Max results |

**Returns:** list of `{uuid, title, status, total_sources, total_chunks, verified}`.

### `list_extraction_sets`
List extraction templates (verified templates first, sorted by quality tier).

| Param | Type | Default | Notes |
|---|---|---|---|
| `domain` | string? | null | Filter by domain (`nsf`, `nih`, `dod`, `doe`, `general`) |
| `limit` | int | 20 | Max results |

**Returns:** list of `{uuid, title, verified, field_count, domain}`. Each entry carries a `quality` sidecar.

### `list_workflows`
List workflows the caller can invoke.

| Param | Type | Default | Notes |
|---|---|---|---|
| `verified_only` | bool | false | Filter to verified |
| `limit` | int | 20 | Max results |

**Returns:** list of `{id, name, description, verified, step_count}`. Carries a `quality` sidecar.

### `get_quality_info`
Inspect the quality record for an extraction set or workflow without running anything.

| Param | Type | Default | Notes |
|---|---|---|---|
| `resource_kind` | `"extraction_set" \| "workflow"` | required | |
| `resource_id` | string | required | |

**Returns:** `{score, tier, grade, accuracy, consistency, last_validated_at, active_alerts}`.

### `search_library`
Search the verified-item library across kinds (workflows, extractions, KBs).

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | string | required | Free-text |
| `kinds` | list[string]? | all | Filter to one or more item kinds |
| `limit` | int | 20 | Max results |

**Returns:** list of `{item_id, kind, name, tags, verified, quality_score}`.

---

## Extraction tools

### `get_document_text`
Return the full text of a document (truncated to 30K characters) so the agent can reason about it before running an extraction.

| Param | Type | Default | Notes |
|---|---|---|---|
| `document_uuid` | string | required | Must be accessible to the caller |

**Returns:** `{uuid, title, text, truncated: bool, pages}`.

### `run_extraction`
Run an extraction template against 1–10 documents.

| Param | Type | Default | Notes |
|---|---|---|---|
| `extraction_set_uuid` | string | required | Template to run |
| `document_uuids` | list[string] | required | Length 1–10 |

**Returns:** `{entities: [...], field_names: [...], quality: {...}}`. If the template is validated, `quality` carries the sidecar.

---

## Knowledge-base write tools

All require a two-step confirmation flow (`confirmed=false` → preview; `confirmed=true` → execute).

### `create_knowledge_base`

| Param | Type | Default | Notes |
|---|---|---|---|
| `title` | string | required | |
| `description` | string? | null | |
| `team_id` | string? | null | Scope to a team the caller belongs to |
| `confirmed` | bool | false | Second call sets true |

**Returns:** `{needs_confirmation: true, preview: {...}}` or `{created: true, uuid, title}`.

### `add_documents_to_kb`
Chunk and index 1–20 documents into a KB.

| Param | Type | Default | Notes |
|---|---|---|---|
| `kb_uuid` | string | required | |
| `document_uuids` | list[string] | required | Length 1–20 |
| `confirmed` | bool | false | |

**Returns:** confirmation response → `{added: N, chunks: M, kb_uuid}`.

### `add_url_to_kb`
Ingest a single URL (plus optional crawl, up to 5 pages).

| Param | Type | Default | Notes |
|---|---|---|---|
| `kb_uuid` | string | required | |
| `url` | string | required | HTTP(S) |
| `crawl` | bool | false | If true, crawl 5 linked pages on the same domain |
| `confirmed` | bool | false | |

**Returns:** confirmation response → `{started: true, task_id}` (ingestion runs async).

---

## Workflow orchestration tools

### `run_workflow`
Dispatch a workflow asynchronously via Celery.

| Param | Type | Default | Notes |
|---|---|---|---|
| `workflow_id` | string | required | Must be invokable by caller |
| `document_uuids` | list[string] | required | Length 1–10 |
| `confirmed` | bool | false | Write-style confirmation |

**Returns:** confirmation response → `{session_id, started_at, steps_total}`. Poll status via `get_workflow_status`.

**Side effect:** increments `User.chat_workflow_count` and sets `first_chat_workflow_at` (via `engagement_service.record_chat_workflow_run`).

### `get_workflow_status`
Poll a workflow session.

| Param | Type | Default | Notes |
|---|---|---|---|
| `session_id` | string | required | Returned by `run_workflow` |

**Returns:** `{status, steps_completed, steps_total, current_step, output?, error_detail?, approval_request_id?}`.

`status` is one of: `queued`, `running`, `paused_for_approval`, `completed`, `failed`.

---

## Validation & guided verification tools

### `list_test_cases`

| Param | Type | Default | Notes |
|---|---|---|---|
| `extraction_set_uuid` | string | required | |

**Returns:** list of `{test_case_id, document_uuid, document_title, ground_truth: {...}}`.

### `propose_test_case`
Run the extraction once on a document, create a `VerificationSession` (not a persisted test case yet), and open the frontend's guided verification modal so the user can approve or correct each extracted value in document context.

| Param | Type | Default | Notes |
|---|---|---|---|
| `extraction_set_uuid` | string | required | |
| `document_uuid` | string | required | |

**Returns:** `{verification_session_id, proposed_values: {...}, launcher_url}`. The frontend uses `launcher_url` to open the modal.

### `run_validation`
Run the extraction N times against each test case, compute the unified score, and persist a `ValidationRun`.

| Param | Type | Default | Notes |
|---|---|---|---|
| `extraction_set_uuid` | string | required | |
| `runs_per_case` | int | 3 | 1–5 |
| `confirmed` | bool | false | |

**Returns:** confirmation response → `{validation_run_id, score, tier, grade, accuracy, consistency, num_test_cases}`. Updates the template's `quality_tier`. Runs in a background thread with a 120-second timeout.

### `create_extraction_from_document`
Analyze 1–5 documents, propose extraction fields via LLM, and create a new `SearchSet`.

| Param | Type | Default | Notes |
|---|---|---|---|
| `document_uuids` | list[string] | required | Length 1–5 |
| `domain` | string? | null | `nsf`, `nih`, `dod`, `doe`, `general` — biases field suggestions |
| `confirmed` | bool | false | |

**Returns:** confirmation response → `{extraction_set_uuid, title, fields: [...]}`.

---

## Adding a new tool

1. Implement `async def your_tool(ctx: RunContext[AgenticChatDeps], ...)` in `chat_tools.py`.
2. Enforce user + team scoping via `_build_owner_filter(ctx.deps)` or equivalent.
3. If the tool writes, add a two-step confirmation pattern (see `create_knowledge_base` for the canonical shape).
4. If it returns quality metadata, populate `ctx.deps.quality_annotations[ctx.tool_call_id]` — it will be stripped from LLM context and streamed to the frontend separately.
5. Append the function to `TOOLS` at the bottom of `chat_tools.py`; the agent factory picks it up automatically.
6. Add a frontend label mapping in `ToolCallDisplay.tsx` (category color + human-readable summary) so the live streaming UX looks right.
7. Add a test: `backend/tests/test_chat_tools_<name>.py`. Confirm both the happy path and an unauthorized-access denial.

See `AGENTIC_CHAT_PLAN.md` for the architectural decisions behind this design.
