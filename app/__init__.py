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
from flask import Flask, got_request_exception
from flask_bootstrap import Bootstrap
from flask_cors import CORS
from flask_dance.contrib.azure import make_azure_blueprint
from flask_mail import Mail

CURRENT_RELEASE_VERSION = "2.1.1"  # Update this when you have a new release.
RELEASE_NOTES = """
Release 2.1.1:
- Background task handling
- Timeout fixes
- Bug fixes and improvements
"""


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
        CELERY=dict(
            broker_url="redis://localhost:6379/",
            result_backend="redis://localhost:6379/",
        ),
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

# Setup blueprints
from .blueprints.auth import auth  # noqa: E402
from .blueprints.feedback import feedback  # noqa: E402
from .blueprints.files import files  # noqa: E402
from .blueprints.home import home  # noqa: E402
from .blueprints.office import office  # noqa: E402
from .blueprints.spaces import spaces  # noqa: E402
from .blueprints.tasks import tasks  # noqa: E402
from .blueprints.workflows import workflows  # noqa: E402

app.register_blueprint(auth)
app.register_blueprint(home, url_prefix="/home")
app.register_blueprint(workflows, url_prefix="/workflows")
app.register_blueprint(files, url_prefix="/files")
app.register_blueprint(spaces, url_prefix="/spaces")
app.register_blueprint(feedback, url_prefix="/feedback")
app.register_blueprint(tasks, url_prefix="/tasks")
app.register_blueprint(office, url_prefix="/office")

# OAuth
blueprint = make_azure_blueprint(
    client_id=app.config["CLIENT_ID"],
    client_secret=app.config["CLIENT_SECRET"],
    tenant=app.config["TENANT_NAME"],
)

app.register_blueprint(blueprint, url_prefix="/login")


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


me.connect(app.config["MONGO_DB"])
