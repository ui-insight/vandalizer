import uuid
import json
import logging
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)

# Import socketio for sending messages to extension
from app import socketio

class SessionState(Enum):
    CREATED = "created"
    CONNECTING = "connecting"
    READY_NO_LOGIN = "ready_no_login"
    WAITING_FOR_LOGIN = "waiting_for_login"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"

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
        self.tab_id = None

    def transition_to(self, new_state, reason=None):
        """Transition session state with validation"""
        logger.info(f"Session {self.session_id} transitioning from {self.state} to {new_state}. Reason: {reason}")
        self.state = new_state

    def is_active(self):
        """Check if session is in an active state"""
        return self.state in [SessionState.READY_NO_LOGIN, SessionState.WAITING_FOR_LOGIN, SessionState.ACTIVE]

class BrowserAutomationService:
    """Main service for managing all browser automation sessions"""
    
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = BrowserAutomationService()
        return cls._instance

    def __init__(self):
        self.sessions = {}  # session_id -> BrowserAutomationSession
        self.websocket_connections = {}  # user_id -> websocket connection
        self.response_futures = {} # request_id -> future/event for async waiting

    def create_session(self, user_id, workflow_result_id, allowed_domains):
        """Initialize a new browser automation session"""
        print(f"[Browser Automation] create_session called with user_id: {user_id}")
        session_id = str(uuid.uuid4())
        session = BrowserAutomationSession(session_id, user_id, workflow_result_id, allowed_domains)
        self.sessions[session_id] = session
        print(f"[Browser Automation] Created session {session_id} for user {user_id}")
        return session

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def start_session(self, session_id, initial_url=None):
        """Send start_session command to extension"""
        print(f"[Browser Automation] start_session called for session {session_id}, initial_url: {initial_url}")
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        print(f"[Browser Automation] Session found, user_id: {session.user_id}")

        payload = {
            "initial_url": initial_url,
            "mode": "new_tab", # or attach_current_tab
            "allowed_domains": session.allowed_domains
        }
        
        return self.send_command(session, "start_session", payload)

    def execute_action(self, session_id, action_config):
        """Execute a single action (navigate, fill, click, extract, etc.)"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        action_type = action_config["type"]

        # Handle both formats: with nested "config" (workflow) and without (smart action LLM output)
        if "config" in action_config:
            # Workflow format: { type: "click", config: { locator: ... } }
            config = action_config["config"]
        else:
            # Smart action format: { type: "click", locator: ... }
            # Create config from action_config minus the type field
            config = {k: v for k, v in action_config.items() if k != "type"}

        # Map action type to command name if needed, or use directly
        command_name = action_type

        # Build payload from the config object
        payload = config.copy()

        # Special handling for specific actions if needed
        if action_type == "navigate":
            payload = {
                "url": config.get("url"),
                "wait_for": config.get("wait_for")
            }
        elif action_type == "click":
             payload = {
                "locator": config.get("locator"),
                "click_type": config.get("click_type", "single"),
                "post_click_wait": config.get("wait_after")
            }
        elif action_type == "extract":
            payload = {
                "extraction_spec": config.get("extraction_spec", config)
            }
        elif action_type == "extract_info":
            # This action uses LLM to extract information, not the extension
            question = config.get("question", "")
            # Get the model from: action config > smart action model > default
            model_to_use = config.get("model") or getattr(self, '_current_model', None) or "gpt-4"
            result = self.extract_information_with_llm(session_id, question, model=model_to_use)
            # Return in structured_data format to match extract action
            return {
                "structured_data": {
                    "extracted_info": result.get("answer"),
                    "found": result.get("found", False)
                }
            }
        elif action_type == "wait_for":
            payload = {
                "condition_type": config.get("condition_type"),
                "condition_value": config.get("condition_value"),
                "timeout_ms": config.get("timeout_ms", 5000)
            }

        return self.send_command(session, command_name, payload)

    def wait_for_user_login(self, session_id, detection_rules, instruction):
        """Pause workflow and wait for user login confirmation"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
            
        session.transition_to(SessionState.WAITING_FOR_LOGIN, "Workflow requested user login")
        
        # In a real implementation, we would block here or return a special status
        # For this implementation, we'll rely on the workflow engine to handle the pause/resume
        # via the requires_user_action flag in the result
        
        # We send a command to the extension to start watching for login
        self.send_command(session, "monitor_login", {
            "detection_rules": detection_rules
        }, wait_for_response=False)

    def extract_data(self, session_id, extraction_spec):
        """Extract structured data from current page"""
        session = self.get_session(session_id)
        return self.send_command(session, "extract", {"extraction_spec": extraction_spec})

    def extract_information_with_llm(self, session_id, question, model=None):
        """
        Use LLM to extract information from the current page by analyzing HTML directly.
        This is different from extract_data which uses CSS selectors.

        Args:
            session_id: Browser session ID
            question: Natural language question (e.g., "What is Luke Sheneman's contact information?")
            model: LLM model to use (defaults to "gpt-4" if not specified)

        Returns:
            Dictionary with extracted information
        """
        # Default model if none provided
        if not model:
            model = "gpt-4"

        # Get current page HTML
        page_state = self.get_page_state(session_id)
        html_content = page_state.get("html", "")

        from app.utilities.agents import create_chat_agent

        system_prompt = """
        You are an information extraction assistant. Your job is to analyze HTML content and answer questions about it.

        You will be given:
        1. A question asking for specific information
        2. The HTML content of a web page

        Your task:
        - Search the HTML for the requested information
        - Extract the relevant text content
        - Return ONLY a JSON object with the extracted information
        - If the information is not found, return null for that field

        Response format:
        {
            "answer": "The extracted information as a string",
            "found": true/false
        }

        Rules:
        - Do NOT make up information
        - Extract actual text content from the HTML
        - Be concise but complete
        - If you find multiple relevant pieces of information, include them all
        - Output ONLY the JSON object, no markdown formatting or explanation
        """

        user_prompt = f"""
        Question: {question}

        Page HTML (truncated):
        {html_content[:50000]}
        """

        try:
            agent = create_chat_agent(model)
            logger.info(f"Created chat agent with model: {model}")

            response = agent.run_sync(f"{system_prompt}\n\n{user_prompt}")
            logger.info(f"Got response from LLM for information extraction")

            # Clean up response if it contains markdown code blocks
            content = response.output.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            result = json.loads(content)
            logger.info(f"Smart information extraction result: {result}")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {response.output[:200]}")
            return {"answer": response.output, "found": False}
        except Exception as e:
            logger.error(f"Error during smart information extraction: {e}")
            # Return a basic response instead of failing the whole workflow
            return {"answer": f"Error extracting information: {str(e)}", "found": False}

    def end_session(self, session_id, close_tab=False):
        """Clean up session resources"""
        session = self.get_session(session_id)
        if session:
            try:
                self.send_command(session, "end_session", {"close_tab": close_tab}, wait_for_response=False)
            except:
                pass # Ignore errors during cleanup
            
            session.transition_to(SessionState.COMPLETED)
            # We might want to keep the session object around for a bit for history
            # del self.sessions[session_id]

    # WebSocket management
    def register_websocket(self, user_id, ws_connection):
        """Register extension websocket connection - user_id is email address"""
        # Store in memory for this process
        self.websocket_connections[user_id] = ws_connection
        logger.info(f"Registered WebSocket for user {user_id}")

        # Also store in database for cross-process access (Flask app <-> Celery workers)
        from app.models import User
        user = User.objects(user_id=user_id).first()
        if user:
            user.browser_automation_session_id = ws_connection
            user.save()
            print(f"[Browser Automation] Stored session ID in database for user {user_id}")
        else:
            print(f"[Browser Automation] WARNING: User {user_id} not found in database")

    def send_to_extension(self, user_id, message):
        """Send message to extension via Socket.IO"""
        print(f"[Browser Automation] send_to_extension called with user_id: {user_id}")
        print(f"[Browser Automation] Available connections: {list(self.websocket_connections.keys())}")

        # First check in-memory connections (same process)
        session_id = self.websocket_connections.get(user_id)

        # If not in memory, check database (cross-process)
        if not session_id:
            from app.models import User
            user = User.objects(user_id=user_id).first()
            if user and user.browser_automation_session_id:
                session_id = user.browser_automation_session_id
                print(f"[Browser Automation] Found session ID in database: {session_id}")
            else:
                print(f"[Browser Automation] No session in database for user {user_id}")

        if session_id:
            # Use Socket.IO emit to send to specific client session
            try:
                print(f"[Browser Automation] Emitting command '{message.get('command_name')}' to session {session_id}")
                socketio.emit('command', message, room=session_id, namespace='/browser_automation')
                logger.info(f"Sent command to extension for user {user_id}: {message.get('command_name')}")
                return True
            except Exception as e:
                logger.error(f"Failed to send to extension for user {user_id}: {e}")
                return False
        else:
            print(f"[Browser Automation] ERROR: No WebSocket connection for user {user_id}")
            logger.warning(f"No WebSocket connection for user {user_id}")
            return False

    def handle_response(self, session_id, request_id, payload):
        """Handle response from extension - called by Socket.IO route handler"""
        print(f"[Browser Automation] Received response for request {request_id}: {payload}")

        # Store response in Redis for cross-process coordination
        import redis
        import json

        r = redis.Redis.from_url('redis://localhost:6379')
        response_key = f"browser_automation:response:{request_id}"
        r.setex(response_key, 60, json.dumps(payload))  # Store for 60 seconds
        print(f"[Browser Automation] Stored response in Redis for request {request_id}")

    def handle_event(self, session_id, event_name, payload):
        """Handle event from extension - called by Socket.IO route handler"""
        print(f"[Browser Automation] Received event {event_name}: {payload}")
        # For now, just log events - we can add specific handling later
        pass

    def handle_extension_message(self, user_id, message):
        """Process incoming message from extension"""
        msg_type = message.get("type")

        if msg_type == "response":
            request_id = message.get("request_id")
            if request_id and request_id in self.response_futures:
                # Resolve the future/event
                future = self.response_futures[request_id]
                future["response"] = message.get("payload")
                future["event"].set()

        elif msg_type == "event":
            self._handle_event(message)

        elif msg_type == "heartbeat":
            # Update last seen
            pass

    def _handle_event(self, message):
        session_id = message.get("session_id")
        event_name = message.get("event_name")
        payload = message.get("payload")
        
        session = self.get_session(session_id)
        if not session:
            return
            
        if event_name == "login_state_changed":
            if payload.get("is_logged_in"):
                # We could auto-advance here, but we prefer explicit user confirmation for now
                pass
        elif event_name == "session_failed":
            session.transition_to(SessionState.FAILED, payload.get("reason"))

    def send_command(self, session, command_name, payload, timeout_ms=30000, wait_for_response=True):
        """Send command to extension and track request"""
        request_id = str(uuid.uuid4())

        message = {
            "type": "command",
            "command_name": command_name,
            "request_id": request_id,
            "session_id": session.session_id,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat()
        }

        success = self.send_to_extension(session.user_id, message)
        if not success:
            raise ConnectionError(f"Could not send command to extension for user {session.user_id}")

        if not wait_for_response:
            return None

        # Wait for response using Redis for cross-process coordination
        import redis
        import time
        import json

        r = redis.Redis.from_url('redis://localhost:6379')
        response_key = f"browser_automation:response:{request_id}"

        # Poll Redis for response (Flask app will write it when received)
        timeout_seconds = timeout_ms / 1000.0
        poll_interval = 0.1  # Poll every 100ms
        elapsed = 0

        print(f"[Browser Automation] Waiting for response to request {request_id}...")
        while elapsed < timeout_seconds:
            response_json = r.get(response_key)
            if response_json:
                # Got response!
                r.delete(response_key)  # Clean up
                response = json.loads(response_json)
                print(f"[Browser Automation] Got response from Redis for request {request_id}")

                if response.get("status") == "error":
                    raise Exception(f"Extension error: {response.get('message')}")

                return response.get("data")

            time.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Command {command_name} timed out after {timeout_ms}ms")

    def get_page_state(self, session_id):
        """Get current page HTML from extension"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
            
        return self.send_command(session, "get_page_state", {})

    def execute_smart_action(self, session_id, instruction, model=None, _processed_steps=None):
        """
        Execute a smart action using LLM to determine concrete steps.
        1. Get page state (HTML)
        2. Ask LLM for action
        3. Execute action
        4. If action causes navigation and more steps remain, re-analyze with new page state

        Args:
            session_id: Browser session ID
            instruction: Natural language instruction
            model: LLM model to use (defaults to "gpt-4" if not specified)
            _processed_steps: Internal parameter to track what we've already done (for recursion after navigation)
        """
        if not model:
            model = "gpt-4"

        # Store model on service for use by extract_info actions
        self._current_model = model

        if _processed_steps is None:
            _processed_steps = []

        # 1. Get page state
        page_state = self.get_page_state(session_id)
        html_content = page_state.get("html", "")
        current_url = page_state.get("url", "")

        # 2. Ask LLM
        from app.utilities.agents import create_chat_agent
        
        system_prompt = """
        You are a browser automation assistant. Your goal is to translate a natural language instruction into a concrete browser action based on the provided HTML.

        You must output a JSON object representing the action to take. If the instruction requires multiple steps, output a JSON ARRAY of objects.

        The available actions are:

        1. Click:
        {
            "type": "click",
            "locator": { "strategy": "css", "value": "selector_here" },
            "click_type": "single" (or "double", "context")
        }

        2. Fill Form:
        {
            "type": "fill_form",
            "fields": [
                { "locator": { "strategy": "css", "value": "selector" }, "value": "text_to_type" }
            ]
        }

        3. Navigate:
        {
            "type": "navigate",
            "url": "https://example.com"
        }

        4. Wait:
        {
            "type": "wait_for",
            "condition_type": "element_present",
            "condition_value": "selector",
            "timeout_ms": 5000
        }

        5. Extract Data (using CSS selectors):
        {
            "type": "extract",
            "extraction_spec": {
                "fields": [
                    { "name": "field_name", "locator": { "value": "selector" }, "attribute": "innerText" (or "href", "src") }
                ]
            }
        }

        6. Extract Information (using LLM analysis - PREFERRED for "get information about X" questions):
        {
            "type": "extract_info",
            "question": "What is the person's contact information?"
        }

        Rules:
        - Analyze the HTML to find the most robust selector for the element described in the instruction.
        - Prefer ID or unique attributes over complex paths.
        - If the instruction implies typing, use 'fill_form'.
        - If the instruction implies clicking a link or button, use 'click'.
        - If the instruction asks to "get information about X", "find out about X", or "extract details about X", use 'extract_info' (NOT 'extract').
        - Only use 'extract' when you need to get specific attributes (like href, src) or when you have a clear, simple selector.

        Important:
        - For information extraction questions ("get info about X", "find details about Y"), ALWAYS use 'extract_info' - it's more reliable.
        - Only use 'extract' when you have a specific, simple selector that you can see in the HTML.
        - DO NOT generate complex CSS selectors or assume HTML structure - use 'extract_info' instead.

        Output ONLY the JSON object (or array), no markdown formatting or explanation.
        """
        
        # Build context about what we've already done (for post-navigation re-analysis)
        context_note = ""
        if _processed_steps:
            steps_summary = ", ".join([f"{s.get('type')}" for s in _processed_steps])
            context_note = f"\nIMPORTANT: You have already completed these steps: {steps_summary}. Do NOT repeat them. Only generate actions for the REMAINING parts of the instruction based on the CURRENT page HTML.\n"

        html_snippet = html_content[:50000]

        # Log HTML analysis metadata (without the actual HTML content)
        logger.info(f"Analyzing page: {current_url}")
        logger.info(f"HTML length: {len(html_content)} chars, sending {len(html_snippet)} chars to LLM")

        user_prompt = f"""
        Instruction: {instruction}
        {context_note}
        Current Page HTML (truncated):
        {html_snippet}
        """

        agent = create_chat_agent(model)
        response = agent.run_sync(f"{system_prompt}\n\n{user_prompt}")
        
        try:
            # Clean up response if it contains markdown code blocks
            content = response.output.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            action_config = json.loads(content)
            logger.info(f"Smart action decided: {action_config}")
            
            # 3. Execute action(s)
            if isinstance(action_config, list):
                results = []
                combined_data = {}

                for i, action in enumerate(action_config):
                    logger.info(f"Executing action {i+1}/{len(action_config)}: {action.get('type')}")
                    result = self.execute_action(session_id, action)
                    results.append(result)
                    _processed_steps.append(action)

                    # Collect any extraction data
                    if isinstance(result, dict) and "structured_data" in result:
                        combined_data.update(result["structured_data"])

                    # If this action was a click/navigate and there are more actions to execute,
                    # check if the page changed (navigation occurred)
                    # Note: extract_info doesn't trigger navigation detection since it doesn't interact with the page
                    if action.get("type") in ["click", "navigate"] and i < len(action_config) - 1:
                        # Get new page state to check if URL changed
                        new_page_state = self.get_page_state(session_id)
                        new_url = new_page_state.get("url", "")

                        if new_url != current_url:
                            logger.info(f"Navigation detected: {current_url} -> {new_url}")
                            logger.info(f"Re-analyzing page for remaining actions with fresh HTML")

                            # Recursively call with same instruction but updated processed_steps
                            # The LLM will see what we've done and continue with remaining steps
                            remaining_result = self.execute_smart_action(
                                session_id,
                                instruction,  # Same instruction
                                model=model,
                                _processed_steps=_processed_steps.copy()  # But with context of what's done
                            )

                            # Merge results
                            if isinstance(remaining_result, dict) and "structured_data" in remaining_result:
                                combined_data.update(remaining_result["structured_data"])

                            # Return combined results
                            if combined_data:
                                return {"structured_data": combined_data}
                            return remaining_result

                # No navigation occurred, return all results
                if combined_data:
                    return {"structured_data": combined_data}
                return results[-1] if results else None
            else:
                return self.execute_action(session_id, action_config)
            
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response: {response.output}")
            raise ValueError("LLM failed to produce valid action JSON")
