"""Activity tracking models — ActivityEvent and related enums."""

import datetime
from enum import Enum
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field


class ActivityType(str, Enum):
    CONVERSATION = "conversation"
    SEARCH_SET_RUN = "search_set_run"
    WORKFLOW_RUN = "workflow_run"


class ActivityStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class ActivityEvent(Document):
    type: str
    title: Optional[str] = "Activity"
    status: str = ActivityStatus.RUNNING.value

    user_id: str
    team_id: Optional[str] = None
    space: Optional[str] = None

    started_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    finished_at: Optional[datetime.datetime] = None
    last_updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    conversation_id: Optional[str] = None
    search_set_uuid: Optional[str] = None
    workflow_result: Optional[PydanticObjectId] = None
    workflow: Optional[PydanticObjectId] = None

    message_count: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    total_tokens: int = 0
    documents_touched: int = 0
    steps_total: int = 0
    steps_completed: int = 0
    error: Optional[str] = None
    progress_message: Optional[str] = None
    meta_summary: dict = Field(default_factory=dict)
    result_snapshot: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    class Settings:
        name = "activity_event"

    @property
    def is_running(self) -> bool:
        return self.status in (ActivityStatus.RUNNING.value, ActivityStatus.QUEUED.value)

    @property
    def duration_ms(self) -> Optional[int]:
        if self.started_at and self.finished_at:
            delta = self.finished_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "type": self.type,
            "status": self.status,
            "title": self.title,
            "conversation_id": self.conversation_id,
            "search_set_uuid": self.search_set_uuid,
            "workflow_id": str(self.workflow) if self.workflow else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error or "",
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "message_count": self.message_count,
            "result_snapshot": self.result_snapshot or {},
        }
