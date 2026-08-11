# Agentic Chat — Tools Reference

*For developers, admins, and power users. A complete catalog of the 49 pydantic-ai tools the agentic chat can call, with parameters, confirmation rules, and authorization notes.*

All tools live in `backend/app/services/chat_tools.py` and are exported through the `TOOLS` registry at the bottom of that module, which `llm_service.create_agentic_chat_agent()` registers on the agent. Each receives a `RunContext[AgenticChatDeps]` carrying the current user, their team access, the active conversation, the active project (if one is open), the plan state, and a shared `quality_annotations` sidecar dict keyed by tool-call ID.

> **Keeping this document honest.** `TOOLS` is the single source of truth for what the agent can do. If you add or remove a tool, update this file in the same commit — the tool count in the subtitle above, the relevant section, and the execution-model sets below.

## Table of contents

1. [Authorization model](#authorization-model)
2. [Execution model](#execution-model)
3. [Quality sidecar](#quality-sidecar)
4. [Plan and progress](#plan-and-progress)
5. [Read-only discovery tools](#read-only-discovery-tools)
6. [Web tools](#web-tools)
7. [Reading and extraction tools](#reading-and-extraction-tools)
8. [Knowledge-base write tools](#knowledge-base-write-tools)
9. [Workflow orchestration tools](#workflow-orchestration-tools)
10. [Validation and guided verification tools](#validation-and-guided-verification-tools)
11. [Autovalidate (optimizer) tools](#autovalidate-optimizer-tools)
12. [Output artifact tools](#output-artifact-tools)
13. [Project tools](#project-tools)
14. [Authoring tools](#authoring-tools)
15. [Certification tools](#certification-tools)

---

## Authorization model

The agentic agent activates only when a request carries **both a user and a team context**. Without one — an anonymous demo, or an admin with no team membership — chat falls back to plain non-agentic mode with no tool access.

Every tool enforces both scopes:

- **User scope** — the caller must own the resource (`user_id` match) or the resource is global.
- **Team scope** — the caller must be a member of the resource's team. Resources with `team_id is None` are the caller's personal workspace.

The agent never holds privileges of its own. Every tool call executes as the calling user, against that user's team access, so the agent cannot reach anything the user could not reach through the normal UI.

### The confirm gate

19 of the 49 tools mutate state, and every one of them is gated. Gated tools take a `confirmed: bool = False` parameter. The first call returns a preview payload with `needs_confirmation: true` and performs no write; the model re-calls with `confirmed=True` only after the user approves in the UI.

The gated set:

| Area | Gated tools |
|---|---|
| Knowledge bases | `create_knowledge_base`, `add_documents_to_kb`, `add_url_to_kb` |
| Workflows | `run_workflow`, `approve_workflow_step`, `reject_workflow_step` |
| Validation | `run_validation`, `create_extraction_from_document` |
| Autovalidate | `start_optimization`, `apply_optimization`, `regenerate_validation_plan` |
| Output | `save_to_folder` |
| Projects | `create_project`, `run_pin_on_project`, `pin_to_project`, `unpin_from_project`, `set_project_status` |
| Authoring | `create_automation`, `create_workflow` |

Write operations also emit admin audit events (`AdminAuditLog`) with the acting user, operation name, and target IDs.

Two workflow tools carry an additional role check beyond team scope: `approve_workflow_step` and `reject_workflow_step` require the caller to be an assigned reviewer or a workflow manager. Approval authority is not delegable to the agent — the agent can only relay a decision the user makes.

---

## Execution model

Three registry-level sets in `chat_tools.py` govern how tools run. All three are **fail-closed**: a tool is only granted the weaker treatment if it is explicitly listed.

**`PARALLEL_SAFE_TOOLS`** — tools that may execute concurrently when the model issues several calls in one response. This is `COMPACTABLE_TOOLS` plus `get_workflow_status` and `get_optimization_run`. Everything else — every gated write tool — is registered sequential, so two mutations (or a mutation and a read of its target) never race, and the confirm gate's `pending_confirmations` bookkeeping is never written from two calls at once.

**`COMPACTABLE_TOOLS`** — read-only tools whose older results may be cleared from replayed history when the conversation nears its context budget, because calling them again safely re-obtains the result. Gated write tools must **never** be added: their preview payloads must replay verbatim for the confirm handshake, and a cleared preview could let the model mis-describe what the user approved. `get_workflow_status` and `get_optimization_run` are excluded too, for staleness rather than safety reasons — their results are small and anchor in-flight processes.

**`TOOLS`** — the registration order, which is also the order the model sees them in.

---

## Quality sidecar

Tools that return validation metadata embed it under a `quality` key in the response dict. `chat_service.py` strips this key before the LLM sees the payload, then yields it to the frontend as part of the `tool_result` chunk. The frontend renders the metadata via `QualityBadge` and related components.

This split is deliberate and load-bearing: **the model cannot see the quality number, so it cannot inflate, round, or editorialize it.** The badge the user reads comes straight from stored `ValidationRun` records.

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

## Plan and progress

### `update_plan`

Updates the visible task checklist for multi-step work. The user sees a live pinned checklist, so this is how they know what the agent is doing and what remains. Registered sequential — it mutates `deps.plan_state`.

| Param | Type | Default | Notes |
|---|---|---|---|
| `tasks` | `list[dict]` | required | The **complete** list every call, never a delta |

Rules enforced by the prompt: send the full list each time, keep exactly one task `in_progress`, mark a task completed immediately on finishing it. Statuses are `pending`, `in_progress`, `completed`; the list is capped at 20 tasks. Intended for requests spanning 3+ distinct steps; skipped for single trivial actions.

---

## Read-only discovery tools

All tools in this section are parallel-safe and compactable.

### `search_documents`

Search the user's documents by title (fast) or full content (slow).

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | `str` | required | Multi-word queries match each word independently, in any order. Filler words ("the", "what's in", "document") and file extensions are stripped |
| `search_content` | `bool` | `False` | Also regex-match extracted text. Off by default: content search is a full collection scan with no text index and can time out on large workspaces |

### `list_documents`

List documents and folders in one directory level.

| Param | Type | Default | Notes |
|---|---|---|---|
| `folder_uuid` | `str?` | `None` | Omit or pass null for the root |

### `list_folders`

Every folder the user can access, flattened across the whole tree — personal and team — in a single call. Used to resolve a folder name to a UUID before `save_to_folder`. No parameters.

### `search_knowledge_base`

Semantic search over a knowledge base's chunks.

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | `str` | required | |
| `kb_uuid` | `str?` | `None` | Uses the active KB if omitted |

Returns cited passages; the frontend renders them as a clickable source list.

### `list_knowledge_bases`

Knowledge bases available to the user — personal, team-shared, and verified. No parameters.

### `list_extraction_sets`

| Param | Type | Default | Notes |
|---|---|---|---|
| `search` | `str?` | `None` | Filter templates by title |

### `list_workflows`

| Param | Type | Default | Notes |
|---|---|---|---|
| `search` | `str?` | `None` | Filter workflows by name |

### `get_quality_info`

Quality, validation, and verification metadata for one item. Also reports the latest autovalidate run — flagging pending recommendations with score deltas — and, for workflows, whether the validation plan has drifted from the definition (`validation_plan_stale`).

| Param | Type | Default | Notes |
|---|---|---|---|
| `item_kind` | `str` | required | One of `search_set`, `workflow`, `knowledge_base` |
| `item_uuid` | `str` | required | UUID or ID of the item |

### `search_library`

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | `str` | required | |
| `kind` | `str?` | `None` | One of `workflow`, `search_set`, `knowledge_base` |

### `get_app_help`

Looks up help content about Vandalizer itself — features, UI navigation, concepts. This is how the agent explains the product on demand, including "what makes this different from ChatGPT."

| Param | Type | Default | Notes |
|---|---|---|---|
| `topic` | `str` | required | Short phrase, e.g. "knowledge bases", "validation", "team folders" |

Topics are defined in `backend/app/services/help_content.py` and matched by token overlap. Bodies swap "Vandalizer" for the configured org name on white-labeled deployments. Not for questions about the user's own data — the search/list tools cover those.

---

## Web tools

Both are parallel-safe and compactable. Both require admin configuration or network egress; see the operator notes in [DEPLOY.md](../DEPLOY.md#agentic-chat-web-access).

### `fetch_url`

Fetches one public web page and returns its readable text. Auto-fires when the user's message contains an http(s) URL they clearly want read.

| Param | Type | Default | Notes |
|---|---|---|---|
| `url` | `str` | required | HTTP(S) |

Limits: 20s timeout, 2 MB raw HTML, ~25k characters of extracted text passed to the model. Does **not** work for pages behind login (SharePoint, Google Docs, Confluence) — those return login HTML, and the tool tells the user to upload an export or use M365 intake instead. Does not fetch arbitrary file types; PDFs and archives should be uploaded to Files so they get OCR'd.

### `web_search`

Searches the public web and returns ranked results (title, URL, snippet).

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | `str` | required | |
| `max_results` | `int` | `5` | |

Requires an admin-configured provider (`web_search_provider`, `web_search_endpoint`, `web_search_api_key` in System Config — serper, tavily, or brave). With no provider configured the tool reports that web search is unavailable rather than failing the turn.

The prompt orders these deliberately: workspace first (`search_documents`, `search_knowledge_base`), web only when the answer isn't in the user's own material or the question needs current external information. `web_search` discovers pages from a query; `fetch_url` reads one page you already have the link to.

---

## Reading and extraction tools

### `get_document_text`

Full text of one document. Parallel-safe, compactable.

| Param | Type | Default | Notes |
|---|---|---|---|
| `document_uuid` | `str` | required | |

### `analyze_documents`

Analyzes several documents **in parallel without loading their full text into the main conversation**, returning one concise digest per document. Each document is handed to its own read-only sub-analysis (`chat_subagents.py`) with the caller's instruction; only the digests come back. This is the context-preserving path for 3+ documents — summaries, comparisons, per-document prose extraction, folder screening. For 1–2 documents, `get_document_text` is used directly.

| Param | Type | Default | Notes |
|---|---|---|---|
| `instruction` | `str` | required | The sub-analysis sees ONLY one document and this instruction — no conversation history, no other documents. Must be self-contained |
| `document_uuids` | `list[str]` | required | Max 20 |

Parallel-safe, compactable.

### `run_extraction`

Runs an extraction template against documents and returns extracted entities with quality metadata.

| Param | Type | Default | Notes |
|---|---|---|---|
| `extraction_set_uuid` | `str` | required | |
| `document_uuids` | `list[str]` | required | Max 10 per call; results capped at 50 entities |

Carries a quality sidecar. The frontend renders an extraction table with CSV/TSV export.

### `check_compliance`

Runs an extraction set against documents, then evaluates the set's **cross-field rules** — sum checks, required-when conditions, date ordering, numeric ranges, cross-references — reporting each rule pass/fail with a plain-language reason.

| Param | Type | Default | Notes |
|---|---|---|---|
| `extraction_set_uuid` | `str` | required | |
| `document_uuids` | `list[str]` | required | Max 10 per call |

Read-only; nothing is saved. If the set has no rules defined, the tool says so — chat cannot author cross-field rules, so the user is pointed at the extraction's Cross-field Rules section.

---

## Knowledge-base write tools

All three are confirm-gated and registered sequential.

### `create_knowledge_base`

| Param | Type | Default | Notes |
|---|---|---|---|
| `title` | `str` | required | |
| `description` | `str` | `''` | |
| `confirmed` | `bool` | `False` | |

For an ongoing effort the user will feed documents into over time, the prompt steers toward `create_project` instead — a project carries an implicit KB, so project-wide chat works with no separate KB building.

### `add_documents_to_kb`

Chunks and indexes documents into ChromaDB.

| Param | Type | Default | Notes |
|---|---|---|---|
| `kb_uuid` | `str` | required | |
| `document_uuids` | `list[str]` | required | |
| `confirmed` | `bool` | `False` | |

### `add_url_to_kb`

| Param | Type | Default | Notes |
|---|---|---|---|
| `kb_uuid` | `str` | required | |
| `url` | `str` | required | |
| `crawl` | `bool` | `False` | Follow links on the page and index them too (max 5 pages) |
| `confirmed` | `bool` | `False` | |

---

## Workflow orchestration tools

### `run_workflow`

Starts a workflow execution and returns a session ID for polling. Confirm-gated. Runs asynchronously via Celery.

| Param | Type | Default | Notes |
|---|---|---|---|
| `workflow_id` | `str` | required | Must be invokable by the caller |
| `document_uuids` | `list[str] \| None` | `None` | |
| `text_input` | `str` | `''` | For text-input workflows |
| `confirmed` | `bool` | `False` | |

A workflow runs on documents, on typed text, or on nothing, depending on its input mode. Successful runs record `first_chat_workflow_at` / `chat_workflow_count` on the user and emit a tagged `ActivityEvent`, which is what the power-user milestone counts.

### `get_workflow_status`

| Param | Type | Default | Notes |
|---|---|---|---|
| `session_id` | `str` | required | Returned by `run_workflow` |

Returns current step, completion, any pending `approval_request_id`, and final output. Parallel-safe but deliberately **not** compactable — it anchors an in-flight process.

### `approve_workflow_step` / `reject_workflow_step`

Resume or fail a workflow paused at an approval gate. Both confirm-gated; both require the caller to be an assigned reviewer or workflow manager. Rejecting marks the run failed — it does not resume.

| Param | Type | Default | Notes |
|---|---|---|---|
| `approval_request_id` | `str` | required | From `get_workflow_status` |
| `comments` | `str` | `''` | Recorded with the decision |
| `confirmed` | `bool` | `False` | |

---

## Validation and guided verification tools

### `list_test_cases`

Existing ground truth for an extraction set, so the agent can suggest a test case with different characteristics rather than a near-duplicate. Parallel-safe, compactable.

| Param | Type | Default | Notes |
|---|---|---|---|
| `extraction_set_uuid` | `str` | required | |

### `propose_test_case`

Runs the extraction once and opens a **`VerificationSession`** — it does **not** persist a test case. The frontend opens the document in the viewer with each extracted value highlighted so the user approves or corrects each one in context. An `ExtractionTestCase` is created only when the user finalizes the session, with user-verified ground truth.

| Param | Type | Default | Notes |
|---|---|---|---|
| `extraction_set_uuid` | `str` | required | |
| `document_uuid` | `str` | required | |
| `label` | `str?` | `None` | |

### `run_validation`

Runs extraction N times per test case against user-verified expected values, returning a unified 0–100 score plus per-field accuracy and consistency. Persists a `ValidationRun` and updates the set's quality tier. Confirm-gated — it costs LLM calls and takes 30–90s.

| Param | Type | Default | Notes |
|---|---|---|---|
| `extraction_set_uuid` | `str` | required | |
| `num_runs` | `int` | `3` | |
| `test_case_uuids` | `list[str]?` | `None` | Defaults to all |
| `confirmed` | `bool` | `False` | |

### `create_extraction_from_document`

Reads sample documents and proposes field names worth extracting, creating a new `SearchSet`. Confirm-gated.

| Param | Type | Default | Notes |
|---|---|---|---|
| `document_uuids` | `list[str]` | required | |
| `title` | `str?` | `None` | |
| `domain` | `str?` | `None` | |
| `pin_to_active_project` | `bool` | `True` | Pins to the open project, if any |
| `confirmed` | `bool` | `False` | |

The natural follow-up is `propose_test_case` on the same document, seeding validation from day one.

---

## Autovalidate (optimizer) tools

Autovalidate sweeps candidate configurations against an item's test set and reports the best one. **Nothing changes until the user applies it.**

### `list_optimization_recommendations`

Pending recommendations across KBs, extraction sets, and workflows — completed shadow runs whose winning config beats the current one. No parameters. Parallel-safe, compactable.

### `get_optimization_run`

| Param | Type | Default | Notes |
|---|---|---|---|
| `item_kind` | `str` | required | `knowledge_base`, `search_set`, or `workflow` (aliases `kb` / `extraction` accepted) |
| `run_uuid` | `str` | required | |

Parallel-safe, not compactable.

### `start_optimization`

Confirm-gated. Costs real LLM tokens and takes 5–30 minutes.

| Param | Type | Default | Notes |
|---|---|---|---|
| `item_kind` | `str` | required | As above |
| `item_uuid` | `str` | required | |
| `token_budget` | `int` | `DEFAULT_OPTIMIZATION_TOKEN_BUDGET` (500,000) | |
| `confirmed` | `bool` | `False` | |

### `apply_optimization`

Applies a completed run's winning config. Confirm-gated; the preview shows scores and deltas. The previous config is snapshotted so the apply can be reverted from the UI.

| Param | Type | Default | Notes |
|---|---|---|---|
| `item_kind` | `str` | required | As above |
| `run_uuid` | `str` | required | |
| `confirmed` | `bool` | `False` | |

An honesty rule in the system prompt covers `tied_with_baseline`: the agent must say applying won't help rather than presenting a tie as a win.

### `regenerate_validation_plan`

For when `get_quality_info` reports `validation_plan_stale=true` — the saved checks no longer match the workflow definition, so grades are unreliable until regenerated. Confirm-gated.

| Param | Type | Default | Notes |
|---|---|---|---|
| `workflow_id` | `str` | required | |
| `confirmed` | `bool` | `False` | |

---

## Output artifact tools

### `save_to_folder`

Saves generated text as a real `SmartDocument` in the user's folder tree — how chat output becomes durable instead of living only in the transcript. The saved file appears in the Files tab, can be downloaded, and once indexing finishes is searchable in chat, addable to a KB, and usable as input to extractions and workflows. Confirm-gated.

| Param | Type | Default | Notes |
|---|---|---|---|
| `title` | `str` | required | |
| `content` | `str` | required | Max 1,000,000 chars |
| `folder_uuid` | `str?` | `None` | Resolve names via `list_folders` |
| `extension` | `str` | `'md'` | `md` or `txt` |
| `confirmed` | `bool` | `False` | |

---

## Project tools

A project is a goal-scoped workspace for one unit of work — a grant, a submission, an audit. Every file added is automatically indexed into the project's implicit knowledge base, so project-wide chat works with no separate KB building. Projects also carry a lifecycle status and pinned capabilities.

`create_project` works anytime; the rest require a project to be open.

### `create_project`

Confirm-gated. Recommended over `create_knowledge_base` whenever the user describes an ongoing effort they'll feed documents into over time — including the common ask, "let me drop files in as they arrive and chat across the whole set."

| Param | Type | Default | Notes |
|---|---|---|---|
| `title` | `str` | required | |
| `description` | `str?` | `None` | |
| `confirmed` | `bool` | `False` | |

### `list_project_documents`

Documents in the active project's folder subtree, up to 50. No parameters. Parallel-safe, compactable.

### `run_pin_on_project`

Runs a project-pinned workflow or extraction on **all** the project's documents, resolving the document set automatically. Confirm-gated.

| Param | Type | Default | Notes |
|---|---|---|---|
| `pin_type` | `str` | required | `workflow` or `extraction`. Automation pins cannot be run from chat |
| `target_id` | `str` | required | From the Active project section of the prompt |
| `confirmed` | `bool` | `False` | |

### `pin_to_project` / `unpin_from_project`

A pin is a reference for quick access — it never moves or copies the artifact, and unpinning leaves the artifact untouched. Both confirm-gated.

| Param | Type | Default | Notes |
|---|---|---|---|
| `pin_type` | `str` | required | `workflow`, `extraction`, `automation`, `knowledge_base` |
| `target_id` | `str` | required | |
| `confirmed` | `bool` | `False` | |

### `set_project_status`

Confirm-gated.

| Param | Type | Default | Notes |
|---|---|---|---|
| `state` | `str` | required | `draft`, `active`, `submitted`, `awarded`, `closeout`, `archived` |
| `confirmed` | `bool` | `False` | |

---

## Authoring tools

These are what make chat a building surface rather than only a driving surface.

### `create_workflow`

Builds a multi-step workflow from a plain-language description. Steps run in order; each step's output feeds the next. Confirm-gated.

| Param | Type | Default | Notes |
|---|---|---|---|
| `name` | `str` | required | |
| `steps` | `list[dict]` | required | Each entry: `name`, `type`, and type-specific config |
| `description` | `str` | `''` | |
| `input_mode` | `str` | `'documents'` | |
| `fixed_document_uuids` | `list[str] \| None` | `None` | |
| `confirmed` | `bool` | `False` | |

The workflow is created **unverified** and ready to run. The agent is instructed to tell the user they can fine-tune it in the visual workflow editor and validate it before relying on it.

### `create_automation`

Creates an automation that runs an existing workflow or extraction on a trigger. Confirm-gated.

| Param | Type | Default | Notes |
|---|---|---|---|
| `name` | `str` | required | |
| `action_type` | `str` | required | `workflow` or `extraction` |
| `action_id` | `str` | required | Must already exist — chat can't author the action inline |
| `trigger_type` | `str` | `'folder_watch'` | `folder_watch` or `schedule` |
| `folder_uuid` | `str` | `''` | Required for `folder_watch` |
| `cron_expression` | `str` | `''` | Required for `schedule`, e.g. `0 9 * * 1` |
| `description` | `str` | `''` | |
| `confirmed` | `bool` | `False` | |

The automation is created **disabled**; the agent tells the user to enable it. Only these two trigger types are reachable from chat — API and M365 intake triggers are configured in the Automations UI.

---

## Certification tools

The Vandal Workflow Architect program runs as a first-class chat experience sharing one progress store with the floating Certification panel — both call `certification_service`, so work done in chat counts in the panel and vice versa. **Grading stays in the deterministic validators; the model only narrates.**

### `get_certification_progress`

Overall XP, level, streak, per-module completion and stars, and the next incomplete module. No parameters. Parallel-safe, compactable.

### `get_certification_module`

One module's exercise: overview, chat-native instructions, criteria.

| Param | Type | Default | Notes |
|---|---|---|---|
| `module_id` | `str` | required | |

The agent is instructed to teach the module's lessons first, one at a time, before the challenge — and to offer to do the doable parts itself, since chat-driven work counts toward the same validators.

### `get_certification_lesson`

One lesson of a module — the same content the panel teaches. Renders as a card the user reads directly, so the agent frames rather than repeats it, and asks any `knowledge_check` question before moving on.

| Param | Type | Default | Notes |
|---|---|---|---|
| `module_id` | `str` | required | |
| `lesson_number` | `int` | required | |

### `provision_certification_lab`

Uploads a module's practice PDFs into a "Certification Lab" folder in the user's workspace, creating it if needed. Already-uploaded documents are reused, so calling again is safe. Reflective modules return an empty list.

| Param | Type | Default | Notes |
|---|---|---|---|
| `module_id` | `str` | required | |

### `check_certification_module`

Runs the module's deterministic validator over the user's **real workspace artifacts** and returns each check with pass/fail and detail. Read-only — it never marks the module complete.

| Param | Type | Default | Notes |
|---|---|---|---|
| `module_id` | `str` | required | |

Parallel-safe, compactable.

### `complete_certification_module`

Re-runs the validator first; if it doesn't pass, nothing is awarded and the failing checks are returned. On success returns XP earned, stars, new total and level, and whether the user just became fully certified. Completing an already-complete module is safe — it only awards bonus XP for star upgrades.

| Param | Type | Default | Notes |
|---|---|---|---|
| `module_id` | `str` | required | |

### `submit_certification_assessment`

Stores a reflective module's self-assessment answers. The agent asks the questions conversationally, one at a time, then submits answers keyed by the module's `assessment_keys`. Every key needs a non-empty answer **in the user's own words** — the prompt forbids inventing or padding answers the user didn't give.

| Param | Type | Default | Notes |
|---|---|---|---|
| `module_id` | `str` | required | One of `ai_literacy`, `process_mapping`, `workflow_design` |
| `answers` | `dict` | required | Keyed by the module's assessment keys |

---

## See also

- [AGENTIC_CHAT_USER_GUIDE.md](./AGENTIC_CHAT_USER_GUIDE.md) — end-user guide to what the chat can do
- [QUALITY_SIGNALS_EXPLAINED.md](./QUALITY_SIGNALS_EXPLAINED.md) — the trust layer in depth
- [DEPLOY.md](../DEPLOY.md#agentic-chat-web-access) — operator configuration for web search and URL fetching
- [AUTHORIZATION_MATRIX.md](../AUTHORIZATION_MATRIX.md) — platform-wide permission model
