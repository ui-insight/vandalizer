#!/usr/bin/env python3
"""Models for the application. Defines data structures and relationships."""

import datetime
import datetime as dt
import json
import os
from enum import Enum
from pathlib import Path

import mongoengine as me
from mongoengine import CASCADE, PULL, signals
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
    tasks = me.ListField(
        me.ReferenceField("WorkflowStepTask", reverse_delete_rule=PULL),
    )
    data = me.DictField(required=False)

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
    steps = me.ListField(
        me.ReferenceField("WorkflowStep", reverse_delete_rule=PULL),
    )
    attachments = me.ListField(
        me.ReferenceField("WorkflowAttachment", reverse_delete_rule=PULL),
    )
    num_executions = me.IntField(default=0)
    space = me.StringField(required=False, max_length=100)
    verified = me.BooleanField(default=False)
    created_by_user_id = me.StringField(required=False, max_length=200)


class WorkflowResult(me.Document):
    """Workflow result model. Represents the result of a workflow execution."""

    workflow = me.ReferenceField("Workflow", reverse_delete_rule=CASCADE)
    num_steps_completed = me.IntField(default=0)
    num_steps_total = me.IntField(default=0)
    steps_output = me.DictField()
    final_output = me.DictField(required=False)
    start_time = me.DateTimeField(default=datetime.datetime.now)
    status = me.StringField(default="running")
    session_id = me.StringField(required=True, max_length=50)


# Teams
class Team(me.Document):
    """A collaborative group of users."""

    uuid = me.StringField(required=True, max_length=200, unique=True)
    name = me.StringField(required=True, max_length=200)
    owner_user_id = me.StringField(required=True, max_length=200)
    created_at = me.DateTimeField(default=datetime.datetime.now)


class TeamMembership(me.Document):
    """Users belonging to teams with a role."""

    team = me.ReferenceField(Team, required=True, reverse_delete_rule=me.CASCADE)
    user_id = me.StringField(required=True, max_length=200)
    role = me.StringField(default="member", choices=["owner", "admin", "member"])
    created_at = me.DateTimeField(default=datetime.datetime.now)

    meta = {
        "indexes": [
            {"fields": ["team", "user_id"], "unique": True},
        ],
    }


class TeamInvite(me.Document):
    """Pending invite to a team by email."""

    team = me.ReferenceField(Team, required=True, reverse_delete_rule=me.CASCADE)
    email = me.StringField(required=True, max_length=320)  # RFC-ish
    invited_by_user_id = me.StringField(required=True, max_length=200)
    role = me.StringField(default="member", choices=["owner", "admin", "member"])
    token = me.StringField(required=True, max_length=200, unique=True)  # secure random
    accepted = me.BooleanField(default=False)
    created_at = me.DateTimeField(default=datetime.datetime.now)

    meta = {
        "indexes": [
            {"fields": ["team", "email"], "unique": True},
            {"fields": ["token"], "unique": True},
        ]
    }


class User(me.Document):
    """User model. Represents a user in the system."""

    user_id = me.StringField(required=True, max_length=200)
    is_admin = me.BooleanField(default=False)
    name = me.StringField()

    current_team = me.ReferenceField(
        "Team", required=False, reverse_delete_rule=me.NULLIFY
    )

    @property
    def current_team_uuid(self) -> str | None:
        return getattr(self.current_team, "uuid", None)

    def ensure_current_team(self) -> "Team | None":
        if self.current_team:
            return self.current_team
        team = _pick_default_team_for_user(self.user_id)
        if team:
            self.current_team = team
            self.save()  # triggers pre_save but already set, safe/idempotent
        return team


def _role_rank(role: str) -> int:
    # lower is higher priority
    return {"owner": 0, "admin": 1, "member": 2}.get(role, 3)


def _pick_default_team_for_user(user_id: str) -> "Team | None":
    memberships = list(
        TeamMembership.objects(user_id=user_id)  # uses your existing index
    )
    if not memberships:
        return None
    memberships.sort(key=lambda m: (_role_rank(m.role), m.created_at))
    return memberships[0].team


def _user_pre_save(sender, document: "User", **kwargs):
    # Only fill if empty; don't override an explicit selection
    if getattr(document, "current_team", None) is None:
        team = _pick_default_team_for_user(document.user_id)
        if team:
            document.current_team = team


signals.pre_save.connect(_user_pre_save, sender=User)


class SmartDocument(me.Document):
    """SmartDocument model. Represents a smart document in the system."""

    path = me.StringField(required=True, max_length=200)
    downloadpath = me.StringField(required=True, max_length=200)
    processing = me.BooleanField(default=False)
    validating = me.BooleanField(default=False)
    valid = me.BooleanField(default=True)
    validation_feedback = me.StringField(required=False, max_length=5000)
    task_id = me.StringField(
        default=None, required=False, max_length=200
    )  # Celery task ID for processing
    task_status = me.StringField(
        default=None,
        required=False,
        max_length=200,
    )  # Status of the Celery task (e.g., 'layout', 'ocr', 'security', 'done')
    title = me.StringField(required=True, max_length=200)
    raw_text = me.StringField(required=True, default="")
    extension = me.StringField(default="pdf", max_length=10)
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
        doc_path = Path(app.root_path) / "static" / "uploads" / self.path
        """Returns the absolute path to the document file."""
        if not os.path.exists(str(doc_path)):
            print("Does not exist adjusting path")
            doc_path = (
                Path(app.root_path) / "static" / "uploads" / self.user_id / self.path
            )
        else:
            print("Exists returning path")
        return doc_path

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
    verified = me.BooleanField(default=False)
    created_by_user_id = me.StringField(required=False, max_length=200)

    def item_count(self) -> int:
        """Return the count of items associated with this search set."""
        return SearchSetItem.objects(searchset=self.uuid).count()

    def search_phrases_csv(self) -> str:
        """Return a list of search items associated with this search set."""
        items = SearchSetItem.objects(searchset=self.uuid, searchtype="extraction")
        return ",".join([item.searchphrase for item in items])

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


class LibraryScope(Enum):
    PERSONAL = "personal"  # one per user
    TEAM = "team"  # one per team
    VERIFIED = "verified"  # global verified catalog


class LibraryItem(me.Document):
    """
    A pointer to either a Workflow or a SearchSet, with provenance and optional verification stamp.
    """

    # Polymorphic reference to Workflow or SearchSet
    obj = me.GenericReferenceField(required=True)  # Workflow OR SearchSet

    # For quick filtering without dereferencing
    kind = me.StringField(required=True, choices=["workflow", "searchset"])

    added_by_user_id = me.StringField(required=True, max_length=200)
    added_at = me.DateTimeField(default=datetime.datetime.now)

    # Whether the referenced object is currently marked verified (mirrors source)
    verified = me.BooleanField(default=False)
    verified_at = me.DateTimeField(required=False)
    verified_by_user_id = me.StringField(required=False, max_length=200)

    # Optional tags/notes to help curate libraries
    tags = me.ListField(me.StringField(max_length=100), default=[])
    note = me.StringField(required=False, max_length=2000)

    meta = {
        "indexes": [
            # Prevent duplicate entries for the same object inside the same library
            {"fields": ["obj", "kind"]},
        ]
    }


# Library
class Library(me.Document):
    """
    A collection of library items under a given scope.
    - PERSONAL:   one per user (owner_user_id populated)
    - TEAM:       one per team (team ref populated)
    - VERIFIED:   global catalog (neither owner_user_id nor team populated)
    """

    scope = me.EnumField(LibraryScope, required=True)
    title = me.StringField(required=True, max_length=200)
    description = me.StringField(required=False, max_length=2000)

    # Only one of these is set depending on scope
    owner_user_id = me.StringField(required=False, max_length=200)  # PERSONAL
    team = me.ReferenceField(
        Team, required=False, reverse_delete_rule=me.CASCADE
    )  # TEAM

    created_at = me.DateTimeField(default=datetime.datetime.now)
    updated_at = me.DateTimeField(default=datetime.datetime.now)

    items = me.ListField(me.ReferenceField("LibraryItem", reverse_delete_rule=me.PULL))

    meta = {
        "indexes": [
            # enforce uniqueness of library by scope & owner/team
            {"fields": ["scope", "owner_user_id"], "unique": True, "sparse": True},
            {"fields": ["scope", "team"], "unique": True, "sparse": True},
        ]
    }


# Activity / Data Analytics


# ---- Activity Types & Status ----


class ActivityType(str, Enum):
    CONVERSATION = "conversation"  # chat/agent session messages
    SEARCH_SET_RUN = "search_set_run"  # SearchSet execution
    WORKFLOW_RUN = "workflow_run"  # WorkflowResult / workflow execution


class ActivityStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


# ---- Activity Event ----


class ActivityEvent(me.Document):
    """
    Immutable-ish append-only activity events for the live feed (and audits).
    One document per top-level run (conversation session, search_set run, workflow run).
    """

    # What happened
    type = me.StringField(required=True, choices=[t.value for t in ActivityType])
    status = me.StringField(
        required=True,
        choices=[s.value for s in ActivityStatus],
        default=ActivityStatus.RUNNING.value,
    )

    # Who/where
    user_id = me.StringField(required=True, max_length=200)
    team_id = me.StringField(
        required=False, max_length=200
    )  # optional: derive via TeamMembership
    space = me.StringField(required=False, max_length=200)

    # When
    started_at = me.DateTimeField(default=dt.datetime.utcnow)
    finished_at = me.DateTimeField(required=False)

    # Linkage to domain objects (use whichever applies)
    # NOTE: keep light to avoid deref unless needed in UI
    conversation_id = me.StringField(
        required=False, max_length=200
    )  # ChatHistory.id or custom session id
    search_set_uuid = me.StringField(required=False, max_length=200)
    workflow_result = me.ReferenceField(
        "WorkflowResult", reverse_delete_rule=me.CASCADE, required=False
    )
    workflow = me.ReferenceField(
        "Workflow", reverse_delete_rule=me.NULLIFY, required=False
    )

    # Metrics (optional but handy for analytics + UI badges)
    # keep primitives: ints/floats/short strings
    message_count = me.IntField(default=0)  # conversation
    tokens_input = me.IntField(default=0)  # LLM tokens in
    tokens_output = me.IntField(default=0)  # LLM tokens out
    documents_touched = me.IntField(default=0)  # # of docs referenced
    steps_total = me.IntField(default=0)  # workflow
    steps_completed = me.IntField(default=0)  # workflow
    error = me.StringField(required=False, max_length=2000)

    # Free-form details to inspect/debug without dereferencing
    meta_summary = me.DictField(
        default={}
    )  # e.g., {"model":"gpt-4o", "search_set_title":"Acme NDA"}
    tags = me.ListField(me.StringField(max_length=50), default=[])

    meta = {
        "indexes": [
            {"fields": ["-started_at"]},
            {"fields": ["user_id", "-started_at"]},
            {"fields": ["team_id", "-started_at"]},
            {"fields": ["type", "-started_at"]},
            {"fields": ["status", "-started_at"]},
        ]
    }

    @property
    def is_running(self) -> bool:
        return self.status in {
            ActivityStatus.QUEUED.value,
            ActivityStatus.RUNNING.value,
        }

    @property
    def duration_ms(self) -> int | None:
        if not self.finished_at:
            return None
        return int((self.finished_at - self.started_at).total_seconds() * 1000)


class DailyUsageAggregate(me.Document):
    """
    Per-day rollups for analytics.
    Separate docs per (scope, principal) so we can query by user, team, and global.
    """

    # Partition key
    date = me.DateField(required=True)  # UTC day boundary
    scope = me.StringField(required=True, choices=["user", "team", "global"])
    user_id = me.StringField(required=False, max_length=200)  # when scope == 'user'
    team_id = me.StringField(required=False, max_length=200)  # when scope == 'team'

    # Generic counts by type
    conversations = me.IntField(default=0)
    searches = me.IntField(default=0)
    workflows_started = me.IntField(default=0)
    workflows_completed = me.IntField(default=0)
    workflows_failed = me.IntField(default=0)

    # Resource metrics
    tokens_input = me.IntField(default=0)
    tokens_output = me.IntField(default=0)
    documents_touched = me.IntField(default=0)

    # Time & size metrics (ms for precision; convert in UI)
    workflow_duration_ms = me.IntField(default=0)  # sum of durations for completed
    conversation_messages = me.IntField(default=0)

    created_at = me.DateTimeField(default=dt.datetime.utcnow)
    updated_at = me.DateTimeField(default=dt.datetime.utcnow)

    meta = {
        "indexes": [
            {"fields": ["date", "scope", "user_id"], "unique": True, "sparse": True},
            {"fields": ["date", "scope", "team_id"], "unique": True, "sparse": True},
            {"fields": ["-date", "scope"]},
        ]
    }
