#!/usr/bin/env python3
"""Office blueprint — M365 integration endpoints.

Handles:
  - Graph consent connection/disconnection
  - Intake configuration CRUD
  - Graph webhook receiver
  - Work item listing, detail, feedback
  - Integration dashboard
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from uuid import uuid4

from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
)
from flask_login import current_user, login_required

from app.models import (
    GraphSubscription,
    IntakeConfig,
    M365AuditEntry,
    WorkItem,
    Workflow,
)
from app.utilities.graph_client import GraphClient, GraphAPIError, GraphAuthError
from app.utilities.graph_token_store import has_valid_token, revoke_token

office = Blueprint("office", __name__)


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


@office.route("/status", methods=["GET"])
@login_required
def connection_status():
    """Check M365 connection status for the current user."""
    user_id = current_user.get_id()
    connected = has_valid_token(user_id)
    return jsonify({
        "connected": connected,
        "m365_enabled": getattr(current_user, "m365_enabled", False),
    })


@office.route("/disconnect", methods=["POST"])
@login_required
def disconnect():
    """Revoke Graph tokens and disable M365 features."""
    user_id = current_user.get_id()

    # Disable all intake configs
    IntakeConfig.objects(owner_user_id=user_id, enabled=True).update(set__enabled=False)

    # Delete active Graph subscriptions
    subs = GraphSubscription.objects(owner_user_id=user_id, active=True)
    for sub in subs:
        try:
            client = GraphClient(user_id)
            client.delete_subscription(sub.subscription_id)
        except Exception:
            pass
        sub.active = False
        sub.save()

    # Revoke tokens
    revoke_token(user_id)

    # Update user flags
    current_user.m365_enabled = False
    current_user.save()

    M365AuditEntry(
        uuid=uuid4().hex,
        action="disconnect",
        actor_user_id=user_id,
        actor_type="user",
    ).save()

    return jsonify({"status": "disconnected"})


# ---------------------------------------------------------------------------
# Intake configuration CRUD
# ---------------------------------------------------------------------------


@office.route("/intakes", methods=["GET"])
@login_required
def list_intakes():
    """List intake configurations for the current user."""
    user_id = current_user.get_id()
    intakes = IntakeConfig.objects(owner_user_id=user_id).order_by("-created_at")
    result = []
    for ic in intakes:
        result.append({
            "uuid": ic.uuid,
            "name": ic.name,
            "intake_type": ic.intake_type,
            "enabled": ic.enabled,
            "mailbox_address": ic.mailbox_address,
            "folder_path": ic.folder_path,
            "triage_enabled": ic.triage_enabled,
            "created_at": ic.created_at.isoformat() if ic.created_at else None,
        })
    return jsonify({"intakes": result})


@office.route("/intakes", methods=["POST"])
@login_required
def create_intake():
    """Create a new intake configuration."""
    user_id = current_user.get_id()
    if not has_valid_token(user_id):
        return jsonify({"error": "M365 not connected"}), 400

    data = request.get_json(silent=True) or {}
    required = ["name", "intake_type"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Missing required field: {field}"}), 400

    intake_type = data["intake_type"]
    if intake_type not in ("outlook_shared", "outlook_folder", "onedrive_drop"):
        return jsonify({"error": "Invalid intake_type"}), 400

    ic = IntakeConfig(
        uuid=uuid4().hex,
        name=data["name"],
        intake_type=intake_type,
        mailbox_address=data.get("mailbox_address"),
        outlook_folder_id=data.get("outlook_folder_id"),
        drive_id=data.get("drive_id"),
        folder_path=data.get("folder_path"),
        triage_enabled=data.get("triage_enabled", True),
        owner_user_id=user_id,
        team_id=data.get("team_id"),
    )

    # Link default workflow if provided
    wf_id = data.get("default_workflow_id")
    if wf_id:
        wf = Workflow.objects(id=wf_id, user_id=user_id).first()
        if wf:
            ic.default_workflow = wf

    # Teams config
    teams = data.get("teams_config")
    if teams:
        ic.teams_config = teams

    ic.save()

    M365AuditEntry(
        uuid=uuid4().hex,
        action="create_intake",
        actor_user_id=user_id,
        actor_type="user",
        intake_config_id=ic.uuid,
        detail={"name": ic.name, "type": ic.intake_type},
    ).save()

    return jsonify({"uuid": ic.uuid, "status": "created"}), 201


@office.route("/intakes/<uuid>", methods=["PUT"])
@login_required
def update_intake(uuid):
    """Update an intake configuration."""
    user_id = current_user.get_id()
    ic = IntakeConfig.objects(uuid=uuid, owner_user_id=user_id).first()
    if not ic:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(silent=True) or {}
    for field in ("name", "mailbox_address", "outlook_folder_id", "drive_id",
                   "folder_path", "triage_enabled", "team_id"):
        if field in data:
            setattr(ic, field, data[field])

    if "triage_rules" in data:
        ic.triage_rules = data["triage_rules"]
    if "file_filters" in data:
        ic.file_filters = data["file_filters"]
    if "teams_config" in data:
        ic.teams_config = data["teams_config"]
    if "default_workflow_id" in data:
        wf = Workflow.objects(id=data["default_workflow_id"], user_id=user_id).first()
        ic.default_workflow = wf

    ic.updated_at = datetime.utcnow()
    ic.save()
    return jsonify({"status": "updated"})


@office.route("/intakes/<uuid>", methods=["DELETE"])
@login_required
def delete_intake(uuid):
    """Delete an intake configuration and its Graph subscription."""
    user_id = current_user.get_id()
    ic = IntakeConfig.objects(uuid=uuid, owner_user_id=user_id).first()
    if not ic:
        return jsonify({"error": "Not found"}), 404

    # Clean up subscription
    if ic.subscription:
        try:
            client = GraphClient(user_id)
            client.delete_subscription(ic.subscription.subscription_id)
        except Exception:
            pass
        ic.subscription.active = False
        ic.subscription.save()

    ic.delete()
    return jsonify({"status": "deleted"})


@office.route("/intakes/<uuid>/enable", methods=["POST"])
@login_required
def enable_intake(uuid):
    """Enable an intake and create a Graph subscription for it."""
    user_id = current_user.get_id()
    ic = IntakeConfig.objects(uuid=uuid, owner_user_id=user_id).first()
    if not ic:
        return jsonify({"error": "Not found"}), 404

    if not has_valid_token(user_id):
        return jsonify({"error": "M365 not connected"}), 400

    # Build the Graph resource path based on intake type
    resource = _build_subscription_resource(ic)
    if not resource:
        return jsonify({"error": "Cannot determine Graph resource for this intake type"}), 400

    notification_url = os.environ.get("GRAPH_NOTIFICATION_URL", "")
    if not notification_url:
        return jsonify({"error": "GRAPH_NOTIFICATION_URL not configured"}), 500

    client_state = os.environ.get("GRAPH_CLIENT_STATE_SECRET", "")

    try:
        client = GraphClient(user_id)
        expiration = datetime.utcnow() + timedelta(days=2)
        result = client.create_subscription(
            resource=resource,
            change_type="created",
            notification_url=notification_url,
            expiration=expiration,
            client_state=client_state or None,
        )

        sub = GraphSubscription(
            subscription_id=result["id"],
            resource=resource,
            change_type="created",
            notification_url=notification_url,
            expiration=expiration,
            owner_user_id=user_id,
            intake_config_id=ic.uuid,
        )
        sub.save()

        ic.subscription = sub
        ic.enabled = True
        ic.updated_at = datetime.utcnow()
        ic.save()

        return jsonify({"status": "enabled", "subscription_id": result["id"]})

    except GraphAPIError as e:
        return jsonify({"error": f"Graph subscription failed: {e}"}), 502
    except GraphAuthError as e:
        return jsonify({"error": str(e)}), 401


@office.route("/intakes/<uuid>/disable", methods=["POST"])
@login_required
def disable_intake(uuid):
    """Disable an intake and delete its Graph subscription."""
    user_id = current_user.get_id()
    ic = IntakeConfig.objects(uuid=uuid, owner_user_id=user_id).first()
    if not ic:
        return jsonify({"error": "Not found"}), 404

    if ic.subscription:
        try:
            client = GraphClient(user_id)
            client.delete_subscription(ic.subscription.subscription_id)
        except Exception:
            pass
        ic.subscription.active = False
        ic.subscription.save()
        ic.subscription = None

    ic.enabled = False
    ic.updated_at = datetime.utcnow()
    ic.save()
    return jsonify({"status": "disabled"})


def _build_subscription_resource(ic: IntakeConfig) -> str | None:
    """Build the Graph resource string for a subscription."""
    if ic.intake_type == "outlook_shared" and ic.mailbox_address:
        return f"/users/{ic.mailbox_address}/mailFolders('Inbox')/messages"
    elif ic.intake_type == "outlook_folder" and ic.outlook_folder_id:
        return f"/me/mailFolders/{ic.outlook_folder_id}/messages"
    elif ic.intake_type == "onedrive_drop" and ic.folder_path:
        if ic.drive_id:
            return f"/drives/{ic.drive_id}/root:/{ic.folder_path.strip('/')}:/children"
        return f"/me/drive/root:/{ic.folder_path.strip('/')}:/children"
    return None


# ---------------------------------------------------------------------------
# Graph webhook receiver
# ---------------------------------------------------------------------------


@office.route("/webhooks/graph", methods=["GET", "POST"])
def graph_webhook():
    """Receive Microsoft Graph change notifications.

    GET: Graph sends a validation request with ``validationToken`` that we must echo back.
    POST: Actual change notifications.

    This endpoint is NOT @login_required — Graph calls it server-to-server.
    """
    # Validation handshake
    if request.method == "GET" or request.args.get("validationToken"):
        token = request.args.get("validationToken", "")
        return token, 200, {"Content-Type": "text/plain"}

    # Process notifications
    data = request.get_json(silent=True)
    if not data or "value" not in data:
        return "", 202

    from app.utilities.graph_webhooks import handle_graph_notification

    for notification in data["value"]:
        try:
            handle_graph_notification(notification)
        except Exception as e:
            # Log but don't fail — Graph expects a quick 202 response
            import logging
            logging.getLogger(__name__).error(f"Webhook handler error: {e}")

    return "", 202


# ---------------------------------------------------------------------------
# Work items
# ---------------------------------------------------------------------------


@office.route("/workitems", methods=["GET"])
@login_required
def list_work_items():
    """List work items with optional filters."""
    user_id = current_user.get_id()
    status_filter = request.args.get("status")
    source_filter = request.args.get("source")
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    query = WorkItem.objects(owner_user_id=user_id)
    if status_filter:
        query = query.filter(status=status_filter)
    if source_filter:
        query = query.filter(source=source_filter)

    total = query.count()
    items = query.order_by("-created_at").skip(offset).limit(limit)

    result = []
    for wi in items:
        result.append({
            "uuid": wi.uuid,
            "source": wi.source,
            "status": wi.status,
            "subject": wi.subject,
            "sender_email": wi.sender_email,
            "triage_category": wi.triage_category,
            "triage_confidence": wi.triage_confidence,
            "sensitivity_flags": wi.sensitivity_flags,
            "attachment_count": wi.attachment_count,
            "created_at": wi.created_at.isoformat() if wi.created_at else None,
            "case_folder_url": wi.case_folder_url,
            "feedback_action": wi.feedback_action,
        })

    return jsonify({"items": result, "total": total})


@office.route("/workitems/<uuid>", methods=["GET"])
@login_required
def get_work_item(uuid):
    """Get detailed view of a single work item."""
    user_id = current_user.get_id()
    wi = WorkItem.objects(uuid=uuid, owner_user_id=user_id).first()
    if not wi:
        return jsonify({"error": "Not found"}), 404

    data = {
        "uuid": wi.uuid,
        "source": wi.source,
        "status": wi.status,
        "subject": wi.subject,
        "sender_email": wi.sender_email,
        "sender_name": wi.sender_name,
        "received_at": wi.received_at.isoformat() if wi.received_at else None,
        "body_text": wi.body_text[:5000] if wi.body_text else None,
        "triage_category": wi.triage_category,
        "triage_confidence": wi.triage_confidence,
        "triage_tags": wi.triage_tags,
        "sensitivity_flags": wi.sensitivity_flags,
        "triage_summary": wi.triage_summary,
        "attachment_count": wi.attachment_count,
        "case_folder_url": wi.case_folder_url,
        "case_folder_drive_path": wi.case_folder_drive_path,
        "feedback_action": wi.feedback_action,
        "feedback_note": wi.feedback_note,
        "created_at": wi.created_at.isoformat() if wi.created_at else None,
    }

    # Include workflow info if available
    try:
        if wi.matched_workflow:
            data["workflow_name"] = wi.matched_workflow.name
    except Exception:
        data["workflow_name"] = None

    # Include result status
    try:
        if wi.workflow_result:
            data["workflow_status"] = wi.workflow_result.status
    except Exception:
        data["workflow_status"] = None

    return jsonify(data)


@office.route("/workitems/<uuid>/feedback", methods=["POST"])
@login_required
def submit_feedback(uuid):
    """Submit feedback on a work item (correct / fix / stop / reassign)."""
    user_id = current_user.get_id()
    wi = WorkItem.objects(uuid=uuid, owner_user_id=user_id).first()
    if not wi:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in ("correct", "fix", "stop", "reassign"):
        return jsonify({"error": "Invalid action"}), 400

    wi.feedback_action = action
    wi.feedback_by = user_id
    wi.feedback_at = datetime.utcnow()
    wi.feedback_note = data.get("note", "")
    wi.updated_at = datetime.utcnow()
    wi.save()

    M365AuditEntry(
        uuid=uuid4().hex,
        action="feedback",
        actor_user_id=user_id,
        actor_type="user",
        work_item_id=wi.uuid,
        detail={"feedback_action": action, "note": data.get("note", "")},
    ).save()

    return jsonify({"status": "feedback_recorded"})


@office.route("/workitems/<uuid>/reprocess", methods=["POST"])
@login_required
def reprocess_work_item(uuid):
    """Re-run triage + workflow on a work item."""
    user_id = current_user.get_id()
    wi = WorkItem.objects(uuid=uuid, owner_user_id=user_id).first()
    if not wi:
        return jsonify({"error": "Not found"}), 404

    wi.status = "received"
    wi.triage_category = None
    wi.triage_confidence = None
    wi.sensitivity_flags = []
    wi.matched_workflow = None
    wi.trigger_event = None
    wi.workflow_result = None
    wi.updated_at = datetime.utcnow()
    wi.save()

    from app.utilities.m365_tasks import triage_work_item

    triage_work_item.delay(str(wi.id))
    return jsonify({"status": "reprocessing"})


@office.route("/workitems/<uuid>/approve", methods=["POST"])
@login_required
def approve_work_item(uuid):
    """Approve a work item held in awaiting_review (sensitivity gate)."""
    user_id = current_user.get_id()
    wi = WorkItem.objects(uuid=uuid, owner_user_id=user_id).first()
    if not wi:
        return jsonify({"error": "Not found"}), 404
    if wi.status != "awaiting_review":
        return jsonify({"error": "Item is not awaiting review"}), 400

    wi.status = "triaged"
    wi.updated_at = datetime.utcnow()
    wi.save()

    M365AuditEntry(
        uuid=uuid4().hex,
        action="approve_review",
        actor_user_id=user_id,
        actor_type="user",
        work_item_id=wi.uuid,
    ).save()

    # Continue processing
    from app.utilities.m365_tasks import triage_work_item

    # Re-dispatch — the triage step will see it's already triaged and route it
    triage_work_item.delay(str(wi.id))
    return jsonify({"status": "approved"})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@office.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    """M365 integration dashboard page."""
    user_id = current_user.get_id()
    connected = has_valid_token(user_id)

    intakes = IntakeConfig.objects(owner_user_id=user_id).order_by("-created_at")

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = datetime.utcnow() - timedelta(days=7)

    recent_items = WorkItem.objects(
        owner_user_id=user_id, created_at__gte=week_ago
    ).order_by("-created_at").limit(50)

    today_items = [i for i in recent_items if i.created_at and i.created_at >= today_start]

    stats = {
        "connected": connected,
        "total_intakes": intakes.count(),
        "active_intakes": intakes.filter(enabled=True).count(),
        "today_items": len(today_items),
        "today_completed": len([i for i in today_items if i.status == "completed"]),
        "today_failed": len([i for i in today_items if i.status == "failed"]),
        "week_items": recent_items.count(),
        "awaiting_review": WorkItem.objects(
            owner_user_id=user_id, status="awaiting_review"
        ).count(),
    }

    return render_template(
        "office/dashboard.html",
        connected=connected,
        intakes=intakes,
        recent_items=recent_items,
        stats=stats,
    )
