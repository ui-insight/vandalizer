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
from flask_login import LoginManager, login_user
from flask_mail import Mail

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
Mail(app)

# Set up logging
logging.basicConfig(level=logging.INFO)
app.logger = logging.getLogger("app_logger")

from app.models import User

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"  # Redirect here if @login_required fails


@login_manager.user_loader
def load_user(user_id: str):
    """Loads user from DB for session management."""
    return User.objects(user_id=user_id).first()


# Setup blueprints
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

# --- 4. CONDITIONAL AUTHENTICATION SETUP ---
AUTH_MODE = "LOCAL" if env != "production" else os.getenv("AUTH_MODE", "AZURE").upper()
app.logger.info(f"Authentication mode set to: {AUTH_MODE}")

if AUTH_MODE == "AZURE":
    # --- Azure AD / Flask-Dance Mode ---
    blueprint = make_azure_blueprint(
        client_id=app.config["CLIENT_ID"],
        client_secret=app.config["CLIENT_SECRET"],
        tenant=app.config["TENANT_NAME"],
    )

    app.register_blueprint(blueprint, url_prefix="/login")

    @oauth_authorized.connect_via(blueprint)
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
        user_id = info["id"]
        user = User.objects(id=user_id).first()

        if not user:
            # Create a new user if they don't exist
            user = User(
                user_id=info["userPrincipalName"], name=info["displayName"]
            ).save()

        login_user(user)  # This is the critical step to create the user session

elif AUTH_MODE == "LOCAL":
    # Point the login view to the local blueprint's login function
    login_manager.login_view = "auth.login"

else:
    raise ValueError(f"Invalid AUTH_MODE: '{AUTH_MODE}'. Must be 'AZURE' or 'LOCAL'.")


app.config["AUTH_MODE"] = AUTH_MODE


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
