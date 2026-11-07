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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "html_artifacts"
        indexes = [IndexModel("uuid", unique=True), "user_id", "team_id", "public_token", "publications.token", "project_uuid", "updated_at",
                   "public_expires_at", "publications.expires_at",
                   # page_sources.notify_source_revised: Pages built from a file
                   # that just got a new version, scanned on every version upload.
                   "revisions.source.documents.uuid"]


class PageLinkViewer(Document):
    """A signed-in person who opened a Page's sign-in-only public link."""
    artifact_uuid: str
    token: str
    user_id: str
    name: str = ""
    email: str = ""
    views: int = 0
    first_at: Optional[datetime] = None
    last_at: Optional[datetime] = None

    class Settings:
        name = "page_link_viewers"
        indexes = [IndexModel([("artifact_uuid", 1), ("token", 1), ("user_id", 1)], unique=True),
                   IndexModel([("artifact_uuid", 1), ("token", 1), ("last_at", -1)])]
