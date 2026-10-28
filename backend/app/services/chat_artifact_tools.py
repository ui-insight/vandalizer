"""Skill-compatible artifact tools using the existing prior-turn approval gate."""
import functools
import hashlib

import anyio
from fastapi import HTTPException
from pydantic_ai.tools import RunContext

from app.services.chat_deps import AgenticChatDeps
from app.services import artifacts
from app.tasks import get_sync_db


async def _call(fn, *args):
    return await anyio.to_thread.run_sync(functools.partial(fn, get_sync_db(), *args))


def _source(context):
    conversation = context.deps.conversation
    skill = getattr(conversation, "active_skill", None)
    return {"kind": "chat", "conversation_uuid": getattr(conversation, "uuid", None),
            "project_uuid": getattr(context.deps, "active_project_uuid", None),
            "turn": context.deps.turn_marker,
            "skill": {"uuid": skill.uuid, "version": skill.version} if skill else None}


async def get_html_artifact(context: RunContext[AgenticChatDeps], artifact_uuid: str) -> dict:
    """Read your own page's latest saved HTML and revision before revising it."""
    try:
        doc = await _call(artifacts.get, artifact_uuid)
        if doc["user_id"] != context.deps.user_id:
            return {"error": "Page not found or you do not own it."}
        rev = artifacts.revision(doc)
        return {"artifact_uuid": doc["uuid"], "title": rev["title"], "revision": rev["uuid"], "html": rev["html"]}
    except HTTPException as exc:
        return {"error": exc.detail}


async def create_html_artifact(context: RunContext[AgenticChatDeps], title: str, html: str, confirmed: bool = False) -> dict:
    """Create a private hosted HTML/CSS page. Self-contained static HTML only; no JS or remote assets.

    Preview first and await a later user approval. Include only the intended report/page,
    not the whole chat or private source documents. Does not publish or share anything.
    """
    return await _save(context, title, html, confirmed)


async def revise_html_artifact(context: RunContext[AgenticChatDeps], artifact_uuid: str, base_revision: str, title: str, html: str, confirmed: bool = False) -> dict:
    """Preview then save a new revision of your own page. Read it with get_html_artifact first.

    Send full replacement HTML and the exact base_revision read. The prior published
    revision remains unchanged. Publication is an explicit owner action in the viewer.
    """
    return await _save(context, title, html, confirmed, artifact_uuid, base_revision)


async def _save(context, title, html, confirmed, artifact_uuid=None, base_revision=None):
    from app.services.chat_tools import _confirm_gate
    try:
        if len(title) > 200:
            return {"error": "Use a title of at most 200 characters."}
        prepared, warnings = artifacts.clean_html(html, title)
        digest = hashlib.sha256((title + prepared).encode()).hexdigest()
        doc = None
        if artifact_uuid:
            doc = await _call(artifacts.get, artifact_uuid)
            if doc["user_id"] != context.deps.user_id:
                return {"error": "Page not found or you do not own it."}
            if doc["latest_revision"] != base_revision:
                return {"error": "Page changed. Read the latest revision before proposing an edit."}
        name = "revise_html_artifact" if artifact_uuid else "create_html_artifact"
        gate = await _confirm_gate(context, tool_name=name,
            key={"artifact": artifact_uuid, "base": base_revision, "sha256": digest}, confirmed=confirmed,
            preview={"needs_confirmation": True, "action": name,
                     "preview": f'Save a private HTML page: {title}. This does not publish it.',
                     "artifact_preview_html": prepared, "warnings": warnings})
        if gate is not None:
            return gate
        if doc:
            saved = await _call(artifacts.revise, doc, title, html, base_revision, _source(context))
        else:
            key = f"chat:{context.deps.conversation.uuid}:{digest}"
            saved = await _call(artifacts.create, context.deps.user_id, title, html, key, _source(context))
        return {"artifact_uuid": saved["uuid"], "title": title, "revision": saved["latest_revision"],
                "url": f'/pages/{saved["uuid"]}', "visibility": "private", "warnings": warnings}
    except HTTPException as exc:
        return {"error": exc.detail}
