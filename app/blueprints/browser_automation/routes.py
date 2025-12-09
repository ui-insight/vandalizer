from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from flask_socketio import emit, disconnect
from app.utilities.browser_automation import BrowserAutomationService, SessionState
from app.utilities.auth import get_user_from_token, token_required
from app import socketio
import json

browser_automation_bp = Blueprint('browser_automation', __name__)

# WebSocket event handlers
@socketio.on('connect', namespace='/browser_automation')
def handle_connect(auth):
    """
    Handle Chrome extension WebSocket connection.
    Requires token authentication via auth parameter.
    """
    # Get token from auth dict
    token = auth.get('token') if isinstance(auth, dict) else None

    if not token:
        print("[Browser Automation] Connection rejected: No token provided")
        disconnect()
        return False

    # Validate token
    user = get_user_from_token(token)

    if not user:
        print("[Browser Automation] Connection rejected: Invalid token")
        disconnect()
        return False

    # Register WebSocket connection with the browser automation service
    service = BrowserAutomationService.get_instance()
    # Use user.user_id (email) as the key, not user.id (MongoDB ObjectId)
    # This matches what's used in workflow execution
    service.register_websocket(user.user_id, request.sid)

    print(f"[Browser Automation] User {user.user_id} connected via WebSocket")
    emit('connected', {'status': 'authenticated', 'user_id': user.user_id})
    return True


@socketio.on('disconnect', namespace='/browser_automation')
def handle_disconnect():
    """Handle WebSocket disconnection."""
    print(f"[Browser Automation] Client {request.sid} disconnected")

    # Clear session ID from database for cross-process sync
    from app.models import User
    user = User.objects(browser_automation_session_id=request.sid).first()
    if user:
        user.browser_automation_session_id = None
        user.save()
        print(f"[Browser Automation] Cleared session ID from database for user {user.user_id}")


@socketio.on('message', namespace='/browser_automation')
def handle_message(data):
    """
    Handle messages from Chrome extension.
    Expected format: {type: 'response'|'event', ...}
    """
    print(f"[Browser Automation] Received message: {data}")

    service = BrowserAutomationService.get_instance()

    # Route to appropriate handler based on message type
    msg_type = data.get('type')

    if msg_type == 'response':
        # Extension responding to a command
        service.handle_response(
            request.sid,
            data.get('request_id'),
            data.get('payload')
        )
    elif msg_type == 'event':
        # Extension sending an event (navigation complete, etc.)
        service.handle_event(
            request.sid,
            data.get('event_name'),
            data.get('payload')
        )
    elif msg_type == 'heartbeat':
        # Keep-alive ping
        emit('heartbeat_ack', {'timestamp': data.get('timestamp')})
    else:
        print(f"[Browser Automation] Unknown message type: {msg_type}")


@socketio.on('error', namespace='/browser_automation')
def handle_error(error_data):
    """Handle errors from Chrome extension."""
    print(f"[Browser Automation] Error from client: {error_data}")

@browser_automation_bp.route("/session/<session_id>/confirm_login", methods=["POST"])
@login_required
def confirm_user_login(session_id):
    """
    User clicks "I'm logged in" button in UI.
    Signals session to continue from WAITING_FOR_LOGIN state.
    """
    service = BrowserAutomationService.get_instance()
    session = service.get_session(session_id)
    
    if not session:
        return jsonify({"error": "Session not found"}), 404
        
    if session.user_id != str(current_user.id):
        return jsonify({"error": "Unauthorized"}), 403
        
    if session.state == SessionState.WAITING_FOR_LOGIN:
        session.transition_to(SessionState.ACTIVE, "User confirmed login")
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": "Session is not waiting for login"}), 400

@browser_automation_bp.route("/session/<session_id>/status", methods=["GET"])
@token_required  # Use token auth for API access
def get_session_status(session_id, auth_user):
    """
    Poll endpoint for real-time session status updates.
    Returns current state, pending actions, errors, etc.
    Supports token-based authentication for Chrome extension.
    """
    service = BrowserAutomationService.get_instance()
    session = service.get_session(session_id)

    if not session:
        return jsonify({"error": "Session not found"}), 404

    if session.user_id != str(auth_user.id):
        return jsonify({"error": "Unauthorized"}), 403

    return jsonify({
        "session_id": session.session_id,
        "state": session.state.value,
        "last_heartbeat": session.last_heartbeat.isoformat() if session.last_heartbeat else None
    })


# Test endpoint to verify token authentication
@browser_automation_bp.route("/test_auth", methods=["GET"])
@token_required
def test_auth(auth_user):
    """Test endpoint to verify API token authentication is working."""
    return jsonify({
        "authenticated": True,
        "user_id": auth_user.user_id,
        "user_name": auth_user.name,
        "message": "API token authentication successful"
    })
