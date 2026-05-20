import io
import re
import zipfile

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response
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


_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _parse_range_header(header: str, total: int) -> tuple[int, int] | None:
    """Parse a single-range `Range` header. Returns (start, end_inclusive) or
    None on a malformed/unsupported header. Multi-range requests are not
    supported — return None so the caller falls back to a full response.
    """
    if not header:
        return None
    match = _RANGE_RE.match(header.strip())
    if not match or "," in header:
        return None
    start_str, end_str = match.group(1), match.group(2)
    if start_str == "" and end_str == "":
        return None
    if start_str == "":
        # Suffix range: last N bytes
        try:
            n = int(end_str)
        except ValueError:
            return None
        if n <= 0:
            return None
        start = max(total - n, 0)
        end = total - 1
    else:
        try:
            start = int(start_str)
        except ValueError:
            return None
        end = int(end_str) if end_str else total - 1
    if start < 0 or end < start or start >= total:
        return None
    end = min(end, total - 1)
    return start, end


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
            # Advertise range support so PDF.js progressively loads pages
            # instead of waiting for the whole file.
            "Accept-Ranges": "bytes",
        },
    )


@router.get("/download")
async def download(
    docid: str,
    inline: bool = Query(False, description="Serve with inline disposition for in-browser viewers."),
    range_header: str | None = Header(None, alias="Range"),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    result = await file_service.download_document(docid, settings, user=user)
    if not result:
        raise HTTPException(status_code=404, detail="File not found")
    media_type = MEDIA_TYPES.get(f".{result.extension.lower()}", "application/octet-stream")
    disposition = "inline" if inline else "attachment"
    data = result.data
    total = len(data)

    # PDF.js issues Range requests once Accept-Ranges is advertised, which
    # lets the viewer paint the first page long before the whole file lands.
    range_spec = _parse_range_header(range_header or "", total)
    if range_spec is not None:
        start, end = range_spec
        chunk = data[start : end + 1]
        return Response(
            content=chunk,
            status_code=206,
            media_type=media_type,
            headers={
                "Content-Disposition": f'{disposition}; filename="{result.title}"',
                "Content-Range": f"bytes {start}-{end}/{total}",
                "Content-Length": str(len(chunk)),
                "Accept-Ranges": "bytes",
            },
        )

    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{result.title}"',
            "Content-Length": str(total),
            "Accept-Ranges": "bytes",
        },
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


@router.get("/{doc_uuid}/sheet-json")
async def sheet_json(
    doc_uuid: str,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Return evaluated rows for an .xlsx file so the viewer can render
    formula results instead of blank cells when Excel didn't cache them.
    """
    result = await file_service.render_xlsx_sheets(doc_uuid, settings, user=user)
    if result is None:
        raise HTTPException(status_code=404, detail="Sheet rendering not available")
    return result


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
