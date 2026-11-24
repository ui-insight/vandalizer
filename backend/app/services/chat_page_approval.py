"""Execute an authenticated Save-button decision without another model call."""
from collections.abc import AsyncIterator
from app.models.chat import ChatConversation
import asyncio
import hashlib
import json
import logging
import uuid

import anyio
from fastapi import HTTPException

from app.services import chat_page_previews
from app.services.chat_artifact_tools import _call

logger = logging.getLogger(__name__)


async def stream_save(conversation: ChatConversation, preview: dict, activity_id: str | None, user_id: str) -> AsyncIterator[str]:
    name = "revise_html_artifact" if preview["artifact_uuid"] else "create_html_artifact"
    call = {"tool_name": name, "tool_call_id": str(uuid.uuid4()),
            "args": {"preview_id": preview["_id"], "title": preview["title"], "confirmed": True}}
    yield json.dumps({"kind": "tool_call", **call}) + "\n"
    # Transport cleanup cancels its producer with asyncio.Task.cancel, which
    # bypasses AnyIO cancel-scope shielding. Keep and join a separate task so
    # both raw asyncio and request-scope cancellation finish the receipt.
    saving = asyncio.create_task(_save_and_record(conversation, preview, activity_id, user_id, call))
    try:
        result, message = await asyncio.shield(saving)
    except asyncio.CancelledError:
        with anyio.CancelScope(shield=True):
            await asyncio.shield(saving)
        raise
    yield json.dumps({"kind": "tool_result", **result}) + "\n"
    yield json.dumps({"kind": "error" if result["content"].get("error") else "text", "content": message}) + "\n"


async def _save_and_record(conversation: ChatConversation, preview: dict, activity_id: str | None, user_id: str, call: dict) -> tuple[dict, str]:
    from app.services.chat_service import _finalize, _save_failed_assistant_turn
    from app.services.chat_tools import _confirm_fingerprint

    name = call["tool_name"]
    with anyio.CancelScope(shield=True):
        try:
            saved = await _call(chat_page_previews.save, user_id, conversation.uuid, preview["_id"])
        except HTTPException as exc:
            saved = {"preview_id": preview["_id"], "error": str(exc.detail)}
        except Exception:
            logger.exception("Could not save page preview %s", preview["_id"])
            saved = {"preview_id": preview["_id"], "error": "The page save could not be confirmed. Retry saving this preview."}
        result = {"tool_name": name, "tool_call_id": call["tool_call_id"], "content": saved}
        message = saved.get("error") or saved["message"]
        segments = [{"kind": "tool_call", "call": call}, {"kind": "tool_result", "result": result}]
        try:
            if saved.get("error"):
                await _save_failed_assistant_turn(conversation, message, activity_id, message,
                    tool_calls=[call], tool_results=[result], segments=segments)
            else:
                digest = hashlib.sha256((preview["title"] + preview["prepared_html"]).encode()).hexdigest()
                fp = _confirm_fingerprint(name, {"artifact": preview["artifact_uuid"],
                    "base": preview["base_revision"], "sha256": digest})
                conversation.pending_confirmations = [p for p in conversation.pending_confirmations if p.get("fp") != fp]
                await _finalize(conversation, message, [], None, activity_id, user_id,
                    tool_calls=[call], tool_results=[result],
                    segments=[*segments, {"kind": "text", "content": message}])
        except Exception:
            logger.exception("Could not record page approval in chat %s", conversation.uuid)
    return result, message
