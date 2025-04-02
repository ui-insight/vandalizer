"""Handles feedback routing."""

import json

from flask import (
    jsonify,
    request,
)
from flask.typing import ResponseReturnValue

from app.models import ExtractionQualityRecord

from . import feedback


@feedback.route("/submit_rating", methods=["POST"])
def submit_rating() -> ResponseReturnValue:
    """Handle the submission of a rating and feedback for an extraction."""
    data = request.get_json()
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
