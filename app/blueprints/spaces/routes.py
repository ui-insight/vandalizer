"""Handles collaborative spaces."""

import uuid

from flask import Blueprint, redirect, render_template, request
from flask.typing import ResponseReturnValue

from app.models import Space

spaces = Blueprint("spaces", __name__)


@spaces.route("/new", methods=["GET"])
def new_space_form() -> ResponseReturnValue:
    """Create a new collaborative space."""
    return render_template("spaces/new.html")


@spaces.route("/new", methods=["POST"])
def create_space() -> ResponseReturnValue:
    """Create a new collaborative space."""
    title = request.form["title"]
    space = Space(title=title, uuid=uuid.uuid4().hex)
    space.save()
    return redirect("/home?id=" + space.uuid)
