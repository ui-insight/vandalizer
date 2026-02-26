from flask import Blueprint

feedback = Blueprint("feedback", __name__)

from . import routes
