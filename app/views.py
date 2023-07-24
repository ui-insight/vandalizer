from flask import url_for, redirect, render_template, flash, g, session, jsonify, Response, send_file
from app import app
from app.models import User
from app.forms import LoginForm
import os
import json
import datetime
import base64
from flask import request
import zipfile

@app.route('/')
def index():
	return render_template('index.html')

