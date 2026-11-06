"""A question or flag a page viewer sent its owner, pinned to a spot on the page.

Support ticket: team members and public-link viewers (grant admins, PIs,
sponsors) could not ask about a figure or flag a section; only the owner
could act on a page.
"""

import datetime
import uuid as uuid_mod
from typing import Optional

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

FEEDBACK_STATUSES = ("open", "answered", "resolved")


class FeedbackAnchor(BaseModel):
    """The spot a viewer clicked: an element path and the text it showed."""

    # Child-element indices from <body>, e.g. "0/3/1/2", as the embed script
    # computes them; text is what the element showed, for re-finding it in a
    # later version and for reading the question without the page.
    path: Optional[str] = None
    text: str = ""


class FeedbackAnswer(BaseModel):
    text: str
    by_user_id: str
    by_name: str = ""
    at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    # Shown to everyone viewing the page (public link included) as a short note.
    on_page: bool = False


class PageFeedback(Document):
    uuid: str = Field(default_factory=lambda: uuid_mod.uuid4().hex)
    artifact_uuid: str
    owner_user_id: str
    revision: str
    version: int = 1
    anchor: FeedbackAnchor = Field(default_factory=FeedbackAnchor)
    message: str
    kind: str = "question"  # "question" or "flag"
    # "member" (signed in, can view the page) or "public" (public link).
    author_kind: str
    author_user_id: Optional[str] = None
    author_name: str = ""
    # Public askers only; never shown to anyone but the owner.
    author_email: Optional[str] = None
    public_token: Optional[str] = None
    status: str = "open"
    answer: Optional[FeedbackAnswer] = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

    class Settings:
        name = "page_feedback"
        indexes = [
            IndexModel([("uuid", ASCENDING)], unique=True),
            IndexModel([("artifact_uuid", ASCENDING), ("created_at", DESCENDING)]),
        ]
