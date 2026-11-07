"""Durable ownership and idempotency receipt for an asynchronous KB check."""
import datetime
from typing import Literal
from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class KBValidationTask(Document):
    uuid: str
    kb_uuid: str
    user_id: str
    options: dict
    dispatch_uncertain: bool = False
    active: bool = True
    terminal_status: Literal["completed", "failed"] | None = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

    class Settings:
        name = "kb_validation_tasks"
        indexes = [
            IndexModel("uuid", unique=True),
            IndexModel([("kb_uuid", 1), ("user_id", 1), ("created_at", -1)]),
            IndexModel([("kb_uuid", 1), ("user_id", 1)], unique=True,
                       partialFilterExpression={"active": True}, name="one_active_check_per_user_kb"),
        ]
