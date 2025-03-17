from flask import (
    Blueprint,
    redirect,
    url_for,
    session,
    render_template,
    request,
    jsonify,
)

from . import feedback
from app.utils import load_user
from app import azure
from app.models import User, ExtractionQualityRecord, Feedback, FeedbackCounter
import json


@feedback.route("/submit_rating", methods=["POST"])
def submit_rating():
    data = request.get_json()
    print(data)
    pdf_title = data["pdf_title"]
    rating = data["rating"]
    comment = data["comment"]
    result_json = data["result_json"]
    result_json_str = json.dumps(result_json)
    record = ExtractionQualityRecord(
        pdf_title=pdf_title,
        star_rating=rating,
        comment=comment,
        result_json=result_json_str,
    )
    record.save()
    return jsonify({"complete": True})

