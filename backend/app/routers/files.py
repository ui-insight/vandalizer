import io
import zipfile

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from fastapi import Request

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.documents import (
    MoveFileRequest,
    RenameDocumentRequest,
    UploadRequest,
)
from app.services import file_service

router = APIRouter()


@router.post("/upload")
@limiter.limit("30/minute")
async def upload(
    request: Request,
    body: UploadRequest,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    try:
        result = await file_service.upload_document(
            blob=body.contentAsBase64String,
            filename=body.fileName,
            raw_extension=body.extension,
            user=user,
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
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}


@router.head("/download")
async def download_head(
    docid: str,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    result = await file_service.download_document(docid, settings, user=user)
    if not result:
        raise HTTPException(status_code=404, detail="File not found")
    media_type = MEDIA_TYPES.get(f".{result.extension.lower()}", "application/octet-stream")
    return Response(
        headers={
            "Content-Type": media_type,
            "Content-Length": str(len(result.data)),
        },
    )


@router.get("/download")
async def download(
    docid: str,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    result = await file_service.download_document(docid, settings, user=user)
    if not result:
        raise HTTPException(status_code=404, detail="File not found")
    media_type = MEDIA_TYPES.get(f".{result.extension.lower()}", "application/octet-stream")
    return StreamingResponse(
        io.BytesIO(result.data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.title}"'},
    )


@router.post("/download-bulk")
async def download_bulk(
    doc_ids: list[str] = Body(..., embed=True),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Download multiple files as a single zip archive."""
    if not doc_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for docid in doc_ids:
            result = await file_service.download_document(
                docid, settings, user=user
            )
            if result:
                zf.writestr(result.title, result.data)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=documents.zip"},
    )


@router.delete("/{doc_uuid}")
async def delete(
    doc_uuid: str,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    ok = await file_service.delete_document(doc_uuid, settings, user=user)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"ok": True}


@router.patch("/rename")
async def rename(
    body: RenameDocumentRequest,
    user: User = Depends(get_current_user),
):
    try:
        ok = await file_service.rename_document(body.uuid, body.newName, user=user)
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
    try:
        ok = await file_service.move_document(body.fileUUID, body.folderID, user=user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"ok": True}
