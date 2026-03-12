import datetime
from typing import Optional

from beanie import Document


class CertificationProgress(Document):
    """Tracks a user's progress through the Vandal Workflow Architect certification."""

    user_id: str
    modules: dict = {}  # {module_id: {completed, stars, completed_at, attempts, xp_earned}}
    total_xp: int = 0
    level: str = "novice"
    certified: bool = False
    certified_at: Optional[datetime.datetime] = None
    streak_days: int = 0
    last_activity_date: Optional[str] = None  # YYYY-MM-DD for streak tracking
    created_at: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)
    updated_at: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)

    class Settings:
        name = "certification_progress"
