"""Request/response models for library endpoints."""

from typing import Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------


class LibraryResponse(BaseModel):
    id: str
    scope: str
    title: str
    description: Optional[str] = None
    owner_user_id: str
    team_id: Optional[str] = None
    item_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UpdateLibraryRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


class LibraryItemResponse(BaseModel):
    id: str
    item_id: str
    item_uuid: Optional[str] = None
    kind: str
    name: str
    description: Optional[str] = None
    set_type: Optional[str] = None
    tags: list[str] = []
    note: Optional[str] = None
    folder: Optional[str] = None
    pinned: bool = False
    favorited: bool = False
    verified: bool = False
    added_by_user_id: str
    created_at: Optional[str] = None
    last_used_at: Optional[str] = None
    quality_tier: Optional[str] = None
    quality_score: Optional[float] = None


class AddItemRequest(BaseModel):
    item_id: str
    kind: str
    note: Optional[str] = None
    tags: Optional[list[str]] = None
    folder: Optional[str] = None


class UpdateItemRequest(BaseModel):
    note: Optional[str] = None
    tags: Optional[list[str]] = None
    pinned: Optional[bool] = None
    favorited: Optional[bool] = None


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


class CreateFolderRequest(BaseModel):
    name: str
    parent_id: Optional[str] = None
    scope: str
    team_id: Optional[str] = None


class RenameFolderRequest(BaseModel):
    name: str


class MoveItemsRequest(BaseModel):
    item_ids: list[str]
    folder_uuid: Optional[str] = None


# ---------------------------------------------------------------------------
# Clone / Share
# ---------------------------------------------------------------------------


class CloneRequest(BaseModel):
    item_id: str


class ShareToTeamRequest(BaseModel):
    item_id: str
    team_id: str


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str
    kind: Optional[str] = None
    team_id: Optional[str] = None
