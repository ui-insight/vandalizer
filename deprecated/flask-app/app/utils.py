# app/utils.py
import os

from flask import session

from app.models import User
from app.utilities.document_manager import DocumentManager


def load_user():
    if is_dev():
        # Create a admin
        user = User.objects(user_id="0").first()
        if not user:
            user = User(user_id="0", is_admin=True)
            user.save()
        session["user_id"] = "0"
        return user
    if "user_id" in session:
        user = User.objects(user_id=session["user_id"]).first()
        if user:
            return user
        user = User(user_id=session["user_id"], is_admin=False)
        user.save()
        return user
    return None


def is_dev() -> bool:
    env = os.getenv("FLASK_ENV", "development").lower()
    return env != "production"


def ingest_semantics(document, user_id) -> None:
    # semantics = SemanticIngest()
    # semantics.ingest(document=document)
    with DocumentManager() as document_manager:
        document_path = document.absolute_path

        document_manager.add_document(
            user_id=user_id,
            document_name=document.title,
            document_id=document.uuid,
            doc_path=document_path,
        )
