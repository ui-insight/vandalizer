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
    if len(result.encode("utf-8")) > MAX_HTML_BYTES:
        raise HTTPException(422, PAGE_TOO_LARGE_MESSAGE + " Rendered page exceeds 256 KiB. Reduce content or inline images.")
    return result, [
        "Unsupported HTML, scripts, or remote assets were removed. Review this preview before saving or sharing. "
        "Data rendered only by scripts will be missing. Use full HTML tables and static CSS charts; "
        "JavaScript charts, filters and table sorting are not supported."
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
        "uuid": uid, "user_id": user_id, "team_id": None, "revisions": [revision],
        "title": title, "source": source or {"kind": "editor"}, "project_uuid": (source or {}).get("project_uuid"),
        "latest_revision": revision["uuid"], "published_revision": None, "public_token": None,
        "created_at": now, "updated_at": now, "deleted_at": None,
    }}, upsert=True, return_document=ReturnDocument.AFTER)
    if doc.get("deleted_at"):
        raise HTTPException(410, "This page was deleted. Start a new page.")
    if doc["revisions"][0]["sha256"] != revision["sha256"]:
        raise HTTPException(409, "This save request was already used for different content.")
    return doc


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
    saved = db.html_artifacts.find_one_and_update({
        "uuid": doc["uuid"], "user_id": doc["user_id"], "deleted_at": None,
        "latest_revision": base_revision,
    }, {"$push": {"revisions": new}, "$set": {"title": title, "latest_revision": new["uuid"], "updated_at": new["created_at"]}}, return_document=ReturnDocument.AFTER)
    if not saved:
        raise HTTPException(409, "This page changed. Reload before saving another revision.")
    return saved


def metadata(doc, owner=False):
    current = revision(doc)
    result = {"uuid": doc["uuid"], "title": current["title"], "latest_revision": doc["latest_revision"],
              "team_id": doc.get("team_id"), "can_manage": owner, "published_revision": doc.get("published_revision"),
              "revisions": [{k: r[k] for k in ("uuid", "title", "created_at", "warnings")} for r in doc["revisions"]]}
    result["created_at"] = doc.get("created_at")
    result["updated_at"] = doc.get("updated_at")
    if owner:
        result["public_token"] = doc.get("public_token")
        result["source"] = doc.get("source") or doc["revisions"][0].get("source", {})
    return result


def publish(db, doc, selected):
    revision(doc, selected)
    return db.html_artifacts.find_one_and_update({"uuid": doc["uuid"], "deleted_at": None}, {
        "$set": {"published_revision": selected, "public_token": doc.get("public_token") or secrets.token_urlsafe(32)},
    }, return_document=ReturnDocument.AFTER)


def workflow_html(output, title):
    """HTML strings stay HTML; structured/text output uses the shared transcript renderer."""
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
    from app.schemas.chat_export import ChatExportRequest
    from app.services.chat_export import render_chat_export
    from app.services.output_handlers import _render_chainable_text
    content = _render_chainable_text(output, title)
    return render_chat_export(ChatExportRequest(format="html", messages=[{"role": "assistant", "content": content}])).decode()


def from_workflow(db, result, user_id, step=None):
    if result.get("status") != "completed":
        raise HTTPException(409, "Finish the workflow before creating its page.")
    workflow = db.workflow.find_one({"_id": result.get("workflow")}) or {}
    title = (workflow.get("name") or "Workflow output")[:200]
    output = (result.get("final_output") or {}).get("output")
    if step:
        if step not in (result.get("steps_output") or {}):
            raise HTTPException(404, "Workflow step output not found")
        output = result["steps_output"][step].get("output")
    if output is None or output == "":
        raise HTTPException(422, "This workflow has no output to save.")
    session_id = result["session_id"]
    activity = db.activity_event.find_one({"workflow_session_id": session_id, "user_id": user_id}) or {}
    return create(db, user_id, title, workflow_html(output, title), f"workflow:{session_id}:{step or 'final'}", {
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
