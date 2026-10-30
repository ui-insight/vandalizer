"""Skill-compatible artifact tools using the existing prior-turn approval gate."""
import functools
from typing import Callable, Concatenate, ParamSpec, TypeVar
from pymongo.database import Database
import hashlib

import anyio
from fastapi import HTTPException
from pydantic_ai.tools import RunContext

from app.services.chat_deps import AgenticChatDeps
from app.services import artifacts, chat_page_previews
from app.services.page_authoring import PAGE_INTERACTION_RULES, PAGE_LANGUAGE_RULES, PAGE_SOURCE_FIDELITY_RULES
from app.tasks import get_sync_db
from app.schemas.page_template import TemplateTable, TemplateValue


RENDERING_NOTE = (
    "Pages render HTML/CSS with native links and expandable sections. JavaScript charts, filters and table sorting are not supported, "
    "including client-side scripts. Describe the actual preview and its working controls. "
    "If warnings are present, explain what was removed and any missing data before asking to save or reporting success. "
    "Put all chart values and table rows directly in the HTML; use CSS bars and complete tables instead of scripts. "
    + PAGE_INTERACTION_RULES
)


P = ParamSpec("P")
ResultT = TypeVar("ResultT")


async def _call(fn: Callable[Concatenate[Database[dict], P], ResultT], *args: P.args, **kwargs: P.kwargs) -> ResultT:
    return await anyio.to_thread.run_sync(functools.partial(fn, get_sync_db(), *args, **kwargs))


def _source(context: RunContext[AgenticChatDeps]) -> dict:
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


async def create_html_artifact(context: RunContext[AgenticChatDeps], title: str, html: str = "", confirmed: bool = False, template_uuid: str | None = None, source_document_uuid: str | None = None, template_values: list[TemplateValue] | None = None, template_tables: list[TemplateTable] | None = None) -> dict:
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
    To reuse a template, read get_page_template, then supply template_uuid,
    source_document_uuid and template_values (field_id, exact value, supporting
    quote from that file). For tables, supply template_tables with all relevant
    rows from the new file, in template column order (value/quote per cell, null
    for missing). This replaces old data rows; do not fill their scalar fields too.
    HTML is ignored for template use; the server preserves
    the design, verifies evidence, marks missing fields and reports fill counts.
    Never carry values from another file or calculate unsupported source values.
    Call it a Page in replies; name the Save page button, never the tool or flags.
    """
    if template_uuid:
        from app.routers.page_templates import authorized
        from app.services import access_control, page_templates
        try:
            template = await authorized(template_uuid, context.deps.user)
            document = await access_control.get_authorized_document(source_document_uuid or '', context.deps.user)
            if not document:
                return {'error': 'Choose a file you can access for this template.'}
            if context.deps.context_document_uuids and source_document_uuid not in context.deps.context_document_uuids:
                return {'error': 'Use the newly attached file for this template, or attach the file you want to use.'}
            html, check = page_templates.fill(template, document, template_values or [], template_tables)
            title = f"{template['name']} — {document.title}"[:200]
            return await _save(context, title, html, confirmed, template_source={
                'template_uuid': template_uuid, 'template_check': check,
            })
        except HTTPException as exc:
            return {'error': exc.detail}
    if source_document_uuid or template_values or template_tables:
        return {'error': 'Choose a template before filling its fields.'}
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


async def _save(context: RunContext[AgenticChatDeps], title: str, html: str, confirmed: bool, artifact_uuid: str | None=None, base_revision: str | None=None, template_source: dict | None=None) -> dict:
    from app.services.chat_tools import _confirm_gate
    conversation = context.deps.conversation
    if conversation is None:
        return {"error": "Start a chat conversation before saving a Page."}
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
            conversation.uuid, title, html, artifact_uuid, base_revision, {**_source(context), **(template_source or {})})
        digest = hashlib.sha256((title + snapshot["prepared_html"]).encode()).hexdigest()
        gate = await _confirm_gate(context, tool_name=name,
            key={"artifact": artifact_uuid, "base": base_revision, "sha256": digest}, confirmed=confirmed,
            preview={"needs_confirmation": True, "action": name,
                     "preview": f'Save a private Page: {title}. This does not publish it.',
                     "preview_id": snapshot["_id"], "title": snapshot["title"],
                     "template_check": snapshot["source"].get("template_check"),
                     "artifact_preview_html": snapshot["prepared_html"], "warnings": snapshot["warnings"], "rendering_note": RENDERING_NOTE,
                     "source_fidelity_note": PAGE_SOURCE_FIDELITY_RULES, "language_note": PAGE_LANGUAGE_RULES})
        if gate is not None:
            return gate
        saved = await _call(chat_page_previews.save, context.deps.user_id,
            conversation.uuid, snapshot["_id"])
        return {**saved, "rendering_note": RENDERING_NOTE,
                "source_fidelity_note": PAGE_SOURCE_FIDELITY_RULES, "language_note": PAGE_LANGUAGE_RULES}
    except HTTPException as exc:
        return {"error": exc.detail}
