from flask import Flask
from flask_bootstrap import Bootstrap
import mongoengine as me
from flask_login import LoginManager
from flask_mail import Mail
from datetime import timedelta
from flask_cors import CORS
from oauthlib.oauth2.rfc6749.errors import TokenExpiredError
from oauthlib.oauth2.rfc6749.errors import MismatchingStateError
from flask_dance.contrib.azure import azure, make_azure_blueprint
import logging

# Error Logging
import os
import rollbar
import rollbar.contrib.flask
from flask import got_request_exception

CURRENT_RELEASE_VERSION = "2.0.2"  # Update this when you have a new release.
RELEASE_NOTES = """
Release 2.0.1=2:
- Bug fixes and stability improvements.
"""

app = Flask(__name__)

# CORS(app)
CORS(
    app,
    resources={
        r"/*": {
            "origins": [
                "http://localhost:3000",
                "https://localhost:3000",
                "https://localhost",
                "http://localhost",
            ]
        }
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

# Setup blueprints
from .blueprints.auth import auth
from .blueprints.home import home
from .blueprints.workflows import workflows
from .blueprints.files import files
from .blueprints.spaces import spaces
from .blueprints.feedback import feedback
from .blueprints.tasks import tasks
from .blueprints.office import office

app.register_blueprint(auth)
app.register_blueprint(home, url_prefix="/home")
app.register_blueprint(workflows, url_prefix="/workflows")
app.register_blueprint(files, url_prefix="/files")
app.register_blueprint(spaces, url_prefix="/spaces")
app.register_blueprint(feedback, url_prefix="/feedback")
app.register_blueprint(tasks, url_prefix="/tasks")
app.register_blueprint(office, url_prefix="/office")
import os

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
        '89d52707026e4341b6ce8451232e7585',
        # environment name - any string, like 'production' or 'development'
        'flasktest',
        # server root directory, makes tracebacks prettier
        root=os.path.dirname(os.path.realpath(__file__)),
        # flask already sets up logging
        allow_logging_basic_config=False)

    # send exceptions from `app` to rollbar, using flask's signal system.
    got_request_exception.connect(rollbar.contrib.flask.report_exception, app)

# @auth.errorhandler(MismatchingStateError)
# def mismatching_state(e):
#     return redirect(url_for("azure.login"))
