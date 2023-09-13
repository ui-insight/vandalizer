from flask_wtf import FlaskForm
from flask_wtf.file import FileRequired, FileField, FileAllowed
from wtforms import StringField, TextAreaField, DateTimeField, DateField, PasswordField, SubmitField, SelectField, BooleanField, RadioField, FloatField
from wtforms.validators import DataRequired, Email, EqualTo
from datetime import datetime

class LoginForm(FlaskForm):
    email = StringField('Email',validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class SpaceForm(FlaskForm):
    title = StringField('Title',validators=[DataRequired()])
    submit = SubmitField('Login')
