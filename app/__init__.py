# -*- encoding: utf-8 -*-
"""
Python Aplication Template
Licence: GPLv3
"""

from flask import Flask
from flask_bootstrap import Bootstrap
from flask_mongoengine import MongoEngine
from flask_login import LoginManager
from flask_mail import Mail
from datetime import timedelta

app = Flask(__name__)

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=60)
app.permanent_session_lifetime = timedelta(days=60)
app.config.from_object('app.configuration.DevelopmentConfig')

app.config['MONGODB_SETTINGS'] = {
    "db": "osp",
}
db = MongoEngine(app)
bs = Bootstrap(app) #flask-bootstrap


from app import views, models
