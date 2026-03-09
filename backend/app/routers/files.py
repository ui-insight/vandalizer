from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models.user import User
from app.schemas.documents import (
    MoveFileRequest,
    RenameDocumentRequest,
    UploadRequest,
)
from app.services import file_service

router = APIRouter()


@router.post("/upload")
async def upload(
    body: UploadRequest,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    try:
        result = await file_service.upload_document(
            blob=body.contentAsBase64String,
            filename=body.fileName,
            raw_extension=body.extension,
            space=body.space,
            user_id=user.user_id,
            settings=settings,
            folder=body.folder,
            root_folder_name=body.rootFolderName,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
}


@router.head("/download")
async def download_head(
    docid: str,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    path = await file_service.download_document(docid, settings)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return Response(
        headers={
            "Content-Type": media_type,
            "Content-Length": str(path.stat().st_size),
        },
    )


@router.get("/download")
async def download(
    docid: str,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    path = await file_service.download_document(docid, settings)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(
        path,
        filename=path.name,
        media_type=media_type,
        content_disposition_type="inline",
    )


@router.delete("/{doc_uuid}")
async def delete(
    doc_uuid: str,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    ok = await file_service.delete_document(doc_uuid, settings)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"ok": True}


@router.patch("/rename")
async def rename(
    body: RenameDocumentRequest,
    user: User = Depends(get_current_user),
):
    try:
        ok = await file_service.rename_document(body.uuid, body.newName)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"ok": True}


@router.patch("/move")
async def move(
    body: MoveFileRequest,
    user: User = Depends(get_current_user),
):
    ok = await file_service.move_document(body.fileUUID, body.folderID)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"ok": True}
