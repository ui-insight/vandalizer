# Passive Vandalizer System - Comprehensive Implementation Plan

## Executive Summary

This document provides a detailed specification for transforming Vandalizer from a **user-triggered, request-driven system** into a **fully passive, autonomous document processing platform** by extending the existing **Workflow system** with **Input Configuration** and **Output Configuration** capabilities.

### Key Architectural Decision

**Instead of creating a separate "Processing Rules" system, we enhance the existing Workflow model to support:**
- **Input Configuration**: How and when the workflow triggers (manual, folder watch, schedule, API)
- **Output Configuration**: What happens when the workflow completes (storage, notifications, webhooks, exports)

This approach is superior because:
1. Users already understand workflows - no new concepts to learn
2. Existing workflows can be "upgraded" to passive mode
3. Single unified system for all automation
4. Workflows, extractions, and chains all use the same trigger/output system
5. Simpler mental model: "A workflow can run manually OR automatically"

### Current State Analysis

**How Vandalizer Works Today:**
- Users manually upload documents via the web UI
- Users explicitly select documents and click "Run" to execute workflows or extractions
- Workflows have steps but no concept of "how they start" or "what happens after"
- Results appear in the Activity stream only
- No scheduled tasks, no event listeners, no automatic triggers

**Target State Vision:**

Every workflow gains two new configuration sections:
```
┌─────────────────────────────────────────────────────────────────────┐
│                         WORKFLOW                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────┐     ┌───────────────┐     ┌───────────────┐     │
│  │    INPUT      │ ──► │    STEPS      │ ──► │    OUTPUT     │     │
│  │ CONFIGURATION │     │  (existing)   │     │ CONFIGURATION │     │
│  └───────────────┘     └───────────────┘     └───────────────┘     │
│                                                                     │
│  • Manual trigger       • Step 1: Extract    • Save to folder      │
│  • Folder watch         • Step 2: Analyze    • Email results       │
│  • Schedule             • Step 3: Format     • Webhook delivery    │
│  • API endpoint                              • Chain to workflow   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Core Concept: Enhanced Workflow Model

### Current Workflow Structure

```
Workflow (existing):
├── name
├── description
├── steps: Array of WorkflowStep
├── attachments
├── user_id
├── team
├── verified
└── timestamps
```

### Enhanced Workflow Structure

```
Workflow (enhanced):
├── name
├── description
├── user_id
├── team
├── verified
├── timestamps
│
├── ═══════════════════════════════════════════════════════════════
│   STEPS (existing, unchanged)
├── ═══════════════════════════════════════════════════════════════
├── steps: Array of WorkflowStep
├── attachments
│
├── ═══════════════════════════════════════════════════════════════
│   INPUT CONFIGURATION (NEW)
├── ═══════════════════════════════════════════════════════════════
├── input_config: Object
│   ├── manual_enabled: Boolean (default: true)
│   │   └── Allow manual "Run" button (current behavior)
│   │
│   ├── folder_watch: Object (optional)
│   │   ├── enabled: Boolean
│   │   ├── folders: Array of References → SmartFolder
│   │   ├── spaces: Array of References → Space
│   │   ├── delay_seconds: Integer (default: 300)
│   │   ├── file_filters: Object
│   │   │   ├── types: Array ["pdf", "docx", "xlsx"]
│   │   │   ├── name_patterns: Array ["invoice_*", "report_*"]
│   │   │   ├── exclude_patterns: Array ["*_draft*", "temp_*"]
│   │   │   ├── min_size_bytes: Integer
│   │   │   └── max_size_bytes: Integer
│   │   └── batch_mode: Enum ("per_document", "collect_batch", "time_window")
│   │
│   ├── schedule: Object (optional)
│   │   ├── enabled: Boolean
│   │   ├── type: Enum ("interval", "cron", "one_time")
│   │   ├── interval_value: Integer
│   │   ├── interval_unit: Enum ("minutes", "hours", "days")
│   │   ├── cron_expression: String
│   │   ├── one_time_datetime: DateTime
│   │   ├── timezone: String
│   │   ├── document_source: Enum ("watched_folders", "specific_folder", "all_space", "query")
│   │   └── document_query: Object (if source is "query")
│   │
│   ├── api_trigger: Object (optional)
│   │   ├── enabled: Boolean
│   │   ├── api_key: String (auto-generated)
│   │   ├── allowed_ips: Array (optional whitelist)
│   │   └── require_documents: Boolean
│   │
│   └── conditions: Array (apply to all triggers)
│       └── { field, operator, value }
│
├── ═══════════════════════════════════════════════════════════════
│   OUTPUT CONFIGURATION (NEW)
├── ═══════════════════════════════════════════════════════════════
├── output_config: Object
│   ├── storage: Object
│   │   ├── enabled: Boolean
│   │   ├── destination_folder: Reference → SmartFolder
│   │   ├── file_naming: String template
│   │   ├── format: Enum ("csv", "json", "xlsx", "pdf")
│   │   ├── append_mode: Boolean
│   │   └── retention_days: Integer
│   │
│   ├── notifications: Array
│   │   └── {
│   │         channel: Enum ("email", "in_app", "slack", "teams"),
│   │         recipients: Array,
│   │         notify_owner: Boolean,
│   │         notify_team: Boolean,
│   │         conditions: Enum ("always", "success", "failure", "conditional"),
│   │         condition_expression: String (if conditional),
│   │         include_summary: Boolean,
│   │         include_download: Boolean,
│   │         include_full_results: Boolean,
│   │         template: String (optional custom template)
│   │       }
│   │
│   ├── webhooks: Array
│   │   └── {
│   │         url: String,
│   │         method: Enum ("POST", "PUT"),
│   │         auth_type: Enum ("none", "api_key", "bearer", "basic", "oauth"),
│   │         auth_config: Object,
│   │         headers: Object,
│   │         payload_template: String,
│   │         retry_count: Integer,
│   │         retry_delay_seconds: Integer
│   │       }
│   │
│   ├── chain_workflows: Array
│   │   └── {
│   │         workflow: Reference → Workflow,
│   │         condition: Enum ("always", "on_success", "on_failure", "conditional"),
│   │         condition_expression: String,
│   │         pass_output: Boolean,
│   │         pass_documents: Boolean
│   │       }
│   │
│   └── exports: Array (future)
│       └── { destination: "s3" | "gdrive" | "onedrive", config: Object }
│
├── ═══════════════════════════════════════════════════════════════
│   RESOURCE CONTROLS (NEW)
├── ═══════════════════════════════════════════════════════════════
├── resource_config: Object
│   ├── budget: Object
│   │   ├── daily_token_limit: Integer
│   │   ├── monthly_token_limit: Integer
│   │   ├── daily_document_limit: Integer
│   │   ├── on_limit_reached: Enum ("pause", "continue_silent", "queue")
│   │   └── alert_at_percentage: Integer (e.g., 80)
│   │
│   ├── throttling: Object
│   │   ├── max_concurrent: Integer
│   │   ├── min_delay_between_runs: Integer (seconds)
│   │   └── max_documents_per_run: Integer
│   │
│   └── retry: Object
│       ├── max_retries: Integer
│       ├── retry_delay_seconds: Integer
│       └── retry_on_errors: Array of error types
│
├── ═══════════════════════════════════════════════════════════════
│   TRACKING (NEW)
├── ═══════════════════════════════════════════════════════════════
└── stats: Object
    ├── total_runs: Integer
    ├── manual_runs: Integer
    ├── passive_runs: Integer
    ├── successful_runs: Integer
    ├── failed_runs: Integer
    ├── documents_processed: Integer
    ├── tokens_used: Integer
    ├── last_run_at: DateTime
    ├── last_passive_run_at: DateTime
    └── next_scheduled_run_at: DateTime
```

---

## Phase 1: Workflow Builder Enhancement - Input Configuration

### 1.1 Input Configuration UI

The existing workflow builder gains a new "Input" tab/section that appears **before** the steps:

```
┌─────────────────────────────────────────────────────────────────────┐
│ Edit Workflow: Invoice Processing                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ [Input ●]  [Steps]  [Output]  [Settings]                           │
│                                                                     │
│ ═══════════════════════════════════════════════════════════════════ │
│ HOW SHOULD THIS WORKFLOW START?                                     │
│ ═══════════════════════════════════════════════════════════════════ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ [✓] MANUAL                                              Default │ │
│ │     Run this workflow by clicking "Run" and selecting documents │ │
│ │     This is the standard behavior.                              │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ [✓] FOLDER WATCH                                       Passive │ │
│ │     Automatically run when new documents arrive                 │ │
│ │                                                                 │ │
│ │     Watch these locations:                                      │ │
│ │     ┌───────────────────────────────────────────────────────┐   │ │
│ │     │ 📁 Incoming Invoices                            [✕]  │   │ │
│ │     │ 📁 Accounts Payable / New                       [✕]  │   │ │
│ │     └───────────────────────────────────────────────────────┘   │ │
│ │     [+ Add Folder]  [+ Add Space]                               │ │
│ │                                                                 │ │
│ │     ▼ Advanced Options                                          │ │
│ │     ┌───────────────────────────────────────────────────────┐   │ │
│ │     │ Wait [5] minutes after upload before processing       │   │ │
│ │     │ (Allows time for batch uploads to complete)           │   │ │
│ │     │                                                       │   │ │
│ │     │ Only process files matching:                          │   │ │
│ │     │ [✓] PDF  [✓] Word  [ ] Excel  [ ] Images  [ ] All    │   │ │
│ │     │                                                       │   │ │
│ │     │ Exclude files matching: [*_draft*, temp_*______]      │   │ │
│ │     │                                                       │   │ │
│ │     │ Processing mode:                                      │   │ │
│ │     │ ● Process each document as it arrives                 │   │ │
│ │     │ ○ Collect documents, process as batch every [1] hour  │   │ │
│ │     │ ○ Collect for [5] minutes, then process batch         │   │ │
│ │     └───────────────────────────────────────────────────────┘   │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ [ ] SCHEDULE                                            Passive │ │
│ │     Run this workflow on a recurring schedule                   │ │
│ │                                                                 │ │
│ │     Schedule type:                                              │ │
│ │     ○ Run every [1] [day(s) ▼]                                  │ │
│ │     ● Run on schedule: [0] [6] [*] [*] [*]                      │ │
│ │       Preview: "Every day at 6:00 AM"                           │ │
│ │     ○ Run once on [January 30, 2026] at [2:00 PM]               │ │
│ │                                                                 │ │
│ │     Timezone: [America/Boise ▼] (Mountain Time)                 │ │
│ │                                                                 │ │
│ │     Documents to process:                                       │ │
│ │     ● All new documents in watched folders since last run       │ │
│ │     ○ All documents in: [Select Folder ▼]                       │ │
│ │     ○ Documents matching query: [Configure...]                  │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ [ ] API TRIGGER                                        Advanced │ │
│ │     Trigger this workflow via API call                          │ │
│ │                                                                 │ │
│ │     Endpoint: POST /api/v1/workflows/{id}/trigger               │ │
│ │     API Key: [Generate Key]                                     │ │
│ │     [View API Documentation]                                    │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ═══════════════════════════════════════════════════════════════════ │
│ DOCUMENT CONDITIONS (Optional)                                      │
│ ═══════════════════════════════════════════════════════════════════ │
│ Only process documents that match ALL of these conditions:          │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ [File size] [is less than ▼] [10 MB_______]              [✕]   │ │
│ │ [+ Add Condition]                                               │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│                                                    [Continue →]     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Folder Watch - Detailed Behavior

#### What It Does
When folder watch is enabled, the workflow automatically processes new documents that appear in the configured folders.

#### How It Works

```
Document uploaded to "Incoming Invoices" folder
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Upload endpoint checks: Any workflows watching this folder?          │
│ Found: "Invoice Processing" workflow has folder_watch.enabled=true   │
└──────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Create WorkflowTriggerEvent:                                         │
│ - workflow: "Invoice Processing"                                     │
│ - document: invoice_2026_005.pdf                                     │
│ - trigger_type: "folder_watch"                                       │
│ - status: "pending"                                                  │
│ - process_after: now + 5 minutes (delay_seconds)                     │
└──────────────────────────────────────────────────────────────────────┘
                    │
                    │ (Celery Beat checks every minute)
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Process pending trigger events where process_after <= now            │
└──────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ For "Invoice Processing" workflow:                                   │
│ 1. Check file filters: Is it PDF/DOCX? ✓                            │
│ 2. Check conditions: Size < 10MB? ✓                                  │
│ 3. Check budget: Tokens remaining? ✓                                 │
│ 4. Check throttling: Not too many concurrent? ✓                      │
└──────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Execute workflow (reuses existing execute_workflow_task):            │
│ - Create WorkflowResult with is_passive=true                         │
│ - Run all workflow steps                                             │
│ - Store results                                                      │
└──────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Process output_config (Phase 2):                                     │
│ - Save to destination folder                                         │
│ - Send email notification                                            │
│ - Call webhook                                                       │
│ - Trigger chained workflows                                          │
└──────────────────────────────────────────────────────────────────────┘
```

#### Batch Processing Modes

**Per-Document (Default):**
```
Doc 1 arrives → Wait 5min → Process Doc 1
Doc 2 arrives → Wait 5min → Process Doc 2
Doc 3 arrives → Wait 5min → Process Doc 3
```

**Collect Batch (Time Window):**
```
Doc 1 arrives → Start 5min window
Doc 2 arrives → (within window)
Doc 3 arrives → (within window)
Window expires → Process [Doc 1, Doc 2, Doc 3] together
```

**Collect Batch (Interval):**
```
Docs arrive throughout the day
Every hour → Process all unprocessed docs as batch
```

#### Edge Cases

| Scenario | Behavior |
|----------|----------|
| Document deleted before processing | Trigger event marked "skipped", no error |
| Document modified during delay | Reset delay timer, process latest version |
| Folder watch disabled mid-processing | In-flight runs complete, no new triggers |
| Same doc triggers multiple workflows | Each workflow runs independently |
| Workflow fails | Retry per retry_config, then mark failed |
| Budget exceeded | Pause triggers, queue for next period |

### 1.3 Schedule - Detailed Behavior

#### What It Does
Runs the workflow at specified times, processing documents from configured sources.

#### Schedule Configuration UI

```
┌─────────────────────────────────────────────────────────────────────┐
│ SCHEDULE Configuration                                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ When to run:                                                        │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ ○ Interval                                                      │ │
│ │   Every [1] [day(s) ▼] starting [now ▼]                         │ │
│ │                                                                 │ │
│ │ ● Cron Schedule                                                 │ │
│ │   ┌─────┬─────┬─────┬─────┬─────┐                               │ │
│ │   │  0  │  6  │  *  │  *  │  1  │                               │ │
│ │   └──┬──┴──┬──┴──┬──┴──┬──┴──┬──┘                               │ │
│ │      │     │     │     │     └─ Day of week (1=Monday)          │ │
│ │      │     │     │     └─────── Month                           │ │
│ │      │     │     └───────────── Day of month                    │ │
│ │      │     └─────────────────── Hour (6 AM)                     │ │
│ │      └───────────────────────── Minute                          │ │
│ │                                                                 │ │
│ │   Preview: "Every Monday at 6:00 AM"                            │ │
│ │                                                                 │ │
│ │   Quick presets:                                                │ │
│ │   [Daily 6AM] [Daily 9AM] [Weekly Mon] [Monthly 1st] [Custom]   │ │
│ │                                                                 │ │
│ │ ○ One-time                                                      │ │
│ │   Run once on [January 30, 2026] at [2:00 PM]                   │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ Timezone: [America/Boise ▼] (Mountain Standard Time, UTC-7)        │
│                                                                     │
│ ─────────────────────────────────────────────────────────────────── │
│                                                                     │
│ Which documents to process:                                         │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ ● New documents since last run                                  │ │
│ │   From watched folders (if folder watch enabled)                │ │
│ │   Or from: [Incoming Invoices ▼]                                │ │
│ │                                                                 │ │
│ │ ○ All documents in folder                                       │ │
│ │   [Weekly Reports / 2026 ▼]                                     │ │
│ │   ⚠️ Warning: Will reprocess all documents each run             │ │
│ │                                                                 │ │
│ │ ○ Documents matching query                                      │ │
│ │   Created in last [7] days                                      │ │
│ │   With tags: [needs_review, pending____]                        │ │
│ │   [Configure Advanced Query...]                                 │ │
│ │                                                                 │ │
│ │ ○ No documents (workflow uses attachments only)                 │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ Next scheduled run: Monday, January 27, 2026 at 6:00 AM (in 2 days)│
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### Schedule + Folder Watch Interaction

When both are enabled:
- **Folder watch**: Processes documents as they arrive (real-time)
- **Schedule**: Runs at specified time with documents that haven't been processed yet

This allows patterns like:
- Process invoices immediately when they arrive
- Also run daily summary at 6 PM with all invoices processed that day

### 1.4 API Trigger

#### What It Does
Allows external systems to trigger the workflow programmatically.

#### API Trigger Configuration

```
┌─────────────────────────────────────────────────────────────────────┐
│ API TRIGGER Configuration                                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ [✓] Enable API Trigger                                              │
│                                                                     │
│ Endpoint:                                                           │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ POST https://vandalizer.example.com/api/v1/workflows/abc123/run │ │
│ │                                                    [Copy URL]   │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ Authentication:                                                     │
│ API Key: [vnd_wf_xxxxxxxxxxxxxxxxxxxx]  [Copy] [Regenerate]        │
│                                                                     │
│ Header: X-Workflow-API-Key: <your-key>                             │
│                                                                     │
│ ─────────────────────────────────────────────────────────────────── │
│                                                                     │
│ Request format:                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ POST /api/v1/workflows/abc123/run                               │ │
│ │ Headers:                                                        │ │
│ │   X-Workflow-API-Key: vnd_wf_xxxxxxxxxxxxxxxxxxxx               │ │
│ │   Content-Type: application/json                                │ │
│ │                                                                 │ │
│ │ Body:                                                           │ │
│ │ {                                                               │ │
│ │   "document_ids": ["doc1", "doc2"],  // Optional                │ │
│ │   "folder_id": "folder123",          // Optional: process all   │ │
│ │   "metadata": {                      // Optional: passed to wf  │ │
│ │     "source": "erp_system",                                     │ │
│ │     "batch_id": "batch_2026_001"                                │ │
│ │   }                                                             │ │
│ │ }                                                               │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ Security:                                                           │
│ [ ] Restrict to IP addresses: [192.168.1.0/24, 10.0.0.5___]        │
│ [✓] Require at least one document or folder                         │
│ [ ] Allow empty runs (for scheduled-style triggers)                 │ │
│                                                                     │
│ [View Full API Documentation]                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Phase 2: Workflow Builder Enhancement - Output Configuration

### 2.1 Output Configuration UI

After the Steps tab, a new "Output" tab configures what happens when the workflow completes:

```
┌─────────────────────────────────────────────────────────────────────┐
│ Edit Workflow: Invoice Processing                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ [Input]  [Steps]  [Output ●]  [Settings]                           │
│                                                                     │
│ ═══════════════════════════════════════════════════════════════════ │
│ WHAT HAPPENS WHEN THIS WORKFLOW COMPLETES?                          │
│ ═══════════════════════════════════════════════════════════════════ │
│                                                                     │
│ Results are always saved to Activity. Configure additional outputs: │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ [✓] SAVE TO FOLDER                                              │ │
│ │                                                                 │ │
│ │     Save results to:                                            │ │
│ │     [Processed Results / Invoices ▼]  [Create New Folder]       │ │
│ │                                                                 │ │
│ │     Filename:                                                   │ │
│ │     [{date}_{workflow_name}_results__________]                  │ │
│ │     Preview: "2026-01-27_invoice_processing_results.csv"        │ │
│ │                                                                 │ │
│ │     Available variables: {date}, {datetime}, {workflow_name},   │ │
│ │     {workflow_id}, {document_count}, {run_id}                   │ │
│ │                                                                 │ │
│ │     Format: [CSV ▼]  (CSV, JSON, Excel, PDF Report)             │ │
│ │                                                                 │ │
│ │     When file exists:                                           │ │
│ │     ● Append new rows to existing file                          │ │
│ │     ○ Create new file with timestamp                            │ │
│ │     ○ Overwrite existing file                                   │ │
│ │                                                                 │ │
│ │     [ ] Auto-delete after [90] days                             │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ [✓] SEND NOTIFICATIONS                                          │ │
│ │                                                                 │ │
│ │     Notification 1:                                             │ │
│ │     ┌───────────────────────────────────────────────────────┐   │ │
│ │     │ Channel: [Email ▼]                                    │   │ │
│ │     │                                                       │   │ │
│ │     │ Recipients:                                           │   │ │
│ │     │ [accounting@company.com, cfo@company.com___]          │   │ │
│ │     │ [✓] Also notify me (workflow owner)                   │   │ │
│ │     │ [ ] Also notify team members                          │   │ │
│ │     │                                                       │   │ │
│ │     │ When to send:                                         │   │ │
│ │     │ ● Always                                              │   │ │
│ │     │ ○ Only on success                                     │   │ │
│ │     │ ○ Only on failure                                     │   │ │
│ │     │ ○ Only when condition met:                            │   │ │
│ │     │   [total_amount] [greater than ▼] [10000]             │   │ │
│ │     │                                                       │   │ │
│ │     │ Include in email:                                     │   │ │
│ │     │ [✓] Summary (docs processed, success/fail count)      │   │ │
│ │     │ [✓] Download link for results                         │   │ │
│ │     │ [ ] Full results table (may be large)                 │   │ │
│ │     │ [✓] Link to view in Vandalizer                        │   │ │
│ │     │                                                       │   │ │
│ │     │                                              [✕]      │   │ │
│ │     └───────────────────────────────────────────────────────┘   │ │
│ │                                                                 │ │
│ │     [+ Add Another Notification]                                │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ [✓] SEND TO WEBHOOK                                             │ │
│ │                                                                 │ │
│ │     Webhook 1:                                                  │ │
│ │     ┌───────────────────────────────────────────────────────┐   │ │
│ │     │ URL: [https://api.erp.company.com/invoices____]       │   │ │
│ │     │ Method: [POST ▼]                                      │   │ │
│ │     │                                                       │   │ │
│ │     │ Authentication: [API Key ▼]                           │   │ │
│ │     │ Header: [X-API-Key_____]  Value: [••••••••] [Show]    │   │ │
│ │     │                                                       │   │ │
│ │     │ Payload template:                                     │   │ │
│ │     │ ┌─────────────────────────────────────────────────┐   │   │ │
│ │     │ │ {                                               │   │   │ │
│ │     │ │   "source": "vandalizer",                       │   │   │ │
│ │     │ │   "workflow": "{{workflow.name}}",              │   │   │ │
│ │     │ │   "completed_at": "{{timestamp}}",              │   │   │ │
│ │     │ │   "invoices": {{results_json}}                  │   │   │ │
│ │     │ │ }                                               │   │   │ │
│ │     │ └─────────────────────────────────────────────────┘   │   │ │
│ │     │                                                       │   │ │
│ │     │ [Test Webhook]                                        │   │ │
│ │     │                                                       │   │ │
│ │     │ On failure: [✓] Retry [3] times                       │   │ │
│ │     │                                              [✕]      │   │ │
│ │     └───────────────────────────────────────────────────────┘   │ │
│ │                                                                 │ │
│ │     [+ Add Another Webhook]                                     │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ [ ] CHAIN TO ANOTHER WORKFLOW                                   │ │
│ │                                                                 │ │
│ │     After this workflow completes, run:                         │ │
│ │     [Select Workflow ▼]                                         │ │
│ │                                                                 │ │
│ │     Trigger when:                                               │ │
│ │     ● Always                                                    │ │
│ │     ○ Only on success                                           │ │
│ │     ○ Only on failure                                           │ │
│ │     ○ Only when condition met: [________________]               │ │
│ │                                                                 │ │
│ │     Pass to next workflow:                                      │ │
│ │     [✓] This workflow's output as context                       │ │
│ │     [✓] Original documents                                      │ │
│ │     [ ] Generated output files                                  │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│                                          [← Back]  [Save Workflow]  │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Email Notification Templates

#### Default Email Template

```
┌─────────────────────────────────────────────────────────────────────┐
│ From: Vandalizer <notifications@vandalizer.example.com>             │
│ To: accounting@company.com                                          │
│ Subject: ✓ Invoice Processing completed (5 documents)               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ [Vandalizer Logo]                                                  │
│                                                                     │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                     │
│ WORKFLOW COMPLETED                                                  │
│                                                                     │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                     │
│ Workflow:    Invoice Processing                                     │
│ Trigger:     Folder watch (Incoming Invoices)                      │
│ Completed:   January 27, 2026 at 2:30 PM (Mountain Time)           │
│ Duration:    45 seconds                                            │
│                                                                     │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                     │
│ SUMMARY                                                             │
│                                                                     │
│ Documents processed:  5                                             │
│ Successful:          5                                             │
│ Failed:              0                                             │
│                                                                     │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                     │
│ RESULTS PREVIEW                                                     │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Document              │ Vendor      │ Amount     │ Date        │ │
│ ├───────────────────────┼─────────────┼────────────┼─────────────┤ │
│ │ invoice_001.pdf       │ Acme Corp   │ $1,234.56  │ 2026-01-15  │ │
│ │ invoice_002.pdf       │ Beta Inc    │ $567.89    │ 2026-01-20  │ │
│ │ invoice_003.pdf       │ Gamma LLC   │ $8,901.22  │ 2026-01-22  │ │
│ │ invoice_004.pdf       │ Delta Co    │ $2,345.00  │ 2026-01-24  │ │
│ │ invoice_005.pdf       │ Epsilon Ltd │ $2,384.00  │ 2026-01-26  │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ Total: $15,432.67                                                  │
│                                                                     │
│              [Download Results (CSV)]  [View in Vandalizer]         │
│                                                                     │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                     │
│ You received this because you're subscribed to notifications for    │
│ the "Invoice Processing" workflow.                                  │
│                                                                     │
│ [Manage Notification Preferences] [Unsubscribe from this workflow] │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### Failure Email Template

```
┌─────────────────────────────────────────────────────────────────────┐
│ From: Vandalizer <notifications@vandalizer.example.com>             │
│ To: accounting@company.com                                          │
│ Subject: ⚠️ Invoice Processing failed (2 of 5 documents)            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ [Vandalizer Logo]                                                  │
│                                                                     │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                     │
│ ⚠️ WORKFLOW COMPLETED WITH ERRORS                                   │
│                                                                     │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                     │
│ SUMMARY                                                             │
│                                                                     │
│ Documents processed:  5                                             │
│ Successful:          3                                             │
│ Failed:              2                                             │
│                                                                     │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                     │
│ FAILURES                                                            │
│                                                                     │
│ ✗ invoice_004.pdf                                                  │
│   Error: Could not extract text - file appears to be corrupted     │
│                                                                     │
│ ✗ invoice_005.pdf                                                  │
│   Error: Rate limit exceeded - will retry automatically            │
│   Next retry: January 27, 2026 at 3:00 PM                          │
│                                                                     │
│                           [View Details]  [Retry Failed Documents]  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.3 Webhook Payload Templates

#### Available Template Variables

```
Workflow context:
{{workflow.id}}           - Workflow ID
{{workflow.name}}         - Workflow name
{{workflow.description}}  - Workflow description

Run context:
{{run.id}}                - This run's unique ID
{{run.status}}            - "completed" | "failed" | "partial"
{{run.trigger_type}}      - "manual" | "folder_watch" | "schedule" | "api"
{{run.started_at}}        - ISO timestamp
{{run.completed_at}}      - ISO timestamp
{{run.duration_ms}}       - Duration in milliseconds

Document context:
{{document_count}}        - Number of documents processed
{{documents}}             - Array of document objects
{{documents[0].name}}     - First document's name
{{documents[0].id}}       - First document's ID

Results:
{{results}}               - Array of result objects
{{results_json}}          - Results as JSON string
{{results_csv}}           - Results as CSV string

Aggregations (if configured):
{{totals.amount}}         - Sum of 'amount' field
{{averages.score}}        - Average of 'score' field
{{counts.high_risk}}      - Count where high_risk=true
```

#### Example Webhook Payloads

**Simple Payload:**
```json
{
  "source": "vandalizer",
  "workflow_id": "{{workflow.id}}",
  "workflow_name": "{{workflow.name}}",
  "status": "{{run.status}}",
  "completed_at": "{{run.completed_at}}",
  "document_count": {{document_count}},
  "results": {{results_json}}
}
```

**ERP Integration Payload:**
```json
{
  "transaction_type": "invoice_import",
  "batch_id": "vnd_{{run.id}}",
  "source_system": "vandalizer",
  "invoices": [
    {{#each results}}
    {
      "vendor_code": "{{vendor_name}}",
      "invoice_number": "{{invoice_number}}",
      "invoice_date": "{{invoice_date}}",
      "amount": {{amount}},
      "currency": "USD",
      "source_document": "{{document.name}}",
      "vandalizer_doc_id": "{{document.id}}"
    }{{#unless @last}},{{/unless}}
    {{/each}}
  ],
  "metadata": {
    "processed_at": "{{run.completed_at}}",
    "workflow_run_id": "{{run.id}}"
  }
}
```

### 2.4 Workflow Chaining

#### What It Does
Allows one workflow's completion to trigger another workflow, passing context and documents.

#### Chain Configuration

```
┌─────────────────────────────────────────────────────────────────────┐
│ CHAIN TO ANOTHER WORKFLOW                                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Chain 1:                                                            │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │                                                                 │ │
│ │ After "Invoice Processing" completes, run:                      │ │
│ │ [Invoice Approval Routing ▼]                                    │ │
│ │                                                                 │ │
│ │ Trigger when:                                                   │ │
│ │ ○ Always run the next workflow                                  │ │
│ │ ● Only on success                                               │ │
│ │ ○ Only on failure (for error handling workflows)                │ │
│ │ ○ Only when condition is met:                                   │ │
│ │   ┌─────────────────────────────────────────────────────────┐   │ │
│ │   │ Any result has [amount] [greater than ▼] [5000]         │   │ │
│ │   │ [+ Add Condition]                                       │   │ │
│ │   └─────────────────────────────────────────────────────────┘   │ │
│ │                                                                 │ │
│ │ What to pass to the next workflow:                              │ │
│ │ [✓] This workflow's output (as input context)                   │ │
│ │     The next workflow can access {{previous.results}}           │ │
│ │ [✓] Original documents                                          │ │
│ │     Same documents will be processed by next workflow           │ │
│ │ [ ] Only documents that matched condition                       │ │
│ │     Only invoices > $5000 will be passed                        │ │
│ │ [ ] Generated output files                                      │ │
│ │     CSV/Excel files become input documents                      │ │
│ │                                                                 │ │
│ │                                                        [✕]      │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ [+ Add Another Chain]                                               │
│                                                                     │
│ ─────────────────────────────────────────────────────────────────── │
│                                                                     │
│ Chain visualization:                                                │
│                                                                     │
│   ┌─────────────────┐     ┌─────────────────────┐                  │
│   │    Invoice      │────►│  Invoice Approval   │                  │
│   │   Processing    │     │     Routing         │                  │
│   └─────────────────┘     └──────────┬──────────┘                  │
│                                      │                              │
│                           ┌──────────┴──────────┐                  │
│                           ▼                     ▼                  │
│                    amount > 10000          amount <= 10000         │
│                           │                     │                  │
│                           ▼                     ▼                  │
│              ┌─────────────────┐    ┌─────────────────┐            │
│              │   CFO Review    │    │  Auto-Approve   │            │
│              │    Workflow     │    │    Workflow     │            │
│              └─────────────────┘    └─────────────────┘            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### Chain Execution Flow

```
Workflow A completes
        │
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Check chain configurations                                           │
│ Found: Chain to Workflow B when amount > 5000                        │
└──────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Evaluate condition: Any result has amount > 5000?                    │
│ Results: [$1234, $567, $8901, $2345, $2384]                         │
│ Match: $8901 > $5000 ✓                                              │
└──────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Prepare context for Workflow B:                                      │
│ - previous_workflow: "Invoice Processing"                            │
│ - previous_results: [full results array]                             │
│ - documents: [original 5 documents]                                  │
│ - chain_condition_matches: [invoice_003.pdf with $8901]             │
└──────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Queue Workflow B execution:                                          │
│ - trigger_type: "chain"                                              │
│ - parent_run_id: [Workflow A's run ID]                              │
│ - is_passive: true                                                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Phase 3: Settings Tab - Resource Controls

### 3.1 Settings Configuration UI

The fourth tab in the workflow builder handles resource limits and operational settings:

```
┌─────────────────────────────────────────────────────────────────────┐
│ Edit Workflow: Invoice Processing                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ [Input]  [Steps]  [Output]  [Settings ●]                           │
│                                                                     │
│ ═══════════════════════════════════════════════════════════════════ │
│ BUDGET & LIMITS                                                     │
│ ═══════════════════════════════════════════════════════════════════ │
│                                                                     │
│ Token Limits (for passive runs):                                    │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Daily limit:   [100,000] tokens    [ ] No limit                 │ │
│ │ Monthly limit: [2,000,000] tokens  [ ] No limit                 │ │
│ │                                                                 │ │
│ │ Current usage:                                                  │ │
│ │ Today:      ████████░░░░░░░░░░░░  45,000 / 100,000 (45%)       │ │
│ │ This month: ██████░░░░░░░░░░░░░░  650,000 / 2,000,000 (32.5%)  │ │
│ │                                                                 │ │
│ │ When limit reached:                                             │ │
│ │ ● Pause workflow until next period                              │ │
│ │ ○ Continue running (no notifications)                           │ │
│ │ ○ Queue documents for next period                               │ │
│ │                                                                 │ │
│ │ [✓] Alert me when usage reaches [80]%                           │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ Document Limits:                                                    │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Max documents per day: [500]        [ ] No limit                │ │
│ │ Max documents per run: [50]         [ ] No limit                │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ═══════════════════════════════════════════════════════════════════ │
│ THROTTLING                                                          │
│ ═══════════════════════════════════════════════════════════════════ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Max concurrent runs: [3]                                        │ │
│ │ (How many instances of this workflow can run simultaneously)    │ │
│ │                                                                 │ │
│ │ Min delay between runs: [60] seconds                            │ │
│ │ (Prevents rapid-fire triggering from folder watch)              │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ═══════════════════════════════════════════════════════════════════ │
│ ERROR HANDLING                                                      │
│ ═══════════════════════════════════════════════════════════════════ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ On failure:                                                     │ │
│ │ [✓] Retry up to [3] times                                       │ │
│ │     Wait [5] minutes between retries                            │ │
│ │     Retry on: [✓] Rate limits  [✓] Timeouts  [ ] All errors    │ │
│ │                                                                 │ │
│ │ After all retries exhausted:                                    │ │
│ │ ● Mark as failed, notify owner                                  │ │
│ │ ○ Mark as failed, no notification                               │ │
│ │ ○ Queue for manual review                                       │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ═══════════════════════════════════════════════════════════════════ │
│ HUMAN APPROVAL (Optional)                                           │
│ ═══════════════════════════════════════════════════════════════════ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ [ ] Require approval before outputs are delivered               │ │
│ │                                                                 │ │
│ │     Approvers: [Select team members...]                         │ │
│ │                                                                 │ │
│ │     When approval needed:                                       │ │
│ │     ○ Always require approval                                   │ │
│ │     ○ Only when condition met: [________________]               │ │
│ │                                                                 │ │
│ │     If no response in [24] hours:                               │ │
│ │     ● Auto-reject and notify                                    │ │
│ │     ○ Auto-approve and notify                                   │ │
│ │     ○ Escalate to: [_____________]                              │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ═══════════════════════════════════════════════════════════════════ │
│ ESTIMATED COSTS                                                     │
│ ═══════════════════════════════════════════════════════════════════ │
│                                                                     │
│ Based on recent usage patterns:                                     │
│ • Average tokens per document: 2,500                               │
│ • Average documents per day: 18                                    │
│ • Estimated daily cost: $4.50                                      │
│ • Estimated monthly cost: $135.00                                  │
│ • At budget limit: $200.00/month maximum                           │
│                                                                     │
│                                          [← Back]  [Save Workflow]  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Phase 4: Workflow Trigger Events & Execution

### 4.1 New Model: WorkflowTriggerEvent

Tracks pending and completed triggers for passive workflow execution:

```
Collection: workflow_trigger_events

Fields:
├── _id: ObjectId
├── uuid: String (unique)
│
├── workflow: Reference → Workflow
├── trigger_type: Enum
│   ├── "manual" - User clicked Run
│   ├── "folder_watch" - Document arrived in watched folder
│   ├── "schedule" - Scheduled execution
│   ├── "api" - API trigger
│   └── "chain" - Triggered by another workflow
│
├── status: Enum
│   ├── "pending" - Waiting to execute (e.g., delay period)
│   ├── "queued" - Ready to execute, in Celery queue
│   ├── "running" - Currently executing
│   ├── "completed" - Finished successfully
│   ├── "partial" - Some documents succeeded, some failed
│   ├── "failed" - All documents failed
│   ├── "skipped" - Cancelled or conditions not met
│   └── "pending_approval" - Waiting for human approval
│
├── documents: Array of References → SmartDocument
├── document_count: Integer
│
├── trigger_context: Object
│   ├── folder: Reference → SmartFolder (if folder_watch)
│   ├── schedule_name: String (if schedule)
│   ├── api_key_id: String (if api)
│   ├── parent_workflow_run: Reference → WorkflowResult (if chain)
│   ├── chain_condition: String (if chain)
│   └── metadata: Object (arbitrary data from API trigger)
│
├── timing: Object
│   ├── created_at: DateTime
│   ├── process_after: DateTime (for delayed triggers)
│   ├── queued_at: DateTime
│   ├── started_at: DateTime
│   ├── completed_at: DateTime
│   └── duration_ms: Integer
│
├── result: Object
│   ├── workflow_result: Reference → WorkflowResult
│   ├── activity_event: Reference → ActivityEvent
│   ├── documents_succeeded: Integer
│   ├── documents_failed: Integer
│   ├── tokens_used: Integer
│   └── error: String (if failed)
│
├── retry: Object
│   ├── attempt_number: Integer
│   ├── max_attempts: Integer
│   ├── next_retry_at: DateTime
│   └── retry_errors: Array of Strings
│
├── approval: Object (if requires approval)
│   ├── status: Enum ("pending", "approved", "rejected")
│   ├── requested_at: DateTime
│   ├── decided_at: DateTime
│   ├── decided_by: String (user_id)
│   └── comment: String
│
└── output_delivery: Object
    ├── storage_status: Enum ("pending", "completed", "failed")
    ├── storage_path: String
    ├── notifications_sent: Array of { channel, recipient, sent_at, status }
    ├── webhooks_called: Array of { url, status, response_code, sent_at }
    └── chains_triggered: Array of { workflow_id, trigger_event_id }
```

### 4.2 Enhanced WorkflowResult Model

```
WorkflowResult (enhanced):

Existing fields remain...

New fields:
├── trigger_event: Reference → WorkflowTriggerEvent
├── trigger_type: Enum (denormalized for queries)
├── is_passive: Boolean (true if not manual)
│
├── input_context: Object
│   ├── parent_workflow_output: Object (if chained)
│   ├── api_metadata: Object (if API triggered)
│   └── schedule_context: Object (if scheduled)
│
└── output_delivery_status: Object
    ├── storage: Enum ("pending", "completed", "failed", "skipped")
    ├── notifications: Enum
    ├── webhooks: Enum
    └── chains: Enum
```

### 4.3 Execution Flow - Folder Watch

```
┌──────────────────────────────────────────────────────────────────────┐
│                     FOLDER WATCH EXECUTION FLOW                       │
└──────────────────────────────────────────────────────────────────────┘

User uploads document to "Incoming Invoices"
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ FILES UPLOAD ENDPOINT (enhanced)                                     │
│ POST /files/upload                                                   │
├──────────────────────────────────────────────────────────────────────┤
│ 1. Save document (existing behavior)                                 │
│ 2. NEW: Check if folder has any watching workflows                   │
│    Query: Workflow.objects(                                          │
│      input_config__folder_watch__enabled=True,                       │
│      input_config__folder_watch__folders=folder                      │
│    )                                                                 │
│ 3. For each watching workflow:                                       │
│    Create WorkflowTriggerEvent with:                                 │
│    - status: "pending"                                               │
│    - process_after: now + delay_seconds                              │
│    - documents: [uploaded_document]                                  │
└──────────────────────────────────────────────────────────────────────┘
                    │
                    │ (Celery Beat task runs every minute)
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ PROCESS PENDING TRIGGERS TASK                                        │
│ process_pending_workflow_triggers()                                  │
├──────────────────────────────────────────────────────────────────────┤
│ 1. Find events where:                                                │
│    - status == "pending"                                             │
│    - process_after <= now                                            │
│                                                                      │
│ 2. For each event:                                                   │
│    a. Load workflow                                                  │
│    b. Check if workflow still enabled                                │
│    c. Apply file filters (type, size, name)                          │
│    d. Apply conditions                                               │
│    e. Check budget limits                                            │
│    f. Check throttling (concurrent runs, min delay)                  │
│    g. If batch_mode == "collect_batch":                              │
│       - Find other pending events for same workflow                  │
│       - Combine documents into single event                          │
│    h. Update status to "queued"                                      │
│    i. Queue Celery task: execute_workflow_passive()                  │
└──────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ EXECUTE WORKFLOW PASSIVE TASK                                        │
│ execute_workflow_passive(trigger_event_id)                           │
├──────────────────────────────────────────────────────────────────────┤
│ 1. Load trigger event and workflow                                   │
│ 2. Update event status to "running"                                  │
│ 3. Create WorkflowResult with:                                       │
│    - is_passive: True                                                │
│    - trigger_event: event                                            │
│    - trigger_type: event.trigger_type                                │
│ 4. Execute workflow steps (EXISTING LOGIC - unchanged)               │
│ 5. On completion:                                                    │
│    - Update WorkflowResult status                                    │
│    - Update trigger event status                                     │
│    - Update workflow stats                                           │
│    - Record tokens used                                              │
│ 6. Process outputs (next section)                                    │
└──────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ PROCESS WORKFLOW OUTPUTS                                             │
│ process_workflow_outputs(workflow_result_id)                         │
├──────────────────────────────────────────────────────────────────────┤
│ Load workflow.output_config                                          │
│                                                                      │
│ 1. STORAGE (if enabled):                                             │
│    - Format results (CSV/JSON/Excel/PDF)                             │
│    - Apply filename template                                         │
│    - Save to destination folder (append or create)                   │
│    - Record in trigger_event.output_delivery.storage_path            │
│                                                                      │
│ 2. NOTIFICATIONS (for each notification):                            │
│    - Check condition (always/success/failure/conditional)            │
│    - Render email template with results                              │
│    - Send via Flask-Mail                                             │
│    - Record in trigger_event.output_delivery.notifications_sent      │
│                                                                      │
│ 3. WEBHOOKS (for each webhook):                                      │
│    - Render payload template                                         │
│    - Send HTTP request                                               │
│    - If failed, queue retry                                          │
│    - Record in trigger_event.output_delivery.webhooks_called         │
│                                                                      │
│ 4. CHAINS (for each chain):                                          │
│    - Evaluate condition                                              │
│    - If met, create new WorkflowTriggerEvent for chained workflow    │
│    - Record in trigger_event.output_delivery.chains_triggered        │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.4 Execution Flow - Schedule

```
┌──────────────────────────────────────────────────────────────────────┐
│                      SCHEDULE EXECUTION FLOW                          │
└──────────────────────────────────────────────────────────────────────┘

Celery Beat fires scheduled task
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ CHECK SCHEDULED WORKFLOWS TASK                                       │
│ check_scheduled_workflows()                                          │
│ (Runs every minute via Celery Beat)                                  │
├──────────────────────────────────────────────────────────────────────┤
│ 1. Find workflows where:                                             │
│    - input_config.schedule.enabled == True                           │
│    - Next scheduled time <= now                                      │
│                                                                      │
│ 2. For each workflow:                                                │
│    a. Determine documents to process based on document_source:       │
│       - "watched_folders": New docs since last run in watched folders│
│       - "specific_folder": All docs in configured folder             │
│       - "query": Execute configured query                            │
│                                                                      │
│    b. Create WorkflowTriggerEvent:                                   │
│       - trigger_type: "schedule"                                     │
│       - status: "queued"                                             │
│       - documents: [found documents]                                 │
│                                                                      │
│    c. Queue execution task                                           │
│                                                                      │
│    d. Calculate and store next_scheduled_run_at                      │
└──────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
            (Same execution flow as folder watch)
```

---

## Phase 5: UI Enhancements

### 5.1 Workflow List - Passive Indicators

The existing workflow list shows which workflows have passive triggers enabled:

```
┌─────────────────────────────────────────────────────────────────────┐
│ Workflows                                          [+ New Workflow] │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Invoice Processing                                    ⚡ 🕐     │ │
│ │ Extracts vendor, amount, date from invoices                     │ │
│ │ 3 steps • Last run: 5 min ago • Today: 47 docs                 │ │
│ │ ⚡ Watching: Incoming Invoices                                  │ │
│ │ 🕐 Schedule: Daily at 6 AM                                      │ │
│ │                                    [Run] [Edit] [Pause] [...]   │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Contract Review                                       ⚡         │ │
│ │ Analyzes contracts for risk factors                             │ │
│ │ 5 steps • Last run: 2 hours ago • Today: 3 docs                │ │
│ │ ⚡ Watching: Pending Contracts                                  │ │
│ │                                    [Run] [Edit] [Pause] [...]   │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Weekly Summary Report                                 🕐         │ │
│ │ Generates weekly summary of all processed documents             │ │
│ │ 2 steps • Last run: 5 days ago • Next: Monday 6 AM             │ │
│ │ 🕐 Schedule: Every Monday at 6 AM                               │ │
│ │                                    [Run] [Edit] [Pause] [...]   │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Ad-hoc Analysis                                                  │ │
│ │ General document analysis workflow                              │ │
│ │ 4 steps • Last run: 1 week ago • Manual only                   │ │
│ │                                           [Run] [Edit] [...]   │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ Legend: ⚡ Folder watch enabled  🕐 Schedule enabled                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 Automation Dashboard

A new section showing all passive workflow activity:

```
┌─────────────────────────────────────────────────────────────────────┐
│ ☰ Vandalizer                                    [Team ▼] [User ▼]  │
├────────┬────────────────────────────────────────────────────────────┤
│        │                                                            │
│  Home  │  AUTOMATION                                                │
│        │  ════════════════════════════════════════════════════════  │
│ Spaces │                                                            │
│        │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│Library │  │ PASSIVE     │ │ TODAY       │ │ THIS MONTH  │          │
│        │  │ WORKFLOWS   │ │             │ │             │          │
│Work-   │  │     8       │ │  127 runs   │ │ 2,847 docs  │          │
│flows   │  │             │ │  3 pending  │ │ 89,432 tkns │          │
│        │  │ [Manage]    │ │ [View All]  │ │ [$89.43]    │          │
│────────│  └─────────────┘ └─────────────┘ └─────────────┘          │
│        │                                                            │
│  AUTO  │  RECENT PASSIVE RUNS                          [View All →] │
│MATION ←│  ─────────────────────────────────────────────────────────  │
│        │                                                            │
│────────│  ✓ Invoice Processing      12 docs   5 min ago   [View]   │
│        │    ⚡ Folder watch trigger                                  │
│Activity│                                                            │
│        │  ✓ Contract Review          1 doc   15 min ago   [View]   │
│ Admin  │    ⚡ Folder watch trigger                                  │
│        │                                                            │
│        │  ⟳ Weekly Summary          running   started 2m  [View]   │
│        │    🕐 Scheduled trigger                                     │
│        │                                                            │
│        │  ✗ Email Processing        failed   30 min ago   [Retry]  │
│        │    ⚡ Error: Rate limit exceeded (retry 2/3)               │
│        │                                                            │
│        │  WATCHED FOLDERS                                           │
│        │  ─────────────────────────────────────────────────────────  │
│        │                                                            │
│        │  📁 Incoming Invoices           47 docs today              │
│        │     → Invoice Processing workflow                          │
│        │                                                            │
│        │  📁 Pending Contracts            3 docs today              │
│        │     → Contract Review workflow                             │
│        │                                                            │
│        │  📁 Email Attachments           12 docs today              │
│        │     → Email Processing workflow                            │
│        │                                                            │
│        │  UPCOMING SCHEDULED RUNS                                   │
│        │  ─────────────────────────────────────────────────────────  │
│        │                                                            │
│        │  🕐 Daily Report             Tomorrow 6:00 AM              │
│        │  🕐 Weekly Summary           Monday 6:00 AM                │
│        │  🕐 Monthly Audit            Feb 1 9:00 AM                 │
│        │                                                            │
└────────┴────────────────────────────────────────────────────────────┘
```

### 5.3 Enhanced Activity Stream

Activity stream now shows trigger type and links to workflow configuration:

```
┌─────────────────────────────────────────────────────────────────────┐
│ Activity                                     [Filter: All ▼]        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Filters: [All] [Manual] [Passive] [Workflows] [Extractions]        │
│                                                                     │
│ ─────────────────────────────────────────────────────────────────── │
│                                                                     │
│ 🤖 Invoice Processing                              5 minutes ago   │
│    ⚡ Folder watch • 12 documents • Completed                       │
│    Triggered by: invoice_batch_jan27.pdf arriving in Incoming...   │
│    [View Results] [View Workflow]                                   │
│                                                                     │
│ ─────────────────────────────────────────────────────────────────── │
│                                                                     │
│ 👤 Ad-hoc Analysis                                15 minutes ago   │
│    Manual run • 3 documents • Completed                            │
│    [View Results]                                                   │
│                                                                     │
│ ─────────────────────────────────────────────────────────────────── │
│                                                                     │
│ 🤖 Weekly Summary Report                               6:00 AM     │
│    🕐 Scheduled • 234 documents • Completed                         │
│    Output: weekly_summary_2026-01-27.pdf saved to Reports          │
│    Notifications: 3 emails sent                                    │
│    [View Results] [Download Report] [View Workflow]                 │
│                                                                     │
│ ─────────────────────────────────────────────────────────────────── │
│                                                                     │
│ 🤖 Invoice Processing → Invoice Approval               5:45 AM     │
│    🔗 Chained • 5 documents • Pending Approval                      │
│    Waiting for approval from: cfo@company.com                      │
│    [View Results] [Approve] [Reject]                                │
│                                                                     │
│ ─────────────────────────────────────────────────────────────────── │
│                                                                     │
│ 🤖 Email Processing                                30 min ago      │
│    ⚡ Folder watch • 2 documents • ✗ Failed                         │
│    Error: Rate limit exceeded                                      │
│    Retry 2/3 scheduled for: 3:30 PM                                │
│    [View Details] [Retry Now] [Skip]                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

Legend:
🤖 = Passive (automatic trigger)
👤 = Manual (user triggered)
⚡ = Folder watch
🕐 = Schedule
🔗 = Chained from another workflow
```

---

## Phase 6: Celery Beat Infrastructure

### 6.1 Celery Configuration Changes

```python
# app/__init__.py - Enhanced Celery configuration

celery = Celery(app.name)
celery.conf.update(
    broker_url='redis://localhost:6379/0',
    result_backend='redis://localhost:6379/1',

    # Existing queues
    task_routes={
        'tasks.documents.*': {'queue': 'documents'},
        'tasks.workflow.*': {'queue': 'workflows'},
        'tasks.upload.*': {'queue': 'uploads'},
        # NEW: Passive processing queue
        'tasks.passive.*': {'queue': 'passive'},
    },

    # NEW: Beat schedule for passive processing
    beat_schedule={
        'process-pending-triggers': {
            'task': 'tasks.passive.process_pending_triggers',
            'schedule': 60.0,  # Every minute
        },
        'check-scheduled-workflows': {
            'task': 'tasks.passive.check_scheduled_workflows',
            'schedule': 60.0,  # Every minute
        },
        'process-webhook-retries': {
            'task': 'tasks.passive.process_webhook_retries',
            'schedule': 300.0,  # Every 5 minutes
        },
        'cleanup-old-trigger-events': {
            'task': 'tasks.passive.cleanup_old_trigger_events',
            'schedule': 86400.0,  # Daily
        },
    },

    # Beat scheduler using database
    beat_scheduler='celery.beat:PersistentScheduler',
    beat_schedule_filename='/var/lib/celery/beat-schedule',

    # Worker settings for passive queue
    worker_prefetch_multiplier=1,  # Fair distribution
    task_acks_late=True,  # Reliability
)
```

### 6.2 Passive Processing Tasks

```python
# app/tasks/passive.py

@celery.task
def process_pending_triggers():
    """
    Process WorkflowTriggerEvents that are ready to execute.
    Runs every minute via Celery Beat.
    """
    now = datetime.utcnow()

    pending_events = WorkflowTriggerEvent.objects(
        status="pending",
        process_after__lte=now
    ).limit(100)  # Batch size

    for event in pending_events:
        try:
            workflow = event.workflow

            # Skip if workflow disabled or deleted
            if not workflow or not workflow.input_config:
                event.status = "skipped"
                event.save()
                continue

            # Apply file filters
            filtered_docs = apply_file_filters(
                event.documents,
                workflow.input_config.folder_watch.file_filters
            )

            if not filtered_docs:
                event.status = "skipped"
                event.result = {"reason": "no_matching_documents"}
                event.save()
                continue

            # Check conditions
            if not evaluate_conditions(
                filtered_docs,
                workflow.input_config.conditions
            ):
                event.status = "skipped"
                event.result = {"reason": "conditions_not_met"}
                event.save()
                continue

            # Check budget
            budget_check = check_workflow_budget(workflow)
            if not budget_check.allowed:
                if workflow.resource_config.budget.on_limit_reached == "pause":
                    # Don't process, will retry next period
                    continue
                elif workflow.resource_config.budget.on_limit_reached == "queue":
                    # Queue for next period
                    event.process_after = get_next_budget_period_start(workflow)
                    event.save()
                    continue

            # Check throttling
            if not check_throttling(workflow):
                # Will retry next minute
                continue

            # Handle batch mode
            if workflow.input_config.folder_watch.batch_mode == "collect_batch":
                event = collect_batch_events(workflow, event)

            # Queue execution
            event.status = "queued"
            event.timing.queued_at = now
            event.documents = filtered_docs
            event.save()

            execute_workflow_passive.delay(str(event.id))

        except Exception as e:
            event.status = "failed"
            event.result = {"error": str(e)}
            event.save()


@celery.task
def check_scheduled_workflows():
    """
    Find workflows with schedules due to run.
    Runs every minute via Celery Beat.
    """
    now = datetime.utcnow()

    # Find workflows with enabled schedules
    workflows = Workflow.objects(
        input_config__schedule__enabled=True
    )

    for workflow in workflows:
        schedule = workflow.input_config.schedule

        # Check if schedule is due
        if not is_schedule_due(schedule, workflow.stats.last_passive_run_at):
            continue

        # Determine documents to process
        documents = get_scheduled_documents(workflow, schedule)

        if not documents and schedule.document_source != "none":
            # No documents to process, skip but update next run
            workflow.stats.next_scheduled_run_at = calculate_next_run(schedule)
            workflow.save()
            continue

        # Create trigger event
        event = WorkflowTriggerEvent(
            workflow=workflow,
            trigger_type="schedule",
            status="queued",
            documents=documents,
            document_count=len(documents),
            trigger_context={
                "schedule_type": schedule.type,
                "schedule_expression": schedule.cron_expression or f"every {schedule.interval_value} {schedule.interval_unit}"
            },
            timing={
                "created_at": now,
                "queued_at": now
            }
        ).save()

        # Update workflow stats
        workflow.stats.next_scheduled_run_at = calculate_next_run(schedule)
        workflow.save()

        # Queue execution
        execute_workflow_passive.delay(str(event.id))


@celery.task
def execute_workflow_passive(trigger_event_id):
    """
    Execute a workflow for a passive trigger.
    """
    event = WorkflowTriggerEvent.objects(id=trigger_event_id).first()
    if not event:
        return

    workflow = event.workflow
    if not workflow:
        event.status = "failed"
        event.result = {"error": "workflow_not_found"}
        event.save()
        return

    try:
        # Update status
        event.status = "running"
        event.timing.started_at = datetime.utcnow()
        event.save()

        # Create WorkflowResult
        result = WorkflowResult(
            workflow=workflow,
            user_id=workflow.user_id,
            documents=event.documents,
            status="running",
            trigger_event=event,
            trigger_type=event.trigger_type,
            is_passive=True,
            input_context=event.trigger_context
        ).save()

        # Execute workflow steps (existing logic)
        execute_workflow_steps(result)

        # Update on completion
        result.status = "completed"
        result.save()

        event.status = "completed"
        event.timing.completed_at = datetime.utcnow()
        event.timing.duration_ms = (
            event.timing.completed_at - event.timing.started_at
        ).total_seconds() * 1000
        event.result = {
            "workflow_result": result.id,
            "documents_succeeded": len(event.documents),
            "documents_failed": 0
        }
        event.save()

        # Update workflow stats
        update_workflow_stats(workflow, event, result)

        # Process outputs
        process_workflow_outputs.delay(str(result.id))

    except Exception as e:
        # Handle failure
        event.status = "failed"
        event.timing.completed_at = datetime.utcnow()
        event.result = {"error": str(e)}

        # Check retry
        if event.retry.attempt_number < event.retry.max_attempts:
            event.retry.attempt_number += 1
            event.retry.next_retry_at = datetime.utcnow() + timedelta(
                seconds=workflow.resource_config.retry.retry_delay_seconds
            )
            event.retry.retry_errors.append(str(e))
            event.status = "pending"
            event.process_after = event.retry.next_retry_at

        event.save()


@celery.task
def process_workflow_outputs(workflow_result_id):
    """
    Process output configuration after workflow completes.
    """
    result = WorkflowResult.objects(id=workflow_result_id).first()
    if not result:
        return

    workflow = result.workflow
    output_config = workflow.output_config
    event = result.trigger_event

    # 1. Storage
    if output_config.storage and output_config.storage.enabled:
        try:
            output_path = save_results_to_folder(result, output_config.storage)
            if event:
                event.output_delivery.storage_status = "completed"
                event.output_delivery.storage_path = output_path
        except Exception as e:
            if event:
                event.output_delivery.storage_status = "failed"

    # 2. Notifications
    for notification in (output_config.notifications or []):
        try:
            if should_send_notification(result, notification):
                send_workflow_notification(result, notification)
                if event:
                    event.output_delivery.notifications_sent.append({
                        "channel": notification.channel,
                        "recipients": notification.recipients,
                        "sent_at": datetime.utcnow(),
                        "status": "sent"
                    })
        except Exception as e:
            if event:
                event.output_delivery.notifications_sent.append({
                    "channel": notification.channel,
                    "status": "failed",
                    "error": str(e)
                })

    # 3. Webhooks
    for webhook in (output_config.webhooks or []):
        try:
            response = call_webhook(result, webhook)
            if event:
                event.output_delivery.webhooks_called.append({
                    "url": webhook.url,
                    "status": "success",
                    "response_code": response.status_code,
                    "sent_at": datetime.utcnow()
                })
        except Exception as e:
            # Queue for retry
            queue_webhook_retry(result, webhook, str(e))
            if event:
                event.output_delivery.webhooks_called.append({
                    "url": webhook.url,
                    "status": "failed",
                    "error": str(e)
                })

    # 4. Chains
    for chain in (output_config.chain_workflows or []):
        if should_trigger_chain(result, chain):
            chained_event = create_chain_trigger(result, chain)
            if event:
                event.output_delivery.chains_triggered.append({
                    "workflow_id": str(chain.workflow.id),
                    "trigger_event_id": str(chained_event.id)
                })

    if event:
        event.save()
```

---

## Database Schema Summary

### New Collections

| Collection | Purpose |
|------------|---------|
| `workflow_trigger_events` | Tracks all passive trigger events and their execution |
| `webhook_delivery_log` | Detailed log of webhook delivery attempts |

### Modified Collections

| Collection | Changes |
|------------|---------|
| `workflows` | Add: `input_config`, `output_config`, `resource_config`, `stats` |
| `workflow_results` | Add: `trigger_event`, `trigger_type`, `is_passive`, `input_context`, `output_delivery_status` |
| `activity_events` | Add: `trigger_type`, `is_passive`, `trigger_event` (for display) |

---

## Implementation Roadmap

### MVP (4-6 weeks)
1. Add `input_config` and `output_config` to Workflow model
2. Workflow builder UI: Input tab with folder watch
3. Workflow builder UI: Output tab with email notifications
4. `WorkflowTriggerEvent` model
5. Celery Beat setup with `process_pending_triggers` task
6. Folder watch detection in upload endpoint
7. Basic Automation dashboard

### V2: Schedules & Webhooks (3-4 weeks)
1. Schedule configuration in Input tab
2. `check_scheduled_workflows` Celery task
3. Webhook configuration in Output tab
4. Webhook delivery with retry logic
5. Enhanced Activity stream with passive indicators

### V3: Advanced Features (4-5 weeks)
1. Workflow chaining
2. API trigger configuration
3. Resource controls (budget, throttling)
4. Human approval workflow
5. Batch processing modes

### V4: Polish & Enterprise (3-4 weeks)
1. Email notification templates
2. PDF report generation for outputs
3. Advanced condition builder
4. Audit logging
5. Admin queue management

---

## Migration Path

### Existing Workflows

All existing workflows continue to work unchanged:
- `input_config.manual_enabled` defaults to `true`
- No folder watch or schedule by default
- No output configuration by default
- Results only appear in Activity (current behavior)

### Upgrade Path

Users can "upgrade" any existing workflow to passive mode by:
1. Opening the workflow in the builder
2. Going to the new "Input" tab
3. Enabling folder watch or schedule
4. Optionally configuring outputs

No migration scripts needed - new fields are optional with sensible defaults.

---

## Success Criteria

### Adoption
- 50% of active teams have at least one passive workflow within 3 months
- 30% of all workflow runs are passive within 6 months

### Efficiency
- 80% reduction in manual workflow triggering for common use cases
- 90% of watched folder documents processed within 10 minutes

### Reliability
- 99.5% uptime for passive processing
- < 5% of passive runs fail after all retries
- 99% webhook delivery success rate

### User Satisfaction
- Workflow builder remains intuitive (no increase in support tickets)
- Users report time savings in surveys
