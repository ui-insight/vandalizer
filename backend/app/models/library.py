"""Library models  - Library, LibraryItem, LibraryFolder, and related enums."""

import datetime
from enum import Enum
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field


class LibraryScope(str, Enum):
    PERSONAL = "personal"
    TEAM = "team"
    VERIFIED = "verified"


class LibraryItemKind(str, Enum):
    WORKFLOW = "workflow"
    SEARCH_SET = "search_set"


class LibraryFolder(Document):
    uuid: str
    name: str
    parent_id: Optional[str] = None
    scope: LibraryScope
    owner_user_id: str
    team: Optional[PydanticObjectId] = None
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    class Settings:
        name = "library_folder"


class LibraryItem(Document):
    item_id: PydanticObjectId
    kind: LibraryItemKind
    added_by_user_id: str
    verified: bool = False
    tags: list[str] = Field(default_factory=list)
    note: Optional[str] = None
    folder: Optional[str] = None
    pinned: bool = False
    favorited: bool = False
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    last_used_at: Optional[datetime.datetime] = None

    class Settings:
        name = "library_item"


class Library(Document):
    scope: LibraryScope
    title: str
    description: Optional[str] = None
    owner_user_id: str
    team: Optional[PydanticObjectId] = None
    items: list[PydanticObjectId] = Field(default_factory=list)
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    class Settings:
        name = "library"
