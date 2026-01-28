"""Automation dashboard blueprint for monitoring passive workflows."""
from __future__ import annotations

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from app.models import Workflow, WorkflowTriggerEvent, WorkflowResult, SmartFolder

automation = Blueprint("automation", __name__, url_prefix="/automation")


@automation.route("/", methods=["GET"])
@login_required
def dashboard():
    """Main automation dashboard."""
    user_id = current_user.get_id()
    
    # Get passive workflows  
    passive_workflows = Workflow.objects(
        user_id=user_id,
        input_config__folder_watch__enabled=True
    ).only('id', 'name', 'input_config', 'output_config', 'stats')
    
    # Get recent trigger events (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_events = WorkflowTriggerEvent.objects(
        workflow__in=[w for w in passive_workflows],
        created_at__gte=week_ago
    ).order_by('-created_at').limit(50)
    
    # Calculate stats
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_events = [e for e in recent_events if e.created_at >= today]
    
    stats = {
        'total_passive_workflows': passive_workflows.count(),
        'total_watched_folders': sum(
            len(w.input_config.get('folder_watch', {}).get('folders', [])) 
            for w in passive_workflows
        ),
        'today_runs': len(today_events),
        'today_successful': len([e for e in today_events if e.status == 'completed']),
        'today_failed': len([e for e in today_events if e.status == 'failed']),
        'week_runs': len(recent_events),
    }
    
    # Get folder names for display
    folder_ids = set()
    for workflow in passive_workflows:
        folder_watch = workflow.input_config.get('folder_watch', {})
        folder_ids.update (folder_watch.get('folders', []))
    
    folders = {f.uuid: f for f in SmartFolder.objects(uuid__in=list(folder_ids)).only('uuid', 'title')}
    
    return render_template(
        'automation/dashboard.html',
        passive_workflows=passive_workflows,
        recent_events=recent_events,
        stats=stats,
        folders=folders
    )


@automation.route("/api/trigger_events", methods=["GET"])
@login_required
def get_trigger_events():
    """Get trigger events for AJAX updates."""
    user_id = current_user.get_id()
    status_filter = request.args.get('status', None)
    limit = int(request.args.get('limit', 20))
    
    # Get user's workflows
    user_workflows = Workflow.objects(user_id=user_id).only('id')
    
    query = WorkflowTriggerEvent.objects(workflow__in=user_workflows)
    
    if status_filter:
        query = query.filter(status=status_filter)
    
    events = query.order_by('-created_at').limit(limit)
    
    result = []
    for event in events:
        result.append({
            'uuid': event.uuid,
            'workflow_name': event.workflow.name if event.workflow else 'Unknown',
            'trigger_type': event.trigger_type,
            'status': event.status,
            'created_at': event.created_at.isoformat() if event.created_at else None,
            'documents_count': event.document_count,
            'error': event.error
        })
    
    return jsonify({'events': result})
