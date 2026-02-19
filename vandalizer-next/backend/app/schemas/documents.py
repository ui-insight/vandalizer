from typing import Optional
from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    title: str
    uuid: str
    extension: str
    processing: bool
    valid: bool
    task_status: Optional[str] = None
    folder: Optional[str] = None
    created_at: str
    token_count: int = 0
    num_pages: int = 0


class FolderResponse(BaseModel):
    id: str
    title: str
    uuid: str
    parent_id: str
    is_shared_team_root: bool = False


class UploadRequest(BaseModel):
    contentAsBase64String: str
    fileName: str
    extension: str
    space: str
    folder: Optional[str] = None
    rootFolderName: Optional[str] = None


class PollStatusResponse(BaseModel):
    status: Optional[str] = None
    status_messages: list[str] = []
    complete: bool = False
    raw_text: str = ""
    validation_feedback: Optional[str] = None
    valid: bool = True
    path: Optional[str] = None


class CreateFolderRequest(BaseModel):
    name: str
    parent_id: str
    space: str
    folder_type: str = "individual"


class RenameFolderRequest(BaseModel):
    uuid: str
    newName: str


class RenameDocumentRequest(BaseModel):
    uuid: str
    newName: str


class MoveFileRequest(BaseModel):
    fileUUID: str
    folderID: str


class ListRequest(BaseModel):
    space: str
    folder: Optional[str] = None
