"""Organization hierarchy model for university structure."""

import datetime
from typing import Optional

from beanie import Document
from pydantic import Field


# Valid role_segment values. Mirrored by auth_service / briefing_primer_content;
# extend in all three places when adding a new role.
VALID_ROLE_SEGMENTS: set[str] = {
    "research_admin",
    "pi",
    "sponsored_programs",
    "compliance",
    "it",
    "other",
}


class Organization(Document):
    """Represents a node in the university org hierarchy.

    Hierarchy: university > college/central_office > department > unit
    Teams are linked to org nodes via Team.organization_id.

    `role_segment` declares the kind of work done in this org node (compliance,
    sponsored_programs, etc.). Users inherit a role_segment by walking up their
    org ancestry until they hit a node that declares one.
    """

    uuid: str
    name: str
    org_type: str  # university, college, central_office, department, unit
    parent_id: Optional[str] = None  # parent org uuid (None for root)
    role_segment: Optional[str] = None  # one of VALID_ROLE_SEGMENTS
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
