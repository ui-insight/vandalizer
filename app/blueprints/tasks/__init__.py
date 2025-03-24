from flask import Blueprint

tasks = Blueprint("tasks", __name__)

from . import routes
