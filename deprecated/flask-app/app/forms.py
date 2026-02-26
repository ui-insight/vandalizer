#!/usr/bin/env python3
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email


class LoginForm(FlaskForm):
    """Handles user login."""

    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")


class SpaceForm(FlaskForm):
    """Handles space creation or editing."""

    title = StringField("Title", validators=[DataRequired()])
    submit = SubmitField("Login")
