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
from flask_cors import CORS
#from app.utilities.llm_manager import LLMManager
# from flask_basicauth import BasicAuth

app = Flask(__name__)
CORS(app)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=60)
app.permanent_session_lifetime = timedelta(days=60)
app.config.from_object('app.configuration.DevelopmentConfig')

me.connect('osp')

bs = Bootstrap(app) #flask-bootstrap

from app import views, models
