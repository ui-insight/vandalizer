"""A Skill's share link: its token and the people who opened it."""

import datetime

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class SearchSetShare(Document):
    """One per shared Skill, kept apart from the Skill itself.

    The Skill document is saved whole from many places (edits, validation
    runs that take minutes), so a link stored on it could be brought back by
    a stale save after its owner turned it off. Everything here is written
    with single conditional updates instead (see ``skill_share_service``).
    """

    search_set_uuid: str
    token: str
    # user_ids of signed-in people who opened the link.
    recipients: list[str] = []
    created_by: str
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))

    class Settings:
        name = "search_set_share"
        indexes = [IndexModel("search_set_uuid", unique=True)]
