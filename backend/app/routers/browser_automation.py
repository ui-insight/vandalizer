"""Browser automation WebSocket endpoint for Chrome extension communication.

Replaces Flask Socket.IO with FastAPI WebSockets.
"""

import asyncio
import json
import logging

from beanie import PydanticObjectId
from fastapi import APIRouter, Cookie, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.user import User
from app.models.workflow import Workflow, WorkflowResult
from app.services import access_control

router = APIRouter()
logger = logging.getLogger(__name__)


class CreateSessionRequest(BaseModel):
    workflow_result_id: str
    allowed_domains: list[str] = []


class NavigateRequest(BaseModel):
    url: str


async def _get_authorized_workflow_result(workflow_result_id: str, user: User) -> WorkflowResult:
    try:
        workflow_result_oid = PydanticObjectId(workflow_result_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Workflow result not found") from exc

    result = await WorkflowResult.get(workflow_result_oid)
    if not result or not result.workflow:
        raise HTTPException(status_code=404, detail="Workflow result not found")

    workflow = await Workflow.get(result.workflow)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow result not found")

    team_access = await access_control.get_team_access_context(user)
    if not access_control.can_view_workflow(workflow, user, team_access):
        raise HTTPException(status_code=404, detail="Workflow result not found")

    return result


# ---------------------------------------------------------------------------
# REST endpoints for session management
# ---------------------------------------------------------------------------


@router.post("/sessions")
async def create_session(req: CreateSessionRequest, user: User = Depends(get_current_user)):
    from app.services.browser_automation import BrowserAutomationService

    workflow_result = await _get_authorized_workflow_result(req.workflow_result_id, user)
    service = BrowserAutomationService.get_instance()
    session = service.create_session(user.user_id, str(workflow_result.id), req.allowed_domains)
    return {
        "session_id": session.session_id,
        "state": session.state.value,
    }


@router.get("/sessions/{session_id}")
async def get_session_status(session_id: str, user: User = Depends(get_current_user)):
    from app.services.browser_automation import BrowserAutomationService

    service = BrowserAutomationService.get_instance()
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Not your session")
    return {
        "session_id": session.session_id,
        "state": session.state.value,
        "audit_trail_count": len(session.audit_trail),
    }


@router.post("/sessions/{session_id}/navigate")
async def navigate_session(session_id: str, req: NavigateRequest, user: User = Depends(get_current_user)):
    from app.services.browser_automation import BrowserAutomationService

    service = BrowserAutomationService.get_instance()
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Not your session")

    result = service.start_session(session_id, initial_url=req.url)
    return {"status": "ok", "result": result}


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, user: User = Depends(get_current_user)):
    from app.services.browser_automation import BrowserAutomationService

    service = BrowserAutomationService.get_instance()
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Not your session")

    service.end_session(session_id)
    return {"status": "ended"}


# ---------------------------------------------------------------------------
# WebSocket endpoint for Chrome extension
# ---------------------------------------------------------------------------


@router.websocket("/ws")
async def browser_automation_ws(
    websocket: WebSocket,
    access_token: str | None = Cookie(default=None),
):
    """WebSocket endpoint for Chrome extension communication.

    Authentication is validated during the handshake via the access_token
    cookie — unauthenticated clients are rejected before the connection
    is accepted.

    Protocol:
    1. Server validates JWT from cookie during handshake.
    2. Extension connects and server registers the connection.
    3. Server forwards commands from Redis pub/sub to the extension.
    4. Extension sends responses/events which are routed back via Redis.
    """
    # Authenticate via cookie before accepting the connection
    from app.config import Settings
    from app.dependencies import get_settings
    from app.models.user import User
    from app.utils.security import decode_token

    settings = get_settings()
    if not access_token:
        await websocket.close(code=4001, reason="Not authenticated")
        return
    payload = decode_token(access_token, settings)
    if not payload or payload.get("type") != "access":
        await websocket.close(code=4001, reason="Invalid token")
        return
    ws_user = await User.find_one(User.user_id == payload["sub"])
    if not ws_user:
        await websocket.close(code=4001, reason="User not found")
        return

    await websocket.accept()

    from app.services.browser_automation import BrowserAutomationService

    service = BrowserAutomationService.get_instance()
    user_id: str | None = ws_user.user_id

    # Background task for forwarding Redis -> WebSocket
    forward_task: asyncio.Task | None = None

    async def _forward_redis_to_ws(uid: str):
        """Subscribe to Redis channel and forward messages to WebSocket."""
        import redis.asyncio as aioredis
        import os

        redis_host = os.environ.get("redis_host", "localhost")
        r = aioredis.Redis(host=redis_host, port=6379, db=0)
        pubsub = r.pubsub()
        channel = f"browser_automation:outgoing:{uid}"

        try:
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
        except Exception as e:
            logger.debug("WebSocket pubsub listener ended: %s", e)
        finally:
            await pubsub.unsubscribe(channel)
            await r.aclose()

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "auth":
                # user_id already validated from JWT during handshake;
                # accept the auth message for protocol compatibility but
                # always use the JWT-authenticated identity.
                service.register_websocket(user_id, websocket)
                await websocket.send_json({"type": "auth_ok"})

                # Start background forwarder
                forward_task = asyncio.create_task(_forward_redis_to_ws(user_id))

            elif msg_type == "response":
                request_id = msg.get("request_id")
                payload = msg.get("payload", {})
                if request_id:
                    service.handle_response(request_id, payload)

            elif msg_type == "event":
                session_id = msg.get("session_id")
                event_name = msg.get("event_name")
                payload = msg.get("payload", {})
                if session_id and event_name:
                    service.handle_extension_event(session_id, event_name, payload)

            elif msg_type == "heartbeat":
                session_id = msg.get("session_id")
                session = service.get_session(session_id) if session_id else None
                if session:
                    from datetime import datetime, timezone
                    session.last_heartbeat = datetime.now(timezone.utc)

    except WebSocketDisconnect:
        logger.info("Browser automation WebSocket disconnected for user %s", user_id)
    except Exception as e:
        logger.error("Browser automation WebSocket error: %s", e)
    finally:
        if user_id:
            service.unregister_websocket(user_id)
        if forward_task:
            forward_task.cancel()
