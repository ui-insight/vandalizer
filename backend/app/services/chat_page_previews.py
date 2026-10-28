"""Immutable chat page proposals: approval saves bytes, not a regenerated prompt."""
import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo import ReturnDocument

from app.services import artifacts


def prepare(db, user_id, conversation_uuid, title, html, artifact_uuid, base_revision, source):
    prepared, warnings = artifacts.clean_html(html, title)
    # Equivalent sanitized HTML reuses the original proposal and its warnings.
    identity = [user_id, conversation_uuid, artifact_uuid, base_revision, title, prepared]
    preview_id = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:32]
    return db.chat_page_previews.find_one_and_update({"_id": preview_id}, {"$setOnInsert": {
        "user_id": user_id, "conversation_uuid": conversation_uuid,
        "title": title, "html": html, "prepared_html": prepared, "warnings": warnings,
        "artifact_uuid": artifact_uuid, "base_revision": base_revision,
        "source": source, "created_at": datetime.now(timezone.utc),
    }}, upsert=True, return_document=ReturnDocument.AFTER)


def get(db, user_id, conversation_uuid, preview_id):
    preview = db.chat_page_previews.find_one({
        "_id": preview_id, "user_id": user_id, "conversation_uuid": conversation_uuid,
    })
    if not preview:
        raise HTTPException(404, "Page preview not found. Ask for a new preview before saving.")
    return preview


def save(db, user_id, conversation_uuid, preview_id):
    preview = get(db, user_id, conversation_uuid, preview_id)
    title, html = preview["title"], preview["html"]
    target, base = preview["artifact_uuid"], preview["base_revision"]
    if target:
        doc = artifacts.get(db, target)
        if doc["user_id"] != user_id:
            raise HTTPException(404, "Page not found")
        # CAS protects newer edits; deterministic revision IDs make a repeated
        # approval safe when the first save's acknowledgement was lost.
        saved = artifacts.revise(db, doc, title, html, base, preview["source"])
    else:
        saved = artifacts.create(db, user_id, title, html, f"chat-preview:{preview_id}", preview["source"])
    expected = artifacts._revision(title, html, base or "", preview["source"])
    revision = artifacts.revision(saved, expected["uuid"])
    version = next(i for i, entry in enumerate(saved["revisions"], 1) if entry["uuid"] == revision["uuid"])
    return {"preview_id": preview_id, "artifact_uuid": saved["uuid"],
            "title": revision["title"], "revision": revision["uuid"],
            "version": version, "message": f'Saved "{revision["title"]}" as Page version {version}.',
            "url": f'/pages/{saved["uuid"]}', "visibility": "private",
            "warnings": revision["warnings"]}
