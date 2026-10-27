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
    title: str = ""
    project_uuid: Optional[str] = None
    source: dict = Field(default_factory=dict)
    latest_revision: str
    revisions: list[dict] = Field(default_factory=list)
    published_revision: Optional[str] = None
    public_token: Optional[str] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "html_artifacts"
        indexes = [IndexModel("uuid", unique=True), "user_id", "team_id", "public_token", "project_uuid", "updated_at"]
