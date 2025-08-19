"""Handles collaborative spaces."""

import uuid

from flask import Blueprint, redirect, render_template, request
from flask.typing import ResponseReturnValue

from app.models import Space

spaces = Blueprint("spaces", __name__)


@spaces.route("/new", methods=["GET", "POST"])
def new_space() -> ResponseReturnValue:
    """Create a new collaborative space."""
    if request.method == "POST":
        title = request.form["title"]
        space = Space(title=title, uuid=uuid.uuid4().hex)
        space.save()
        return redirect("/home?id=" + space.uuid)
    return render_template("spaces/new.html")
