from flask import Blueprint

spaces = Blueprint("spaces", __name__)

from . import routes
