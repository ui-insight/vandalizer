import logging

# Error Logging
import os
from datetime import timedelta

import mongoengine as me
import rollbar
import rollbar.contrib.flask
from flask import Flask, got_request_exception
from flask_bootstrap import Bootstrap
from flask_cors import CORS
from flask_dance.contrib.azure import make_azure_blueprint
from flask_mail import Mail

# Setup blueprints
from .blueprints.auth import auth
from .blueprints.feedback import feedback
from .blueprints.files import files
from .blueprints.home import home
from .blueprints.office import office
from .blueprints.spaces import spaces
from .blueprints.tasks import tasks
from .blueprints.workflows import workflows

CURRENT_RELEASE_VERSION = "2.0.2"  # Update this when you have a new release.
RELEASE_NOTES = """
Release 2.0.1=2:
- Bug fixes and stability improvements.
"""

app = Flask(__name__)

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
app.config.from_object("app.configuration.DevelopmentConfig")

me.connect("osp")
Bootstrap(app)  # flask-bootstrap
Mail(app)

# Set up logging
logging.basicConfig(level=logging.INFO)
app.logger = logging.getLogger("app_logger")


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
