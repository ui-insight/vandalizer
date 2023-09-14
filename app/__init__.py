# -*- encoding: utf-8 -*-
"""
Python Aplication Template
Licence: GPLv3
"""

from flask import Flask
from flask_bootstrap import Bootstrap
import mongoengine as me
from flask_login import LoginManager
from flask_mail import Mail
from datetime import timedelta
from app.utilities.llm_manager import LLMManager
from flask_basicauth import BasicAuth

app = Flask(__name__)

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=60)
app.permanent_session_lifetime = timedelta(days=60)
app.config.from_object('app.configuration.DevelopmentConfig')

me.connect('osp')

bs = Bootstrap(app) #flask-bootstrap
llm = LLMManager()
llm.root_path = app.root_path

app.config['BASIC_AUTH_USERNAME'] = 'admin'
app.config['BASIC_AUTH_PASSWORD'] = 'rcds'
app.config['BASIC_AUTH_FORCE'] = True
basic_auth = BasicAuth(app)

from app import views, models
