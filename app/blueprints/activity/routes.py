#!/usr/bin/env python3

import logging
from flask import Blueprint, render_template, request, current_app, jsonify, redirect, url_for
from app.models import ActivityEvent

activity = Blueprint("activity", __name__)

logger = logging.getLogger(__name__)

@activity.route("/runs/<activity_id>", methods=["GET"])
def activity_index(activity_id):

    # get activity data from the database and redirect to home page while including activity data into the template context
    return redirect(url_for("home.index", activity_id=activity_id))
