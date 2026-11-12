"""Skill-compatible artifact tools using the existing prior-turn approval gate."""
import functools
from typing import Callable, Concatenate, ParamSpec, TypeVar
from pymongo.database import Database
import hashlib
import re
from datetime import datetime

import anyio
from fastapi import HTTPException
from pydantic_ai.tools import RunContext

from app.services.chat_deps import AgenticChatDeps
from app.services import artifacts, chat_page_previews, page_sources
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


MAX_FOUND_PAGES = 20


def name_pattern(name: str) -> str | None:
    """A title regex that matches every word of *name*, in any order.

    Support ticket: a page asked for as "NIH R01 Budget Dashboard — 5-Year
    Breakdown" must match whatever dash or quotes the saved title uses.
    """
    words = re.findall(r"[^\W_]+", name or "", flags=re.UNICODE)
    if not words:
        return None
    return "".join(f"(?=.*{re.escape(word)})" for word in words[:12])


def version_status(meta: dict) -> dict:
    """Which version is latest, which the public link shows, and which the team sees.

    Support ticket: find_pages said only "published": true, so chat told a
    user the latest version (8) was the published one while the public link
    still showed version 4. Each is a separate pointer; report all three.
    """
    numbers = {r["uuid"]: r.get("version", i) for i, r in enumerate(meta["revisions"], 1)}
    latest = numbers.get(meta["latest_revision"], len(meta["revisions"]))
    if not meta.get("can_manage"):
        # A teammate's view holds only the shared version; other versions and
        # publishing are the owner's and are not visible here.
        return {"version": latest, "team_version": latest, "publication_note": (
            f"Shared with your team at version {latest}. Only the owner can see other versions "
            "or which version the public link shows.")}
    published = numbers.get(meta.get("published_revision") or "")
    team = numbers.get(meta.get("team_revision") or "") if meta.get("team_id") else None
    status: dict = {"version": latest, "latest_version": latest, "published": published is not None,
                    "published_version": published}
    if team is not None:
        status["team_version"] = team
    # Versions published on their own links (Share → version links), apart
    # from the main public link.
    separate = sorted({numbers[p["revision"]] for p in meta.get("publications") or [] if p.get("revision") in numbers})
    if separate:
        status["versions_with_own_links"] = separate
    if published is None:
        status["publication_note"] = (
            "No main public link." + (f" Versions with their own links: {', '.join(map(str, separate))}." if separate
                                      else " Not published.")
        )
    elif published == latest:
        status["publication_note"] = f"The public link shows version {published}, the latest."
    else:
        newer = f"version {latest}" if latest == published + 1 else f"versions {published + 1}–{latest}"
        status["publication_note"] = (
            f"The public link shows version {published}; the latest saved is version {latest}, "
            f"so {newer} {'is' if latest == published + 1 else 'are'} not published yet."
        )
    return status


def _find_pages(db: Database[dict], user_id: str, team_ids: list[str], name: str, limit: int) -> dict:
    conditions: list[dict] = [{"deleted_at": None}, {"$or": [{"user_id": user_id}, {"team_id": {"$in": team_ids}}]}]
    pipeline: list[dict] = [{"$match": {"$and": conditions}}, *artifacts.visible_metadata_stages(user_id)]
    pattern = name_pattern(name)
    if pattern:
        pipeline.append({"$match": {"title": {"$regex": pattern, "$options": "is"}}})
    pipeline.append({"$facet": {
        "items": [{"$sort": {"updated_at": -1, "uuid": 1}}, {"$limit": limit}],
        "total": [{"$count": "value"}],
    }})
    result: dict = next(db.html_artifacts.aggregate(pipeline), {"items": [], "total": []})
    items = []
    for doc in result["items"]:
        meta = artifacts.metadata(doc, doc["user_id"] == user_id)
        updated = meta.get("updated_at")
        items.append({
            "artifact_uuid": meta["uuid"], "title": meta["title"],
            **version_status(meta),
            "updated_at": updated.isoformat() if isinstance(updated, datetime) else updated,
            "yours": meta["can_manage"], "shared_with_team": bool(meta.get("team_id")),
            "link": f"/pages/{meta['uuid']}",
        })
    return {"items": items, "total": result["total"][0]["value"] if result["total"] else 0}


async def find_pages(context: RunContext[AgenticChatDeps], name: str = "", limit: int = 10) -> dict:
    """Find the user's saved Pages (Files → Pages), and Pages shared with their team, by name.

    Use it whenever the user names a Page or asks to see, open, change or update
    one, and for "show me my pages" (leave name empty for the most recent).
    latest_version, published_version (what the public link shows; null when
    unpublished) and team_version (what the team sees) are separate: report
    them as given, using publication_note, and never assume the latest is the
    published one. Every
    word of name must appear in the title, in any order. Then read a result with
    get_html_artifact(artifact_uuid) before revising it. Only Pages marked yours
    can be revised; for a team Page, say only its owner can change it and offer
    to make the change in a copy (Duplicate on the Page). If nothing matches,
    say plainly you couldn't find a Page called that and suggest opening it
    from Files → Pages and choosing Request changes. Never answer from a Page
    template or a document instead.
    """
    from app.services import access_control
    limit = max(1, min(int(limit or 10), MAX_FOUND_PAGES))
    access = await access_control.get_team_access_context(context.deps.user)
    team_ids = [str(t) for t in (access.team_uuids | access.team_object_ids)]
    found = await _call(_find_pages, context.deps.user_id, team_ids, name, limit)
    if not found["items"]:
        found["note"] = (
            f"No saved Page matches “{name}”. Tell the user you couldn't find a Page called that, "
            "and suggest opening it from Files → Pages and choosing Request changes, or asking to list their Pages."
            if name.strip() else "The user has no saved Pages yet."
        )
    elif found["total"] > len(found["items"]):
        found["note"] = f"Showing {len(found['items'])} of {found['total']} matching Pages, most recently updated first."
    return found



def _revision_by_version(doc: dict, version: int | None) -> dict:
    if version is None:
        return artifacts.revision(doc)
    for number, entry in enumerate(doc["revisions"], 1):
        if entry.get("version", number) == version:
            return dict(entry)
    raise HTTPException(404, f"This Page has no version {version}; it has versions 1 to {len(doc['revisions'])}.")


async def get_html_artifact(context: RunContext[AgenticChatDeps], artifact_uuid: str, version: int | None = None) -> dict:
    """Read your own page's saved HTML: the latest version, or an earlier one by number.

    Revise from the latest version (omit version). Pass version to read an
    older saved version, e.g. to quote what it said; to answer "what changed",
    use compare_page_versions instead.
    Generated HTML is not source evidence. Read the original documents to verify
    values and source notes before revising a document-based page.
    """
    try:
        doc = await _call(artifacts.get, artifact_uuid)
        if doc["user_id"] != context.deps.user_id:
            return {"error": "Page not found or you do not own it."}
        rev = _revision_by_version(doc, version)
        # The files the version read was built from (an older version may
        # cite an older file version than the latest one does).
        sources = await _call(page_sources.freshness, page_sources.revision_sources(rev), changes=True)
        sources = await page_sources.hide_unreadable_versions(sources, context.deps.user)
        return {"artifact_uuid": doc["uuid"], "title": rev["title"], "revision": rev["uuid"], "html": rev["html"],
                # status "updated" names the newer version (latest.uuid) and what
                # changed; rebuild every affected value from that file.
                "source_files": sources,
                "version": next(i for i, entry in enumerate(doc["revisions"], 1) if entry["uuid"] == rev["uuid"]),
                "is_latest": rev["uuid"] == doc["latest_revision"], "change_summary": rev.get("change_summary"),
                **{k: v for k, v in version_status(artifacts.metadata(doc, True)).items() if k != "version"},
                "warnings": rev["warnings"], "rendering_note": RENDERING_NOTE,
                "source_fidelity_note": PAGE_SOURCE_FIDELITY_RULES, "language_note": PAGE_LANGUAGE_RULES}
    except HTTPException as exc:
        return {"error": exc.detail}


async def compare_page_versions(context: RunContext[AgenticChatDeps], artifact_uuid: str, from_version: int, to_version: int | None = None) -> dict:
    """Compare two saved versions of your Page: what changed from from_version to to_version (latest if omitted).

    Returns changed figures (label, old, new), sections added and removed, other
    text edits, and design-only changes, each computed from the saved HTML.
    Report them as given: list every changed figure with old → new, then the
    sections, then text edits; mention design changes separately. Each version
    also has a one-line change_summary.
    """
    from app.services.page_diff import compare
    try:
        doc = await _call(artifacts.get, artifact_uuid)
        if doc["user_id"] != context.deps.user_id:
            return {"error": "Page not found or you do not own it."}
        old = _revision_by_version(doc, from_version)
        new = _revision_by_version(doc, to_version)
        number = {r["uuid"]: r.get("version", i) for i, r in enumerate(doc["revisions"], 1)}
        diff = await anyio.to_thread.run_sync(compare, old["html"], new["html"])
        summaries = [{"version": r.get("version", i), "change_summary": r.get("change_summary")}
                     for i, r in enumerate(doc["revisions"], 1) if number[old["uuid"]] < r.get("version", i) <= number[new["uuid"]]]
        return {"artifact_uuid": doc["uuid"], "from_version": number[old["uuid"]], "to_version": number[new["uuid"]],
                **diff, "versions_between": summaries}
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
            }, source_documents=[document.uuid])
        except artifacts.PageTooLargeError:
            raise
        except HTTPException as exc:
            return {'error': exc.detail}
    # Support ticket: "make a one-page award snapshot page" was refused with
    # "Choose a template before filling its fields" (a source file was passed
    # without a template), and chat saved a .md file instead.
    if template_values or template_tables:
        return {'error': 'template_values and template_tables only fill a saved Page template, and none was given.',
                'hint': ('To make a new Page, call create_html_artifact again with the complete page in html '
                         '(no template needed), using values you read from the document. Make a Page as asked: '
                         'do not deliver a different kind of output, such as a file, instead.')}
    if not (html or '').strip():
        return {'error': 'Write the Page in html: complete, self-contained HTML/CSS.',
                'hint': 'A source file alone does not make a Page. Read it, then write the page in html.'}
    # A source file passed without a template is simply what the page is
    # built from; it needs no template.
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


def _used_documents(context: RunContext[AgenticChatDeps]) -> list[str]:
    """Files this turn's page was built from: attached files, then files read."""
    used = list(getattr(context.deps, "context_document_uuids", None) or [])
    used += [u for u in getattr(context.deps, "documents_read", None) or [] if u not in used]
    return used


def _source_documents(db: Database[dict], doc: dict | None, used: list[str]) -> list[dict]:
    if doc is None:
        return page_sources.resolve(db, used)
    previous = page_sources.revision_sources(artifacts.revision(doc))
    return page_sources.resolve(db, page_sources.carry_forward(db, previous, used))


def _figure_check_view(result: dict | None) -> dict:
    """The figure check as the preview card and chat see it: the summary, and
    the figures that need attention (manual edits, figures not found)."""
    from app.services import page_figures

    figures = (result or {}).get("figures") or []
    return {
        "summary": page_figures.summary(result),
        "checked": result is not None,
        "manual": [f for f in figures if f["status"] == "manual"][:20],
        "unmatched": [f["figure"] for f in figures if f["status"] == "unmatched"][:20],
        "instruction": (
            "Tell the user this summary. For each figure not found in the source, check it against the "
            "source and fix it, or mark a requested change with data-source-value; never call an "
            "unmatched figure verified."
        ) if result and (result.get("unmatched") or result.get("manual")) else None,
    }


def _annotated(snapshot: dict) -> str:
    """The preview HTML with each figure's origin as hover text (display only)."""
    from bs4 import BeautifulSoup

    from app.services import page_figures

    result = (snapshot.get("source") or {}).get("figure_check")
    if not result:
        return str(snapshot["prepared_html"])
    soup = BeautifulSoup(snapshot["prepared_html"], "html.parser")
    page_figures.annotate(soup, result)
    return str(soup)


async def _save(context: RunContext[AgenticChatDeps], title: str, html: str, confirmed: bool, artifact_uuid: str | None=None, base_revision: str | None=None, template_source: dict | None=None, source_documents: list[str] | None=None) -> dict:
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
        from app.services.inbox_provenance import PAGE_ERROR, credits_inbox
        if not confirmed and credits_inbox(html) and not getattr(context.deps, "inbox_read", False):
            return {"error": PAGE_ERROR}
        documents = await _call(_source_documents, doc, source_documents or _used_documents(context))
        snapshot = await _call(chat_page_previews.prepare, context.deps.user_id,
            conversation.uuid, title, html, artifact_uuid, base_revision,
            {**_source(context), **(template_source or {}), "documents": documents})
        digest = hashlib.sha256((title + snapshot["prepared_html"]).encode()).hexdigest()
        gate = await _confirm_gate(context, tool_name=name,
            key={"artifact": artifact_uuid, "base": base_revision, "sha256": digest}, confirmed=confirmed,
            preview={"needs_confirmation": True, "action": name,
                     "preview": f'Save a private Page: {title}. This does not publish it.',
                     "preview_id": snapshot["_id"], "title": snapshot["title"],
                     "template_check": snapshot["source"].get("template_check"),
                     "figure_check": _figure_check_view(snapshot["source"].get("figure_check")),
                     "artifact_preview_html": _annotated(snapshot), "warnings": snapshot["warnings"], "rendering_note": RENDERING_NOTE,
                     "source_fidelity_note": PAGE_SOURCE_FIDELITY_RULES, "language_note": PAGE_LANGUAGE_RULES})
        if gate is not None:
            return gate
        saved = await _call(chat_page_previews.save, context.deps.user_id,
            conversation.uuid, snapshot["_id"])
        return {**saved, "rendering_note": RENDERING_NOTE,
                "source_fidelity_note": PAGE_SOURCE_FIDELITY_RULES, "language_note": PAGE_LANGUAGE_RULES}
    except artifacts.PageTooLargeError:
        # Do not ask the model to regenerate the same oversized Page this turn.
        # Chat translates this into the actionable size message and stops.
        raise
    except HTTPException as exc:
        return {"error": exc.detail}
