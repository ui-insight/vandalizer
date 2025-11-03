"""Handles authorization routing."""

from devtools import debug
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_dance.contrib.azure import azure
from flask_login import login_user
from mongoengine.errors import NotUniqueError

from app import load_user
from app.models import TeamInvite, TeamMembership, User

auth = Blueprint("auth", __name__)


@auth.route("/")
def index() -> ResponseReturnValue:
    """Render the landing page if not authorized."""
    # debug("Not authorized")
    user = load_user()
    debug(user)
    if user is not None:
        return redirect(url_for("home.index"))

    return render_template("landing.html", AUTH_MODE=current_app.config["AUTH_MODE"])


@auth.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    """Handle the login process. Redirect to Azure login if not authorized."""
    # Bypass Azure login in dev/local environments

    auth_mode = current_app.config.get("AUTH_MODE")
    print(f"Logging in with {auth_mode}")

    if auth_mode == "LOCAL":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.objects(user_id=email).first()

        # Check that user exists and password is correct
        if user and user.check_password(password):
            login_user(user)
            flash("You have been logged in!", "success")
            return redirect(url_for("home.index"))  # Or your main app page
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("auth.index"))

    if not azure.authorized:
        return redirect(url_for("azure.login"))
    return redirect(url_for("home.index"))


@auth.route("/register", methods=["GET", "POST"])
def register():
    """Handles user registration."""
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password")

        # Check if user already exists
        if User.objects(user_id=email).first():
            flash("An account with that email already exists.", "warning")
            return redirect(url_for("auth.register"))

        # Create new user
        new_user = User(user_id=email, email=email, name=name)
        new_user.set_password(password)

        # Check for pending invites BEFORE saving the user
        # This prevents the pre_save hook from creating a personal team
        # Normalize email to lowercase since invites are stored lowercased
        pending_invites = list(TeamInvite.objects(email=email.lower(), accepted=False))

        first_invited_team = None
        if pending_invites:
            # Set the current_team before first save to prevent personal team creation
            first_invited_team = pending_invites[0].team
            new_user.current_team = first_invited_team

        # Now save the user (with current_team set if there are invites)
        new_user.save()

        # Process the invites: create memberships and mark as accepted
        for inv in pending_invites:
            # Create membership if not already present (unique index will also protect us)
            try:
                existing = TeamMembership.objects(
                    team=inv.team, user_id=new_user.user_id
                ).first()
                if not existing:
                    TeamMembership(
                        team=inv.team,
                        user_id=new_user.user_id,
                        role=inv.role,
                    ).save()
                # mark invite as accepted
                inv.accepted = True
                inv.save()
            except NotUniqueError:
                # Membership already exists due to race/duplicate; still mark invite accepted.
                inv.accepted = True
                inv.save()

        # Log the user in automatically
        login_user(new_user)

        flash("Account created successfully!", "success")
        return redirect(url_for("home.index"))

    # For GET requests, show the registration form
    return render_template("users/register.html")


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
