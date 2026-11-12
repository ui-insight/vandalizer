"""Web search ledger - one row per search sent to the configured provider.

Paid providers bill per query, and every query leaves the deployment for a
third party. LlmUsageRecord counts model tokens, so searches had no record at
all: nobody could say how many were run, by whom, from which surface, or what
was sent. Rows are written by web_search_service, attributed from the active
metering scope (chat, workflow, kb_source_suggestions, ...).
"""

import datetime
from typing import Optional

from beanie import Document
from pydantic import Field


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# Long enough to recognize a search in an audit; a query is not stored whole.
QUERY_RECORD_CHARS = 200


class WebSearchUsage(Document):
    timestamp: datetime.datetime = Field(default_factory=_utcnow)
    feature: str = "unattributed"
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    activity_id: Optional[str] = None
    provider: Optional[str] = None
    query: str = ""
    result_count: int = 0
    # "ok", "error" or "not_configured".
    status: str = "ok"
    error: Optional[str] = None

    class Settings:
        name = "web_search_usage"
        indexes = [
            "user_id",
            "team_id",
            "feature",
            "timestamp",
            [("user_id", 1), ("timestamp", -1)],
        ]
