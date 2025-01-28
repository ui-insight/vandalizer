from flask import (Blueprint, 
                   redirect, 
                   url_for, 
                   session, 
                   render_template, 
                   request, jsonify)

from . import auth
from app.utils import load_user
from app import azure
from app.models import User, ExtractionQualityRecord, Feedback, FeedbackCounter
import json

feedback = Blueprint('feedback', __name__)


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

####### Feedback #######
## MARK: Feedback
@feedback.route("/feedback", methods=["POST"])
def feedback():

    user = load_user()
    user_id = user.user_id
    data = request.get_json()

    feedback_type = data.get("feedback_type")
    question = data.get("question")
    answer = data.get("answer")
    context = data.get("context")
    context = " ".join(context)
    docs_uuids = data.get("docs_uuids")

    print("feedback_type", feedback_type)
    print("question", question)
    print("docs_uuids", docs_uuids)
    feedback = Feedback(
        user_id=user_id,
        feedback=feedback_type,
        question=question,
        answer=answer,
        context=context,
        docs_uuids=docs_uuids,
    )

    feedback.save()

    # Maintain feedback count
    feedback_counter = FeedbackCounter.objects().first()

    if not feedback_counter:
        feedback_counter = FeedbackCounter(count=0)

    feedback_counter.count += 1
    feedback_counter.save()
    max_feedback_count = 100

    response = {
        "complete": True,
    }
    return jsonify(response)
