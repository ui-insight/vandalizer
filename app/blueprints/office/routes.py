#!/usr/bin/env python3
from flask import (
    Blueprint,
    request,
    jsonify,
    current_app,
    redirect,
    url_for,
    render_template,
    send_file,
)
from copy import deepcopy
import csv, os, uuid
from devtools import debug

from app.utils import load_user

from . import office

from app.utilities.chat import chat_with_prompt


@office.route("/chat", methods=["POST"])
def chat():
    user = load_user()
    user_id = user.user_id
    data = request.get_json()
    prompt = data.get("prompt", "")
    document = data.get("document", "")
    message = f"""
    {prompt}
    Document:
    {document}
    """
    debug(data)
    answer = chat_with_prompt(message, user_id)
    return jsonify(answer)
