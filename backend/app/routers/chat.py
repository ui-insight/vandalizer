"""Chat API routes."""

import io
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.rate_limit import limiter
from app.models.activity import ActivityEvent, ActivityStatus, ActivityType
from app.models.chat import (
    ChatConversation,
    ChatMessage,
    ChatRole,
    FileAttachment,
    UrlAttachment,
)
from app.models.user import User
from app.schemas.chat import AddLinkRequest, ChatDownloadRequest, ChatRequest
from app.services import activity_service
from app.services.chat_service import chat_stream

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("")
@limiter.limit("30/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Streaming chat endpoint. Returns newline-delimited JSON chunks."""
    user_id = user.user_id
    message = body.message
    activity_id = body.activity_id
    document_uuids = list(body.document_uuids)

    # Resolve folder selections: find all documents inside selected folders
    if body.folder_uuids:
        from app.models.document import SmartDocument

        existing = set(document_uuids)
        for folder_uuid in body.folder_uuids:
            folder_docs = await SmartDocument.find(
                SmartDocument.folder == folder_uuid,
            ).to_list()
            for doc in folder_docs:
                if doc.uuid not in existing:
                    document_uuids.append(doc.uuid)
                    existing.add(doc.uuid)

    activity: Optional[ActivityEvent] = None
    conversation: Optional[ChatConversation] = None

    if not activity_id or len(str(activity_id).strip()) < 10:
        # New conversation
        conversation = ChatConversation(
            title=message.strip(),
            uuid=str(uuid.uuid4()),
            user_id=user_id,
        )
        conversation.generate_title()
        await conversation.insert()

        activity = await activity_service.activity_start(
            type=ActivityType.CONVERSATION,
            title=None,
            user_id=user_id,
            team_id=str(user.current_team) if user.current_team else None,
            conversation_id=conversation.uuid,
            space=body.current_space_id,
        )

        # Always set a placeholder title from the first message so the rail
        # shows something immediately while the AI title generates in the background.
        if not activity.title:
            first_line = (message or "").strip().splitlines()[0] if message else ""
            words = [w for w in first_line.split() if w]
            short = " ".join(words[:6]).strip() or "Chat"
            if len(short) > 80:
                short = short[:77].rstrip() + "..."
            activity.title = short
            await activity.save()
    else:
        # Resume existing conversation
        from beanie import PydanticObjectId

        activity = await ActivityEvent.get(PydanticObjectId(activity_id))
        if activity:
            activity.status = ActivityStatus.RUNNING.value
            activity.last_updated_at = datetime.now(timezone.utc)
            await activity.save()
            conversation = await ChatConversation.find_one(
                ChatConversation.uuid == activity.conversation_id,
                ChatConversation.user_id == user_id,
            )
            if not conversation:
                conversation = ChatConversation(
                    title=message.strip(),
                    uuid=str(uuid.uuid4()),
                    user_id=user_id,
                )
                conversation.generate_title()
                await conversation.insert()
                activity.conversation_id = conversation.uuid
                await activity.save()

    if not conversation:
        raise HTTPException(status_code=500, detail="Failed to create conversation")

    # Save user message
    await conversation.add_message(ChatRole.USER, message)

    async def generate():
        async for chunk in chat_stream(
            message=message,
            document_uuids=document_uuids,
            conversation_uuid=conversation.uuid,
            user_id=user_id,
            space=body.current_space_id,
            activity_id=str(activity.id) if activity else None,
            settings=settings,
            model_override=body.model,
            kb_uuid=body.knowledge_base_uuid,
            include_onboarding_context=body.include_onboarding_context,
        ):
            yield chunk

    headers = {"X-Conversation-UUID": conversation.uuid}
    if activity:
        headers["X-Activity-ID"] = str(activity.id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/add-link")
async def add_link(
    body: AddLinkRequest,
    user: User = Depends(get_current_user),
):
    """Add a URL attachment to a chat conversation."""
    user_id = user.user_id
    activity: Optional[ActivityEvent] = None
    conversation: Optional[ChatConversation] = None

    if not body.current_activity_id or len(str(body.current_activity_id).strip()) == 0:
        conversation = ChatConversation(
            user_id=user_id,
            uuid=str(uuid.uuid4()),
            title="Link Attached",
        )
        await conversation.insert()
        activity = await activity_service.activity_start(
            title="Link Attached",
            type=ActivityType.CONVERSATION,
            user_id=user_id,
            team_id=str(user.current_team) if user.current_team else None,
            conversation_id=conversation.uuid,
            space=body.current_space_id,
        )
    else:
        from beanie import PydanticObjectId

        activity = await ActivityEvent.get(PydanticObjectId(body.current_activity_id))
        if activity:
            activity.status = ActivityStatus.RUNNING.value
            activity.last_updated_at = datetime.now(timezone.utc)
            await activity.save()
            conversation = await ChatConversation.find_one(
                ChatConversation.uuid == activity.conversation_id,
                ChatConversation.user_id == user_id,
            )

    if not conversation or not activity:
        raise HTTPException(status_code=500, detail="Failed to create conversation")

    # Fetch URL content
    try:
        from app.utils.url_validation import validate_outbound_url

        validate_outbound_url(body.link)
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(body.link)
            resp.raise_for_status()
            content = resp.text[:500000]
            title = urlparse(body.link).netloc
    except ValueError as e:
        await activity_service.activity_finish(
            activity.id, status=ActivityStatus.FAILED, error=str(e)
        )
        raise HTTPException(status_code=400, detail=f"Blocked URL: {e}")
    except Exception as e:
        await activity_service.activity_finish(
            activity.id, status=ActivityStatus.FAILED, error=str(e)
        )
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}")

    url_attachment = UrlAttachment(
        url=body.link, title=title, content=content, user_id=user_id
    )
    await url_attachment.insert()

    conversation.url_attachments.append(url_attachment.id)
    conversation.updated_at = datetime.now()
    await conversation.save()

    await conversation.add_message(
        ChatRole.USER, f"[Link attached: {title}]\nURL: {body.link}]"
    )

    return {
        "success": True,
        "conversation_uuid": conversation.uuid,
        "attachment_id": str(url_attachment.id),
        "title": title,
        "content_preview": content[:500] if content else "",
        "activity_id": str(activity.id),
        "attachment": url_attachment.to_dict(),
    }


@router.post("/add-document")
async def add_document(
    files: list[UploadFile] = File(...),
    current_space_id: Optional[str] = Form(None),
    current_activity_id: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
):
    """Add file attachments to a chat conversation."""
    user_id = user.user_id
    activity: Optional[ActivityEvent] = None
    conversation: Optional[ChatConversation] = None

    if not current_activity_id or len(str(current_activity_id).strip()) < 10:
        conversation = ChatConversation(
            title="Attachments Added",
            uuid=str(uuid.uuid4()),
            user_id=user_id,
        )
        await conversation.insert()
        activity = await activity_service.activity_start(
            type=ActivityType.CONVERSATION,
            title="Document Attached",
            user_id=user_id,
            team_id=str(user.current_team) if user.current_team else None,
            conversation_id=conversation.uuid,
            space=current_space_id,
        )
    else:
        from beanie import PydanticObjectId

        activity = await ActivityEvent.get(PydanticObjectId(current_activity_id))
        if activity:
            activity.status = ActivityStatus.RUNNING.value
            activity.last_updated_at = datetime.now(timezone.utc)
            await activity.save()
            conversation = await ChatConversation.find_one(
                ChatConversation.uuid == activity.conversation_id,
                ChatConversation.user_id == user_id,
            )

    if not conversation or not activity:
        raise HTTPException(status_code=500, detail="Failed to create conversation")

    uploaded_attachments = []
    for file in files:
        if not file.filename:
            continue
        try:
            file_content = await file.read()
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

            # Use document_readers for proper text extraction (PDF, DOCX, etc.)
            # For PDFs, go straight to OCR to match the main files pipeline.
            from app.services.document_readers import extract_text_from_file, ocr_extract_text_from_pdf

            suffix = f".{ext}" if ext else ""
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name
            try:
                if ext == "pdf":
                    content_text = ocr_extract_text_from_pdf(tmp_path)
                else:
                    content_text = extract_text_from_file(tmp_path, ext or "txt")
            finally:
                os.unlink(tmp_path)

            max_content_length = 50000
            if len(content_text) > max_content_length:
                content_text = content_text[:max_content_length] + "\n\n[Content truncated...]"

            file_attachment = FileAttachment(
                filename=file.filename,
                content=content_text,
                file_type=f".{ext}" if ext else "",
                user_id=user_id,
            )
            await file_attachment.insert()

            conversation.file_attachments.append(file_attachment.id)
            await conversation.add_message(
                ChatRole.USER,
                f"File attached: {file.filename} ({len(content_text):,} characters)",
            )

            uploaded_attachments.append({
                "id": str(file_attachment.id),
                "filename": file.filename,
                "file_type": f".{ext}" if ext else "",
                "content_preview": content_text[:500],
                "content_length": len(content_text),
                "created_at": file_attachment.created_at.isoformat(),
            })
        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {e}")
            file_attachment = FileAttachment(
                filename=file.filename,
                content=f"[Error processing file: {e}]",
                file_type="",
                user_id=user_id,
            )
            await file_attachment.insert()
            conversation.file_attachments.append(file_attachment.id)

    conversation.updated_at = datetime.now()
    await conversation.save()

    return {
        "success": True,
        "conversation_uuid": conversation.uuid,
        "attachments": uploaded_attachments,
        "attachment": uploaded_attachments[0] if uploaded_attachments else None,
        "activity_id": str(activity.id),
    }


@router.delete("/remove-document/{attachment_id}")
async def remove_document(
    attachment_id: str,
    user: User = Depends(get_current_user),
):
    """Remove a file attachment from chat."""
    from beanie import PydanticObjectId

    user_id = user.user_id
    att = await FileAttachment.find_one(
        FileAttachment.id == PydanticObjectId(attachment_id),
        FileAttachment.user_id == user_id,
    )
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Remove from conversation
    conversation = await ChatConversation.find_one(
        {"file_attachments": att.id, "user_id": user_id}
    )
    if conversation:
        conversation.file_attachments = [
            a for a in conversation.file_attachments if a != att.id
        ]
        await conversation.save()

    await att.delete()
    return {"success": True}


@router.get("/conversations")
async def list_conversations(
    limit: int = 50,
    user: User = Depends(get_current_user),
):
    """List the user's chat conversations, most recent first."""
    conversations = await ChatConversation.find(
        ChatConversation.user_id == user.user_id,
    ).sort(-ChatConversation.updated_at).limit(limit).to_list()

    return [
        {
            "uuid": c.uuid,
            "title": c.title,
            "message_count": len(c.messages),
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in conversations
    ]


@router.get("/history/{conversation_uuid}")
async def get_chat_history(
    conversation_uuid: str,
    user: User = Depends(get_current_user),
):
    """Get chat conversation history."""
    conversation = await ChatConversation.find_one(
        ChatConversation.uuid == conversation_uuid,
        ChatConversation.user_id == user.user_id,
    )
    if not conversation:
        return {"messages": [], "url_attachments": [], "file_attachments": []}

    messages = await conversation.get_messages()
    url_attachments = await conversation.get_url_attachments()
    file_attachments = await conversation.get_file_attachments()

    return {
        "messages": messages,
        "url_attachments": [
            {
                "id": str(a.id),
                "url": a.url,
                "title": a.title,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in url_attachments
        ],
        "file_attachments": [
            {
                "id": str(a.id),
                "filename": a.filename,
                "file_type": a.file_type,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in file_attachments
        ],
    }


@router.delete("/history/{conversation_uuid}")
async def delete_chat_history(
    conversation_uuid: str,
    user: User = Depends(get_current_user),
):
    """Delete a chat conversation and all related records."""
    conversation = await ChatConversation.find_one(
        ChatConversation.uuid == conversation_uuid,
        ChatConversation.user_id == user.user_id,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Delete messages
    if conversation.messages:
        await ChatMessage.find({"_id": {"$in": conversation.messages}}).delete()

    # Delete attachments
    if conversation.file_attachments:
        await FileAttachment.find(
            {"_id": {"$in": conversation.file_attachments}}
        ).delete()
    if conversation.url_attachments:
        await UrlAttachment.find(
            {"_id": {"$in": conversation.url_attachments}}
        ).delete()

    await conversation.delete()
    return {"success": True, "message": "Conversation deleted successfully"}


@router.post("/download")
async def download_chat(
    body: ChatDownloadRequest,
    user: User = Depends(get_current_user),
):
    """Export chat content as TXT or CSV."""
    fmt = body.format.lower()
    content = body.content

    if fmt == "csv":
        buf = io.BytesIO(content.encode("utf-8"))
        return StreamingResponse(
            buf,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=chat_output.csv"},
        )

    # Default to txt
    buf = io.BytesIO(content.encode("utf-8"))
    return StreamingResponse(
        buf,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=chat_output.txt"},
    )
