from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.utilities.browser_automation import BrowserAutomationService, SessionState
import json

browser_automation_bp = Blueprint('browser_automation', __name__)

@browser_automation_bp.route("/websocket/connect")
def browser_automation_websocket():
    """
    WebSocket endpoint for Chrome extension to connect.
    Handles bidirectional communication for browser control.
    
    Note: This is a placeholder. Real WebSocket implementation depends on 
    the server setup (e.g. Flask-SocketIO, gevent-websocket, etc.)
    For this implementation plan, we assume the extension connects here 
    and upgrades to a WebSocket.
    """
    # In a real app with Flask-SocketIO, this would be handled differently.
    # We'll just return a message saying this should be a WS connection.
    return jsonify({"message": "This endpoint expects a WebSocket connection"}), 426

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
@login_required
def get_session_status(session_id):
    """
    Poll endpoint for real-time session status updates.
    Returns current state, pending actions, errors, etc.
    """
    service = BrowserAutomationService.get_instance()
    session = service.get_session(session_id)
    
    if not session:
        return jsonify({"error": "Session not found"}), 404
        
    if session.user_id != str(current_user.id):
        return jsonify({"error": "Unauthorized"}), 403
        
    return jsonify({
        "session_id": session.session_id,
        "state": session.state.value,
        "last_heartbeat": session.last_heartbeat.isoformat() if session.last_heartbeat else None
    })
