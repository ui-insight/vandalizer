from flask import request, redirect, render_template
from app.models import Space
import uuid
from . import spaces

@spaces.route("/new", methods=["GET", "POST"])
def new_space():
    if request.method == "POST":
        title = request.form["title"]
        space = Space(title=title, uuid=uuid.uuid4().hex)
        space.save()
        return redirect("/home?id=" + space.uuid)
    return render_template("spaces/new.html")