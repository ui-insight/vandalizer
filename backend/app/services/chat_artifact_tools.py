"""Skill-compatible artifact tools using the existing prior-turn approval gate."""
import functools
import hashlib

import anyio
from fastapi import HTTPException
from pydantic_ai.tools import RunContext

from app.services.chat_deps import AgenticChatDeps
from app.services import artifacts, chat_page_previews
from app.services.page_authoring import PAGE_INTERACTION_RULES, PAGE_LANGUAGE_RULES, PAGE_SOURCE_FIDELITY_RULES
from app.tasks import get_sync_db


RENDERING_NOTE = (
    "Pages render HTML/CSS with native links and expandable sections. JavaScript charts, filters and table sorting are not supported, "
    "including client-side scripts. Describe the actual preview and its working controls. "
    "If warnings are present, explain what was removed and any missing data before asking to save or reporting success. "
    "Put all chart values and table rows directly in the HTML; use CSS bars and complete tables instead of scripts. "
    + PAGE_INTERACTION_RULES
)


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
    """Read your own page's latest saved HTML and revision before revising it.

    Generated HTML is not source evidence. Read the original documents to verify
    values and source notes before revising a document-based page.
    """
    try:
        doc = await _call(artifacts.get, artifact_uuid)
        if doc["user_id"] != context.deps.user_id:
            return {"error": "Page not found or you do not own it."}
        rev = artifacts.revision(doc)
        return {"artifact_uuid": doc["uuid"], "title": rev["title"], "revision": rev["uuid"], "html": rev["html"],
                "version": next(i for i, entry in enumerate(doc["revisions"], 1) if entry["uuid"] == rev["uuid"]),
                "warnings": rev["warnings"], "rendering_note": RENDERING_NOTE,
                "source_fidelity_note": PAGE_SOURCE_FIDELITY_RULES, "language_note": PAGE_LANGUAGE_RULES}
    except HTTPException as exc:
        return {"error": exc.detail}


async def create_html_artifact(context: RunContext[AgenticChatDeps], title: str, html: str, confirmed: bool = False) -> dict:
    """Create a private hosted HTML/CSS page. Self-contained static HTML only; no JS or remote assets.

    Preview first and await a later user approval. Include only the intended report/page,
    not the whole chat or private source documents. Does not publish or share anything.
    For dashboards, embed all data in full HTML tables and static CSS bars. No canvas,
    SVG, JavaScript charts, filter controls or sortable tables. For interactivity, include
    a linked table of contents, KPI-to-chart jump links, details/summary disclosures
    for Source notes and Calculated summary, and known web/mailto links. Explain
    which controls work without scripts; disclose returned warnings before saving.
    Read the original source and preserve every category/year value in its own
    table cell, including repeated values. Label calculated summaries separately;
    never invent source notes or call exact source values ranges. Compare all
    displayed values and source claims with the original before previewing.
    Call it a Page in replies; name the Save page button, never the tool or flags.
    """
    return await _save(context, title, html, confirmed)


async def revise_html_artifact(context: RunContext[AgenticChatDeps], artifact_uuid: str, base_revision: str, title: str, html: str, confirmed: bool = False) -> dict:
    """Preview then save a new revision of your own page. Read it with get_html_artifact first.

    Send full replacement HTML and the exact base_revision read. The prior published
    revision remains unchanged. Publication is an explicit owner action in the viewer.
    Static HTML/CSS only: embed all table rows and chart values directly in the HTML.
    Preserve and offer native jump links, details/summary expandable sections and
    known web/mailto links. JavaScript charts, filters and table sorting are
    unsupported. Disclose returned warnings.
    Re-read the original source, not just the old page: preserve every category/year
    value in separate cells, including repeated values. Label calculated summaries
    separately and verify source notes instead of carrying forward earlier inventions.
    Call it a Page in replies; name the Save new version button, never revision IDs or flags.
    """
    return await _save(context, title, html, confirmed, artifact_uuid, base_revision)


async def _save(context, title, html, confirmed, artifact_uuid=None, base_revision=None):
    from app.services.chat_tools import _confirm_gate
    try:
        if len(title) > 200:
            return {"error": "Use a title of at most 200 characters."}
        doc = None
        if artifact_uuid:
            doc = await _call(artifacts.get, artifact_uuid)
            if doc["user_id"] != context.deps.user_id:
                return {"error": "Page not found or you do not own it."}
            if doc["latest_revision"] != base_revision:
                return {"error": "Page changed. Read the latest revision before proposing an edit."}
        name = "revise_html_artifact" if artifact_uuid else "create_html_artifact"
        snapshot = await _call(chat_page_previews.prepare, context.deps.user_id,
            context.deps.conversation.uuid, title, html, artifact_uuid, base_revision, _source(context))
        digest = hashlib.sha256((title + snapshot["prepared_html"]).encode()).hexdigest()
        gate = await _confirm_gate(context, tool_name=name,
            key={"artifact": artifact_uuid, "base": base_revision, "sha256": digest}, confirmed=confirmed,
            preview={"needs_confirmation": True, "action": name,
                     "preview": f'Save a private Page: {title}. This does not publish it.',
                     "preview_id": snapshot["_id"], "title": snapshot["title"],
                     "artifact_preview_html": snapshot["prepared_html"], "warnings": snapshot["warnings"], "rendering_note": RENDERING_NOTE,
                     "source_fidelity_note": PAGE_SOURCE_FIDELITY_RULES, "language_note": PAGE_LANGUAGE_RULES})
        if gate is not None:
            return gate
        saved = await _call(chat_page_previews.save, context.deps.user_id,
            context.deps.conversation.uuid, snapshot["_id"])
        return {**saved, "rendering_note": RENDERING_NOTE,
                "source_fidelity_note": PAGE_SOURCE_FIDELITY_RULES, "language_note": PAGE_LANGUAGE_RULES}
    except HTTPException as exc:
        return {"error": exc.detail}
