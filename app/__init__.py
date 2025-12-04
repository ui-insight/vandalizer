#!/usr/bin/env python3
"""Application initialization and configuration. Defines Flask and its components."""

import logging

# Error Logging
import os
from datetime import timedelta

import mongoengine as me
import rollbar
import rollbar.contrib.flask
from celery import Celery, Task
from dotenv import load_dotenv
from flask import Flask, got_request_exception
from flask_bootstrap import Bootstrap
from flask_cors import CORS
from flask_dance.consumer import oauth_authorized
from flask_dance.contrib.azure import make_azure_blueprint
from flask_login import LoginManager, current_user, login_user
from flask_mail import Mail
from app.utilities.config import get_auth_methods, get_highlight_color, get_ui_radius

CURRENT_RELEASE_VERSION = "2.3.01"  # Update this when you have a new release.
RELEASE_NOTES = """
Release 2.3.01:
- Over 20 bug fixes and tweaks
- Restored elegant formatting
- Improved workflow speed and performance
"""

# Load environment variables from .env file
load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")


def celery_init_app(app: Flask) -> Celery:
    class FlaskTask(Task):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.set_default()
    app.extensions["celery"] = celery_app
    return celery_app


# Use app factory pattern
def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        CELERY={
            "broker_url": f"redis://{REDIS_HOST}:6379/0",
            "result_backend": f"redis://{REDIS_HOST}:6379/1",
            "task_default_queue": "default",
            "task_routes": {
                "tasks.documents.*": {"queue": "documents"},
                "tasks.workflow.*": {"queue": "workflows"},
                "tasks.upload.*": {"queue": "uploads"},
            },
        }
    )
    app.config.from_prefixed_env()
    celery_init_app(app)
    return app


app = create_app()

CORS(
    app,
    resources={
        r"/*": {
            "origins": [
                "http://localhost:3000",
                "https://localhost:3000",
                "https://localhost",
                "http://localhost",
            ],
        },
    },
)

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=60)
app.permanent_session_lifetime = timedelta(days=60)

# SET FLASK_ENV FOR EACH SERVER
env = os.getenv("FLASK_ENV", "development").lower()

if env == "production":
    config_class = "app.configuration.ProductionConfig"
elif env == "testing":
    config_class = "app.configuration.TestingConfig"
else:
    # anything else (including 'development') → development settings
    config_class = "app.configuration.DevelopmentConfig"

# Log which env/config we're using
logging.basicConfig(level=logging.INFO)
app.logger.info(f"Starting server in '{env}' environment → loading {config_class!r}")


app.config.from_object(config_class)


Bootstrap(app)  # flask-bootstrap
mail = Mail(app)

# Set up logging
logging.basicConfig(level=logging.INFO)
app.logger = logging.getLogger("app_logger")

from app.models import User

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"  # Redirect here if @login_required fails


@login_manager.user_loader
def load_user(user_id: str | None = None) -> User | None:
    """Loads user from DB for session management."""
    id = user_id if user_id else current_user.get_id()
    return User.objects(user_id=id).first()


# Setup blueprints
from .blueprints.activity.routes import activity  # noqa: E402
from .blueprints.admin.routes import admin  # noqa: E402
from .blueprints.auth.routes import auth  # noqa: E402
from .blueprints.feedback.routes import feedback  # noqa: E402
from .blueprints.files.routes import files  # noqa: E402
from .blueprints.home.routes import home  # noqa: E402
from .blueprints.library.routes import library  # noqa: E402
from .blueprints.office.routes import office  # noqa: E402
from .blueprints.spaces.routes import spaces  # noqa: E402
from .blueprints.tasks.routes import tasks  # noqa: E402
from .blueprints.team.routes import teams  # noqa: E402
from .blueprints.workflows.routes import workflows  # noqa: E402
from .blueprints.browser_automation.routes import browser_automation_bp  # noqa: E402

app.register_blueprint(auth)
app.register_blueprint(home, url_prefix="/home")
app.register_blueprint(workflows, url_prefix="/workflows")
app.register_blueprint(files, url_prefix="/files")
app.register_blueprint(spaces, url_prefix="/spaces")
app.register_blueprint(feedback, url_prefix="/feedback")
app.register_blueprint(tasks, url_prefix="/tasks")
app.register_blueprint(office, url_prefix="/office")
app.register_blueprint(admin, url_prefix="/admin")
app.register_blueprint(library, url_prefix="/library")
app.register_blueprint(teams, url_prefix="/teams")
app.register_blueprint(activity, url_prefix="/activity")
app.register_blueprint(browser_automation_bp, url_prefix="/browser_automation")

# Import Celery tasks so they're registered when app starts
# This ensures tasks are discovered by Celery workers
with app.app_context():
    from app.utilities import activity_description  # noqa: F401

# --- 4. CONDITIONAL AUTHENTICATION SETUP ---
auth_methods = get_auth_methods()

# In non-production, always allow password auth so devs can't lock themselves out
if env != "production" and "password" not in auth_methods:
    app.logger.warning("Enforcing password auth in non-production to avoid lockout.")
    auth_methods = auth_methods + ["password"]
PASSWORD_AUTH_ENABLED = "password" in auth_methods
OAUTH_AUTH_ENABLED = "oauth" in auth_methods

app.config["AUTH_PASSWORD_ENABLED"] = PASSWORD_AUTH_ENABLED
app.config["AUTH_OAUTH_ENABLED"] = OAUTH_AUTH_ENABLED
app.config["AUTH_MODE"] = (
    "OAUTH"
    if OAUTH_AUTH_ENABLED and not PASSWORD_AUTH_ENABLED
    else "PASSWORD"
    if PASSWORD_AUTH_ENABLED and not OAUTH_AUTH_ENABLED
    else "HYBRID"
)

azure_blueprint = None
if OAUTH_AUTH_ENABLED:
    try:
        azure_blueprint = make_azure_blueprint(
            client_id=app.config.get("CLIENT_ID"),
            client_secret=app.config.get("CLIENT_SECRET"),
            tenant=app.config.get("TENANT_NAME"),
        )
        app.register_blueprint(azure_blueprint, url_prefix="/login")
    except Exception as e:
        app.logger.warning(f"OAuth enabled but Azure blueprint could not be registered: {e}")

if azure_blueprint:

    @oauth_authorized.connect_via(azure_blueprint)
    def azure_logged_in(blueprint, token):
        """Creates or loads a user after successful Azure login."""
        if not token:
            app.logger.warning("Failed to fetch token from Azure.")
            return

        resp = blueprint.session.get("/v1.0/me")
        if not resp.ok:
            app.logger.warning(
                f"Failed to fetch user info from Azure Graph: {resp.text}"
            )
            return

        info = resp.json()
        user_principal_name = info.get("userPrincipalName")
        user = User.objects(user_id=user_principal_name).first()

        if not user:
            email = info.get("mail") or user_principal_name
            user = User(
                user_id=user_principal_name, email=email, name=info["displayName"]
            ).save()
        else:
            if not user.email:
                user.email = info.get("mail") or user_principal_name
            if not user.name:
                user.name = info["displayName"]
            user.save()

        login_user(user)

# Point the login view to the local blueprint's login function (always available path)
login_manager.login_view = "auth.login"


@app.context_processor
def inject_ui_config():
    """Expose UI/auth configuration to templates."""
    return {
        "highlight_color": get_highlight_color(),
        "ui_radius": get_ui_radius(),
        "auth_password_enabled": PASSWORD_AUTH_ENABLED,
        "auth_oauth_enabled": OAUTH_AUTH_ENABLED,
    }


with app.app_context():
    """init rollbar module"""
    rollbar.init(
        # access token
        "89d52707026e4341b6ce8451232e7585",
        # environment name - any string, like 'production' or 'development'
        "flasktest",
        # server root directory, makes tracebacks prettier
        root=os.path.dirname(os.path.realpath(__file__)),
        # flask already sets up logging
        allow_logging_basic_config=False,
    )

    # send exceptions from `app` to rollbar, using flask's signal system.
    got_request_exception.connect(rollbar.contrib.flask.report_exception, app)


me.connect(
    app.config["MONGO_DB"],
    host=os.getenv("MONGO_HOST", "mongodb://localhost:27017/").lower(),
)
