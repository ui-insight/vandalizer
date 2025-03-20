# app/blueprints/auth/routes.py
from flask import redirect, url_for, session, render_template
from . import auth
from app.utils import load_user, is_dev
from app import azure
from app.models import User

@auth.route("/")
def index():
    print("Not authorized")
    return render_template("landing.html")

@auth.route("/login")
def login():
    # Bypass Azure login in dev/local environments
    if is_dev():
        user = load_user()
        if user:
            return redirect(url_for("home.index"))
        

    if not azure.authorized:
        return redirect(url_for("azure.login"))
    else:
        return redirect(url_for("main.home"))

@auth.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.index"))

@auth.route("/build_admin")
def build_admin():
    user = User(user_id="admin", is_admin=True)
    user.save()
    session["user_id"] = "admin"