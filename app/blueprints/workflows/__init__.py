from flask import Blueprint

workflows = Blueprint("workflows", __name__)

from . import routes
