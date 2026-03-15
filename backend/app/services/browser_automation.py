"""Browser automation session management and Chrome extension communication.

Ported from Flask app/utilities/browser_automation.py.
Uses FastAPI WebSockets instead of Socket.IO.
Uses Redis for cross-process command/response coordination.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import redis

logger = logging.getLogger(__name__)


class SessionState(Enum):
    CREATED = "created"
    CONNECTING = "connecting"
    READY_NO_LOGIN = "ready_no_login"
    WAITING_FOR_LOGIN = "waiting_for_login"
    WAITING_FOR_REAUTH = "waiting_for_reauth"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class BrowserAutomationSession:
    """Represents a single browser automation session tied to a workflow execution."""

    def __init__(self, session_id: str, user_id: str, workflow_result_id: str, allowed_domains: list[str]):
        self.session_id = session_id
        self.user_id = user_id
        self.workflow_result_id = workflow_result_id
        self.state = SessionState.CREATED
        self.allowed_domains = allowed_domains
        self.pending_commands: dict = {}
        self.last_heartbeat = datetime.now(timezone.utc)
        self.tab_id: str | None = None
        self.audit_trail: list[dict] = []
        self.screenshots: list[dict] = []

    def transition_to(self, new_state: SessionState, reason: str | None = None):
        logger.info("Session %s: %s -> %s (%s)", self.session_id, self.state.value, new_state.value, reason)
        self.state = new_state

    def is_active(self) -> bool:
        return self.state in (
            SessionState.READY_NO_LOGIN,
            SessionState.WAITING_FOR_LOGIN,
            SessionState.WAITING_FOR_REAUTH,
            SessionState.ACTIVE,
        )


class BrowserAutomationService:
    """Manages all browser automation sessions.

    Singleton. Commands to the Chrome extension are sent via WebSocket connections
    stored per user_id. Responses are coordinated through Redis.
    """

    _instance: BrowserAutomationService | None = None

    @classmethod
    def get_instance(cls) -> BrowserAutomationService:
        if cls._instance is None:
            cls._instance = BrowserAutomationService()
        return cls._instance

    def __init__(self):
        self.sessions: dict[str, BrowserAutomationSession] = {}
        self.websocket_connections: dict[str, object] = {}  # user_id -> WebSocket
        self._redis: redis.Redis | None = None
        self._current_model: str | None = None

    @property
    def redis_client(self) -> redis.Redis:
        if self._redis is None:
            redis_host = os.environ.get("redis_host", "localhost")
            self._redis = redis.Redis(host=redis_host, port=6379, db=0)
        return self._redis

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def create_session(self, user_id: str, workflow_result_id: str, allowed_domains: list[str]) -> BrowserAutomationSession:
        session_id = str(uuid.uuid4())
        session = BrowserAutomationSession(session_id, user_id, workflow_result_id, allowed_domains)
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> BrowserAutomationSession | None:
        return self.sessions.get(session_id)

    def start_session(self, session_id: str, initial_url: str | None = None) -> dict | None:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        payload = {
            "initial_url": initial_url,
            "mode": "new_tab",
            "allowed_domains": session.allowed_domains,
        }

        result = self.send_command(session, "start_session", payload)

        try:
            self.send_command(session, "start_session_monitoring", {"sessionId": session_id}, wait_for_response=False)
        except Exception as e:
            logger.warning("Failed to start session monitoring: %s", e)

        return result

    def end_session(self, session_id: str, close_tab: bool = False):
        session = self.get_session(session_id)
        if session:
            try:
                self.send_command(session, "end_session", {"close_tab": close_tab}, wait_for_response=False)
            except Exception:
                pass
            session.transition_to(SessionState.COMPLETED)

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    def execute_action(self, session_id: str, action_config: dict) -> dict | None:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        action_type = action_config["type"]

        if "config" in action_config:
            config = action_config["config"]
        else:
            config = {k: v for k, v in action_config.items() if k != "type"}

        payload = config.copy()

        if action_type == "navigate":
            payload = {"url": config.get("url") or config.get("target_url"), "wait_for": config.get("wait_for")}
        elif action_type == "click":
            payload = {
                "locator": config.get("locator"),
                "click_type": config.get("click_type", "single"),
                "post_click_wait": config.get("wait_after"),
            }
        elif action_type == "extract":
            payload = {"extraction_spec": config.get("extraction_spec", config)}
        elif action_type == "extract_info":
            question = config.get("question", "")
            model = config.get("model") or self._current_model or "gpt-4"
            result = self.extract_information_with_llm(session_id, question, model=model)
            return {"structured_data": {"extracted_info": result.get("answer"), "found": result.get("found", False)}}
        elif action_type == "wait_for":
            payload = {
                "condition_type": config.get("condition_type"),
                "condition_value": config.get("condition_value"),
                "timeout_ms": config.get("timeout_ms", 5000),
            }
        elif action_type == "extract_by_example":
            page_content = self.send_command(session, "get_page_content", {})
            html = (page_content or {}).get("html", "")
            model = getattr(self, "_current_model", None) or "gpt-4"
            extracted = self.extract_by_example_with_llm(session_id, html, config.get("examples", []), model=model)
            return {"structured_data": extracted}

        return self.send_command(session, action_type, payload)

    def execute_action_with_stack(self, session_id: str, action: dict) -> dict | None:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session.state == SessionState.WAITING_FOR_REAUTH:
            self._wait_for_reauth(session_id)

        self.record_audit_event(session_id, "action_start", {
            "action_type": action.get("type"),
            "description": action.get("description", "Unknown action"),
        })

        if "target" in action:
            if isinstance(action["target"], str):
                action["target_stack"] = [{"type": "css", "value": action["target"], "priority": 1}]
            elif isinstance(action["target"], dict) and "strategies" in action["target"]:
                action["target_stack"] = action["target"]["strategies"]
            elif isinstance(action["target"], dict) and "locator" in action["target"]:
                action["target_stack"] = [action["target"]["locator"]]
            else:
                action["target_stack"] = [{"type": "css", "value": str(action["target"]), "priority": 1}]

        action_copy = action.copy()
        if "target_stack" in action:
            if "config" not in action_copy:
                action_copy["config"] = {}
            action_copy["config"]["target_stack"] = action["target_stack"]
            action_copy["target_stack"] = action["target_stack"]

        try:
            result = self.execute_action(session_id, action_copy)
            self.record_audit_event(session_id, "action_success", {"action_type": action.get("type"), "result": result})
            return result
        except Exception as e:
            self.record_audit_event(session_id, "action_failure", {"action_type": action.get("type"), "error": str(e)})
            raise

    # ------------------------------------------------------------------
    # Assertions
    # ------------------------------------------------------------------

    def execute_assertion(self, session_id: str, assertion: dict) -> dict:
        assertion_type = assertion.get("type")
        handlers = {
            "text_present": self._assert_text_present,
            "element_present": self._assert_element_present,
            "url_matches": self._assert_url_matches,
            "value_equals": self._assert_value_equals,
        }
        handler = handlers.get(assertion_type)
        if not handler:
            raise ValueError(f"Unknown assertion type: {assertion_type}")

        result = handler(session_id, assertion)
        if not result["passed"] and assertion.get("on_failure") == "fail":
            raise AssertionError(f"Assertion failed: {result['message']}")
        return result

    def _assert_text_present(self, session_id: str, assertion: dict) -> dict:
        session = self.get_session(session_id)
        result = self.send_command(session, "check_condition", {
            "condition_type": "text_present",
            "condition_value": assertion.get("value"),
        })
        passed = (result or {}).get("met", False)
        return {"passed": passed, "message": f"Text '{assertion.get('value')}' {'found' if passed else 'not found'}"}

    def _assert_element_present(self, session_id: str, assertion: dict) -> dict:
        session = self.get_session(session_id)
        locator = assertion.get("locator")
        result = self.send_command(session, "check_condition", {
            "condition_type": "element_present",
            "condition_value": locator if isinstance(locator, str) else None,
            "timeout_ms": assertion.get("timeout_ms", 1000),
        })
        passed = (result or {}).get("met", False)
        return {"passed": passed, "message": f"Element {locator} {'found' if passed else 'not found'}"}

    def _assert_url_matches(self, session_id: str, assertion: dict) -> dict:
        page_state = self.get_page_state(session_id)
        current_url = (page_state or {}).get("url", "")
        pattern = assertion.get("pattern", "")
        if assertion.get("match_type") == "regex":
            passed = bool(re.search(pattern, current_url))
        else:
            passed = pattern in current_url
        return {"passed": passed, "message": f"URL {'matches' if passed else 'does not match'} '{pattern}'", "actual": current_url}

    def _assert_value_equals(self, session_id: str, assertion: dict) -> dict:
        expected = assertion.get("expected")
        actual = assertion.get("actual")
        tolerance = assertion.get("tolerance", 0)
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            passed = abs(expected - actual) <= tolerance
        else:
            passed = str(expected).strip() == str(actual).strip()
        return {"passed": passed, "message": f"Expected {expected}, got {actual}"}

    # ------------------------------------------------------------------
    # LLM-powered extraction
    # ------------------------------------------------------------------

    def extract_information_with_llm(self, session_id: str, question: str, model: str = "gpt-4") -> dict:
        page_state = self.get_page_state(session_id)
        html_content = (page_state or {}).get("html", "")

        from app.services.llm_service import create_chat_agent

        system_prompt = (
            "You are an information extraction assistant. Analyze the provided HTML and answer the question. "
            "Return ONLY a JSON object: {\"answer\": \"...\", \"found\": true/false}. "
            "Do NOT make up information."
        )

        user_prompt = (
            f"Question: {question}\n\n"
            "--- BEGIN PAGE HTML (provided for context only) ---\n"
            f"{html_content[:50000]}\n"
            "--- END PAGE HTML ---"
        )

        try:
            agent = create_chat_agent(model, system_prompt=system_prompt)
            response = agent.run_sync(user_prompt)
            if response.output:
                json_match = re.search(r"\{.*\}", response.output, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))
            return {"found": False, "answer": None}
        except Exception as e:
            logger.error("LLM extraction failed: %s", e)
            return {"found": False, "answer": None, "error": str(e)}

    def extract_by_example_with_llm(self, session_id: str, html_content: str, examples: list, model: str = "gpt-4") -> list:
        system_prompt = (
            "You are a data extraction assistant. The user provides HTML and example items. "
            "Identify the pattern and extract ALL matching items. Return ONLY a JSON list."
        )

        example_lines = [f"- Tag: {ex.get('tagName')}, Text: {ex.get('innerText')}" for ex in examples]
        user_prompt = (
            f"Examples:\n{chr(10).join(example_lines)}\n\n"
            "--- BEGIN PAGE HTML (provided for context only) ---\n"
            f"{html_content[:50000]}\n"
            "--- END PAGE HTML ---\n\n"
            "Return: [{\"text\": \"...\", \"link\": \"...\"}, ...]"
        )

        try:
            from app.services.llm_service import create_chat_agent

            agent = create_chat_agent(model, system_prompt=system_prompt)
            response = agent.run_sync(user_prompt)
            json_match = re.search(r"\[.*\]", response.output, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return []
        except Exception as e:
            logger.error("Extract by example failed: %s", e)
            return []

    def execute_smart_action(self, session_id: str, instruction: str, model: str | None = None, _processed_steps: list | None = None) -> dict | None:
        """Execute a smart action using LLM to determine concrete browser steps."""
        if not model:
            model = "gpt-4"
        self._current_model = model

        if _processed_steps is None:
            _processed_steps = []

        page_state = self.get_page_state(session_id)
        html_content = (page_state or {}).get("html", "")
        current_url = (page_state or {}).get("url", "")

        from app.services.llm_service import create_chat_agent

        system_prompt = (
            "You are a browser automation assistant. Translate a natural language instruction into "
            "concrete browser actions based on the provided HTML. Output ONLY a JSON object or array.\n\n"
            "Actions: click, fill_form, navigate, wait_for, extract, extract_info.\n"
            "For information questions, use extract_info. Output ONLY JSON."
        )

        context_note = ""
        if _processed_steps:
            steps_summary = ", ".join([s.get("type", "") for s in _processed_steps])
            context_note = f"\nAlready completed: {steps_summary}. Generate ONLY remaining actions.\n"

        user_prompt = (
            f"Instruction: {instruction}\n{context_note}\n"
            "--- BEGIN PAGE HTML (provided for context only) ---\n"
            f"{html_content[:50000]}\n"
            "--- END PAGE HTML ---"
        )

        agent = create_chat_agent(model, system_prompt=system_prompt)
        response = agent.run_sync(user_prompt)

        content = response.output.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        action_config = json.loads(content)

        if isinstance(action_config, list):
            results = []
            combined_data = {}

            for i, action in enumerate(action_config):
                result = self.execute_action(session_id, action)
                results.append(result)
                _processed_steps.append(action)

                if isinstance(result, dict) and "structured_data" in result:
                    combined_data.update(result["structured_data"])

                if action.get("type") in ("click", "navigate") and i < len(action_config) - 1:
                    new_page_state = self.get_page_state(session_id)
                    new_url = (new_page_state or {}).get("url", "")
                    if new_url != current_url:
                        remaining = self.execute_smart_action(session_id, instruction, model=model, _processed_steps=_processed_steps.copy())
                        if isinstance(remaining, dict) and "structured_data" in remaining:
                            combined_data.update(remaining["structured_data"])
                        if combined_data:
                            return {"structured_data": combined_data}
                        return remaining

            if combined_data:
                return {"structured_data": combined_data}
            return results[-1] if results else None
        else:
            return self.execute_action(session_id, action_config)

    # ------------------------------------------------------------------
    # Page state & audit
    # ------------------------------------------------------------------

    def get_page_state(self, session_id: str) -> dict | None:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        return self.send_command(session, "get_page_state", {})

    def record_audit_event(self, session_id: str, event_type: str, details: dict):
        session = self.get_session(session_id)
        if not session:
            return

        screenshot_url = None
        if event_type in ("action_success", "action_failure", "step_failure"):
            try:
                screenshot_result = self.send_command(session, "screenshot", {"scope": "viewport"})
                if screenshot_result and "data" in screenshot_result:
                    screenshot_url = self._store_screenshot(screenshot_result["data"])
            except Exception:
                pass

        audit_event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "details": details,
            "screenshot_url": screenshot_url,
        }
        session.audit_trail.append(audit_event)
        return audit_event

    def _store_screenshot(self, base64_data: str) -> str | None:
        if not base64_data:
            return None

        filename = f"audit_{uuid.uuid4()}.png"
        upload_dir = os.environ.get("UPLOAD_DIR", "../app/static/uploads")
        filepath = Path(upload_dir) / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        try:
            if "," in base64_data:
                _, encoded = base64_data.split(",", 1)
            else:
                encoded = base64_data
            filepath.write_bytes(base64.b64decode(encoded))
            return f"/static/uploads/{filename}"
        except Exception as e:
            logger.error("Error saving screenshot: %s", e)
            return None

    # ------------------------------------------------------------------
    # Session expiration handling
    # ------------------------------------------------------------------

    def handle_session_expired(self, session_id: str, expired_info: dict):
        session = self.get_session(session_id)
        if not session:
            return
        session.transition_to(SessionState.WAITING_FOR_REAUTH, f"Login detected at {expired_info.get('url')}")

    def resume_session_after_reauth(self, session_id: str):
        session = self.get_session(session_id)
        if not session:
            return
        session.transition_to(SessionState.ACTIVE, "User resumed session")

    def _wait_for_reauth(self, session_id: str, timeout: int = 300):
        """Block until session is no longer WAITING_FOR_REAUTH."""
        session = self.get_session(session_id)
        if not session:
            return
        start = time.time()
        while session.state == SessionState.WAITING_FOR_REAUTH and time.time() - start < timeout:
            time.sleep(1.0)
        if session.state == SessionState.WAITING_FOR_REAUTH:
            raise TimeoutError("Re-authentication timeout")

    # ------------------------------------------------------------------
    # WebSocket / extension communication
    # ------------------------------------------------------------------

    def register_websocket(self, user_id: str, ws):
        self.websocket_connections[user_id] = ws
        logger.info("Registered WebSocket for user %s", user_id)

    def unregister_websocket(self, user_id: str):
        self.websocket_connections.pop(user_id, None)

    async def send_to_extension_async(self, user_id: str, message: dict) -> bool:
        """Send message to extension via WebSocket (async — for FastAPI WebSocket handler)."""
        ws = self.websocket_connections.get(user_id)
        if ws:
            try:
                await ws.send_json(message)
                return True
            except Exception as e:
                logger.error("Failed to send to extension for user %s: %s", user_id, e)
                return False
        logger.warning("No WebSocket connection for user %s", user_id)
        return False

    def send_to_extension_via_redis(self, user_id: str, message: dict) -> bool:
        """Publish message via Redis for the WebSocket handler to pick up (sync — for Celery workers)."""
        try:
            channel = f"browser_automation:outgoing:{user_id}"
            self.redis_client.publish(channel, json.dumps(message))
            return True
        except Exception as e:
            logger.error("Redis publish failed: %s", e)
            return False

    def send_command(self, session: BrowserAutomationSession | str, command_name: str, payload: dict, timeout_ms: int = 30000, wait_for_response: bool = True) -> dict | None:
        """Send command to extension and optionally wait for response via Redis."""
        if isinstance(session, str):
            session = self.get_session(session)
        if not session:
            raise ValueError("Session not found")

        request_id = str(uuid.uuid4())
        message = {
            "type": "command",
            "command_name": command_name,
            "request_id": request_id,
            "session_id": session.session_id,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Try async WebSocket first, fall back to Redis pub/sub
        ws = self.websocket_connections.get(session.user_id)
        if ws:
            # We're in the WebSocket handler process — send directly via Redis publish
            # (the WebSocket handler subscribes and forwards)
            self.send_to_extension_via_redis(session.user_id, message)
        else:
            success = self.send_to_extension_via_redis(session.user_id, message)
            if not success:
                raise ConnectionError(f"Could not send command to extension for user {session.user_id}")

        if not wait_for_response:
            return None

        # Poll Redis for response
        response_key = f"browser_automation:response:{request_id}"
        timeout_seconds = timeout_ms / 1000.0
        elapsed = 0.0
        poll_interval = 0.1

        while elapsed < timeout_seconds:
            response_json = self.redis_client.get(response_key)
            if response_json:
                self.redis_client.delete(response_key)
                response = json.loads(response_json)
                if response.get("status") == "error":
                    raise Exception(f"Extension error: {response.get('message')}")
                return response.get("data")
            time.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Command {command_name} timed out after {timeout_ms}ms")

    def handle_response(self, request_id: str, payload: dict):
        """Store response from extension in Redis."""
        response_key = f"browser_automation:response:{request_id}"
        self.redis_client.setex(response_key, 60, json.dumps(payload))

    def handle_extension_event(self, session_id: str, event_name: str, payload: dict):
        """Process incoming event from extension."""
        session = self.get_session(session_id)
        if not session:
            return

        if event_name == "session_expired":
            self.handle_session_expired(session_id, payload)
        elif event_name == "session_restored":
            if session.state == SessionState.WAITING_FOR_REAUTH:
                session.transition_to(SessionState.ACTIVE, "Session restored")
                self.record_audit_event(session_id, "session_restored", payload)
        elif event_name == "session_failed":
            session.transition_to(SessionState.FAILED, payload.get("reason"))

    def extract_data(self, session_id: str, extraction_spec: dict) -> dict | None:
        session = self.get_session(session_id)
        return self.send_command(session, "extract", {"extraction_spec": extraction_spec})

    def wait_for_user_login(self, session_id: str, detection_rules: dict, instruction: str):
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        session.transition_to(SessionState.WAITING_FOR_LOGIN, "Workflow requested user login")
        self.send_command(session, "monitor_login", {"detection_rules": detection_rules}, wait_for_response=False)
