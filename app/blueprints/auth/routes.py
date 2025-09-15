"""Handles authorization routing."""

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

from app.models import User

auth = Blueprint("auth", __name__)


@auth.route("/")
def index() -> ResponseReturnValue:
    """Render the landing page if not authorized."""
    # debug("Not authorized")
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


# <<< NEW REGISTRATION ROUTE >>>
@auth.route("/register", methods=["GET", "POST"])
def register():
    """Handles user registration."""
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        # Check if user already exists
        if User.objects(user_id=email).first():
            flash("An account with that email already exists.", "warning")
            return redirect(url_for("auth.register"))

        # Create new user
        new_user = User(
            user_id=email,
        )
        new_user.set_password(password)
        new_user.save()

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
