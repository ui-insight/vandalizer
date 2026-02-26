# Vandalizer MCP Integration Plan

## Executive Summary

This document outlines the complete architectural plan for integrating the **Model Context Protocol (MCP)** into Vandalizer, transforming it into a tool-enabled, autonomous platform where:

- **MCP Client**: Embedded in the chat agent, enabling autonomous tool usage and multi-step orchestration
- **Internal MCP Server**: Provides standardized tool interface for the chat agent to access Vandalizer capabilities
- **Browser Automation as Tools**: The planned Chrome extension workflows become callable MCP tools
- **Semantic Intelligence**: Recommendations and activity history become context-aware resources
- **External MCP Servers**: Agent can connect to external services (GitHub, databases, calendars) via their MCP servers

This creates a **unified tool layer** where the Vandalizer chat agent can autonomously discover, plan, and execute complex document workflows, combining internal capabilities with external integrations.

---

## Table of Contents

1. [What is MCP and Why It Matters](#1-what-is-mcp-and-why-it-matters)
2. [Current Vandalizer Architecture](#2-current-vandalizer-architecture)
3. [MCP Integration Architecture](#3-mcp-integration-architecture)
4. [MCP Server Implementation](#4-mcp-server-implementation)
5. [MCP Client Integration](#5-mcp-client-integration)
6. [Browser Automation via MCP](#6-browser-automation-via-mcp)
7. [Security and Access Control](#7-security-and-access-control)
8. [Real-Time Streaming and Progress](#8-real-time-streaming-and-progress)
9. [Implementation Phases](#9-implementation-phases)
10. [Advanced Use Cases](#10-advanced-use-cases)
11. [Performance and Scalability](#11-performance-and-scalability)
12. [Future Enhancements](#12-future-enhancements)

---

## 1. What is MCP and Why It Matters

### 1.1 Model Context Protocol Overview

**MCP** is an open protocol created by Anthropic that standardizes how AI applications connect to data sources and tools. Think of it as **USB for AI** - a universal standard that enables:

- **Tool Discovery**: LLMs can query what capabilities are available
- **Resource Access**: Standardized way to fetch documents, data, and context
- **Prompt Templates**: Pre-configured workflows and prompts
- **Progress Streaming**: Real-time updates from long-running operations

### 1.2 Why MCP for Vandalizer

**Current State:**
- Rich document processing capabilities (OCR, extraction, validation)
- Complex workflow orchestration (multi-step document pipelines)
- Semantic recommendations (ChromaDB-powered matching)
- Limited tool usage (only one RAG retrieval tool exists)
- Manual workflow configuration via UI
- No programmatic access from external clients

**With MCP:**
- ✅ **Autonomous Agents**: Chat can discover and use all capabilities without hardcoding
- ✅ **Tool Composability**: Chain workflows, extractions, and browser automation in natural language
- ✅ **Intelligent Routing**: Agent picks the right workflow/extraction based on document semantics
- ✅ **Progress Transparency**: Real-time streaming of long Celery tasks
- ✅ **External Integration**: Connect to GitHub, databases, calendars via external MCP servers
- ✅ **Future-Proof**: New features (browser automation, external MCP servers) auto-discoverable

### 1.3 The Vision

```
User: "Extract all invoice totals from these PDFs and compare them to the amounts
       listed on the vendor's website."

Agent (with MCP):
1. [Discovers tools] run_extraction_set, browser_automation, compare_data
2. [Plans] Extract invoices → Navigate to vendor portal → Compare values
3. [Executes] Calls MCP tools autonomously
4. [Streams] Progress updates from each step
5. [Returns] "Found 3 discrepancies: Invoice #1234 shows $5,000 but website shows $4,850..."
```

**Without MCP:** User manually runs extraction → downloads CSV → opens browser →
manually compares → pastes results back into chat.

---

## 2. Current Vandalizer Architecture

### 2.1 System Components

**Backend (Flask + MongoDB + ChromaDB + Celery):**
```
┌─────────────────────────────────────────────────────────────────┐
│  Flask Application (app/)                                        │
│  ├── blueprints/                                                 │
│  │   ├── chat/          Chat interface, conversation management  │
│  │   ├── files/         Upload, processing, validation           │
│  │   ├── workflows/     Workflow CRUD, execution, downloads      │
│  │   ├── team/          Multi-tenant team management            │
│  │   └── ...                                                     │
│  ├── utilities/                                                  │
│  │   ├── chat_manager.py       ChatManager (streaming, RAG)     │
│  │   ├── agents.py              Pydantic-AI agents (chat, RAG)  │
│  │   ├── workflow.py            WorkflowEngine, Node classes    │
│  │   ├── document_manager.py   ChromaDB vector storage          │
│  │   ├── semantic_recommender.py  Workflow/extraction matching  │
│  │   ├── upload_manager.py     File processing pipelines        │
│  │   └── ...                                                     │
│  └── models.py                  MongoDB models (User, Team, etc)│
└─────────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
    ┌──────────┐        ┌──────────┐        ┌──────────┐
    │ MongoDB  │        │ ChromaDB │        │  Celery  │
    │ Metadata │        │ Vectors  │        │  Tasks   │
    └──────────┘        └──────────┘        └──────────┘
```

**Key Existing Capabilities:**

1. **Document Pipeline:**
   - Upload → OCR/conversion → Validation → Vector embedding
   - Supported: PDF, DOCX, XLSX with OCR fallback
   - Security: Magic number validation, compliance checking

2. **Chat System:**
   - ChatManager with streaming support
   - RAG agent with single `retrieve` tool
   - Conversation persistence (MongoDB)
   - Document/URL attachments

3. **Workflow Engine:**
   - Node-based execution (Document → Extraction → Prompt → Format)
   - Topological sort for dependencies
   - Celery async execution with progress tracking
   - Output chaining between steps

4. **Activity Tracking:**
   - ActivityEvent model (conversation, workflow_run, search_set_run)
   - Metrics: tokens, duration, documents touched
   - Flexible metadata storage (meta_summary dict)

5. **Semantic Recommender:**
   - ChromaDB-backed similarity search
   - Suggests workflows/extractions for documents
   - Popularity ranking (execution counts)

6. **Multi-Tenancy:**
   - Team/user/space hierarchy
   - Role-based access (owner, admin, member)
   - Verified library for approved workflows
   - Folder-based document organization

### 2.2 Current Tool Usage

**Existing Tools:**
- ✅ `retrieve` tool in RAG agent (document vector search)
- ❌ No extraction tools
- ❌ No workflow execution tools
- ❌ No file operation tools
- ❌ No browser automation tools
- ❌ No external MCP server connections

**Limitation:** Chat agent is conversational but not action-oriented.

---

## 3. MCP Integration Architecture

### 3.1 Internal MCP Architecture

Vandalizer implements MCP as an **internal tool layer** for the chat agent:

```
┌───────────────────────────────────────────────────────────────────┐
│                    FLASK APPLICATION                               │
│  (Existing routes, Celery tasks, ChatManager, WorkflowEngine)     │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │         INTERNAL MCP SERVER (Tool Registry)                  │ │
│  │  ┌────────────────────────────────────────────────────────┐  │ │
│  │  │ Tools:                                                  │  │ │
│  │  │  - search_documents, get_document_content              │  │ │
│  │  │  - run_workflow, get_workflow_status, list_workflows   │  │ │
│  │  │  - run_extraction, list_extraction_sets                │  │ │
│  │  │  - browser_navigate, browser_extract, browser_fill     │  │ │
│  │  │  - recommend_workflow, get_activity_history            │  │ │
│  │  ├────────────────────────────────────────────────────────┤  │ │
│  │  │ Resources:                                              │  │ │
│  │  │  - vandalizer://documents/{uuid}                       │  │ │
│  │  │  - vandalizer://conversations/{uuid}                   │  │ │
│  │  │  - vandalizer://workflows/{id}                         │  │ │
│  │  │  - vandalizer://activities/{id}                        │  │ │
│  │  ├────────────────────────────────────────────────────────┤  │ │
│  │  │ Prompts:                                                │  │ │
│  │  │  - extract_structured_data                             │  │ │
│  │  │  - summarize_documents                                 │  │ │
│  │  │  - compare_versions                                    │  │ │
│  │  └────────────────────────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────┬──────────────────────────────────────────┘
                         │ MCP Client
                         │ (embedded in agents)
┌────────────────────────▼──────────────────────────────────────────┐
│                    MCP CLIENT (Chat Agent)                         │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Pydantic-AI Agent with MCP tools:                           │  │
│  │  - All internal Vandalizer tools (auto-discovered)          │  │
│  │  - External MCP servers (GitHub, Snowflake, Calendar, etc.) │  │
│  │                                                              │  │
│  │ Agent autonomously:                                          │  │
│  │  1. Discovers available tools via MCP                       │  │
│  │  2. Plans multi-step workflows                              │  │
│  │  3. Calls tools with proper context                         │  │
│  │  4. Streams progress to user                                │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
                         │
┌────────────────────────▼──────────────────────────────────────────┐
│               EXTERNAL MCP SERVERS (Optional)                      │
│  - GitHub MCP (issue tracking, code search)                        │
│  - Snowflake MCP (data warehouse queries)                          │
│  - Calendar MCP (scheduling, availability)                         │
│  - Speech MCP (transcription, synthesis)                           │
└───────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow Examples

**Example 1: Vandalizer Chat Uses External MCP**
```
[User in Vandalizer Chat]
  → "Create a GitHub issue for the discrepancies we found"
  → Chat Agent (MCP Client): discovers GitHub MCP tools
  → Calls: github.create_issue(title="...", body="...")
  → GitHub MCP Server: creates issue
  → Agent: "Created issue #123 at https://github.com/..."
```

**Example 2: Autonomous Workflow Chaining**
```
[User] "Extract invoices and verify amounts on vendor site"

[Agent with MCP]:
1. tool_call: search_documents(query="invoices") → [doc1, doc2, doc3]
2. tool_call: run_extraction(docs=[doc1,doc2,doc3], fields=["invoice_number", "total"])
   → Streams progress: "Extracting from page 1/12..."
   → Returns: [{invoice: "1234", total: "$5,000"}, ...]
3. tool_call: browser_automation([
     {navigate: "vendor.com/invoices"},
     {ensure_login: "..."},
     {fill_form: {invoice_number: "1234"}},
     {extract: ["amount"]}
   ])
   → Streams: "Waiting for user login..."
   → Returns: {amount: "$4,850"}
4. tool_call: compare_data(extracted=[...], scraped=[...])
   → Returns: "Discrepancy found: $150 difference"
```

### 3.3 Why This Architecture Wins

**Benefits:**
- ✅ **Unified Tool Interface**: Standardized way for agent to access all Vandalizer capabilities
- ✅ **Composable**: Internal + external tools work seamlessly
- ✅ **Future-proof**: New MCP servers auto-integrate
- ✅ **No Custom Code**: Add new tools without modifying agent logic
- ✅ **Secure**: User context propagation + existing RBAC
- ✅ **Observable**: Activity tracking for all MCP operations

---

## 4. MCP Server Implementation

### 4.1 Server Architecture

**New Flask Blueprint:** `app/blueprints/mcp/`

**Structure:**
```
app/blueprints/mcp/
├── __init__.py
├── server.py              # Main MCP server implementation
├── tools/
│   ├── __init__.py
│   ├── document_tools.py  # upload, list, search, delete
│   ├── workflow_tools.py  # run, status, list
│   ├── extraction_tools.py # run extraction sets
│   ├── browser_tools.py   # browser automation wrappers
│   ├── chat_tools.py      # conversation management
│   └── context_tools.py   # team/space switching
├── resources/
│   ├── __init__.py
│   ├── document_resources.py
│   ├── conversation_resources.py
│   └── activity_resources.py
├── prompts/
│   ├── __init__.py
│   └── template_prompts.py
├── auth.py                # MCP authentication
└── streaming.py           # SSE/stdio streaming handlers
```

### 4.2 Tool Catalog

All tools follow the MCP tool schema:

```json
{
  "name": "tool_name",
  "description": "What this tool does",
  "inputSchema": {
    "type": "object",
    "properties": {
      "param1": {"type": "string", "description": "..."},
      "param2": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["param1"]
  }
}
```

#### 4.2.1 Document Tools

**list_documents**
- **Description**: List documents in current or specified context
- **Inputs**:
  - `folder_uuid` (string, optional): Filter by folder
  - `space_uuid` (string, optional): Filter by space
  - `team_uuid` (string, optional): Filter by team (if user has access)
  - `limit` (integer, optional): Max results (default 50)
  - `offset` (integer, optional): Pagination offset
- **Returns**: Array of document objects with metadata
- **Implementation**: Queries SmartDocument model with access control

**search_documents**
- **Description**: Semantic search across document content
- **Inputs**:
  - `query` (string, required): Search query
  - `document_uuids` (array, optional): Limit to specific documents
  - `folder_uuid` (string, optional): Limit to folder
  - `limit` (integer, optional): Max results
- **Returns**: Ranked document chunks with similarity scores
- **Implementation**: Uses DocumentManager.search_documents_for_user()

**get_document_content**
- **Description**: Retrieve full text content of a document
- **Inputs**:
  - `document_uuid` (string, required): Document to retrieve
- **Returns**:
  - `content`: Full extracted text
  - `metadata`: Title, upload date, format, validation status
- **Implementation**: Reads SmartDocument.text_content

**delete_document**
- **Description**: Delete a document and all associated data
- **Inputs**:
  - `document_uuid` (string, required): Document to delete
- **Returns**: `success: true/false`
- **Implementation**: Wraps `/files/delete_document`

**rename_document**
- **Description**: Update document title
- **Inputs**:
  - `document_uuid` (string, required)
  - `new_title` (string, required)
- **Returns**: Updated document object
- **Implementation**: SmartDocument.objects.get(uuid=...).update(title=...)

#### 4.2.2 Workflow Tools

**list_workflows**
- **Description**: List available workflows (personal, team, verified)
- **Inputs**:
  - `scope` (string, optional): "personal" | "team" | "verified" | "all"
  - `team_uuid` (string, optional): Filter by team
- **Returns**: Array of workflows with:
  - `id`, `name`, `description`, `num_executions`, `verified`
  - `steps`: Simplified step overview
- **Implementation**: Queries Workflow model with access checks

**get_workflow_details**
- **Description**: Get full workflow configuration
- **Inputs**:
  - `workflow_id` (string, required)
- **Returns**: Complete workflow structure including:
  - All steps with tasks
  - Extraction keys, prompts, formatters
  - Browser automation actions (if any)
- **Implementation**: Workflow.objects.get(id=...).to_json()

**run_workflow**
- **Description**: Execute a workflow on documents
- **Inputs**:
  - `workflow_id` (string, required)
  - `document_uuids` (array, required): Documents to process
  - `model` (string, optional): LLM model override
- **Returns**:
  - `workflow_result_id`: UUID for tracking execution
  - `status_url`: Polling URL
- **Implementation**: Wraps execute_workflow_task.delay() Celery task
- **Progress**: Streams via WorkflowResult updates

**get_workflow_status**
- **Description**: Poll workflow execution progress
- **Inputs**:
  - `workflow_result_id` (string, required)
- **Returns**:
  - `status`: "running" | "completed" | "failed"
  - `progress`: {current_step, num_steps_completed, num_steps_total}
  - `current_step_name`, `current_step_detail`, `current_step_preview`
  - `final_output` (if completed): Results from all steps
  - `steps_output`: Historical data from each step
- **Implementation**: Queries WorkflowResult model

**cancel_workflow**
- **Description**: Stop a running workflow
- **Inputs**:
  - `workflow_result_id` (string, required)
- **Returns**: `success: true/false`
- **Implementation**: Revokes Celery task

**download_workflow_result**
- **Description**: Get workflow output in specified format
- **Inputs**:
  - `workflow_result_id` (string, required)
  - `format` (string, required): "txt" | "csv" | "pdf"
- **Returns**: Base64-encoded file content or download URL
- **Implementation**: Wraps `/workflows/workflow_download`

#### 4.2.3 Extraction Tools

**list_extraction_sets**
- **Description**: List available extraction templates (SearchSets)
- **Inputs**:
  - `scope` (string, optional): "personal" | "team" | "verified"
- **Returns**: Array of SearchSet objects with keys/metadata
- **Implementation**: Queries SearchSet model

**run_extraction**
- **Description**: Extract structured data from documents
- **Inputs**:
  - `document_uuids` (array, required)
  - `search_set_uuid` (string, optional): Use predefined extraction
  - `fields` (array, optional): Custom field list (if not using search_set)
  - `context` (string, optional): Additional context for LLM
- **Returns**:
  - `extraction_id`: UUID for tracking
  - `status_url`: Polling URL
- **Implementation**: Wraps perform_extraction_task.delay()
- **Progress**: Streams extraction progress

**get_extraction_status**
- **Description**: Poll extraction progress
- **Inputs**:
  - `extraction_id` (string, required)
- **Returns**:
  - `status`: "running" | "completed" | "failed"
  - `progress`: Documents processed count
  - `results`: Extracted data (if completed)
- **Implementation**: Queries ActivityEvent or custom extraction tracking

#### 4.2.4 Browser Automation Tools

*These integrate with the Chrome Extension Workflow system from AGENTIAL_CHROME_EXTENSION_WORKFLOW.md*

**browser_start_session**
- **Description**: Initiate browser automation session
- **Inputs**:
  - `initial_url` (string, optional)
  - `allowed_domains` (array, optional): Domain whitelist
- **Returns**:
  - `session_id`: Browser session UUID
  - `status`: "connecting" | "ready"
- **Implementation**: Calls BrowserAutomationService.create_session()

**browser_navigate**
- **Description**: Navigate to a URL in controlled browser
- **Inputs**:
  - `session_id` (string, required)
  - `url` (string, required)
  - `wait_for` (object, optional): Wait conditions
- **Returns**: Navigation success/failure
- **Implementation**: BrowserAutomationService.execute_action(type="navigate")

**browser_ensure_login**
- **Description**: Pause workflow and wait for user login
- **Inputs**:
  - `session_id` (string, required)
  - `detection_rules` (object, required): URL pattern or element selector
  - `instruction` (string, required): Message to user
- **Returns**: Login confirmation status
- **Implementation**: Sets session to WAITING_FOR_LOGIN state
- **Progress**: Streams "waiting for user..." messages

**browser_fill_form**
- **Description**: Fill form fields in the browser
- **Inputs**:
  - `session_id` (string, required)
  - `fields` (array, required): [{locator, value}, ...]
  - `typing_delay_ms` (integer, optional): Human-like typing speed
- **Returns**: Per-field success/failure
- **Implementation**: Sends fill_form command to extension

**browser_click**
- **Description**: Click an element
- **Inputs**:
  - `session_id` (string, required)
  - `locator` (object, required): {strategy, value}
  - `wait_after` (object, optional): Post-click wait condition
- **Returns**: Click success
- **Implementation**: Sends click command

**browser_extract_data**
- **Description**: Extract structured data from current page
- **Inputs**:
  - `session_id` (string, required)
  - `extraction_spec` (object, required): Fields or table spec
- **Returns**: Extracted structured data
- **Implementation**: Sends extract command to extension

**browser_end_session**
- **Description**: Clean up browser session
- **Inputs**:
  - `session_id` (string, required)
  - `close_tab` (boolean, optional): Whether to close the tab
- **Returns**: Cleanup success
- **Implementation**: BrowserAutomationService.end_session()

**browser_automation_workflow**
- **Description**: Run a complete browser automation workflow (composite tool)
- **Inputs**:
  - `actions` (array, required): Full action sequence
  - `summarization` (object, optional): LLM summary config
  - `allowed_domains` (array, optional)
- **Returns**:
  - `workflow_result_id`: Tracking UUID
  - `status_url`: Polling URL
- **Implementation**: Creates BrowserAutomationNode and executes
- **Progress**: Streams action-by-action progress

#### 4.2.5 Chat Tools

**start_conversation**
- **Description**: Create a new conversation
- **Inputs**:
  - `title` (string, optional): Conversation title
  - `initial_message` (string, optional): First message
- **Returns**:
  - `conversation_uuid`: UUID for tracking
  - `activity_id`: ActivityEvent ID
- **Implementation**: Creates Conversation + ActivityEvent

**send_message**
- **Description**: Send a message in a conversation
- **Inputs**:
  - `conversation_uuid` (string, required)
  - `message` (string, required)
  - `document_uuids` (array, optional): Attach documents
  - `stream` (boolean, optional): Enable streaming response
- **Returns**:
  - `response`: Agent response (or SSE stream)
  - `message_id`: UUID of the message
- **Implementation**: Wraps ChatManager.send_message()
- **Progress**: Streams token-by-token if enabled

**get_conversation_history**
- **Description**: Retrieve conversation messages
- **Inputs**:
  - `conversation_uuid` (string, required)
  - `limit` (integer, optional): Max messages
- **Returns**: Array of messages with attachments
- **Implementation**: Queries Conversation.messages

**attach_url_to_conversation**
- **Description**: Fetch and attach web content
- **Inputs**:
  - `conversation_uuid` (string, required)
  - `url` (string, required)
- **Returns**: Attachment metadata
- **Implementation**: Wraps `/chat/add_link`

**attach_document_to_conversation**
- **Description**: Link existing document to conversation
- **Inputs**:
  - `conversation_uuid` (string, required)
  - `document_uuid` (string, required)
- **Returns**: Attachment confirmation
- **Implementation**: Adds to Conversation.document_attachments

#### 4.2.6 Context Tools

**get_current_context**
- **Description**: Get current user/team/space context
- **Inputs**: None (uses authenticated user)
- **Returns**:
  - `user_id`, `username`
  - `current_team`: {uuid, name, role}
  - `current_space`: {uuid, name}
  - `current_folder`: {uuid, name}
- **Implementation**: Queries User.current_team, session[space_uuid]

**switch_team**
- **Description**: Change active team context
- **Inputs**:
  - `team_uuid` (string, required)
- **Returns**: New context object
- **Implementation**: Wraps `/team/switch/<team_uuid>`

**list_teams**
- **Description**: List user's team memberships
- **Inputs**: None
- **Returns**: Array of teams with roles
- **Implementation**: Queries TeamMembership

**create_folder**
- **Description**: Create a document folder
- **Inputs**:
  - `name` (string, required)
  - `parent_uuid` (string, optional): Parent folder
  - `is_team_folder` (boolean, optional): Create as team folder
- **Returns**: New folder object
- **Implementation**: Wraps `/files/create_folder`

#### 4.2.7 Recommendation Tools

**recommend_workflows**
- **Description**: Get workflow recommendations for documents
- **Inputs**:
  - `document_uuids` (array, required): Documents to analyze
  - `limit` (integer, optional): Max recommendations
- **Returns**: Ranked workflow recommendations with similarity scores
- **Implementation**: Uses SemanticRecommender.search_recommendations()

**recommend_extractions**
- **Description**: Get extraction set recommendations
- **Inputs**:
  - `document_uuids` (array, required)
  - `limit` (integer, optional)
- **Returns**: Ranked SearchSet recommendations
- **Implementation**: SemanticRecommender for extraction sets

**get_activity_history**
- **Description**: Retrieve user's recent activities
- **Inputs**:
  - `type` (string, optional): Filter by activity type
  - `status` (string, optional): Filter by status
  - `limit` (integer, optional): Max results
  - `offset` (integer, optional): Pagination
- **Returns**: Array of ActivityEvent objects with metrics
- **Implementation**: Queries ActivityEvent.objects(user_id=...)

**get_popular_workflows**
- **Description**: Get most-used workflows (team or global)
- **Inputs**:
  - `scope` (string, optional): "team" | "verified" | "all"
  - `limit` (integer, optional)
- **Returns**: Workflows sorted by num_executions
- **Implementation**: Queries Workflow.objects.order_by('-num_executions')

### 4.3 Resource Catalog

MCP resources provide read access to Vandalizer data via URIs.

**Resource URI Format:** `vandalizer://{resource_type}/{identifier}[?params]`

#### Resource Types

**Documents:**
```
URI: vandalizer://documents/{document_uuid}
Content-Type: text/plain or application/json
Returns: Full document text content + metadata

URI: vandalizer://documents/{document_uuid}/chunks
Content-Type: application/json
Returns: Array of vector chunks with embeddings

URI: vandalizer://documents/{document_uuid}/metadata
Content-Type: application/json
Returns: Document metadata (title, upload_date, validation_status, etc.)
```

**Conversations:**
```
URI: vandalizer://conversations/{conversation_uuid}
Content-Type: application/json
Returns: Full conversation history with messages and attachments

URI: vandalizer://conversations/{conversation_uuid}/summary
Content-Type: text/plain
Returns: LLM-generated conversation summary
```

**Workflows:**
```
URI: vandalizer://workflows/{workflow_id}
Content-Type: application/json
Returns: Complete workflow configuration (steps, tasks, parameters)

URI: vandalizer://workflows/{workflow_id}/executions
Content-Type: application/json
Returns: Recent execution history for this workflow
```

**Workflow Results:**
```
URI: vandalizer://workflow-results/{result_id}
Content-Type: application/json
Returns: Execution details, outputs, timing

URI: vandalizer://workflow-results/{result_id}/output
Content-Type: text/plain or application/json
Returns: Final output in requested format
```

**Activities:**
```
URI: vandalizer://activities/{activity_id}
Content-Type: application/json
Returns: ActivityEvent details with full metrics and metadata

URI: vandalizer://activities/recent?type={type}&limit={n}
Content-Type: application/json
Returns: Recent activities filtered by type
```

**Folders:**
```
URI: vandalizer://folders/{folder_uuid}
Content-Type: application/json
Returns: Folder contents (documents, subfolders)
```

**Libraries:**
```
URI: vandalizer://libraries/personal
Content-Type: application/json
Returns: User's personal library (prompts, workflows, extractions)

URI: vandalizer://libraries/team/{team_uuid}
Content-Type: application/json
Returns: Team library contents

URI: vandalizer://libraries/verified
Content-Type: application/json
Returns: Verified/approved library items
```

### 4.4 Prompt Templates

MCP prompts are pre-configured workflows that clients can invoke with parameters.

**Template Structure:**
```json
{
  "name": "prompt_name",
  "description": "What this prompt does",
  "arguments": [
    {
      "name": "arg1",
      "description": "Argument description",
      "required": true
    }
  ]
}
```

#### Prompt Catalog

**extract_structured_data**
```json
{
  "name": "extract_structured_data",
  "description": "Extract specific fields from documents using LLM",
  "arguments": [
    {"name": "document_uuids", "description": "Documents to process", "required": true},
    {"name": "fields", "description": "Comma-separated field names", "required": true},
    {"name": "context", "description": "Additional extraction context", "required": false}
  ]
}
```
**Implementation**: Generates messages that call `run_extraction` tool

**summarize_documents**
```json
{
  "name": "summarize_documents",
  "description": "Generate comprehensive summary of documents",
  "arguments": [
    {"name": "document_uuids", "description": "Documents to summarize", "required": true},
    {"name": "focus", "description": "What to focus on (optional)", "required": false},
    {"name": "max_length", "description": "Max summary length in words", "required": false}
  ]
}
```
**Implementation**: Creates workflow with Prompt node configured for summarization

**compare_document_versions**
```json
{
  "name": "compare_document_versions",
  "description": "Identify differences between document versions",
  "arguments": [
    {"name": "document_uuid_old", "description": "Original document", "required": true},
    {"name": "document_uuid_new", "description": "Updated document", "required": true}
  ]
}
```
**Implementation**: Multi-step workflow: extract both → compare with LLM prompt

**auto_classify_documents**
```json
{
  "name": "auto_classify_documents",
  "description": "Automatically categorize documents by type/topic",
  "arguments": [
    {"name": "document_uuids", "description": "Documents to classify", "required": true},
    {"name": "categories", "description": "Comma-separated category options", "required": false}
  ]
}
```
**Implementation**: Prompt node with classification instructions

**verify_compliance**
```json
{
  "name": "verify_compliance",
  "description": "Check documents against compliance rules",
  "arguments": [
    {"name": "document_uuids", "description": "Documents to check", "required": true},
    {"name": "rules", "description": "Compliance rules to verify", "required": true}
  ]
}
```
**Implementation**: Uses existing validation pipeline with custom rules

**web_to_document_extraction**
```json
{
  "name": "web_to_document_extraction",
  "description": "Scrape web data and compare to document data",
  "arguments": [
    {"name": "document_uuids", "description": "Reference documents", "required": true},
    {"name": "url", "description": "Website to scrape", "required": true},
    {"name": "comparison_fields", "description": "Fields to compare", "required": true}
  ]
}
```
**Implementation**: Chains browser_automation → extraction → comparison

---

## 5. MCP Client Integration

### 5.1 Embedding MCP Client in Chat Agent

**Current State:**
```python
# app/utilities/agents.py
@rag_agent.tool
def retrieve(context: RunContext[RagDeps], question: str, docs_ids: Optional[list[str]] = None):
    """Single hardcoded tool"""
```

**With MCP Client:**
```python
# app/utilities/agents.py (enhanced)
from mcp_client import MCPClient

# Initialize MCP client with internal server
mcp_client = MCPClient(
    servers={
        "vandalizer": {"type": "internal"},  # Connect to own MCP server
        "github": {"command": "mcp-server-github"},  # External servers
        "snowflake": {"command": "mcp-server-snowflake"}
    }
)

def create_chat_agent_with_mcp(agent_model, system_prompt=None, user_context=None):
    """
    Creates Pydantic-AI agent with dynamically discovered MCP tools
    """

    # Discover all available tools from all MCP servers
    available_tools = mcp_client.list_tools(user_context=user_context)

    # Convert MCP tools to Pydantic-AI tool format
    pydantic_tools = []
    for tool in available_tools:
        pydantic_tools.append(
            create_pydantic_tool_from_mcp(tool, mcp_client, user_context)
        )

    # Create agent with all discovered tools
    agent = Agent(
        model=get_agent_model(agent_model),
        system_prompt=system_prompt,
        tools=pydantic_tools  # Auto-discovered, not hardcoded
    )

    return agent


def create_pydantic_tool_from_mcp(mcp_tool, client, user_context):
    """
    Wraps an MCP tool as a Pydantic-AI tool
    """

    async def tool_function(context: RunContext, **kwargs):
        # Call MCP tool with user context for auth/scoping
        result = await client.call_tool(
            tool_name=mcp_tool["name"],
            arguments=kwargs,
            user_context=user_context
        )

        # Track activity
        create_activity_event(
            type="mcp_tool_call",
            user_id=user_context["user_id"],
            meta_summary={
                "tool": mcp_tool["name"],
                "arguments": kwargs,
                "result_preview": str(result)[:200]
            }
        )

        return result

    # Set function metadata for LLM discovery
    tool_function.__name__ = mcp_tool["name"]
    tool_function.__doc__ = mcp_tool["description"]

    return tool_function
```

### 5.2 Agent Behavior with MCP Tools

**Discovery Phase:**
```
User starts chat → Agent initialization
  → MCP client connects to servers (Vandalizer + external)
  → Lists all available tools (~30+ tools)
  → Agent receives tool catalog in system prompt
```

**Execution Phase:**
```
User: "Extract invoice totals from my recent uploads and verify on vendor site"

Agent reasoning:
1. [Analyzes request] Need to: find documents → extract data → verify via web
2. [Checks available tools]
   - list_documents ✓
   - run_extraction ✓
   - browser_automation_workflow ✓
3. [Plans execution]
   - Step 1: list_documents(limit=10, folder=recent)
   - Step 2: run_extraction(document_uuids=[...], fields=["invoice_number", "total"])
   - Step 3: browser_automation_workflow(actions=[...])
4. [Executes tools sequentially]
5. [Streams progress] "Found 5 documents... Extracting data... Navigating to vendor.com..."
6. [Returns result] "Found 3 discrepancies: ..."
```

**Multi-Server Orchestration:**
```
User: "Create a GitHub issue for the compliance failures we found yesterday"

Agent:
1. tool_call: get_activity_history(type="workflow_run", limit=10)
   → Finds workflow_result_id from yesterday
2. tool_call: get_workflow_status(workflow_result_id="...")
   → Retrieves compliance failure details
3. tool_call: github.create_issue(
     title="Compliance Failures - [Date]",
     body="Found X failures: [details from workflow]",
     labels=["compliance", "urgent"]
   )
   → External MCP server creates issue
4. Returns: "Created issue #456 at https://github.com/..."
```

### 5.3 Streaming Progress from MCP Tools

**Challenge:** Long-running Celery tasks (workflows, extractions) need real-time updates.

**Solution:** MCP supports progress notifications via the notification system.

**Implementation:**

```python
# In MCP tool wrapper
async def run_workflow_tool(workflow_id, document_uuids):
    # Start Celery task
    task = execute_workflow_task.delay(workflow_id, document_uuids, user_id)
    workflow_result_id = task.id

    # Stream progress updates
    while True:
        # Poll WorkflowResult
        result = WorkflowResult.objects.get(id=workflow_result_id)

        # Send MCP progress notification
        await mcp_client.send_notification(
            method="notifications/progress",
            params={
                "progressToken": workflow_result_id,
                "progress": result.num_steps_completed,
                "total": result.num_steps_total,
                "message": f"{result.current_step_name}: {result.current_step_detail}"
            }
        )

        if result.status in ["completed", "failed"]:
            break

        await asyncio.sleep(2)  # Poll every 2 seconds

    # Return final result
    return {
        "status": result.status,
        "output": result.final_output,
        "steps_output": result.steps_output
    }
```

**User Experience:**
```
User: "Run the invoice extraction workflow on these 50 documents"

Chat response (streaming):
[Agent] I'll run the invoice extraction workflow on your 50 documents.

[Progress] Starting workflow...
[Progress] Step 1/4: Document ingestion - Processing document 1/50...
[Progress] Step 1/4: Document ingestion - Processing document 25/50...
[Progress] Step 1/4: Document ingestion - Complete
[Progress] Step 2/4: Invoice extraction - Extracting from page 1/120...
[Progress] Step 2/4: Invoice extraction - Extracting from page 60/120...
[Progress] Step 2/4: Invoice extraction - Complete
[Progress] Step 3/4: Prompt summarization - Generating summary...
[Progress] Step 3/4: Prompt summarization - Complete
[Progress] Step 4/4: Format output - Formatting as CSV...
[Progress] Step 4/4: Format output - Complete

[Agent] Workflow completed! Extracted 143 invoices totaling $1,245,890.
Download CSV: [link]
```

### 5.4 Context Propagation

**Problem:** MCP is stateless, but Vandalizer has user/team/space context.

**Solution:** Pass context in every MCP call via user_context parameter.

**Context Object:**
```json
{
  "user_id": "user123",
  "team_id": "team456",
  "team_role": "admin",
  "space_uuid": "space789",
  "folder_uuid": "folder012",
  "session_id": "session345"
}
```

**Implementation:**

```python
# When initializing MCP client in chat
user_context = {
    "user_id": current_user.id,
    "team_id": current_user.current_team.uuid if current_user.current_team else None,
    "team_role": get_user_team_role(current_user),
    "space_uuid": session.get("space_uuid"),
    "folder_uuid": session.get("folder_uuid")
}

# Agent uses this context for all tool calls
agent = create_chat_agent_with_mcp(
    model="claude-sonnet-4-5",
    user_context=user_context
)

# MCP server validates context and applies access control
@mcp_tool("list_documents")
def list_documents_tool(user_context, folder_uuid=None, **kwargs):
    # Validate user has access
    user = User.objects.get(id=user_context["user_id"])

    # Apply team/space filtering
    query = SmartDocument.objects(user_id=user.id)

    if folder_uuid:
        folder = Folder.objects.get(uuid=folder_uuid)
        # Check access to folder
        if folder.team_id and folder.team_id != user_context["team_id"]:
            raise PermissionError("Cannot access folder from different team")
        query = query.filter(folder=folder)

    return query.to_json()
```

---

## 6. Browser Automation via MCP

### 6.1 Integration with Chrome Extension Plan

The browser automation system from `AGENTIAL_CHROME_EXTENSION_WORKFLOW.md` becomes accessible via MCP tools, enabling:

- **Direct tool calls**: Chat agent can call individual browser actions
- **Workflow composition**: Chain browser automation with document processing
- **Agent autonomy**: Agent can trigger browser automation based on user requests
- **Progress streaming**: Real-time updates during multi-step browser workflows

### 6.2 Browser Automation Tool Mapping

**From AGENTIAL_CHROME_EXTENSION_WORKFLOW.md → MCP Tools:**

| Chrome Extension Action | MCP Tool | Description |
|------------------------|----------|-------------|
| `start_session` | `browser_start_session` | Initialize browser session |
| `navigate` | `browser_navigate` | Navigate to URL |
| `ensure_login` | `browser_ensure_login` | Pause for user login |
| `fill_form` | `browser_fill_form` | Fill form fields |
| `click` | `browser_click` | Click elements |
| `wait_for` | `browser_wait_for` | Wait for conditions |
| `extract` | `browser_extract_data` | Extract page data |
| `end_session` | `browser_end_session` | Cleanup session |
| BrowserAutomationNode | `browser_automation_workflow` | Complete workflow |

### 6.3 Composite Workflows

**Example: Document-to-Web Verification**

User request: "Compare the invoice totals in these PDFs to what's shown on the vendor portal"

**Agent execution plan (using MCP tools):**

```python
# Step 1: Extract data from documents
extraction_result = await mcp_call_tool(
    "run_extraction",
    document_uuids=["doc1", "doc2", "doc3"],
    fields=["invoice_number", "total", "date"]
)
# Returns: [
#   {invoice: "INV-001", total: "$5,000", date: "2024-01-15"},
#   {invoice: "INV-002", total: "$3,200", date: "2024-01-16"},
#   ...
# ]

# Step 2: Start browser automation workflow
browser_result = await mcp_call_tool(
    "browser_automation_workflow",
    actions=[
        {
            "type": "navigate",
            "url": "https://vendor.example.com/invoices"
        },
        {
            "type": "ensure_login",
            "detection_rules": {"url_pattern": "^https://vendor\\.example\\.com/dashboard"},
            "instruction_to_user": "Please log into the vendor portal with your credentials"
        },
        {
            "type": "fill_form",
            "fields": [
                {
                    "locator": {"strategy": "css", "value": "input[name='invoice_number']"},
                    "value": extraction_result[0]["invoice"]
                }
            ]
        },
        {
            "type": "click",
            "locator": {"strategy": "css", "value": "button[type='submit']"}
        },
        {
            "type": "wait_for",
            "condition_type": "element_present",
            "condition_value": ".invoice-details"
        },
        {
            "type": "extract",
            "extraction_spec": {
                "mode": "simple",
                "fields": [
                    {
                        "name": "web_total",
                        "locator": {"strategy": "css", "value": ".invoice-amount"},
                        "attribute": "innerText"
                    }
                ]
            }
        }
    ],
    summarization={
        "enabled": False  # We'll do comparison ourselves
    }
)

# Step 3: Compare results
comparison = compare_data(
    document_data=extraction_result,
    web_data=browser_result["raw_data"]
)

# Step 4: Return formatted results
return f"""
Verification complete:

Document: Invoice INV-001 = $5,000
Website: Invoice INV-001 = $4,850
Status: ❌ DISCREPANCY ($150 difference)

Document: Invoice INV-002 = $3,200
Website: Invoice INV-002 = $3,200
Status: ✓ MATCH

Recommendation: Please investigate Invoice INV-001 for the $150 discrepancy.
"""
```

**MCP Value:** The agent autonomously orchestrates document extraction → browser automation → comparison without the user writing any code or manually navigating between systems.

### 6.4 User Login Flow in MCP Context

**Challenge:** Browser automation requires user login, which is asynchronous.

**Solution:** MCP progress notifications + user confirmation.

**Flow:**

```
1. Agent calls browser_ensure_login tool
   → MCP server sets session state to WAITING_FOR_LOGIN
   → Sends progress notification: "Waiting for user to log in..."

2. MCP server updates chat UI
   → Shows alert: "Please log into vendor.example.com in your browser"
   → Displays "I'm logged in" button

3. User logs into browser, clicks button
   → Frontend calls /browser_automation/session/{id}/confirm_login
   → MCP server transitions session to ACTIVE
   → Sends progress notification: "Login confirmed, continuing..."

4. Agent receives login confirmation
   → Continues with next browser automation actions
```

**User Experience:**
```
[Agent] I'll verify the invoice amounts on the vendor portal.

[Progress] Connecting to browser extension...
[Progress] Navigating to https://vendor.example.com/invoices

⚠️ ACTION REQUIRED
Please log into the vendor portal in your browser, then click "I'm logged in" below.

[Button: I'm logged in]

[User clicks button]

[Progress] Login confirmed, searching for invoice INV-001...
[Progress] Extracting invoice data...
[Progress] Complete! Found invoice amount: $4,850

[Agent] Verification complete. Found discrepancy: ...
```

---

## 7. Security and Access Control

### 7.1 Authentication and User Context

**Approach:** Since MCP is used internally by the chat agent, authentication uses the existing Flask session.

**User Context Propagation:**

```python
# When creating chat agent, extract user context from Flask session
def create_chat_agent_with_mcp(agent_model, system_prompt=None):
    """
    Creates Pydantic-AI agent with MCP tools and user context
    """
    # Extract user context from current Flask session
    user_context = {
        "user_id": current_user.id,
        "team_id": current_user.current_team.uuid if current_user.current_team else None,
        "team_role": get_user_team_role(current_user),
        "space_uuid": session.get("space_uuid"),
        "folder_uuid": session.get("folder_uuid"),
        "session_id": session.sid
    }

    # Initialize MCP client with user context
    mcp_client = MCPClient(
        servers=get_mcp_servers(),
        user_context=user_context
    )

    # Discover and register tools
    available_tools = mcp_client.list_tools()
    pydantic_tools = [create_pydantic_tool_from_mcp(tool, mcp_client, user_context)
                      for tool in available_tools]

    # Create agent
    agent = Agent(
        model=get_agent_model(agent_model),
        system_prompt=system_prompt,
        tools=pydantic_tools
    )

    return agent
```

**Benefits:**
- No additional authentication mechanism needed
- User context automatically tied to Flask session
- Existing RBAC and team permissions apply
- Tools execute with same permissions as logged-in user

### 7.2 Resource Access Control

**Resource URI Authorization:**

```python
@mcp_resource("vandalizer://documents/{document_uuid}")
def get_document_resource(user_context, document_uuid):
    """
    Retrieve document content with access control
    """
    # Verify user has access to document
    user = User.objects.get(id=user_context["user_id"])
    document = SmartDocument.objects.get(uuid=document_uuid)

    # Access rules:
    # 1. Personal documents: user must be owner
    if document.user_id != user.id:
        # 2. Team documents: user must be team member
        if not document.team_id or document.team_id != user_context.get("team_id"):
            raise PermissionError("Access denied to this document")

        # 3. Check team membership
        membership = TeamMembership.objects.get(
            team__uuid=document.team_id,
            user_id=user.id
        )
        if not membership:
            raise PermissionError("Not a member of document's team")

    # Return document content
    return {
        "uri": f"vandalizer://documents/{document_uuid}",
        "mimeType": "text/plain",
        "text": document.text_content,
        "metadata": {
            "title": document.title,
            "upload_date": document.upload_date,
            "validation_status": document.validation_status
        }
    }
```

### 7.3 Audit Logging

**Every MCP operation creates an ActivityEvent:**

```python
def log_mcp_activity(user_context, tool_name, arguments, result, duration_ms):
    """
    Create audit log for MCP tool call
    """
    activity = ActivityEvent(
        type="mcp_tool_call",
        status="completed",
        user_id=user_context["user_id"],
        team_id=user_context.get("team_id"),

        message_count=1,  # One tool call

        meta_summary={
            "tool": tool_name,
            "arguments": sanitize_arguments(arguments),  # Remove sensitive data
            "result_preview": str(result)[:500],
            "duration_ms": duration_ms,
            "session_id": user_context.get("session_id")
        }
    )
    activity.save()
```

**Audit Dashboard:**

Admins can view:
- All MCP tool calls by team members
- Most-used tools
- Failed permission checks
- Tool execution duration and performance metrics

---

## 8. Real-Time Streaming and Progress

### 8.1 MCP Progress Notifications

**MCP Spec:** Servers can send `notifications/progress` to update clients on long-running operations.

**Implementation:**

```python
class MCPProgressStreamer:
    """
    Streams progress updates from Celery tasks to MCP clients
    """

    def __init__(self, mcp_session):
        self.mcp_session = mcp_session

    async def stream_workflow_progress(self, workflow_result_id):
        """
        Poll WorkflowResult and stream updates to MCP client
        """
        progress_token = workflow_result_id

        while True:
            result = WorkflowResult.objects.get(id=workflow_result_id)

            # Send progress notification
            await self.mcp_session.send_notification(
                method="notifications/progress",
                params={
                    "progressToken": progress_token,
                    "progress": result.num_steps_completed,
                    "total": result.num_steps_total,
                    "message": self._format_progress_message(result)
                }
            )

            # Check if complete
            if result.status in ["completed", "failed", "canceled"]:
                break

            await asyncio.sleep(2)

    def _format_progress_message(self, result):
        """
        Generate human-readable progress message
        """
        step = result.current_step_name
        detail = result.current_step_detail
        preview = result.current_step_preview

        msg = f"Step {result.num_steps_completed + 1}/{result.num_steps_total}: {step}"

        if detail:
            msg += f" - {detail}"

        if preview:
            msg += f"\n{preview[:200]}"

        return msg
```

### 8.2 Streaming Chat Responses

**Challenge:** Chat responses stream token-by-token, but MCP tool results are discrete.

**Solution:** Use MCP's SSE transport for streaming, or buffer and return complete response.

**Option A: Buffered Response (Simple)**
```python
@mcp_tool("send_message")
async def send_message_tool(conversation_uuid, message, document_uuids=None):
    """
    Send message and return complete response
    """
    response_tokens = []

    # Call ChatManager with callback
    def token_callback(token):
        response_tokens.append(token)

    chat_manager = ChatManager(model="claude-sonnet-4-5")
    chat_manager.send_message(
        message=message,
        conversation_uuid=conversation_uuid,
        document_uuids=document_uuids,
        stream=True,
        callback=token_callback
    )

    # Return complete response
    return {
        "response": "".join(response_tokens),
        "conversation_uuid": conversation_uuid
    }
```

**Option B: Progressive Streaming (Advanced)**
```python
@mcp_tool("send_message_streaming")
async def send_message_streaming_tool(conversation_uuid, message, document_uuids=None):
    """
    Send message with progressive updates via notifications
    """
    progress_token = f"chat_{conversation_uuid}_{uuid.uuid4()}"
    response_buffer = []

    def token_callback(token):
        response_buffer.append(token)

        # Send progress notification every 10 tokens
        if len(response_buffer) % 10 == 0:
            asyncio.create_task(
                mcp_session.send_notification(
                    method="notifications/progress",
                    params={
                        "progressToken": progress_token,
                        "message": "".join(response_buffer)
                    }
                )
            )

    # Call ChatManager
    chat_manager = ChatManager(model="claude-sonnet-4-5")
    final_response = chat_manager.send_message(
        message=message,
        conversation_uuid=conversation_uuid,
        document_uuids=document_uuids,
        stream=True,
        callback=token_callback
    )

    return {
        "response": final_response,
        "conversation_uuid": conversation_uuid,
        "progress_token": progress_token
    }
```

### 8.3 WebSocket for Browser Automation Progress

**Browser automation already uses WebSocket** (from AGENTIAL_CHROME_EXTENSION_WORKFLOW.md).

**Integration:** MCP server subscribes to browser automation WebSocket events and forwards as MCP progress notifications.

```python
@mcp_tool("browser_automation_workflow")
async def browser_automation_workflow_tool(actions, summarization=None, allowed_domains=None):
    """
    Run browser workflow with real-time progress streaming
    """
    # Start browser automation
    service = BrowserAutomationService.get_instance()
    session = service.create_session(
        user_id=user_context["user_id"],
        workflow_result_id=None,
        allowed_domains=allowed_domains
    )

    progress_token = session.session_id

    # Subscribe to browser automation events
    async def on_browser_event(event_type, event_data):
        # Forward as MCP progress notification
        await mcp_session.send_notification(
            method="notifications/progress",
            params={
                "progressToken": progress_token,
                "message": format_browser_event(event_type, event_data)
            }
        )

    service.subscribe_to_events(session.session_id, on_browser_event)

    # Execute actions
    for i, action in enumerate(actions):
        await mcp_session.send_notification(
            method="notifications/progress",
            params={
                "progressToken": progress_token,
                "progress": i,
                "total": len(actions),
                "message": f"Executing: {action['type']}"
            }
        )

        result = await service.execute_action(session.session_id, action)

        # Handle user login pause
        if action["type"] == "ensure_login":
            await mcp_session.send_notification(
                method="notifications/message",
                params={
                    "level": "warning",
                    "message": action.get("instruction_to_user", "Please log in")
                }
            )
            # Wait for user confirmation (blocks until login confirmed)

    # Cleanup
    service.end_session(session.session_id)

    return {
        "status": "completed",
        "extracted_data": session.final_data
    }
```

---

## 9. Implementation Phases

### Phase 1: Core MCP Server (Weeks 1-3)

**Goals:**
- MCP server blueprint with authentication
- Core tools: documents, conversations, workflows
- Resource URIs for documents and conversations
- Basic prompt templates

**Deliverables:**
1. **MCP Server Infrastructure**
   - Flask blueprint: `app/blueprints/mcp/`
   - Internal MCP server (tool registry)
   - User context propagation from Flask session
   - Audit logging for tool calls

2. **Document Tools**
   - `list_documents`, `search_documents`, `get_document_content`
   - `delete_document`, `rename_document`
   - Resource: `vandalizer://documents/{uuid}`

3. **Conversation Tools**
   - `start_conversation`, `send_message`, `get_conversation_history`
   - `attach_url_to_conversation`, `attach_document_to_conversation`
   - Resource: `vandalizer://conversations/{uuid}`

4. **Workflow Tools**
   - `list_workflows`, `get_workflow_details`, `run_workflow`
   - `get_workflow_status`, `cancel_workflow`, `download_workflow_result`
   - Resource: `vandalizer://workflows/{id}`

5. **Testing**
   - Unit tests for each tool
   - Integration tests with chat agent
   - Test tool discovery and execution

**Success Criteria:**
- Chat agent can discover and use MCP tools
- Can list documents, run workflows, get results
- Progress streaming works for workflows
- Audit logs are created

---

### Phase 2: MCP Client Integration (Weeks 4-5)

**Goals:**
- Embed MCP client in chat agent
- Auto-discover tools from internal and external servers
- Enable autonomous multi-step workflows

**Deliverables:**
1. **MCP Client Setup**
   - Install MCP client library (e.g., `mcp` Python package)
   - Configure connection to internal MCP server
   - Add external MCP server support (GitHub, etc.)

2. **Agent Enhancement**
   - Modify `create_chat_agent()` to include MCP tools
   - Convert MCP tools to Pydantic-AI tools
   - Pass user context with all tool calls

3. **Tool Discovery**
   - List all available tools on agent initialization
   - Include tool descriptions in system prompt
   - Handle tool discovery errors gracefully

4. **Context Management**
   - Extract user context from Flask session
   - Propagate context to all MCP calls
   - Handle team/space switching

5. **Testing**
   - Test agent with internal tools (document operations)
   - Test agent with external tools (GitHub MCP)
   - Test multi-step orchestration
   - Test context isolation between users

**Success Criteria:**
- Chat agent can autonomously use MCP tools
- Multi-step workflows execute correctly
- External MCP servers work (GitHub issue creation, etc.)
- User context is properly enforced

---

### Phase 3: Browser Automation MCP Integration (Weeks 6-7)

**Goals:**
- Expose browser automation as MCP tools
- Enable document-to-web workflows
- Stream browser automation progress

**Deliverables:**
1. **Browser Automation Tools**
   - `browser_start_session`, `browser_navigate`, `browser_fill_form`
   - `browser_click`, `browser_extract_data`, `browser_end_session`
   - `browser_automation_workflow` (composite tool)

2. **Progress Streaming**
   - Forward browser WebSocket events as MCP notifications
   - Stream action-by-action progress
   - Handle user login pauses with MCP messages

3. **User Login Flow**
   - Detect `ensure_login` actions
   - Send MCP notification to display login prompt
   - Wait for user confirmation before continuing
   - Update chat UI to show login instructions

4. **Composite Workflows**
   - Document extraction → browser verification workflows
   - Automatic comparison and discrepancy detection
   - LLM-generated summaries of verification results

5. **Testing**
   - Test individual browser tools
   - Test complete document-to-web workflow
   - Test user login flow in chat interface
   - Test progress streaming accuracy

**Success Criteria:**
- Agent can autonomously run browser automation
- Document-to-web verification works end-to-end
- User login prompts appear correctly in chat UI
- Progress notifications work correctly

---

### Phase 4: Advanced Features (Weeks 8-10)

**Goals:**
- Extraction tools and recommendations
- Activity tracking and analytics
- Advanced prompt templates
- Performance optimization

**Deliverables:**
1. **Extraction Tools**
   - `list_extraction_sets`, `run_extraction`, `get_extraction_status`
   - Custom field extraction without predefined sets
   - Resource: `vandalizer://extractions/{id}`

2. **Recommendation Tools**
   - `recommend_workflows`, `recommend_extractions`
   - `get_activity_history`, `get_popular_workflows`
   - Semantic search integration with ChromaDB

3. **Context Tools**
   - `get_current_context`, `switch_team`, `list_teams`
   - `create_folder`, team/space management

4. **Advanced Prompts**
   - `extract_structured_data`, `summarize_documents`
   - `compare_document_versions`, `auto_classify_documents`
   - `verify_compliance`, `web_to_document_extraction`

5. **Performance Optimization**
   - Caching for frequently accessed resources
   - Batch operations for bulk tool calls
   - Async execution for independent operations
   - Connection pooling for external MCP servers

6. **Documentation**
   - MCP tool reference documentation
   - Example workflows and use cases
   - Agent configuration guide
   - External MCP server integration examples (GitHub, etc.)

**Success Criteria:**
- All core Vandalizer features accessible via MCP
- Recommendations integrate with chat agent
- Performance meets production standards
- Documentation is comprehensive

---

### Phase 5: Production Hardening (Weeks 11-12)

**Goals:**
- Security audits
- Load testing
- Monitoring and observability
- Production deployment

**Deliverables:**
1. **Security**
   - Penetration testing of MCP tool execution
   - Permission validation audit
   - Input sanitization review
   - Security testing for browser automation

2. **Monitoring**
   - MCP tool call metrics (Prometheus/Grafana)
   - Error rate tracking
   - Performance dashboards
   - Alert rules for failures

3. **Observability**
   - Distributed tracing for tool calls
   - Correlation IDs across services
   - Detailed error logging
   - User activity heatmaps

4. **Load Testing**
   - Concurrent user chat session testing
   - Celery task queue stress testing
   - Database connection pooling limits
   - Tool execution performance benchmarks

5. **Deployment**
   - Production environment setup
   - Blue-green deployment strategy
   - Rollback procedures
   - Disaster recovery plan

**Success Criteria:**
- Security audit passes
- Handles 1000+ concurrent user chat sessions
- 99.9% uptime SLA
- Production deployment successful

---

## 10. Advanced Use Cases

### 10.1 Autonomous Document Triage

**Scenario:** New documents uploaded → Automatically classify, extract, and route.

**Implementation:**

```
User uploads 50 mixed documents (invoices, contracts, receipts)

[Autopilot Agent with MCP]
1. tool_call: list_documents(limit=50, folder="Inbox")
   → Retrieves recent uploads

2. For each document:
   a. tool_call: auto_classify_documents(document_uuids=[doc])
      → Returns: "Invoice"

   b. Based on classification, select workflow:
      - Invoice → run_workflow(workflow_id="invoice_extraction")
      - Contract → run_workflow(workflow_id="contract_analysis")
      - Receipt → run_workflow(workflow_id="receipt_ocr")

   c. tool_call: run_workflow(...)
      → Extracts relevant fields

   d. tool_call: recommend_workflows(document_uuids=[doc])
      → Suggests additional processing steps

   e. Move to appropriate folder based on classification

3. Generate summary report:
   "Processed 50 documents:
    - 23 invoices (total: $45,890)
    - 15 contracts (3 require legal review)
    - 12 receipts (categorized for expense report)"
```

**Value:** User uploads documents and they're automatically processed, classified, and organized without manual intervention.

### 10.2 Cross-Platform Knowledge Synthesis

**Scenario:** Combine Vandalizer docs with external data sources (GitHub, Snowflake, Calendar).

**Implementation:**

```
User: "Summarize all project deliverables mentioned in our contracts,
       check if we have GitHub issues for them, and identify any gaps."

[Agent with MCP - Multiple Servers]
1. tool_call: search_documents(query="deliverables project scope")
   → Finds 5 contract documents

2. tool_call: run_extraction(
     document_uuids=[...],
     fields=["deliverable", "due_date", "status"]
   )
   → Extracts: ["Feature A - 2024-03-15", "Feature B - 2024-04-01", ...]

3. For each deliverable:
   tool_call: github.search_issues(query="Feature A")
   → Checks if GitHub issue exists

4. Identify gaps (deliverables without issues)

5. tool_call: calendar.check_availability(dates=[...])
   → Verify if due dates align with team capacity

6. Generate report:
   "Found 12 deliverables across 5 contracts:
    ✓ 8 have active GitHub issues
    ❌ 4 missing GitHub issues: Feature C, Feature G, Feature H, Feature K
    ⚠️ 3 due dates conflict with planned PTO

    Recommended actions:
    1. Create GitHub issues for 4 missing deliverables
    2. Review timeline for Features X, Y, Z due to PTO conflicts"

7. Offer: "Would you like me to create the missing GitHub issues?"
```

**Value:** Seamlessly combines internal documents with external project management and calendar data.

### 10.3 Compliance Monitoring Pipeline

**Scenario:** Continuous monitoring of uploaded documents for compliance violations.

**Implementation:**

```
[Background Agent - Triggered on Document Upload]

1. tool_call: get_document_content(document_uuid=new_upload)

2. tool_call: verify_compliance(
     document_uuids=[new_upload],
     rules="GDPR, HIPAA, SOC2"
   )
   → Returns: [
       {rule: "GDPR", status: "FAIL", reason: "PII without consent notice"},
       {rule: "HIPAA", status: "PASS"},
       {rule: "SOC2", status: "FAIL", reason: "Unencrypted sensitive data"}
     ]

3. If violations found:
   a. Flag document in database

   b. tool_call: github.create_issue(
        title="Compliance Violation: GDPR in Document XYZ",
        body="...",
        labels=["compliance", "urgent"]
      )

   c. tool_call: send_message(
        conversation_uuid=compliance_channel,
        message="⚠️ New compliance violation detected in Document XYZ"
      )

4. Generate audit trail:
   - ActivityEvent with compliance results
   - Notification to compliance team
   - Automatic remediation suggestions
```

**Value:** Automated, real-time compliance monitoring with cross-system alerting.

### 10.4 Intelligent Workflow Composition

**Scenario:** User describes desired outcome; agent composes custom workflow.

**Implementation:**

```
User: "I need to extract party names and dates from these contracts,
       summarize each in one paragraph, then export to CSV"

[Agent with MCP]
1. Analyze request:
   - Extraction: party names, dates
   - Transformation: summarization
   - Output: CSV format

2. tool_call: list_workflows()
   → Check if existing workflow matches

3. If no match, compose custom workflow:

   a. Create extraction configuration:
      {
        fields: ["party_names", "dates"],
        context: "Legal contracts"
      }

   b. Create prompt configuration:
      {
        prompt: "Summarize this contract in one paragraph focusing on parties and key dates",
        model: "claude-sonnet-4-5"
      }

   c. Create formatter configuration:
      {
        format: "CSV",
        columns: ["Document", "Party Names", "Dates", "Summary"]
      }

4. Execute composed workflow:
   tool_call: run_extraction(...)
   → Extract fields

   tool_call: send_message(...)  # For summarization
   → Generate summaries

   tool_call: format_output(...)
   → Convert to CSV

5. Return result:
   "Here's your CSV with extracted data and summaries: [download link]"

6. Offer to save as reusable workflow:
   "Would you like me to save this as a workflow named 'Contract Summary Export'
    for future use?"
```

**Value:** No-code workflow creation through natural language.

### 10.5 Multi-Document Analysis with Web Verification

**Scenario:** Analyze documents and cross-reference with live web data.

**Implementation:**

```
User: "Check if the pricing in these vendor proposals matches what's currently
       listed on their websites"

[Agent with MCP]
1. tool_call: search_documents(query="vendor proposal pricing")
   → Finds 3 vendor proposals

2. tool_call: run_extraction(
     document_uuids=[...],
     fields=["vendor_name", "product", "price", "website_url"]
   )
   → Extracts: [
       {vendor: "Acme Corp", product: "Widget X", price: "$500", url: "acme.com"},
       ...
     ]

3. For each vendor:
   tool_call: browser_automation_workflow(
     actions=[
       {navigate: extracted_data.url},
       {search_for_product: extracted_data.product},
       {extract: ["current_price"]}
     ]
   )
   → Scrapes current web pricing

4. Compare:
   - Document price vs web price
   - Flag discrepancies

5. Generate report:
   "Pricing Analysis:

   Acme Corp - Widget X:
   📄 Proposal: $500
   🌐 Website: $450
   ✓ FAVORABLE ($50 savings)

   BetaCo - Gadget Y:
   📄 Proposal: $1,200
   🌐 Website: $1,350
   ⚠️ DISCREPANCY ($150 increase since proposal)

   Recommendation: Request updated pricing from BetaCo before proceeding."

6. tool_call: attach_url_to_conversation(url="betaco.com/pricing")
   → Attach web evidence for reference
```

**Value:** Automated vendor price verification across documents and live websites.

---


## 11. Performance and Scalability

### 11.1 Caching Strategy

**Resource Caching:**

```python
from functools import lru_cache
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)

@lru_cache(maxsize=1000)
def get_document_content_cached(document_uuid):
    """
    Cache document content in memory (LRU)
    """
    # Check Redis first
    cached = redis_client.get(f"doc_content:{document_uuid}")
    if cached:
        return json.loads(cached)

    # Fetch from MongoDB
    doc = SmartDocument.objects.get(uuid=document_uuid)
    content = {
        "text": doc.text_content,
        "metadata": doc.to_json()
    }

    # Cache for 1 hour
    redis_client.setex(
        f"doc_content:{document_uuid}",
        3600,
        json.dumps(content)
    )

    return content
```

**Tool Discovery Caching:**

```python
# Cache tool list per user context
def get_tools_for_user(user_context):
    cache_key = f"mcp_tools:{user_context['user_id']}:{user_context.get('team_id')}"

    cached_tools = redis_client.get(cache_key)
    if cached_tools:
        return json.loads(cached_tools)

    # Build tool list based on scopes
    tools = build_tool_catalog(user_context)

    # Cache for 10 minutes
    redis_client.setex(cache_key, 600, json.dumps(tools))

    return tools
```

**Activity History Caching:**

```python
# Cache recent activities
def get_activity_history(user_id, limit=20):
    cache_key = f"activities:{user_id}:{limit}"

    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    activities = ActivityEvent.objects(user_id=user_id).order_by('-created_at').limit(limit)

    # Cache for 1 minute (frequently updated)
    redis_client.setex(cache_key, 60, activities.to_json())

    return activities
```

### 11.2 Connection Pooling

**MCP Client Connection Pool:**

```python
from asyncio import Queue

class MCPConnectionPool:
    """
    Pool of MCP client connections to external servers
    """

    def __init__(self, server_url, pool_size=10):
        self.server_url = server_url
        self.pool = Queue(maxsize=pool_size)

        # Pre-populate pool
        for _ in range(pool_size):
            client = MCPClient(url=server_url)
            self.pool.put_nowait(client)

    async def acquire(self):
        """Get client from pool"""
        return await self.pool.get()

    async def release(self, client):
        """Return client to pool"""
        await self.pool.put(client)

    async def call_tool(self, tool_name, **kwargs):
        """Call tool using pooled connection"""
        client = await self.acquire()
        try:
            result = await client.call_tool(tool_name, **kwargs)
            return result
        finally:
            await self.release(client)
```

**MongoDB Connection Pooling:**

```python
# Already handled by MongoEngine, but ensure proper config
from mongoengine import connect

connect(
    db="vandalizer",
    host="mongodb://localhost:27017",
    maxPoolSize=50,  # Increase for high concurrency
    minPoolSize=10,
    maxIdleTimeMS=30000
)
```

### 11.3 Async Execution

**Tool Execution:**

```python
import asyncio

async def execute_tools_in_parallel(tool_calls):
    """
    Execute multiple independent tool calls concurrently
    """
    tasks = [
        call_mcp_tool(tool["name"], tool["args"])
        for tool in tool_calls
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle errors
    return [
        result if not isinstance(result, Exception) else {"error": str(result)}
        for result in results
    ]
```

**Batch Operations:**

```python
@mcp_tool("batch_extract_documents")
async def batch_extract_documents(document_uuids, fields):
    """
    Extract data from multiple documents in parallel
    """
    extraction_tasks = [
        run_extraction_async(doc_uuid, fields)
        for doc_uuid in document_uuids
    ]

    results = await asyncio.gather(*extraction_tasks)

    return {
        "extracted": len(results),
        "results": results
    }
```

### 11.4 Load Balancing

**Multiple MCP Server Instances:**

```
[Load Balancer - NGINX]
  ↓
[MCP Server Instance 1] ← Flask app 1
[MCP Server Instance 2] ← Flask app 2
[MCP Server Instance 3] ← Flask app 3
  ↓
[Shared Redis Cache]
[Shared MongoDB]
[Shared Celery Queue]
```

**NGINX Configuration:**

```nginx
upstream mcp_servers {
    least_conn;  # Load balance by least connections
    server 127.0.0.1:5001;
    server 127.0.0.1:5002;
    server 127.0.0.1:5003;
}

server {
    listen 443 ssl;
    server_name vandalizer.example.com;

    location /mcp {
        proxy_pass http://mcp_servers;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### 11.5 Monitoring and Metrics

**Prometheus Metrics:**

```python
from prometheus_client import Counter, Histogram, Gauge

# MCP tool call metrics
mcp_tool_calls_total = Counter(
    'mcp_tool_calls_total',
    'Total MCP tool calls',
    ['tool_name', 'status']
)

mcp_tool_duration_seconds = Histogram(
    'mcp_tool_duration_seconds',
    'MCP tool execution time',
    ['tool_name']
)

mcp_active_sessions = Gauge(
    'mcp_active_sessions',
    'Number of active MCP sessions'
)

# Track in tool execution
@mcp_tool("run_workflow")
def run_workflow_tool(**kwargs):
    start_time = time.time()
    mcp_active_sessions.inc()

    try:
        result = execute_workflow(**kwargs)
        mcp_tool_calls_total.labels(tool_name="run_workflow", status="success").inc()
        return result
    except Exception as e:
        mcp_tool_calls_total.labels(tool_name="run_workflow", status="error").inc()
        raise
    finally:
        duration = time.time() - start_time
        mcp_tool_duration_seconds.labels(tool_name="run_workflow").observe(duration)
        mcp_active_sessions.dec()
```

**Grafana Dashboards:**

- MCP Tool Call Rate (calls/sec)
- Tool Latency (p50, p95, p99)
- Error Rate by Tool
- Active User Sessions
- Tool Usage by User/Team
- Celery Task Queue Depth

---

## 12. Future Enhancements

### 12.1 MCP Marketplace

**Vision:** Vandalizer-specific MCP servers contributed by community.

**Examples:**

- **Legal Contract Analysis MCP**: Specialized tools for contract review
- **Financial Document MCP**: Advanced invoice/receipt processing
- **Compliance MCP**: Industry-specific compliance checking (HIPAA, GDPR, SOC2)
- **Translation MCP**: Multi-language document translation
- **OCR Enhancement MCP**: Advanced OCR with handwriting recognition

**Implementation:**

```
[Vandalizer Marketplace]
  ↓
[User browses MCP servers]
  ↓
[Installs "Legal Contract MCP"]
  ↓
[Server added to user's MCP client config]
  ↓
[Chat agent auto-discovers new tools]
```

### 12.2 Visual Workflow Builder with MCP

**Vision:** Drag-and-drop workflow builder that generates MCP tool sequences.

**UI:**

```
[Canvas]
  ┌───────────────┐
  │ Select Docs   │ (MCP: list_documents)
  └───────┬───────┘
          │
  ┌───────▼───────┐
  │ Extract Data  │ (MCP: run_extraction)
  └───────┬───────┘
          │
  ┌───────▼───────┐
  │ Verify Web    │ (MCP: browser_automation_workflow)
  └───────┬───────┘
          │
  ┌───────▼───────┐
  │ Generate CSV  │ (MCP: format_output)
  └───────────────┘
```

**Generated MCP Sequence:**

```json
{
  "workflow": "Document to Web Verification",
  "steps": [
    {
      "tool": "list_documents",
      "params": {"folder_uuid": "{{input.folder}}", "limit": 10}
    },
    {
      "tool": "run_extraction",
      "params": {"document_uuids": "{{steps[0].documents}}", "fields": ["invoice_number", "total"]}
    },
    {
      "tool": "browser_automation_workflow",
      "params": {"actions": [...]}
    },
    {
      "tool": "format_output",
      "params": {"format": "csv", "data": "{{steps[2].extracted_data}}"}
    }
  ]
}
```

**Value:** Non-technical users can build complex MCP workflows visually.

### 12.3 MCP Workflow Versioning

**Vision:** Version control for MCP tool sequences and workflows.

**Features:**

- Git-like versioning for workflows
- Branching and merging of workflow variants
- Rollback to previous versions
- A/B testing different workflow configurations
- Team collaboration with pull requests

**Example:**

```
[User creates workflow v1.0]
  → Commits to version control

[User creates branch "improved-extraction"]
  → Modifies extraction parameters
  → Tests on sample documents
  → Compares results with v1.0
  → Merges if better performance

[Workflow now at v1.1]
  → All team members auto-updated
```

### 12.4 Multi-Agent Orchestration

**Vision:** Multiple specialized agents collaborate via MCP.

**Architecture:**

```
[User Request] "Complete due diligence on this acquisition target"
  ↓
[Coordinator Agent]
  ↓
  ├─→ [Legal Agent] (uses legal MCP tools)
  │   → Reviews contracts, checks compliance
  │
  ├─→ [Financial Agent] (uses financial MCP tools)
  │   → Analyzes financials, calculates metrics
  │
  ├─→ [Web Research Agent] (uses browser automation MCP)
  │   → Scrapes public info, news articles
  │
  └─→ [Synthesis Agent]
      → Combines all findings into comprehensive report
```

**Implementation:**

```python
# Coordinator agent with multiple specialized sub-agents
class DueDiligenceOrchestrator:

    def __init__(self):
        self.legal_agent = create_chat_agent(
            model="claude-opus-4-5",
            mcp_servers=["vandalizer", "legal-mcp"]
        )

        self.financial_agent = create_chat_agent(
            model="claude-sonnet-4-5",
            mcp_servers=["vandalizer", "financial-mcp"]
        )

        self.research_agent = create_chat_agent(
            model="claude-sonnet-4-5",
            mcp_servers=["vandalizer", "browser-automation"]
        )

    async def perform_due_diligence(self, target_company, documents):
        # Parallel execution of specialized agents
        results = await asyncio.gather(
            self.legal_agent.analyze(documents, focus="legal risks"),
            self.financial_agent.analyze(documents, focus="financial health"),
            self.research_agent.research(target_company, sources=["web", "news"])
        )

        # Synthesis agent combines findings
        synthesis_agent = create_chat_agent(model="claude-opus-4-5")
        final_report = await synthesis_agent.synthesize(results)

        return final_report
```

**Value:** Complex multi-domain tasks executed by specialized expert agents.

### 12.5 Real-Time Collaboration via MCP

**Vision:** Multiple users collaborating on workflows in real-time via MCP.

**Features:**

- Shared MCP sessions
- Real-time cursor tracking in workflow builder
- Live progress updates for all team members
- Collaborative chat with shared MCP context

**Example:**

```
[User A] Starts workflow on Document X
  ↓ MCP broadcast to team

[User B] Sees notification: "Alice is extracting data from Contract.pdf"
  ↓ Joins session

[User A & B] See same progress updates
  ↓ User B suggests different extraction fields
  ↓ User A adjusts workflow

[Both users] Review results together
  ↓ Approve and save workflow
```

### 12.6 MCP-Powered Training and Recommendations

**Vision:** System learns from MCP tool usage to recommend workflows.

**Implementation:**

```
[ActivityEvent tracking]
  → Records all MCP tool calls with context

[ML Model]
  → Analyzes patterns:
    - Which tools are used together
    - Successful vs failed workflows
    - User preferences and behavior

[Recommendation Engine]
  → Suggests:
    - "Users who extracted invoices also ran this workflow"
    - "This workflow succeeded 95% of the time for similar documents"
    - "Based on your document, I recommend extracting these fields"

[Proactive Agent]
  → "I noticed you often extract invoices and verify on vendor sites.
      Would you like me to create an automated workflow for this?"
```

**Value:** Continuous improvement through usage analytics.

---

## Conclusion

Integrating MCP into Vandalizer transforms it from a powerful document processing platform into an **intelligent, autonomous workflow orchestrator**.

**Key Benefits:**

1. **Autonomous Agents**: Chat becomes truly agentic with tool-calling capabilities
2. **Tool Discoverability**: Agent automatically finds and uses all Vandalizer capabilities
3. **Composability**: Seamlessly combine internal tools + external MCP servers (GitHub, databases, etc.)
4. **Browser Automation**: Document-to-web workflows via Chrome extension MCP tools
5. **Future-Proof**: New features auto-discoverable without modifying agent code
6. **Security**: Uses existing Flask session authentication and RBAC
7. **Performance**: Caching, connection pooling, async execution

**Strategic Value:**

- **Competitive Differentiation**: Autonomous agents that can orchestrate complex workflows
- **External Integration**: Connect to any MCP-compatible service (GitHub, Snowflake, calendars)
- **No Custom Code**: Add new capabilities without hardcoding in agent logic
- **User Productivity**: Autonomous agents handle complex multi-step workflows
- **Unified Interface**: Standardized tool layer for all Vandalizer operations

**Timeline:** 12 weeks to full production MCP integration with browser automation.

**Next Steps:**
1. Review and approve this plan
2. Set up development environment for MCP
3. Begin Phase 1: Core MCP Server (document/conversation/workflow tools)
4. Parallel track: Continue browser automation development from AGENTIAL_CHROME_EXTENSION_WORKFLOW.md
5. Integrate browser automation as MCP tools in Phase 3

This MCP layer will position Vandalizer as a leader in the emerging AI-native document processing space.
