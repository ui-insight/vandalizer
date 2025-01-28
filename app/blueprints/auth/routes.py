# app/blueprints/auth/routes.py
from flask import Blueprint, redirect, url_for, session, render_template
from . import auth
from app import azure
from app.models import User

auth = Blueprint('auth', __name__)

@auth.route("/")
def index():
    print("Not authorized")
    return render_template("landing.html")

@auth.route("/login")
def login():
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