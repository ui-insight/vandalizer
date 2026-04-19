"""UserMemory — per-(user, team) behavioral patterns for personalizing chat.

Tracks what extraction templates, workflows, and knowledge bases a user
actually exercises, so the agentic chat can surface "you usually use X"
guidance without asking the LLM to infer it from conversation text.
"""

import datetime
from typing import Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class UserMemory(Document):
    user_id: str
    # team_id is nullable: a user has one memory doc per team they operate in,
    # plus one for personal (team_id=None) work.
    team_id: Optional[str] = None

    # Each map: item uuid/id -> {"title": str, "count": int, "last_used": iso datetime}
    extraction_runs: dict[str, dict] = Field(default_factory=dict)
    workflow_runs: dict[str, dict] = Field(default_factory=dict)
    kb_queries: dict[str, dict] = Field(default_factory=dict)

    updated_at: datetime.datetime = Field(default_factory=_utcnow)

    class Settings:
        name = "user_memories"
        indexes = [
            IndexModel(
                [("user_id", ASCENDING), ("team_id", ASCENDING)],
                unique=True,
                name="user_team_unique",
            ),
        ]
