import mongoengine as me
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import datetime
import os
from pypdf import PdfReader
from app import app


class User(me.Document):
    user_id = me.StringField(required=True, max_length=200)
    is_admin = me.BooleanField(default=False)


class SmartDocument(me.Document):
    path = me.StringField(required=True, max_length=200)
    title = me.StringField(required=True, max_length=200)
    uuid = me.StringField(required=True, max_length=200)
    space = me.StringField(required=True, max_length=200)
    user_id = me.StringField(required=True, max_length=200)
    created_at = me.DateTimeField(default=datetime.datetime.now)
    updated_at = me.DateTimeField(default=datetime.datetime.now)
    folder = me.StringField(required=False, max_length=200)
    is_default = me.BooleanField(
        default=False
    )  # default document to add to the llm context
    token_count = me.IntField(default=0)
    num_pages = me.IntField(default=0)

    def time_ago_in_words(self):
        now = datetime.datetime.now()
        diff = now - self.created_at

        if diff < datetime.timedelta(minutes=1):
            return f"{int(diff.total_seconds())} seconds"
        elif diff < datetime.timedelta(hours=1):
            minutes = int(diff.total_seconds() / 60)
            return f"{minutes} minutes"
        elif diff < datetime.timedelta(days=1):
            hours = int(diff.total_seconds() / 3600)
            return f"{hours} hours"
        elif diff < datetime.timedelta(days=7):
            days = diff.days
            return f"{days} days"
        else:
            return self.created_at.strftime("%Y-%m-%d")


class SmartFolder(me.Document):
    parent_id = me.StringField(required=True, max_length=200)
    title = me.StringField(required=True, max_length=200)
    uuid = me.StringField(required=True, max_length=200)
    space = me.StringField(required=True, max_length=200)
    user_id = me.StringField(required=True, max_length=200)

    def number_of_documents(self):
        return SmartDocument.objects(folder=self.uuid).count()

    def document_uuids(self):
        return SmartDocument.objects(folder=self.uuid).values_list("uuid")


class Space(me.Document):
    uuid = me.StringField(required=True, max_length=200)
    title = me.StringField(required=True, max_length=200)
    user = me.StringField(required=False, max_length=200)


class ExtractionQualityRecord(me.Document):
    pdf_title = me.StringField(required=True, max_length=200)
    result_json = me.StringField(required=True, max_length=5000)
    star_rating = me.FloatField(required=True)
    comment = me.StringField(required=False, max_length=5000)


class SearchSet(me.Document):
    title = me.StringField(required=True, max_length=200)
    uuid = me.StringField(required=True, max_length=200)
    space = me.StringField(required=True, max_length=200)
    status = me.StringField(required=True, max_length=200)
    set_type = me.StringField(required=True, max_length=200)
    user_id = me.StringField(required=False, max_length=200)
    is_global = me.BooleanField(default=False)
    created_at = me.DateTimeField(default=datetime.datetime.now)
    user = me.StringField(required=False, max_length=200)
    fillable_pdf_url = me.StringField(required=False, max_length=200)

    def item_count(self):
        return SearchSetItem.objects(searchset=self.uuid).count()

    def search_items(self):
        return SearchSetItem.objects(searchset=self.uuid, searchtype="search")

    def extraction_items(self):
        return SearchSetItem.objects(searchset=self.uuid, searchtype="extraction")

    def items(self):
        return SearchSetItem.objects(searchset=self.uuid)

    def get_fillable_fields(self):
        if self.fillable_pdf_url == None or self.fillable_pdf_url == "":
            return []
        pdf_path = os.path.join(
            app.root_path, "static", "uploads", self.fillable_pdf_url
        )
        reader = PdfReader(pdf_path)
        form_fields = reader.get_fields()
        fields = []
        for field_name, field_data in form_fields.items():
            fields.append(field_name)

        return fields


class SearchSetItem(me.Document):
    searchphrase = me.StringField(required=True)
    searchset = me.StringField(required=True, max_length=200)
    searchtype = me.StringField(required=True, max_length=200)
    text_blocks = me.ListField(me.StringField(), required=False)
    pdf_binding = me.StringField(required=False, max_length=200)


class WhiteList(me.Document):
    email = me.StringField(required=True, max_length=200)

    def check_email(self):
        return WhiteList.objects(email=self.email).first()


class Feedback(me.Document):
    user_id = me.StringField(required=True, max_length=200)
    # feedback is 'positive' or 'negative'
    feedback = me.StringField(required=True, max_length=2000)
    question = me.StringField(required=True, max_length=10000)
    answer = me.StringField(required=True, max_length=100000)
    context = me.StringField(required=False, max_length=500000)
    docs_uuids = me.ListField(me.StringField(), required=True)
    created_at = me.DateTimeField(default=datetime.datetime.now)


class FeedbackCounter(me.Document):
    count = me.IntField(default=0)
