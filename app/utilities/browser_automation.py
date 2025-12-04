import uuid
import json
import logging
from enum import Enum
from datetime import datetime
from app.utilities.workflow import Node

logger = logging.getLogger(__name__)

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
        session_id = str(uuid.uuid4())
        session = BrowserAutomationSession(session_id, user_id, workflow_result_id, allowed_domains)
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def start_session(self, session_id, initial_url=None):
        """Send start_session command to extension"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

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
        # Map action type to command name if needed, or use directly
        command_name = action_type
        
        # Some actions might need payload restructuring
        payload = action_config.copy()
        if "type" in payload:
            del payload["type"]
            
        # Special handling for specific actions if needed
        if action_type == "navigate":
            payload = {
                "target_url": action_config.get("url"),
                "wait_for": action_config.get("wait_for")
            }
        elif action_type == "click":
             payload = {
                "locator": action_config.get("locator"),
                "click_type": action_config.get("click_type", "single"),
                "post_click_wait": action_config.get("wait_after")
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
        """Register extension websocket connection"""
        self.websocket_connections[user_id] = ws_connection
        logger.info(f"Registered WebSocket for user {user_id}")

    def send_to_extension(self, user_id, message):
        """Send message to extension via WebSocket"""
        ws = self.websocket_connections.get(user_id)
        if ws:
            # This assumes ws is an object with a send method (like Flask-SocketIO emit or similar)
            # Adjust based on actual WebSocket implementation
            try:
                ws.send(json.dumps(message))
                return True
            except Exception as e:
                logger.error(f"Failed to send to extension for user {user_id}: {e}")
                return False
        else:
            logger.warning(f"No WebSocket connection for user {user_id}")
            return False

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
            
        # Wait for response
        import threading
        event = threading.Event()
        future = {"event": event, "response": None}
        self.response_futures[request_id] = future
        
        signaled = event.wait(timeout=timeout_ms/1000.0)
        del self.response_futures[request_id]
        
        if not signaled:
            raise TimeoutError(f"Command {command_name} timed out after {timeout_ms}ms")
            
        response = future["response"]
        if response.get("status") == "error":
            raise Exception(f"Extension error: {response.get('message')}")
            
        return response.get("data")
