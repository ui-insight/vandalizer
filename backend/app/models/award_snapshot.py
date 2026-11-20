"""A project's award snapshot: its key facts and budget, each with its source.

Only the facts read from the project's documents are stored here. Deadlines,
status, the last run and saved pages are read live whenever the snapshot is
shown (``app.services.award_snapshot.view``), so marking a deadline Done
changes the snapshot at once without a rebuild.
"""

import datetime
from typing import Optional

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel

SNAPSHOT_STATUSES = ("empty", "building", "ready", "error")


class SnapshotFact(BaseModel):
    """One fact as found: the value, and the passage and page it came from."""

    key: str
    label: str
    value: str
    document_uuid: Optional[str] = None
    document_title: Optional[str] = None
    page: Optional[int] = None
    page_approximate: bool = False
    quote: Optional[str] = None
    # extraction_sources support state: supported / unassessed /
    # quote_unsupported / unverified. Only "supported" reads as confirmed.
    support: str = "unverified"


class AwardSnapshot(Document):
    project_uuid: str
    status: str = "empty"
    facts: list[SnapshotFact] = []
    budget_years: list[SnapshotFact] = []
    # The project documents the facts were read from, and a fingerprint of
    # their state, so a changed document set shows as out of date.
    documents: list[dict] = []
    # Files Vandalizer wrote (summaries) left unread because originals exist.
    skipped_documents: list[dict] = []
    fingerprint: Optional[str] = None
    model: Optional[str] = None
    error: Optional[str] = None
    # Who the last build was for; an automatic rebuild is metered to them.
    requested_by: Optional[str] = None
    build_token: Optional[str] = None
    requested_at: Optional[datetime.datetime] = None
    built_at: Optional[datetime.datetime] = None
    # The Page made with "Share as Page"; sharing again adds a revision to it.
    page_uuid: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

    class Settings:
        name = "award_snapshot"
        indexes = [IndexModel([("project_uuid", ASCENDING)], unique=True)]
