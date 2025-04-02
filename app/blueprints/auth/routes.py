"""Handles authorization routing."""

from devtools import debug
from flask import redirect, render_template, session, url_for
from flask.typing import ResponseReturnValue

from app import azure
from app.models import User
from app.utils import is_dev, load_user

from . import auth


@auth.route("/")
def index() -> ResponseReturnValue:
    """Render the landing page if not authorized."""
    debug("Not authorized")
    return render_template("landing.html")


@auth.route("/login")
def login() -> ResponseReturnValue:
    """Handle the login process. Redirect to Azure login if not authorized."""
    # Bypass Azure login in dev/local environments
    if is_dev():
        user = load_user()
        if user:
            return redirect(url_for("home.index"))

    if not azure.authorized:
        return redirect(url_for("azure.login"))
    return redirect(url_for("main.home"))


@auth.route("/logout")
def logout() -> ResponseReturnValue:
    """Handle the logout process. Clear the session and redirect to the landing page."""
    session.clear()
    return redirect(url_for("auth.index"))


@auth.route("/build_admin")
def build_admin() -> ResponseReturnValue:
    """Build an admin user for development purposes."""
    user = User(user_id="admin", is_admin=True)
    user.save()
    session["user_id"] = "admin"
