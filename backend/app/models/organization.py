"""Organization hierarchy model for university structure."""

import datetime
from typing import Optional

from beanie import Document
from pydantic import Field


class Organization(Document):
    """Represents a node in the university org hierarchy.

    Hierarchy: university > college/central_office > department > unit
    Teams are linked to org nodes via Team.organization_id.
    """

    uuid: str
    name: str
    org_type: str  # university | college | central_office | department | unit
    parent_id: Optional[str] = None  # parent org uuid (None for root)
    metadata: dict = {}
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )

    class Settings:
        name = "organization"
        indexes = [
            "uuid",
            "parent_id",
            "org_type",
        ]
