#!/usr/bin/env python3

import logging
import time

from devtools import debug
from flask import (
    Blueprint,
    Response,
    jsonify,
    redirect,
    request,
    url_for,
)

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


def generate_events(user_id, limit=100, poll_interval=2):
    """
    SSE generator that streams only NEW activities.
    """
    # Track the IDs we've already sent
    sent_ids = set()

    while True:
        # Query the most recent events (descending order - newest first)
        events = list(
            ActivityEvent.objects(user_id=user_id).order_by("started_at").limit(limit)
        )

        # Only send events we haven't sent before
        for ev in events:
            event_id = str(ev.id)
            if event_id not in sent_ids:
                yield f"data: {ev.to_json()}\n\n"
                sent_ids.add(event_id)

        # Sleep briefly to avoid hammering the DB
        time.sleep(poll_interval)


@activity.route("/streams/", methods=["GET"])
def activity_streams():
    user = load_user()
    user_id = user.get_id()

    limit = int(request.args.get("limit", 100))
    return Response(generate_events(user_id, limit), mimetype="text/event-stream")
