# app/utils.py
from app.models import User
from flask import session
import os



def load_user():
    if "dev" in os.environ.get("APP_ENV"):
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


def ingest_semantics(document):
    semantics = SemanticIngest()
    semantics.ingest(document=document)
    document_manager = DocumentManager()
    document_manager.add_document(
        user_id=document.user_id,
        doc_path=document.path,
        document_name=document.title,
        document_id=document.uuid,
    )
    user_docs = document_manager.list_user_documents(document.user_id)

