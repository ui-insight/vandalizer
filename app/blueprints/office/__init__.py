from flask import Blueprint

office = Blueprint("office", __name__)

from . import routes
