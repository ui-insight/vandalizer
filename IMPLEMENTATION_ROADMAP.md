# Vandalizer Browser Automation: Implementation Roadmap

**Analysis Date**: 2026-01-06
**Current System**: Chrome Extension + Flask Backend + MongoDB

---

## Executive Summary

Your current system has a **strong foundation** with many sophisticated features already in place:
- Robust locator stack with fallback strategies
- Real-time WebSocket communication
- LLM-powered smart actions
- Recording infrastructure with persistent state
- Audit trails and screenshots
- Cross-process coordination (Flask ↔ Celery via Redis)

However, to achieve the **"resilient admin automation system"** described in the document, you need to add:
1. **Intent-based recording** (not just raw clicks)
2. **Semantic extraction** (tables, pagination, structured schemas)
3. **Self-healing repair UI** (guided element correction)
4. **Page landmarks & verification** (detect wrong page/logged out states)
5. **Human-in-the-loop primitives** (forms, approvals, picklists)
6. **Branching/loops in workflows** (if/else, for-each)
7. **Safety rails** (destructive action detection, dry-run mode)
8. **Workflow versioning & repair history**

---

## Part 1: Current State Analysis

### ✅ What You Have (Strengths)

#### Browser Extension
- **Locator Stack with Fallback** ([locator-stack.js](chrome-extension/locator-stack.js))
  - Priority-based strategies: `data-testid` → `aria-label` → `role` → `text` → `css` → `xpath`
  - Polling with timeout (5000ms default)
  - Visibility validation
  - Adaptive learning: successful strategies get priority boost ([browser_automation.py:715](app/utilities/browser_automation.py#L715))

- **Recording System** ([recorder.js](chrome-extension/recorder.js))
  - Captures clicks, form inputs, navigation
  - Sensitive data detection (passwords, SSNs) with variable placeholders
  - Persistent state across page navigation (uses `chrome.storage.local`)
  - Real-time step counter

- **Target Picker** ([target-picker.js](chrome-extension/target-picker.js))
  - Interactive element selection
  - Auto-generates prioritized locator stack

- **Smart Actions** ([browser_automation.py:456](app/utilities/browser_automation.py#L456))
  - LLM-driven action planning (GPT-4 integration)
  - Supports: `click`, `fill_form`, `navigate`, `wait_for`, `extract`, `extract_info`
  - Handles navigation mid-execution (recursive re-analysis)

- **Audit Trail** ([browser_automation.py:238](app/utilities/browser_automation.py#L238))
  - Screenshots at action success/failure
  - Event log with timestamps
  - Stored in `/static/uploads/audit_{uuid}.png`

- **WebSocket Communication**
  - Socket.IO real-time bidirectional communication
  - Token-based authentication for extension
  - Cross-process coordination via Redis

#### Backend Workflow System
- **DAG-based Execution** ([workflow.py:100](app/utilities/workflow.py#L100))
  - Topological sort for step ordering
  - Node types: Document, Extraction, Prompt, Format, BrowserAutomation, MultiTask

- **Variable Interpolation** ([browser_automation.py:593](app/utilities/browser_automation.py#L593))
  - Basic template syntax: `{{previous_step.field_name}}`
  - Supports nested dict access

- **Session State Management** ([browser_automation.py:49](app/utilities/browser_automation.py#L49))
  - States: CREATED → CONNECTING → READY_NO_LOGIN → WAITING_FOR_LOGIN → ACTIVE → COMPLETED/FAILED
  - Manual login pause support (`ensure_login` action type)

- **Modal UI** ([workflow_add_browser_automation_modal.html](app/templates/workflows/workflow_steps/workflow_add_browser_automation_modal.html))
  - Record and Manual Build tabs
  - Drag-and-drop action builder
  - Action types: Navigate, Login Pause, Fill Form, Click, Extract, Smart Action, Verify

#### Data Models
- **LocatorStrategy** ([models.py:124](app/models.py#L124))
  - Named, reusable selector bundles
  - `confidence_score`, `last_tested` tracking

- **BrowserActionStep** ([models.py:142](app/models.py#L142))
  - Supports: `navigate`, `click`, `extract`, `assert`, `fill_form`, `wait_for`, `smart_action`
  - Execution options: `timeout_ms`, `retry_count`, `on_failure`, `requires_approval`
  - Output variable binding

---

### ❌ Critical Gaps (What's Missing)

#### Browser Extension: "Robot Hands + Eyes"

1. **Semantic Action Layer During Recording**
   - **Current**: Records raw events (click x,y, type "text")
   - **Needed**: Capture intent ("Click 'Run Report' button", "Set field 'Term' = 2026 Spring")
   - **Why**: Brittle macro vs. intent-based automation

2. **Element Neighborhood & Context**
   - **Current**: Stores selector strategies only
   - **Needed**: Store parent container info, nearby labels, relative selectors ("button near label 'Term'")
   - **Why**: Enables LLM to intelligently repair when UI changes

3. **Page Identity & Landmarks System**
   - **Current**: No page verification
   - **Needed**: Store URL pattern + title + stable landmarks (header text, breadcrumbs) per step
   - **Why**: Prevents "typed student ID into wrong tab" disasters

4. **Table Extraction with Pagination**
   - **Current**: Basic CSS selector extraction
   - **Needed**:
     - Schema-based extraction (headers by meaning, not position)
     - Header synonyms ("ID" = "Student ID" = "SID")
     - Pagination detection ("Next Page" button, "Show 100 rows")
     - Multi-page aggregation
   - **Why**: Core admin use case (extract all students from report)

5. **Document/Report Extraction**
   - **Current**: No download detection
   - **Needed**:
     - Detect CSV/XLSX/PDF downloads
     - Capture filename and file path
     - Scrape HTML tables when downloads unavailable
   - **Why**: Many reports are downloadable files

6. **Extract-by-Example Mode**
   - **Current**: Manual CSS selector definition
   - **Needed**: User highlights 2-3 examples → LLM learns pattern
   - **Why**: Non-technical admins can't write CSS selectors

7. **Variable Binding UI in Extension**
   - **Current**: Variables only work in backend workflow
   - **Needed**:
     - Variable picker UI in extension
     - Expression language (string ops, date formatting, regex)
     - Preview interpolated values during recording
   - **Why**: Templates like "Type {{student_id}} into 'Student ID'"

8. **Frame/Iframe Awareness**
   - **Current**: No frame handling
   - **Needed**: Detect and target elements inside iframes
   - **Why**: University systems use iframes heavily (banner, PeopleSoft)

9. **Logged-Out State Detection**
   - **Current**: Manual login pause only
   - **Needed**:
     - Auto-detect logout (URL patterns, known DOM cues)
     - Pause workflow and notify user
     - Resume after re-auth
   - **Why**: SSO/Duo sessions expire mid-workflow

10. **Self-Healing Repair UI**
    - **Current**: No guided repair when element not found
    - **Needed**:
      - Dim page and prompt: "I couldn't find 'Run Report'. Click the correct button."
      - Capture new fingerprint and patch workflow
      - Show diff of old vs. new selector
    - **Why**: **Highest leverage feature** to prevent abandonment

11. **Protected Actions Firewall**
    - **Current**: Optional `requires_approval` flag
    - **Needed**:
      - Auto-detect destructive actions (keywords: delete, remove, approve, submit, payment)
      - Require confirmation with summary/diff
      - Dry-run mode (simulate without executing)
      - Audit trail overlay: "Robot is about to click Submit on Banner → Confirm"
    - **Why**: Safety for university admins

12. **Step Replay-from-Here**
    - **Current**: All-or-nothing replay
    - **Needed**: Click any step in devtools → replay from that point
    - **Why**: Debugging and iterative refinement

13. **Live Variable Inspector**
    - **Current**: No visibility into variables during execution
    - **Needed**: Devtools panel showing all variables + values in real-time
    - **Why**: Debugging extraction and template issues

14. **Test Extraction UI**
    - **Current**: No extraction preview
    - **Needed**: "Run extraction on current page" button → show JSON output
    - **Why**: Validate schemas before full workflow run

#### Workflow System: "Brain + Orchestration"

15. **Branching & Conditionals**
    - **Current**: Linear DAG execution
    - **Needed**:
      - `if/else` based on extracted values
      - Example: "If enrollment_status == 'Closed', skip notification step"
    - **Why**: Real workflows have decision points

16. **Loops (For-Each)**
    - **Current**: No iteration support
    - **Needed**:
      - `for each row` in extracted table
      - `for each item` in list variable
      - Example: "For each student ID, lookup enrollment, then send email"
    - **Why**: Bulk operations are core admin use case

17. **Compensation Steps (Undo-ish)**
    - **Current**: No rollback support
    - **Needed**: Define "undo" steps that run on failure
    - **Why**: Partially completed workflows leave dirty state

18. **Typed Variables & Schema**
    - **Current**: Variables are untyped `Dict`
    - **Needed**:
      - Types: `string`, `number`, `date`, `list`, `object`, `file`
      - Validation at runtime
      - Auto-conversion (string → date parsing)
    - **Why**: Prevents type errors and enables better UI

19. **Artifact Provenance**
    - **Current**: `steps_output` is flat dict
    - **Needed**: Track "this value came from Banner report X at timestamp Y"
    - **Why**: Auditing and debugging

20. **Connectors (Email, Sheets, Storage)**
    - **Current**: Browser-only automation
    - **Needed**:
      - **Email**: Send via SMTP/Office365/Gmail
      - **Google Sheets**: Read/write cells
      - **S3/Drive**: Upload extracted files
      - **Campus APIs**: REST/SOAP clients
    - **Why**: "Report lookup → email result → update spreadsheet" workflows

21. **Human-in-the-Loop Forms**
    - **Current**: No structured input prompts
    - **Needed**:
      - Multi-field input forms ("Enter term, department, date range")
      - Picklists from extracted data ("Select which John Smith")
      - Approval screens with diffs ("Approve these 12 roster changes")
      - Comment + escalation ("Send to supervisor")
    - **Why**: Admins need to inject data and make decisions

22. **Policy & Access Controls**
    - **Current**: No workflow permissions
    - **Needed**:
      - Workflow permissions by team role
      - Per-workflow allowed domains (only banner.myuni.edu)
      - PII redaction in logs
      - Auto-delete artifacts after N days
    - **Why**: IT/security will kill it without this

23. **Failure Clustering & Analytics**
    - **Current**: Basic audit trail only
    - **Needed**:
      - Group failures by root cause ("Banner login page changed")
      - Suggest fixes based on failure patterns
      - Metrics: time saved, success rate by site
    - **Why**: Identify systemic issues and ROI

24. **Workflow Versioning**
    - **Current**: No version history
    - **Needed**:
      - Every repair creates new version
      - Diff view between versions
      - Rollback to previous version
      - Regression tests ("find Run Report button")
    - **Why**: "Fix for Registrar breaks Finance"

25. **Workflow Templates + Parameterization**
    - **Current**: Workflows are not parameterized
    - **Needed**:
      - Define input parameters (term, department, report type)
      - Input form UI
      - Template library (verified workflows)
    - **Why**: Most admin work is same flow with different inputs

26. **LLM-Assisted Repair & Suggestions**
    - **Current**: Smart actions for execution only
    - **Needed**:
      - Auto-generate robust selectors from DOM
      - Map renamed labels/headers ("Enrollment" → "Student Count")
      - Propose recovery steps ("close modal", "re-login")
      - Label recorded steps ("Run Enrollment Report")
      - Generate extraction schemas from table HTML
    - **Why**: Reduce manual repair effort

---

## Part 2: Priority-Ordered Implementation Roadmap

### Phase 1: Make Recording Replayable in Real World (Weeks 1-4)
**Goal**: Stop workflows from breaking when UI changes

#### 1.1: Element Fingerprinting with Neighborhood Context (COMPLETED)
**Priority**: P0 (Critical)
**Impact**: Foundation for self-healing
**Effort**: Medium (2 weeks)

**Changes**:
- **Extension** ([locator-stack.js](chrome-extension/locator-stack.js)):
  - Add `neighborhood` field to each strategy:
    ```javascript
    {
      type: 'role',
      role: 'button',
      name: 'Run Report',
      neighborhood: {
        container_label: 'Reports Section',
        nearby_labels: ['Term', 'Department'],
        parent_tag: 'div.card'
      },
      priority: 3
    }
    ```
  - Capture during target picker and recording
  - Use for fuzzy matching when exact match fails

- **Backend** ([browser_automation.py](app/utilities/browser_automation.py)):
  - Update `execute_action_with_stack()` to use neighborhood for fallback
  - LLM prompt: "Find button with label 'Run Report' near label 'Term'"

**Acceptance Criteria**:
- [x] Target picker captures parent container and nearby labels
- [x] Locator stack tries neighborhood-based matching after exact fails
- [x] Test: Rename button class, workflow still finds it by neighborhood

---

#### 1.2: Page Landmarks & Precondition Verification (COMPLETED)
**Priority**: P0 (Critical)
**Impact**: Prevents "wrong page" failures
**Effort**: Medium (1.5 weeks)

**Changes**:
- **Data Model** ([models.py:142](app/models.py#L142)):
  ```python
  class BrowserActionStep(me.EmbeddedDocument):
      # Existing fields...

      # NEW: Page verification
      preconditions = me.DictField()  # {
      #   "url_pattern": "/banner/reports",
      #   "title_contains": "Reports Dashboard",
      #   "landmarks": ["Reports", "Run Report", "Export"]
      # }

      expected_outcome = me.DictField()  # {
      #   "type": "download_starts" | "table_appears" | "url_changes",
      #   "value": "/results" | "table.results"
      # }
  ```

- **Extension** ([content-script.js](chrome-extension/content-script.js)):
  - New command: `verify_preconditions`
  - Check URL, title, landmark elements
  - Return `{verified: true/false, missing_landmarks: [...]}`

- **Backend** ([browser_automation.py](app/utilities/browser_automation.py)):
  - Before each step, call `verify_preconditions`
  - If fail, enter recovery mode (check for login page, modal, error)

**Acceptance Criteria**:
- [x] Each step can define preconditions (URL, title, landmarks)
- [x] Workflow pauses if preconditions fail
- [x] Test: Navigate to wrong page → workflow detects and fails gracefully

---

#### 1.3: Self-Healing Repair UI (Guided Element Selection) (SKIPPED)
**Priority**: P0 (Critical)
**Impact**: **Highest leverage** - prevents abandonment
**Effort**: High (3 weeks)

**Changes**:
- **Extension** ([repair-ui.js](chrome-extension/repair-ui.js)) - NEW FILE:
  ```javascript
  class RepairUI {
    async promptUserToFixElement(targetDescription, oldStrategies) {
      // 1. Dim page with overlay
      // 2. Show banner: "I couldn't find '{targetDescription}'. Click the correct element."
      // 3. Enter target picker mode
      // 4. User clicks element
      // 5. Generate new locator stack
      // 6. Show diff: old vs. new strategies
      // 7. User confirms or retries
      // 8. Send new strategies to backend
    }
  }
  ```

- **Backend** ([browser_automation.py](app/utilities/browser_automation.py)):
  - When `execute_action_with_stack()` fails all strategies:
    1. Send `request_repair` command to extension with target description
    2. Wait for user to select correct element
    3. Receive new locator stack
    4. Save as **workflow version patch**
    5. Continue execution with new locator

- **Data Model** ([models.py](app/models.py)):
  ```python
  class WorkflowRepairHistory(me.Document):
      workflow_id = me.StringField(required=True)
      version = me.IntField(required=True)
      repair_date = me.DateTimeField(default=datetime.datetime.now)
      step_id = me.StringField(required=True)
      old_locator = me.DictField()
      new_locator = me.DictField()
      reason = me.StringField()  # "Element not found"
      repaired_by_user_id = me.StringField()
  ```

- **UI** ([workflow_add_browser_automation_modal.html](app/templates/workflows/workflow_steps/workflow_add_browser_automation_modal.html)):
  - Show repair history for each action
  - "Rollback to version X" button

**Acceptance Criteria**:
- [ ] When element not found, extension dims page and prompts user
- [ ] User clicks correct element → new locator saved
- [ ] Workflow version increments automatically
- [ ] Repair history visible in workflow editor
- [ ] Test: Change button ID → workflow fails → user fixes → workflow continues

---

#### 3.3: Protected Actions Firewall (IN PROGRESS)
**Priority**: P1 (High)
**Impact**: Safety for university admins
**Effort**: Medium (2 weeks)

**Changes**:
- **Extension** ([recorder.js](chrome-extension/recorder.js)):
  - Auto-scan clicked elements for destructive keywords ("Delete", "Remove", "Drop Course")
  - Flag step as `destructive: true`
  - Show warning in recorder UI ("Recording destructive action")

- **Backend** ([browser_automation.py](app/utilities/browser_automation.py)):
  - Before executing `destructive` step:
    - Pause workflow
    - Trigger "Approval Request" (email/SMS/UI)
    - Wait for human confirmation
  - Dry-Run Mode: Skip destructive steps, log as "Would have clicked X"

- **UI**:
  - Approval Dashboard: "Robot waiting to Delete 50 records"
  - "Approve" / "Deny" buttons
  - Dry-Run Toggle in execution modal

**Acceptance Criteria**:
- [x] Extension flags destructive actions (Delete, Remove)
- [ ] Workflow pauses on destructive action
- [ ] User must approve to continue
- [ ] Dry-run mode skips destructive actions
- [ ] Test: Record "Delete Student" → Replay → Pauses for approvaluse → resume

---

#### 1.4: Logged-Out State Detection & Auto-Pause (COMPLETED)
**Priority**: P1 (High)
**Impact**: Handles SSO/Duo session expiration
**Effort**: Low (1 week)

**Changes**:
- **Extension** ([content-script.js](chrome-extension/content-script.js)):
  - Auto-detect common logout indicators:
    - URL contains `/login`, `/sso`, `/auth`
    - Page title contains "Sign In", "Login"
    - DOM contains login form elements
  - Send `session_expired` event to backend

- **Backend** ([browser_automation.py:49](app/utilities/browser_automation.py#L49)):
  - Add new state: `WAITING_FOR_REAUTH`
  - On `session_expired` event:
    1. Pause workflow execution
    2. Notify user: "Session expired. Please log in, then click Resume."
    3. Wait for `confirm_login` (existing endpoint)
    4. Resume workflow from paused step

**Acceptance Criteria**:
- [x] Extension detects login page automatically
- [x] Workflow pauses and notifies user
- [x] User logs in and clicks Resume → workflow continues
- [x] Test: SSO timeout mid-workflow → auto-pause → resume

---

#### 1.5: Outcome-Based Execution (No More sleep(2))
**Priority**: P1 (High)
**Impact**: Reliability and speed
**Effort**: Medium (1.5 weeks)

**Changes**:
- **Extension** ([dom-actions.js](chrome-extension/dom-actions.js)):
  - Update `wait_for` command to support:
    ```javascript
    wait_for({
      type: 'element_appears',
      selector: 'table.results',
      timeout_ms: 5000
    })

    wait_for({
      type: 'element_disappears',
      selector: '.spinner',
      timeout_ms: 10000
    })

    wait_for({
      type: 'url_changes',
      pattern: '/results',
      timeout_ms: 5000
    })

    wait_for({
      type: 'download_starts',
      timeout_ms: 5000
    })
    ```

- **Data Model** ([models.py:142](app/models.py#L142)):
  - Use existing `expected_outcome` field from 1.2

- **Backend** ([browser_automation.py](app/utilities/browser_automation.py)):
  - After each action, check `expected_outcome`
  - If outcome not met within timeout → enter recovery mode

**Acceptance Criteria**:
- [ ] Replace all hardcoded delays with outcome checks
- [ ] Support: element appears/disappears, URL change, download, toast message
- [ ] Test: Click "Run Report" → wait for table (not sleep 3 seconds)

---

### Phase 2: Make It Useful (Data In/Out) (Weeks 5-8)
**Goal**: Structured data extraction and variable binding

#### 2.1: Table Extraction with Schema & Pagination (COMPLETED)
**Priority**: P0 (Critical)
**Impact**: Core admin use case
**Effort**: High (3 weeks)

**Changes**:
- **Data Model** ([models.py:142](app/models.py#L142)):
  ```python
  class BrowserActionStep(me.EmbeddedDocument):
      # Existing fields...

      extraction_spec = me.DictField()  # {
      #   "type": "table",
      #   "selector": "table.enrollment-report",
      #   "schema": {
      #     "Student ID": {"synonyms": ["ID", "SID"], "type": "string"},
      #     "Name": {"synonyms": ["Student Name"], "type": "string"},
      #     "Enrollment Status": {"synonyms": ["Status"], "type": "string"}
      #   },
      #   "pagination": {
      #     "enabled": true,
      #     "next_button_selector": "button.next-page",
      #     "max_pages": 10
      #   }
      # }
  ```

- **Extension** ([extractor.js](chrome-extension/extractor.js)):
  - Rewrite table extraction:
    ```javascript
    extractTable(spec) {
      const table = document.querySelector(spec.selector);
      const headers = this.detectHeaders(table);
      const schema = spec.schema || this.autoDetectSchema(headers);

      let allRows = [];
      let page = 1;

      do {
        const rows = this.extractRows(table, schema, headers);
        allRows = allRows.concat(rows);

        if (spec.pagination?.enabled) {
          const nextBtn = document.querySelector(spec.pagination.next_button_selector);
          if (!nextBtn || page >= spec.pagination.max_pages) break;
          nextBtn.click();
          await this.waitForTableRefresh(table);
          page++;
        }
      } while (spec.pagination?.enabled);

      return {
        headers: Object.keys(schema),
        rows: allRows,
        total_rows: allRows.length,
        pages_extracted: page
      };
    }

    mapHeaderToSchema(header, schema) {
      // Match header to schema using exact match or synonyms
      for (const [canonical, config] of Object.entries(schema)) {
        if (header === canonical) return canonical;
        if (config.synonyms?.includes(header)) return canonical;
      }
      return header; // Unmapped
    }
    ```

- **UI** ([workflow_add_browser_automation_modal.html](app/templates/workflows/workflow_steps/workflow_add_browser_automation_modal.html)):
  - New: "Extract Table" action type
  - Table selector input (or target picker)
  - Schema builder:
    - Click "Auto-detect schema" → extract headers from current page
    - For each header: add synonyms, set type
  - Pagination toggle:
    - Next button selector
    - Max pages

**Acceptance Criteria**:
- [x] Extract table by schema (header meanings, not positions)
- [x] Support header synonyms ("Student ID" = "SID")
- [x] Auto-paginate and aggregate rows
- [x] Output: `{headers: [...], rows: [...], total_rows: N}`
- [x] Test: Banner enrollment report with 3 pages → extract all students

---

#### 2.2: Document/Report Extraction (Downloads) (COMPLETED)
**Priority**: P1 (High)
**Impact**: Many reports are downloadable files
**Effort**: Medium (2 weeks)

**Changes**:
- **Extension** ([content-script.js](chrome-extension/content-script.js)):
  - Listen for `chrome.downloads.onCreated` event
  - Capture filename, file path, timestamp
  - Send to backend: `download_detected`

- **Backend** ([browser_automation.py](app/utilities/browser_automation.py)):
  - New action type: `wait_for_download`
  - Store download metadata in session:
    ```python
    session.downloads.append({
      "filename": "enrollment_report.csv",
      "path": "/Users/.../Downloads/enrollment_report.csv",
      "timestamp": "2026-01-06T12:34:56Z"
    })
    ```
  - Parse CSV/XLSX files (use pandas)
  - Store as artifact in `steps_output`

- **Data Model** ([models.py:231](app/models.py#L231)):
  ```python
  class WorkflowArtifact(me.Document):
      workflow_result_id = me.StringField(required=True)
      artifact_type = me.StringField()  # "csv", "xlsx", "pdf"
      filename = me.StringField()
      file_path = me.StringField()
      extracted_data = me.DictField()  # Parsed CSV/XLSX as JSON
      created_at = me.DateTimeField(default=datetime.datetime.now)
  ```

**Acceptance Criteria**:
- [x] Detect CSV/XLSX/PDF downloads
- [x] Parse and store as structured data
- [x] Make available to subsequent steps
- [x] Test: Click "Export" → CSV downloads → parse into JSON

---

#### 2.3: Variable Binding UI in Extension (COMPLETED)
**Priority**: P1 (High)
**Impact**: Enables workflow templates
**Effort**: Medium (2 weeks)

**Changes**:
- **Extension** ([recorder.js](chrome-extension/recorder.js)):
  - When recording, detect form inputs
  - Show popup: "Create variable for this value?"
  - User names variable: `student_id`
  - Record step as: `{type: 'fill_form', locator: {...}, value: '{{student_id}}'}`

- **UI** ([workflow_add_browser_automation_modal.html](app/templates/workflows/workflow_steps/workflow_add_browser_automation_modal.html)):
  - For each action with input, show variable picker dropdown:
    - List: Previous step outputs, workflow inputs
    - Text input: `{{expression}}`
  - Variable preview: "This will be: [actual value]"

- **Backend** (Already implemented in [browser_automation.py:593](app/utilities/browser_automation.py#L593)):
  - Enhance expression language:
    - `{{term.upper()}}` - String methods
    - `{{date.format('YYYY-MM-DD')}}` - Date formatting
    - `{{id.substring(0, 5)}}` - Substring
    - `{{name.replace('Dr.', '')}}` - Replace

**Acceptance Criteria**:
- [x] During recording, prompt to create variables for inputs
- [x] Workflow editor shows variable picker for all input fields (via Extension Overlay)
- [x] Expressions work: `{{student_id.upper()}}`
- [x] Test: Record with variable → replay with different value

---

#### 2.4: Extract-by-Example Mode (LLM-Powered) (COMPLETED)
**Priority**: P2 (Medium)
**Impact**: Non-technical admins can extract data
**Effort**: Medium (2 weeks)

**Changes**:
- **Extension** ([extractor.js](chrome-extension/extractor.js)):
  - New mode: "Extract by Example"
  - User clicks 2-3 examples of data to extract
  - Extension captures:
    - Element paths
    - Text content
    - Parent containers
  - Send to backend LLM: "Generate extraction schema"

- **Backend** (New utility: `llm_extraction_schema_generator.py`):
  - LLM prompt:
    ```
    User selected these elements as examples:
    1. <span class="student-name">John Doe</span>
    2. <span class="student-name">Jane Smith</span>
    3. <span class="student-name">Bob Johnson</span>

    Generate a CSS selector and schema to extract all similar elements.
    Output: {selector: "span.student-name", field_name: "Student Name", type: "string"}
    ```

- **UI**:
  - "Extract by Example" button in workflow builder
  - Opens extension in example mode
  - User clicks 2-3 examples
  - Schema auto-generated and inserted

**Acceptance Criteria**:
- [x] User selects 2-3 examples
- [x] LLM generates extraction schema
- [x] Schema inserted into workflow action
- [x] Test: Select 3 student names → extract all names from page

---

### Phase 3: Make It Scalable (Workflows & Safety) (Weeks 9-12)
**Goal**: Branching, loops, safety rails

#### 3.1: Branching & Conditionals
**Priority**: P1 (High)
**Impact**: Real workflows have decision points
**Effort**: High (3 weeks)

**Changes**:
- **Data Model** ([models.py:186](app/models.py#L186)):
  ```python
  class WorkflowStep(me.Document):
      # Existing fields...

      # NEW: Conditional execution
      condition = me.DictField()  # {
      #   "type": "if",
      #   "expression": "{{enrollment_status}} == 'Closed'",
      #   "then_step_id": "send_notification",
      #   "else_step_id": "skip_notification"
      # }
  ```

- **Workflow Engine** ([workflow.py:100](app/utilities/workflow.py#L100)):
  - Before executing node, evaluate `condition`
  - Support expressions:
    - `{{var}} == 'value'`
    - `{{count}} > 10`
    - `{{status}} in ['Active', 'Pending']`
  - Skip node if condition false, jump to `else_step_id`

- **UI**:
  - Step editor: "Add Condition" button
  - Expression builder:
    - Left: Variable dropdown
    - Operator: `==`, `!=`, `>`, `<`, `in`, `contains`
    - Right: Value input
  - Visual flow diagram showing branches

**Acceptance Criteria**:
- [ ] Steps can have if/else conditions
- [ ] Condition expressions evaluated at runtime
- [ ] Workflow skips steps based on condition
- [ ] Test: If enrollment closed, skip notification step

---

#### 3.2: Loops (For-Each)
**Priority**: P1 (High)
**Impact**: Bulk operations
**Effort**: High (3 weeks)

**Changes**:
- **Data Model** ([models.py:186](app/models.py#L186)):
  ```python
  class WorkflowStep(me.Document):
      # Existing fields...

      # NEW: Loop configuration
      loop = me.DictField()  # {
      #   "enabled": true,
      #   "iterate_over": "{{extracted_students}}",  # List variable
      #   "item_name": "student",  # Loop variable name
      #   "max_iterations": 100
      # }
  ```

- **Workflow Engine** ([workflow.py:100](app/utilities/workflow.py#L100)):
  - Before processing node, check `loop.enabled`
  - If true:
    1. Get list from `loop.iterate_over`
    2. For each item, set `{{loop.item_name}}` variable
    3. Execute node with item context
    4. Aggregate outputs
  - Support nested loops (track loop depth)

- **UI**:
  - Step editor: "Loop over list" toggle
  - Variable dropdown: Select list variable
  - Item name input: Variable name for current item
  - Max iterations safety limit

**Acceptance Criteria**:
- [ ] Steps can loop over list variables
- [ ] Loop item accessible as `{{student}}` in nested steps
- [ ] Outputs aggregated from all iterations
- [ ] Test: Extract 10 students → for each, lookup enrollment → aggregate results

---

#### 3.3: Protected Actions Firewall
**Priority**: P1 (High)
**Impact**: Safety for admins
**Effort**: Medium (2 weeks)

**Changes**:
- **Extension** ([dom-actions.js](chrome-extension/dom-actions.js)):
  - Before executing action, check if element/action is destructive:
    ```javascript
    isDestructive(action, element) {
      const destructiveKeywords = [
        'delete', 'remove', 'drop', 'terminate',
        'approve', 'submit', 'finalize', 'post',
        'payment', 'charge', 'withdraw'
      ];

      const text = element.textContent.toLowerCase();
      const elType = element.type?.toLowerCase();

      // Check button text
      if (destructiveKeywords.some(kw => text.includes(kw))) {
        return {destructive: true, reason: `Button contains '${kw}'`};
      }

      // Check form submit
      if (action.type === 'click' && elType === 'submit') {
        return {destructive: true, reason: 'Form submission'};
      }

      return {destructive: false};
    }
    ```

  - If destructive, send `confirmation_required` to backend
  - Show modal with:
    - Action description
    - Element details (text, type)
    - Screenshot preview
    - "Confirm" / "Cancel" buttons

- **Backend** ([browser_automation.py](app/utilities/browser_automation.py)):
  - On `confirmation_required`, pause execution
  - Notify user via WebSocket
  - Wait for user confirmation
  - Resume or abort

- **Data Model** ([models.py:142](app/models.py#L142)):
  ```python
  class BrowserActionStep(me.EmbeddedDocument):
      # Existing fields...

      safety_level = me.StringField(default="safe")  # "safe", "write", "destructive"
      requires_approval = me.BooleanField(default=False)  # ALREADY EXISTS
      dry_run_mode = me.BooleanField(default=False)  # NEW
  ```

- **UI**:
  - Step editor: Safety level dropdown
  - Workflow settings: "Enable dry-run mode" (simulate, log but don't execute)

**Acceptance Criteria**:
- [ ] Auto-detect destructive actions (delete, submit, approve)
- [ ] Pause workflow and request confirmation
- [ ] Show preview with element details
- [ ] Dry-run mode: log actions without executing
- [ ] Test: Click "Delete Student" → confirmation required

---

#### 3.4: Workflow Versioning & Diff View
**Priority**: P1 (High)
**Impact**: Prevents "fix for X breaks Y"
**Effort**: Medium (2 weeks)

**Changes**:
- **Data Model** ([models.py:211](app/models.py#L211)):
  ```python
  class Workflow(me.Document):
      # Existing fields...

      version = me.IntField(default=1)
      parent_version_id = me.StringField()  # For version history

  class WorkflowVersion(me.Document):
      workflow_id = me.StringField(required=True)
      version_number = me.IntField(required=True)
      created_at = me.DateTimeField(default=datetime.datetime.now)
      created_by = me.StringField()
      change_description = me.StringField()
      steps_snapshot = me.ListField(me.DictField())  # Full step data
      repair_history = me.ListField(me.ReferenceField("WorkflowRepairHistory"))
  ```

- **Backend** ([workflows/routes.py](app/blueprints/workflows/routes.py)):
  - On workflow save, if steps changed:
    1. Create `WorkflowVersion` with snapshot
    2. Increment `workflow.version`
  - New endpoint: `GET /workflows/{id}/versions`
  - New endpoint: `GET /workflows/{id}/diff/{v1}/{v2}`

- **UI**:
  - Workflow editor: "Version History" button
  - List all versions with change descriptions
  - Diff view: side-by-side step comparison
  - "Rollback to version X" button

**Acceptance Criteria**:
- [ ] Every workflow save creates version
- [ ] Version history accessible from editor
- [ ] Diff view shows step-by-step changes
- [ ] Rollback to previous version
- [ ] Test: Edit workflow 3 times → 3 versions → rollback to v2

---

### Phase 4: Make It Enterprise-Ready (Weeks 13-16)
**Goal**: Connectors, human-in-the-loop, policy controls

#### 4.1: Human-in-the-Loop Forms & Approvals
**Priority**: P1 (High)
**Impact**: Admins need to inject data and approve changes
**Effort**: High (3 weeks)

**Changes**:
- **Data Model** ([models.py:142](app/models.py#L142)):
  ```python
  class BrowserActionStep(me.EmbeddedDocument):
      # Existing fields...

      # NEW: Human input prompt
      human_input = me.DictField()  # {
      #   "type": "form" | "approval" | "picklist",
      #   "prompt": "Enter term and department",
      #   "fields": [
      #     {"name": "term", "type": "text", "label": "Term"},
      #     {"name": "dept", "type": "dropdown", "options": ["CS", "MATH"]}
      #   ],
      #   "approval_type": "changes",  # For approval
      #   "changes_preview": "{{extracted_changes}}"  # Variable with changes
      # }
  ```

- **Backend** ([browser_automation.py](app/utilities/browser_automation.py)):
  - New action type: `request_human_input`
  - Pause workflow and send form/approval UI to frontend
  - Wait for user response
  - Store response in workflow variables

- **UI** (New: `human_input_modal.html`):
  - Form renderer:
    - Text inputs, dropdowns, checkboxes, date pickers
    - File upload (for CSV import)
  - Approval screen:
    - Show changes as table diff (old → new)
    - "Approve All" / "Approve Selected" / "Reject" buttons
    - Comment box
  - Picklist:
    - Radio buttons or checkboxes from extracted data
    - Example: "Select which John Smith: [John Smith (123), John Smith (456)]"

**Acceptance Criteria**:
- [ ] Workflow can request multi-field input
- [ ] User fills form → values stored as variables
- [ ] Approval screen shows diff of changes
- [ ] User approves/rejects → workflow continues/aborts
- [ ] Picklist from extracted data
- [ ] Test: Request term/dept → user enters → workflow continues with values

---

#### 4.2: Connectors (Email, Sheets, Storage)
**Priority**: P2 (Medium)
**Impact**: Off-browser workflows
**Effort**: High (3 weeks)

**Changes**:
- **New Step Types** ([workflow.py](app/utilities/workflow.py)):
  ```python
  class EmailNode(Node):
      def process(self, inputs):
          # Send email via SMTP/Office365/Gmail
          config = self.data["email_config"]
          send_email(
              to=config["to"],
              subject=config["subject"],
              body=interpolate(config["body"], inputs),
              attachments=inputs.get("attachments", [])
          )

  class GoogleSheetsNode(Node):
      def process(self, inputs):
          # Read/write Google Sheets
          spreadsheet_id = self.data["spreadsheet_id"]
          range = self.data["range"]
          data = inputs.get("data")
          write_to_sheet(spreadsheet_id, range, data)

  class S3UploadNode(Node):
      def process(self, inputs):
          # Upload file to S3
          bucket = self.data["bucket"]
          key = self.data["key"]
          file = inputs.get("file")
          upload_to_s3(bucket, key, file)
  ```

- **Backend** (New: `utilities/connectors/`):
  - `email_connector.py`: SMTP, Office365, Gmail clients
  - `sheets_connector.py`: Google Sheets API
  - `storage_connector.py`: S3, Drive clients

- **UI**:
  - New step types: "Send Email", "Update Sheet", "Upload to S3"
  - Configuration forms for each connector (credentials, config)

**Acceptance Criteria**:
- [ ] Send email with extracted data
- [ ] Write extracted table to Google Sheet
- [ ] Upload downloaded report to S3
- [ ] Test: Extract students → write to Google Sheet → send email notification

---

#### 4.3: Policy & Access Controls
**Priority**: P2 (Medium)
**Impact**: Security and compliance
**Effort**: Medium (2 weeks)

**Changes**:
- **Data Model** ([models.py:211](app/models.py#L211)):
  ```python
  class Workflow(me.Document):
      # Existing fields...

      # NEW: Access control
      permissions = me.DictField()  # {
      #   "allowed_roles": ["admin", "registrar"],
      #   "allowed_domains": ["banner.uidaho.edu", "peoplesoft.uidaho.edu"],
      #   "pii_handling": "redact" | "encrypt" | "none",
      #   "retention_days": 30
      # }
  ```

- **Backend** ([browser_automation.py](app/utilities/browser_automation.py)):
  - Before executing action, check:
    - Is user in `allowed_roles`?
    - Is target URL in `allowed_domains`?
  - Fail if unauthorized

- **Extension** ([content-script.js](chrome-extension/content-script.js)):
  - Before executing, verify domain whitelist

- **Audit Trail** ([browser_automation.py:238](app/utilities/browser_automation.py#L238)):
  - If `pii_handling == "redact"`:
    - Redact sensitive data (SSN, DOB) from logs
  - If `retention_days` set:
    - Auto-delete artifacts after N days

**Acceptance Criteria**:
- [ ] Workflow permissions by team role
- [ ] Domain whitelist enforcement
- [ ] PII redaction in logs
- [ ] Auto-delete artifacts after retention period
- [ ] Test: Non-admin tries to run admin workflow → rejected

---

#### 4.4: Failure Clustering & Analytics Dashboard
**Priority**: P2 (Medium)
**Impact**: Identify systemic issues
**Effort**: Medium (2 weeks)

**Changes**:
- **Data Model** (New: `models.py`):
  ```python
  class FailureReport(me.Document):
      workflow_id = me.StringField(required=True)
      step_id = me.StringField(required=True)
      failure_reason = me.StringField()  # "Element not found", "Session expired"
      failed_at = me.DateTimeField(default=datetime.datetime.now)
      resolved = me.BooleanField(default=False)

  class FailureCluster(me.Document):
      failure_signature = me.StringField(unique=True)  # "workflow_X_step_Y_element_Z"
      failure_count = me.IntField(default=1)
      first_seen = me.DateTimeField()
      last_seen = me.DateTimeField()
      suggested_fix = me.StringField()  # LLM-generated
      related_repairs = me.ListField(me.ReferenceField("WorkflowRepairHistory"))
  ```

- **Backend** (New: `utilities/failure_analyzer.py`):
  - On workflow failure, create `FailureReport`
  - Group failures by signature (workflow + step + error type)
  - Update `FailureCluster` counts
  - Use LLM to suggest fix based on repair history

- **UI** (New: `analytics_dashboard.html`):
  - Charts:
    - Success rate by workflow
    - Most common failure reasons
    - Time saved (estimated based on manual time)
  - Failure clusters table:
    - Signature, count, suggested fix
    - "Apply suggested fix" button

**Acceptance Criteria**:
- [ ] Failures grouped by root cause
- [ ] LLM suggests fixes based on repair patterns
- [ ] Dashboard shows success rate, time saved, failure clusters
- [ ] Test: Run workflow 5 times, fail on same step → 1 cluster with count 5

---

### Phase 5: LLM-Assisted Authoring (Weeks 17-18)
**Goal**: Use LLM to reduce manual work

#### 5.1: LLM Step Labeling & Robust Selector Generation
**Priority**: P2 (Medium)
**Impact**: Better workflow readability
**Effort**: Medium (2 weeks)

**Changes**:
- **Backend** (New: `utilities/llm_workflow_enhancer.py`):
  - After recording, call LLM:
    ```python
    def label_recorded_steps(recorded_steps):
        prompt = f"""
        Recorded steps:
        {json.dumps(recorded_steps, indent=2)}

        For each step, generate:
        1. Human-readable description (intent)
        2. Robust selector suggestions

        Output JSON:
        [
          {{"step_id": "step_1", "description": "Click 'Run Report' button", "selector_suggestions": [...]}}
        ]
        """
        labels = llm.generate(prompt)
        return labels
    ```

  - Apply labels to `BrowserActionStep.description`
  - Show selector suggestions to user for approval

- **UI**:
  - After recording, show "Enhance Workflow" button
  - LLM generates labels → user reviews and accepts/edits

**Acceptance Criteria**:
- [ ] LLM generates human-readable step labels
- [ ] LLM suggests robust selectors (prefer aria-label, role over CSS)
- [ ] User reviews and accepts/edits
- [ ] Test: Record 5 steps → enhance → get meaningful labels

---

#### 5.2: LLM Extraction Schema Generation
**Priority**: P2 (Medium)
**Impact**: Faster table extraction setup
**Effort**: Low (1 week)

**Changes**:
- **Backend** (Enhance existing `extract_information_with_llm` in [browser_automation.py:418](app/utilities/browser_automation.py#L418)):
  - New function: `generate_extraction_schema_from_html(html, table_selector)`
  - LLM prompt:
    ```
    HTML:
    <table class="enrollment">
      <thead><tr><th>Student ID</th><th>Name</th><th>Status</th></tr></thead>
      ...
    </table>

    Generate extraction schema:
    {
      "Student ID": {"type": "string", "synonyms": ["ID", "SID"]},
      "Name": {"type": "string", "synonyms": ["Student Name"]},
      "Status": {"type": "string", "synonyms": ["Enrollment Status"]}
    }
    ```

- **UI**:
  - Table extraction builder: "Generate schema from page" button
  - LLM analyzes current page → generates schema → user edits

**Acceptance Criteria**:
- [ ] LLM generates schema from table HTML
- [ ] Includes column types and synonyms
- [ ] User can edit and refine
- [ ] Test: Open Banner report → generate schema → extract data

---

#### 5.3: LLM Failure Recovery Suggestions
**Priority**: P2 (Medium)
**Impact**: Reduce manual repair effort
**Effort**: Low (1 week)

**Changes**:
- **Backend** (Enhance `execute_action_with_stack` in [browser_automation.py:279](app/utilities/browser_automation.py#L279)):
  - On failure, before prompting user, call LLM:
    ```python
    def suggest_recovery(failure_context):
        prompt = f"""
        Action failed: {failure_context['action_type']}
        Target: {failure_context['target_description']}
        Page HTML: {failure_context['page_html'][:5000]}
        Error: {failure_context['error']}

        Suggest recovery steps:
        1. New selector to try
        2. Is there a modal blocking the element?
        3. Is the page logged out?
        4. Should we wait for an element to appear first?

        Output JSON: {{"recovery_type": "new_selector", "selector": "...", "confidence": 0.8}}
        """
        suggestion = llm.generate(prompt)
        return suggestion
    ```

  - Show suggestion to user in repair UI
  - User can apply suggestion or manually fix

**Acceptance Criteria**:
- [ ] On failure, LLM suggests recovery steps
- [ ] Suggestions include: new selector, close modal, wait for element
- [ ] User can apply suggestion with one click
- [ ] Test: Element not found → LLM suggests alternative selector → apply → success

---

## Part 3: Implementation Guidelines

### Testing Strategy

For each phase, create:

1. **Unit Tests**:
   - Locator stack fallback logic
   - Variable interpolation
   - Condition evaluation
   - Loop execution

2. **Integration Tests**:
   - Recording → playback flow
   - Repair UI → patch workflow → continue execution
   - Multi-page table extraction
   - Human-in-the-loop pause → resume

3. **End-to-End Tests** (Real University Sites):
   - Banner login → navigate to reports → extract table
   - PeopleSoft session timeout → auto-pause → resume
   - Enrollment report with pagination (3 pages) → extract all

4. **Regression Tests**:
   - After workflow repair, run previous test workflows
   - Ensure "fix for X doesn't break Y"

---

### Deployment Plan

**Phase 1**: Internal pilot (2 workflows, 1 department)
**Phase 2**: Expand to 3 departments, 10 workflows
**Phase 3**: University-wide beta, IT/security review
**Phase 4**: Production launch with monitoring

---

### Monitoring & Metrics

Track:
- **Success Rate**: % of workflows that complete without failure
- **Repair Rate**: % of workflows that require repair per month
- **Time Saved**: Estimated manual time vs. automated time
- **Top Failure Reasons**: Element not found, session expired, etc.
- **Adoption**: # of workflows created, # of executions per week

---

## Part 4: Quick Wins (Low-Hanging Fruit)

If you want to show immediate value with minimal effort:

### Quick Win #1: Logged-Out State Detection (1 week, P1)
- Biggest pain point for admins (SSO timeouts)
- Simple URL/DOM pattern matching
- Auto-pause is user-friendly

### Quick Win #2: Table Extraction with Header Synonyms (1.5 weeks, P0)
- Core use case for admins
- Enhance existing `extractor.js`
- Immediate value: "extract all students even when header renamed"

### Quick Win #3: Destructive Action Confirmation (1 week, P1)
- Safety + trust
- Simple keyword detection
- Shows you care about user mistakes

### Quick Win #4: Workflow Versioning UI (1 week, P1)
- Already have repair history in backend
- Just need UI to show versions
- Huge confidence boost for admins

---

## Part 5: Risk Mitigation

### Risk: LLM Hallucinations
**Mitigation**: Never let LLM execute directly. Always:
1. LLM proposes action
2. Human reviews and confirms
3. Deterministic executor runs action

### Risk: Brittle Selectors Still Break
**Mitigation**:
1. Self-healing repair UI (1.3) is **critical**
2. Neighborhood context (1.1) reduces brittleness
3. LLM fallback for fuzzy matching

### Risk: IT/Security Blocks Extension
**Mitigation**:
1. Phase 3.3: Policy & access controls
2. Domain whitelisting
3. PII redaction in logs
4. Audit trail for compliance

### Risk: Admins Don't Trust Automation
**Mitigation**:
1. Phase 3.3: Destructive action confirmation
2. Dry-run mode
3. Visual audit trail overlay ("Robot is about to...")
4. Human-in-the-loop approvals (4.1)

---

## Summary: Your Path Forward

### Critical Path (P0):
1. **Element Fingerprinting with Neighborhood** (1.1) - Foundation for self-healing
2. **Self-Healing Repair UI** (1.3) - **Highest leverage**, prevents abandonment
3. **Table Extraction with Schema** (2.1) - Core admin use case
4. **Page Landmarks & Verification** (1.2) - Prevents "wrong page" failures

### High Priority (P1):
5. **Logged-Out State Detection** (1.4) - SSO/Duo pain point
6. **Outcome-Based Execution** (1.5) - Reliability and speed
7. **Branching & Loops** (3.1, 3.2) - Real workflows need these
8. **Protected Actions Firewall** (3.3) - Safety and trust
9. **Workflow Versioning** (3.4) - Prevents "fix for X breaks Y"
10. **Human-in-the-Loop Forms** (4.1) - Admins need to inject data

### Medium Priority (P2):
11. **Variable Binding UI** (2.3) - Workflow templates
12. **Download Extraction** (2.2) - Many reports are files
13. **Connectors** (4.2) - Off-browser workflows
14. **Failure Clustering** (4.4) - Identify systemic issues
15. **LLM Enhancements** (5.1-5.3) - Reduce manual work

---

## Next Steps

1. **Review this roadmap** with your team
2. **Prioritize phases** based on user feedback and pain points
3. **Start with Phase 1** (weeks 1-4): Make recording replayable
4. **Run internal pilot** after Phase 2 with 1-2 departments
5. **Iterate based on feedback** before Phase 3

**Your system is 60% of the way there.** The most critical missing pieces are:
- Self-healing repair UI (1.3)
- Table extraction with schema (2.1)
- Branching/loops (3.1, 3.2)
- Safety rails (3.3)

With these 4 features, you'll have a **resilient, production-ready admin RPA system**.

---

**Questions or need clarification on any phase? Ready to start implementing?**
