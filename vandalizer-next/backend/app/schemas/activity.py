"""Activity schemas for request/response validation."""

from typing import Optional

from pydantic import BaseModel


class ActivityEventResponse(BaseModel):
    id: str
    type: str
    status: str
    title: Optional[str] = None
    conversation_id: Optional[str] = None
    search_set_uuid: Optional[str] = None
    workflow_id: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    message_count: int = 0
    result_snapshot: dict = {}
