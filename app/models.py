import mongoengine as me
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import datetime

class User(me.Document):
    firstname = me.StringField(required=True, max_length=200)
    lastname = me.StringField(required=True, max_length=200)
    email = me.StringField(required=True, max_length=200)
    affiliation = me.StringField(required=True, max_length=500)
    wildmarkerid = me.StringField(required=True, max_length=200)
    
    password_hash = me.StringField(required=True, max_length=200)
    
class SmartDocument(me.Document):
    path = me.StringField(required=True, max_length=200)
    title = me.StringField(required=True, max_length=200)
    uuid = me.StringField(required=True, max_length=200)
    space = me.StringField(required=True, max_length=200)

class Space(me.Document):
    uuid = me.StringField(required=True, max_length=200)
    title = me.StringField(required=True, max_length=200)
    user = me.StringField(required=False, max_length=200)

class User(me.Document):
    firstname = me.StringField(required=True, max_length=200)
    lastname = me.StringField(required=True, max_length=200)
    email = me.StringField(required=True, max_length=200)
    password_hash = me.StringField(required=True, max_length=200)


