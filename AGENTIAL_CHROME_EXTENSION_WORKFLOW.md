# Agential Chrome Extension Workflow Implementation Plan

## Executive Summary

This document outlines the complete implementation plan for integrating browser automation capabilities into the existing workflow system. The feature enables users to create workflows that:

- Navigate to websites and interact with web pages through a Chrome extension
- Handle secure user authentication (user logs in manually when prompted)
- Fill complex forms with data from previous workflow steps
- Extract structured data from web pages
- Return results in natural language format
- Chain multiple web interactions together in a single workflow

## Architecture Overview

### Component Ecosystem

```
┌─────────────────────────────────────────────────────────────────┐
│                        Workflow UI (Frontend)                    │
│  - Browser step configuration modals                            │
│  - Real-time execution monitoring                               │
│  - User login prompts & confirmations                           │
└──────────────────┬──────────────────────────────────────────────┘
                   │ HTTP/WebSocket
┌──────────────────▼──────────────────────────────────────────────┐
│              Flask Backend (Vandalizer)                          │
│  - BrowserAutomationNode (workflow.py)                          │
│  - Browser Automation Service (new: browser_automation.py)      │
│  - WebSocket manager for real-time control                      │
│  - Session state management                                     │
└──────────────────┬──────────────────────────────────────────────┘
                   │ WebSocket/HTTP
┌──────────────────▼──────────────────────────────────────────────┐
│            Chrome Extension (New Component)                      │
│  - Background script (service worker)                           │
│  - Content scripts (DOM manipulation)                           │
│  - Connection manager to backend                                │
│  - Visual overlays & cursor                                     │
└─────────────────────────────────────────────────────────────────┘
```

### Integration with Existing Workflow System

The browser automation feature will integrate as a new **Node type** in the existing workflow engine, following the established patterns:

- **DocumentNode** → Trigger (existing)
- **ExtractionNode** → Extract from documents (existing)
- **PromptNode** → LLM interaction (existing)
- **FormatNode** → Transform output (existing)
- **BrowserAutomationNode** → Web automation (NEW)

## Phase 1: Backend Foundation

### 1.1 Data Models (No Schema Changes Required)

Leverage existing `WorkflowStepTask.data` DictField for flexible storage.

**BrowserAutomation Task Data Schema:**

```python
{
    "task_type": "BrowserAutomation",
    "session_mode": "user_browser",  # vs "headless" (future)
    "actions": [
        {
            "action_id": "uuid-1",
            "type": "navigate",
            "url": "https://example.com/search",
            "wait_for": {
                "condition": "element_present",
                "selector": "#search-form",
                "timeout_ms": 5000
            }
        },
        {
            "action_id": "uuid-2",
            "type": "ensure_login",
            "detection_rules": {
                "url_pattern": "^https://example\\.com/dashboard",
                "element_selector": ".user-profile",
                "element_text": null
            },
            "instruction_to_user": "Please log into Example.com with your account that has access to customer data."
        },
        {
            "action_id": "uuid-3",
            "type": "fill_form",
            "fields": [
                {
                    "locator": {"strategy": "css", "value": "input[name='customer_name']"},
                    "value_source": "literal",  # or "previous_step", "user_input"
                    "value": "{{previous_step.customer_name}}"  # Template variable
                }
            ],
            "options": {
                "clear_before": true,
                "typing_delay_ms": 50
            }
        },
        {
            "action_id": "uuid-4",
            "type": "click",
            "locator": {"strategy": "css", "value": "button[type='submit']"},
            "wait_after": {
                "condition": "navigation_complete",
                "timeout_ms": 10000
            }
        },
        {
            "action_id": "uuid-5",
            "type": "extract",
            "extraction_spec": {
                "mode": "simple",  # or "table"
                "fields": [
                    {
                        "name": "invoice_total",
                        "locator": {"strategy": "css", "value": ".invoice-amount"},
                        "attribute": "innerText"
                    },
                    {
                        "name": "invoice_date",
                        "locator": {"strategy": "css", "value": ".invoice-date"},
                        "attribute": "innerText"
                    }
                ]
            }
        }
    ],
    "summarization": {
        "enabled": true,
        "prompt_template": "Based on the extracted data, provide a summary of the invoice information for the customer."
    },
    "model": "claude-sonnet-4-5",  # For LLM summarization
    "allowed_domains": ["example.com"],
    "timeout_seconds": 300
}
```

### 1.2 Browser Automation Service

**New File:** `app/utilities/browser_automation.py`

**Responsibilities:**
- Manage browser automation sessions
- Route commands to Chrome extension
- Track session state machine
- Handle command timeouts and retries
- Normalize responses from extension

**Key Classes:**

```python
class BrowserAutomationSession:
    """Represents a single browser automation session tied to a workflow execution"""

    def __init__(self, session_id, user_id, workflow_result_id, allowed_domains):
        self.session_id = session_id
        self.user_id = user_id
        self.workflow_result_id = workflow_result_id
        self.state = SessionState.CREATED
        self.allowed_domains = allowed_domains
        self.pending_commands = {}  # request_id -> command metadata
        self.last_heartbeat = datetime.utcnow()

    # State machine management
    def transition_to(self, new_state, reason=None):
        """Transition session state with validation"""

    def is_active(self):
        """Check if session is in an active state"""

    # Command management
    def send_command(self, command_name, payload, timeout_ms=30000):
        """Send command to extension and track request"""

    def handle_response(self, request_id, response_data):
        """Process response from extension"""

    def handle_event(self, event_type, event_data):
        """Process async event from extension"""


class SessionState(Enum):
    CREATED = "created"
    CONNECTING = "connecting"
    READY_NO_LOGIN = "ready_no_login"
    WAITING_FOR_LOGIN = "waiting_for_login"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class BrowserAutomationService:
    """Main service for managing all browser automation sessions"""

    def __init__(self):
        self.sessions = {}  # session_id -> BrowserAutomationSession
        self.websocket_connections = {}  # user_id -> websocket connection

    def create_session(self, user_id, workflow_result_id, allowed_domains):
        """Initialize a new browser automation session"""

    def start_session(self, session_id, initial_url=None):
        """Send start_session command to extension"""

    def execute_action(self, session_id, action_config):
        """Execute a single action (navigate, fill, click, extract, etc.)"""

    def wait_for_user_login(self, session_id, detection_rules, instruction):
        """Pause workflow and wait for user login confirmation"""

    def extract_data(self, session_id, extraction_spec):
        """Extract structured data from current page"""

    def end_session(self, session_id, close_tab=False):
        """Clean up session resources"""

    # WebSocket management
    def register_websocket(self, user_id, ws_connection):
        """Register extension websocket connection"""

    def send_to_extension(self, user_id, message):
        """Send message to extension via WebSocket"""

    def handle_extension_message(self, user_id, message):
        """Process incoming message from extension"""
```

**Message Protocol:**

```python
class MessageEnvelope:
    """Standard message format between backend and extension"""

    type: str  # "command", "response", "event", "heartbeat"
    command_name: str  # "start_session", "navigate", "fill_form", etc.
    request_id: str  # UUID for correlating request/response
    session_id: str
    payload: dict  # Command-specific data
    timestamp: datetime
```

### 1.3 BrowserAutomationNode

**Location:** `app/utilities/workflow.py`

**Implementation:**

```python
class BrowserAutomationNode(Node):
    """
    Node for browser automation within workflows.
    Executes web interactions via Chrome extension.
    """

    def __init__(self, data):
        super().__init__("BrowserAutomation")
        self.data = data
        self.model = data.get("model", "claude-sonnet-4-5")
        self.actions = data["actions"]
        self.summarization = data.get("summarization", {})
        self.allowed_domains = data.get("allowed_domains", [])
        self.timeout_seconds = data.get("timeout_seconds", 300)
        self.user_id = data.get("user_id")
        self.workflow_result_id = data.get("workflow_result_id")

    def process(self, inputs):
        """
        Execute browser automation workflow.

        Flow:
        1. Create browser session
        2. Start session (open/attach to tab)
        3. Execute each action in sequence
        4. Handle user login pauses
        5. Extract final data
        6. Optionally summarize with LLM
        7. Clean up session
        """

        service = BrowserAutomationService.get_instance()

        # Create session
        session = service.create_session(
            user_id=self.user_id,
            workflow_result_id=self.workflow_result_id,
            allowed_domains=self.allowed_domains
        )

        try:
            # Start browser session
            self._report_progress("Connecting to browser extension...")
            service.start_session(session.session_id)

            # Execute actions sequentially
            extracted_data = {}
            for i, action in enumerate(self.actions):
                self._report_progress(
                    f"Step {i+1}/{len(self.actions)}: {action['type']}...",
                    preview=self._get_action_preview(action)
                )

                result = self._execute_action(service, session, action, inputs)

                # If extraction, store data
                if action["type"] == "extract":
                    extracted_data.update(result)

                # If login required, wait for user
                if action["type"] == "ensure_login":
                    self._wait_for_user_login(service, session, action)

            # Summarize results if configured
            final_output = extracted_data
            if self.summarization.get("enabled"):
                self._report_progress("Generating summary...")
                final_output = self._summarize_results(extracted_data, inputs)

            # Clean up
            service.end_session(session.session_id, close_tab=False)

            return {
                "output": final_output,
                "input": self._format_input(inputs),
                "step_name": self.name
            }

        except Exception as e:
            service.end_session(session.session_id, close_tab=False)
            raise

    def _execute_action(self, service, session, action, inputs):
        """Execute a single action and return results"""

        # Interpolate variables from previous steps
        action_with_values = self._interpolate_variables(action, inputs)

        return service.execute_action(session.session_id, action_with_values)

    def _wait_for_user_login(self, service, session, action):
        """Pause execution and wait for user to complete login"""

        # Update workflow result with special status
        self._report_progress(
            "Waiting for user login...",
            detail=action["instruction_to_user"],
            requires_user_action=True
        )

        # Block until login confirmed
        service.wait_for_user_login(
            session.session_id,
            action["detection_rules"],
            action["instruction_to_user"]
        )

    def _summarize_results(self, extracted_data, inputs):
        """Use LLM to generate natural language summary"""

        from app.utilities.chat import ChatManager

        prompt = self.summarization["prompt_template"]
        context = {
            "extracted_data": json.dumps(extracted_data, indent=2),
            "original_input": inputs
        }

        chat_manager = ChatManager(model=self.model)
        summary = chat_manager.send_message(
            prompt.format(**context),
            stream=True,
            callback=lambda chunk: self._report_progress_preview(chunk)
        )

        return {
            "raw_data": extracted_data,
            "summary": summary
        }

    def _interpolate_variables(self, action, inputs):
        """Replace template variables like {{previous_step.field}} with actual values"""

        action_json = json.dumps(action)

        # Simple template replacement
        # Supports: {{previous_step.field_name}}
        import re
        pattern = r'\{\{([^}]+)\}\}'

        def replace_var(match):
            var_path = match.group(1).strip()
            parts = var_path.split('.')

            value = inputs
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part, match.group(0))
                else:
                    return match.group(0)

            return str(value) if value is not None else match.group(0)

        interpolated = re.sub(pattern, replace_var, action_json)
        return json.loads(interpolated)
```

### 1.4 Flask Routes

**New File:** `app/blueprints/browser_automation/routes.py`

**Endpoints:**

```python
@browser_automation_bp.route("/websocket/connect")
def browser_automation_websocket():
    """
    WebSocket endpoint for Chrome extension to connect.
    Handles bidirectional communication for browser control.
    """

@browser_automation_bp.route("/session/<session_id>/confirm_login", methods=["POST"])
@login_required
def confirm_user_login(session_id):
    """
    User clicks "I'm logged in" button in UI.
    Signals session to continue from WAITING_FOR_LOGIN state.
    """

@browser_automation_bp.route("/session/<session_id>/status", methods=["GET"])
@login_required
def get_session_status(session_id):
    """
    Poll endpoint for real-time session status updates.
    Returns current state, pending actions, errors, etc.
    """
```

**Integration into Workflows Blueprint:**

`app/blueprints/workflows/routes.py`

```python
@workflows.route("/add_browser_automation_step", methods=["GET", "POST"])
@login_required
def workflow_add_browser_automation_step():
    """
    GET: Return modal template for configuring browser automation step
    POST: Create WorkflowStepTask with browser automation configuration
    """
    if request.method == "GET":
        workflow_step = WorkflowStep.objects.get(id=request.args.get("workflow_step_id"))
        return render_template(
            "workflows/workflow_steps/workflow_add_browser_automation_modal.html",
            workflow_step=workflow_step
        )
    else:
        # Create task
        task_data = {
            "task_type": "BrowserAutomation",
            "actions": request.json.get("actions", []),
            "summarization": request.json.get("summarization", {}),
            "allowed_domains": request.json.get("allowed_domains", []),
            "timeout_seconds": request.json.get("timeout_seconds", 300)
        }

        task = WorkflowStepTask(name="BrowserAutomation", data=task_data)
        task.save()

        workflow_step = WorkflowStep.objects.get(id=request.json.get("workflow_step_id"))
        workflow_step.tasks.append(task)
        workflow_step.save()

        return jsonify({"success": True, "task_id": str(task.id)})


@workflows.route("/browser_automation/element_picker", methods=["GET"])
@login_required
def browser_automation_element_picker():
    """
    Return UI for "pick element from page" mode.
    Works with extension to let user click on page elements
    to generate selectors.
    """
```

### 1.5 Workflow Engine Integration

**Location:** `app/utilities/workflow.py`, function `build_workflow_engine()`

**Add to builder logic:**

```python
def build_workflow_engine(workflow, user_id, documents, model="claude-sonnet-4-5", workflow_result=None):
    # ... existing code ...

    for step in workflow.steps:
        for task in step.tasks:
            # ... existing task handling ...

            elif task.name == "BrowserAutomation":
                task.data["user_id"] = user_id
                task.data["model"] = model
                task.data["workflow_result_id"] = str(workflow_result.id) if workflow_result else None

                node = BrowserAutomationNode(data=task.data)
                tasks.append(node)

    # ... rest of function ...
```

## Phase 2: Chrome Extension

### 2.1 Extension Structure

```
chrome-extension/
├── manifest.json
├── background/
│   ├── service-worker.js       # Main background script
│   ├── session-manager.js      # Session state management
│   └── command-handler.js      # Execute commands
├── content/
│   ├── content-script.js       # Injected into pages
│   ├── dom-actions.js          # DOM manipulation utilities
│   ├── extractor.js            # Data extraction logic
│   └── overlay.js              # Visual cursor/highlights
├── popup/
│   ├── popup.html              # Extension popup UI
│   ├── popup.js
│   └── popup.css
└── assets/
    ├── icons/
    └── styles/
```

### 2.2 Manifest Configuration

**manifest.json:**

```json
{
  "manifest_version": 3,
  "name": "Vandalizer Browser Automation",
  "version": "1.0.0",
  "description": "Browser automation extension for Vandalizer workflows",

  "permissions": [
    "tabs",
    "activeTab",
    "scripting",
    "storage",
    "webNavigation"
  ],

  "host_permissions": [
    "<all_urls>"
  ],

  "background": {
    "service_worker": "background/service-worker.js",
    "type": "module"
  },

  "content_scripts": [
    {
      "matches": ["<all_urls>"],
      "js": [
        "content/dom-actions.js",
        "content/extractor.js",
        "content/overlay.js",
        "content/content-script.js"
      ],
      "run_at": "document_idle",
      "all_frames": false
    }
  ],

  "action": {
    "default_popup": "popup/popup.html",
    "default_icon": {
      "16": "assets/icons/icon-16.png",
      "48": "assets/icons/icon-48.png",
      "128": "assets/icons/icon-128.png"
    }
  },

  "web_accessible_resources": [
    {
      "resources": ["assets/*"],
      "matches": ["<all_urls>"]
    }
  ]
}
```

### 2.3 Background Service Worker

**background/service-worker.js:**

```javascript
import { SessionManager } from './session-manager.js';
import { CommandHandler } from './command-handler.js';

class BrowserAutomationBackground {
    constructor() {
        this.wsConnection = null;
        this.sessionManager = new SessionManager();
        this.commandHandler = new CommandHandler(this.sessionManager);
        this.reconnectInterval = null;
        this.backendUrl = null;
        this.userToken = null;

        this.setupListeners();
    }

    setupListeners() {
        // Listen for messages from content scripts
        chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
            this.handleContentScriptMessage(message, sender, sendResponse);
            return true; // Keep channel open for async response
        });

        // Listen for tab updates (navigation, close)
        chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
            this.handleTabUpdate(tabId, changeInfo, tab);
        });

        chrome.tabs.onRemoved.addListener((tabId) => {
            this.handleTabRemoved(tabId);
        });

        // Extension installation/startup
        chrome.runtime.onInstalled.addListener(() => {
            this.initialize();
        });

        chrome.runtime.onStartup.addListener(() => {
            this.initialize();
        });
    }

    async initialize() {
        // Load configuration from storage
        const config = await chrome.storage.local.get(['backendUrl', 'userToken']);
        this.backendUrl = config.backendUrl || 'ws://localhost:5000';
        this.userToken = config.userToken;

        if (this.userToken) {
            this.connectToBackend();
        }
    }

    connectToBackend() {
        if (this.wsConnection?.readyState === WebSocket.OPEN) {
            return; // Already connected
        }

        this.wsConnection = new WebSocket(`${this.backendUrl}/browser_automation/websocket/connect`);

        this.wsConnection.onopen = () => {
            console.log('[BrowserAutomation] Connected to backend');

            // Send authentication
            this.sendToBackend({
                type: 'auth',
                token: this.userToken
            });

            // Start heartbeat
            this.startHeartbeat();
        };

        this.wsConnection.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleBackendMessage(message);
        };

        this.wsConnection.onerror = (error) => {
            console.error('[BrowserAutomation] WebSocket error:', error);
        };

        this.wsConnection.onclose = () => {
            console.log('[BrowserAutomation] Disconnected from backend');
            this.scheduleReconnect();
        };
    }

    scheduleReconnect() {
        if (this.reconnectInterval) return;

        this.reconnectInterval = setInterval(() => {
            if (this.wsConnection?.readyState !== WebSocket.OPEN) {
                this.connectToBackend();
            } else {
                clearInterval(this.reconnectInterval);
                this.reconnectInterval = null;
            }
        }, 5000);
    }

    startHeartbeat() {
        setInterval(() => {
            if (this.wsConnection?.readyState === WebSocket.OPEN) {
                this.sendToBackend({ type: 'heartbeat', timestamp: Date.now() });
            }
        }, 30000); // Every 30 seconds
    }

    sendToBackend(message) {
        if (this.wsConnection?.readyState === WebSocket.OPEN) {
            this.wsConnection.send(JSON.stringify(message));
        }
    }

    async handleBackendMessage(message) {
        const { type, command_name, request_id, session_id, payload } = message;

        if (type === 'command') {
            // Execute command and send response
            try {
                const result = await this.commandHandler.execute(
                    command_name,
                    session_id,
                    payload
                );

                this.sendToBackend({
                    type: 'response',
                    command_name,
                    request_id,
                    session_id,
                    payload: { status: 'success', data: result },
                    timestamp: Date.now()
                });
            } catch (error) {
                this.sendToBackend({
                    type: 'response',
                    command_name,
                    request_id,
                    session_id,
                    payload: {
                        status: 'error',
                        message: error.message,
                        stack: error.stack
                    },
                    timestamp: Date.now()
                });
            }
        }
    }

    async handleContentScriptMessage(message, sender, sendResponse) {
        const { action, data } = message;

        switch (action) {
            case 'element_picked':
                // User picked an element for selector generation
                this.handleElementPicked(data, sender.tab.id);
                sendResponse({ success: true });
                break;

            case 'login_detected':
                // Content script detected successful login
                this.handleLoginDetected(data, sender.tab.id);
                sendResponse({ success: true });
                break;

            case 'extraction_complete':
                // Content script finished extracting data
                this.handleExtractionComplete(data, sender.tab.id);
                sendResponse({ success: true });
                break;
        }
    }

    handleTabUpdate(tabId, changeInfo, tab) {
        if (changeInfo.status === 'complete') {
            const session = this.sessionManager.getSessionByTabId(tabId);
            if (session) {
                // Send navigation_complete event
                this.sendToBackend({
                    type: 'event',
                    event_name: 'navigation_complete',
                    session_id: session.id,
                    payload: {
                        url: tab.url,
                        title: tab.title
                    },
                    timestamp: Date.now()
                });
            }
        }
    }

    handleTabRemoved(tabId) {
        const session = this.sessionManager.getSessionByTabId(tabId);
        if (session) {
            // Tab closed unexpectedly
            this.sendToBackend({
                type: 'event',
                event_name: 'session_failed',
                session_id: session.id,
                payload: {
                    reason: 'Tab closed by user'
                },
                timestamp: Date.now()
            });

            this.sessionManager.removeSession(session.id);
        }
    }

    handleElementPicked(data, tabId) {
        // Forward to backend for element picker feature
        const session = this.sessionManager.getSessionByTabId(tabId);
        if (session) {
            this.sendToBackend({
                type: 'event',
                event_name: 'element_picked',
                session_id: session.id,
                payload: data,
                timestamp: Date.now()
            });
        }
    }

    handleLoginDetected(data, tabId) {
        const session = this.sessionManager.getSessionByTabId(tabId);
        if (session) {
            this.sendToBackend({
                type: 'event',
                event_name: 'login_state_changed',
                session_id: session.id,
                payload: {
                    is_logged_in: true,
                    ...data
                },
                timestamp: Date.now()
            });
        }
    }

    handleExtractionComplete(data, tabId) {
        const session = this.sessionManager.getSessionByTabId(tabId);
        if (session) {
            this.sendToBackend({
                type: 'event',
                event_name: 'extraction_result',
                session_id: session.id,
                payload: data,
                timestamp: Date.now()
            });
        }
    }
}

// Initialize
const browserAutomation = new BrowserAutomationBackground();
```

**background/command-handler.js:**

```javascript
export class CommandHandler {
    constructor(sessionManager) {
        this.sessionManager = sessionManager;
    }

    async execute(commandName, sessionId, payload) {
        const handler = this.handlers[commandName];
        if (!handler) {
            throw new Error(`Unknown command: ${commandName}`);
        }

        return await handler.call(this, sessionId, payload);
    }

    handlers = {
        start_session: async (sessionId, payload) => {
            const { initial_url, mode, allowed_domains } = payload;

            let tab;
            if (mode === 'attach_current_tab') {
                const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
                tab = activeTab;
            } else {
                tab = await chrome.tabs.create({ url: initial_url || 'about:blank' });
            }

            // Create session
            this.sessionManager.createSession(sessionId, tab.id, allowed_domains);

            // Inject content scripts if not already present
            await this.injectContentScripts(tab.id);

            return { tabId: tab.id, url: tab.url };
        },

        navigate: async (sessionId, payload) => {
            const { target_url, wait_for } = payload;
            const session = this.sessionManager.getSession(sessionId);

            if (!session) {
                throw new Error(`Session not found: ${sessionId}`);
            }

            // Check domain allowlist
            const url = new URL(target_url);
            if (!this.sessionManager.isDomainAllowed(sessionId, url.hostname)) {
                throw new Error(`Domain not allowed: ${url.hostname}`);
            }

            await chrome.tabs.update(session.tabId, { url: target_url });

            // Wait for page load
            if (wait_for) {
                await this.waitForCondition(session.tabId, wait_for);
            }

            return { success: true };
        },

        fill_form: async (sessionId, payload) => {
            const { field_mappings, options } = payload;
            const session = this.sessionManager.getSession(sessionId);

            // Send to content script
            const result = await chrome.tabs.sendMessage(session.tabId, {
                action: 'fill_form',
                data: { field_mappings, options }
            });

            return result;
        },

        click: async (sessionId, payload) => {
            const { locator, click_type, post_click_wait } = payload;
            const session = this.sessionManager.getSession(sessionId);

            const result = await chrome.tabs.sendMessage(session.tabId, {
                action: 'click_element',
                data: { locator, click_type }
            });

            if (post_click_wait) {
                await this.waitForCondition(session.tabId, post_click_wait);
            }

            return result;
        },

        wait_for: async (sessionId, payload) => {
            const { condition_type, condition_value, timeout_ms } = payload;
            const session = this.sessionManager.getSession(sessionId);

            await this.waitForCondition(session.tabId, payload);

            return { success: true };
        },

        extract: async (sessionId, payload) => {
            const { extraction_spec } = payload;
            const session = this.sessionManager.getSession(sessionId);

            const result = await chrome.tabs.sendMessage(session.tabId, {
                action: 'extract_data',
                data: { extraction_spec }
            });

            return result;
        },

        scroll: async (sessionId, payload) => {
            const session = this.sessionManager.getSession(sessionId);

            const result = await chrome.tabs.sendMessage(session.tabId, {
                action: 'scroll_page',
                data: payload
            });

            return result;
        },

        end_session: async (sessionId, payload) => {
            const { close_tab } = payload;
            const session = this.sessionManager.getSession(sessionId);

            if (close_tab) {
                await chrome.tabs.remove(session.tabId);
            }

            this.sessionManager.removeSession(sessionId);

            return { success: true };
        },

        set_cursor_visibility: async (sessionId, payload) => {
            const { visible, style } = payload;
            const session = this.sessionManager.getSession(sessionId);

            await chrome.tabs.sendMessage(session.tabId, {
                action: 'set_cursor',
                data: { visible, style }
            });

            return { success: true };
        },

        capture_screenshot: async (sessionId, payload) => {
            const session = this.sessionManager.getSession(sessionId);

            const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'png' });

            return { screenshot: dataUrl };
        }
    };

    async waitForCondition(tabId, condition) {
        const { condition_type, condition_value, timeout_ms = 30000 } = condition;

        const startTime = Date.now();

        while (Date.now() - startTime < timeout_ms) {
            try {
                const result = await chrome.tabs.sendMessage(tabId, {
                    action: 'check_condition',
                    data: { condition_type, condition_value }
                });

                if (result.met) {
                    return true;
                }
            } catch (error) {
                // Tab might not be ready yet
            }

            await new Promise(resolve => setTimeout(resolve, 500));
        }

        throw new Error(`Condition timeout: ${condition_type}`);
    }

    async injectContentScripts(tabId) {
        try {
            await chrome.scripting.executeScript({
                target: { tabId },
                files: [
                    'content/dom-actions.js',
                    'content/extractor.js',
                    'content/overlay.js',
                    'content/content-script.js'
                ]
            });
        } catch (error) {
            // Scripts might already be injected
            console.log('Content scripts already injected or injection failed:', error);
        }
    }
}
```

**background/session-manager.js:**

```javascript
export class SessionManager {
    constructor() {
        this.sessions = new Map(); // sessionId -> { id, tabId, allowedDomains, state }
        this.tabToSession = new Map(); // tabId -> sessionId
    }

    createSession(sessionId, tabId, allowedDomains = []) {
        const session = {
            id: sessionId,
            tabId,
            allowedDomains,
            state: 'READY_NO_LOGIN',
            createdAt: Date.now()
        };

        this.sessions.set(sessionId, session);
        this.tabToSession.set(tabId, sessionId);

        return session;
    }

    getSession(sessionId) {
        return this.sessions.get(sessionId);
    }

    getSessionByTabId(tabId) {
        const sessionId = this.tabToSession.get(tabId);
        return sessionId ? this.sessions.get(sessionId) : null;
    }

    removeSession(sessionId) {
        const session = this.sessions.get(sessionId);
        if (session) {
            this.tabToSession.delete(session.tabId);
            this.sessions.delete(sessionId);
        }
    }

    updateState(sessionId, newState) {
        const session = this.sessions.get(sessionId);
        if (session) {
            session.state = newState;
        }
    }

    isDomainAllowed(sessionId, hostname) {
        const session = this.sessions.get(sessionId);
        if (!session || session.allowedDomains.length === 0) {
            return true; // No restrictions
        }

        return session.allowedDomains.some(allowed => {
            // Support wildcards like *.example.com
            const pattern = allowed.replace(/\*/g, '.*');
            const regex = new RegExp(`^${pattern}$`);
            return regex.test(hostname);
        });
    }
}
```

### 2.4 Content Scripts

**content/content-script.js:**

```javascript
// Main content script - coordinates between background and page
class BrowserAutomationContent {
    constructor() {
        this.overlay = new OverlayManager();
        this.domActions = new DOMActions();
        this.extractor = new DataExtractor();

        this.setupListeners();
    }

    setupListeners() {
        chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
            this.handleMessage(message, sender, sendResponse);
            return true; // Async response
        });
    }

    async handleMessage(message, sender, sendResponse) {
        const { action, data } = message;

        try {
            let result;

            switch (action) {
                case 'fill_form':
                    result = await this.fillForm(data);
                    break;

                case 'click_element':
                    result = await this.clickElement(data);
                    break;

                case 'extract_data':
                    result = await this.extractData(data);
                    break;

                case 'scroll_page':
                    result = await this.scrollPage(data);
                    break;

                case 'check_condition':
                    result = await this.checkCondition(data);
                    break;

                case 'set_cursor':
                    this.overlay.setCursor(data.visible, data.style);
                    result = { success: true };
                    break;

                case 'enable_element_picker':
                    this.overlay.enableElementPicker((element) => {
                        chrome.runtime.sendMessage({
                            action: 'element_picked',
                            data: this.domActions.generateSelector(element)
                        });
                    });
                    result = { success: true };
                    break;
            }

            sendResponse(result);
        } catch (error) {
            sendResponse({
                success: false,
                error: error.message,
                stack: error.stack
            });
        }
    }

    async fillForm(data) {
        const { field_mappings, options } = data;
        const results = [];

        for (const mapping of field_mappings) {
            const { locator, value } = mapping;

            try {
                const element = this.domActions.findElement(locator);

                if (!element) {
                    results.push({
                        locator,
                        success: false,
                        error: 'Element not found'
                    });
                    continue;
                }

                // Highlight element
                this.overlay.highlightElement(element);

                // Fill value
                if (options?.clear_before) {
                    element.value = '';
                }

                await this.domActions.typeIntoElement(
                    element,
                    value,
                    options?.typing_delay_ms || 0
                );

                results.push({ locator, success: true });
            } catch (error) {
                results.push({
                    locator,
                    success: false,
                    error: error.message
                });
            }
        }

        return { field_results: results };
    }

    async clickElement(data) {
        const { locator, click_type } = data;

        const element = this.domActions.findElement(locator);

        if (!element) {
            throw new Error('Element not found');
        }

        // Highlight and click
        this.overlay.highlightElement(element);
        await this.domActions.clickElement(element, click_type);

        return { success: true };
    }

    async extractData(data) {
        const { extraction_spec } = data;

        return this.extractor.extract(extraction_spec);
    }

    async scrollPage(data) {
        const { direction, distance, target_locator, smooth } = data;

        if (target_locator) {
            const element = this.domActions.findElement(target_locator);
            if (element) {
                element.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto' });
            }
        } else {
            const scrollAmount = direction === 'down' ? distance : -distance;
            window.scrollBy({
                top: scrollAmount,
                behavior: smooth ? 'smooth' : 'auto'
            });
        }

        return { success: true };
    }

    async checkCondition(data) {
        const { condition_type, condition_value } = data;

        switch (condition_type) {
            case 'element_present':
                const element = this.domActions.findElement({
                    strategy: 'css',
                    value: condition_value
                });
                return { met: !!element };

            case 'element_visible':
                const visElement = this.domActions.findElement({
                    strategy: 'css',
                    value: condition_value
                });
                return {
                    met: visElement && this.domActions.isElementVisible(visElement)
                };

            case 'url_matches':
                const regex = new RegExp(condition_value);
                return { met: regex.test(window.location.href) };

            case 'text_present':
                return { met: document.body.innerText.includes(condition_value) };

            default:
                return { met: false };
        }
    }
}

// Initialize
const browserAutomationContent = new BrowserAutomationContent();
```

**content/dom-actions.js:**

```javascript
class DOMActions {
    findElement(locator) {
        const { strategy, value } = locator;

        switch (strategy) {
            case 'css':
                return document.querySelector(value);

            case 'xpath':
                const result = document.evaluate(
                    value,
                    document,
                    null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                    null
                );
                return result.singleNodeValue;

            case 'id':
                return document.getElementById(value);

            case 'name':
                return document.querySelector(`[name="${value}"]`);

            case 'semantic':
                // Try to find by label text, placeholder, aria-label, etc.
                return this.findBySemantic(value);

            default:
                throw new Error(`Unknown locator strategy: ${strategy}`);
        }
    }

    findBySemantic(description) {
        // Try various semantic selectors
        const selectors = [
            `[aria-label*="${description}" i]`,
            `[placeholder*="${description}" i]`,
            `label:has-text("${description}") input`,
            `button:has-text("${description}")`,
            `a:has-text("${description}")`
        ];

        for (const selector of selectors) {
            try {
                const element = document.querySelector(selector);
                if (element) return element;
            } catch (e) {
                // Some selectors might not be valid
            }
        }

        // Fallback: search by text content
        const xpath = `//*[contains(text(), "${description}")]`;
        const result = document.evaluate(
            xpath,
            document,
            null,
            XPathResult.FIRST_ORDERED_NODE_TYPE,
            null
        );

        return result.singleNodeValue;
    }

    async typeIntoElement(element, text, delayMs = 0) {
        // Focus element
        element.focus();

        // Type character by character for human-like behavior
        if (delayMs > 0) {
            for (const char of text) {
                element.value += char;
                element.dispatchEvent(new Event('input', { bubbles: true }));
                await new Promise(resolve => setTimeout(resolve, delayMs));
            }
        } else {
            element.value = text;
            element.dispatchEvent(new Event('input', { bubbles: true }));
        }

        // Trigger change event
        element.dispatchEvent(new Event('change', { bubbles: true }));
    }

    async clickElement(element, clickType = 'single') {
        // Scroll into view
        element.scrollIntoView({ block: 'center' });

        // Wait a bit for scroll
        await new Promise(resolve => setTimeout(resolve, 100));

        switch (clickType) {
            case 'single':
                element.click();
                break;

            case 'double':
                element.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
                break;

            case 'context':
                element.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true }));
                break;
        }
    }

    isElementVisible(element) {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);

        return (
            rect.width > 0 &&
            rect.height > 0 &&
            style.visibility !== 'hidden' &&
            style.display !== 'none' &&
            style.opacity !== '0'
        );
    }

    generateSelector(element) {
        // Generate robust CSS selector
        const id = element.id;
        if (id) {
            return {
                strategy: 'css',
                value: `#${id}`,
                semantic: this.getSemanticInfo(element)
            };
        }

        const name = element.getAttribute('name');
        if (name) {
            return {
                strategy: 'css',
                value: `[name="${name}"]`,
                semantic: this.getSemanticInfo(element)
            };
        }

        // Build selector from tag + classes
        let selector = element.tagName.toLowerCase();
        const classes = Array.from(element.classList).filter(c => !c.startsWith('overlay-'));
        if (classes.length > 0) {
            selector += '.' + classes.join('.');
        }

        // Add nth-child if needed for uniqueness
        const siblings = Array.from(element.parentElement?.children || [])
            .filter(e => e.tagName === element.tagName);

        if (siblings.length > 1) {
            const index = siblings.indexOf(element) + 1;
            selector += `:nth-child(${index})`;
        }

        return {
            strategy: 'css',
            value: selector,
            semantic: this.getSemanticInfo(element)
        };
    }

    getSemanticInfo(element) {
        return {
            label: element.getAttribute('aria-label'),
            placeholder: element.getAttribute('placeholder'),
            text: element.innerText?.substring(0, 50),
            type: element.getAttribute('type'),
            role: element.getAttribute('role')
        };
    }
}
```

**content/extractor.js:**

```javascript
class DataExtractor {
    extract(extractionSpec) {
        const { mode, fields, table_spec } = extractionSpec;

        if (mode === 'simple') {
            return this.extractSimple(fields);
        } else if (mode === 'table') {
            return this.extractTable(table_spec);
        } else {
            throw new Error(`Unknown extraction mode: ${mode}`);
        }
    }

    extractSimple(fields) {
        const data = {};

        for (const field of fields) {
            const { name, locator, attribute } = field;

            const element = new DOMActions().findElement(locator);

            if (!element) {
                data[name] = null;
                continue;
            }

            // Extract requested attribute
            switch (attribute) {
                case 'innerText':
                    data[name] = element.innerText.trim();
                    break;

                case 'innerHTML':
                    data[name] = element.innerHTML;
                    break;

                case 'value':
                    data[name] = element.value;
                    break;

                default:
                    // Custom attribute
                    data[name] = element.getAttribute(attribute);
            }
        }

        return { structured_data: data, metadata: { fields_extracted: fields.length } };
    }

    extractTable(tableSpec) {
        const { row_locator, columns } = tableSpec;

        const rows = document.querySelectorAll(row_locator.value);
        const data = [];

        for (const row of rows) {
            const rowData = {};

            for (const column of columns) {
                const { column_name, cell_locator, attribute } = column;

                // Find cell within this row
                const cell = row.querySelector(cell_locator.value);

                if (cell) {
                    rowData[column_name] = attribute === 'innerText'
                        ? cell.innerText.trim()
                        : cell.getAttribute(attribute);
                } else {
                    rowData[column_name] = null;
                }
            }

            data.push(rowData);
        }

        return {
            structured_data: data,
            metadata: {
                rows_extracted: data.length,
                columns: columns.length
            }
        };
    }
}
```

**content/overlay.js:**

```javascript
class OverlayManager {
    constructor() {
        this.cursor = null;
        this.highlightBox = null;
        this.elementPickerActive = false;
        this.elementPickerCallback = null;

        this.createOverlayElements();
    }

    createOverlayElements() {
        // Create cursor element
        this.cursor = document.createElement('div');
        this.cursor.id = 'vandalizer-cursor';
        this.cursor.style.cssText = `
            position: fixed;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: rgba(59, 130, 246, 0.5);
            border: 2px solid rgb(59, 130, 246);
            pointer-events: none;
            z-index: 999999;
            display: none;
            transition: all 0.1s ease;
        `;
        document.body.appendChild(this.cursor);

        // Create highlight box
        this.highlightBox = document.createElement('div');
        this.highlightBox.id = 'vandalizer-highlight';
        this.highlightBox.style.cssText = `
            position: absolute;
            border: 2px solid rgb(34, 197, 94);
            background: rgba(34, 197, 94, 0.1);
            pointer-events: none;
            z-index: 999998;
            display: none;
            transition: all 0.2s ease;
        `;
        document.body.appendChild(this.highlightBox);
    }

    setCursor(visible, style = {}) {
        if (visible) {
            this.cursor.style.display = 'block';
            this.trackMouse();
        } else {
            this.cursor.style.display = 'none';
        }

        // Apply custom styles
        Object.assign(this.cursor.style, style);
    }

    trackMouse() {
        document.addEventListener('mousemove', (e) => {
            if (this.cursor.style.display === 'block') {
                this.cursor.style.left = e.clientX + 'px';
                this.cursor.style.top = e.clientY + 'px';
            }
        });
    }

    highlightElement(element, duration = 1000) {
        const rect = element.getBoundingClientRect();

        this.highlightBox.style.display = 'block';
        this.highlightBox.style.left = (rect.left + window.scrollX) + 'px';
        this.highlightBox.style.top = (rect.top + window.scrollY) + 'px';
        this.highlightBox.style.width = rect.width + 'px';
        this.highlightBox.style.height = rect.height + 'px';

        // Auto-hide after duration
        if (duration > 0) {
            setTimeout(() => {
                this.highlightBox.style.display = 'none';
            }, duration);
        }
    }

    enableElementPicker(callback) {
        this.elementPickerActive = true;
        this.elementPickerCallback = callback;

        // Add hover listener
        const hoverHandler = (e) => {
            if (!this.elementPickerActive) return;

            e.stopPropagation();
            this.highlightElement(e.target, 0);
        };

        // Add click listener
        const clickHandler = (e) => {
            if (!this.elementPickerActive) return;

            e.preventDefault();
            e.stopPropagation();

            // Disable picker
            this.elementPickerActive = false;
            this.highlightBox.style.display = 'none';

            // Remove listeners
            document.removeEventListener('mouseover', hoverHandler, true);
            document.removeEventListener('click', clickHandler, true);

            // Call callback with picked element
            if (this.elementPickerCallback) {
                this.elementPickerCallback(e.target);
            }
        };

        document.addEventListener('mouseover', hoverHandler, true);
        document.addEventListener('click', clickHandler, true);
    }
}
```

### 2.5 Extension Popup UI

**popup/popup.html:**

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Vandalizer Browser Automation</title>
    <link rel="stylesheet" href="popup.css">
</head>
<body>
    <div class="popup-container">
        <header>
            <h1>Vandalizer</h1>
            <p class="subtitle">Browser Automation</p>
        </header>

        <div id="connection-status" class="status-section">
            <div class="status-indicator" id="status-dot"></div>
            <span id="status-text">Disconnected</span>
        </div>

        <div id="setup-section">
            <h3>Setup</h3>
            <form id="setup-form">
                <label for="backend-url">Backend URL:</label>
                <input type="text" id="backend-url" placeholder="http://localhost:5000" />

                <label for="user-token">User Token:</label>
                <input type="text" id="user-token" placeholder="Your auth token" />

                <button type="submit">Connect</button>
            </form>
        </div>

        <div id="active-section" style="display: none;">
            <h3>Active Sessions</h3>
            <div id="sessions-list">
                <p class="no-sessions">No active sessions</p>
            </div>

            <button id="disconnect-btn" class="secondary">Disconnect</button>
        </div>

        <footer>
            <p class="version">v1.0.0</p>
        </footer>
    </div>

    <script src="popup.js"></script>
</body>
</html>
```

**popup/popup.js:**

```javascript
document.addEventListener('DOMContentLoaded', async () => {
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const setupSection = document.getElementById('setup-section');
    const activeSection = document.getElementById('active-section');
    const setupForm = document.getElementById('setup-form');
    const disconnectBtn = document.getElementById('disconnect-btn');
    const backendUrlInput = document.getElementById('backend-url');
    const userTokenInput = document.getElementById('user-token');

    // Load saved config
    const config = await chrome.storage.local.get(['backendUrl', 'userToken', 'connected']);

    if (config.backendUrl) {
        backendUrlInput.value = config.backendUrl;
    }

    if (config.userToken) {
        userTokenInput.value = config.userToken;
    }

    // Check connection status
    checkConnectionStatus();

    // Setup form submission
    setupForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const backendUrl = backendUrlInput.value;
        const userToken = userTokenInput.value;

        // Save config
        await chrome.storage.local.set({
            backendUrl,
            userToken,
            connected: true
        });

        // Trigger connection in background script
        chrome.runtime.sendMessage({ action: 'connect_to_backend' });

        setTimeout(checkConnectionStatus, 1000);
    });

    // Disconnect button
    disconnectBtn.addEventListener('click', async () => {
        await chrome.storage.local.set({ connected: false });
        chrome.runtime.sendMessage({ action: 'disconnect_from_backend' });

        setupSection.style.display = 'block';
        activeSection.style.display = 'none';
        updateStatus('disconnected');
    });

    async function checkConnectionStatus() {
        // Ask background script for status
        chrome.runtime.sendMessage({ action: 'get_connection_status' }, (response) => {
            if (response && response.connected) {
                updateStatus('connected');
                setupSection.style.display = 'none';
                activeSection.style.display = 'block';
                loadActiveSessions();
            } else {
                updateStatus('disconnected');
                setupSection.style.display = 'block';
                activeSection.style.display = 'none';
            }
        });
    }

    function updateStatus(status) {
        if (status === 'connected') {
            statusDot.className = 'status-indicator connected';
            statusText.textContent = 'Connected';
        } else {
            statusDot.className = 'status-indicator disconnected';
            statusText.textContent = 'Disconnected';
        }
    }

    async function loadActiveSessions() {
        // Ask background for active sessions
        chrome.runtime.sendMessage({ action: 'get_active_sessions' }, (response) => {
            const sessionsList = document.getElementById('sessions-list');

            if (response && response.sessions && response.sessions.length > 0) {
                sessionsList.innerHTML = '';

                for (const session of response.sessions) {
                    const sessionEl = document.createElement('div');
                    sessionEl.className = 'session-item';
                    sessionEl.innerHTML = `
                        <strong>Session ${session.id.substring(0, 8)}</strong>
                        <span class="session-state">${session.state}</span>
                    `;
                    sessionsList.appendChild(sessionEl);
                }
            } else {
                sessionsList.innerHTML = '<p class="no-sessions">No active sessions</p>';
            }
        });
    }

    // Auto-refresh sessions every 3 seconds
    setInterval(() => {
        if (activeSection.style.display !== 'none') {
            loadActiveSessions();
        }
    }, 3000);
});
```

## Phase 3: Frontend UI Integration

### 3.1 Workflow Step Modal

**New Template:** `app/templates/workflows/workflow_steps/workflow_add_browser_automation_modal.html`

```html
{% extends "workflows/workflow_steps/workflow_step_base_modal.html" %}

{% block modal_title %}Add Browser Automation Step{% endblock %}

{% block modal_body %}
<div class="browser-automation-config">
    <div class="section">
        <h4>Target Website</h4>
        <div class="form-group">
            <label for="initial-url">Starting URL</label>
            <input type="url" id="initial-url" class="form-control"
                   placeholder="https://example.com" />
        </div>

        <div class="form-group">
            <label for="allowed-domains">Allowed Domains (comma-separated)</label>
            <input type="text" id="allowed-domains" class="form-control"
                   placeholder="example.com, subdomain.example.com" />
            <small class="form-text text-muted">
                Leave empty to allow all domains
            </small>
        </div>
    </div>

    <div class="section">
        <h4>Actions</h4>
        <div id="actions-list" class="actions-list">
            <!-- Actions will be added here dynamically -->
        </div>

        <div class="actions-toolbar">
            <button type="button" class="btn btn-sm btn-outline-primary"
                    onclick="addAction('navigate')">
                <i class="bi bi-arrow-right-circle"></i> Navigate
            </button>
            <button type="button" class="btn btn-sm btn-outline-primary"
                    onclick="addAction('ensure_login')">
                <i class="bi bi-shield-check"></i> Require Login
            </button>
            <button type="button" class="btn btn-sm btn-outline-primary"
                    onclick="addAction('fill_form')">
                <i class="bi bi-input-cursor-text"></i> Fill Form
            </button>
            <button type="button" class="btn btn-sm btn-outline-primary"
                    onclick="addAction('click')">
                <i class="bi bi-cursor"></i> Click
            </button>
            <button type="button" class="btn btn-sm btn-outline-primary"
                    onclick="addAction('wait_for')">
                <i class="bi bi-hourglass"></i> Wait For
            </button>
            <button type="button" class="btn btn-sm btn-outline-primary"
                    onclick="addAction('extract')">
                <i class="bi bi-download"></i> Extract Data
            </button>
        </div>
    </div>

    <div class="section">
        <h4>Output Settings</h4>

        <div class="form-check">
            <input type="checkbox" id="enable-summarization" class="form-check-input" checked />
            <label for="enable-summarization" class="form-check-label">
                Generate natural language summary
            </label>
        </div>

        <div id="summarization-config" class="mt-2">
            <label for="summary-prompt">Summary Instructions</label>
            <textarea id="summary-prompt" class="form-control" rows="3"
                      placeholder="Based on the extracted data, provide a summary that..."></textarea>

            <label for="model-select" class="mt-2">Model</label>
            <select id="model-select" class="form-control">
                <option value="claude-sonnet-4-5">Claude Sonnet 4.5</option>
                <option value="claude-opus-4-5">Claude Opus 4.5</option>
                <option value="claude-haiku-4">Claude Haiku 4</option>
            </select>
        </div>
    </div>
</div>
{% endblock %}

{% block modal_footer %}
<button type="button" class="btn btn-secondary" data-dismiss="modal">Cancel</button>
<button type="button" class="btn btn-primary" onclick="saveBrowserAutomationStep()">
    Add Step
</button>
{% endblock %}

{% block modal_scripts %}
<script src="{{ url_for('static', filename='js/browser_automation_builder.js') }}"></script>
{% endblock %}
```

### 3.2 Action Configuration UI Components

**New File:** `app/static/js/browser_automation_builder.js`

```javascript
let actions = [];
let actionIdCounter = 0;

function addAction(actionType) {
    const actionId = `action-${actionIdCounter++}`;
    const action = {
        action_id: actionId,
        type: actionType,
        config: getDefaultConfigForAction(actionType)
    };

    actions.push(action);
    renderActions();
}

function getDefaultConfigForAction(actionType) {
    switch (actionType) {
        case 'navigate':
            return { url: '', wait_for: null };
        case 'ensure_login':
            return {
                detection_rules: { url_pattern: '', element_selector: '' },
                instruction_to_user: ''
            };
        case 'fill_form':
            return { fields: [], options: { clear_before: true } };
        case 'click':
            return { locator: { strategy: 'css', value: '' } };
        case 'wait_for':
            return { condition_type: 'element_present', condition_value: '', timeout_ms: 5000 };
        case 'extract':
            return { extraction_spec: { mode: 'simple', fields: [] } };
        default:
            return {};
    }
}

function renderActions() {
    const container = document.getElementById('actions-list');
    container.innerHTML = '';

    if (actions.length === 0) {
        container.innerHTML = '<p class="text-muted">No actions configured yet</p>';
        return;
    }

    actions.forEach((action, index) => {
        const actionEl = createActionElement(action, index);
        container.appendChild(actionEl);
    });
}

function createActionElement(action, index) {
    const div = document.createElement('div');
    div.className = 'action-item card mb-2';
    div.innerHTML = `
        <div class="card-header d-flex justify-content-between align-items-center">
            <span>
                <strong>${index + 1}.</strong>
                ${getActionIcon(action.type)}
                ${getActionLabel(action.type)}
            </span>
            <div>
                <button class="btn btn-sm btn-outline-secondary" onclick="editAction(${index})">
                    <i class="bi bi-pencil"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="removeAction(${index})">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </div>
        <div class="card-body">
            ${renderActionConfig(action)}
        </div>
    `;

    return div;
}

function getActionIcon(type) {
    const icons = {
        navigate: '<i class="bi bi-arrow-right-circle"></i>',
        ensure_login: '<i class="bi bi-shield-check"></i>',
        fill_form: '<i class="bi bi-input-cursor-text"></i>',
        click: '<i class="bi bi-cursor"></i>',
        wait_for: '<i class="bi bi-hourglass"></i>',
        extract: '<i class="bi bi-download"></i>'
    };
    return icons[type] || '';
}

function getActionLabel(type) {
    const labels = {
        navigate: 'Navigate',
        ensure_login: 'Ensure User Login',
        fill_form: 'Fill Form',
        click: 'Click',
        wait_for: 'Wait For',
        extract: 'Extract Data'
    };
    return labels[type] || type;
}

function renderActionConfig(action) {
    switch (action.type) {
        case 'navigate':
            return `
                <div class="form-group mb-0">
                    <label>URL</label>
                    <input type="url" class="form-control form-control-sm"
                           value="${action.config.url || ''}"
                           onchange="updateActionConfig('${action.action_id}', 'url', this.value)" />
                    <small class="text-muted">Supports template variables: {{previous_step.field}}</small>
                </div>
            `;

        case 'ensure_login':
            return `
                <div class="form-group">
                    <label>Instructions for User</label>
                    <textarea class="form-control form-control-sm" rows="2"
                              onchange="updateActionConfig('${action.action_id}', 'instruction_to_user', this.value)"
                    >${action.config.instruction_to_user || ''}</textarea>
                </div>
                <div class="form-group mb-0">
                    <label>Login Detection (URL pattern or element selector)</label>
                    <input type="text" class="form-control form-control-sm"
                           value="${action.config.detection_rules?.url_pattern || ''}"
                           placeholder="^https://example\\.com/dashboard"
                           onchange="updateActionConfig('${action.action_id}', 'detection_url_pattern', this.value)" />
                </div>
            `;

        case 'fill_form':
            return `
                <div class="form-group mb-0">
                    <label>Form Fields</label>
                    <div id="fields-${action.action_id}">
                        ${renderFormFields(action)}
                    </div>
                    <button class="btn btn-sm btn-outline-primary mt-2"
                            onclick="addFormField('${action.action_id}')">
                        Add Field
                    </button>
                </div>
            `;

        case 'click':
            return `
                <div class="form-group mb-0">
                    <label>Element Selector</label>
                    <div class="input-group input-group-sm">
                        <input type="text" class="form-control"
                               value="${action.config.locator?.value || ''}"
                               placeholder="button[type='submit']"
                               onchange="updateActionConfig('${action.action_id}', 'selector', this.value)" />
                        <button class="btn btn-outline-secondary"
                                onclick="pickElement('${action.action_id}')">
                            <i class="bi bi-cursor"></i> Pick
                        </button>
                    </div>
                </div>
            `;

        case 'extract':
            return `
                <div class="form-group mb-0">
                    <label>Fields to Extract</label>
                    <div id="extract-fields-${action.action_id}">
                        ${renderExtractFields(action)}
                    </div>
                    <button class="btn btn-sm btn-outline-primary mt-2"
                            onclick="addExtractField('${action.action_id}')">
                        Add Field
                    </button>
                </div>
            `;

        default:
            return '<p class="text-muted mb-0">No additional configuration needed</p>';
    }
}

function renderFormFields(action) {
    const fields = action.config.fields || [];

    if (fields.length === 0) {
        return '<p class="text-muted">No fields configured</p>';
    }

    return fields.map((field, i) => `
        <div class="input-group input-group-sm mb-1">
            <input type="text" class="form-control" placeholder="Selector"
                   value="${field.locator?.value || ''}" />
            <input type="text" class="form-control" placeholder="Value or {{variable}}"
                   value="${field.value || ''}" />
            <button class="btn btn-outline-danger"
                    onclick="removeFormField('${action.action_id}', ${i})">
                <i class="bi bi-x"></i>
            </button>
        </div>
    `).join('');
}

function renderExtractFields(action) {
    const fields = action.config.extraction_spec?.fields || [];

    if (fields.length === 0) {
        return '<p class="text-muted">No extraction fields configured</p>';
    }

    return fields.map((field, i) => `
        <div class="input-group input-group-sm mb-1">
            <input type="text" class="form-control" placeholder="Field name"
                   value="${field.name || ''}" />
            <input type="text" class="form-control" placeholder="Selector"
                   value="${field.locator?.value || ''}" />
            <select class="form-control">
                <option value="innerText" ${field.attribute === 'innerText' ? 'selected' : ''}>Text</option>
                <option value="innerHTML" ${field.attribute === 'innerHTML' ? 'selected' : ''}>HTML</option>
                <option value="href" ${field.attribute === 'href' ? 'selected' : ''}>Link</option>
                <option value="src" ${field.attribute === 'src' ? 'selected' : ''}>Image</option>
            </select>
            <button class="btn btn-outline-danger"
                    onclick="removeExtractField('${action.action_id}', ${i})">
                <i class="bi bi-x"></i>
            </button>
        </div>
    `).join('');
}

function updateActionConfig(actionId, key, value) {
    const action = actions.find(a => a.action_id === actionId);
    if (!action) return;

    // Handle nested config keys
    if (key === 'url') {
        action.config.url = value;
    } else if (key === 'selector') {
        action.config.locator = { strategy: 'css', value: value };
    } else if (key === 'detection_url_pattern') {
        action.config.detection_rules = action.config.detection_rules || {};
        action.config.detection_rules.url_pattern = value;
    } else if (key === 'instruction_to_user') {
        action.config.instruction_to_user = value;
    }

    renderActions();
}

function removeAction(index) {
    actions.splice(index, 1);
    renderActions();
}

function pickElement(actionId) {
    // Send message to extension to enable element picker
    alert('Element picker feature: Click on any element in the controlled tab to select it');
    // TODO: Implement actual element picker integration
}

function saveBrowserAutomationStep() {
    const initialUrl = document.getElementById('initial-url').value;
    const allowedDomains = document.getElementById('allowed-domains').value
        .split(',')
        .map(d => d.trim())
        .filter(d => d.length > 0);

    const summarizationEnabled = document.getElementById('enable-summarization').checked;
    const summaryPrompt = document.getElementById('summary-prompt').value;
    const model = document.getElementById('model-select').value;

    // Add initial navigate action if URL provided
    if (initialUrl && !actions.some(a => a.type === 'navigate')) {
        actions.unshift({
            action_id: `action-initial`,
            type: 'navigate',
            config: { url: initialUrl }
        });
    }

    const stepData = {
        workflow_step_id: '{{ workflow_step.id }}',
        actions: actions,
        summarization: {
            enabled: summarizationEnabled,
            prompt_template: summaryPrompt
        },
        allowed_domains: allowedDomains,
        model: model,
        timeout_seconds: 300
    };

    // Save via AJAX
    fetch('/workflows/add_browser_automation_step', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(stepData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Close modal and refresh
            $('#browserAutomationModal').modal('hide');
            location.reload();
        } else {
            alert('Error saving step: ' + data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Failed to save browser automation step');
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    renderActions();

    // Toggle summarization config visibility
    document.getElementById('enable-summarization').addEventListener('change', (e) => {
        document.getElementById('summarization-config').style.display =
            e.target.checked ? 'block' : 'none';
    });
});
```

### 3.3 Workflow Execution UI Updates

**Update:** `app/templates/workflows/workflow.html`

Add UI elements to handle user login prompts during execution:

```html
<!-- Add to the workflow execution status section -->
<div id="user-action-required" class="alert alert-warning" style="display: none;">
    <h5><i class="bi bi-exclamation-triangle"></i> Action Required</h5>
    <p id="user-action-message"></p>
    <button class="btn btn-primary" id="confirm-action-btn">I've Completed This Step</button>
</div>
```

**Update:** `app/static/js/workflow_execution.js`

```javascript
function pollWorkflowStatus(workflowResultId) {
    const interval = setInterval(async () => {
        const response = await fetch(`/workflows/result/${workflowResultId}/status`);
        const data = await response.json();

        // Update progress
        updateProgressBar(data.num_steps_completed, data.num_steps_total);
        updateCurrentStep(data.current_step_name, data.current_step_detail);

        // Check if user action required (e.g., login)
        if (data.requires_user_action) {
            showUserActionPrompt(data.current_step_detail, data.session_id);
        }

        // Check if complete
        if (data.status === 'completed' || data.status === 'failed') {
            clearInterval(interval);
            showFinalResult(data);
        }
    }, 2000);
}

function showUserActionPrompt(message, sessionId) {
    const alertBox = document.getElementById('user-action-required');
    const messageEl = document.getElementById('user-action-message');
    const confirmBtn = document.getElementById('confirm-action-btn');

    messageEl.textContent = message;
    alertBox.style.display = 'block';

    confirmBtn.onclick = async () => {
        // Confirm login completed
        await fetch(`/browser_automation/session/${sessionId}/confirm_login`, {
            method: 'POST'
        });

        alertBox.style.display = 'none';
    };
}
```

### 3.4 Add to Workflow Step Type Selector

**Update:** `app/templates/workflows/workflow_steps/new_workflow_task_modal.html`

```html
<!-- Add new button to the task type selector -->
<button type="button" class="task-type-btn"
        onclick="openBrowserAutomationModal()">
    <i class="bi bi-browser-chrome"></i>
    <span>Browser Automation</span>
    <small>Navigate sites, fill forms, extract data</small>
</button>

<script>
function openBrowserAutomationModal() {
    // Close current modal
    $('#newWorkflowTaskModal').modal('hide');

    // Load browser automation modal
    const workflowStepId = '{{ workflow_step.id }}';
    fetch(`/workflows/add_browser_automation_step?workflow_step_id=${workflowStepId}`)
        .then(response => response.text())
        .then(html => {
            document.body.insertAdjacentHTML('beforeend', html);
            $('#browserAutomationModal').modal('show');
        });
}
</script>
```

## Phase 4: Testing & Deployment

### 4.1 Testing Strategy

**Backend Unit Tests:**

```python
# tests/test_browser_automation.py

def test_browser_session_creation():
    service = BrowserAutomationService()
    session = service.create_session(
        user_id="test-user",
        workflow_result_id="test-workflow",
        allowed_domains=["example.com"]
    )

    assert session.session_id is not None
    assert session.state == SessionState.CREATED


def test_browser_automation_node():
    node = BrowserAutomationNode(data={
        "actions": [
            {
                "type": "navigate",
                "url": "https://example.com"
            }
        ],
        "summarization": {"enabled": False}
    })

    # Mock service
    # ... test node.process()


def test_variable_interpolation():
    node = BrowserAutomationNode(data={...})

    action = {
        "type": "fill_form",
        "fields": [
            {
                "locator": {"strategy": "css", "value": "#name"},
                "value": "{{previous_step.customer_name}}"
            }
        ]
    }

    inputs = {"customer_name": "John Doe"}

    interpolated = node._interpolate_variables(action, inputs)

    assert interpolated["fields"][0]["value"] == "John Doe"
```

**Extension Integration Tests:**

```javascript
// chrome-extension/tests/integration.test.js

describe('Browser Automation Extension', () => {
    test('connects to backend WebSocket', async () => {
        // Mock WebSocket server
        // Test connection handshake
    });

    test('executes navigate command', async () => {
        // Send command, verify navigation
    });

    test('fills form fields', async () => {
        // Create test page with form
        // Send fill_form command
        // Verify values entered
    });

    test('extracts data correctly', async () => {
        // Create test page with data
        // Send extract command
        // Verify extracted structure
    });
});
```

**End-to-End Test:**

```python
# tests/test_e2e_browser_workflow.py

def test_complete_browser_workflow():
    """
    Test a complete workflow:
    1. Navigate to form
    2. Fill customer search
    3. Extract invoice data
    4. Summarize results
    """

    # Create workflow with browser automation step
    workflow = create_test_workflow_with_browser_step()

    # Start execution
    result = execute_workflow(workflow, documents=[])

    # Verify final output
    assert result.status == "completed"
    assert "invoice_total" in result.final_output["raw_data"]
    assert len(result.final_output["summary"]) > 0
```

### 4.2 Security Considerations

**Implemented Security Measures:**

1. **Domain Allowlisting:**
   - Workflows declare `allowed_domains`
   - Extension enforces domain restrictions
   - Prevents malicious site access

2. **No Credential Storage:**
   - User logs in manually in their browser
   - No passwords transmitted to backend
   - Sessions use detection rules only

3. **User Confirmation:**
   - `ensure_login` step requires explicit user action
   - "I've completed this step" button
   - Prevents automated credential entry

4. **WebSocket Authentication:**
   - Token-based auth on WebSocket connection
   - User ID validation on all commands
   - Session ownership verification

5. **Content Security:**
   - Content scripts sandboxed per tab
   - No access to other tabs/windows
   - Limited to declared permissions

### 4.3 Performance Optimization

**Optimization Strategies:**

1. **Parallel Extraction:**
   - Multiple extract fields in single DOM query pass
   - Batch selector lookups

2. **Smart Waiting:**
   - Polling with exponential backoff
   - Event-driven navigation detection
   - Avoid fixed sleep() calls

3. **Session Reuse:**
   - Keep tab open between steps
   - Maintain cookies/localStorage
   - Reduce navigation overhead

4. **Streaming Progress:**
   - Real-time preview updates
   - Incremental extraction results
   - User feedback during long operations

### 4.4 Deployment Checklist

**Backend:**

- [ ] Add `browser_automation.py` service
- [ ] Implement `BrowserAutomationNode` in `workflow.py`
- [ ] Add routes in new blueprint `browser_automation/routes.py`
- [ ] Update workflow routes with browser automation modal endpoint
- [ ] Configure WebSocket support (Flask-SocketIO or similar)
- [ ] Add environment variables for WebSocket URL
- [ ] Update requirements.txt with WebSocket dependencies

**Frontend:**

- [ ] Create browser automation modal template
- [ ] Add `browser_automation_builder.js` to static files
- [ ] Update workflow execution UI for user action prompts
- [ ] Add browser automation button to task type selector
- [ ] Update CSS for new UI elements

**Chrome Extension:**

- [ ] Package extension files
- [ ] Configure manifest.json with production URLs
- [ ] Create icons (16x16, 48x48, 128x128)
- [ ] Test extension on Chrome Web Store submission requirements
- [ ] Create privacy policy document
- [ ] Submit for Chrome Web Store review

**Documentation:**

- [ ] User guide: How to install extension
- [ ] User guide: Creating browser automation workflows
- [ ] User guide: Handling login steps
- [ ] Developer docs: Adding new action types
- [ ] Security documentation
- [ ] Example workflows

## Phase 5: Future Enhancements

### 5.1 Advanced Features (Post-MVP)

**Headless Mode:**
- Server-side Playwright integration
- For non-login-required workflows
- Faster execution, no user browser needed

**Visual Workflow Builder:**
- Record browser actions in real-time
- Generate workflow configuration automatically
- "Record & Replay" mode

**Smart Selectors:**
- AI-powered element locators
- Resilient to page changes
- Natural language element descriptions

**Conditional Logic:**
- If/else branches based on extracted data
- Loop over multiple search results
- Error handling and retries

**Multi-Tab Orchestration:**
- Coordinate actions across multiple tabs
- Cross-reference data from different sites
- Parallel data extraction

**Data Validation:**
- Schema validation for extracted data
- Type coercion (string to number, date parsing)
- Required field checks

**Browser Session Persistence:**
- Save cookies/localStorage between workflow runs
- Reuse authenticated sessions
- "Stay logged in" support

### 5.2 Integration Opportunities

**Zapier/Make.com Style:**
- Pre-built templates for common sites
- Community-shared workflow library
- One-click workflow installation

**API Mode:**
- Trigger workflows via REST API
- Webhook callbacks for completion
- Scheduled workflow execution

**Collaboration:**
- Share workflows with team members
- Version control for workflows
- Approval workflows for production use

## Appendix A: Message Protocol Reference

### Command Messages (Backend → Extension)

| Command | Payload Fields | Response |
|---------|---------------|----------|
| `start_session` | `initial_url`, `mode`, `allowed_domains` | `{ tabId, url }` |
| `navigate` | `target_url`, `wait_for` | `{ success: true }` |
| `fill_form` | `field_mappings`, `options` | `{ field_results: [...] }` |
| `click` | `locator`, `click_type`, `post_click_wait` | `{ success: true }` |
| `wait_for` | `condition_type`, `condition_value`, `timeout_ms` | `{ success: true }` |
| `extract` | `extraction_spec` | `{ structured_data, metadata }` |
| `scroll` | `direction`, `distance`, `target_locator` | `{ success: true }` |
| `end_session` | `close_tab` | `{ success: true }` |

### Event Messages (Extension → Backend)

| Event | Payload Fields | Triggered By |
|-------|---------------|--------------|
| `session_status_changed` | `session_id`, `new_status`, `reason` | Session state transitions |
| `navigation_complete` | `url`, `title`, `load_time_ms` | Page load finished |
| `condition_met` | `condition_type`, `elapsed_ms` | wait_for success |
| `condition_timeout` | `condition_type`, `reason` | wait_for timeout |
| `extraction_result` | `structured_data`, `metadata` | Extract complete |
| `login_state_changed` | `is_logged_in`, `detection_method` | Login detected |
| `error` | `severity`, `source`, `message`, `stack` | Any error |
| `element_picked` | `locator`, `semantic` | User picked element |

## Appendix B: Example Workflows

### Example 1: Simple Form Submission

**Use Case:** Search for a customer and extract invoice total

**Configuration:**

```json
{
  "actions": [
    {
      "type": "navigate",
      "url": "https://invoices.example.com/search"
    },
    {
      "type": "ensure_login",
      "detection_rules": {
        "url_pattern": "^https://invoices\\.example\\.com/dashboard"
      },
      "instruction_to_user": "Please log into the invoice system"
    },
    {
      "type": "fill_form",
      "fields": [
        {
          "locator": {"strategy": "css", "value": "input[name='customer']"},
          "value": "{{document.customer_name}}"
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
      "condition_value": ".results-table"
    },
    {
      "type": "extract",
      "extraction_spec": {
        "mode": "simple",
        "fields": [
          {
            "name": "invoice_total",
            "locator": {"strategy": "css", "value": ".invoice-amount"},
            "attribute": "innerText"
          }
        ]
      }
    }
  ],
  "summarization": {
    "enabled": true,
    "prompt_template": "The invoice total for this customer is: {extracted_data.invoice_total}"
  }
}
```

### Example 2: Multi-Step Research

**Use Case:** Look up company info, then find related articles

**Configuration:**

```json
{
  "actions": [
    {
      "type": "navigate",
      "url": "https://companydb.example.com/search"
    },
    {
      "type": "fill_form",
      "fields": [
        {
          "locator": {"strategy": "css", "value": "#company-name"},
          "value": "{{previous_step.company}}"
        }
      ]
    },
    {
      "type": "click",
      "locator": {"strategy": "css", "value": "#search-btn"}
    },
    {
      "type": "extract",
      "extraction_spec": {
        "mode": "simple",
        "fields": [
          {
            "name": "company_id",
            "locator": {"strategy": "css", "value": ".company-id"},
            "attribute": "innerText"
          }
        ]
      }
    }
  ]
}
```

Then in next workflow step:

```json
{
  "actions": [
    {
      "type": "navigate",
      "url": "https://news.example.com/company/{{previous_step.company_id}}"
    },
    {
      "type": "extract",
      "extraction_spec": {
        "mode": "table",
        "row_locator": {"strategy": "css", "value": ".article-row"},
        "columns": [
          {
            "column_name": "title",
            "cell_locator": {"strategy": "css", "value": ".article-title"},
            "attribute": "innerText"
          },
          {
            "column_name": "date",
            "cell_locator": {"strategy": "css", "value": ".article-date"},
            "attribute": "innerText"
          }
        ]
      }
    }
  ]
}
```

---

## Implementation Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Backend Foundation | 1-2 weeks | None |
| Phase 2: Chrome Extension | 2-3 weeks | Phase 1 |
| Phase 3: Frontend UI | 1-2 weeks | Phase 1, 2 |
| Phase 4: Testing & Deployment | 1 week | Phase 1, 2, 3 |
| Phase 5: Future Enhancements | Ongoing | MVP complete |

**Total MVP Timeline:** 5-8 weeks

---

## Conclusion

This plan provides a complete architecture for integrating browser automation into the Vandalizer workflow system. The design:

- Leverages existing workflow patterns (Node-based execution)
- Maintains security (user-controlled login, no credential storage)
- Provides flexibility (template variables, natural language summaries)
- Scales well (WebSocket communication, session management)
- Offers great UX (visual workflow builder, element picker, real-time progress)

The modular design allows for incremental implementation and testing, with clear extension points for future enhancements.
