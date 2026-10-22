"""What a proposal or award needs from the RA, taken from its documents (#999).

An obligation is a deadline, a required piece of material, or a sponsor limit
found in a project's solicitation, amendment, draft or award, always with the
document, page and quote it came from. They feed the RA inbox on Home.

``status`` is a fact about the project, shared by everyone on it: ``open``,
``done``, or ``superseded`` (an amendment replaced it). Hiding an item from
Home is personal and lives in ``dismissed_by``: dismissing never changes what
teammates see.
"""

import datetime
from typing import Optional

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel

OBLIGATION_KINDS = ("deadline", "required_material", "limit")
DEADLINE_TYPES = ("sponsor_submission", "internal_routing", "report_due", "other")
OBLIGATION_STATUSES = ("open", "done", "superseded")


class ObligationSource(BaseModel):
    """Where a claim comes from: one document, one page, the exact passage."""

    document_uuid: str
    document_title: str = ""
    page: Optional[int] = None
    quote: str
    # "limit" items cite the limit and the observed value separately.
    role: str = "evidence"


class Obligation(Document):
    uuid: str
    project_uuid: str
    team_id: Optional[str] = None
    kind: str
    title: str
    deadline_type: Optional[str] = None
    due_at: Optional[datetime.datetime] = None
    # As written in the source ("5:00 p.m. Pacific Time"), kept so the
    # inbox never restates a time zone the document didn't give.
    due_text: Optional[str] = None
    limit_value: Optional[float] = None
    observed_value: Optional[float] = None
    unit: Optional[str] = None
    sources: list[ObligationSource] = []
    status: str = "open"
    superseded_by: Optional[str] = None
    supersedes: Optional[str] = None
    dismissed_by: list[str] = []
    created_by: str
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    completed_by: Optional[str] = None
    completed_at: Optional[datetime.datetime] = None

    class Settings:
        name = "obligation"
        indexes = [
            IndexModel([("uuid", ASCENDING)], unique=True),
            IndexModel([("project_uuid", ASCENDING), ("status", ASCENDING)]),
        ]

    @property
    def in_conflict(self) -> bool:
        """A limit the observed value exceeds."""
        return (
            self.kind == "limit"
            and self.limit_value is not None
            and self.observed_value is not None
            and self.observed_value > self.limit_value
        )
