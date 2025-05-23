#!/usr/bin/env python3
"""Models for the application. Defines data structures and relationships."""

import datetime
import json
import os
from enum import Enum
from pathlib import Path

import mongoengine as me
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
)
from pypdf import PdfReader

from app import app


class UserModelConfig(me.Document):
    """User configuration model. Represents user-specific settings."""

    user_id = me.StringField(required=True, max_length=200)
    name = me.StringField(required=True, max_length=200)
    temperature = me.FloatField(default=0.7)
    top_p = me.FloatField(default=0.9)
    available_models = me.ListField(me.DictField(), required=False, default=[])


class WorkflowStepTask(me.Document):
    """Workflow step task model. Represents a task within a workflow step."""

    name = me.StringField(required=True, max_length=50)
    data = me.DictField(required=True)

    def extraction_items(self):
        if "search_set_uuid" in self.data:
            search_set = SearchSet.objects(uuid=self.data["search_set_uuid"]).first()
            if search_set is None:
                return []
            items = search_set.extraction_items()
            return [item.searchphrase for item in items] if items else []
        if "searchphrases" in self.data:
            return [phrase.strip() for phrase in self.data["searchphrases"].split(",")]

        return 0


class WorkflowStep(me.Document):
    """Workflow step model. Represents a step within a workflow."""

    name = me.StringField(required=True, max_length=50)
    tasks = me.ListField(me.ReferenceField(WorkflowStepTask))

    data = me.DictField(required=False)

    # TODO: This is deprecated need to refactor out
    def extraction_items(self):
        if "search_set_uuid" in self.data:
            search_set = SearchSet.objects(uuid=self.data["search_set_uuid"]).first()
            items = search_set.extraction_items()
            return [item.searchphrase for item in items] if items else []
        if "searchphrases" in self.data:
            return [phrase.strip() for phrase in self.data["searchphrases"].split(",")]

        return 0


class WorkflowAttachment(me.Document):
    """Workflow attachment model. Represents an attachment within a workflow."""

    attachment = me.StringField(required=True, max_length=50)


class Workflow(me.Document):
    """Workflow model. Represents a complete workflow."""

    name = me.StringField(required=True, max_length=500)
    description = me.StringField(required=False, max_length=2000)
    user_id = me.StringField(required=True, max_length=200)
    created_at = me.DateTimeField(default=datetime.datetime.now)
    updated_at = me.DateTimeField(default=datetime.datetime.now)
    steps = me.ListField(me.ReferenceField(WorkflowStep))
    attachments = me.ListField(me.ReferenceField(WorkflowAttachment))
    num_executions = me.IntField(default=0)
    space = me.StringField(required=False, max_length=100)


class WorkflowResult(me.Document):
    """Workflow result model. Represents the result of a workflow execution."""

    workflow = me.ReferenceField(Workflow)
    num_steps_completed = me.IntField(default=0)
    num_steps_total = me.IntField(default=0)
    steps_output = me.DictField()
    start_time = me.DateTimeField(default=datetime.datetime.now)
    status = me.StringField(default="running")
    session_id = me.StringField(required=True, max_length=50)


class User(me.Document):
    """User model. Represents a user in the system."""

    user_id = me.StringField(required=True, max_length=200)
    is_admin = me.BooleanField(default=False)


class SmartDocument(me.Document):
    """SmartDocument model. Represents a smart document in the system."""

    path = me.StringField(required=True, max_length=200)
    processing = me.BooleanField(default=False)
    validating = me.BooleanField(default=False)
    valid = me.BooleanField(default=True)
    validation_feedback = me.StringField(required=False, max_length=5000)
    task_id = me.StringField(
        default=None, required=False, max_length=200
    )  # Celery task ID for processing
    title = me.StringField(required=True, max_length=200)
    raw_text = me.StringField(required=True, default="")
    extension = me.StringField(default="pdf", max_length=10)
    task_id = me.StringField(
        default=None, required=False, max_length=200
    )  # Celery task ID for processing
    uuid = me.StringField(required=True, max_length=200)
    space = me.StringField(required=True, max_length=200)
    user_id = me.StringField(required=True, max_length=200)
    created_at = me.DateTimeField(default=datetime.datetime.now)
    updated_at = me.DateTimeField(default=datetime.datetime.now)
    folder = me.StringField(required=False, max_length=200)
    is_default = me.BooleanField(
        default=False,
    )  # default document to add to the llm context
    token_count = me.IntField(default=0)
    num_pages = me.IntField(default=0)

    @property
    def absolute_path(self) -> Path:
        """Returns the absolute path to the document file."""
        return Path(app.root_path) / "static" / "uploads" / self.path

    def time_ago_in_words(self) -> str:
        """Returns a human-readable string representing the time elapsed since the document was created."""
        now = datetime.datetime.now()
        diff = now - self.created_at

        if diff < datetime.timedelta(minutes=1):
            return f"{int(diff.total_seconds())} seconds"
        if diff < datetime.timedelta(hours=1):
            minutes = int(diff.total_seconds() / 60)
            return f"{minutes} minutes"
        if diff < datetime.timedelta(days=1):
            hours = int(diff.total_seconds() / 3600)
            return f"{hours} hours"
        if diff < datetime.timedelta(days=7):
            days = diff.days
            return f"{days} days"
        return self.created_at.strftime("%Y-%m-%d")


class SmartFolder(me.Document):
    """Represents a smart folder in the application."""

    parent_id = me.StringField(required=True, max_length=200)
    title = me.StringField(required=True, max_length=200)
    uuid = me.StringField(required=True, max_length=200)
    space = me.StringField(required=True, max_length=200)
    user_id = me.StringField(required=True, max_length=200)

    def number_of_documents(self) -> int:
        """Returns the number of documents in this smart folder."""
        return SmartDocument.objects(folder=self.uuid).count()

    def document_uuids(self) -> list[str]:
        """Returns a list of UUIDs of documents in this smart folder."""
        return SmartDocument.objects(folder=self.uuid).values_list("uuid")


class Space(me.Document):
    """Represents a space in the application."""

    uuid = me.StringField(required=True, max_length=200)
    title = me.StringField(required=True, max_length=200)
    user = me.StringField(required=False, max_length=200)


class ExtractionQualityRecord(me.Document):
    """Represents an extraction quality record in the application."""

    pdf_title = me.StringField(required=True, max_length=200)
    result_json = me.StringField(required=True, max_length=5000)
    star_rating = me.FloatField(required=True)
    comment = me.StringField(required=False, max_length=5000)


class SearchSetItem(me.Document):
    """Represents a extraction item in the application."""

    searchphrase = me.StringField(required=True)
    searchset = me.StringField(max_length=200)
    searchtype = me.StringField(required=True, max_length=200)
    text_blocks = me.ListField(me.StringField(), required=False)
    pdf_binding = me.StringField(required=False, max_length=200)
    user_id = me.StringField(required=False, max_length=200)
    space_id = me.StringField(required=False, max_length=200)
    title = me.StringField(required=False, max_length=200)

    def to_workflow_step_data(self):
        return {
            "type": self.searchtype,
            "search_set_item_id": self.id,
            "search_set_item_title": self.title,
            "prompt": self.searchphrase,
        }


class SearchSet(me.Document):
    """Represents an extraction set in the application."""

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

    def item_count(self) -> int:
        """Return the count of items associated with this search set."""
        return SearchSetItem.objects(searchset=self.uuid).count()

    def search_items(self) -> list[SearchSetItem]:
        """Return a list of search items associated with this search set."""
        return SearchSetItem.objects(searchset=self.uuid, searchtype="search")

    def extraction_items(self) -> list[SearchSetItem]:
        """Return a list of extraction items associated with this search set."""
        return SearchSetItem.objects(searchset=self.uuid, searchtype="extraction")

    def items(self) -> list[SearchSetItem]:
        """Return a list of all items associated with this search set."""
        return SearchSetItem.objects(searchset=self.uuid)

    def get_fillable_fields(self) -> list[str]:
        """Return a list of fillable fields from the PDF associated with this search set."""
        if self.fillable_pdf_url is None or self.fillable_pdf_url == "":
            return []
        pdf_path = os.path.join(
            app.root_path,
            "static",
            "uploads",
            self.fillable_pdf_url,
        )
        reader = PdfReader(pdf_path)
        form_fields = reader.get_fields()
        fields = []
        for field_name in form_fields:
            fields.append(field_name)

        return fields

    def to_workflow_step_data(self):
        return {
            "search_set_type": self.set_type,
            "search_set_uuid": self.uuid,
            "search_set_title": self.title,
            "search_set_space": self.space,
        }


class WhiteList(me.Document):
    """Represents a whitelist entry for an email address."""

    email = me.StringField(required=True, max_length=200)

    def check_email(self):
        return WhiteList.objects(email=self.email).first()


class Feedback(me.Document):
    """Represents a feedback entry for a user."""

    user_id = me.StringField(required=True, max_length=200)
    # feedback is 'positive' or 'negative'
    feedback = me.StringField(required=True, max_length=2000)
    question = me.StringField(required=True, max_length=10000)
    answer = me.StringField(required=True, max_length=100000)
    context = me.StringField(required=False, max_length=500000)
    docs_uuids = me.ListField(me.StringField(), required=True)
    created_at = me.DateTimeField(default=datetime.datetime.now)


class FeedbackCounter(me.Document):
    """Represents a counter for feedback entries."""

    count = me.IntField(default=0)


class ChatRole(Enum):
    """Represents a role in a chat."""

    SYSTEM = "system"
    USER = "user"


MAX_CHAT_MESSAGES = 20


class ChatMessage(me.Document):
    """Represents a message in a chat."""

    role = me.EnumField(ChatRole, required=True)
    message = me.StringField(required=True, max_length=500000)
    created_at = me.DateTimeField(default=datetime.datetime.now)


class ChatHistory(me.Document):
    """Represents a chat history for a user."""

    user_id = me.StringField(required=True, max_length=200)
    messages = me.ListField(me.ReferenceField(ChatMessage))
    last_conversation_id = me.StringField(required=False, max_length=200)
    created_at = me.DateTimeField(default=datetime.datetime.now)
    updated_at = me.DateTimeField(default=datetime.datetime.now)

    @staticmethod
    def get_latest_conversation_messages(user_id):
        # latest conversation MAX_CHAT_MESSAGES from the user
        history = ChatHistory.objects(user_id=user_id).order_by("-created_at").first()
        if history is None:
            return None
        # take the last 2h of conversation
        return [m for m in history.messages if convert_to_hours(m) < 2]


def convert_to_hours(message):
    time_slot = datetime.datetime.now() - message.created_at
    return time_slot.total_seconds() / 3600


class AgentHistory(me.Document):
    """Simple agent history model for storing conversation messages as JSON."""

    user_id = me.StringField(required=True)
    messages = me.ListField(me.DictField())  # Store messages as plain JSON
    created_at = me.DateTimeField(default=datetime.datetime.now)

    meta = {"collection": "agent_history"}

    @classmethod
    def get_latest_conversation_messages(cls, user_id):
        """Retrieve the latest conversation messages for a user."""
        # Get today's conversation and filter by the latest conversation
        # history = cls.objects(user_id=user_id).order_by("-created_at").first()
        today_history = cls.objects(user_id=user_id).filter(
            created_at__gte=datetime.datetime.now().replace(hour=0, minute=0, second=0),
        )
        if today_history:
            latest_conversation = today_history.order_by("-created_at").first()
            # return latest_conversation.messages
            messages: list[ModelMessage] = []
            for message in latest_conversation.messages:
                # convert message to ModelMessage
                if message["kind"] == "request":
                    messages.append(ModelRequest(**message))
                elif message["kind"] == "response":
                    messages.append(ModelResponse(**message))
            return messages
        return []

    @classmethod
    def save_messages(cls, user_id, messages_json):
        """Save new messages to the history."""
        messages_data = json.loads(messages_json)
        return AgentHistory(user_id=user_id, messages=messages_data).save()
