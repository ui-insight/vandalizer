"""Hosted static HTML pages. Revisions are append-only within a bounded document."""
from datetime import datetime, timezone
from typing import Optional

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class Artifact(Document):
    uuid: str
    user_id: str
    team_id: Optional[str] = None
    team_revision: Optional[str] = None
    title: str = ""
    project_uuid: Optional[str] = None
    source: dict = Field(default_factory=dict)
    latest_revision: str
    revisions: list[dict] = Field(default_factory=list)
    published_revision: Optional[str] = None
    public_token: Optional[str] = None
    publications: list[dict] = Field(default_factory=list)
    deleted_at: Optional[datetime] = None
    # Viewer questions (services/page_feedback.py): whether public-link
    # viewers may ask, and how the "Shared by" line names the owner.
    public_questions: bool = False
    sharing_contact: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "html_artifacts"
        indexes = [IndexModel("uuid", unique=True), "user_id", "team_id", "public_token", "publications.token", "project_uuid", "updated_at"]



class PageFeedback(Document):
    """A viewer's question or flag about a Page, and the owner's answer.

    Written and read through pymongo in services/page_feedback.py; this model
    declares the collection's shape and indexes.
    """
    uuid: str
    artifact_uuid: str
    owner_user_id: str
    revision: str
    version: Optional[int] = None
    page_title: str = ""
    anchor_id: Optional[str] = None
    anchor_label: Optional[str] = None
    message: str
    # {"kind": "user", "user_id", "name"} or {"kind": "public", "email", "name", "token", "ip"}
    asker: dict = Field(default_factory=dict)
    status: str = "open"  # open | answered | closed
    # {"text", "answered_at", "show_on_page"}
    answer: Optional[dict] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "page_feedback"
        indexes = [IndexModel("uuid", unique=True), [("artifact_uuid", 1), ("created_at", -1)],
                   [("artifact_uuid", 1), ("status", 1)], "asker.user_id"]
