#!/usr/bin/env python3
"""Models for the application. Defines data structures and relationships."""

import datetime
import datetime as dt
import json
import os
from datetime import timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4

import mongoengine as me
from devtools import debug
from mongoengine import CASCADE, PULL, signals
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pypdf import PdfReader
from werkzeug.security import check_password_hash, generate_password_hash

from app import app


def _as_aware_utc(dt):
    if dt is None:
        return None
    # If naive, assume it was intended as UTC (MongoEngine often stores UTC-naive)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    # If aware, normalize to UTC
    return dt.astimezone(timezone.utc)


class UserModelConfig(me.Document):
    """User configuration model. Represents user-specific settings."""

    user_id = me.StringField(required=True, max_length=200)
    name = me.StringField(required=True, max_length=200)
    temperature = me.FloatField(default=0.7)
    top_p = me.FloatField(default=0.9)
    available_models = me.ListField(me.DictField(), required=False, default=[])

    # Library Preferences
    pinned_items = me.ListField(me.StringField(), default=[])
    favorite_items = me.ListField(me.StringField(), default=[])


class SystemConfig(me.Document):
    """System-wide configuration model. Only accessible to system administrators."""

    # OCR Configuration
    ocr_endpoint = me.StringField(
        default="https://processpdf.insight.uidaho.edu", max_length=500
    )

    # LLM Configuration
    llm_endpoint = me.StringField(
        default="https://mindrouter-api.nkn.uidaho.edu/v1", max_length=500
    )

    # Available models configuration
    # Each model is a dict with keys: name, tag, external, thinking, endpoint, api_protocol
    # thinking: bool - whether the model supports thinking mode (default False)
    # endpoint: str - API endpoint URL for this specific model (optional, falls back to llm_endpoint)
    # api_protocol: str - API protocol to use: "openai", "ollama", or "vllm" (default: auto-detect)
    available_models = me.ListField(
        me.DictField(),
        default=[
            {
                "name": "gpt-oss-32k:120b",
                "tag": "University of Idaho - Private",
                "external": False,
                "thinking": False,
                "endpoint": "",
                "api_protocol": "",
            },
            {
                "name": "openai/gpt-5",
                "tag": "Cloud",
                "external": True,
                "thinking": False,
                "endpoint": "",
                "api_protocol": "",
            },
        ],
    )
    # Extraction model configuration
    # If empty, use user-selected or default model
    extraction_model = me.StringField(default="", max_length=200)
    # Extraction strategy configuration
    # two_pass: thinking draft -> structured final (no thinking)
    # one_pass_thinking: structured extraction with thinking enabled
    # one_pass_no_thinking: structured extraction with thinking disabled
    extraction_strategy = me.StringField(
        default="two_pass",
        choices=["two_pass", "one_pass_thinking", "one_pass_no_thinking"],
        max_length=50,
    )

    # UI Configuration
    highlight_color = me.StringField(
        default="#eab308",  # Vandal gold/yellow (Tailwind yellow-500)
        max_length=50,
    )
    ui_radius = me.StringField(default="12px", max_length=50)

    # Authentication Configuration
    # List of enabled authentication methods
    auth_methods = me.ListField(me.StringField(), default=["password"])

    # OAuth/SAML provider configurations
    # Each provider is a dict with keys:
    # - provider: "azure" | "saml" | "google" | "github" | etc.
    # - enabled: bool
    # - display_name: str (e.g., "Sign in with Azure")
    # - client_id: str
    # - client_secret: str (encrypted in production)
    # - tenant_id: str (Azure-specific)
    # - redirect_uri: str
    # - metadata_url: str (SAML-specific)
    # - entity_id: str (SAML-specific)
    # - authorization_endpoint: str (custom OAuth)
    # - token_endpoint: str (custom OAuth)
    # - userinfo_endpoint: str (custom OAuth)
    oauth_providers = me.ListField(me.DictField(), default=[])

    # Metadata
    updated_at = me.DateTimeField(default=datetime.datetime.now)
    updated_by = me.StringField(max_length=200)

    meta = {"collection": "system_config", "indexes": []}

    @classmethod
    def get_config(cls):
        """Get or create the singleton system configuration."""
        config = cls.objects.first()
        if not config:
            config = cls().save()
        return config


class WorkflowStepTask(me.Document):
    """Workflow step task model. Represents a task within a workflow step."""

    name = me.StringField(required=True, max_length=500)
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
    
    # Passive Vandalizer: Input configuration (how workflow triggers)
    input_config = me.DictField(required=False, default=lambda: {
        'manual_enabled': True,  # Existing manual "Run" behavior
        'fixed_documents': [],  # List of {uuid, title} dicts - always included in every run
        'folder_watch': {
            'enabled': False,
            'folders': [],  # List of SmartFolder UUIDs to watch
            'delay_seconds': 300,  # Wait 5 min after upload
            'file_filters': {
                'types': [],  # e.g., ['pdf', 'docx']
                'exclude_patterns': []  # e.g., ['*_draft*']
            },
            'batch_mode': 'per_document'  # or 'collect_batch'
        },
        'conditions': []  # Optional document filters
    })
    
    # Passive Vandalizer: Output configuration (what happens after completion)
    output_config = me.DictField(required=False, default=lambda: {
        'storage': {
            'enabled': False,
            'destination_folder': None,  # SmartFolder UUID
            'file_naming': '{date}_{workflow_name}_results',
            'format': 'csv',  # csv, json, xlsx
            'append_mode': False
        },
        'notifications': []  # List of notification configs
    })
    
    # Passive Vandalizer: Resource controls
    resource_config = me.DictField(required=False, default=lambda: {
        'budget': {
            'daily_token_limit': None,
            'monthly_token_limit': None
        },
        'throttling': {
            'max_concurrent': 3,
            'min_delay_between_runs': 60
        },
        'retry': {
            'max_retries': 3,
            'retry_delay_seconds': 300
        }
    })
    
    # Passive Vandalizer: Statistics tracking
    stats = me.DictField(required=False, default=lambda: {
        'total_runs': 0,
        'manual_runs': 0,
        'passive_runs': 0,
        'successful_runs': 0,
        'failed_runs': 0,
        'documents_processed': 0,
        'tokens_used': 0,
        'last_run_at': None,
        'last_passive_run_at': None
    })


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
    current_step_name = me.StringField(required=False, max_length=500)
    current_step_detail = me.StringField(required=False, max_length=50000)
    current_step_preview = me.StringField(required=False)
    
    # Passive Vandalizer: Passive execution tracking
    trigger_event = me.ReferenceField("WorkflowTriggerEvent", required=False)
    trigger_type = me.StringField(required=False)  # Denormalized for queries: 'manual', 'folder_watch', etc.
    is_passive = me.BooleanField(default=False)
    input_context = me.DictField(required=False)  # For chained workflows, API metadata


class WorkflowTriggerEvent(me.Document):
    """Tracks pending and completed triggers for passive workflow execution."""
    
    uuid = me.StringField(required=True, max_length=200, unique=True)
    workflow = me.ReferenceField("Workflow", reverse_delete_rule=CASCADE)
    trigger_type = me.StringField(
        required=True,
        choices=["manual", "folder_watch", "schedule", "api", "chain", "m365_intake"]
    )
    status = me.StringField(
        required=True,
        choices=["pending", "queued", "running", "completed", "failed", "skipped"],
        default="pending"
    )

    # Documents to process
    documents = me.ListField(me.ReferenceField("SmartDocument"))
    document_count = me.IntField(default=0)

    # M365 work item reference (set when trigger_type == "m365_intake")
    work_item = me.ReferenceField("WorkItem", required=False)

    # Trigger context
    trigger_context = me.DictField()  # folder ref, schedule name, etc.
    
    # Timing
    created_at = me.DateTimeField(default=datetime.datetime.now)
    process_after = me.DateTimeField()  # For delayed processing
    queued_at = me.DateTimeField()
    started_at = me.DateTimeField()
    completed_at = me.DateTimeField()
    duration_ms = me.IntField()
    
    # Results
    workflow_result = me.ReferenceField("WorkflowResult")
    documents_succeeded = me.IntField(default=0)
    documents_failed = me.IntField(default=0)
    tokens_used = me.IntField(default=0)
    error = me.StringField()
    
    # Retry tracking
    attempt_number = me.IntField(default=0)
    max_attempts = me.IntField(default=3)
    next_retry_at = me.DateTimeField()
    
    # Output delivery status
    output_delivery = me.DictField(default=lambda: {
        "storage_status": None,
        "storage_path": None,
        "notifications_sent": [],
        "webhooks_called": [],
        "chains_triggered": []
    })
    
    meta = {
        "collection": "workflow_trigger_events",
        "indexes": [
            "workflow",
            "status",
            "process_after",
            "trigger_type",
            "created_at"
        ]
    }


class EvaluationPlan(me.Document):
    """Evaluation plan generated for a workflow. Contains a checklist of validation checks."""

    uuid = me.StringField(default=lambda: uuid4().hex, required=True, unique=True)
    workflow = me.ReferenceField("Workflow", reverse_delete_rule=CASCADE, required=True)

    coverage_level = me.StringField(
        default="standard",
        choices=["quick", "standard", "exhaustive"],
        max_length=20,
    )
    model_used = me.StringField(required=False, max_length=200)

    # Each check dict: check_id, check_type, target_step, target_field, description,
    # severity (must/should/nice), weight, deterministic, validation_rule, llm_prompt
    checks = me.ListField(me.DictField(), default=[])
    num_checks = me.IntField(default=0)

    created_at = me.DateTimeField(
        default=lambda: datetime.datetime.now(timezone.utc)
    )
    created_by_user_id = me.StringField(required=False, max_length=200)

    meta = {
        "collection": "evaluation_plans",
        "indexes": [
            {"fields": ["workflow"]},
            {"fields": ["uuid"], "unique": True},
        ],
    }


class EvaluationRun(me.Document):
    """Execution of an evaluation plan against a specific workflow result."""

    uuid = me.StringField(default=lambda: uuid4().hex, required=True, unique=True)
    plan = me.ReferenceField("EvaluationPlan", reverse_delete_rule=CASCADE, required=True)
    workflow_result = me.ReferenceField(
        "WorkflowResult", reverse_delete_rule=CASCADE, required=True
    )

    status = me.StringField(
        default="pending",
        choices=["pending", "running", "completed", "failed"],
        max_length=20,
    )

    # Each result dict: check_id, status, confidence, evidence, reasoning, fix_suggestion
    check_results = me.ListField(me.DictField(), default=[])

    overall_score = me.FloatField(default=0.0)
    grade = me.StringField(default="", max_length=2)
    num_passed = me.IntField(default=0)
    num_failed = me.IntField(default=0)
    num_warned = me.IntField(default=0)
    num_skipped = me.IntField(default=0)

    model_used = me.StringField(required=False, max_length=200)
    started_at = me.DateTimeField(required=False)
    finished_at = me.DateTimeField(required=False)
    error = me.StringField(required=False, max_length=2000)

    created_at = me.DateTimeField(
        default=lambda: datetime.datetime.now(timezone.utc)
    )
    created_by_user_id = me.StringField(required=False, max_length=200)

    meta = {
        "collection": "evaluation_runs",
        "indexes": [
            {"fields": ["workflow_result"]},
            {"fields": ["plan"]},
            {"fields": ["uuid"], "unique": True},
        ],
    }


# Teams
class Team(me.Document):
    """A collaborative group of users."""

    uuid = me.StringField(required=True, max_length=200, unique=True)
    name = me.StringField(required=True, max_length=200)
    owner_user_id = me.StringField(required=True, max_length=200)
    created_at = me.DateTimeField(default=datetime.datetime.now)

    def ensure_shared_folder(self, *, space_id: str | None = None) -> "SmartFolder":
        """
        Ensure the team has a root shared SmartFolder.
        Returns the existing folder if present, otherwise creates/adopts one.
        """
        folder = SmartFolder.objects(
            team_id=self.uuid, is_shared_team_root=True
        ).first()
        if folder:
            if space_id and folder.space != space_id:
                folder.space = space_id
                folder.save()
            return folder

        existing = (
            SmartFolder.objects(team_id=self.uuid, parent_id="0").order_by("id").first()
        )
        if existing:
            existing.is_shared_team_root = True
            if space_id and existing.space != space_id:
                existing.space = space_id
            if existing.parent_id != "0":
                existing.parent_id = "0"
            existing.save()
            return existing

        resolved_space = space_id or self.uuid
        folder = SmartFolder(
            parent_id="0",
            title=f"{self.name} Shared",
            uuid=uuid4().hex,
            space=resolved_space,
            team_id=self.uuid,
            is_shared_team_root=True,
        )
        folder.save()
        return folder


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
    sent_at = me.DateTimeField(default=datetime.datetime.now)
    resend_count = me.IntField(default=0)

    meta = {
        "indexes": [
            {"fields": ["team", "email"], "unique": True},
            {"fields": ["token"], "unique": True},
        ]
    }


class User(me.Document):
    """User model. Represents a user in the system."""

    user_id = me.StringField(required=True, max_length=200)
    email = me.StringField(max_length=320)  # User's email address
    is_admin = me.BooleanField(default=False)
    is_examiner = me.BooleanField(default=False)
    name = me.StringField()

    current_team = me.ReferenceField(
        "Team", required=False, reverse_delete_rule=me.NULLIFY
    )

    # M365 integration opt-in
    m365_enabled = me.BooleanField(default=False)
    m365_connected_at = me.DateTimeField(required=False)

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

    password_hash = me.StringField()

    def set_password(self, password):
        """Create a hashed password."""
        if password is None or not isinstance(password, str):
            raise ValueError("Password must be a non-empty string")
        if len(password) == 0:
            raise ValueError("Password cannot be empty")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check a hashed password."""
        if password is None or not isinstance(password, str):
            return False
        return check_password_hash(self.password_hash, password)

    def _membership_for(self, team: "Team | None" = None) -> "TeamMembership | None":
        """
        Return the TeamMembership doc for this user in the given team (or current team).
        """
        if team is None:
            team = self.ensure_current_team()
        if not team:
            return None
        return TeamMembership.objects(team=team, user_id=self.user_id).first()

    def role_in_team(self, team: "Team | None" = None) -> str | None:
        """
        Returns 'owner' | 'admin' | 'member' or None if not a member.
        """
        m = self._membership_for(team)
        return m.role if m else None

    def has_min_role(self, min_role: str, team: "Team | None" = None) -> bool:
        """
        True if the user's role rank in team <= rank(min_role).
        """
        role = self.role_in_team(team)
        if role is None:
            return False
        return _role_rank(role) <= _role_rank(min_role)

    # Convenience shorthands for the CURRENT team
    @property
    def is_owner_current_team(self) -> bool:
        return self.has_min_role("owner")

    @property
    def is_admin_current_team(self) -> bool:
        """
        Admin-or-owner for the current team.
        Prefer this over the legacy global boolean.
        """
        return self.has_min_role("admin")

    @property
    def is_member_current_team(self) -> bool:
        return self.has_min_role("member")

    # You might need to add this if you use Flask-Login
    @property
    def is_active(self):
        return True

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return self.user_id


def _role_rank(role: str) -> int:
    # lower is higher priority
    return {"owner": 0, "admin": 1, "member": 2}.get(role, 3)


def _ensure_personal_team_for_user(user_id: str, user_name: str | None = None) -> Team:
    """
    Ensure the user has a personal team:
    - Create Team(name="My Team") owned by the user if none exists
    - Create TeamMembership(owner) if missing
    Returns the Team.
    """
    # Try to find an existing "personal" team owned by this user.
    team = Team.objects(owner_user_id=user_id).first()
    if not team:
        team = Team(
            uuid=str(uuid4()),
            name="My Team",
            owner_user_id=user_id,
            created_at=datetime.datetime.now(),
        ).save()

    # Ensure membership as owner
    if not TeamMembership.objects(team=team, user_id=user_id).first():
        TeamMembership(team=team, user_id=user_id, role="owner").save()

    return team


def _pick_default_team_for_user(user_id: str) -> "Team | None":
    memberships = list(TeamMembership.objects(user_id=user_id))
    if not memberships:
        # Auto-create a personal team and return it
        return _ensure_personal_team_for_user(user_id)

    memberships.sort(key=lambda m: (_role_rank(m.role), m.created_at))
    return memberships[0].team


def _user_pre_save(sender, document: "User", **kwargs):
    # Only fill if empty; don't override an explicit selection
    if getattr(document, "current_team", None) is None:
        # Check if there are pending team invites for this user
        # If so, skip auto-creating a personal team; let the invite processing set the team
        from app.models import TeamInvite

        pending_invites = TeamInvite.objects(
            email=document.user_id.lower(), accepted=False
        ).first()
        if not pending_invites:
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
    user_id = me.StringField(max_length=200)
    team_id = me.StringField(max_length=200)
    is_shared_team_root = me.BooleanField(default=False)

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
    ASSISTANT = "assistant"  # Added assistant role


MAX_CHAT_MESSAGES = 20


class FileAttachment(me.Document):
    """Represents a file attachment in a chat."""

    filename = me.StringField(required=True, max_length=200)
    file_type = me.StringField(max_length=50)  # Store file extension
    content = me.StringField(required=True, max_length=500000)
    created_at = me.DateTimeField(default=datetime.datetime.now)
    user_id = me.StringField(required=True, max_length=200)

    def to_dict(self):
        return {
            "id": str(self.id),
            "filename": self.filename,
            "file_type": self.file_type,
            "content": self.content,
            "created_at": self.created_at,
            "user_id": self.user_id,
        }


class UrlAttachment(me.Document):
    """Represents a URL attachment in a chat."""

    url = me.StringField(required=True, max_length=500)
    title = me.StringField(required=False, max_length=200)
    content = me.StringField(required=False, max_length=500000)
    created_at = me.DateTimeField(default=datetime.datetime.now)
    user_id = me.StringField(required=True, max_length=200)

    def to_dict(self):
        return {
            "id": str(self.id),
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at,
            "user_id": self.user_id,
        }


class ChatMessage(me.Document):
    """Represents a message in a chat."""

    role = me.EnumField(ChatRole, required=True)
    message = me.StringField(required=True, max_length=500000)
    created_at = me.DateTimeField(default=datetime.datetime.now)

    def to_dict(self):
        """Convert to dictionary format"""
        return {"role": self.role.value, "content": self.message}

    def to_model_message(self) -> ModelMessage:
        """Convert to ModelMessage format for pydantic-ai"""
        if self.role == ChatRole.USER:
            # User messages become ModelRequest with UserPromptPart
            return ModelRequest(parts=[UserPromptPart(content=self.message)])
        elif self.role == ChatRole.ASSISTANT:
            # Assistant messages become ModelResponse with TextPart
            return ModelResponse(parts=[TextPart(content=self.message)])
        elif self.role == ChatRole.SYSTEM:
            # System messages become ModelRequest with SystemPromptPart
            return ModelRequest(parts=[SystemPromptPart(content=self.message)])
        else:
            # Fallback to user message if role is unknown
            return ModelRequest(parts=[UserPromptPart(content=self.message)])


class ChatConversation(me.Document):
    """Represents a chat history for a user."""

    uuid = me.StringField(required=True, max_length=200, unique=True)
    title = me.StringField(required=True, max_length=50000)
    user_id = me.StringField(required=True, max_length=200)
    messages = me.ListField(me.ReferenceField(ChatMessage, reverse_delete_rule=CASCADE))
    # attachments can be files or urls
    file_attachments = me.ListField(
        me.ReferenceField(FileAttachment, reverse_delete_rule=CASCADE)
    )
    url_attachments = me.ListField(
        me.ReferenceField(UrlAttachment, reverse_delete_rule=CASCADE)
    )
    created_at = me.DateTimeField(default=datetime.datetime.now)
    updated_at = me.DateTimeField(default=datetime.datetime.now)

    def add_message(self, role, content):
        """Add a message to the conversation and save it"""
        message = ChatMessage(role=role, message=content)
        message.save()
        self.messages.append(message)
        self.updated_at = datetime.datetime.now()

        # # Keep only the last MAX_CHAT_MESSAGES
        # if len(self.messages) > MAX_CHAT_MESSAGES:
        #     # Delete old messages from database
        #     old_messages = self.messages[:-MAX_CHAT_MESSAGES]
        #     for msg in old_messages:
        #         msg.delete()
        #     self.messages = self.messages[-MAX_CHAT_MESSAGES:]

        self.save()
        debug(f"Added message to conversation {self.id}: {role} - {content[:30]}...")
        return message

    def get_messages(self):
        """Get messages in format expected by pydantic_ai agent"""
        return [msg.to_dict() for msg in self.messages]

    def to_model_messages(self) -> list[ModelMessage]:
        """Get messages in ModelMessage format"""
        return [msg.to_model_message() for msg in self.messages]

    def generate_title(self):
        """Generate a title from the first user message"""
        if self.messages and self.title == "New Conversation":
            first_user_msg = next(
                (msg for msg in self.messages if msg.role == ChatRole.USER), None
            )
            if first_user_msg:
                # Take first 50 characters of the message as title
                self.title = first_user_msg.message[:50] + (
                    "..." if len(first_user_msg.message) > 50 else ""
                )
                self.save()

    def to_dict(self):
        return {
            "_id": str(self.id),
            "uuid": self.uuid,
            "title": self.title,
            "user_id": self.user_id,
            "messages": [
                {
                    "role": msg.role.value,
                    "message": msg.message,
                    "created_at": msg.created_at,
                    # add other message fields as needed
                }
                for msg in self.messages  # This will dereference
            ],
            "file_attachments": [u.to_dict() for u in self.file_attachments],
            "url_attachments": [u.to_dict() for u in self.url_attachments],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


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


class LibraryFolder(me.Document):
    """
    Represents a folder within the library (personal or team).
    """

    uuid = me.StringField(default=lambda: uuid4().hex, required=True, unique=True)
    name = me.StringField(required=True, max_length=200)
    parent_id = me.StringField(
        default=None, required=False, max_length=200
    )  # uuid of parent folder or None for root

    scope = me.EnumField(LibraryScope, required=True)

    # Ownership (matches Library)
    owner_user_id = me.StringField(required=False, max_length=200)
    team = me.ReferenceField(Team, required=False, reverse_delete_rule=me.CASCADE)

    created_at = me.DateTimeField(
        default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at = me.DateTimeField(
        default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    meta = {
        "indexes": [
            {"fields": ["scope", "owner_user_id", "parent_id", "name"]},
            {"fields": ["scope", "team", "parent_id", "name"]},
        ]
    }


class LibraryItem(me.Document):
    """
    A pointer to either a Workflow or a SearchSet, with provenance and optional verification stamp.
    """

    # Polymorphic reference to Workflow or SearchSet
    obj = me.GenericReferenceField(required=True)  # Workflow OR SearchSet

    # For quick filtering without dereferencing
    kind = me.StringField(
        required=True, choices=["workflow", "searchset", "prompt", "formatter"]
    )

    added_by_user_id = me.StringField(required=True, max_length=200)
    added_at = me.DateTimeField(default=datetime.datetime.now)

    # Whether the referenced object is currently marked verified (mirrors source)
    verified = me.BooleanField(default=False)
    verified_at = me.DateTimeField(required=False)
    verified_by_user_id = me.StringField(required=False, max_length=200)

    # Optional tags/notes to help curate libraries
    tags = me.ListField(me.StringField(max_length=100), default=[])
    note = me.StringField(required=False, max_length=10000)

    # Folder organization
    folder = me.ReferenceField(
        "LibraryFolder", required=False, reverse_delete_rule=me.NULLIFY
    )

    meta = {
        "indexes": [
            # Prevent duplicate entries for the same object inside the same library
            {"fields": ["obj", "kind"]},
        ]
    }


# Library
class Library(me.Document):
    scope = me.EnumField(
        LibraryScope, required=True
    )  # 'personal' | 'team' | 'verified'
    title = me.StringField(required=True, max_length=200)
    description = me.StringField(required=False, max_length=2000)

    owner_user_id = me.StringField(required=False, max_length=200)  # PERSONAL
    team = me.ReferenceField(
        Team, required=False, reverse_delete_rule=me.CASCADE
    )  # TEAM

    # Make these timezone-aware in UTC
    created_at = me.DateTimeField(
        default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at = me.DateTimeField(
        default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    items = me.ListField(me.ReferenceField("LibraryItem", reverse_delete_rule=me.PULL))

    meta = {
        "indexes": [
            # PERSONAL: one per user
            {
                "fields": ["scope", "owner_user_id"],
                "unique": True,
                "partialFilterExpression": {
                    "scope": "personal",
                    "owner_user_id": {"$exists": True},
                    # optionally: {"$type": "string"}
                },
            },
            # TEAM: one per team
            {
                "fields": ["scope", "team"],
                "unique": True,
                "partialFilterExpression": {
                    "scope": "team",
                    "team": {"$exists": True},
                    # if you know it's an ObjectId, you can use:
                    # "team": {"$type": "objectId"}
                },
            },
            # VERIFIED: single global
            {
                "fields": ["scope"],
                "unique": True,
                "partialFilterExpression": {"scope": "verified"},
            },
        ]
    }

    def clean(self):
        # Optional: enforce mutual exclusivity at the app layer
        if self.scope == "personal":
            self.team = None
            if not self.owner_user_id:
                raise me.ValidationError("owner_user_id required for personal scope")
        elif self.scope == "team":
            self.owner_user_id = None
            if not self.team:
                raise me.ValidationError("team required for team scope")
        elif self.scope == "verified":
            self.owner_user_id = None
            self.team = None


class VerificationStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class VerificationRequest(me.Document):
    """
    Metadata captured when a workflow/task is submitted for verification.
    """

    uuid = me.StringField(default=lambda: uuid4().hex, required=True, unique=True)
    item_kind = me.StringField(
        required=True, choices=["workflow", "searchset", "prompt", "formatter"]
    )
    item_identifier = me.StringField(required=True, max_length=200)
    library_item = me.ReferenceField("LibraryItem", required=False)
    team = me.ReferenceField(Team, required=False, reverse_delete_rule=me.NULLIFY)

    status = me.EnumField(VerificationStatus, default=VerificationStatus.SUBMITTED)

    submitter_user_id = me.StringField(required=True, max_length=200)
    submitter_name = me.StringField(required=False, max_length=200)
    submitter_org = me.StringField(required=False, max_length=200)
    submitter_role = me.StringField(required=False, max_length=200)

    item_title = me.StringField(required=True, max_length=300)
    item_version_hash = me.StringField(required=False, max_length=200)
    category = me.StringField(required=False, max_length=100)
    summary = me.StringField(required=False, max_length=500)
    description = me.StringField(required=False, max_length=5000)
    example_inputs = me.ListField(me.StringField(max_length=500), default=[])
    test_files = me.ListField(me.DictField(), default=[])
    expected_outputs = me.ListField(me.StringField(max_length=500), default=[])
    dependencies = me.ListField(me.StringField(max_length=300), default=[])
    run_instructions = me.StringField(required=False, max_length=5000)
    known_limitations = me.StringField(required=False, max_length=2000)
    intended_use_tags = me.ListField(me.StringField(max_length=100), default=[])
    evaluation_notes = me.StringField(required=False, max_length=5000)

    created_at = me.DateTimeField(
        default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at = me.DateTimeField(
        default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    submitted_at = me.DateTimeField(required=False)

    meta = {
        "indexes": [
            {"fields": ["item_kind", "item_identifier"], "unique": True},
            {"fields": ["status"]},
            {"fields": ["team", "status"]},
        ],
        "ordering": ["-updated_at"],
    }

    def save(self, *args, **kwargs):
        if not self.uuid:
            self.uuid = uuid4().hex
        now = datetime.datetime.now(datetime.timezone.utc)
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        if (
            self.status in (VerificationStatus.SUBMITTED, VerificationStatus.IN_REVIEW)
            and not self.submitted_at
        ):
            self.submitted_at = now
        return super().save(*args, **kwargs)

    def to_public_dict(self) -> dict:
        status_value = (
            self.status.value
            if isinstance(self.status, VerificationStatus)
            else self.status
        )
        return {
            "id": str(self.id),
            "uuid": self.uuid,
            "item_kind": self.item_kind,
            "item_identifier": self.item_identifier,
            "team_id": str(self.team.id) if self.team else None,
            "team_name": self.team.name if self.team else "",
            "status": status_value,
            "submitter_user_id": self.submitter_user_id,
            "submitter_name": self.submitter_name or "",
            "submitter_org": self.submitter_org or "",
            "submitter_role": self.submitter_role or "",
            "item_title": self.item_title,
            "item_version_hash": self.item_version_hash or "",
            "category": self.category or "",
            "summary": self.summary or "",
            "description": self.description or "",
            "example_inputs": self.example_inputs or [],
            "test_files": self.test_files or [],
            "expected_outputs": self.expected_outputs or [],
            "dependencies": self.dependencies or [],
            "run_instructions": self.run_instructions or "",
            "known_limitations": self.known_limitations or "",
            "intended_use_tags": self.intended_use_tags or [],
            "evaluation_notes": self.evaluation_notes or "",
            "submitted_at": self.submitted_at.isoformat()
            if self.submitted_at
            else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class VerifiedItemMetadata(me.Document):
    """Curated metadata for verified library items."""

    item_kind = me.StringField(
        required=True, choices=["workflow", "searchset", "prompt", "formatter"]
    )
    item_identifier = me.StringField(required=True, max_length=200)
    display_name = me.StringField(required=False, max_length=300)
    description = me.StringField(required=False, max_length=5000)
    markdown = me.StringField(required=False, max_length=20000)
    updated_at = me.DateTimeField(
        default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_by_user_id = me.StringField(required=False, max_length=200)

    meta = {
        "indexes": [
            {"fields": ["item_kind", "item_identifier"], "unique": True},
        ]
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.datetime.now(datetime.timezone.utc)
        return super().save(*args, **kwargs)


class VerifiedCollection(me.Document):
    """Curated collection of verified items."""

    title = me.StringField(required=True, max_length=200)
    description = me.StringField(required=False, max_length=2000)
    promo_image_url = me.StringField(required=False, max_length=500)
    items = me.ListField(
        me.ReferenceField("LibraryItem", reverse_delete_rule=me.PULL), default=[]
    )
    created_by_user_id = me.StringField(required=False, max_length=200)
    created_at = me.DateTimeField(
        default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at = me.DateTimeField(
        default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    meta = {"ordering": ["-updated_at"]}

    def save(self, *args, **kwargs):
        now = datetime.datetime.now(datetime.timezone.utc)
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        return super().save(*args, **kwargs)


# ---- Edit History ----


class EditHistoryEntry(me.Document):
    """Immutable-ish history entry for edits to prompts/search sets/workflows."""

    obj_kind = me.StringField(
        required=True, choices=["workflow", "searchset", "prompt", "formatter"]
    )
    obj_id = me.StringField(required=True, max_length=200)
    action = me.StringField(required=True, max_length=50)

    user_id = me.StringField(required=False, max_length=200)
    user_name = me.StringField(required=False, max_length=200)

    created_at = me.DateTimeField(
        default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    changes = me.DictField()

    meta = {
        "indexes": [
            {"fields": ["obj_kind", "obj_id", "-created_at"]},
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
    title = me.StringField(default="Activity", max_length=50000)
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
    last_updated_at = me.DateTimeField(default=dt.datetime.utcnow)

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
    total_tokens = me.IntField(default=0)  # LLM tokens in+out
    documents_touched = me.IntField(default=0)  # # of docs referenced
    steps_total = me.IntField(default=0)  # workflow
    steps_completed = me.IntField(default=0)  # workflow
    error = me.StringField(required=False, max_length=2000)

    # Free-form details to inspect/debug without dereferencing
    meta_summary = me.DictField(
        default={}
    )  # e.g., {"model":"gpt-4o", "search_set_title":"Acme NDA"}
    result_snapshot = me.DictField(default=dict)
    tags = me.ListField(me.StringField(max_length=50), default=[])

    meta = {
        "indexes": [
            {"fields": ["-started_at"]},
            {"fields": ["-last_updated_at"]},
            {"fields": ["user_id", "-last_updated_at"]},
            {"fields": ["team_id", "-last_updated_at"]},
            {"fields": ["type", "-last_updated_at"]},
            {"fields": ["status", "-last_updated_at"]},
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
        s = _as_aware_utc(self.started_at)
        f = _as_aware_utc(self.finished_at)
        if s is None or f is None:
            return None
        return int((f - s).total_seconds() * 1000)

    @property
    def safe_workflow_name(self) -> str:
        """
        Safely retrieve workflow name without throwing DoesNotExist error.
        Returns workflow name from meta_summary, or from workflow reference if available,
        or a fallback string if workflow was deleted.
        """
        # Try meta_summary first (preferred, no dereferencing)
        if self.meta_summary and self.meta_summary.get("workflow_name"):
            return self.meta_summary["workflow_name"]

        # Try to dereference workflow, handle DoesNotExist
        try:
            if self.workflow:
                return self.workflow.name
        except me.DoesNotExist:
            pass

        return "(workflow)"


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
            {
                "fields": ["date", "scope", "user_id"],
                "unique": True,
                "partialFilterExpression": {"scope": "user"},
            },
            {
                "fields": ["date", "scope", "team_id"],
                "unique": True,
                "partialFilterExpression": {"scope": "team"},
            },
            {
                "fields": ["date", "scope"],
                "unique": True,
                "partialFilterExpression": {"scope": "global"},
            },
            {"fields": ["-date", "scope"]},
        ]
    }


# ---------------------------------------------------------------------------
# M365 Passive Workflow Models
# ---------------------------------------------------------------------------


class WorkItem(me.Document):
    """Normalized intake item from any M365 source (email, OneDrive file, etc.)."""

    uuid = me.StringField(required=True, unique=True, max_length=200)
    source = me.StringField(
        required=True,
        choices=["outlook_shared", "outlook_folder", "onedrive_drop", "manual"],
    )
    status = me.StringField(
        required=True,
        default="received",
        choices=[
            "received",
            "triaged",
            "processing",
            "awaiting_review",
            "completed",
            "failed",
            "rejected",
        ],
    )

    # Source identifiers (Graph API IDs)
    graph_message_id = me.StringField(max_length=500)
    graph_drive_item_id = me.StringField(max_length=500)
    source_mailbox = me.StringField(max_length=320)
    source_folder_path = me.StringField(max_length=500)

    # Extracted metadata
    subject = me.StringField(max_length=1000)
    sender_email = me.StringField(max_length=320)
    sender_name = me.StringField(max_length=200)
    received_at = me.DateTimeField()
    body_text = me.StringField()
    body_html = me.StringField()

    # Attachments (stored as SmartDocuments after download)
    attachments = me.ListField(me.ReferenceField("SmartDocument"))
    attachment_count = me.IntField(default=0)

    # Triage results (populated by triage agent)
    triage_category = me.StringField(max_length=200)
    triage_confidence = me.FloatField()
    triage_tags = me.ListField(me.StringField(max_length=100))
    sensitivity_flags = me.ListField(me.StringField(max_length=100))
    triage_summary = me.StringField(max_length=5000)

    # Workflow binding
    intake_config = me.ReferenceField("IntakeConfig", required=False)
    matched_workflow = me.ReferenceField("Workflow", required=False)
    trigger_event = me.ReferenceField("WorkflowTriggerEvent", required=False)
    workflow_result = me.ReferenceField("WorkflowResult", required=False)

    # OneDrive case folder (populated after output)
    case_folder_url = me.StringField(max_length=1000)
    case_folder_drive_path = me.StringField(max_length=500)

    # Feedback (from Teams cards or UI)
    feedback_action = me.StringField(
        max_length=50, choices=["correct", "fix", "stop", "reassign", None]
    )
    feedback_by = me.StringField(max_length=200)
    feedback_at = me.DateTimeField()
    feedback_note = me.StringField(max_length=2000)

    # Ownership / audit
    owner_user_id = me.StringField(required=True, max_length=200)
    team_id = me.StringField(max_length=200)
    created_at = me.DateTimeField(default=datetime.datetime.utcnow)
    updated_at = me.DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "work_items",
        "indexes": [
            "uuid",
            "source",
            "status",
            "owner_user_id",
            "team_id",
            "graph_message_id",
            "-created_at",
            {"fields": ["source_mailbox", "status"]},
        ],
    }


class GraphSubscription(me.Document):
    """Tracks an active Microsoft Graph webhook subscription."""

    subscription_id = me.StringField(required=True, unique=True, max_length=200)
    resource = me.StringField(required=True, max_length=500)
    change_type = me.StringField(required=True, max_length=50)
    notification_url = me.StringField(required=True, max_length=500)
    expiration = me.DateTimeField(required=True)
    owner_user_id = me.StringField(required=True, max_length=200)
    intake_config_id = me.StringField(max_length=200)
    active = me.BooleanField(default=True)
    created_at = me.DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "graph_subscriptions",
        "indexes": ["subscription_id", "expiration", "active"],
    }


class IntakeConfig(me.Document):
    """Configuration for an M365 intake lane (shared mailbox, folder, OneDrive drop)."""

    uuid = me.StringField(required=True, unique=True, max_length=200)
    name = me.StringField(required=True, max_length=200)
    intake_type = me.StringField(
        required=True,
        choices=["outlook_shared", "outlook_folder", "onedrive_drop"],
    )
    enabled = me.BooleanField(default=False)

    # Source configuration (populate the ones relevant to intake_type)
    mailbox_address = me.StringField(max_length=320)
    outlook_folder_id = me.StringField(max_length=500)
    drive_id = me.StringField(max_length=200)
    folder_path = me.StringField(max_length=500)

    # Routing — which workflow(s) to route to
    default_workflow = me.ReferenceField("Workflow", required=False)
    triage_enabled = me.BooleanField(default=True)
    triage_rules = me.ListField(me.DictField(), default=[])

    # File filters (reuse concept from passive_triggers)
    file_filters = me.DictField(
        default=lambda: {
            "types": ["pdf", "docx", "xlsx"],
            "exclude_patterns": [],
            "max_size_bytes": 50_000_000,
        }
    )

    # Teams notification configuration
    teams_config = me.DictField(
        default=lambda: {
            "enabled": False,
            "team_id": None,
            "channel_id": None,
            "notify_on_complete": True,
            "notify_on_error": True,
            "daily_digest": True,
        }
    )

    # Graph subscription reference
    subscription = me.ReferenceField("GraphSubscription", required=False)

    # Ownership
    owner_user_id = me.StringField(required=True, max_length=200)
    team_id = me.StringField(max_length=200)

    created_at = me.DateTimeField(default=datetime.datetime.utcnow)
    updated_at = me.DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "intake_configs",
        "indexes": ["uuid", "intake_type", "owner_user_id", "enabled"],
    }


class M365AuditEntry(me.Document):
    """Immutable audit log for M365 integration actions."""

    uuid = me.StringField(required=True, unique=True, max_length=200)
    action = me.StringField(required=True, max_length=50)
    actor_user_id = me.StringField(max_length=200)
    actor_type = me.StringField(
        max_length=20, choices=["user", "system", "graph_webhook"]
    )

    work_item_id = me.StringField(max_length=200)
    intake_config_id = me.StringField(max_length=200)
    workflow_id = me.StringField(max_length=200)

    detail = me.DictField()
    created_at = me.DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "m365_audit_log",
        "indexes": ["-created_at", "action", "work_item_id", "actor_user_id"],
    }
