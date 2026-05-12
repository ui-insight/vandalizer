"""Shared user-related response schemas."""

from typing import Optional

from pydantic import BaseModel


class AuthorRef(BaseModel):
    """Lightweight reference to a user, used for author/creator badges in lists."""

    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
