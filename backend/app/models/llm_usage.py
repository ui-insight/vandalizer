"""LLM usage ledger  - append-only record of token consumption per LLM call.

Every LLM call in the app is metered at a single chokepoint (the MeteredModel
wrapper in llm_service.py) and recorded here, attributed to a feature and, when
available, a user/team/activity. This is the canonical source of truth for token
usage; ActivityEvent token fields are a denormalized convenience updated
alongside this ledger when a call belongs to an activity.
"""

import datetime
from typing import Optional

from beanie import Document
from pydantic import Field


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# Sentinel feature used when an LLM call fires with no metering scope set. These
# rows flag call sites that still need attribution wiring; they should be rare.
UNATTRIBUTED_FEATURE = "unattributed"


class LlmUsageRecord(Document):
    timestamp: datetime.datetime = Field(default_factory=_utcnow)

    # Which product surface made the call: "chat", "extraction", "workflow",
    # "classification", "validation", "title_gen", etc. (see metering.py).
    feature: str

    user_id: Optional[str] = None
    team_id: Optional[str] = None
    space: Optional[str] = None

    # Links back to an ActivityEvent (its str id) when the call is part of one.
    activity_id: Optional[str] = None

    model: Optional[str] = None

    tokens_input: int = 0
    tokens_output: int = 0
    total_tokens: int = 0

    # Number of underlying model HTTP requests aggregated into this row (a single
    # logical operation may make several: retries, tool sub-calls, multi-step).
    request_count: int = 1

    # True when token counts were estimated locally because the provider/gateway
    # returned no usage. Lets reporting separate exact from estimated totals.
    estimated: bool = False

    status: str = "ok"

    class Settings:
        name = "llm_usage"
        indexes = [
            "user_id",
            "team_id",
            "feature",
            "timestamp",
            [("user_id", 1), ("timestamp", -1)],
        ]
