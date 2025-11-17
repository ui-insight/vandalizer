#!/usr/bin/env python3

import json
import logging

from devtools import debug
from flask import Blueprint, jsonify, redirect, request, url_for

from app import load_user
from app.models import ActivityEvent, ChatConversation

activity = Blueprint("activity", __name__)

logger = logging.getLogger(__name__)


@activity.route("/runs/<activity_id>", methods=["GET"])
def activity_index(activity_id):
    # get activity data from the database and redirect to home page while including activity data into the template context
    return redirect(url_for("home.index", activity_id=activity_id))


@activity.route("/runs/<activity_id>/data", methods=["GET"])
def get_activity_data(activity_id):
    """Get activity data as JSON for client-side rendering."""
    user = load_user()
    user_id = user.get_id()
    
    event = ActivityEvent.objects(id=activity_id, user_id=user_id).first()
    if not event:
        return jsonify({"error": "Activity not found"}), 404
    
    # Convert to dict format similar to what _build_activities returns
    from app.blueprints.home.routes import event_to_dict
    activity_data = event_to_dict(event)
    
    # Add workflow session_id if this is a workflow activity
    if event.type == "workflow_run" and event.workflow_result:
        activity_data["workflow_session_id"] = event.workflow_result.session_id
    
    return jsonify({"activity": activity_data})


@activity.route("/runs/delete/<activity_id>", methods=["POST"])
def delete_activity(activity_id):
    user = load_user()
    user_id = user.get_id()
    debug(user)
    debug(user_id)
    # Delete the activity event from the database
    event = ActivityEvent.objects(id=activity_id, user_id=user_id).first()
    if event:
        # delete the related conversation
        conversation = ChatConversation.objects(
            uuid=event.conversation_id, user_id=user_id
        ).first()
        if conversation:
            # delete the corresponding messages as well
            for msg in conversation.messages:
                msg.delete()

            # delete the attachments
            for file_attachment in conversation.file_attachments:
                file_attachment.delete()

            # delete the url attachments
            for url_attachment in conversation.url_attachments:
                url_attachment.delete()

            conversation.delete()
            logger.info(
                f"Deleted related conversation with ID: {event.conversation_id}"
            )

        event.delete()
        logger.info(f"Deleted activity event with ID: {activity_id}")
        return jsonify(
            {"status": "success", "message": f"Activity {activity_id} deleted."}
        ), 200
    else:
        logger.warning(
            f"Attempted to delete non-existent activity event with ID: {activity_id}"
        )
        return jsonify(
            {"status": "error", "message": f"Activity {activity_id} not found."}
        ), 404


@activity.route("/streams/", methods=["GET"])
def activity_streams():
    user = load_user()
    user_id = user.get_id()

    # Sanitize the limit so polling cannot overwhelm the DB.
    try:
        limit = int(request.args.get("limit", 50))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 200))

    # after = request.args.get("after")

    query = ActivityEvent.objects(user_id=user_id)
    # if after:
    #     try:
    #         after_oid = ObjectId(after)
    #     except (InvalidId, TypeError):
    #         logger.warning("Ignoring invalid 'after' cursor for activity stream")
    #     else:
    #         query = query.filter(id__gt=after_oid)

    events = list(query.order_by("-started_at").limit(limit))
    serialized_events = [json.loads(event.to_json()) for event in events]
    return jsonify({"events": serialized_events})
