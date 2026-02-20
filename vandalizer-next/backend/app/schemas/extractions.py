"""Request/response models for extraction endpoints."""

from typing import Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# SearchSet
# ---------------------------------------------------------------------------

class CreateSearchSetRequest(BaseModel):
    title: str
    space: str
    set_type: str = "extraction"
    extraction_config: Optional[dict] = None


class UpdateSearchSetRequest(BaseModel):
    title: Optional[str] = None
    extraction_config: Optional[dict] = None


class SearchSetItemRequest(BaseModel):
    searchphrase: str
    searchtype: str = "extraction"
    title: Optional[str] = None


class UpdateSearchSetItemRequest(BaseModel):
    searchphrase: Optional[str] = None
    title: Optional[str] = None


class BuildFromDocumentRequest(BaseModel):
    document_uuids: list[str]
    model: Optional[str] = None


class SearchSetResponse(BaseModel):
    id: str
    title: str
    uuid: str
    space: str
    status: str
    set_type: str
    user_id: Optional[str] = None
    is_global: bool = False
    verified: bool = False
    item_count: int = 0
    extraction_config: dict = {}


class SearchSetItemResponse(BaseModel):
    id: str
    searchphrase: str
    searchset: Optional[str] = None
    searchtype: str
    title: Optional[str] = None


# ---------------------------------------------------------------------------
# Extraction execution
# ---------------------------------------------------------------------------

class RunExtractionRequest(BaseModel):
    search_set_uuid: str
    document_uuids: list[str]
    model: Optional[str] = None
    extraction_config_override: Optional[dict] = None


class RunExtractionSyncRequest(BaseModel):
    search_set_uuid: str
    document_uuids: list[str]
    model: Optional[str] = None
    extraction_config_override: Optional[dict] = None


class ExtractionStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[list] = None
