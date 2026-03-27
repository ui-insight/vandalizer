"""Passive automation models — WorkflowTriggerEvent, ExtractionTriggerEvent, GraphSubscription, M365AuditEntry."""

import datetime
from typing import Optional
from uuid import uuid4

from beanie import Document, PydanticObjectId
from pydantic import Field


class WorkflowTriggerEvent(Document):
    """A pending/running/completed passive workflow trigger."""

    uuid: str = Field(default_factory=lambda: uuid4().hex)
    workflow: Optional[PydanticObjectId] = None
    trigger_type: str = "manual"  # manual, folder_watch, schedule, api, chain, m365_intake
    status: str = "pending"  # pending, queued, running, completed, failed, skipped

    documents: list[PydanticObjectId] = Field(default_factory=list)
    document_count: int = 0
    work_item: Optional[PydanticObjectId] = None

    trigger_context: dict = Field(default_factory=dict)

    # Timing
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    process_after: Optional[datetime.datetime] = None
    queued_at: Optional[datetime.datetime] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None
    duration_ms: Optional[int] = None

    # Results
    workflow_result: Optional[PydanticObjectId] = None
    documents_succeeded: int = 0
    documents_failed: int = 0
    tokens_used: int = 0
    error: Optional[str] = None

    # Retry tracking
    attempt_number: int = 1
    max_attempts: int = 3
    next_retry_at: Optional[datetime.datetime] = None

    # Output delivery status
    output_delivery: dict = Field(default_factory=lambda: {
        "storage_status": None,
        "notifications_sent": [],
        "webhooks_called": [],
        "chains_triggered": [],
    })

    class Settings:
        name = "workflow_trigger_event"


class ExtractionTriggerEvent(Document):
    """Tracks API-triggered extraction runs (analogous to WorkflowTriggerEvent)."""

    uuid: str = Field(default_factory=lambda: uuid4().hex)
    automation_id: str = ""
    search_set_uuid: str = ""
    user_id: str = ""
    status: str = "pending"  # pending, queued, running, completed, failed

    document_uuids: list[str] = Field(default_factory=list)

    # Results
    result: Optional[dict] = None  # {doc_uuid: {key: value, ...}, ...}
    error: Optional[str] = None

    # Timing
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None
    duration_ms: Optional[int] = None

    # Callback / delivery
    trigger_context: dict = Field(default_factory=dict)
    output_delivery: dict = Field(default_factory=lambda: {
        "storage_status": None,
        "webhooks_called": [],
        "callback_status": None,
    })

    class Settings:
        name = "extraction_trigger_event"


class GraphSubscription(Document):
    """Microsoft Graph change notification subscription."""

    subscription_id: str  # Graph-assigned subscription ID
    resource: str  # e.g. "/users/{id}/mailFolders('Inbox')/messages"
    change_type: str = "created"
    notification_url: str = ""
    expiration: Optional[datetime.datetime] = None
    client_state: Optional[str] = None

    owner_user_id: str = ""
    intake_config_id: Optional[PydanticObjectId] = None
    team_id: Optional[str] = None
    active: bool = True

    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    class Settings:
        name = "graph_subscription"


class M365AuditEntry(Document):
    """Immutable audit trail entry for M365 operations."""

    uuid: str = Field(default_factory=lambda: uuid4().hex)
    action: str  # ingest, triage, approve, reject, etc.
    actor_user_id: Optional[str] = None
    actor_type: str = "system"  # user, system, graph_webhook

    work_item_id: Optional[str] = None
    intake_config_id: Optional[str] = None
    workflow_id: Optional[str] = None

    detail: dict = Field(default_factory=dict)
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    class Settings:
        name = "m365_audit_entry"
