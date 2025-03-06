# app/utils.py
from app.models import User
from flask import session
import os
from app.utilities.semantic_ingest import SemanticIngest
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
        else:
            user = User(user_id=session["user_id"], is_admin=False)
            user.save()
            print("Built new user" + user.user_id)
            return user
    return None


def is_dev():
    if "prod" in os.uname().nodename:
        return False
    elif "dev" in os.uname().nodename:
        return True
    else:
        return True


def ingest_semantics(document):
    # semantics = SemanticIngest()
    # semantics.ingest(document=document)
    document_manager = DocumentManager()
    document_manager.add_document(
        user_id=document.user_id,
        doc_path=document.absolute_path,
        document_name=document.title,
        document_id=document.uuid,
    )
