# Agentic Chat Implementation Plan

## Status: ALL PHASES COMPLETE

- **Phase 1** (Read-only tools): DONE — 8 tools
- **Phase 2** (Extraction tools): DONE — 2 tools
- **Phase 3** (KB write tools): DONE — 3 tools
- **Phase 4** (Workflow orchestration): DONE — 2 tools
- **Frontend**: DONE — ToolCallDisplay, QualityBadge, extended useChat + ChatMessage + ChatPanel
- **Tests**: DONE — 17 unit tests passing, 31 existing chat tests passing, TypeScript clean

**Total: 15 tools registered, full end-to-end streaming pipeline, quality sidecar pattern**

---

## Context

Vandalizer's chat is currently a prompt-response system with document/KB context injection. Users across the industry are using raw Claude Code + file stores with zero quality guarantees. Vandalizer already has validated workflows, extraction engines, quality scoring, audit trails, and verification gates — but these are only accessible through dedicated UI pages, not through chat.

This plan transforms the chat into a fully agentic system where the LLM can invoke Vandalizer's services as pydantic-ai tools, surfacing quality/trust signals inline. The result: administrators can search documents, run extractions, query knowledge bases, execute workflows, and check quality — all through conversation, with every action audited and quality-annotated.

---

## Architecture Overview

```
Today:
  User message → context assembly → LLM generates text → stream back

Agentic:
  User message → context assembly → LLM reasons → calls tools →
  tools execute services → quality metadata attached as sidecar →
  results fed back to LLM → LLM reasons again →
  streams response with inline quality signals
```

Key design principle: **Quality metadata flows to the frontend as a sidecar, never polluting the LLM context.** Tools write quality annotations to a shared dict on the deps dataclass keyed by `tool_call_id`. The streaming layer reads these when emitting `tool_result` events.

---

## Verified pydantic-ai API (v1.56+)

- `Agent.is_call_tools_node(node)` — identifies tool execution nodes in `agent.iter()` loop
- `Agent.is_model_request_node(node)` — identifies model request nodes (already used)
- `CallToolsNode.stream(ctx)` — yields async iterators of `HandleResponseEvent`
- `FunctionToolCallEvent.part` — `ToolCallPart` with `.tool_name`, `.args`, `.tool_call_id`
- `FunctionToolResultEvent.result` — `ToolReturnPart` with `.tool_name`, `.content`, `.tool_call_id`
- `Agent(model, deps_type=T, system_prompt=...)` — dependency injection via `RunContext[T]`
- `@agent.tool` decorator — registers tool functions (can be sync or async)
- Existing pattern in codebase: `RagDeps` dataclass + `@agent.tool def retrieve(context: RunContext[RagDeps], ...)` in `llm_service.py:599-653`

---

## Phase 1: Backend Foundation — Read-Only Tools

### Step 1: Create `AgenticChatDeps` dataclass

**New file: `backend/app/services/chat_deps.py`**

```python
from dataclasses import dataclass, field
from typing import Optional
from app.models.user import User
from app.services.access_control import TeamAccessContext

@dataclass
class AgenticChatDeps:
    user: User                              # Full user object for authorization
    user_id: str
    team_id: str | None
    team_access: TeamAccessContext           # Pre-computed team memberships/roles
    organization_id: str | None
    system_config_doc: dict                  # For ExtractionEngine, model resolution
    model_name: str                          # Current model for sub-agent calls
    context_document_uuids: list[str]        # Documents selected in chat context
    active_kb_uuid: str | None               # KB selected in chat context
    quality_annotations: dict[str, dict] = field(default_factory=dict)
    # ^^ tool_call_id -> quality metadata sidecar (not sent to LLM)
```

### Step 2: Create tool functions

**New file: `backend/app/services/chat_tools.py`**

Eight read-only tools for Phase 1:

| Tool | Wraps | Returns |
|------|-------|---------|
| `search_documents(query, folder_uuid?)` | `SmartDocument.find()` regex | `[{uuid, title, extension, pages, classification}]` (max 20) |
| `list_documents(folder_uuid?)` | `SmartDocument.find()` + `SmartFolder.find()` | `{folders: [...], documents: [...]}` |
| `search_knowledge_base(query, kb_uuid?)` | `DocumentManager.query_kb()` | `[{content, source_name, chunk_index}]` |
| `list_knowledge_bases()` | `KnowledgeBase.find()` scoped by team | `[{uuid, title, status, total_sources, total_chunks, verified}]` |
| `list_extraction_sets(search?)` | `SearchSet.find()` scoped by team | `[{uuid, title, verified, field_count, domain}]` |
| `list_workflows(search?)` | `Workflow.find()` scoped by team | `[{uuid, title, verified, step_count}]` |
| `get_quality_info(item_kind, item_uuid)` | `ValidationRun.find()` + `QualityAlert.find()` | `{score, tier, grade, last_validated, active_alerts, test_cases}` |
| `search_library(query, kind?)` | `library_service.search_libraries()` | `[{item_id, kind, name, tags, verified, quality_score}]` |

Each tool:
1. Receives `context: RunContext[AgenticChatDeps]`
2. Uses `context.deps.user` / `context.deps.team_access` for authorization
3. Returns truncated results (max items per tool)
4. For quality-relevant results: writes to `context.deps.quality_annotations[tool_call_id]`

All tools exported as `TOOLS` list for registration.

### Step 3: Create agentic agent factory

**Modify: `backend/app/services/llm_service.py`**

- Add `_agentic_chat_agent_cache: dict[str, Agent] = {}`
- Add `create_agentic_chat_agent()` function: creates Agent with `deps_type=AgenticChatDeps`, registers all tools from `chat_tools.TOOLS`
- Add `AGENTIC_CHAT_SYSTEM_PROMPT` constant
- Update `clear_agent_caches()` to also clear `_agentic_chat_agent_cache`

### Step 4: Extend streaming protocol

**Modify: `backend/app/services/chat_service.py`**

Add imports:
```python
from pydantic_ai.messages import FunctionToolCallEvent, FunctionToolResultEvent
```

Extend `chat_stream()` signature with `user: User | None = None, team_access: TeamAccessContext | None = None`.

Agent selection: if user + team_access provided → create agentic agent with deps; else → fall back to plain agent.

Extend streaming loop with `elif Agent.is_call_tools_node(node):` block that:
1. Streams `tool_stream` from `node.stream(agent_run.ctx)`
2. On `FunctionToolCallEvent`: yields `{"kind": "tool_call", "tool_name": ..., "tool_call_id": ..., "args": ...}`
3. On `FunctionToolResultEvent`: pops quality from `deps.quality_annotations`, yields `{"kind": "tool_result", "tool_name": ..., "content": ..., "quality": ...}`

Pass deps to `agent.iter()`: `agent.iter(prompt, message_history=previous_messages, deps=deps)`

### Step 5: Pass user context from router

**Modify: `backend/app/routers/chat.py`**

Add `user=user, team_access=team_access` to the `chat_stream()` call. The router already resolves both.

---

## Phase 2: Extraction Tools

### Step 6: Add extraction tools to `chat_tools.py`

```python
async def run_extraction(context, extraction_set_uuid: str, document_uuids: list[str]) -> dict:
    """Run extraction set against documents. Returns extracted entities."""
    # 1. Authorize documents
    # 2. Load SearchSet, get field keys
    # 3. Load document raw_text
    # 4. ExtractionEngine.extract() via asyncio.to_thread()
    # 5. Query ValidationRun for quality score
    # 6. Write quality to context.deps.quality_annotations
    # 7. Return {entities: [...], fields: [...], token_usage: {...}}

async def get_document_text(context, document_uuid: str) -> dict:
    """Get full text content of a document."""
```

---

## Phase 3: Write Tools

### Step 8: Add write tools

```python
async def create_knowledge_base(context, title: str, description: str = "") -> dict:
async def add_documents_to_kb(context, kb_uuid: str, document_uuids: list[str]) -> dict:
async def add_url_to_kb(context, kb_uuid: str, url: str, crawl: bool = False) -> dict:
```

Each logs an audit event via `audit_service.log_event()`.

---

## Phase 4: Workflow Orchestration

### Step 9: Add workflow tools

```python
async def run_workflow(context, workflow_uuid: str, document_uuids: list[str]) -> dict:
    # Dispatches Celery task, returns workflow_result_id for polling

async def get_workflow_status(context, workflow_result_id: str) -> dict:
    # Returns status, step progress, partial results
```

---

## Frontend Changes

### Step 10: Extend types

**Modify: `frontend/src/types/chat.ts`**

- Add `'tool_call' | 'tool_result'` to `StreamChunk.kind` union
- Add `tool_name?`, `tool_call_id?`, `args?`, `quality?` optional fields to `StreamChunk`
- Add `tool_calls?` and `tool_results?` arrays to `ChatMessage`

### Step 11: Extend useChat hook

**Modify: `frontend/src/hooks/useChat.ts`**

- Add `activeToolCalls` and `toolResults` state + refs
- Add `'tool_call'` and `'tool_result'` chunk handler cases
- Attach to final assistant message, reset on new send
- Return new state from hook

### Step 12: Create ToolCallDisplay component

**New file: `frontend/src/components/chat/ToolCallDisplay.tsx`**

Renders inline in message area:
- Active tool calls: tool name + spinner + human-readable args
- Completed results: collapsible section with result summary
- Quality badge when present

### Step 13: Create QualityBadge component

**New file: `frontend/src/components/chat/QualityBadge.tsx`**

Pill component: `[Verified · Score 87]` with tier-based colors (gold/silver/bronze).

### Step 14: Wire into ChatMessage and ChatPanel

**Modify: `frontend/src/components/chat/ChatMessage.tsx`**
- Accept `activeToolCalls` and `toolResults` props
- Render `<ToolCallDisplay>` between thinking and text content

**Modify: `frontend/src/components/chat/ChatPanel.tsx`**
- Destructure new values from `useChat()`
- Pass to streaming ChatMessage instance

---

## File Summary

### New files
| File | Purpose |
|------|---------|
| `backend/app/services/chat_deps.py` | AgenticChatDeps dataclass |
| `backend/app/services/chat_tools.py` | All tool function definitions + TOOLS list |
| `frontend/src/components/chat/ToolCallDisplay.tsx` | Tool call/result renderer |
| `frontend/src/components/chat/QualityBadge.tsx` | Quality tier badge |
| `backend/tests/test_chat_tools.py` | Tool unit tests |

### Modified files
| File | Change |
|------|--------|
| `backend/app/services/llm_service.py` | Add `create_agentic_chat_agent()`, `AGENTIC_CHAT_SYSTEM_PROMPT`, update `clear_agent_caches()` |
| `backend/app/services/chat_service.py` | Add `user`/`team_access` params, agent selection, `CallToolsNode` streaming, new imports |
| `backend/app/routers/chat.py` | Pass `user` and `team_access` to `chat_stream()` |
| `frontend/src/types/chat.ts` | Add tool types to `StreamChunk`, `ChatMessage` |
| `frontend/src/hooks/useChat.ts` | Add tool state tracking, new chunk handlers |
| `frontend/src/components/chat/ChatMessage.tsx` | Accept and render tool call props |
| `frontend/src/components/chat/ChatPanel.tsx` | Pass tool state to ChatMessage |

### Existing code reused (not modified)
| File | Reused interface |
|------|-----------------|
| `backend/app/services/access_control.py` | `TeamAccessContext`, `get_authorized_document()` |
| `backend/app/services/extraction_engine.py` | `ExtractionEngine.extract()` |
| `backend/app/services/document_manager.py` | `DocumentManager.query_kb()` |
| `backend/app/services/knowledge_service.py` | All KB CRUD operations |
| `backend/app/services/library_service.py` | Library search, item listing |
| `backend/app/services/quality_service.py` | Quality score computation |
| `backend/app/models/validation_run.py` | `ValidationRun` queries |
| `backend/app/models/quality_alert.py` | `QualityAlert` queries |

---

## Backwards Compatibility

- **Non-agentic chat untouched**: Falls back to plain agent when deps are None
- **Frontend additive**: New `StreamChunk` kinds handled by new `else if` branches
- **Agent caching separate**: `_agentic_chat_agent_cache` independent from `_chat_agent_cache`
- **Message storage**: `tool_calls`/`tool_results` are optional fields (MongoDB handles gracefully)
- **System prompt selection**: Existing document/KB/onboarding prompt overrides still work

---

## Verification & Testing

### Backend
1. Unit test each tool in `test_chat_tools.py`: mock deps, verify auth + service delegation
2. Test streaming loop with mock agent: verify `tool_call`/`tool_result` chunks
3. Test fallback: plain chat still works without agentic deps
4. `make backend-ci` — no regressions

### Frontend
1. Test useChat hook: simulate tool chunks, verify state accumulation
2. Test ToolCallDisplay: render active (spinner) and completed (content) states
3. `make frontend-ci` — no regressions

### End-to-end
1. Start dev servers: `uvicorn app.main:app --reload --port 8001` + `npm run dev`
2. Chat: "What documents do I have?" → tool_call spinner → tool_result list → summarized response
3. Chat: "What's the quality of [extraction set]?" → quality badge renders inline
4. Chat: "Run [extraction] on [document]" → extraction results with quality annotation
