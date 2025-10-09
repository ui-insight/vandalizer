#!/usr/bin/env python3

import logging
from flask import Blueprint, render_template, request, current_app, jsonify, redirect, url_for
from app.models import ActivityEvent, ChatConversation

activity = Blueprint("activity", __name__)

logger = logging.getLogger(__name__)

@activity.route("/runs/<activity_id>", methods=["GET"])
def activity_index(activity_id):

    # get activity data from the database and redirect to home page while including activity data into the template context
    return redirect(url_for("home.index", activity_id=activity_id))


@activity.route("/runs/delete/<activity_id>", methods=["POST"])
def delete_activity(activity_id):
    # Delete the activity event from the database
    event = ActivityEvent.objects(id=activity_id).first()
    if event:
        # delete the related conversation
        conversation = ChatConversation.objects(uuid=event.conversation_id).first()
        if conversation:
            conversation.delete()
            logger.info(f"Deleted related conversation with ID: {event.conversation_id}")

        event.delete()
        logger.info(f"Deleted activity event with ID: {activity_id}")
        return jsonify({"status": "success", "message": f"Activity {activity_id} deleted."}), 200
    else:
        logger.warning(f"Attempted to delete non-existent activity event with ID: {activity_id}")
        return jsonify({"status": "error", "message": f"Activity {activity_id} not found."}), 404
