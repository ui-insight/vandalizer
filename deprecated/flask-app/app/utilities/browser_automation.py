import uuid
import json
import logging
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)

# Import socketio for sending messages to extension
from app import socketio
from app.models import LocatorStrategy
import re
import uuid
import os
import base64

class SessionState(Enum):
    CREATED = "created"
    CONNECTING = "connecting"
    READY_NO_LOGIN = "ready_no_login"
    WAITING_FOR_LOGIN = "waiting_for_login"
    WAITING_FOR_REAUTH = "waiting_for_reauth"  # Session expired, waiting for user to log back in
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
        
        # Audit Trail
        self.audit_trail = [] # List of events
        self.screenshots = [] # List of screenshot metadata

    def transition_to(self, new_state, reason=None):
        """Transition session state with validation"""
        logger.info(f"Session {self.session_id} transitioning from {self.state} to {new_state}. Reason: {reason}")
        self.state = new_state

    def is_active(self):
        """Check if session is in an active state"""
        return self.state in [
            SessionState.READY_NO_LOGIN,
            SessionState.WAITING_FOR_LOGIN,
            SessionState.WAITING_FOR_REAUTH,
            SessionState.ACTIVE
        ]

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
        self.recordings = {} # recording_id -> recording data (temporary)

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

        result = self.send_command(session, "start_session", payload)

        # Automatically start session expiration monitoring
        try:
            self.start_session_monitoring(session_id)
        except Exception as e:
            logger.warning(f"Failed to start session monitoring: {e}")

        return result

    def start_session_monitoring(self, session_id):
        """Start monitoring for session expiration (SSO/Duo timeouts)"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        logger.info(f"Starting session expiration monitoring for session {session_id}")

        payload = {
            "sessionId": session_id
        }

        return self.send_command(session, "start_session_monitoring", payload, wait_for_response=False)

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
                "url": config.get("url") or config.get("target_url"),
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
                "condition_type": config.get("condition_type"),
                "condition_value": config.get("condition_value"),
                "timeout_ms": config.get("timeout_ms", 5000)
            }
        elif action_type == "extract_by_example":
            # Runtime LLM extraction
            examples = config.get("examples", [])
            # Get full page HTML from extension to feed to LLM
            # We use check_condition just to get state or implement a new 'get_state' command?
            # Actually get_page_state exists but might return simplified.
            # Let's request specific HTML.
            
            # Note: We need the HTML to be sent to us. 
            # We can use send_command('get_page_content') if it existed, or eval.
            # For now, let's assume we can get the HTML from the session state or a command.
            
            page_content = self.send_command(session, 'get_page_content', {}) # Need to implement this in extension
            html = page_content.get('html', '')
            
            # Use LLM to find similar items
            model = getattr(self, '_current_model', None) or "gpt-4"
            extracted = self.extract_by_example_with_llm(session_id, html, examples, model=model)
            
            return {
                "structured_data": extracted
            }

        return self.send_command(session, command_name, payload)

    def execute_action_with_stack(self, session_id: str, action: dict) -> dict:
        """Execute action using locator stack with fallback"""
        session = self.get_session(session_id)

        # Check if session is waiting for re-authentication
        if session.state == SessionState.WAITING_FOR_REAUTH:
            logger.info(f"Session {session_id} is waiting for re-authentication, pausing execution...")
            self._wait_for_reauth(session_id)

        # Record start
        self.record_audit_event(session_id, 'action_start', {
            'action_type': action.get('type'),
            'description': action.get('description', 'Unknown action')
        })

        # Build locator stack if target specified
        if 'target' in action:
            if isinstance(action['target'], str):
                # Load from database
                locator_strategy = LocatorStrategy.objects(target_name=action['target']).first()
                if not locator_strategy:
                    # If not found, check if it's just a raw selector string provided as simple target
                    # For legacy compatibility or ad-hoc actions
                    action['target_stack'] = [{'type': 'css', 'value': action['target'], 'priority': 1}]
                else:
                    action['target_stack'] = locator_strategy.strategies
            elif isinstance(action['target'], dict) and 'strategies' in action['target']:
                # Inline locator stack
                action['target_stack'] = action['target']['strategies']
            else:
                # Legacy single locator config or object - convert to stack
                # If target is dict with 'locator', use it
                target = action['target']
                if isinstance(target, dict) and 'locator' in target:
                     # This matches the structure { target: { locator: {...} } }
                     action['target_stack'] = [target['locator']] if 'locator' in target else []
                elif isinstance(target, dict) and 'strategy' in target:
                     # This matches direct locator object
                     action['target_stack'] = [target]
                else:
                     # Fallback
                     action['target_stack'] = [{'type': 'css', 'value': str(target), 'priority': 1}]

        # Send to extension with stack
        # We need to reshape the action for execute_action expectations or call send_command directly
        # execute_action expects 'config' in some cases or direct keys
        
        # Helper to inject stack into payload
        action_copy = action.copy()
        if 'target_stack' in action:
            # Most actions (click, fill) use 'locator' in config. 
            # We add 'target_stack' to the config.
            if 'config' not in action_copy:
                action_copy['config'] = {}
            action_copy['config']['target_stack'] = action['target_stack']
            
            # Also support direct payload structure (smart action)
            action_copy['target_stack'] = action['target_stack']

        try:
            result = self.execute_action(session_id, action_copy)

            # Record which strategy succeeded
            if isinstance(result, dict) and result.get('usedStrategy'):
                 self._record_strategy_success(action.get('target'), result['usedStrategy'])

            # Record success
            self.record_audit_event(session_id, 'action_success', {
                'action_type': action.get('type'),
                'result': result
            })

            return result
        except Exception as e:
            # Check if failure is due to element not found
            error_message = str(e).lower()
            is_element_not_found = any(phrase in error_message for phrase in [
                'element not found',
                'could not find',
                'no such element',
                'selector failed'
            ])

            # Record failure
            self.record_audit_event(session_id, 'action_failure', {
                'action_type': action.get('type'),
                'error': str(e)
            })

            # If element not found and repair is enabled, trigger self-healing
            if is_element_not_found and action.get('on_failure') == 'repair':
                logger.info(f"Triggering self-healing repair for step: {action.get('step_id')}")

                # Trigger repair mode
                repair_result = self._trigger_repair_mode(
                    session_id,
                    action.get('step_id'),
                    action.get('description', 'Unknown element'),
                    action.get('target_stack', [])
                )

                if repair_result.get('success'):
                    # Repair succeeded, update action with new strategies and retry
                    logger.info(f"Repair successful, retrying action with new selectors")
                    action_copy['target_stack'] = repair_result['newStrategies']

                    # Retry the action with new strategies
                    return self.execute_action(session_id, action_copy)
                else:
                    # User cancelled or repair failed
                    logger.warning(f"Repair cancelled or failed")
                    raise Exception(f"Element not found and repair was cancelled: {str(e)}")

            # No repair or different error type
            raise

    def _trigger_repair_mode(self, session_id: str, step_id: str, target_description: str, old_strategies: list) -> dict:
        """
        Trigger self-healing repair mode in the extension.
        Waits for user to select correct element and returns new strategies.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        logger.info(f"Triggering repair mode for step {step_id}: '{target_description}'")

        # Send repair request to extension
        try:
            result = self.send_command(session, 'request_repair', {
                'stepId': step_id,
                'targetDescription': target_description,
                'oldStrategies': old_strategies
            })

            if not result.get('success'):
                logger.warning("Failed to start repair mode in extension")
                return {'success': False, 'error': 'Failed to start repair mode'}

        except Exception as e:
            logger.error(f"Error sending repair command: {e}")
            return {'success': False, 'error': str(e)}

        # Wait for repair completion (user selecting element)
        # The extension will send 'repair_completed' message back to backend
        # We use Redis to coordinate the async response
        repair_key = f"browser_automation:repair:{session_id}:{step_id}"

        # Wait up to 5 minutes for user to complete repair
        timeout = 300  # 5 minutes
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check if repair result is available in Redis
            repair_result_json = self.redis_client.get(repair_key)

            if repair_result_json:
                # Parse result
                repair_result = json.loads(repair_result_json)

                # Clean up Redis key
                self.redis_client.delete(repair_key)

                if repair_result.get('success'):
                    # Save repair to workflow history
                    self._save_repair_to_history(
                        session_id,
                        step_id,
                        old_strategies,
                        repair_result['newStrategies']
                    )

                return repair_result

            # Sleep briefly before checking again
            time.sleep(0.5)

        # Timeout - user didn't complete repair
        logger.warning(f"Repair mode timeout for step {step_id}")
        return {'success': False, 'error': 'User did not complete repair within timeout'}

    def _save_repair_to_history(self, session_id: str, step_id: str, old_strategies: list, new_strategies: list):
        """Save repair to WorkflowRepairHistory"""
        from app.models import WorkflowRepairHistory, Workflow

        session = self.get_session(session_id)
        if not session or not session.workflow_result_id:
            return

        try:
            # Get workflow from result
            from app.models import WorkflowResult
            workflow_result = WorkflowResult.objects(id=session.workflow_result_id).first()
            if not workflow_result or not workflow_result.workflow:
                return

            workflow = workflow_result.workflow

            # Create repair history record
            repair_history = WorkflowRepairHistory(
                workflow_id=str(workflow.id),
                step_id=step_id,
                old_locator={'strategies': old_strategies},
                new_locator={'strategies': new_strategies},
                reason='Element not found - self-healing repair',
                repair_date=datetime.utcnow()
            )
            repair_history.save()

            # Increment workflow version
            if not hasattr(workflow, 'version'):
                workflow.version = 1
            workflow.version += 1
            workflow.updated_at = datetime.utcnow()
            workflow.save()

            logger.info(f"Saved repair to history for workflow {workflow.id}, new version: {workflow.version}")

        except Exception as e:
            logger.error(f"Error saving repair to history: {e}")

    def _record_strategy_success(self, target_name: str, strategy: dict):
        """Update confidence scores based on successful strategy"""
        if not target_name or not isinstance(target_name, str):
            return

        locator = LocatorStrategy.objects(target_name=target_name).first()
        if locator:
            # Boost priority of successful strategy
            # Simple re-ranking: Move successful strategy up, others down
            # Or increment a score. Plan suggests priority manipulation.

            strategies_updated = False
            for s in locator.strategies:
                # Strategy dict comparison
                if s.get('type') == strategy.get('type') and s.get('value') == strategy.get('value'):
                    s['priority'] = max(1, s.get('priority', 5) - 1) # Lower is better? Plan said "sort a-b". JS stack sorts a-b (asc).
                    # So priority 1 is highest.
                    strategies_updated = True
                else:
                    s['priority'] = min(10, s.get('priority', 5) + 1)

            if strategies_updated:
                locator.strategies.sort(key=lambda x: x.get('priority', 5))
                locator.last_tested = datetime.utcnow()
                locator.save()

    def record_audit_event(self, session_id: str, event_type: str, details: dict):
        """Record audit event with screenshot"""
        session = self.get_session(session_id)
        if not session:
            return

        # Take screenshot for significant events
        screenshot_url = None
        if event_type in ['action_success', 'action_failure', 'step_failure']:
            try:
                # We need to make this async safe or fire-and-forget? 
                # For now, explicit call.
                screenshot_result = self.send_command(session_id, 'screenshot', {'scope': 'viewport'})
                if screenshot_result and 'data' in screenshot_result:
                    screenshot_url = self._store_screenshot(screenshot_result['data'])
            except Exception as e:
                logger.error(f"Failed to capture audit screenshot: {e}")

    def handle_download_completed(self, session_id: str, download_info: dict):
        """Handle download complete event"""
        from app.models import WorkflowArtifact
        import pandas as pd
        import os

        session = self.get_session(session_id)
        if not session:
            return

        logger.info(f"Download completed for session {session_id}: {download_info.get('filename')}")

        try:
            # Create artifact
            artifact = WorkflowArtifact(
                workflow_result_id=session.workflow_result_id,
                artifact_type=self._get_artifact_type(download_info.get('mime'), download_info.get('filename')),
                filename=download_info.get('filename'),
                file_path=download_info.get('filename'), # Extension gives filename/relative path
                # Note: We don't have absolute path unless we know download dir. 
                # Assuming simple mapping or just storing name for now.
                created_at=datetime.utcnow()
            )

            # Try to parse if data available? 
            # Note: The extension doesn't send file CONTENT, only metadata. 
            # We can't parse unless the file is on the server (which it typically is if local browser).
            # If browser is remote/user's, we can't parse. 
            # Assuming 'local' execution context for V1 or file is accessible.
            
            # For this Phase, simple logging and recording is 'Success'. 
            # Parsing would require file access.
            
            artifact.save()
            logger.info("Saved download artifact")

        except Exception as e:
            logger.error(f"Error handling download: {e}")

    def _get_artifact_type(self, mime, filename):
        if 'csv' in mime or filename.endswith('.csv'): return 'csv'
        if 'excel' in mime or 'spreadsheet' in mime or filename.endswith('.xlsx'): return 'xlsx'
        if 'pdf' in mime or filename.endswith('.pdf'): return 'pdf'
        return 'other'


    def handle_session_expired(self, session_id: str, expired_info: dict):
        """Handle session expiration event from extension"""
        session = self.get_session(session_id)
        if not session:
            return

        logger.warning(f"Session expired detected for session {session_id}. Info: {expired_info}")
        
        # Transition state
        session.transition_to(SessionState.WAITING_FOR_REAUTH, reason=f"Login detected at {expired_info.get('url')}")
        
        # Notify frontend via WebSocket
        socketio.emit('workflow_paused', {
            'session_id': session_id,
            'reason': 'session_expired',
            'details': expired_info
        }, room=session.user_id)
        
        # We need to pause the execution thread. 
        # Ideally, `execute_workflow` checks session state before each step.
        
    def resume_session_after_reauth(self, session_id: str):
        """Resume session after user logs back in"""
        session = self.get_session(session_id)
        if not session:
            return

        logger.info(f"Resuming session {session_id} after re-authentication")
        session.transition_to(SessionState.ACTIVE, reason="User resumed session")
        
        # Notify execution thread to continue (if using events/conditions)
        # For now, just state change might be enough if execution loop checks state.

        # Record audit event
        audit_event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'details': details,
            'screenshot_url': screenshot_url
        }

        session.audit_trail.append(audit_event)
        # If we were using DB, we'd save here. session.save()
        return audit_event

    def _store_screenshot(self, base64_data: str) -> str:
        """Store screenshot data (Mock implementation for now)"""
        if not base64_data: 
            return None
            
        # In real impl, save to GridFS or S3
        # For now, just return a data URI truncation or placeholder if too large for memory
        # to avoid blowing up memory.
        # Ideally we write to a temp file or static folder.
        
        filename = f"audit_{uuid.uuid4()}.png"
        filepath = os.path.join('app', 'static', 'uploads', filename)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        try:
            # base64_data is usually "data:image/png;base64,...."
            if "," in base64_data:
                header, encoded = base64_data.split(",", 1)
            else:
                encoded = base64_data
                
            data = base64.b64decode(encoded)
            
            with open(filepath, "wb") as f:
                f.write(data)
                
            return f"/static/uploads/{filename}"
        except Exception as e:
            logger.error(f"Error saving screenshot: {e}")
            return None

    def execute_assertion(self, session_id: str, assertion: dict) -> dict:
        """Execute verification step"""
        assertion_type = assertion.get('type')

        handlers = {
            'text_present': self._assert_text_present,
            'element_present': self._assert_element_present,
            'url_matches': self._assert_url_matches,
            'value_equals': self._assert_value_equals,
            # 'table_contains': self._assert_table_contains, # TODO: Implement later
        }

        handler = handlers.get(assertion_type)
        if not handler:
            raise ValueError(f"Unknown assertion type: {assertion_type}")

        result = handler(session_id, assertion)

        if not result['passed']:
            # Take screenshot of failure
            try:
                # We reuse send_command directly to avoid infinite recursion if execute_action wraps this
                session = self.get_session(session_id)
                # screenshot = self.send_command(session, 'screenshot', {}) 
                # result['screenshot'] = screenshot # Implement screenshot support later
                pass
            except Exception:
                pass

            if assertion.get('on_failure') == 'fail':
                raise AssertionError(f"Assertion failed: {result['message']}")

        return result

    def _assert_text_present(self, session_id: str, assertion: dict) -> dict:
        """Check if text is present on page"""
        text = assertion.get('value')
        case_sensitive = assertion.get('case_sensitive', False)

        page_state = self.get_page_state(session_id)
        # Using innerText from body is safer than raw HTML for text assertions
        # But get_page_state usually returns { html: ..., url: ... }
        # We might need to ask extension for text content or parse HTML
        # For robustness, let's ask extension via check_condition which we already have!
        
        session = self.get_session(session_id)
        result = self.send_command(session, 'check_condition', {
            'condition_type': 'text_present',
            'condition_value': text
        })
        
        passed = result.get('met', False)

        return {
            'passed': passed,
            'message': f"Text '{text}' {'found' if passed else 'not found'} on page",
            'expected': text
        }

    def _assert_element_present(self, session_id: str, assertion: dict) -> dict:
        """Check if element exists"""
        locator = assertion.get('locator') # Could be string or dict with stack

        session = self.get_session(session_id)
        
        # Prepare payload with stack if needed
        payload = {
            'condition_type': 'element_present',
            'condition_value': locator if isinstance(locator, str) else None,
            'timeout_ms': assertion.get('timeout_ms', 1000)
        }
        
        # Handle locator stack for assertions
        if isinstance(locator, dict) or (isinstance(locator, str) and LocatorStrategy.objects(target_name=locator).first()):
             # If it's a stack-able locator, we should resolve it
             # Reuse logic from execute_action_with_stack to build stack?
             # For now, let's just pass what we have. If it's a string that matches a DB entry, we should resolve it.
             if isinstance(locator, str):
                 strat = LocatorStrategy.objects(target_name=locator).first()
                 if strat:
                     payload['target_stack'] = strat.strategies
                     
        result = self.send_command(session, 'check_condition', payload)

        passed = result.get('met', False)

        return {
            'passed': passed,
            'message': f"Element {locator} {'found' if passed else 'not found'}",
            'locator': locator
        }

    def _assert_url_matches(self, session_id: str, assertion: dict) -> dict:
        """Check if current URL matches pattern"""
        pattern = assertion.get('pattern')

        page_state = self.get_page_state(session_id)
        current_url = page_state.get('url', '')

        if assertion.get('match_type') == 'regex':
            passed = bool(re.search(pattern, current_url))
        else:
            passed = pattern in current_url

        return {
            'passed': passed,
            'message': f"URL {'matches' if passed else 'does not match'} pattern '{pattern}'",
            'expected': pattern,
            'actual': current_url
        }

    def _assert_value_equals(self, session_id: str, assertion: dict) -> dict:
        """Check if two values are equal (with tolerance for numbers)"""
        expected = assertion.get('expected')
        actual = assertion.get('actual') # Caller should resolve variable before calling
        tolerance = assertion.get('tolerance', 0)

        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            passed = abs(expected - actual) <= tolerance
        else:
            passed = str(expected).strip() == str(actual).strip()

        return {
            'passed': passed,
            'message': f"Expected {expected}, got {actual}",
            'expected': expected,
            'actual': actual,
            'tolerance': tolerance
        }

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

            if response.output:
                # Basic JSON parsing cleanup
                import re
                json_match = re.search(r'\{.*\}', response.output, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))
            
            return {"found": False, "answer": None}

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return {"found": False, "answer": None, "error": str(e)}

    def extract_by_example_with_llm(self, session_id: str, html_content: str, examples: list, model="gpt-4") -> list:
        """
        Extract items similar to the provided examples using an LLM.
        """
        system_prompt = """
        You are an intelligent data extraction assistant.
        The user will provide HTML content and a list of 'example' items that were selected from that page.
        Your task is to identify the pattern and extract ALL items that match that pattern from the HTML.
        
        Return ONLY a JSON list of objects.
        """

        example_descriptions = []
        for ex in examples:
            example_descriptions.append(f"- Tag: {ex.get('tagName')}, Text: {ex.get('innerText')}")

        user_prompt = f"""
        Examples selected by user:
        {chr(10).join(example_descriptions)}

        Page HTML (truncated):
        {html_content[:50000]}

        Extract all items similar to the examples. capture the inner text and any relevant links.
        Return a JSON list: [ {{"text": "...", "link": "..."}}, ... ]
        """

        try:
            agent = create_chat_agent(model)
            response = agent.run_sync(f"{system_prompt}\n\n{user_prompt}")
            
            import re
            json_match = re.search(r'\[.*\]', response.output, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return []
        except Exception as e:
            logger.error(f"Extract by example failed: {e}")
            return []

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
        elif event_name == "session_expired":
            # SSO/Duo session expired - pause workflow
            logger.warning(f"Session {session_id} expired - transitioning to WAITING_FOR_REAUTH")
            session.transition_to(SessionState.WAITING_FOR_REAUTH, "Session expired - SSO/Duo timeout detected")

            # Record audit event
            self.record_audit_event(session_id, 'session_expired', {
                'url': payload.get('url'),
                'title': payload.get('title'),
                'timestamp': payload.get('timestamp')
            })
        elif event_name == "session_restored":
            # User logged back in
            if session.state == SessionState.WAITING_FOR_REAUTH:
                logger.info(f"Session {session_id} restored - transitioning back to ACTIVE")
                session.transition_to(SessionState.ACTIVE, "Session restored - user logged back in")

                # Record audit event
                self.record_audit_event(session_id, 'session_restored', {
                    'url': payload.get('url'),
                    'title': payload.get('title'),
                    'timestamp': payload.get('timestamp')
                })

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
