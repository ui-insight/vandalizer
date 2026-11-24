"""Local operational observations only; never evidence for assessed credit."""
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class CertificationJourneyEvent(Document):
    uuid: str
    user_id: str
    enrollment_id: str | None = None
    course_version: str | None = None
    manifest_sha256: str | None = None
    state: str
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = 'certification_journey_events'
        indexes = [IndexModel('uuid', unique=True), 'user_id',
                   IndexModel('observed_at', expireAfterSeconds=90 * 24 * 60 * 60)]
