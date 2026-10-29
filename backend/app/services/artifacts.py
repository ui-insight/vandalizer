"""Common persistence and static rendering for chat and workflow artifacts.

MongoDB stores self-contained HTML with no external assets. Atomic append/CAS
keeps revisions immutable and avoids transactions on standalone deployments.
25 x 256 KiB stays well below MongoDB's document size limit.
"""
import hashlib
import secrets
import re
from datetime import datetime, timezone
from html import escape
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Comment
from fastapi import HTTPException
from pymongo import ReturnDocument

from app.services.page_links import prepare_page_links

MAX_HTML_BYTES = 262144
PAGE_TOO_LARGE_MESSAGE = "This page is too large; try fewer rows or tabs, or split it into pages."
MAX_REVISIONS = 25
CONTENT_CSP = (
    "sandbox; default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; "
    "img-src data:; font-src data:; connect-src 'none'; frame-src 'none'; "
    "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
)
ALLOWED_TAGS = set("html head body title style main section article header footer aside nav div span p h1 h2 h3 h4 h5 h6 ul ol li dl dt dd table thead tbody tfoot tr th td caption colgroup col pre code blockquote strong b em i u s del small sub sup mark br hr a img details summary figure figcaption time address".split())
ALLOWED_ATTRS = {"class", "id", "style", "title", "lang", "dir", "role", "aria-label", "colspan", "rowspan", "scope", "width", "height", "alt", "open", "start", "value"}


def clean_html(html: str, title: str) -> tuple[str, list[str]]:
    if not html.strip() or not title.strip():
        raise HTTPException(422, "A title and HTML content are required.")
    try:
        size = len(html.encode("utf-8"))
        title.encode("utf-8")
    except UnicodeError as exc:
        raise HTTPException(422, "Page text must be valid Unicode.") from exc
    if size > MAX_HTML_BYTES:
        raise HTTPException(422, PAGE_TOO_LARGE_MESSAGE + " Pages support at most 256 KiB of self-contained HTML.")
    soup = BeautifulSoup(html, "html.parser")
    removed = False
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    for tag in list(soup.find_all(True)):
        if tag.name is None:
            continue
        if tag.name not in ALLOWED_TAGS:
            report_removal = tag.name != "meta" or str(tag.get("http-equiv", "")).lower() == "refresh"
            tag.decompose()
            removed = removed or report_removal
            continue
        for attr in list(tag.attrs):
            value = tag.attrs[attr]
            if attr == "href" and tag.name == "a" and isinstance(value, str):
                try:
                    scheme = urlsplit(value).scheme.lower()
                except ValueError:
                    scheme = ""
                if value.startswith("#") or scheme in {"https", "http", "mailto"}:
                    continue
            elif tag.name == "a" and attr in {"target", "rel", "referrerpolicy"}:
                # Replaced by prepare_page_links, never trusted as authored.
                continue
            elif attr == "src" and tag.name == "img" and isinstance(value, str):
                if value.lower().startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/gif;base64,", "data:image/webp;base64,")):
                    continue
            elif attr in ALLOWED_ATTRS:
                continue
            del tag.attrs[attr]
            removed = True
    # Reconstruct one document so authored heads, encoding, and CSP cannot override ours.
    styles = "".join(str(t) for t in soup.find_all("style"))
    for tag in soup.find_all(["style", "title"]):
        tag.extract()
    if not soup.body:
        for tag in soup.find_all(["html", "head"]):
            tag.unwrap()
    body = soup.body.decode_contents() if soup.body else str(soup)
    result = f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{CONTENT_CSP}"><title>{escape(title)}</title>{styles}</head><body>{body}</body></html>'
    result, _ = prepare_page_links(result, CONTENT_CSP)
    if len(result.encode("utf-8")) > MAX_HTML_BYTES:
        raise HTTPException(422, PAGE_TOO_LARGE_MESSAGE + " Rendered page exceeds 256 KiB. Reduce content or inline images.")
    return result, [
        "Unsupported HTML, scripts, or remote assets were removed. Review this preview before saving or sharing. "
        "Data rendered only by scripts will be missing. Use full HTML tables and static CSS charts; "
        "JavaScript charts, filters and table sorting are not supported. "
        "Jump links, expandable sections, and web or email links can still be used."
    ] if removed else []


def _revision(title, html, base="", source=None):
    content, warnings = clean_html(html, title)
    digest = hashlib.sha256((title.strip() + "\n" + content).encode()).hexdigest()
    return {"uuid": hashlib.sha256((base + digest).encode()).hexdigest()[:32], "title": title.strip(),
            "html": content, "sha256": digest, "warnings": warnings,
            "created_at": datetime.now(timezone.utc), "source": source or {"kind": "editor"}}


def create(db, user_id, title, html, request_id, source=None):
    uid = hashlib.sha256(f"{user_id}\0{request_id}".encode()).hexdigest()[:32]
    revision = _revision(title, html, source=source)
    now = datetime.now(timezone.utc)
    doc = db.html_artifacts.find_one_and_update({"uuid": uid}, {"$setOnInsert": {
        "uuid": uid, "user_id": user_id, "team_id": None, "team_revision": None, "revisions": [revision],
        "title": title, "source": source or {"kind": "editor"}, "project_uuid": (source or {}).get("project_uuid"),
        "latest_revision": revision["uuid"], "published_revision": None, "public_token": None, "publications": [],
        "created_at": now, "updated_at": now, "deleted_at": None,
    }}, upsert=True, return_document=ReturnDocument.AFTER)
    if doc.get("deleted_at"):
        raise HTTPException(410, "This page was deleted. Start a new page.")
    if doc["revisions"][0]["sha256"] != revision["sha256"]:
        raise HTTPException(409, "This save request was already used for different content.")
    return doc


def rename(db, doc, title):
    """Change the owner's library name without modifying immutable versions."""
    saved = db.html_artifacts.find_one_and_update({
        "uuid": doc["uuid"], "user_id": doc["user_id"], "deleted_at": None,
    }, {"$set": {"title": title, "updated_at": datetime.now(timezone.utc)}}, return_document=ReturnDocument.AFTER)
    if not saved:
        raise HTTPException(404, "Page not found")
    return saved


def duplicate(db, doc, user_id, request_id):
    """Copy the latest accessible version; never inherit sharing or provenance."""
    key = f"duplicate:{doc['uuid']}:{request_id}"
    uid = hashlib.sha256(f"{user_id}\0{key}".encode()).hexdigest()[:32]
    existing = db.html_artifacts.find_one({"uuid": uid, "user_id": user_id})
    if existing:
        if existing.get("deleted_at"):
            raise HTTPException(410, "The duplicate was deleted. Start a new copy.")
        return existing
    current = revision(doc)
    title = f"Copy of {doc.get('title') or current['title']}"[:200]
    return create(db, user_id, title, current["html"], key, {
        "kind": "editor", "copied_from": doc["uuid"], "copied_revision": current["uuid"],
    })


def get(db, uuid):
    doc = db.html_artifacts.find_one({"uuid": uuid, "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Page not found")
    return doc


def revision(doc, uuid=None):
    selected = next((r for r in doc["revisions"] if r["uuid"] == (uuid or doc["latest_revision"])), None)
    if not selected:
        raise HTTPException(404, "Page revision not found")
    return selected


def revise(db, doc, title, html, base_revision, source=None):
    new = _revision(title, html, base_revision, source)
    if any(r["uuid"] == new["uuid"] for r in doc["revisions"]):
        return doc  # a retried save must not append again
    if len(doc["revisions"]) >= MAX_REVISIONS:
        raise HTTPException(422, "This page has 25 revisions. Create a new page to continue.")
    _pin_legacy_team_revision(db, doc)
    saved = db.html_artifacts.find_one_and_update({
        "uuid": doc["uuid"], "user_id": doc["user_id"], "deleted_at": None,
        "latest_revision": base_revision,
    }, {"$push": {"revisions": new}, "$set": {"title": title, "latest_revision": new["uuid"], "updated_at": new["created_at"]}}, return_document=ReturnDocument.AFTER)
    if not saved:
        # Identical approvals may race. Return the winning immutable revision
        # rather than reporting a conflict for an already-completed save.
        latest = get(db, doc["uuid"])
        if any(r["uuid"] == new["uuid"] for r in latest["revisions"]):
            return latest
        raise HTTPException(409, "This page changed. Reload before saving another revision.")
    return saved


def team_revision(doc):
    """Existing shares default to publication (or latest), never all history."""
    if not doc.get("team_id"):
        return None
    return doc.get("team_revision") or doc.get("published_revision") or doc["latest_revision"]


def team_view(doc):
    selected = team_revision(doc)
    if not selected:
        raise HTTPException(404, "Page not found")
    visible = revision(doc, selected)
    number = visible.get("version") or next(i for i, r in enumerate(doc["revisions"], 1) if r["uuid"] == selected)
    return {**doc, "title": visible["title"], "latest_revision": selected,
            # Preserve the page's origin before narrowing revision history.
            "source": doc.get("source") or doc["revisions"][0].get("source", {}),
            "team_revision": selected, "revisions": [{**visible, "version": number}],
            "published_revision": selected if selected == doc.get("published_revision") else None,
            "updated_at": visible["created_at"]}


def _pin_legacy_team_revision(db, doc) -> None:
    # Freeze old shares before changing latest/publication. Otherwise removing a
    # public link or saving a draft would silently expose a different revision.
    if doc.get("team_id") and not doc.get("team_revision"):
        db.html_artifacts.update_one({"uuid": doc["uuid"], "deleted_at": None,
            "team_id": doc["team_id"], "team_revision": None,
            "latest_revision": doc["latest_revision"], "published_revision": doc.get("published_revision")},
            {"$set": {"team_revision": team_revision(doc)}})


def share_team(db, doc, team_id, selected=None):
    selected = (selected or team_revision(doc) or doc.get("published_revision") or doc["latest_revision"]) if team_id else None
    if selected:
        revision(doc, selected)
    saved = db.html_artifacts.find_one_and_update({"uuid": doc["uuid"], "user_id": doc["user_id"], "deleted_at": None},
        {"$set": {"team_id": team_id, "team_revision": selected}}, return_document=ReturnDocument.AFTER)
    if not saved:
        raise HTTPException(404, "Page not found")
    return saved


def visible_metadata_stages(user_id):
    """Select the visible title/date BEFORE search, sort, and pagination."""
    owner = {"$eq": ["$user_id", user_id]}
    selected = {"$cond": [owner, "$latest_revision",
        {"$ifNull": ["$team_revision", {"$ifNull": ["$published_revision", "$latest_revision"]}]}]}
    return [
        {"$project": {"revisions.html": 0}},
        {"$addFields": {"_visible_revision": {"$arrayElemAt": [{"$filter": {
            "input": "$revisions", "as": "revision", "cond": {"$eq": ["$$revision.uuid", selected]},
        }}, 0]}}},
        {"$addFields": {"title": {"$cond": [owner, {"$ifNull": ["$title", "$_visible_revision.title"]}, "$_visible_revision.title"]},
            "updated_at": {"$cond": [owner, "$updated_at", "$_visible_revision.created_at"]}}},
    ]


def metadata(doc, owner=False):
    if not owner:
        doc = team_view(doc)
    current = revision(doc)
    result = {"uuid": doc["uuid"], "title": (doc.get("title") or current["title"]) if owner else current["title"], "latest_revision": doc["latest_revision"],
              "team_id": doc.get("team_id"), "can_manage": owner, "published_revision": doc.get("published_revision"),
              "team_revision": team_revision(doc),
              "revisions": [{**{k: r[k] for k in ("uuid", "title", "created_at", "warnings")},
                             "version": r.get("version", i)} for i, r in enumerate(doc["revisions"], 1)]}
    result["created_at"] = doc.get("created_at")
    result["updated_at"] = doc.get("updated_at")
    source = doc.get("source") or doc["revisions"][0].get("source", {})
    # The origin label is shared; source identifiers and provenance are private.
    result["source"] = source if owner else {"kind": source.get("kind", "editor")}
    if owner:
        result["public_token"] = doc.get("public_token")
        result["publications"] = doc.get("publications", [])
    return result


def publish_separate(db, doc, selected):
    """One revocable, immutable public link per explicitly published revision."""
    revision(doc, selected)
    saved = db.html_artifacts.find_one_and_update({
        "uuid": doc["uuid"], "user_id": doc["user_id"], "deleted_at": None,
        "publications.revision": {"$ne": selected},
    }, {"$push": {"publications": {
        "revision": selected, "token": secrets.token_urlsafe(32),
        "published_at": datetime.now(timezone.utc),
    }}}, return_document=ReturnDocument.AFTER)
    # Concurrent/retried publication reuses the winning link. Never append a
    # second token for the same version or overwrite another version's link.
    return saved if saved is not None else get(db, doc["uuid"])


def unpublish_separate(db, doc, selected) -> None:
    revision(doc, selected)
    db.html_artifacts.update_one({"uuid": doc["uuid"], "user_id": doc["user_id"], "deleted_at": None},
        {"$pull": {"publications": {"revision": selected}}})


def publish(db, doc, selected):
    revision(doc, selected)
    _pin_legacy_team_revision(db, doc)
    return db.html_artifacts.find_one_and_update({"uuid": doc["uuid"], "deleted_at": None}, {
        "$set": {"published_revision": selected, "public_token": doc.get("public_token") or secrets.token_urlsafe(32)},
    }, return_document=ReturnDocument.AFTER)


def unpublish(db, doc) -> None:
    _pin_legacy_team_revision(db, doc)
    db.html_artifacts.update_one({"uuid": doc["uuid"], "user_id": doc["user_id"], "deleted_at": None},
        {"$set": {"public_token": None, "published_revision": None}})


def workflow_html(output, title):
    """Render report content without chat transcript titles or role headings."""
    def has_file(value):
        if isinstance(value, dict):
            return value.get("type") == "file_download" or any(has_file(v) for v in value.values())
        return isinstance(value, list) and any(has_file(v) for v in value)
    if has_file(output):
        raise HTTPException(422, "Use the text or HTML step output to create a page, not a binary file.")
    if isinstance(output, str):
        text = output.strip()
        if text.startswith('```html') and text.endswith('```'):
            text = text[7:-3].strip()
        if re.match(r"<(?:!doctype|html|head|body|main|section|article|div|style|h[1-6])\b", text, re.I):
            return text
    from app.services.workflow_pages import render_report_markdown
    from app.services.output_handlers import _render_chainable_text
    content = _render_chainable_text(output, title)
    return render_report_markdown(content)


def from_workflow(db, result, user_id, step=None, *, recreate_deleted=False):
    if result.get("status") != "completed":
        raise HTTPException(409, "Finish the workflow before creating its page.")
    session_id = result["session_id"]
    request_id = f"workflow:{session_id}:{step or 'final'}"
    base_request_id = request_id
    replacing_deleted = False
    while True:
        uid = hashlib.sha256(f"{user_id}\0{request_id}".encode()).hexdigest()[:32]
        existing = db.html_artifacts.find_one({"uuid": uid, "user_id": user_id})
        if existing is None:
            if replacing_deleted and not recreate_deleted:
                raise HTTPException(410, "This page was deleted. Use Save as page on the completed run to create a new page.")
            break
        if existing.get("deleted_at"):
            # A deterministic successor keeps repeated/concurrent saves on one
            # new Page, without reviving the deleted Page or its shared links.
            request_id = f"{base_request_id}:after:{existing['uuid']}"
            replacing_deleted = True
            continue
        # Retries reuse immutable saved content, even after a renderer update
        # or a source rename. Never replace an edited or published page.
        return existing
    workflow = db.workflow.find_one({"_id": result.get("workflow")}) or {}
    from app.services.workflow_pages import report_page, workflow_source
    source = workflow_source(db, result, workflow)
    title = source["workflow_name"][:200]
    output = (result.get("final_output") or {}).get("output")
    if step:
        if step not in (result.get("steps_output") or {}):
            raise HTTPException(404, "Workflow step output not found")
        output = result["steps_output"][step].get("output")
    if output is None or output == "":
        raise HTTPException(422, "This workflow has no output to save.")
    activity = db.activity_event.find_one({"workflow_session_id": session_id, "user_id": user_id}) or {}
    title, html = report_page(workflow_html(output, title), title, source)
    return create(db, user_id, title, html, request_id, {
        **source,
        "kind": "workflow", "workflow_id": str(result.get("workflow", "")), "session_id": session_id, "step": step,
        "project_uuid": activity.get("project_uuid"),
    })


def deliver_workflow_artifact(db, result, user_id):
    """Idempotent output delivery, with a visible failure and a manual retry path."""
    failure = "The HTML page could not be created. Use Save as page on the completed run to retry."
    try:
        doc = from_workflow(db, result, user_id)
        db.workflow_result.update_one({"_id": result["_id"]}, {
            "$set": {"hosted_artifact_uuid": doc["uuid"]}, "$pull": {"delivery_failures": failure},
        })
        return {"status": "completed", "artifact_uuid": doc["uuid"]}
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Page delivery failed for workflow run %s", result.get("session_id"))
        db.workflow_result.update_one({"_id": result["_id"]}, {"$addToSet": {"delivery_failures": failure}})
        return {"status": "failed", "error": failure}


def output_enabled(config):
    setting = config.get("artifact") if isinstance(config, dict) else None
    return isinstance(setting, dict) and setting.get("enabled") is True
