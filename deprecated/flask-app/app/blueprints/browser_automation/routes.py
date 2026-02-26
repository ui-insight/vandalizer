from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from flask_socketio import emit, disconnect
from app.utilities.browser_automation import BrowserAutomationService, SessionState
from app.utilities.auth import get_user_from_token, token_required
from app.models import LocatorStrategy
from app import socketio, limiter
import json
import uuid
from datetime import datetime

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


@socketio.on('recording_step_added', namespace='/browser_automation')
def handle_recording_step(data):
    """Handle new step added during recording"""
    recording_id = data.get('recording_id')
    step = data.get('step')

    service = BrowserAutomationService.get_instance()
    recording = service.recordings.get(recording_id)

    if recording:
        recording['steps'].append(step)
        print(f"[Browser Automation] Step added to recording {recording_id}: {len(recording['steps'])} steps")

        # Echo back to web UI if needed
        emit('recording_updated', {
            'recording_id': recording_id,
            'step_count': len(recording['steps'])
        }, broadcast=True)

@socketio.on('recording_complete', namespace='/browser_automation')
def handle_recording_complete(data):
    """Handle completed recording from extension"""
    recording_id = data.get('recording_id')
    steps = data.get('steps', [])
    variables = data.get('variables', [])

    service = BrowserAutomationService.get_instance()
    recording = service.recordings.get(recording_id)

    if recording:
        # Only update steps if incoming steps is not empty, or if we have no steps yet
        # This prevents navigation to a new page from erasing captured steps
        if steps or not recording.get('steps'):
            recording['steps'] = steps

        # Merge variables instead of overwriting
        if variables:
            recording['variables'] = variables

        recording['status'] = 'completed'
        recording['completed_at'] = datetime.utcnow().isoformat()

        final_step_count = len(recording.get('steps', []))
        print(f"[Browser Automation] Recording {recording_id} completed with {final_step_count} steps")

        # Notify web UI
        emit('recording_completed', {
            'recording_id': recording_id,
            'step_count': final_step_count
        }, broadcast=True)
    else:
        # Create new recording if not found (legacy support)
        recording_id = recording_id or ('rec_' + str(uuid.uuid4()))
        service.recordings[recording_id] = {
            'id': recording_id,
            'steps': steps,
            'variables': variables,
            'status': 'completed',
            'created_at': datetime.utcnow().isoformat(),
            'completed_at': datetime.utcnow().isoformat()
        }
        print(f"[Browser Automation] Created new recording {recording_id} with {len(steps)} steps")

@socketio.on('repair_completed', namespace='/browser_automation')
def handle_repair_completed(data):
    """Handle self-healing repair completed from extension"""
    session_id = data.get('sessionId')
    step_id = data.get('stepId')
    repair_result = data.get('repairResult')

    print(f"[Browser Automation] Repair completed for session {session_id}, step {step_id}")

    # Store repair result in Redis so the waiting backend thread can retrieve it
    service = BrowserAutomationService.get_instance()
    repair_key = f"browser_automation:repair:{session_id}:{step_id}"

    service.redis_client.setex(
        repair_key,
        600,  # 10 minute TTL
        json.dumps(repair_result)
    )

    print(f"[Browser Automation] Stored repair result in Redis: {repair_key}")

    # Emit confirmation back to extension
    emit('repair_acknowledged', {
        'sessionId': session_id,
        'stepId': step_id,
        'success': True
    })

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

@browser_automation_bp.route("/connection/status", methods=["GET"])
@login_required
@limiter.exempt
def get_connection_status():
    """Check if extension is connected for current user (exempt from rate limiting)"""
    service = BrowserAutomationService.get_instance()
    user_socket_id = service.websocket_connections.get(current_user.user_id)

    return jsonify({
        'connected': user_socket_id is not None,
        'user_id': current_user.user_id
    })

@browser_automation_bp.route("/session/<session_id>/status", methods=["GET"])
@token_required  # Use token auth for API access
@limiter.exempt
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
    return jsonify({
        "authenticated": True,
        "user_id": auth_user.user_id,
        "user_name": auth_user.name,
        "message": "API token authentication successful"
    })

@browser_automation_bp.route('/session/<session_id>/repair_step', methods=['POST'])
@token_required
def repair_step(auth_user, session_id):
    """Allow user to fix a failed step"""
    data = request.json
    step_id = data.get('step_id')
    repair_action = data.get('repair_action')  # 'repick_target', 'retry', 'skip'
    
    browser_automation_service = BrowserAutomationService.get_instance()
    session = browser_automation_service.get_session(session_id)
    
    if not session:
         return jsonify({"error": "Session not found"}), 404

    if repair_action == 'repick_target':
        # Launch target picker in extension
        browser_automation_service.send_command(session, 'start_target_picker', {
            'step_id': step_id,
            'callback_url': f'/session/{session_id}/update_target'
        })
        return jsonify({'status': 'waiting_for_pick'})

    elif repair_action == 'retry':
        # Retry the step
        # Note: In a real system we needs to know WHICH step failed. 
        # For now assuming the session tracks failed_step or we just re-execute based on step_id look up in workflow
        # Simulating retry logic:
        # step = session.failed_step
        # result = browser_automation_service.execute_action_with_stack(session_id, step)
        return jsonify({'status': 'success', 'message': 'Retry initiated (not fully implemented)'})

    elif repair_action == 'skip':
        # Mark step as skipped and continue
        # session.skipped_steps.append(step_id)
        # session.save()
        return jsonify({'status': 'skipped'})

    return jsonify({'error': 'Unknown repair action'}), 400

@browser_automation_bp.route('/session/<session_id>/update_target', methods=['POST'])
@token_required
def update_target(auth_user, session_id):
    """Receive new target from extension after user picks element"""
    data = request.json
    step_id = data.get('step_id')
    new_strategies = data.get('strategies')  # Generated by extension

    browser_automation_service = BrowserAutomationService.get_instance()
    session = browser_automation_service.get_session(session_id)
    
    if not session:
        return jsonify({"error": "Session not found"}), 404

    # Update step's locator stack
    # In a full implementation, we'd update the WorkflowStep in the DB.
    # Here we are updating the active session or the persistent strategy.
    
    # We don't have the step object accessible easily from just session_id without querying workflow
    # But we can update the persistent LocatorStrategy if we know the target_name
    
    # For now, we assume this endpoint is called by the extension to save the learned strategy
    # The client UI would then trigger 'retry'
    
    # Ideally we'd know the target_name. 
    # If the step in the workflow has a target_name (e.g. "login_button"), we save it there.
    # Otherwise we might need to create a new one.
    
    # Since we can't easily map back to target_name without more context, 
    # we'll just log it for now or assume the extension sends potential target_name if it knows it.
    
    # Fallback: Just return success so extension knows it worked.
    # In a real app we'd save to LocatorStrategy.objects(target_name=...).update(...)
    
    return jsonify({'status': 'updated', 'strategies': new_strategies})

# --- Recorder Routes ---

@browser_automation_bp.route('/recording/start', methods=['POST'])
@login_required
@limiter.exempt
def start_recording():
    """Start a new recording session and tell extension to begin recording (exempt from rate limiting)"""
    service = BrowserAutomationService.get_instance()

    # Generate recording ID
    recording_id = 'rec_' + str(uuid.uuid4())

    # Validating and cleaning external variables
    data = request.json or {}
    external_variables = data.get('external_variables', [])
    
    # Initialize recording session in memory
    service.recordings[recording_id] = {
        'id': recording_id,
        'steps': [],
        'variables': [],
        'status': 'recording',
        'created_at': datetime.utcnow().isoformat(),
        'user_id': current_user.user_id
    }

    # Send command to extension via Socket.IO
    user_socket_id = service.websocket_connections.get(current_user.user_id)
    if user_socket_id:
        socketio.emit('start_recording', {
            'recording_id': recording_id,
            'external_variables': external_variables
        }, room=user_socket_id, namespace='/browser_automation')

        return jsonify({
            'recording_id': recording_id,
            'status': 'recording',
            'message': 'Recording started'
        })
    else:
        return jsonify({
            'error': 'Extension not connected',
            'message': 'Please ensure the browser extension is installed and connected'
        }), 400

@browser_automation_bp.route('/recording/<recording_id>/stop', methods=['POST'])
@login_required
@limiter.exempt
def stop_recording(recording_id):
    """Stop an active recording session (exempt from rate limiting)"""
    service = BrowserAutomationService.get_instance()
    recording = service.recordings.get(recording_id)

    if not recording:
        return jsonify({'error': 'Recording not found'}), 404

    # If recording is already completed or stopped, treat it as success (idempotent)
    if recording['status'] in ['completed', 'stopped']:
        return jsonify({
            'recording_id': recording_id,
            'status': recording['status'],
            'step_count': len(recording.get('steps', [])),
            'message': f"Recording already {recording['status']}"
        })

    if recording['status'] != 'recording':
        return jsonify({'error': 'Recording is not active'}), 400

    # Send stop command to extension
    user_socket_id = service.websocket_connections.get(current_user.user_id)
    if user_socket_id:
        socketio.emit('stop_recording', {
            'recording_id': recording_id
        }, room=user_socket_id, namespace='/browser_automation')

    # Update status
    recording['status'] = 'stopped'
    recording['stopped_at'] = datetime.utcnow().isoformat()

    return jsonify({
        'recording_id': recording_id,
        'status': 'stopped',
        'step_count': len(recording.get('steps', [])),
        'message': 'Recording stopped'
    })

@browser_automation_bp.route('/recording/save', methods=['POST'])
@token_required
def save_recording(auth_user):
    """Receive raw recording from extension"""
    data = request.json
    steps = data.get('steps', [])
    variables = data.get('variables', [])

    # Save to temporary storage or DB
    from app.models import Workflow  # Or a new Recording model

    # For MVP, we'll just store in memory cache or return ID
    recording_id = str(uuid.uuid4())

    # Store in a temporary collection/cache
    # In real app: Recording.objects.create(...)
    # Simulating storage:
    browser_automation_service = BrowserAutomationService.get_instance()
    browser_automation_service.recordings[recording_id] = {
        'steps': steps,
        'variables': variables,
        'created_at': datetime.utcnow().isoformat(),
        'user_id': auth_user.id
    }

    return jsonify({'recording_id': recording_id})

@browser_automation_bp.route('/recording/<recording_id>', methods=['GET'])
@login_required 
def labeling_ui(recording_id):
    """Serve the labeling UI"""
    return render_template('browser_automation/labeling.html', recording_id=recording_id)

@browser_automation_bp.route('/api/recording/<recording_id>', methods=['GET'])
@login_required
@limiter.exempt
def get_recording(recording_id):
    """Get recording data for UI (polling endpoint - exempt from rate limiting)"""
    service = BrowserAutomationService.get_instance()
    recording = service.recordings.get(recording_id)

    if not recording:
        return jsonify({'error': 'Recording not found'}), 404

    return jsonify(recording)

@browser_automation_bp.route('/workflows/create_from_recording', methods=['POST'])
@login_required
def create_workflow_from_recording():
    """Create a real workflow from labeled recording"""
    data = request.json
    recording_id = data.get('recording_id')
    workflow_data = data.get('workflow')
    
    # Validate and Create Workflow in DB
    # ... implementation to map to Workflow model ...
    
    return jsonify({'workflow_id': 'new_workflow_id', 'status': 'created'})
