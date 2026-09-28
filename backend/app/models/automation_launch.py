"""One durable receipt per manual launch intent; retries never dispatch twice."""
import datetime

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class AutomationLaunch(Document):
    request_id: str
    automation_id: str
    user_id: str
    document_uuids: list[str]
    response: dict | None = None
    selection: dict
    action_type: str
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

    class Settings:
        name = "automation_launches"
        indexes = [IndexModel([("automation_id", 1), ("user_id", 1), ("request_id", 1)], unique=True)]
