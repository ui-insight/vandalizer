#!/usr/bin/env python3

import json
import logging

from bson import ObjectId
from bson.errors import InvalidId
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

    after = request.args.get("after")

    query = ActivityEvent.objects(user_id=user_id)

    if after:
        try:
            after_oid = ObjectId(after)
        except (InvalidId, TypeError):
            logger.warning("Ignoring invalid 'after' cursor for activity stream")
        else:
            query = query.filter(id__gt=after_oid)

    events = list(query.order_by("-started_at").limit(limit))
    events.reverse()  # Oldest first so DOM insertions keep newest at the top.
    serialized_events = [json.loads(event.to_json()) for event in events]

    return jsonify({"events": serialized_events})
