"""What a proposal or award needs from the RA, taken from its documents (#999).

An obligation is a deadline, a required piece of material, or a sponsor limit
found in a project's solicitation, amendment, draft or award, always with the
document, page and quote it came from. They feed the RA inbox on Home. The one
exception is a deadline someone on the project adds by hand
(``entered_by_hand``): it has no checked source, and the inbox says so.

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


class DeadlineCalculation(BaseModel):
    """Server-calculated calendar date, retained with its quoted evidence."""

    rule: str
    anchor_kind: str
    anchor_date: str
    offset_days: int
    formula: str


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
    deadline_calculation: Optional[DeadlineCalculation] = None
    limit_value: Optional[float] = None
    observed_value: Optional[float] = None
    unit: Optional[str] = None
    sources: list[ObligationSource] = []
    status: str = "open"
    superseded_by: Optional[str] = None
    supersedes: Optional[str] = None
    dismissed_by: list[str] = []
    # A cited file was deleted and someone who manages the project chose to
    # keep the item anyway. Until then it waits for that decision and sends
    # no reminders (see obligation_service.awaiting_source_decision).
    kept_without_source: bool = False
    # Added in the inbox by someone who manages the project rather than found
    # in a document: never checked against a source, and shown that way.
    # Support ticket: a deadline the document check refused could not be
    # recorded at all.
    entered_by_hand: bool = False
    # Where that person says it comes from ("Subaward §5"), as typed. Not a
    # verified citation.
    source_note: Optional[str] = None
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


class ObligationReminder(Document):
    """One reminder sent to one user for one deadline stage.

    The unique key is what makes the reminder sweep safe to run every hour and
    on several workers: a stage is claimed by inserting this row first, and a
    duplicate insert means someone already sent it. ``due_date`` is part of
    the key, so an obligation whose date changes is reminded again on its new
    schedule. The weekly summary uses the same table with
    ``obligation_uuid="weekly-summary"`` and the ISO week as ``stage``.
    """

    obligation_uuid: str
    user_id: str
    # "before_14", "before_3", ... "due", "overdue"; an ISO week for the summary.
    stage: str
    due_date: str = ""
    channels: list[str] = []
    sent_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

    class Settings:
        name = "obligation_reminder"
        indexes = [
            IndexModel(
                [("obligation_uuid", ASCENDING), ("user_id", ASCENDING), ("stage", ASCENDING), ("due_date", ASCENDING)],
                unique=True,
            ),
        ]
